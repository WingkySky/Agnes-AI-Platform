/* =====================================================
 * 摄像机预设相关 API 封装
 * - 预设列表查询
 * - 对齐后端 REST API：GET /api/camera-presets
 * ===================================================== */

import client from './client'

// =====================================================
// 类型定义
// =====================================================

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
