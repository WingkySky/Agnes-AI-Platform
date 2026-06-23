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

/** 图片清晰度等级 */
export type ImageTier = 'sd' | 'hd' | '4k'

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
  /** 清晰度等级：sd=标清 / hd=超清 / 4k=4K */
  tier?: ImageTier
  /** 实际输出像素数（用于 UI 展示） */
  pixels?: number
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
  // 图片尺寸：基于 Agnes Image 2.0/2.1 Flash 实测真实输出尺寸
  // 按清晰度等级分组：sd=标清 / hd=超清 / 4k=4K
  // 实测发现：非标准尺寸会被 Agnes 自动降级到 ~1MP 标清档，故只保留真实输出尺寸
  imageSizes: [
    // 标清档 (~1MP, 耗时 ~20s)
    { value: '1024x1024', w: 1,  h: 1,  label: '1:1 方形',  tier: 'sd', pixels: 1048576 },
    { value: '1312x736',  w: 16, h: 9,  label: '16:9 横屏', tier: 'sd', pixels: 965632 },
    { value: '1248x832',  w: 3,  h: 2,  label: '3:2 横屏',  tier: 'sd', pixels: 1038336 },
    { value: '832x1248',  w: 2,  h: 3,  label: '2:3 竖屏',  tier: 'sd', pixels: 1038336 },
    // 超清档 (2048x2048, 4MP, 耗时 ~56s)
    { value: '2048x2048', w: 1,  h: 1,  label: '1:1 方形',  tier: 'hd', pixels: 4194304 },
    // 4K 档 (~8MP, 耗时 ~150s)
    { value: '3840x2160', w: 16, h: 9,  label: '16:9 横屏', tier: '4k', pixels: 8294400 },
    { value: '4096x4096', w: 1,  h: 1,  label: '1:1 方形',  tier: '4k', pixels: 16777216 },
  ],
  defaultImageSize: '1024x1024',

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
  // Agnes 官方 Q&A 限制：FPS 与时长联动：
  //   24 FPS 不超过 15s；30 FPS 不超过 10s；60 FPS 不超过 5s
  // 前端 ParamSelector 会按当前 FPS 过滤可选时长，这里给出全量候选项
  videoDurations: [3, 5, 7, 10, 15],
  defaultVideoDuration: 5,

  // 视频帧率：匹配 Agnes Video V2.0 文档示例（FPS）
  videoFrameRates: [24, 30, 60],
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

// =====================================================
// 清晰度等级相关工具函数
// =====================================================

/** 清晰度等级配置：标签 + 颜色 + 耗时提示 */
export const IMAGE_TIER_CONFIG: Record<ImageTier, {
  label: string
  color: string
  desc: string
}> = {
  sd: {
    label: '标清',
    color: '#909399',
    desc: '约 1MP · 耗时 ~20s',
  },
  hd: {
    label: '超清',
    color: '#409eff',
    desc: '约 4MP · 耗时 ~56s',
  },
  '4k': {
    label: '4K',
    color: '#9c27b0',
    desc: '约 8MP · 耗时 ~150s',
  },
}

/** 清晰度等级列表（按清晰度从低到高排序） */
export const IMAGE_TIER_ORDER: ImageTier[] = ['sd', 'hd', '4k']

/**
 * 获取所有可选的清晰度等级
 * 从 imageSizes 中提取实际存在的 tier，避免显示空等级
 */
export function getAvailableTiers(provider?: string): ImageTier[] {
  const params = getModelParams(provider)
  const tiers = new Set<ImageTier>()
  for (const opt of params.imageSizes) {
    if (opt.tier) tiers.add(opt.tier)
  }
  // 按预定义顺序返回
  return IMAGE_TIER_ORDER.filter(t => tiers.has(t))
}

/**
 * 获取指定清晰度等级下所有可选的图片尺寸
 */
export function getSizesByTier(tier: ImageTier, provider?: string): ImageSizeOption[] {
  const params = getModelParams(provider)
  return params.imageSizes.filter(o => o.tier === tier)
}

/**
 * 获取指定尺寸的清晰度等级
 */
export function getTierBySize(value: string, provider?: string): ImageTier | undefined {
  const params = getModelParams(provider)
  return params.imageSizes.find(o => o.value === value)?.tier
}

/**
 * 格式化像素数为易读字符串
 * 1048576 → "1.05 MP" 或 "1024×1024"
 */
export function formatPixels(pixels?: number): string {
  if (!pixels) return ''
  const mp = pixels / 1e6
  if (mp >= 1) return `${mp.toFixed(2)} MP`
  return `${pixels} px`
}

/**
 * 从尺寸值 "1024x1024" 提取宽高数值
 */
export function sizeToDimensions(value: string): { w: number; h: number } | null {
  const m = value.match(/^(\d+)x(\d+)$/i)
  if (!m) return null
  return { w: parseInt(m[1], 10), h: parseInt(m[2], 10) }
}
