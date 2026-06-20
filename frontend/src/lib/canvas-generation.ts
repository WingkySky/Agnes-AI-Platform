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
import { parseSize } from '@/config/model-params'
import type { ImageGenerationRequest, VideoGenerationRequest } from '@/types'

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

/** 面板类型（简化） */
interface Panel {
  id: string
  type: string
  name?: string
  x?: number
  y?: number
  width?: number
  height?: number
  content?: Record<string, any>
}

/** 连线类型 */
interface Connection {
  source_panel_id: string
  target_panel_id: string
  [key: string]: any
}

/** Canvas Store 接口（简化） */
interface CanvasStore {
  panels: Panel[]
  connections: Connection[]
  addPanel: (panel: Record<string, any>) => string | undefined
  addConnection: (conn: Record<string, any>) => void
  updatePanel: (id: string, updates: Record<string, any>) => void
  pushSnapshot: () => void
}

/** 生成任务配置 */
interface GenerationConfig {
  model?: string
  size?: string
  response_format?: string
  seconds?: number
  aspect_ratio?: string
}

/** 生成任务选项 */
interface GenerationOptions {
  onProgress?: (phase: string, data: Record<string, any>) => void
}

// ---------- 常量 ----------

/** @[node:xxx] 引用 token 的正则匹配模式 */
const NODE_REFERENCE_PATTERN = /@\[node:([^\]]+)\]/g

/** 资源类型标签生成器：图片1、图片2、文本1、视频1... */
function resourceLabel(type: string, index: number): string {
  const labels: Record<string, string> = { image: '图片', text: '文本', video: '视频', audio: '音频' }
  return `${labels[type] || '资源'}${index + 1}`
}

// ---------- 资源收集 ----------

/**
 * 判断面板是否为资源节点（可作为生成输入）
 * - image / text / video / audio 类型都是资源节点
 * - config / frame / quick-generate 不是资源节点
 */
export function isResourceNode(panel: Panel | null | undefined): boolean {
  if (!panel) return false
  return ['image', 'text', 'video', 'audio'].includes(panel.type)
}

/**
 * 获取指定节点的所有上游资源节点（根据连线查找）
 * - 查找 connections 中 target_panel_id === nodeId 的所有 source_panel_id
 * - 过滤掉非资源节点
 */
export function getUpstreamNodes(nodeId: string, panels: Panel[], connections: Connection[]): Panel[] {
  const upstreamIds = connections
    .filter((c) => c.target_panel_id === nodeId)
    .map((c) => c.source_panel_id)
    .filter(Boolean)

  const panelMap = new Map(panels.map((p) => [p.id, p]))
  return upstreamIds
    .map((id) => panelMap.get(id))
    .filter((p): p is Panel => !!p && isResourceNode(p))
}

/**
 * 从资源节点提取内容
 * - image: 返回 { type: 'image', nodeId, imageUrl, title }
 * - text: 返回 { type: 'text', nodeId, text, title }
 * - video: 返回 { type: 'video', nodeId, videoUrl, title }
 */
