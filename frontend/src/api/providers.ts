/* =====================================================
 * Provider 与模型管理 API 封装
 * 对应后端 /api/providers/* 和 /api/models/* 接口
 * ===================================================== */

import client from './client'
import type {
  ApiProvider,
  ProviderListResponse,
  ProviderCreateRequest,
  ProviderUpdateRequest,
  ModelDefinition,
  ModelListResponse,
  CustomModelCreateRequest,
  ModelUpdateRequest,
  SyncModelsResponse,
  SyncAllResponse,
} from '@/types'

// =====================================================
// Provider 管理
// =====================================================

/** 列出所有 Provider */
export function listProviders(): Promise<ProviderListResponse> {
  return client.get('/api/providers')
}

/** 创建 Provider */
export function createProvider(data: ProviderCreateRequest): Promise<ApiProvider> {
  return client.post('/api/providers', data)
}

/** 更新 Provider */
export function updateProvider(providerId: number, data: ProviderUpdateRequest): Promise<ApiProvider> {
  return client.put(`/api/providers/${providerId}`, data)
}

/** 删除 Provider */
export function deleteProvider(providerId: number): Promise<{ status: string; message: string }> {
  return client.delete(`/api/providers/${providerId}`)
}

// =====================================================
// 模型定义管理
// =====================================================

/** 列出指定 Provider 的模型 */
export function listProviderModels(providerId: number): Promise<ModelListResponse> {
  return client.get(`/api/providers/${providerId}/models`)
}

/** 列出所有模型定义（管理视图） */
export function listAllModels(): Promise<ModelListResponse> {
  return client.get('/api/models')
}

/** 添加自定义模型 */
export function addCustomModel(data: CustomModelCreateRequest): Promise<ModelDefinition> {
  return client.post('/api/models', data)
}

/** 更新模型定义 */
export function updateModel(modelId: string, data: ModelUpdateRequest): Promise<ModelDefinition> {
  return client.put(`/api/models/${modelId}`, data)
}

/** 删除模型定义 */
export function deleteModel(modelId: string): Promise<{ status: string; message: string }> {
  return client.delete(`/api/models/${modelId}`)
}

// =====================================================
// 模型同步
// =====================================================

/** 同步指定 Provider 的模型列表（调用 /models API） */
export function syncProviderModels(providerId: number): Promise<SyncModelsResponse> {
  return client.post(`/api/providers/${providerId}/sync-models`)
}

/** 同步所有 Provider 的模型列表 */
export function syncAllProvidersModels(): Promise<SyncAllResponse> {
  return client.post('/api/providers/sync-all-models')
}
