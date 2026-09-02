/* =====================================================
 * 提示词预设相关 API 封装（统一预设广场）
 * - 列表（tab=plaza/favorites/recent/mine）/详情/创建/更新/删除
 * - 收藏 toggle / 使用记录 / Fork / 投稿 / 导入导出
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
 * 获取预设列表（统一预设广场）
 * 支持 tab / type / category / q / sort / page 参数
 */
export function getPresets(params: PresetQueryParams = {}): Promise<PresetListResponse> {
  return client.get('/api/presets', { params })
}

/**
 * 获取单个预设详情
 */
export function getPreset(id: number): Promise<PromptPreset> {
  return client.get(`/api/presets/${id}`)
}

/**
 * 创建预设
 */
export function createPreset(data: PresetCreate): Promise<PromptPreset> {
  return client.post('/api/presets', data)
}

/**
 * 更新预设
 */
export function updatePreset(id: number, data: PresetUpdate): Promise<PromptPreset> {
  return client.put(`/api/presets/${id}`, data)
}

/**
 * 删除预设
 */
export function deletePreset(id: number): Promise<{ message: string }> {
  return client.delete(`/api/presets/${id}`)
}

/**
 * 收藏/取消收藏（toggle）
 */
export function toggleFavorite(id: number): Promise<{ is_favorite: boolean }> {
  return client.post(`/api/presets/${id}/favorite`)
}

/**
 * 记录一次使用（最近使用 + 热度）
 */
export function recordPresetUse(id: number): Promise<{ message: string }> {
  return client.post(`/api/presets/${id}/use`)
}

/**
 * AI 生成预设封面（管理员，官方卡维护）
 * effect/camera 类型返回 cover_video（动态封面），其余返回 cover_image
 */
export function generatePresetCover(id: number): Promise<{ cover_image?: string; cover_video?: string }> {
  return client.post(`/api/presets/${id}/generate-cover`)
}

/**
 * Fork 预设到名下
 */
export function forkPreset(id: number): Promise<PromptPreset> {
  return client.post(`/api/presets/${id}/fork`)
}

/**
 * 投稿公开审核
 */
export function submitPreset(id: number): Promise<PromptPreset> {
  return client.post(`/api/presets/${id}/submit`)
}

