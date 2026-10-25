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
  ModelBatchUpdateRequest,
  ModelBatchDeleteRequest,
  ModelRoutesResponse,
  ModelRouteSaveRequest,
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
export function deleteProvider(providerId: number): Promise<null> {
  return client.delete(`/api/providers/${providerId}`)
}

// =====================================================
// 模型定义管理
// =====================================================

/** 列出指定 Provider 的模型 */
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
export function deleteModel(modelId: string): Promise<null> {
  return client.delete(`/api/models/${modelId}`)
}

/** 批量停用/启用模型 */
export function batchUpdateModels(data: ModelBatchUpdateRequest): Promise<{ updated: number }> {
  return client.put('/api/models/batch', data)
}

/** 批量删除模型 */
export function batchDeleteModels(data: ModelBatchDeleteRequest): Promise<{ deleted: number }> {
  return client.post('/api/models/batch-delete', data)
}

/** 批量设置模型积分倍率（实扣=基准价×倍率） */
export function batchSetCostMultiplier(data: { model_ids: string[]; cost_multiplier: number }): Promise<{ updated: number }> {
  return client.put('/api/models/batch-cost-multiplier', data)
}

// =====================================================
// 模型备用路由（多渠道路由 failover）
// =====================================================

/** 查询模型备用路由列表 */
export function listModelRoutes(modelId: string): Promise<ModelRoutesResponse> {
  return client.get(`/api/models/${encodeURIComponent(modelId)}/routes`)
}

/** 保存模型备用路由（整表替换） */
export function saveModelRoutes(modelId: string, data: ModelRouteSaveRequest): Promise<ModelRoutesResponse> {
  return client.put(`/api/models/${encodeURIComponent(modelId)}/routes`, data)
}

/** 测试声明式 HTTP 渠道连接（按模型目录模板真实请求一次） */
export function testHttpProvider(providerId: number): Promise<{
  ok: boolean
  mode: string
  count: number
  sample: string[]
  error: string | null
}> {
  return client.post(`/api/providers/${providerId}/test-http`)
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
