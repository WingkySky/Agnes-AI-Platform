/* =====================================================
 * 画布多元素合并生成核心逻辑
 * - Config 节点 + @[node:xxx] 引用模式
 * - 收集 Config 节点的上游资源（根据连线查找）
 * - 解析 composerContent 中的 @[node:xxx] 引用 token
 * - 文本资源拼到 prompt 末尾，图片资源作为 referenceImages 数组
 * - 调用 /api/images/tasks 创建异步生成任务
 * - 轮询任务状态，完成后回填结果到画布新节点
 * - 同步注册到任务队列（TaskQueue），让画布任务在队列面板中可见
 *
 * 核心数据流：
 *   Config 节点 + 上游资源 + composerContent
 *     → buildGenerationContext() 合并为 { prompt, referenceImages }
 *     → createImageTask() 创建任务
 *     → pollImageTask() 轮询状态（同步更新 TaskQueue）
 *     → 回填结果到新 image 节点 + 连线
 * ===================================================== */

import { createImageTask, getImageTaskStatus } from '@/api/images'
import { createVideoTask, getVideoStatus } from '@/api/videos'
import { useTaskQueueStore } from '@/stores/taskQueue'
import { useModelsStore } from '@/stores/models'
import { usePreferencesStore } from '@/stores/preferences'
import { isMediaSuccess, isMediaFailed } from '@/lib/media-status'
import { captureVideoFrame, getVideoTime } from '@/lib/canvas-image-ops'
import type { CanvasPanel, CanvasConnection } from '@/stores/canvas'
import type { ImageGenerationRequest, VideoGenerationRequest, GenerationContextPayload } from '@/types'
import { getErrorMessage } from '@/lib/type-helpers'

// ---------- 类型定义 ----------

/** 资源内容：从资源节点提取的内容 */
interface ResourceContent {
  type: 'image' | 'text' | 'video'
  nodeId: string
  imageUrl?: string
  text?: string
  videoUrl?: string
  title: string
}

/** 输入摘要（供 UI 显示） */
interface InputSummary {
  textCount: number
  imageCount: number
  videoCount: number
  total: number
}

/** 上游视频输入：url 供 video2video 直传；panelId 用于降级抽帧时读取该节点当前播放位置 */
interface ReferenceVideo {
  url: string
  panelId: string
}

/** 生成上下文 */
interface GenerationContext {
  prompt: string
  referenceImages: string[]
  /** 上游视频节点（连线收集）；video2video 能力协商与降级抽帧在任务创建层处理 */
  referenceVideos: ReferenceVideo[]
  referenceTexts: string[]
  inputSummary: InputSummary
}

/** 面板类型（对齐 CanvasPanel） */
interface GenerationPanel extends Omit<CanvasPanel, 'content'> {
  content: Record<string, any>
}

/** 连线类型（对齐 CanvasConnection） */
type GenerationConnection = CanvasConnection

/** Canvas Store 接口（抽象） */
export interface CanvasGenerationStore {
  panels: GenerationPanel[]
  connections: GenerationConnection[]
  addPanel(panel: Record<string, any>): string | undefined
  addConnection(conn: Record<string, any>): void
  updatePanel(id: string, updates: Record<string, any>): void
  pushSnapshot(): void
}

/** 生成任务配置 */
interface GenerationConfig {
  model?: string
  size?: string
  response_format?: 'url' | 'b64_json'
  seconds?: number
  aspect_ratio?: string
  resolution?: number
  frame_rate?: number
  use_keyframes?: boolean  // 是否使用关键帧模式（true=keyframes，false=image2video自动识别）
}

/** 生成任务选项 */
interface GenerationOptions {
  onProgress?: (phase: string, data: Record<string, any>) => void
  /** true: 等待生成完成（含轮询回填）后再返回，供批量编排做并发控制；默认立即返回 */
  waitFor?: boolean
}

/**
 * 节点生成参数：字段名对齐 Config 节点 content 与 GenerationConfig
 * Config / image / video 节点共用同一套字段名，ComposerParamBar 与各生成入口无需再做映射
 */
export interface PanelGenParams {
  model: string
  size: string
  aspect_ratio: string
  resolution: number
  frame_rate: number
  seconds: number
}

// ---------- 常量 ----------

/** 节点类型中文名映射 */
const TYPE_NAME_MAP: Record<string, string> = { image: '图片', text: '文本', video: '视频', audio: '音频' }

/**
 * @图片1 / @文本2 等可读标签的正则匹配模式
 * 匹配：@图片1、@文本2、@视频3、@音频4
 * 捕获组：[1]类型中文名, [2]序号数字
 */
const MENTION_PATTERN = /@(图片|文本|视频|音频)(\d+)/g

/** 资源类型标签生成器：图片1、图片2、文本1、视频1...（与节点显示序号一致） */
function resourceLabel(type: string, index: number): string {
  return `${TYPE_NAME_MAP[type] || '资源'}${index}`
}

/**
 * 构建画布创作上下文
 * - 分镜派生节点（content.lineage 含 scriptPanelId）归档到其「剧本」容器，命名 #镜头号
 * - 其余画布节点统一归档到「画布」容器
 * - source=canvas：历史页默认过滤
 */
export function buildCanvasContext(node: GenerationPanel, store: CanvasGenerationStore): GenerationContextPayload {
  const lineage = node.content?.lineage as { scriptPanelId?: unknown; shotNo?: unknown } | undefined
  if (lineage && typeof lineage.scriptPanelId === 'string' && lineage.scriptPanelId) {
    const scriptPanel = store.panels.find((p) => p.id === lineage.scriptPanelId)
    const shotNo = typeof lineage.shotNo === 'number' ? lineage.shotNo : undefined
    return {
      source: 'canvas',
      container_type: 'canvas_script',
      container_id: lineage.scriptPanelId,
      container_name: (scriptPanel?.name as string) || undefined,
      asset_name: shotNo ? `#${shotNo}` : ((node.name as string) || undefined),
    }
  }
  return {
    source: 'canvas',
    container_type: 'canvas',
    container_id: 'canvas',
    asset_name: (node.name as string) || undefined,
  }
}

// ---------- 资源收集 ----------

/**
 * 判断面板是否为资源节点（可作为生成输入）
 * - image / text / video / audio 类型都是资源节点
 * - config / frame / quick-generate 不是资源节点
 */
export function isResourceNode(panel: GenerationPanel | null | undefined): boolean {
  if (!panel) return false
  return ['image', 'text', 'video', 'audio'].includes(panel.type || '')
}

/**
 * 获取指定节点的所有上游资源节点（根据连线查找）
 * - 查找 connections 中 target_panel_id === nodeId 的所有 source_panel_id
 * - 按连接创建时间排序（保证序号与节点显示的1、2、3标记一致）
 * - 过滤掉非资源节点和重复连接
 */
export function getUpstreamNodes(nodeId: string, panels: GenerationPanel[], connections: GenerationConnection[]): GenerationPanel[] {
  // 先按连接创建时间排序
  const incomingConns = connections
    .filter((c) => c.target_panel_id === nodeId)
    .sort((a, b) => {
      const timeA = a.created_at ? new Date(a.created_at as string).getTime() : 0
      const timeB = b.created_at ? new Date(b.created_at as string).getTime() : 0
      return timeA - timeB
    })

  // 去重（同一节点可能有多条连线）
  const seen = new Set<string>()
  const upstreamIds: string[] = []
  for (const conn of incomingConns) {
    if (conn.source_panel_id) {
      const id = conn.source_panel_id as string
      if (!seen.has(id)) {
        seen.add(id)
        upstreamIds.push(id)
      }
    }
  }

  const panelMap = new Map(panels.map((p) => [p.id, p]))
  return upstreamIds
    .map((id) => panelMap.get(id))
    .filter((p): p is GenerationPanel => !!p && isResourceNode(p))
}

