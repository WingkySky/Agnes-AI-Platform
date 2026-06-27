/* =====================================================
 * 摄像机相关 TS 类型定义
 * 对齐后端 Pydantic CameraPreset Schema
 * ===================================================== */

/** 摄像机参数字段 — 全部 10 个摄像参数，均为可选 */
export interface CameraParams {
  /** 是否启用摄像机参数 */
  enabled: boolean
  /** 摄影机型号，如 Sony FX3 */
  camera_model?: string
  /** 镜头焦段，如 85mm */
  focal_length?: string
  /** 光圈值，如 f/2.8 */
  aperture?: string
  /** 景深描述，如 浅景深 */
  depth_of_field?: string
  /** 快门速度，如 1/250s */
  shutter_speed?: string
  /** 快门角度，如 180° */
  shutter_angle?: string
  /** 运镜方式，如 手持运镜 */
  camera_movement?: string
  /** 拍摄角度，如 平视 */
  camera_angle?: string
  /** 画幅比例，如 2.35:1 */
  aspect_ratio?: string
  /** 视觉风格，如 暖色调胶片风格 */
  visual_style?: string
}

/** 摄像机预设（列表/详情） — 对齐后端 CameraPresetResponse */
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

/** 创建预设请求 — 对齐后端 CameraPresetCreate */
export interface CameraPresetCreate {
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

/** 更新预设请求 — 对齐后端 CameraPresetUpdate */
export interface CameraPresetUpdate {
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

/** 预设列表响应 */
export interface CameraPresetListResponse {
  items: CameraPreset[]
  total: number
  page: number
  page_size: number
}
