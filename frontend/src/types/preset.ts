/* =====================================================
 * 统一提示词预设 TS 类型定义
 * 对齐后端 Pydantic Preset Schema（Phase 2A）
 * ===================================================== */

/** 预设类型枚举 */
export type PresetType = 'camera' | 'prompt' | 'style' | 'script' | 'pipeline'

/** 预设排序方式 */
export type PresetSort = 'new' | 'hot' | 'usage'

/** 基础预设字段 */
export interface PresetBase {
  id: number
  user_id: number
  name: string
  description?: string
  type: PresetType
  category: string
  tags: string[]
  is_public: boolean
  is_approved: boolean
  usage_count: number
  created_at: string
  updated_at?: string
}

/** 提示词预设（完整） */
export interface PromptPreset extends PresetBase {
  prompt_text: string
  camera_params?: Record<string, unknown> | null
  style_params?: Record<string, unknown> | null
  script_text?: string | null
  pipeline_config?: Record<string, unknown> | null
}

/** 预设索引条目 */
export interface PresetIndex {
  id: number
  preset_type: PresetType
  preset_id: number
  category: string
  tags: string[]
  user_id: number
  is_public: boolean
  is_approved: boolean
  usage_count: number
  name: string
  description?: string
  created_at: string
}

/** 创建预设请求 */
export interface PresetCreate {
  name: string
  prompt_text?: string
  description?: string
  type?: PresetType
  category?: string
  tags?: string[]
  camera_params?: Record<string, unknown> | null
  style_params?: Record<string, unknown> | null
  script_text?: string | null
  pipeline_config?: Record<string, unknown> | null
  is_public?: boolean
}

/** 更新预设请求（所有字段可选） */
export interface PresetUpdate {
  name?: string
  prompt_text?: string
  description?: string
  category?: string
  tags?: string[]
  camera_params?: Record<string, unknown> | null
  style_params?: Record<string, unknown> | null
  script_text?: string | null
  pipeline_config?: Record<string, unknown> | null
  is_public?: boolean
}

/** 预设列表查询参数 */
export interface PresetQueryParams {
  type?: PresetType
  category?: string
  tags?: string
  search?: string
  sort?: PresetSort
  limit?: number
  offset?: number
}

/** 预设列表响应 */
export interface PresetListResponse {
  items: PromptPreset[]
  total: number
}