/**
 * 获取上游资源节点及其统一序号（与节点上显示的1、2、3标记一致）
 * - 返回 Array<{ panel, index, typeLabel }>，index 从 1 开始，按连接顺序
 */
export function getUpstreamNodesWithIndex(nodeId: string, panels: GenerationPanel[], connections: GenerationConnection[]): Array<{ panel: GenerationPanel; index: number; label: string }> {
  const upstreamPanels = getUpstreamNodes(nodeId, panels, connections)
  return upstreamPanels.map((panel, idx) => {
    const labels: Record<string, string> = { image: '图片', text: '文本', video: '视频', audio: '音频' }
    const typeName = labels[panel.type || 'image'] || '资源'
    return {
      panel,
      index: idx + 1,
      label: `${typeName}${idx + 1}`,
    }
  })
}

/**
 * 从资源节点提取内容
 * - image: 返回 { type: 'image', nodeId, imageUrl, title }
 * - text: 返回 { type: 'text', nodeId, text, title }
 * - video: 返回 { type: 'video', nodeId, videoUrl, title }
 */
function extractResourceContent(panel: GenerationPanel): ResourceContent | null {
  if (!panel) return null
  const c = panel.content || {}
  const title = (panel.name || panel.type || 'Untitled') as string

  switch (panel.type) {
    case 'image':
      return {
        type: 'image',
        nodeId: panel.id,
        title: (panel.name || panel.type || 'Untitled') as string,
        imageUrl: c.content || c.imageUrl || c.image || c.url || '',
      }
    case 'text':
      return {
        type: 'text',
        nodeId: panel.id,
        title: (panel.name || panel.type || 'Untitled') as string,
        text: c.content || c.text || '',
      }
    case 'video':
      return {
        type: 'video',
        nodeId: panel.id,
        title: (panel.name || panel.type || 'Untitled') as string,
        videoUrl: c.content || c.videoUrl || c.url || '',
      }
    default:
      return null
  }
}

// ---------- 生成上下文构建 ----------

/**
 * 合并 config 自带的参考图快照（script 节点批量派生时写入 content.referenceImages，
 * 上游是 script 节点而非资源节点，不依赖运行时上溯）
 */
function withSnapshotImages(ctx: GenerationContext, snapshotImages: string[]): GenerationContext {
  if (snapshotImages.length === 0) return ctx
  return { ...ctx, referenceImages: [...(ctx.referenceImages || []), ...snapshotImages] }
}

/** 附加上游视频节点（image/video 节点连线收集共用） */
function withUpstreamVideos(ctx: GenerationContext, videos: ReferenceVideo[]): GenerationContext {
  if (videos.length === 0) return ctx
  return { ...ctx, referenceVideos: videos }
}

/**
 * 构建生成上下文：解析 @[node:xxx] 引用，合并多资源
 *
 * 合并策略（composer 上下文聚合）：
 * - 如果 configNode 有 composerContent（组装提示词），走引用解析路径：
 *   · 解析 @[node:xxx] token，把引用替换为标签（图片1、文本2...，序号与节点显示一致）
 *   · 文本资源：在 prompt 末尾追加 【文本1】\n内容 块
 *   · 图片资源：作为 referenceImages 数组传给 AI
 * - 如果没有 composerContent，走简单合并路径：
 *   · 节点自身无提示词：上游文本充当提示词来源（拼到 prompt）
 *   · 节点自身有提示词：上游文本不再自动拼接（典型场景：分镜图连剧本节点仅作派生溯源，
 *     剧本全文混入会把单帧提示词污染成叙事多格构图）；需要引用走 @[文本N] 显式引用
 *   · 上游图片始终作为 referenceImages、上游视频作为 video2video 输入
 * - 注意：prompt字段也会走引用解析（不一定非要composerContent）
 */
export function buildGenerationContext(configNode: GenerationPanel, panels: GenerationPanel[], connections: GenerationConnection[]): GenerationContext | null {
  if (!configNode) return null

  // 收集上游资源（带统一序号）
  const upstreamWithIndex = getUpstreamNodesWithIndex(configNode.id, panels, connections)
  const inputs: Array<ResourceContent & { index: number; label: string }> = upstreamWithIndex
    .map(({ panel, index, label }) => {
      const res = extractResourceContent(panel)
      if (!res) return null
      return { ...res, index, label }
    })
    .filter((r): r is ResourceContent & { index: number; label: string } => r !== null)

  // 兼容旧的ResourceContent格式（不带index的）
  const plainInputs: ResourceContent[] = inputs.map(({ index, label, ...rest }) => rest)

  // 获取提示词：优先用 composerContent，其次用 prompt
  const composerContent = configNode.content?.composerContent?.trim()
  const promptContent = configNode.content?.prompt?.trim()
  const hasComposer = !!composerContent
  const contentToParse = composerContent || promptContent || ''

  // 输入摘要（供 UI 显示）
  const inputSummary: InputSummary = {
    textCount: plainInputs.filter((i) => i.type === 'text').length,
    imageCount: plainInputs.filter((i) => i.type === 'image').length,
    videoCount: plainInputs.filter((i) => i.type === 'video').length,
    total: plainInputs.length,
  }

  // 分镜派生 config 的参考图快照（见 canvas-storyboard.ts，随 content 持久化）
  const snapshotImages = Array.isArray(configNode.content?.referenceImages)
    ? configNode.content.referenceImages.filter((u): u is string => typeof u === 'string')
    : []

  // 上游视频节点（video2video 能力协商 / 降级抽帧在任务创建层处理）
  const upstreamVideos: ReferenceVideo[] = plainInputs
    .filter((i) => i.type === 'video' && i.videoUrl)
    .map((i) => ({ url: i.videoUrl!, panelId: i.nodeId }))

  // 如果没有任何需要解析的内容，走简单合并路径
  if (!contentToParse) {
    return withUpstreamVideos(withSnapshotImages(buildSimpleContext(plainInputs, '', inputSummary), snapshotImages), upstreamVideos)
  }

  // 如果有 @图片1/@文本2 等可读标签引用，或使用了composerContent，走引用解析路径
  const hasMention = MENTION_PATTERN.test(contentToParse)
  MENTION_PATTERN.lastIndex = 0 // 重置正则lastIndex
  if (!hasMention && !hasComposer) {
    // 节点自身已有提示词：上游文本不自动拼接（防剧本全文污染单帧提示词），图片/视频参考照常收集
    const nonTextInputs = plainInputs.filter((i) => i.type !== 'text')
    return withUpstreamVideos(withSnapshotImages(buildSimpleContext(nonTextInputs, contentToParse, inputSummary), snapshotImages), upstreamVideos)
  }

  // 走引用解析路径
  return withUpstreamVideos(withSnapshotImages(buildComposerContext(inputs, contentToParse, inputSummary), snapshotImages), upstreamVideos)
}

/**
 * 简单合并路径：所有上游文本拼到 prompt，所有图片作为参考图
 */
