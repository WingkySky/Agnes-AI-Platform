/* =====================================================
 * 模型参数统一配置
 * 集中管理图片分辨率、视频宽高比、时长、帧率等参数预设
 * 各页面/组件通过此配置获取选项，避免硬编码分散
 *
 * 设计原则：
 *   - 按 provider 分类，Agnes 官方参数优先匹配文档
 *   - 未来新增 provider 只需扩展 PROVIDER_PARAMS
 *   - 页面通过 getModelParams() 获取当前模型可用参数
 *   - 图生图时可通过 matchImageSize() 自适应输入图片分辨率
 * ===================================================== */

// =====================================================
// 类型定义
// =====================================================

/** 图片尺寸选项 */
export interface ImageSizeOption {
  /** 传给 API 的值，如 "1024x768" */
  value: string
  /** 宽高比宽分量（用于绘制比例图标） */
  w: number
  /** 宽高比高分量 */
  h: number
  /** 显示标签，如 "16:9 横屏" */
  label: string
}

/** 视频宽高比选项 */
export interface VideoAspectRatioOption {
  /** 传给 API 的值，如 "16:9" */
  value: string
  w: number
  h: number
  label: string
}

/** 单个 Provider 的参数预设 */
export interface ProviderParamPreset {
  /** 图片尺寸选项 */
  imageSizes: ImageSizeOption[]
  /** 默认图片尺寸 */
  defaultImageSize: string
  /** 视频宽高比选项 */
  videoAspectRatios: VideoAspectRatioOption[]
  /** 默认视频宽高比 */
  defaultVideoAspectRatio: string
  /** 视频时长选项（秒） */
  videoDurations: number[]
  /** 默认视频时长（秒） */
  defaultVideoDuration: number
  /** 视频帧率选项 */
  videoFrameRates: number[]
  /** 默认帧率 */
  defaultFrameRate: number
}

/** 模型参数汇总（页面使用） */
export interface ModelParams {
  imageSizes: ImageSizeOption[]
  defaultImageSize: string
  videoAspectRatios: VideoAspectRatioOption[]
  defaultVideoAspectRatio: string
  videoDurations: number[]
  defaultVideoDuration: number
  videoFrameRates: number[]
  defaultFrameRate: number
}

// =====================================================
// Agnes 官方参数预设（匹配 API 文档）
// =====================================================

const AGNES_PARAMS: ProviderParamPreset = {
  // 图片尺寸：覆盖 Agnes Image 2.0/2.1 Flash 文档中所有示例尺寸
  imageSizes: [
    { value: '1280x720',  w: 16, h: 9,  label: '16:9 横屏' },
    { value: '1024x768',  w: 4,  h: 3,  label: '4:3 横屏' },
    { value: '1536x1024', w: 3,  h: 2,  label: '3:2 横屏' },
    { value: '1792x1024', w: 7,  h: 4,  label: '7:4 宽幅' },
    { value: '1024x1024', w: 1,  h: 1,  label: '1:1 方形' },
    { value: '1024x1536', w: 2,  h: 3,  label: '2:3 竖屏' },
    { value: '720x1280',  w: 9,  h: 16, label: '9:16 竖屏' },
    { value: '1024x1792', w: 4,  h: 7,  label: '4:7 窄幅' },
  ],
  defaultImageSize: '1280x720',

  // 视频宽高比：匹配 Agnes Video V2.0 文档
  videoAspectRatios: [
    { value: '16:9', w: 16, h: 9,  label: '16:9 横屏' },
    { value: '4:3',  w: 4,  h: 3,  label: '4:3 横屏' },
    { value: '1:1',  w: 1,  h: 1,  label: '1:1 方形' },
    { value: '3:4',  w: 3,  h: 4,  label: '3:4 竖屏' },
    { value: '9:16', w: 9,  h: 16, label: '9:16 竖屏' },
  ],
  defaultVideoAspectRatio: '16:9',

  // 视频时长（秒）：覆盖常见创作场景
  videoDurations: [3, 5, 7, 10, 15],
  defaultVideoDuration: 5,

  // 视频帧率：匹配 Agnes Video V2.0 文档示例
  videoFrameRates: [24, 30],
  defaultFrameRate: 24,
}

// =====================================================
// 通用/其他 Provider 预设（兜底）
// =====================================================

