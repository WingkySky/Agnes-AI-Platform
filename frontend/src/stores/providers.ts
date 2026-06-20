/* =====================================================
 * Provider 与模型管理 Store
 * 管理前端配置页的状态：Provider 列表、模型定义列表、加载状态
 * ===================================================== */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  listProviders,
  createProvider,
  updateProvider,
  deleteProvider,
  listAllModels,
  addCustomModel,
  updateModel,
  deleteModel,
  syncProviderModels,
  syncAllProvidersModels,
} from '@/api/providers'
import type {
  ApiProvider,
  ProviderCreateRequest,
  ProviderUpdateRequest,
  ModelDefinition,
  CustomModelCreateRequest,
  ModelUpdateRequest,
  SyncModelsResponse,
} from '@/types'

export const useProvidersStore = defineStore('providers', () => {
  // Provider 列表
  const providers = ref<ApiProvider[]>([])
  // 所有模型定义列表（管理视图，包括未激活和自定义）
  const modelDefinitions = ref<ModelDefinition[]>([])
  // 加载状态
  const loading = ref(false)
  const syncing = ref(false)

  /** 加载 Provider 列表 */
  async function fetchProviders() {
    loading.value = true
    try {
      const resp = await listProviders()
      providers.value = resp.items || []
    } finally {
      loading.value = false
    }
  }

  /** 加载所有模型定义 */
  async function fetchModelDefinitions() {
    loading.value = true
    try {
      const resp = await listAllModels()
      modelDefinitions.value = resp.items || []
    } finally {
      loading.value = false
    }
  }

  /** 加载 Provider 列表 + 模型定义列表 */
  async function fetchAll() {
    loading.value = true
    try {
      await Promise.all([fetchProviders(), fetchModelDefinitions()])
    } finally {
      loading.value = false
    }
  }

  /** 创建 Provider */
  async function addProvider(data: ProviderCreateRequest) {
    const provider = await createProvider(data)
    await fetchProviders()
    return provider
  }

  /** 更新 Provider */
  async function editProvider(providerId: number, data: ProviderUpdateRequest) {
    const provider = await updateProvider(providerId, data)
    await fetchProviders()
    return provider
  }

  /** 删除 Provider */
  async function removeProvider(providerId: number) {
    await deleteProvider(providerId)
    await fetchAll()
  }

  /** 添加自定义模型 */
  async function addModel(data: CustomModelCreateRequest) {
    const defn = await addCustomModel(data)
    await fetchModelDefinitions()
    return defn
  }

  /** 更新模型定义 */
  async function editModel(modelId: string, data: ModelUpdateRequest) {
    const defn = await updateModel(modelId, data)
    await fetchModelDefinitions()
    return defn
  }

  /** 删除模型定义 */
  async function removeModel(modelId: string) {
    await deleteModel(modelId)
    await fetchModelDefinitions()
  }

  /** 同步指定 Provider 的模型列表 */
  async function syncProvider(providerId: number): Promise<SyncModelsResponse> {
    syncing.value = true
    try {
      const result = await syncProviderModels(providerId)
      await fetchModelDefinitions()
      return result
    } finally {
      syncing.value = false
    }
  }

  /** 同步所有 Provider 的模型列表 */
  async function syncAll(): Promise<SyncModelsResponse[]> {
    syncing.value = true
    try {
      const resp = await syncAllProvidersModels()
      await fetchModelDefinitions()
      return resp.results
    } finally {
      syncing.value = false
    }
  }

  return {
    providers,
    modelDefinitions,
    loading,
    syncing,
    fetchProviders,
    fetchModelDefinitions,
    fetchAll,
    addProvider,
    editProvider,
    removeProvider,
    addModel,
    editModel,
    removeModel,
    syncProvider,
    syncAll,
  }
})