function buildSimpleContext(inputs: ResourceContent[], basePrompt: string, inputSummary: InputSummary): GenerationContext {
  const textBlocks = inputs
    .filter((i) => i.type === 'text' && i.text)
    .map((i) => i.text!)

  const referenceImages = inputs
    .filter((i) => i.type === 'image' && i.imageUrl)
    .map((i) => i.imageUrl!)

  const referenceTexts = textBlocks.slice()

  // 把上游文本拼到 prompt 末尾
  let prompt = basePrompt
  if (textBlocks.length > 0) {
    prompt = `${prompt}\n\n${textBlocks.join('\n\n')}`
  }

  return { prompt, referenceImages, referenceVideos: [], referenceTexts, inputSummary }
}

/**
 * 引用解析路径：解析 @图片1/@文本2 等可读标签，按引用合并资源
 *
 * 解析规则（使用统一序号，与节点上显示的1、2、3标记一致）：
 * - @图片1、@文本2 中的"图片"/"文本"是类型，数字是序号
 * - 图片资源：作为 referenceImages 数组，严格按标签序号排列（图片1→[0], 图片2→[1]...）
 * - 文本资源：在 prompt 中被@引用的位置保留 @文本N 标签，同时在末尾追加【文本N】\n内容块
 * - 视频/音频资源：暂不支持，跳过
 * - 未匹配到的标签保留原样
 * - 所有上游资源（无论是否被@引用）：文本按序号追加到末尾，图片全部加入参考图
 */
function buildComposerContext(
  inputs: Array<ResourceContent & { index: number; label: string }>,
  composerContent: string,
  inputSummary: InputSummary
): GenerationContext {
  // 建立 label -> input 的映射（如 "图片1" -> 对应input，"文本2" -> 对应input）
  const inputByLabel = new Map<string, ResourceContent & { index: number; label: string }>()
  for (const input of inputs) {
    inputByLabel.set(input.label, input)
  }
  // 按序号排序的所有上游输入（用于最终收集，确保referenceImages顺序与标签序号一致）
  const sortedInputs = [...inputs].sort((a, b) => a.index - b.index)

  // 第一步：解析 @图片1/@文本2 引用标签
  // - 图片标签（@图片1）：保留在prompt中不动，AI能直接理解
  // - 文本标签（@文本2）：替换为【文本2】格式（与末尾追加的文本块标题一致）
  let nextPrompt = ''
  let lastIndex = 0

  for (const match of composerContent.matchAll(MENTION_PATTERN)) {
    if (match.index === undefined) continue
    const typeName = match[1] // "图片" / "文本" / "视频" / "音频"
    const indexNum = parseInt(match[2], 10) // 1, 2, 3...
    const label = `${typeName}${indexNum}`
    const input = inputByLabel.get(label)

    // 保留匹配之前的原文
    nextPrompt += composerContent.slice(lastIndex, match.index)

    if (input) {
      // 图片/视频：保留 @图片N 标签（AI能自然理解"图片1"指代第一张参考图）
      // 文本：替换为【文本N】格式，与末尾追加的文本块呼应
      nextPrompt += input.type === 'text' ? `【${input.label}】` : match[0]
    } else {
      // 未匹配到的标签保留原样
      nextPrompt += match[0]
    }

    lastIndex = match.index + match[0].length
  }

  // 追加最后一段原文
  nextPrompt += composerContent.slice(lastIndex)

  // 第二步：按序号顺序收集所有文本块和图片
  // 注意：所有上游资源（无论是否被@引用）都会被包含，确保AI能看到全部输入
  // - 文本：按序号追加【标签】\n内容到prompt末尾
  // - 图片：按序号加入referenceImages数组（图片1→第0位，图片2→第1位...）
  const textBlocks: string[] = []
  const selectedImages: string[] = []

  for (const input of sortedInputs) {
    if (input.type === 'text' && input.text) {
      textBlocks.push(`【${input.label}】\n${input.text}`)
    } else if (input.type === 'image' && input.imageUrl) {
      selectedImages.push(input.imageUrl)
    }
  }

  // 把文本块追加到 prompt 末尾
  if (textBlocks.length > 0) {
    nextPrompt = `${nextPrompt.trim()}\n\n${textBlocks.join('\n\n')}`
  }

  return {
    prompt: nextPrompt,
    referenceImages: selectedImages,
    referenceVideos: [],
    referenceTexts: textBlocks,
    inputSummary,
  }
}

// ---------- API 调用与轮询 ----------

/** 轮询连续失败容忍次数（网络抖动/后端重启时不因单次查询失败就判死任务） */
const MAX_POLL_ERRORS = 6

/**
 * 将图片 URL 转为 base64 data URI
 * - blob URL / 本地 URL：fetch 后转 data URI
 * - 公网 URL：直接返回原 URL
 * - data URI：直接返回
 */
async function toBase64IfNeeded(imageUrl: string): Promise<string> {
  if (!imageUrl) return ''
  // data URI 直接返回
  if (imageUrl.startsWith('data:')) return imageUrl
  // 公网 URL 直接返回
  if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')) return imageUrl
  // blob URL 等本地 URL：fetch 后转 data URI
  try {
    const response = await fetch(imageUrl)
    const blob = await response.blob()
    return await new Promise<string>((resolve) => {
      const reader = new FileReader()
      reader.onloadend = () => resolve(reader.result as string)
      reader.readAsDataURL(blob)
    })
  } catch {
    // 转换失败，返回原值（让后端报错更明确）
    return imageUrl
  }
}

/**
 * 把图片 URL 列表分类为 base64 数组和 URL 数组
 * - 公网 URL（http/https）放入 imageUrls
 * - 其余（data URI / base64）放入 base64Images
 * - blob URL 会先转为 data URI 再分类
 */
export async function classifyImages(images: string[]): Promise<{ base64Images: string[]; imageUrls: string[] }> {
  const base64Images: string[] = []
  const imageUrls: string[] = []
  for (const img of images) {
    if (!img) continue
    // 先处理 blob URL 等本地 URL
    const normalized = await toBase64IfNeeded(img)
    if (normalized.startsWith('http://') || normalized.startsWith('https://')) {
      imageUrls.push(normalized.trim())
    } else {
      base64Images.push(normalized)
    }
  }
  return { base64Images, imageUrls }
}

/**
 * 创建图片生成任务（调用 /api/images/tasks）
 * - 根据是否有参考图自动选择 text2image / image2image 模式
 * - 多图参考：base64_images / image_urls 数组
 */
export async function createGenerationTask(
  ctx: GenerationContext,
  config: GenerationConfig,
  context?: GenerationContextPayload,
): Promise<{ task_id: string }> {
  const { prompt, referenceImages } = ctx
  const modelsStore = useModelsStore()
  const model = config.model || modelsStore.defaultImageModel
  // 参考图按所选模型生成能力配置截断（gen_params.max_ref_images，后端仍兜底），无配置不截断；
  // 参考图数组已按「锚点/底图 > 角色 > 场景」优先级排序，截断保留前 N 张
  const imageRefLimit = modelsStore.getModelGenParams(model)?.max_ref_images ?? undefined
  const effectiveRefs = imageRefLimit && referenceImages && referenceImages.length > imageRefLimit
    ? referenceImages.slice(0, imageRefLimit)
    : referenceImages
  const { base64Images, imageUrls } = await classifyImages(effectiveRefs || [])

  const hasReferenceImages = effectiveRefs && effectiveRefs.length > 0
  const params: ImageGenerationRequest = {
    prompt,
    model,
    size: config.size || '1024x1024',
    response_format: config.response_format || 'url',
    mode: hasReferenceImages ? 'image2image' : 'text2image',
    base64_images: base64Images.length > 0 ? base64Images : null,
    image_urls: imageUrls.length > 0 ? imageUrls : null,
    context: context ?? undefined,
  }

  const resp = await createImageTask(params)
  if (!resp || !resp.task_id) {
    throw new Error('创建生成任务失败：未返回 task_id')
  }
  return resp
}

