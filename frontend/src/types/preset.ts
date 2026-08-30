/* =====================================================
 * 统一预设广场 TS 类型定义
 * 对齐后端 Preset Schema（五类统一：style/effect/camera/prompt/script）
 * ===================================================== */

/** 预设类型枚举（pipeline 为画布工作流配置，不进广场） */
export type PresetType = 'camera' | 'prompt' | 'style' | 'effect' | 'script' | 'pipeline'

/** 广场主 tab（mine 为管理页"我的预设"列表） */
export type PresetTab = 'plaza' | 'favorites' | 'recent' | 'mine'

/** 预设排序方式 */
export type PresetSort = 'new' | 'hot' | 'name'

/** 提示词配置（style/effect 类型的核心字段） */
export interface PresetPromptConfig {
  prefix?: string
  suffix?: string
  negative_prompt?: string
}

/** 基础预设字段 */
export interface PresetBase {
  id: number
  user_id?: number | null
  name: string
  description?: string | null
  type: PresetType
  category: string
  tags: string[]
  is_public: boolean
  is_approved: boolean
  is_official: boolean
  usage_count: number
  created_at?: string | null
  updated_at?: string | null
}

/** 提示词预设（完整，含广场附加字段） */
export interface PromptPreset extends PresetBase {
  prompt_text: string
  camera_params?: Record<string, unknown> | null
  style_params?: Record<string, unknown> | null
  prompt_config?: PresetPromptConfig | null
  cover_image?: string | null
  /** 动态封面视频 URL（effect/camera 类型，悬停循环播放） */
  cover_video?: string | null
  script_text?: string | null
  pipeline_config?: Record<string, unknown> | null
  author_nickname?: string
  is_favorite?: boolean
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
  prompt_config?: PresetPromptConfig | null
  cover_image?: string | null
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
  prompt_config?: PresetPromptConfig | null
  cover_image?: string | null
  is_official?: boolean
  script_text?: string | null
  pipeline_config?: Record<string, unknown> | null
  is_public?: boolean
}

/** 预设列表查询参数 */
export interface PresetQueryParams {
  tab?: PresetTab
  /** 预设类型，逗号分隔多类型 */
  type?: string
  category?: string
  q?: string
  sort?: PresetSort
  page?: number
  page_size?: number
}

/** 预设列表响应 */
export interface PresetListResponse {
  items: PromptPreset[]
  total: number
}

/** 广场上下文：决定默认类型与类型可见性 */
export type PresetContext = 'image' | 'video' | 'admin'
