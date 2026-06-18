/* =====================================================
 * 画布多元素合并生成核心逻辑
 * - 参考 infinite-canvas 项目的 Config 节点 + @[node:xxx] 引用模式
 * - 收集 Config 节点的上游资源（根据连线查找）
 * - 解析 composerContent 中的 @[node:xxx] 引用 token
 * - 文本资源拼到 prompt 末尾，图片资源作为 referenceImages 数组
 * - 调用 /api/images/tasks 创建异步生成任务
 * - 轮询任务状态，完成后回填结果到画布新节点
 *
 * 核心数据流：
 *   Config 节点 + 上游资源 + composerContent
 *     → buildGenerationContext() 合并为 { prompt, referenceImages }
 *     → createImageTask() 创建任务
 *     → pollImageTask() 轮询状态
 *     → 回填结果到新 image 节点 + 连线
 * ===================================================== */

import { createImageTask, getImageTaskStatus } from '@/api/images'

// ---------- 常量 ----------

/** @[node:xxx] 引用 token 的正则匹配模式 */
const NODE_REFERENCE_PATTERN = /@\[node:([^\]]+)\]/g

/** 资源类型标签生成器：图片1、图片2、文本1、视频1... */
function resourceLabel(type, index) {
  const labels = { image: '图片', text: '文本', video: '视频', audio: '音频' }
  return `${labels[type] || '资源'}${index + 1}`
}

// ---------- 资源收集 ----------

/**
 * 判断面板是否为资源节点（可作为生成输入）
 * - image / text / video / audio 类型都是资源节点
 * - config / frame / quick-generate 不是资源节点
 */
export function isResourceNode(panel) {
  if (!panel) return false
  return ['image', 'text', 'video', 'audio'].includes(panel.type)
}

/**
 * 获取指定节点的所有上游资源节点（根据连线查找）
 * - 查找 connections 中 target_panel_id === nodeId 的所有 source_panel_id
 * - 过滤掉非资源节点
 * @param {string} nodeId - 目标节点 ID
 * @param {Array} panels - 所有面板
 * @param {Array} connections - 所有连线
 * @returns {Array} 上游资源节点数组
 */
export function getUpstreamNodes(nodeId, panels, connections) {
  const upstreamIds = connections
    .filter((c) => c.target_panel_id === nodeId)
    .map((c) => c.source_panel_id)
    .filter(Boolean)

  const panelMap = new Map(panels.map((p) => [p.id, p]))
  return upstreamIds
    .map((id) => panelMap.get(id))
    .filter((p) => p && isResourceNode(p))
}

/**
 * 从资源节点提取内容
 * - image: 返回 { type: 'image', nodeId, imageUrl, title }
 * - text: 返回 { type: 'text', nodeId, text, title }
 * - video: 返回 { type: 'video', nodeId, videoUrl, title }
 */