/**
 * 轮询图片/视频任务状态的公共实现
 * - 图片/视频仅 API、间隔、超时、结果字段与提示文案不同（见 MEDIA_POLL_PRESETS）
 * - onProgress 回调用于更新 UI 进度
 * - 同步更新 TaskQueue Store，让画布任务在队列面板中可见
 */
type MediaPollStatusData = {
  status: string
  progress: number
  message?: string | null
  result_url?: string | null
  url?: string | null
  video_url?: string | null
}

interface MediaPollPreset {
  interval: number
  timeout: number
  fetch: (taskId: string) => Promise<MediaPollStatusData>
  pickUrl: (data: MediaPollStatusData) => string
  messages: { timeout: string; queryFailed: string; noResultUrl: string; failed: string; cancelled: string }
}

const MEDIA_POLL_PRESETS: Record<'image' | 'video', MediaPollPreset> = {
  image: {
    interval: 2000,
    timeout: 300000,
    fetch: (taskId) => getImageTaskStatus(taskId),
    pickUrl: (data) => data.result_url || data.url || '',
    messages: {
      timeout: '生成任务超时（超过 5 分钟未完成）',
      queryFailed: '查询任务状态失败',
      noResultUrl: '生成完成但未返回图片 URL',
      failed: '生成失败',
      cancelled: '任务已取消',
    },
  },
  video: {
    interval: 5000,
    timeout: 600000,
    fetch: (taskId) => getVideoStatus(taskId),
    pickUrl: (data) => data.video_url || '',
    messages: {
      timeout: '视频生成任务超时（超过 10 分钟未完成）',
      queryFailed: '查询视频任务状态失败',
      noResultUrl: '视频生成完成但未返回视频 URL',
      failed: '视频生成失败',
      cancelled: '视频任务已取消',
    },
  },
}

async function pollMediaTask(
  preset: MediaPollPreset,
  taskId: string,
  onProgress: ((status: string, data: Record<string, any>) => void) | undefined,
  timeout: number,
): Promise<{ status: string; url: string }> {
  const startTime = Date.now()
  const queueStore = useTaskQueueStore()
  let consecutiveErrors = 0

  while (true) {
    if (Date.now() - startTime > timeout) {
      // 超时，更新队列状态
      queueStore.updateCanvasTask(taskId, { status: 'failed' })
      throw new Error(preset.messages.timeout)
    }

    // 单次查询失败静默重试（网络抖动/后端重启），连续多次才判失败
    let data: MediaPollStatusData | null = null
    try {
      data = await preset.fetch(taskId)
    } catch (_) { /* 按连续错误计数处理 */ }
    if (!data) {
      consecutiveErrors += 1
      if (consecutiveErrors >= MAX_POLL_ERRORS) {
        queueStore.updateCanvasTask(taskId, { status: 'failed' })
        throw new Error(preset.messages.queryFailed)
      }
      await new Promise((resolve) => setTimeout(resolve, preset.interval))
      continue
    }
    consecutiveErrors = 0

    const status = data.status || 'pending'
    if (onProgress) onProgress(status, data)

    // 同步更新任务队列
    if (isMediaSuccess(status)) {
      const url = preset.pickUrl(data)
      if (!url) {
        queueStore.updateCanvasTask(taskId, { status: 'failed' })
        throw new Error(preset.messages.noResultUrl)
      }
      queueStore.updateCanvasTask(taskId, { status: 'success', resultUrl: url, progress: 100 })
      return { status: 'success', url }
    }

    if (isMediaFailed(status)) {
      queueStore.updateCanvasTask(taskId, { status: 'failed' })
      throw new Error(data.message || preset.messages.failed)
    }

    if (status === 'cancelled') {
      queueStore.updateCanvasTask(taskId, { status: 'cancelled' })
      throw new Error(preset.messages.cancelled)
    }

    // 更新进度
    const progress = typeof data.progress === 'number' ? data.progress : undefined
    queueStore.updateCanvasTask(taskId, { status: 'processing', progress })

    // 继续等待
    await new Promise((resolve) => setTimeout(resolve, preset.interval))
  }
}

/**
 * 轮询图片任务状态直到完成
 * - 间隔 2 秒，超时 5 分钟
 * - onProgress 回调用于更新 UI 进度
 * - 同步更新 TaskQueue Store，让画布任务在队列面板中可见
 */
export async function pollImageTask(
  taskId: string,
  onProgress?: (status: string, data: Record<string, any>) => void,
  timeout: number = MEDIA_POLL_PRESETS.image.timeout,
): Promise<{ status: string; resultUrl: string }> {
  const { status, url } = await pollMediaTask(MEDIA_POLL_PRESETS.image, taskId, onProgress, timeout)
  return { status, resultUrl: url }
}

/**
 * 轮询视频任务状态直到完成
 * - 间隔 5 秒，超时 10 分钟
 * - onProgress 回调用于更新 UI 进度
 * - 同步更新 TaskQueue Store，让画布任务在队列面板中可见
 */
export async function pollVideoTask(
  taskId: string,
  onProgress?: (status: string, data: Record<string, any>) => void,
  timeout: number = MEDIA_POLL_PRESETS.video.timeout,
): Promise<{ status: string; videoUrl: string }> {
  const { status, url } = await pollMediaTask(MEDIA_POLL_PRESETS.video, taskId, onProgress, timeout)
  return { status, videoUrl: url }
}

// ---------- 完整生成流程 ----------

/**
 * 计算新结果节点的位置（Config 节点右侧，自动排列）
 * - 返回 { x, y, width, height }
 */
function calcResultNodePosition(configNode: GenerationPanel, isVideo: boolean, index: number) {
  const cols = 4
  const nodeWidth = isVideo ? 320 : 200
  const nodeHeight = isVideo ? 200 : 200
  const gapX = isVideo ? 360 : 220
  const gapY = 240

  return {
    x: (configNode.x ?? 0) + (configNode.width ?? 240) + 40 + (index % cols) * gapX,
    y: (configNode.y ?? 0) + Math.floor(index / cols) * gapY,
    width: nodeWidth,
    height: nodeHeight,
  }
}

/**
 * 在 Config 节点右侧创建一个 loading 状态的结果节点并连线
 * - 返回新节点 ID
 */
export function createLoadingResultNode(store: CanvasGenerationStore, configNode: GenerationPanel, isVideo: boolean, index: number = 0): string {
  const pos = calcResultNodePosition(configNode, isVideo, index)
  const prompt = configNode.content?.prompt || ''

  const newPanel = {
    type: isVideo ? 'video' : 'image',
    x: pos.x,
    y: pos.y,
    width: pos.width,
    height: pos.height,
    content: {
      content: '',
      status: 'loading',
      prompt,
      sourceFrom: configNode.id,
    },
  }

  const newId = store.addPanel(newPanel)

  // 创建连线：Config → 新节点
  if (newId) {
    store.addConnection({
      source_panel_id: configNode.id,
      target_panel_id: newId,
      type: 'auto',
      source_anchor: 'right-middle',
      target_anchor: 'left-middle',
    })
  }

  return newId!
}