function extractResourceContent(panel: Panel): ResourceContent | null {
  if (!panel) return null
  const c = panel.content || {}
  const title = panel.name || panel.type

  switch (panel.type) {
    case 'image':
      return {
        type: 'image',
        nodeId: panel.id,
        imageUrl: c.content || c.imageUrl || c.image || c.url || '',
        title,
      }
    case 'text':
      return {
        type: 'text',
        nodeId: panel.id,
        text: c.content || c.text || '',
        title,
      }
    case 'video':
      return {
        type: 'video',
        nodeId: panel.id,
        videoUrl: c.content || c.videoUrl || c.url || '',
        title,
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
export function extractResourceContentForComposer(panel: Panel): ResourceContentForComposer | null {
  if (!panel) return null
  const c = panel.content || {}
  const title = panel.name || panel.type
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
 * 构建生成上下文：解析 @[node:xxx] 引用，合并多资源
 *
 * 合并策略（参考 infinite-canvas 的 buildComposerGenerationContext）：
 * - 如果 configNode 有 composerContent（组装提示词），走引用解析路径：
 *   · 解析 @[node:xxx] token，把引用替换为标签（图片1、文本1...）
 *   · 文本资源：在 prompt 末尾追加 【文本1】\n内容 块
 *   · 图片资源：作为 referenceImages 数组传给 AI
 * - 如果没有 composerContent，走简单合并路径：
 *   · 所有上游文本拼到 prompt 末尾
 *   · 所有上游图片作为 referenceImages
 */
export function buildGenerationContext(configNode: Panel, panels: Panel[], connections: Connection[]): GenerationContext | null {
  if (!configNode) return null

  // 收集上游资源
  const upstreamPanels = getUpstreamNodes(configNode.id, panels, connections)
  const inputs = upstreamPanels.map(extractResourceContent).filter((r): r is ResourceContent => r !== null)

  // 获取组装提示词（composerContent）或普通 prompt
  const composerContent = configNode.content?.composerContent?.trim()
  const basePrompt = composerContent || configNode.content?.prompt || ''

  // 输入摘要（供 UI 显示）
  const inputSummary: InputSummary = {
    textCount: inputs.filter((i) => i.type === 'text').length,
    imageCount: inputs.filter((i) => i.type === 'image').length,
    videoCount: inputs.filter((i) => i.type === 'video').length,
    total: inputs.length,
  }

  // 如果没有 composerContent，走简单合并路径
  if (!composerContent) {
    return buildSimpleContext(inputs, basePrompt, inputSummary)
  }

  // 有 composerContent，走引用解析路径
  return buildComposerContext(inputs, composerContent, inputSummary)
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
 * 引用解析路径：解析 @[node:xxx] token，按引用合并资源
 *
 * 解析规则：
 * - @[node:xxx] 中的 xxx 是节点 ID
 * - 文本资源：在 prompt 末尾追加 【文本1】\n内容 块，prompt 中替换为 【文本1】
 * - 图片资源：作为 referenceImages 数组，prompt 中替换为 图片1
 * - 视频/音频资源：暂不支持，跳过
 * - 未匹配到的 token 保留原样
 */
function buildComposerContext(inputs: ResourceContent[], composerContent: string, inputSummary: InputSummary): GenerationContext {
  const inputByNodeId = new Map(inputs.map((i) => [i.nodeId, i]))
  const labelByNodeId = new Map<string, string>()
  const selectedImages: string[] = []
  const textBlocks: string[] = []
  const counts: Record<string, number> = { image: 0, text: 0, video: 0, audio: 0 }
  let nextPrompt = ''
  let lastIndex = 0

  // 遍历所有 @[node:xxx] 匹配，替换为标签
  for (const match of composerContent.matchAll(NODE_REFERENCE_PATTERN)) {
    if (match.index === undefined) continue
    const nodeId = match[1]
    const input = inputByNodeId.get(nodeId)

    // 保留 token 之前的原文
    nextPrompt += composerContent.slice(lastIndex, match.index)

    if (input) {
      // 为该资源分配标签（图片1、文本1...）
      let label = labelByNodeId.get(input.nodeId)
      if (!label) {
        label = resourceLabel(input.type, counts[input.type]++)
        labelByNodeId.set(input.nodeId, label)

        // 文本资源：拼到 prompt 末尾的 textBlocks
        if (input.type === 'text' && input.text) {
          textBlocks.push(`【${label}】\n${input.text}`)
        }
        // 图片资源：加入 referenceImages
        else if (input.type === 'image' && input.imageUrl) {
          selectedImages.push(input.imageUrl)
        }
      }

      // prompt 中替换为标签
      nextPrompt += input.type === 'text' ? `【${label}】` : label
    } else {
      // 未匹配到的 token 保留原样
      nextPrompt += match[0]
    }

    lastIndex = match.index + match[0].length
  }

  // 追加最后一段原文
  nextPrompt += composerContent.slice(lastIndex)

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
export async function createGenerationTask(ctx: GenerationContext, config: GenerationConfig): Promise<{ task_id: string }> {
  const { prompt, referenceImages } = ctx
  const { base64Images, imageUrls } = await classifyImages(referenceImages || [])

  const params: Record<string, any> = {
    prompt,
    model: config.model || useModelsStore().defaultImageModel,
    size: config.size || '1024x1024',
    response_format: config.response_format || 'url',
    mode: referenceImages && referenceImages.length > 0 ? 'image2image' : 'text2image',
  }

  if (base64Images.length > 0) {
    params.base64_images = base64Images
  }
  if (imageUrls.length > 0) {
    params.image_urls = imageUrls
  }

  const resp = await createImageTask(params as ImageGenerationRequest)
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

  while (true) {
    if (Date.now() - startTime > timeout) {
      // 超时，更新队列状态
      queueStore.updateCanvasTask(taskId, { status: 'failed' })
      throw new Error('生成任务超时（超过 5 分钟未完成）')
    }

    const data = await getImageTaskStatus(taskId)
    if (!data) {
      queueStore.updateCanvasTask(taskId, { status: 'failed' })
      throw new Error('查询任务状态失败')
    }

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
function calcResultNodePosition(configNode: Panel, isVideo: boolean, index: number) {
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
export function createLoadingResultNode(store: CanvasStore, configNode: Panel, isVideo: boolean, index: number = 0): string {
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
export async function executeMergeGeneration(configId: string, store: CanvasStore, options: GenerationOptions = {}): Promise<string> {
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

  // 4. 异步执行生成 + 轮询 + 回填（不阻塞调用方）
  ;(async () => {
    try {
      if (onProgress) onProgress('creating', { index: 0, total: 1 })

      // 创建任务
      const taskResp = await createGenerationTask(ctx, config)
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
    } catch (err) {
      // 失败：更新节点为 error 状态
      const errMsg = (err as Error).message || '生成失败'
      store.updatePanel(newNodeId, {
        content: { status: 'error', errorDetails: errMsg },
      })
      if (onProgress) onProgress('error', { resultNodeIds: [newNodeId], error: errMsg })
    }
  })()

  // 立刻返回新节点 ID（loading 状态）
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
 * - image2video：1 张参考图生成视频
 * - keyframes：2+ 张参考图自动触发关键帧动画（起始帧+结束帧）
 * - 模式根据参考图数量自动推断，无需手动指定
 */
export async function createVideoGenerationTask(ctx: GenerationContext, config: GenerationConfig): Promise<{ task_id: string }> {
  const { prompt, referenceImages } = ctx
  const { base64Images, imageUrls } = await classifyImages(referenceImages || [])

  // 合并所有参考图（URL 和 base64 统一排列）
  const allImages = [...imageUrls, ...base64Images]

  // 根据参考图数量自动推断模式
  let mode: string
  if (allImages.length >= 2) {
    mode = 'keyframes'  // 2+ 张图 → 关键帧（起始帧+结束帧）
  } else if (allImages.length === 1) {
    mode = 'image2video'  // 1 张图 → 图生视频
  } else {
    mode = 'text2video'  // 无图 → 文生视频
  }

  const params: Record<string, any> = {
    prompt,
    model: config.model || useModelsStore().defaultVideoModel,
    mode,
  }

  // 视频时长（秒）
  if (config.seconds) {
    params.seconds = config.seconds
  }

  // 画面比例（如 "16:9"）
  if (config.aspect_ratio) {
    params.aspect_ratio = config.aspect_ratio
  }

  // 根据模式传参考图
  if (mode === 'keyframes') {
    // 关键帧模式：传 images 数组（起始帧 + 结束帧）
    params.images = allImages.slice(0, 2)
    params.image_mime_types = allImages.slice(0, 2).map(() => 'image/png')
  } else if (mode === 'image2video') {
    // 图生视频模式：取第一张参考图
    params.image = allImages[0]
    params.image_mime_type = 'image/png'
  }

  const resp = await createVideoTask(params as VideoGenerationRequest)
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

  while (true) {
    if (Date.now() - startTime > timeout) {
      queueStore.updateCanvasTask(taskId, { status: 'failed' })
      throw new Error('视频生成任务超时（超过 10 分钟未完成）')
    }

    const data = await getVideoStatus(taskId)
    if (!data) {
      queueStore.updateCanvasTask(taskId, { status: 'failed' })
      throw new Error('查询视频任务状态失败')
    }

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
export async function executeMergeVideoGeneration(configId: string, store: CanvasStore, options: GenerationOptions = {}): Promise<string> {
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

  if (onProgress) onProgress('building', { inputSummary: ctx.inputSummary })

  // 3. 立刻创建 loading 状态的结果节点
  const newNodeId = createLoadingResultNode(store, configNode, true)

  const config: GenerationConfig = {
    model: configNode.content?.model || useModelsStore().defaultVideoModel,
    seconds: configNode.content?.seconds || 5,
    aspect_ratio: configNode.content?.aspect_ratio || '16:9',
  }

  // 4. 异步执行生成 + 轮询 + 回填（不阻塞调用方）
  ;(async () => {
    try {
      if (onProgress) onProgress('creating', { index: 0, total: 1 })

      // 创建视频任务
      const taskResp = await createVideoGenerationTask(ctx, config)
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
    } catch (err) {
      // 失败：更新节点为 error 状态
      const errMsg = (err as Error).message || '视频生成失败'
      store.updatePanel(newNodeId, {
        content: { status: 'error', errorDetails: errMsg },
      })
      if (onProgress) onProgress('error', { resultNodeIds: [newNodeId], error: errMsg })
    }
  })()

  // 立刻返回新节点 ID（loading 状态）
  return newNodeId
}