function extractResourceContent(panel) {
  if (!panel) return null
  const c = panel.content || {}
  const title = panel.name || panel.type

  switch (panel.type) {
    case 'image':
      return {
        type: 'image',
        nodeId: panel.id,
        imageUrl: c.imageUrl || c.image || c.url || '',
        title,
      }
    case 'text':
      return {
        type: 'text',
        nodeId: panel.id,
        text: c.text || '',
        title,
      }
    case 'video':
      return {
        type: 'video',
        nodeId: panel.id,
        videoUrl: c.videoUrl || c.url || '',
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
export function extractResourceContentForComposer(panel) {
  if (!panel) return null
  const c = panel.content || {}
  const title = panel.name || panel.type
  switch (panel.type) {
    case 'image':
      return {
        nodeId: panel.id,
        type: 'image',
        title,
        imageUrl: c.imageUrl || c.image || c.url || '',
      }
    case 'text':
      return {
        nodeId: panel.id,
        type: 'text',
        title,
        text: c.text || '',
      }
    case 'video':
      return {
        nodeId: panel.id,
        type: 'video',
        title,
        videoUrl: c.videoUrl || c.url || '',
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
 *
 * @param {Object} configNode - Config 节点
 * @param {Array} panels - 所有面板
 * @param {Array} connections - 所有连线
 * @returns {{ prompt: string, referenceImages: string[], referenceTexts: string[], inputSummary: object }}
 */
export function buildGenerationContext(configNode, panels, connections) {
  if (!configNode) return null

  // 收集上游资源
  const upstreamPanels = getUpstreamNodes(configNode.id, panels, connections)
  const inputs = upstreamPanels.map(extractResourceContent).filter(Boolean)

  // 获取组装提示词（composerContent）或普通 prompt
  const composerContent = configNode.content?.composerContent?.trim()
  const basePrompt = composerContent || configNode.content?.prompt || ''

  // 输入摘要（供 UI 显示）
  const inputSummary = {
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
function buildSimpleContext(inputs, basePrompt, inputSummary) {
  const textBlocks = inputs
    .filter((i) => i.type === 'text' && i.text)
    .map((i) => i.text)

  const referenceImages = inputs
    .filter((i) => i.type === 'image' && i.imageUrl)
    .map((i) => i.imageUrl)

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
function buildComposerContext(inputs, composerContent, inputSummary) {
  const inputByNodeId = new Map(inputs.map((i) => [i.nodeId, i]))
  const labelByNodeId = new Map()
  const selectedImages = []
  const textBlocks = []
  const counts = { image: 0, text: 0, video: 0, audio: 0 }
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
 * 把图片 URL 列表分类为 base64 数组和 URL 数组
 * - 以 http 开头的为 URL，其余为 base64
 */
function classifyImages(images) {
  const base64Images = []
  const imageUrls = []
  for (const img of images) {
    if (!img) continue
    if (img.trim().toLowerCase().startsWith('http')) {
      imageUrls.push(img.trim())
    } else {
      base64Images.push(img)
    }
  }
  return { base64Images, imageUrls }
}

/**
 * 创建图片生成任务（调用 /api/images/tasks）
 * - 根据是否有参考图自动选择 text2image / image2image 模式
 * - 多图参考：base64_images / image_urls 数组
 *
 * @param {Object} ctx - 生成上下文 { prompt, referenceImages }
 * @param {Object} config - Config 节点配置 { model, size, response_format }
 * @returns {Promise<{ task_id: string }>}
 */
export async function createGenerationTask(ctx, config) {
  const { prompt, referenceImages } = ctx
  const { base64Images, imageUrls } = classifyImages(referenceImages || [])

  const params = {
    prompt,
    model: config.model || 'agnes-image-2.1-flash',
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
 *
 * @param {string} taskId - 任务 ID
 * @param {Function} onProgress - 进度回调 (status, data) => void
 * @param {number} timeout - 超时时间（毫秒），默认 300000（5分钟）
 * @returns {Promise<{ status: string, resultUrl: string }>}
 */
export async function pollImageTask(taskId, onProgress, timeout = 300000) {
  const startTime = Date.now()
  const interval = 2000

  while (true) {
    if (Date.now() - startTime > timeout) {
      throw new Error('生成任务超时（超过 5 分钟未完成）')
    }

    const data = await getImageTaskStatus(taskId)
    if (!data) {
      throw new Error('查询任务状态失败')
    }

    const status = data.status || 'pending'
    if (onProgress) onProgress(status, data)

    // 完成
    if (status === 'success' || status === 'done' || status === 'completed') {
      const resultUrl = data.result_url || data.url || ''
      if (!resultUrl) {
        throw new Error('生成完成但未返回图片 URL')
      }
      return { status: 'success', resultUrl }
    }

    // 失败
    if (status === 'failed' || status === 'error') {
      throw new Error(data.message || data.error || '生成失败')
    }

    // 取消
    if (status === 'cancelled') {
      throw new Error('任务已取消')
    }

    // 继续等待
    await new Promise((resolve) => setTimeout(resolve, interval))
  }
}

// ---------- 完整生成流程 ----------

/**
 * 执行完整的合并生成流程
 * 1. 构建生成上下文（收集上游资源 + 解析 @[node:xxx]）
 * 2. 创建生成任务
 * 3. 轮询任务状态
 * 4. 回填结果到画布新节点
 *
 * @param {string} configId - Config 节点 ID
 * @param {Object} store - Pinia canvas store
 * @param {Object} options - { onProgress, count }
 * @returns {Promise<Array>} 创建的结果节点 ID 数组
 */
export async function executeMergeGeneration(configId, store, options = {}) {
  const { onProgress, count = 1 } = options

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

  const config = {
    model: configNode.content?.model || 'agnes-image-2.1-flash',
    size: normalizeSize(configNode.content?.size),
    response_format: 'url',
  }

  const resultNodeIds = []

  // 3. 按 count 循环创建任务
  const taskCount = Math.max(1, Number(count) || 1)
  for (let i = 0; i < taskCount; i++) {
    if (onProgress) onProgress('creating', { index: i, total: taskCount })

    // 创建任务
    const taskResp = await createGenerationTask(ctx, config)
    const taskId = taskResp.task_id

    if (onProgress) onProgress('polling', { index: i, taskId })

    // 轮询任务状态
    const result = await pollImageTask(taskId, (status, data) => {
      if (onProgress) onProgress('generating', { index: i, status, progress: data.progress })
    })

    // 4. 回填结果到画布新节点
    const newNodeId = addResultNode(store, configNode, result.resultUrl, i)
    resultNodeIds.push(newNodeId)
  }

  if (onProgress) onProgress('done', { resultNodeIds })
  return resultNodeIds
}

/**
 * 把生成结果回填到画布：在 Config 节点右侧创建新 image 节点并连线
 *
 * @param {Object} store - Pinia canvas store
 * @param {Object} configNode - Config 节点
 * @param {string} imageUrl - 生成结果的图片 URL
 * @param {number} index - 第几张（用于错开位置）
 * @returns {string} 新节点 ID
 */
function addResultNode(store, configNode, imageUrl, index = 0) {
  const cols = 4
  const nodeWidth = 200
  const nodeHeight = 200
  const gapX = 220
  const gapY = 240

  const newPanel = {
    type: 'image',
    x: (configNode.x ?? 0) + (configNode.width ?? 240) + 40 + (index % cols) * gapX,
    y: (configNode.y ?? 0) + Math.floor(index / cols) * gapY,
    width: nodeWidth,
    height: nodeHeight,
    content: {
      imageUrl,
      image: imageUrl,
      sourceFrom: configNode.id,
      status: 'success',
      rotation: 0,
    },
  }

  // addPanel 返回新创建面板的 id
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

  return newId
}

/**
 * 尺寸格式归一化
 * - "1:1" → "1024x1024"
 * - "16:9" → "1024x576"
 * - "1024x1024" → 原样返回
 */
function normalizeSize(size) {
  if (!size) return '1024x1024'
  // 已经是 宽x高 格式
  if (/^\d+x\d+$/i.test(size)) return size
  // 比例格式转换
  const ratioMap = {
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