/**
 * 执行完整的合并生成流程（异步，不阻塞配置面板）
 * 1. 构建生成上下文（收集上游资源 + 解析 @[node:xxx]）
 * 2. 创建 loading 状态的结果节点（立刻显示在画布上）
 * 3. 创建生成任务 + 注册到任务队列
 * 4. 异步轮询任务状态
 * 5. 轮询完成后回填结果到结果节点（成功/失败都有反馈）
 *
 * @returns 新创建的结果节点 ID（loading 状态）
 */
export async function executeMergeGeneration(configId: string, store: CanvasGenerationStore, options: GenerationOptions = {}): Promise<string> {
  const { onProgress } = options

  // 1. 查找 Config 节点
  const configNode = store.panels.find((p) => p.id === configId)
  if (!configNode || configNode.type !== 'config') {
    throw new Error('未找到 Config 节点')
  }

  // 2. 构建生成上下文
  const ctx = buildGenerationContext(configNode, store.panels, store.connections)
  if (!ctx) {
    throw new Error('构建生成上下文失败')
  }

  if (!ctx.prompt || !ctx.prompt.trim()) {
    throw new Error('提示词为空，请填写 composerContent 或 prompt')
  }

  if (onProgress) onProgress('building', { inputSummary: ctx.inputSummary })

  const config: GenerationConfig = {
    model: configNode.content?.model || useModelsStore().defaultImageModel,
    size: normalizeSize(configNode.content?.size),
    response_format: 'url',
  }

  // 3. 立刻创建 loading 状态的结果节点：数量跟随偏好"默认生成张数"，右侧 4 列网格排布
  const count = Math.max(1, Number(usePreferencesStore().generation?.default_image_count) || 1)
  const aggregated = aggregateProgress(onProgress, count)
  const newNodeIds: string[] = []
  const runs: Promise<boolean>[] = []
  for (let i = 0; i < count; i++) {
    const nodeId = createLoadingResultNode(store, configNode, false, i)
    newNodeIds.push(nodeId)
    runs.push(runMediaTask(
      store,
      nodeId,
      false,
      () => createGenerationTask(ctx, config, buildCanvasContext(configNode, store)),
      (taskId, cb) => pollImageTask(taskId, cb),
      ctx.prompt,
      config.model,
      aggregated,
    ))
  }

  // 4. 异步执行生成 + 轮询 + 回填（默认不阻塞调用方；waitFor=true 时等待全部完成，供批量编排限流）
  if (options.waitFor) {
    await Promise.all(runs)
  }

  // 返回首个新节点 ID（loading 状态）
  return newNodeIds[0]!
}

/**
 * 媒体节点就地生成的上下文：节点自身内容 + 上游连线资源合并
 * - 上游文本拼 prompt、上游图片进 referenceImages（buildGenerationContext 简单合并路径）
 * - 节点自身 referenceImages（分镜直出角色图/源图）保留在前，按 URL 去重
 * - includeUpstream=false（首尾帧模式）不收集上游，只读节点自身内容
 */
function buildMediaNodeContext(panel: CanvasPanel, store: CanvasGenerationStore, includeUpstream: boolean): GenerationContext {
  const ownRefs = Array.isArray(panel.content?.referenceImages)
    ? panel.content.referenceImages.filter((u): u is string => typeof u === 'string')
    : []
  if (!includeUpstream) {
    return {
      prompt: typeof panel.content?.prompt === 'string' ? panel.content.prompt.trim() : '',
      referenceImages: ownRefs,
      referenceVideos: [],
      referenceTexts: [],
      inputSummary: { textCount: 0, imageCount: ownRefs.length, videoCount: 0, total: ownRefs.length },
    }
  }
  const ctx = buildGenerationContext(panel, store.panels, store.connections) ?? {
    prompt: '',
    referenceImages: [],
    referenceVideos: [],
    referenceTexts: [],
    inputSummary: { textCount: 0, imageCount: 0, videoCount: 0, total: 0 },
  }
  const seen = new Set<string>()
  ctx.referenceImages = [...ownRefs, ...ctx.referenceImages].filter((u) => {
    if (!u || seen.has(u)) return false
    seen.add(u)
    return true
  })
  return ctx
}

/** 上游视频降级为参考图：抽各视频当前播放位置的帧（未播放过=0 即首帧；源不可用时抛错让任务显式失败） */
async function videosToCurrentFrames(videos: ReferenceVideo[]): Promise<string[]> {
  const frames: string[] = []
  for (const video of videos.slice(0, 3)) {
    frames.push(await captureVideoFrame(video.url, getVideoTime(video.panelId)))
  }
  return frames
}

/**
 * 执行就地生成（分镜直出节点：结果回填节点自身，不新建结果节点、不加 config 连线）
 * 1. 节点自身内容 + 上游连线资源合并为生成上下文（上游文本拼 prompt、上游图片/视频帧进参考图）
 * 2. 节点置 loading -> 建任务 + 注册队列（panelId 为节点自身，便于队列定位）-> 轮询 -> 回填
 *
 * @returns 节点自身 ID；waitFor 模式下生成失败返回 null（供批量编排汇总失败数，
 *          失败详情已写入节点 content.errorDetails，这里不抛，避免打断并发池其余任务）
 */
export async function executeInNodeGeneration(
  panel: CanvasPanel,
  store: CanvasGenerationStore,
  options: GenerationOptions = {},
): Promise<string | null> {
  const { onProgress } = options

  const ctx = buildMediaNodeContext(panel, store, true)
  if (!ctx.prompt || !ctx.prompt.trim()) {
    throw new Error('提示词为空，请在节点上填写 prompt 或连接上游文本节点')
  }
  const params = readPanelGenParams(panel, 'image')
  const config: GenerationConfig = { model: params.model, size: normalizeSize(params.size), response_format: 'url' }

  // 先置 loading（抽帧可能耗时数秒，需要有反馈）：只写状态字段，不传 referenceImages 数组（deepMerge 会把数组转成索引对象）
  store.updatePanel(panel.id, { content: { status: 'loading', errorDetails: null } })

  const run = () => runMediaTask(
    store,
    panel.id,
    false,
    async () => {
      // 图片生成吃不到视频输入：上游视频节点抽当前播放帧转为参考图；失败走 runMediaTask 统一标错
      if (ctx.referenceVideos.length > 0) {
        const frames = await videosToCurrentFrames(ctx.referenceVideos)
        const seen = new Set(ctx.referenceImages)
        for (const frame of frames) {
          if (!seen.has(frame)) {
            ctx.referenceImages.push(frame)
            seen.add(frame)
          }
        }
        ctx.inputSummary.imageCount = ctx.referenceImages.length
        ctx.referenceVideos = []
      }
      return createGenerationTask(ctx, config, buildCanvasContext(panel, store))
    },
    (taskId, cb) => pollImageTask(taskId, cb),
    ctx.prompt,
    config.model,
    onProgress,
  )

  // waitFor 模式下生成失败返回 null（供批量编排汇总失败数，失败详情已写入节点，这里不抛）
  if (options.waitFor) {
    const ok = await run()
    return ok ? panel.id : null
  }
  void run()
  return panel.id
}

/**
 * 视频节点就地生成（分镜直出）：节点自身承载参数与结果
 * 1. 节点自身内容 + 上游连线资源合并（首尾帧模式只吃节点自身 images，不混上游）；
 *    上游视频按所选模型 capabilities 协商：支持 video2video 走参考视频，否则降级抽首帧
 * 2. 节点置 loading -> 建任务 + 注册队列 -> 轮询 -> 视频地址回填 content.content
 * 失败语义与 executeInNodeGeneration 一致：waitFor 模式返回 null，不打断批量并发池
 */
