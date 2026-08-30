/* =====================================================
 * 画布多元素合并生成核心逻辑
 * - 参考 infinite-canvas 项目的 Config 节点 + @[node:xxx] 引用模式
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
import { parseSize } from '@/config/model-params'
import type { CanvasPanel, CanvasConnection } from '@/stores/canvas'
import type { ImageGenerationRequest, VideoGenerationRequest, GenerationContextPayload, ImageTaskStatusResponse, VideoStatusResponse } from '@/types'
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

/** Composer 编辑器需要的 inputs 格式 */
interface ResourceContentForComposer {
  nodeId: string
  type: 'image' | 'text' | 'video'
  title: string
  imageUrl?: string
  text?: string
  videoUrl?: string
}

/** 输入摘要（供 UI 显示） */
interface InputSummary {
  textCount: number
  imageCount: number
  videoCount: number
  total: number
}

/** 生成上下文 */
interface GenerationContext {
  prompt: string
  referenceImages: string[]
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

/**
 * 从资源节点提取 Composer 编辑器需要的 inputs 格式
 * - 供 CanvasConfigComposer 组件使用
 * - 返回 { nodeId, type, title, text, imageUrl }
 */
export function extractResourceContentForComposer(panel: GenerationPanel): ResourceContentForComposer | null {
  if (!panel) return null
  const c = panel.content || {}
  const title = (panel.name || panel.type || 'Untitled') as string
  switch (panel.type) {
    case 'image':
      return {
        nodeId: panel.id,
        type: 'image',
        title,
        imageUrl: c.content || c.imageUrl || c.image || c.url || '',
      }
    case 'text':
      return {
        nodeId: panel.id,
        type: 'text',
        title,
        text: c.content || c.text || '',
      }
    case 'video':
      return {
        nodeId: panel.id,
        type: 'video',
        title,
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

/**
 * 构建生成上下文：解析 @[node:xxx] 引用，合并多资源
 *
 * 合并策略（参考 infinite-canvas 的 buildComposerGenerationContext）：
 * - 如果 configNode 有 composerContent（组装提示词），走引用解析路径：
 *   · 解析 @[node:xxx] token，把引用替换为标签（图片1、文本2...，序号与节点显示一致）
 *   · 文本资源：在 prompt 末尾追加 【文本1】\n内容 块
 *   · 图片资源：作为 referenceImages 数组传给 AI
 * - 如果没有 composerContent，走简单合并路径：
 *   · 所有上游文本拼到 prompt 末尾
 *   · 所有上游图片作为 referenceImages
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

  // 如果没有任何需要解析的内容，走简单合并路径
  if (!contentToParse) {
    return withSnapshotImages(buildSimpleContext(plainInputs, '', inputSummary), snapshotImages)
  }

  // 如果有 @图片1/@文本2 等可读标签引用，或使用了composerContent，走引用解析路径
  const hasMention = MENTION_PATTERN.test(contentToParse)
  MENTION_PATTERN.lastIndex = 0 // 重置正则lastIndex
  if (!hasMention && !hasComposer) {
    return withSnapshotImages(buildSimpleContext(plainInputs, contentToParse, inputSummary), snapshotImages)
  }

  // 走引用解析路径
  return withSnapshotImages(buildComposerContext(inputs, contentToParse, inputSummary), snapshotImages)
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

  return { prompt, referenceImages, referenceTexts, inputSummary }
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
    referenceTexts: textBlocks,
    inputSummary,
  }
}

// ---------- API 调用与轮询 ----------

/** 轮询连续失败容忍次数（网络抖动/后端重启时不因单次查询失败就判死任务） */
const MAX_POLL_ERRORS = 6

/** 参考图张数上限：仅 agnes-video-2.5-flash 的独立契约限制（2.5 非 Flash 与 2.0 无此硬限制） */
const VIDEO_FLASH_REF_MAX = 5

/** 图片模型参考图张数上限：仅上游契约明确限制的模型，其余模型不截断（超出上限上游会 400 拒绝） */
const IMAGE_MODEL_REF_LIMITS: Record<string, number> = {
  'agnes-image-2.1-flash': 6,
}

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
async function classifyImages(images: string[]): Promise<{ base64Images: string[]; imageUrls: string[] }> {
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
  const model = config.model || useModelsStore().defaultImageModel
  // 参考图按所选模型的契约上限截断：仅命中已知限制的模型（如 2.1 Flash 上游最多 6 张），其余模型原样透传；
  // 参考图数组已按「锚点/底图 > 角色 > 场景」优先级排序，截断保留前 N 张
  const imageRefLimit = IMAGE_MODEL_REF_LIMITS[model]
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
 * 轮询图片任务状态直到完成
 * - 间隔 2 秒，超时 5 分钟
 * - onProgress 回调用于更新 UI 进度
 * - 同步更新 TaskQueue Store，让画布任务在队列面板中可见
 */
export async function pollImageTask(
  taskId: string,
  onProgress?: (status: string, data: Record<string, any>) => void,
  timeout: number = 300000,
): Promise<{ status: string; resultUrl: string }> {
  const startTime = Date.now()
  const interval = 2000
  const queueStore = useTaskQueueStore()
  let consecutiveErrors = 0

  while (true) {
    if (Date.now() - startTime > timeout) {
      // 超时，更新队列状态
      queueStore.updateCanvasTask(taskId, { status: 'failed' })
      throw new Error('生成任务超时（超过 5 分钟未完成）')
    }

    // 单次查询失败静默重试（网络抖动/后端重启），连续多次才判失败
    let data: ImageTaskStatusResponse | null = null
    try {
      data = await getImageTaskStatus(taskId)
    } catch (_) { /* 按连续错误计数处理 */ }
    if (!data) {
      consecutiveErrors += 1
      if (consecutiveErrors >= MAX_POLL_ERRORS) {
        queueStore.updateCanvasTask(taskId, { status: 'failed' })
        throw new Error('查询任务状态失败')
      }
      await new Promise((resolve) => setTimeout(resolve, interval))
      continue
    }
    consecutiveErrors = 0

    const status = data.status || 'pending'
    if (onProgress) onProgress(status, data)

    // 同步更新任务队列
    const isSuccess = ['success', 'completed', 'done', 'succeeded', 'finished'].includes(status)
    const isFailed = ['failed', 'error', 'timeout'].includes(status)

    if (isSuccess) {
      const resultUrl = data.result_url || data.url || ''
      if (!resultUrl) {
        queueStore.updateCanvasTask(taskId, { status: 'failed' })
        throw new Error('生成完成但未返回图片 URL')
      }
      queueStore.updateCanvasTask(taskId, { status: 'success', resultUrl, progress: 100 })
      return { status: 'success', resultUrl }
    }

    if (isFailed) {
      queueStore.updateCanvasTask(taskId, { status: 'failed' })
      throw new Error(data.message || '生成失败')
    }

    if (status === 'cancelled') {
      queueStore.updateCanvasTask(taskId, { status: 'cancelled' })
      throw new Error('任务已取消')
    }

    // 更新进度
    const progress = typeof data.progress === 'number' ? data.progress : undefined
    queueStore.updateCanvasTask(taskId, { status: 'processing', progress })

    // 继续等待
    await new Promise((resolve) => setTimeout(resolve, interval))
  }
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
  const queueStore = useTaskQueueStore()

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

  // 3. 立刻创建 loading 状态的结果节点
  const newNodeId = createLoadingResultNode(store, configNode, false)

  const config: GenerationConfig = {
    model: configNode.content?.model || useModelsStore().defaultImageModel,
    size: normalizeSize(configNode.content?.size),
    response_format: 'url',
  }

  // 4. 异步执行生成 + 轮询 + 回填（默认不阻塞调用方；waitFor=true 时等待完成，供批量编排限流）
  const run = async (): Promise<void> => {
    try {
      if (onProgress) onProgress('creating', { index: 0, total: 1 })

      // 创建任务
      const taskResp = await createGenerationTask(ctx, config, buildCanvasContext(configNode, store))
      const taskId = taskResp.task_id

      // 注册到任务队列
      queueStore.registerCanvasTask({
        taskId,
        type: 'image',
        prompt: ctx.prompt,
        backendTaskId: taskId,
        panelId: newNodeId,
      })

      if (onProgress) onProgress('polling', { index: 0, taskId })

      // 轮询任务状态
      const result = await pollImageTask(taskId, (status, data) => {
        if (onProgress) onProgress('generating', { index: 0, status, progress: data.progress })
      })

      // 5. 回填结果到结果节点
      store.updatePanel(newNodeId, {
        content: { content: result.resultUrl, status: 'success' },
      })
      store.pushSnapshot()
      if (onProgress) onProgress('done', { resultNodeIds: [newNodeId] })
      // 【用户偏好】自动下载 + 完成通知（不阻塞主流程）
      const prefsStore = usePreferencesStore()
      prefsStore.autoDownload(result.resultUrl, 'image', { modelId: config.model })
      prefsStore.notifyComplete('image', { prompt: ctx.prompt, modelId: config.model })
    } catch (err) {
      // 失败：更新节点为 error 状态
      const errMsg = getErrorMessage(err) || '生成失败'
      store.updatePanel(newNodeId, {
        content: { status: 'error', errorDetails: errMsg },
      })
      if (onProgress) onProgress('error', { resultNodeIds: [newNodeId], error: errMsg })
    }
  }

  if (options.waitFor) {
    await run()
  } else {
    void run()
  }

  // 返回新节点 ID（loading 状态）
  return newNodeId
}

/**
 * 执行就地生成（分镜直出节点：结果回填节点自身，不新建结果节点、不加 config 连线）
 * 1. 读取节点上的模型/尺寸参数，取 content.prompt 与 content.referenceImages 作为生成上下文
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
  const queueStore = useTaskQueueStore()
  const prefsStore = usePreferencesStore()

  const prompt = typeof panel.content?.prompt === 'string' ? panel.content.prompt.trim() : ''
  if (!prompt) {
    throw new Error('提示词为空，请在节点上填写 prompt')
  }
  const referenceImages = Array.isArray(panel.content?.referenceImages)
    ? panel.content.referenceImages.filter((u): u is string => typeof u === 'string')
    : []
  const ctx: GenerationContext = {
    prompt,
    referenceImages,
    referenceTexts: [],
    inputSummary: { textCount: 0, imageCount: referenceImages.length, videoCount: 0, total: referenceImages.length },
  }
  const params = readPanelGenParams(panel, 'image')
  const config: GenerationConfig = { model: params.model, size: normalizeSize(params.size), response_format: 'url' }

  // 置 loading：此处只写状态字段，不传 referenceImages 数组（deepMerge 会把数组转成索引对象）
  store.updatePanel(panel.id, { content: { status: 'loading', errorDetails: null } })

  let failed = false
  const run = async (): Promise<void> => {
    try {
      if (onProgress) onProgress('creating', { index: 0, total: 1 })

      const taskResp = await createGenerationTask(ctx, config, buildCanvasContext(panel, store))
      const taskId = taskResp.task_id

      queueStore.registerCanvasTask({
        taskId,
        type: 'image',
        prompt,
        backendTaskId: taskId,
        panelId: panel.id,
      })

      if (onProgress) onProgress('polling', { index: 0, taskId })

      const result = await pollImageTask(taskId, (status, data) => {
        if (onProgress) onProgress('generating', { index: 0, status, progress: data.progress })
      })

      store.updatePanel(panel.id, { content: { content: result.resultUrl, status: 'success' } })
      store.pushSnapshot()
      if (onProgress) onProgress('done', { resultNodeIds: [panel.id] })
      prefsStore.autoDownload(result.resultUrl, 'image', { modelId: config.model })
      prefsStore.notifyComplete('image', { prompt, modelId: config.model })
    } catch (err) {
      failed = true
      const errMsg = getErrorMessage(err) || '生成失败'
      store.updatePanel(panel.id, { content: { status: 'error', errorDetails: errMsg } })
      if (onProgress) onProgress('error', { resultNodeIds: [panel.id], error: errMsg })
    }
  }

  if (options.waitFor) {
    await run()
  } else {
    void run()
  }

  return failed ? null : panel.id
}

/**
 * 视频节点就地生成（分镜直出）：节点自身承载参数与结果
 * 1. 读取节点上的模型/比例/分辨率/帧率/时长，content.referenceImages[0] 为源分镜图
 * 2. 节点置 loading -> 建任务 + 注册队列 -> 轮询 -> 视频地址回填 content.content
 * 失败语义与 executeInNodeGeneration 一致：waitFor 模式返回 null，不打断批量并发池
 */
export async function executeInNodeVideoGeneration(
  panel: CanvasPanel,
  store: CanvasGenerationStore,
  options: GenerationOptions = {},
): Promise<string | null> {
  const { onProgress } = options
  const queueStore = useTaskQueueStore()
  const prefsStore = usePreferencesStore()

  const prompt = typeof panel.content?.prompt === 'string' ? panel.content.prompt.trim() : ''
  const referenceImages = Array.isArray(panel.content?.referenceImages)
    ? panel.content.referenceImages.filter((u): u is string => typeof u === 'string')
    : []
  if (!prompt && referenceImages.length === 0) {
    throw new Error('提示词为空且无参考图，无法生成视频')
  }
  const params = readPanelGenParams(panel, 'video')
  // 首尾帧模式（分镜直出写入 use_keyframes）：参考图限首尾 2 张，路由到 keyframes
  const useKeyframes = panel.content?.use_keyframes === true
  if (useKeyframes && referenceImages.length > 2) {
    throw new Error('关键帧模式最多只能使用 2 张参考图（首帧 + 尾帧）')
  }
  // 参考图按所选视频模型截断：仅 2.5 Flash 限 5 张（多图参考场景前端拦截，避免发超限请求），其余模型不截断
  const effectiveRefImages = params.model === 'agnes-video-2.5-flash' && referenceImages.length > VIDEO_FLASH_REF_MAX
    ? referenceImages.slice(0, VIDEO_FLASH_REF_MAX)
    : referenceImages
  const ctx: GenerationContext = {
    prompt,
    referenceImages: effectiveRefImages,
    referenceTexts: [],
    inputSummary: { textCount: 0, imageCount: effectiveRefImages.length, videoCount: 0, total: effectiveRefImages.length },
  }
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

  let failed = false
  const run = async (): Promise<void> => {
    try {
      if (onProgress) onProgress('creating', { index: 0, total: 1 })

      const taskResp = await createVideoGenerationTask(ctx, config, buildCanvasContext(panel, store))
      const taskId = taskResp.task_id

      queueStore.registerCanvasTask({
        taskId,
        type: 'video',
        prompt,
        backendTaskId: taskId,
        panelId: panel.id,
      })

      if (onProgress) onProgress('polling', { index: 0, taskId })

      const result = await pollVideoTask(taskId, (status, data) => {
        if (onProgress) onProgress('generating', { index: 0, status, progress: data.progress })
      })

      const videoUrl = result.videoUrl || ''
      store.updatePanel(panel.id, { content: { content: videoUrl, status: 'success' } })
      store.pushSnapshot()
      if (onProgress) onProgress('done', { resultNodeIds: [panel.id] })
      prefsStore.autoDownload(videoUrl, 'video', { modelId: config.model })
      prefsStore.notifyComplete('video', { prompt, modelId: config.model })
    } catch (err) {
      failed = true
      const errMsg = getErrorMessage(err) || '视频生成失败'
      store.updatePanel(panel.id, { content: { status: 'error', errorDetails: errMsg } })
      if (onProgress) onProgress('error', { resultNodeIds: [panel.id], error: errMsg })
    }
  }

  if (options.waitFor) {
    await run()
  } else {
    void run()
  }

  return failed ? null : panel.id
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

// ---------- 媒体节点对话框生成（LibTV 复刻：图生图 / 首帧生视频） ----------

/** 单个媒体生成任务的通用执行：建任务 -> 注册队列 -> 轮询 -> 回填结果节点 -> 自动下载/通知 */
async function runMediaTask(
  store: CanvasGenerationStore,
  newNodeId: string,
  isVideo: boolean,
  create: () => Promise<{ task_id: string }>,
  poll: (taskId: string, cb: (status: string, data: Record<string, any>) => void) => Promise<{ resultUrl?: string; videoUrl?: string }>,
  prompt: string,
  modelId: string,
): Promise<void> {
  const queueStore = useTaskQueueStore()
  const prefsStore = usePreferencesStore()
  try {
    const taskResp = await create()
    queueStore.registerCanvasTask({
      taskId: taskResp.task_id,
      type: isVideo ? 'video' : 'image',
      prompt,
      backendTaskId: taskResp.task_id,
      panelId: newNodeId,
    })
    const result = await poll(taskResp.task_id, () => {})
    const resultUrl = (isVideo ? result.videoUrl : result.resultUrl) || ''
    store.updatePanel(newNodeId, { content: { content: resultUrl, status: 'success' } })
    store.pushSnapshot()
    prefsStore.autoDownload(resultUrl, isVideo ? 'video' : 'image', { modelId })
    prefsStore.notifyComplete(isVideo ? 'video' : 'image', { prompt, modelId })
  } catch (err) {
    store.updatePanel(newNodeId, {
      content: { status: 'error', errorDetails: getErrorMessage(err) || (isVideo ? '视频生成失败' : '生成失败') },
    })
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
 * - 模式根据参考图数量和 use_keyframes 开关自动推断
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

  // 根据参考图数量 + use_keyframes 开关推断最终模式
  let mode: string
  if (allImages.length >= 1) {
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
    mode: mode as 'text2video' | 'image2video' | 'keyframes',
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

  // 根据模式传参考图
  if (mode === 'keyframes') {
    // 关键帧模式：传 images 数组（最多 2 张：起始帧 + 结束帧）
    const images = allImages.slice(0, 2)
    params.images = images
    params.image_mime_types = images.map(() => 'image/png')
  } else if (mode === 'image2video') {
    // 图生视频模式：支持单张或多张参考图，统一用 images 数组
    params.images = allImages
    params.image_mime_types = allImages.map(() => 'image/png')
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
 * 轮询视频任务状态直到完成
 * - 间隔 5 秒，超时 10 分钟
 * - onProgress 回调用于更新 UI 进度
 * - 同步更新 TaskQueue Store，让画布任务在队列面板中可见
 */
export async function pollVideoTask(
  taskId: string,
  onProgress?: (status: string, data: Record<string, any>) => void,
  timeout: number = 600000,
): Promise<{ status: string; videoUrl: string }> {
  const startTime = Date.now()
  const interval = 5000
  const queueStore = useTaskQueueStore()
  let consecutiveErrors = 0

  while (true) {
    if (Date.now() - startTime > timeout) {
      queueStore.updateCanvasTask(taskId, { status: 'failed' })
      throw new Error('视频生成任务超时（超过 10 分钟未完成）')
    }

    // 单次查询失败静默重试（网络抖动/后端重启），连续多次才判失败
    let data: VideoStatusResponse | null = null
    try {
      data = await getVideoStatus(taskId)
    } catch (_) { /* 按连续错误计数处理 */ }
    if (!data) {
      consecutiveErrors += 1
      if (consecutiveErrors >= MAX_POLL_ERRORS) {
        queueStore.updateCanvasTask(taskId, { status: 'failed' })
        throw new Error('查询视频任务状态失败')
      }
      await new Promise((resolve) => setTimeout(resolve, interval))
      continue
    }
    consecutiveErrors = 0

    const status = data.status || 'pending'
    if (onProgress) onProgress(status, data)

    // 同步更新任务队列
    const isSuccess = ['success', 'completed', 'done', 'succeeded', 'finished'].includes(status)
    const isFailed = ['failed', 'error', 'timeout'].includes(status)

    if (isSuccess) {
      const videoUrl = data.video_url || ''
      if (!videoUrl) {
        queueStore.updateCanvasTask(taskId, { status: 'failed' })
        throw new Error('视频生成完成但未返回视频 URL')
      }
      queueStore.updateCanvasTask(taskId, { status: 'success', resultUrl: videoUrl, progress: 100 })
      return { status: 'success', videoUrl }
    }

    if (isFailed) {
      queueStore.updateCanvasTask(taskId, { status: 'failed' })
      throw new Error(data.message || '视频生成失败')
    }

    if (status === 'cancelled') {
      queueStore.updateCanvasTask(taskId, { status: 'cancelled' })
      throw new Error('视频任务已取消')
    }

    // 更新进度
    const progress = typeof data.progress === 'number' ? data.progress : undefined
    queueStore.updateCanvasTask(taskId, { status: 'processing', progress })

    // 继续等待
    await new Promise((resolve) => setTimeout(resolve, interval))
  }
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
  const queueStore = useTaskQueueStore()

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
  const run = async (): Promise<void> => {
    try {
      if (onProgress) onProgress('creating', { index: 0, total: 1 })

      // 创建视频任务
      const taskResp = await createVideoGenerationTask(ctx, config, buildCanvasContext(configNode, store))
      const taskId = taskResp.task_id

      // 注册到任务队列
      queueStore.registerCanvasTask({
        taskId,
        type: 'video',
        prompt: ctx.prompt,
        backendTaskId: taskId,
        panelId: newNodeId,
      })

      if (onProgress) onProgress('polling', { index: 0, taskId })

      // 轮询任务状态
      const result = await pollVideoTask(taskId, (status, data) => {
        if (onProgress) onProgress('generating', { index: 0, status, progress: data.progress })
      })

      // 5. 回填结果到结果节点
      store.updatePanel(newNodeId, {
        content: { content: result.videoUrl, status: 'success' },
      })
      store.pushSnapshot()
      if (onProgress) onProgress('done', { resultNodeIds: [newNodeId] })
      // 【用户偏好】自动下载 + 完成通知（不阻塞主流程）
      const prefsStore = usePreferencesStore()
      prefsStore.autoDownload(result.videoUrl, 'video', { modelId: config.model })
      prefsStore.notifyComplete('video', { prompt: ctx.prompt, modelId: config.model })
    } catch (err) {
      // 失败：更新节点为 error 状态
      const errMsg = getErrorMessage(err) || '视频生成失败'
      store.updatePanel(newNodeId, {
        content: { status: 'error', errorDetails: errMsg },
      })
      if (onProgress) onProgress('error', { resultNodeIds: [newNodeId], error: errMsg })
    }
  }

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
