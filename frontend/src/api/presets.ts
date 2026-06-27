/* =====================================================
 * 提示词预设相关 API 封装
 * - 预设列表/详情/创建/更新/删除
 * - 对齐后端 REST API：GET/POST /api/presets,
 *   PUT/DELETE /api/presets/{preset_id}
 * ===================================================== */

import client from './client'
import type {
  PromptPreset,
  PresetCreate,
  PresetUpdate,
  PresetQueryParams,
  PresetListResponse,
} from '@/types/preset'

/**
 * 获取提示词预设列表
 * 支持 type / category / tags / search / sort 参数
 */
export function getPresets(params: PresetQueryParams = {}): Promise<PresetListResponse> {
  return client.get('/api/presets', { params })
}

/**
 * 获取单个提示词预设详情
 */
export function getPreset(id: number): Promise<PromptPreset> {
  return client.get(`/api/presets/${id}`)
}

/**
 * 创建提示词预设
 */
export function createPreset(data: PresetCreate): Promise<PromptPreset> {
  return client.post('/api/presets', data)
}

/**
 * 更新提示词预设
 */
export function updatePreset(id: number, data: PresetUpdate): Promise<PromptPreset> {
  return client.put(`/api/presets/${id}`, data)
}

/**
 * 删除提示词预设
 */
export function deletePreset(id: number): Promise<{ message: string }> {
  return client.delete(`/api/presets/${id}`)
}
