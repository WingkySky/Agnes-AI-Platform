/* =====================================================
 * 摄像机预设相关 API 封装
 * - 预设列表/详情/创建/更新/删除
 * - 对齐后端 REST API：GET/POST /api/camera-presets,
 *   PUT/DELETE /api/camera-presets/{preset_id}
 * ===================================================== */

import client from './client'

// =====================================================
// 类型定义
// =====================================================

/** 摄像机参数子对象 */
export interface CameraParams {
  camera_model?: string
  focal_length?: string
  aperture?: string
  depth_of_field?: string
  shutter_speed?: string
  shutter_angle?: string
  camera_movement?: string
  camera_angle?: string
  aspect_ratio?: string
  visual_style?: string
}

/** 摄像机预设 */
export interface CameraPreset {
  id: number
  user_id: number
  name: string
  description?: string
  type: string
  category: string
  tags: string[]
  camera_model?: string
  focal_length?: string
  aperture?: string
  depth_of_field?: string
  shutter_speed?: string
  shutter_angle?: string
  camera_movement?: string
  camera_angle?: string
  aspect_ratio?: string
  visual_style?: string
  is_public: boolean
  is_approved: boolean
  usage_count: number
  created_at: string
  updated_at?: string
}

/** 创建预设请求 */
export interface CreateCameraPresetRequest {
  name: string
  description?: string
  category?: string
  tags?: string[]
  camera_model?: string
  focal_length?: string
  aperture?: string
  depth_of_field?: string
  shutter_speed?: string
  shutter_angle?: string
  camera_movement?: string
  camera_angle?: string
  aspect_ratio?: string
  visual_style?: string
  is_public?: boolean
}

/** 更新预设请求（全部字段可选） */
export interface UpdateCameraPresetRequest {
  name?: string
  description?: string
  category?: string
  tags?: string[]
  camera_model?: string
  focal_length?: string
  aperture?: string
  depth_of_field?: string
  shutter_speed?: string
  shutter_angle?: string
  camera_movement?: string
  camera_angle?: string
  aspect_ratio?: string
  visual_style?: string
  is_public?: boolean
}

/** 列表查询参数 */
export interface CameraPresetListParams {
  page?: number
  page_size?: number
  search?: string
  category?: string
  is_public?: boolean
}

/** 分页列表结果 */
export interface ListResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

// =====================================================
// API 函数
// =====================================================

/**
 * 获取摄像机预设列表
 */
export function getCameraPresets(params: CameraPresetListParams = {}): Promise<ListResult<CameraPreset>> {
  return client.get('/api/camera-presets', { params })
}

/**
 * 获取单个摄像机预设详情
 */
export function getCameraPreset(id: number): Promise<CameraPreset> {
  return client.get(`/api/camera-presets/${id}`)
}

/**
 * 创建摄像机预设
 */
export function createCameraPreset(data: CreateCameraPresetRequest): Promise<CameraPreset> {
  return client.post('/api/camera-presets', data)
}

/**
 * 更新摄像机预设
 */
export function updateCameraPreset(id: number, data: UpdateCameraPresetRequest): Promise<CameraPreset> {
  return client.put(`/api/camera-presets/${id}`, data)
}

/**
 * 删除摄像机预设
 */
export function deleteCameraPreset(id: number): Promise<{ message: string; preset_id: number }> {
  return client.delete(`/api/camera-presets/${id}`)
}