export async function executeInNodeVideoGeneration(
  panel: CanvasPanel,
  store: CanvasGenerationStore,
  options: GenerationOptions = {},
): Promise<string | null> {
  const { onProgress } = options

  const useKeyframes = panel.content?.use_keyframes === true
  const ctx = buildMediaNodeContext(panel, store, !useKeyframes)
  if (!ctx.prompt.trim() && ctx.referenceImages.length === 0 && ctx.referenceVideos.length === 0) {
    throw new Error('提示词为空且无参考图/参考视频，无法生成视频')
  }
  if (useKeyframes && ctx.referenceImages.length > 2) {
    throw new Error('关键帧模式最多只能使用 2 张参考图（首帧 + 尾帧）')
  }
  const params = readPanelGenParams(panel, 'video')
  // 参考图按所选视频模型的生成能力配置截断（gen_params.max_ref_images，后端仍兜底），无配置不截断
  const videoRefMax = useModelsStore().getModelGenParams(params.model)?.max_ref_images ?? undefined
  const effectiveRefImages = videoRefMax && ctx.referenceImages.length > videoRefMax
    ? ctx.referenceImages.slice(0, videoRefMax)
    : ctx.referenceImages
  const genCtx: GenerationContext = { ...ctx, referenceImages: effectiveRefImages }
  const config: GenerationConfig = {
    model: params.model,
    seconds: params.seconds,
    aspect_ratio: params.aspect_ratio,
    resolution: params.resolution,
    frame_rate: params.frame_rate,
    use_keyframes: useKeyframes,
  }

  // 置 loading：此处只写状态字段，不传 referenceImages 数组（deepMerge 会把数组转成索引对象）
  store.updatePanel(panel.id, { content: { status: 'loading', errorDetails: null } })

  const run = () => runMediaTask(
    store,
    panel.id,
    true,
    () => createVideoGenerationTask(genCtx, config, buildCanvasContext(panel, store)),
    (taskId, cb) => pollVideoTask(taskId, cb),
    genCtx.prompt,
    config.model,
    onProgress,
  )

  // 失败语义与 executeInNodeGeneration 一致：waitFor 模式返回 null，不打断批量并发池
  if (options.waitFor) {
    const ok = await run()
    return ok ? panel.id : null
  }
  void run()
  return panel.id
}

// ---------- 节点生成参数读写 ----------

function readContentString(content: Record<string, unknown>, key: string, fallback: string): string {
  const value = content[key]
  return typeof value === 'string' && value ? value : fallback
}

