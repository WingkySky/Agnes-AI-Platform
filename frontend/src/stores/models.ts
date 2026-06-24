/* =====================================================
 * 模型配置 Store
 * 从后端 /api/config 获取可用模型列表和参数配置
 * 按 provider 匹配参数预设，兜底使用本地配置
 * ===================================================== */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getPlatformConfig } from '@/api/history'
import type { ModelInfo, ConfigResponse, ImageSizeOption, VideoAspectRatioOption, VideoResolutionOption, WatermarkConfigPublic } from '@/types'
import {
  getModelParams as getLocalModelParams,
  type ModelParams,
} from '@/config/model-params'

export const useModelsStore = defineStore('models', () => {
  // 所有模型列表
  const models = ref<ModelInfo[]>([])
  // 图片尺寸选项（兼容旧版，纯字符串数组）
  const imageSizes = ref<string[]>([])
  // 图片尺寸选项（结构化，含比例信息）
  const imageSizeOptions = ref<ImageSizeOption[]>([])
  // 默认图片尺寸
  const defaultImageSize = ref('1024x1024')
  // 视频宽高比选项
  const videoAspectRatios = ref<VideoAspectRatioOption[]>([])
  // 默认视频宽高比
  const defaultVideoAspectRatio = ref('16:9')
  // 视频分辨率选项
  const videoResolutions = ref<VideoResolutionOption[]>([])
  // 默认视频分辨率（高度）
  const defaultVideoResolution = ref(720)
  // 视频时长选项（秒）
  const videoDurations = ref<number[]>([3, 5, 7, 10, 15])
  // 默认视频时长
  const defaultVideoDuration = ref(5)
  // 视频帧率选项
  const videoFrameRates = ref<number[]>([24, 30])
  // 默认帧率
  const defaultFrameRate = ref(24)
  // 水印配置
  const watermark = ref<WatermarkConfigPublic | null>(null)
  // 是否已加载
  const loaded = ref(false)

  // 按类型分类的模型
  const imageModels = computed(() => models.value.filter((m) => m.type === 'image'))
  const videoModels = computed(() => models.value.filter((m) => m.type === 'video'))
  const chatModels = computed(() => models.value.filter((m) => m.type === 'chat'))

  // 默认模型（各类型第一个）
  const defaultImageModel = computed(() => imageModels.value[0]?.id || '')
  const defaultVideoModel = computed(() => videoModels.value[0]?.id || '')

  /** 从后端加载配置（仅加载一次） */
  async function fetchConfig() {
    if (loaded.value) return
    try {
      const resp: ConfigResponse = await getPlatformConfig()
      models.value = resp.models || []
      // 图片尺寸
      imageSizes.value = resp.image_sizes || []
      imageSizeOptions.value = resp.image_size_options || []
      defaultImageSize.value = resp.default_image_size || '1024x1024'
      // 视频参数
      videoAspectRatios.value = resp.video_aspect_ratios || []
      defaultVideoAspectRatio.value = resp.default_video_aspect_ratio || '16:9'
      videoResolutions.value = resp.video_resolutions || []
      defaultVideoResolution.value = resp.default_video_resolution || 720
      videoDurations.value = resp.video_durations || [3, 5, 7, 10, 15]
      defaultVideoDuration.value = resp.default_video_duration || 5
      videoFrameRates.value = resp.video_frame_rates || [24, 30]
      defaultFrameRate.value = resp.default_frame_rate || 24
      // 水印配置
      watermark.value = resp.watermark || null
      loaded.value = true
    } catch (err) {
      console.error('[models store] 加载配置失败:', err)
    }
  }

  /** 根据模型 ID 查找模型信息 */
  function getModelById(id: string): ModelInfo | undefined {
    return models.value.find((m) => m.id === id)
  }

  /** 根据模式获取对应的模型列表 */
  function getModelsByMode(mode: string): ModelInfo[] {
    if (mode.includes('video')) return videoModels.value
    return imageModels.value
  }

  /** 根据模式获取默认模型 ID */
  function getDefaultModelByMode(mode: string): string {
    if (mode.includes('video')) return defaultVideoModel.value
    return defaultImageModel.value
  }

  /**
   * 获取当前模型的参数配置
   * 优先使用后端返回的结构化配置，兜底使用本地 model-params 配置
   * provider 参数用于匹配本地预设，后端配置为主
   */
  function getModelParamsConfig(provider?: string): ModelParams {
    // 后端已返回结构化配置时直接使用
    if (imageSizeOptions.value.length > 0) {
      return {
        imageSizes: imageSizeOptions.value,
        defaultImageSize: defaultImageSize.value,
        videoAspectRatios: videoAspectRatios.value,
        defaultVideoAspectRatio: defaultVideoAspectRatio.value,
        videoResolutions: videoResolutions.value,
        defaultVideoResolution: defaultVideoResolution.value,
        videoDurations: videoDurations.value,
        defaultVideoDuration: defaultVideoDuration.value,
        videoFrameRates: videoFrameRates.value,
        defaultFrameRate: defaultFrameRate.value,
      }
    }
    // 兜底：使用本地配置（按 provider 匹配）
    return getLocalModelParams(provider)
  }

  return {
    models,
    imageSizes,
    imageSizeOptions,
    defaultImageSize,
    videoAspectRatios,
    defaultVideoAspectRatio,
    videoResolutions,
    defaultVideoResolution,
    videoDurations,
    defaultVideoDuration,
    videoFrameRates,
    defaultFrameRate,
    watermark,
    loaded,
    imageModels,
    videoModels,
    chatModels,
    defaultImageModel,
    defaultVideoModel,
    fetchConfig,
    getModelById,
    getModelsByMode,
    getDefaultModelByMode,
    getModelParamsConfig,
  }
})
