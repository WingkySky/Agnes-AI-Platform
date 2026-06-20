/* =====================================================
 * 模型配置 Store
 * 从后端 /api/config 获取可用模型列表，按类型自动分类
 * ===================================================== */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getPlatformConfig } from '@/api/history'
import type { ModelInfo, ConfigResponse } from '@/types'

export const useModelsStore = defineStore('models', () => {
  // 所有模型列表
  const models = ref<ModelInfo[]>([])
  // 图片尺寸选项
  const imageSizes = ref<string[]>([])
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
      imageSizes.value = resp.image_sizes || []
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

  return {
    models,
    imageSizes,
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
  }
})