function readContentNumber(content: Record<string, unknown>, key: string, fallback: number): number {
  const value = content[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

/** 类型谓词：参数子对象（script 节点多套参数分区存放时读取用） */
function isParamsRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * 读取节点上的生成参数，未选择的项回落到该类型的默认参数
 * - 默认值链：节点 content > 用户偏好默认模型（default_image_model_id / default_video_model_id）> 该类型列表第一个（getDefaultModel）
 * - Config / image / video 节点读 content 根字段；script 节点多套参数用 contentKey 分区存放
 * - fallback 用于覆盖逐项回落值（如批量派生沿用偏好比例尺寸、逐镜头时长）
 */
export function readPanelGenParams(
  panel: CanvasPanel | null | undefined,
  mode: 'image' | 'video',
  contentKey?: string,
  fallback?: Partial<PanelGenParams>,
): PanelGenParams {
  const content = panel?.content || {}
  const scoped = contentKey ? content[contentKey] : content
  const source = isParamsRecord(scoped) ? scoped : {}
  const modelsStore = useModelsStore()
  const isVideo = mode === 'video'
  return {
    model: readContentString(source, 'model', fallback?.model ?? modelsStore.getDefaultModel(isVideo ? 'video' : 'image')),
    size: readContentString(source, 'size', fallback?.size ?? modelsStore.defaultImageSize),
    aspect_ratio: readContentString(source, 'aspect_ratio', fallback?.aspect_ratio ?? modelsStore.defaultVideoAspectRatio),
    resolution: readContentNumber(source, 'resolution', fallback?.resolution ?? modelsStore.defaultVideoResolution),
    frame_rate: readContentNumber(source, 'frame_rate', fallback?.frame_rate ?? modelsStore.defaultFrameRate),
    seconds: readContentNumber(source, 'seconds', fallback?.seconds ?? modelsStore.defaultVideoDuration),
  }
}

// ---------- 媒体节点对话框生成（图生图 / 首帧生视频） ----------

/**
 * 单个媒体生成任务的通用执行：建任务 -> 注册队列 -> 轮询 -> 回填结果节点 -> 自动下载/通知/标错
 * - onProgress 阶段与 GenerationOptions.onProgress 对齐（creating/polling/generating/done/error）
 * - 失败时把错误写入节点 content.errorDetails
 * @returns true = 生成成功；false = 生成失败
 */
/**
 * 聚合多任务进度回调：N 张图各自 done/error，收敛为一次最终回调
 * - 全部结束后：有成功回一次 'done'（携带全部成功节点），否则回一次 'error'
 * - 其余阶段原样透传；total <= 1 时直接返回原回调
 */
function aggregateProgress(
  onProgress: GenerationOptions['onProgress'] | undefined,
  total: number,
): GenerationOptions['onProgress'] {
  if (!onProgress || total <= 1) return onProgress
  let settled = 0
  const successIds: string[] = []
  let lastError = ''
  return (phase, data) => {
    if (phase !== 'done' && phase !== 'error') {
      onProgress(phase, data)
      return
    }
    settled++
    if (phase === 'done') successIds.push(...(data?.resultNodeIds || []))
    else lastError = String(data?.error || '') || lastError
    if (settled >= total) {
      if (successIds.length > 0) onProgress('done', { resultNodeIds: successIds })
      else onProgress('error', { resultNodeIds: [], error: lastError })
    }
  }
}

async function runMediaTask(
  store: CanvasGenerationStore,
  panelId: string,
  isVideo: boolean,
  create: () => Promise<{ task_id: string }>,
  poll: (taskId: string, cb: (status: string, data: Record<string, any>) => void) => Promise<{ resultUrl?: string; videoUrl?: string }>,
  prompt: string,
  modelId: string | undefined,
  onProgress?: (phase: string, data: Record<string, any>) => void,
): Promise<boolean> {
  const queueStore = useTaskQueueStore()
  const prefsStore = usePreferencesStore()
  const kind = isVideo ? 'video' : 'image'
  try {
    if (onProgress) onProgress('creating', { index: 0, total: 1 })
    const taskResp = await create()
    const taskId = taskResp.task_id
    queueStore.registerCanvasTask({
      taskId,
      type: kind,
      prompt,
      backendTaskId: taskId,
      panelId,
    })
    if (onProgress) onProgress('polling', { index: 0, taskId })
    const result = await poll(taskId, (status, data) => {
      if (onProgress) onProgress('generating', { index: 0, status, progress: data.progress })
    })
    const resultUrl = (isVideo ? result.videoUrl : result.resultUrl) || ''
    store.updatePanel(panelId, { content: { content: resultUrl, status: 'success' } })
    store.pushSnapshot()
    if (onProgress) onProgress('done', { resultNodeIds: [panelId] })
    // 【用户偏好】自动下载 + 完成通知（不阻塞主流程）
    prefsStore.autoDownload(resultUrl, kind, { modelId })
    prefsStore.notifyComplete(kind, { prompt, modelId })
    return true
  } catch (err) {
    const errMsg = getErrorMessage(err) || (isVideo ? '视频生成失败' : '生成失败')
    store.updatePanel(panelId, { content: { status: 'error', errorDetails: errMsg } })
    if (onProgress) onProgress('error', { resultNodeIds: [panelId], error: errMsg })
    return false
  }
}

/**
 * 图片节点对话框生成（图生图）：以当前图片为参考图，在右侧创建新图片结果节点
 * @param params 节点上选择的模型与尺寸，不传时回落默认模型与默认尺寸
 * @returns 新结果节点 ID（调用方无需等待完成，任务后台轮询回填）
 */
export async function executeImageReferenceGeneration(
  sourcePanel: GenerationPanel,
  prompt: string,
  store: CanvasGenerationStore,
  params?: Partial<PanelGenParams>,
): Promise<string> {
  const modelsStore = useModelsStore()
  const ctx: GenerationContext = {
    prompt,
    referenceImages: [String(sourcePanel.content?.content || '')],
    referenceVideos: [],
    referenceTexts: [],
    inputSummary: { textCount: 0, imageCount: 1, videoCount: 0, total: 1 },
  }
  const newNodeId = createLoadingResultNode(store, sourcePanel, false)
  const modelId = params?.model || modelsStore.defaultImageModel
  const size = params?.size || modelsStore.defaultImageSize
  // 后台执行，不阻塞对话框
  void runMediaTask(
    store,
    newNodeId,
    false,
    () => createGenerationTask(ctx, { model: modelId, size }, buildCanvasContext(sourcePanel, store)),
    (taskId, cb) => pollImageTask(taskId, cb),
    prompt,
    modelId,
  )
  return newNodeId
}

/**
 * 视频节点对话框生成（首帧生视频）：抽取当前视频首帧作为参考图图生视频，右侧创建新视频节点
 * @param frameDataUrl 视频首帧 dataURI（调用方抽取）
 * @param params 节点上选择的模型与视频参数，不传时回落默认模型与默认参数
 * @returns 新结果节点 ID
 */
export async function executeVideoFromFrameGeneration(
  sourcePanel: GenerationPanel,
  frameDataUrl: string,
  prompt: string,
  store: CanvasGenerationStore,
  params?: Partial<PanelGenParams>,
): Promise<string> {
  const modelsStore = useModelsStore()
  const ctx: GenerationContext = {
    prompt,
    referenceImages: [frameDataUrl],
    referenceVideos: [],
    referenceTexts: [],
    inputSummary: { textCount: 0, imageCount: 1, videoCount: 0, total: 1 },
  }
  const newNodeId = createLoadingResultNode(store, sourcePanel, true)
  const modelId = params?.model || modelsStore.defaultVideoModel
  const config: GenerationConfig = {
    model: modelId,
    seconds: params?.seconds || modelsStore.defaultVideoDuration,
    aspect_ratio: params?.aspect_ratio || modelsStore.defaultVideoAspectRatio,
    resolution: params?.resolution || modelsStore.defaultVideoResolution,
    frame_rate: params?.frame_rate || modelsStore.defaultFrameRate,
  }
  // 后台执行，不阻塞对话框
  void runMediaTask(
    store,
    newNodeId,
    true,
    () => createVideoGenerationTask(ctx, config, buildCanvasContext(sourcePanel, store)),
    (taskId, cb) => pollVideoTask(taskId, cb),
    prompt,
    modelId,
  )
  return newNodeId
}

/**
 * 尺寸格式归一化
 * - "1:1" → "1024x1024"
 * - "16:9" → "1024x576"
 * - "1024x1024" → 原样返回
 */
function normalizeSize(size: string | undefined): string {
  if (!size) return '1024x1024'
  // 已经是 宽x高 格式
  if (/^\d+x\d+$/i.test(size)) return size
  // 比例格式转换
  const ratioMap: Record<string, string> = {
    '1:1': '1024x1024',
    '16:9': '1024x576',
    '9:16': '576x1024',
    '4:3': '1024x768',
    '3:4': '768x1024',
    '3:2': '1024x683',
    '2:3': '683x1024',
  }
  return ratioMap[size] || '1024x1024'
}

// ---------- 视频合并生成 ----------

/**
 * 创建视频生成任务（调用 /api/videos）
 * - text2video：纯文本生成视频
 * - image2video：自动识别：1 张参考图=单图，2+ 张参考图=多图参考
 * - keyframes：关键帧动画（需 config.use_keyframes=true，最多 2 张）
 * - video2video：上游视频作参考视频（需所选模型 capabilities 声明 video2video；
 *   未声明时降级抽上游视频首帧转参考图走 image2video）
 * - 模式根据参考图/参考视频数量和 use_keyframes 开关自动推断
 */
export async function createVideoGenerationTask(
  ctx: GenerationContext,
  config: GenerationConfig,
  context?: GenerationContextPayload,
): Promise<{ task_id: string }> {
  const { prompt, referenceImages } = ctx
  const { base64Images, imageUrls } = await classifyImages(referenceImages || [])

  // 合并所有参考图（URL 和 base64 统一排列）
  const allImages = [...imageUrls, ...base64Images]

  // 上游视频（连线收集）；首尾帧模式不混入上游视频
  const refVideos: ReferenceVideo[] = config.use_keyframes ? [] : (ctx.referenceVideos || []).filter((v) => v.url && v.url.trim())

  // 根据参考图/参考视频数量 + use_keyframes 开关推断最终模式
  let mode: string
  let referenceVideosParam: string[] | null = null
  if (refVideos.length > 0) {
    // 与后端 /api/videos 能力校验同口径（capabilities 声明 + 按名兜底）
    if (useModelsStore().supportsVideo2Video(config.model)) {
      // 原生视频参考：后端 video2video 模式，最多 5 个
      mode = 'video2video'
      referenceVideosParam = refVideos.slice(0, 5).map((v) => v.url)
    } else {
      // 模型不支持视频参考：降级抽当前播放帧转参考图，走图生视频
      allImages.push(...await videosToCurrentFrames(refVideos))
      mode = allImages.length > 0 ? 'image2video' : 'text2video'
    }
  } else if (allImages.length >= 1) {
    if (config.use_keyframes) {
      mode = 'keyframes'  // 开启关键帧：强制 keyframes 模式（最多2张）
    } else {
      mode = 'image2video'  // 图生视频：自动识别单张/多张
    }
  } else {
    mode = 'text2video'  // 无图 → 文生视频
  }

  const params: VideoGenerationRequest = {
    prompt,
    model: config.model || useModelsStore().defaultVideoModel,
    mode: mode as 'text2video' | 'image2video' | 'keyframes' | 'video2video',
  }

  // 视频帧率
  if (config.frame_rate) {
    params.frame_rate = config.frame_rate
  }

  // 视频时长（秒）
  if (config.seconds) {
    params.seconds = config.seconds
  }

  // 分辨率：根据高度（resolution）和宽高比计算 width/height
  if (config.resolution && config.aspect_ratio) {
    const arParts = config.aspect_ratio.split(':')
    if (arParts.length === 2) {
      const arW = parseInt(arParts[0], 10)
      const arH = parseInt(arParts[1], 10)
      if (arW > 0 && arH > 0) {
        const height = config.resolution
        const width = Math.round(height * arW / arH)
        // 确保宽高为 8 的倍数（视频编码硬性要求，向上取整）
        params.width = Math.floor((width + 7) / 8) * 8
        params.height = Math.floor((height + 7) / 8) * 8
      }
    }
  }

  // 画面比例（如 "16:9"，如果没传具体宽高则后端会用默认高度按比例计算）
  if (config.aspect_ratio && !params.width) {
    params.aspect_ratio = config.aspect_ratio
  }

  // 根据模式传参考图/参考视频
  if (mode === 'keyframes') {
    // 关键帧模式：传 images 数组（最多 2 张：起始帧 + 结束帧）
    const images = allImages.slice(0, 2)
    params.images = images
    params.image_mime_types = images.map(() => 'image/png')
  } else if (mode === 'image2video') {
    // 图生视频模式：支持单张或多张参考图，统一用 images 数组
    params.images = allImages
    params.image_mime_types = allImages.map(() => 'image/png')
  } else if (mode === 'video2video') {
    // 视频转视频模式：参考视频 URL 数组（最多 5 个，后端校验）
    params.reference_videos = referenceVideosParam
  }

  // 创作上下文：画布/项目生成时携带，用于历史瘦身 + 自动归档
  params.context = context ?? undefined

  const resp = await createVideoTask(params)
  if (!resp || !resp.task_id) {
    throw new Error('创建视频任务失败：未返回 task_id')
  }
  return { task_id: resp.task_id }
}

/**
 * 执行完整的视频合并生成流程（异步，不阻塞配置面板）
 * 1. 构建生成上下文（收集上游资源 + 解析 @[node:xxx]）
 * 2. 创建 loading 状态的结果节点（立刻显示在画布上）
 * 3. 创建视频任务 + 注册到任务队列
 * 4. 异步轮询任务状态
 * 5. 轮询完成后回填结果到结果节点（成功/失败都有反馈）
 *
 * @returns 新创建的结果节点 ID（loading 状态）
 */
export async function executeMergeVideoGeneration(configId: string, store: CanvasGenerationStore, options: GenerationOptions = {}): Promise<string> {
  const { onProgress } = options

  // 1. 查找 Config 节点
  const configNode = store.panels.find((p) => p.id === configId)
  if (!configNode || configNode.type !== 'config') {
    throw new Error('未找到 Config 节点')
  }

  // 2. 构建生成上下文（复用图片生成的上下文构建逻辑）
  const ctx = buildGenerationContext(configNode, store.panels, store.connections)
  if (!ctx) {
    throw new Error('构建生成上下文失败')
  }

  if (!ctx.prompt || !ctx.prompt.trim()) {
    throw new Error('提示词为空，请填写 composerContent 或 prompt')
  }

  // 关键帧模式校验：最多只能有2张参考图
  const useKeyframes = configNode.content?.use_keyframes || false
  if (useKeyframes && ctx.referenceImages && ctx.referenceImages.length > 2) {
    throw new Error('关键帧模式最多只能连接 2 张图片（起始帧 + 结束帧）')
  }

  if (onProgress) onProgress('building', { inputSummary: ctx.inputSummary })

  // 3. 立刻创建 loading 状态的结果节点
  const newNodeId = createLoadingResultNode(store, configNode, true)

  const config: GenerationConfig = {
    model: configNode.content?.model || useModelsStore().defaultVideoModel,
    seconds: configNode.content?.seconds || 5,
    aspect_ratio: configNode.content?.aspect_ratio || '16:9',
    resolution: configNode.content?.resolution || useModelsStore().defaultVideoResolution,
    frame_rate: configNode.content?.frame_rate || useModelsStore().defaultFrameRate,
    use_keyframes: useKeyframes,  // 是否使用关键帧模式
  }

  // 4. 异步执行生成 + 轮询 + 回填（默认不阻塞调用方；waitFor=true 时等待完成，供批量编排限流）
  const run = () => runMediaTask(
    store,
    newNodeId,
    true,
    () => createVideoGenerationTask(ctx, config, buildCanvasContext(configNode, store)),
    (taskId, cb) => pollVideoTask(taskId, cb),
    ctx.prompt,
    config.model,
    onProgress,
  )

  if (options.waitFor) {
    await run()
  } else {
    void run()
  }

  // 返回新节点 ID（loading 状态）
  return newNodeId
}

// ---------- 中断任务恢复 ----------

/** 正在恢复轮询的节点 id（防止同一节点重复拉起轮询） */
const resumingPanelIds = new Set<string>()

/**
 * 恢复中断的画布生成任务（画布加载完成 / 切换工作区时调用）
 * - 页面刷新会杀掉内存中的轮询循环，节点 content.status 停留在 'loading'、队列任务停留在 processing
 * - 按队列任务的 panelId 匹配 loading 节点：已完成的直接回填，进行中的用 backendTaskId 重新拉起轮询
 * - 队列中找不到对应任务（记录过期/流式中断）时标记失败，避免节点永久显示"生成中"
 */
export function resumeLoadingCanvasNodes(store: CanvasGenerationStore): void {
  const queueStore = useTaskQueueStore()
  const prefsStore = usePreferencesStore()

  const loadingPanels = store.panels.filter((p) => p.content?.status === 'loading')
  for (const panel of loadingPanels) {
    if (resumingPanelIds.has(panel.id)) continue
    const task = queueStore.taskList
      .filter((t) => t.source === 'canvas' && t.panelId === panel.id)
      .sort((a, b) => b.createdAt - a.createdAt)[0]

    // 队列任务已完成：直接回填，不再查询后端
    if (task?.status === 'success' && task.resultUrl) {
      store.updatePanel(panel.id, { content: { content: task.resultUrl, status: 'success' } })
      store.pushSnapshot()
      continue
    }
    // 队列任务已失败：保留原始错误信息直接标错
    if (task?.status === 'failed') {
      store.updatePanel(panel.id, { content: { status: 'error', errorDetails: task.errorMessage || '生成失败' } })
      continue
    }
    // 队列中找不到进行中的任务：无法查询后端状态，标记失败
    if (!task?.backendTaskId) {
      store.updatePanel(panel.id, { content: { status: 'error', errorDetails: '生成任务已中断，请重新生成' } })
      continue
    }

    // 任务进行中：用 backendTaskId 重新轮询，完成后回填节点（队列状态由 poll 函数同步更新）
    resumingPanelIds.add(panel.id)
    const isVideo = task.type === 'video'
    const pollResult = isVideo
      ? pollVideoTask(task.backendTaskId).then((r) => r.videoUrl)
      : pollImageTask(task.backendTaskId).then((r) => r.resultUrl)
    pollResult
      .then((url) => {
        // 恢复期间用户若重新生成了该节点（出现更新的任务），放弃回填旧结果
        const hasNewerTask = queueStore.taskList.some(
          (t) => t.source === 'canvas' && t.panelId === panel.id && t.createdAt > task.createdAt,
        )
        if (hasNewerTask) return
        store.updatePanel(panel.id, { content: { content: url, status: 'success' } })
        store.pushSnapshot()
        prefsStore.autoDownload(url, isVideo ? 'video' : 'image')
        prefsStore.notifyComplete(isVideo ? 'video' : 'image', { prompt: task.prompt })
      })
      .catch((err) => {
        const hasNewerTask = queueStore.taskList.some(
          (t) => t.source === 'canvas' && t.panelId === panel.id && t.createdAt > task.createdAt,
        )
        if (hasNewerTask) return
        store.updatePanel(panel.id, { content: { status: 'error', errorDetails: getErrorMessage(err) || '生成失败' } })
      })
      .finally(() => {
        resumingPanelIds.delete(panel.id)
      })
  }
}