const DEFAULT_PARAMS: ProviderParamPreset = {
  imageSizes: [
    { value: '1024x1024', w: 1, h: 1,  label: '1:1 方形' },
    { value: '1024x768',  w: 4, h: 3,  label: '4:3 横屏' },
    { value: '768x1024',  w: 3, h: 4,  label: '3:4 竖屏' },
    { value: '1280x720',  w: 16, h: 9, label: '16:9 横屏' },
    { value: '720x1280',  w: 9, h: 16, label: '9:16 竖屏' },
  ],
  defaultImageSize: '1024x1024',
  videoAspectRatios: AGNES_PARAMS.videoAspectRatios,
  defaultVideoAspectRatio: '16:9',
  videoDurations: [3, 5, 8, 10],
  defaultVideoDuration: 5,
  videoFrameRates: [24, 30],
  defaultFrameRate: 24,
}

// =====================================================
// Provider 参数映射表
// =====================================================

const PROVIDER_PARAMS: Record<string, ProviderParamPreset> = {
  Agnes: AGNES_PARAMS,
  // 未来新增 provider 在此扩展，例如：
  // OpenAI: OPENAI_PARAMS,
  // 字节跳动: BYTEDANCE_PARAMS,
}

// =====================================================
// 公共 API
// =====================================================

/**
 * 根据 provider 名称获取参数预设
 * 未匹配到时返回通用兜底预设
 */
export function getProviderParams(provider: string): ProviderParamPreset {
  return PROVIDER_PARAMS[provider] || DEFAULT_PARAMS
}

/**
 * 根据模型信息获取参数配置
 * 优先按 provider 匹配，兜底用通用预设
 */
export function getModelParams(provider?: string): ModelParams {
  const preset = provider ? getProviderParams(provider) : AGNES_PARAMS
  return {
    imageSizes: preset.imageSizes,
    defaultImageSize: preset.defaultImageSize,
    videoAspectRatios: preset.videoAspectRatios,
    defaultVideoAspectRatio: preset.defaultVideoAspectRatio,
    videoDurations: preset.videoDurations,
    defaultVideoDuration: preset.defaultVideoDuration,
    videoFrameRates: preset.videoFrameRates,
    defaultFrameRate: preset.defaultFrameRate,
  }
}

/**
 * 解析尺寸字符串为宽高数值
 * "1024x768" → { width: 1024, height: 768 }
 */
export function parseSize(size: string): { width: number; height: number } | null {
  const match = size.match(/^(\d+)x(\d+)$/i)
  if (!match) return null
  return { width: parseInt(match[1], 10), height: parseInt(match[2], 10) }
}

/**
 * 根据输入图片尺寸匹配最接近的预设尺寸
 * 用于图生图时自动适配分辨率，免去手动选择
 *
 * 匹配逻辑：
 *   1. 优先匹配宽高比最接近的选项
 *   2. 同比例下选面积最接近的
 *   3. 找不到时返回默认尺寸
 */
export function matchImageSize(
  imgWidth: number,
  imgHeight: number,
  provider?: string,
): string {
  const params = getModelParams(provider)
  if (!imgWidth || !imgHeight) return params.defaultImageSize

  const imgRatio = imgWidth / imgHeight
  let bestMatch = params.defaultImageSize
  let bestScore = Infinity

  for (const opt of params.imageSizes) {
    const optRatio = opt.w / opt.h
    // 比例差异权重更高，面积差异次之
    const ratioDiff = Math.abs(imgRatio - optRatio)
    const sizeScore = ratioDiff * 1000 // 比例差异放大权重

    if (sizeScore < bestScore) {
      bestScore = sizeScore
      bestMatch = opt.value
    }
  }

  return bestMatch
}

/**
 * 根据输入图片尺寸匹配最接近的视频宽高比
 * 用于图生视频时自动适配比例
 */
export function matchVideoAspectRatio(
  imgWidth: number,
  imgHeight: number,
  provider?: string,
): string {
  const params = getModelParams(provider)
  if (!imgWidth || !imgHeight) return params.defaultVideoAspectRatio

  const imgRatio = imgWidth / imgHeight
  let bestMatch = params.defaultVideoAspectRatio
  let bestDiff = Infinity

  for (const opt of params.videoAspectRatios) {
    const optRatio = opt.w / opt.h
    const diff = Math.abs(imgRatio - optRatio)
    if (diff < bestDiff) {
      bestDiff = diff
      bestMatch = opt.value
    }
  }

  return bestMatch
}

/**
 * 获取图片尺寸选项中指定 value 的 label
 */
export function getImageSizeLabel(value: string, provider?: string): string {
  const params = getModelParams(provider)
  const opt = params.imageSizes.find(o => o.value === value)
  return opt?.label || value
}

/**
 * 获取视频宽高比选项中指定 value 的 label
 */
export function getVideoAspectRatioLabel(value: string, provider?: string): string {
  const params = getModelParams(provider)
  const opt = params.videoAspectRatios.find(o => o.value === value)
  return opt?.label || value
}
