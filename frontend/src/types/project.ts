/* =====================================================
 * 项目制创作相关类型定义 — 对齐后端 schemas/project.py
 *
 * 涵盖: 项目主表、剧本、角色、场景、道具、分镜、帧图、视频、实体素材版本
 * ===================================================== */

// =====================================================
// 项目状态枚举
// =====================================================

/** 项目状态机 */
export type ProjectStatus =
  | 'draft'          // 草稿
  | 'creating'       // 向导运行中
  | 'in_progress'    // 已就绪，可逐个适配
  | 'merging'        // 合成中
  | 'completed'      // 已完成
  | 'archived'       // 已归档

/** 实体类型 */
export type EntityType = 'character' | 'scene' | 'prop'

/** 项目活动视图 */
export type ProjectActiveView = 'manager' | 'canvas'

// =====================================================
// 项目主表
// =====================================================

export interface Project {
  id: number
  title: string
  description?: string | null
  template_id?: number | null
  user_id: number
  status: ProjectStatus
  cover_url?: string | null
  aspect_ratio: string
  resolution: string
  wizard_inputs: Record<string, any>
  active_view: ProjectActiveView
  canvas_data: Record<string, any>
  timeline_data: Record<string, any>
  final_video_url?: string | null
  total_duration: number
  started_at?: string | null
  finished_at?: string | null
  created_at: string
  updated_at: string
  // 关联（详情接口返回）
  scripts?: ProjectScript[]
  characters?: ProjectCharacter[]
  scenes?: ProjectScene[]
  props?: ProjectProp[]
  shots?: ProjectShot[]
}

export interface ProjectCreateRequest {
  title: string
  description?: string
  template_id?: number
  aspect_ratio?: string
  resolution?: string
  wizard_inputs?: Record<string, any>
}

export interface ProjectUpdateRequest {
  title?: string
  description?: string
  cover_url?: string
  aspect_ratio?: string
  resolution?: string
}

export interface ActiveViewUpdateRequest {
  view: ProjectActiveView
}

export interface ProjectListParams {
  status?: ProjectStatus
  search?: string
  page?: number
  page_size?: number
}

export interface ProjectListResult {
  items: Project[]
  total: number
  page: number
  page_size: number
}

// =====================================================
// 剧本
// =====================================================

export interface ProjectScript {
  id: number
  project_id: number
  episode_no: number
  title?: string | null
  content: string
  status: string
  created_at: string
  updated_at: string
}

export interface ScriptCreateRequest {
  episode_no?: number
  title?: string
  content: string
  status?: string
}

export interface ScriptUpdateRequest {
  title?: string
  content?: string
  status?: string
}

export interface ScriptRegenerateRequest {
  prompt_template?: string
  model?: string
  inputs?: Record<string, any>
}

// =====================================================
// 实体素材版本（角色/场景/道具通用）
// =====================================================

export interface ProjectEntityAsset {
  id: number
  entity_type: EntityType
  entity_id: number
  version: number
  file_url?: string | null
  thumbnail_url?: string | null
  prompt?: string | null
  model?: string | null
  generation_id?: number | null
  file_type?: string | null
  file_size?: number | null
  width?: number | null
  height?: number | null
  duration_ms?: number | null
  is_manual: boolean
  is_active: boolean
  created_by?: string | null
  created_at: string
}

export interface SetActiveVersionRequest {
  entity_type: EntityType
  entity_id: number
  version_id: number
}

// =====================================================
// 角色
// =====================================================

export interface ProjectCharacter {
  id: number
  project_id: number
  name: string
  description?: string | null
  appearance_desc?: string | null
  role_type?: string | null
  asset_id?: number | null
  active_image_id?: number | null
  sort_order: number
  created_at: string
  updated_at: string
  // 动态字段（service 注入）
  active_image?: ProjectEntityAsset | null
  versions?: ProjectEntityAsset[]
}

export interface CharacterCreateRequest {
  name: string
  description?: string
  appearance_desc?: string
  role_type?: string
}

export interface CharacterUpdateRequest {
  name?: string
  description?: string
  appearance_desc?: string
  role_type?: string
}

export interface CharacterGenerateImageRequest {
  model?: string
  style_config?: Record<string, any>
}

export interface BatchGenerateCharactersRequest {
  ids: number[]
  model?: string
  style_config?: Record<string, any>
  size?: string
}

// =====================================================
// 场景
// =====================================================

export interface ProjectScene {
  id: number
  project_id: number
  name: string
  description?: string | null
  location?: string | null
  time_of_day?: string | null
  atmosphere?: string | null
  asset_id?: number | null
  active_image_id?: number | null
  sort_order: number
  created_at: string
  updated_at: string
  active_image?: ProjectEntityAsset | null
  versions?: ProjectEntityAsset[]
}

export interface SceneCreateRequest {
  name: string
  description?: string
  location?: string
  time_of_day?: string
  atmosphere?: string
}

export interface SceneUpdateRequest {
  name?: string
  description?: string
  location?: string
  time_of_day?: string
  atmosphere?: string
}

// =====================================================
// 道具
// =====================================================

export interface ProjectProp {
  id: number
  project_id: number
  name: string
  description?: string | null
  visual_desc?: string | null
  asset_id?: number | null
  active_image_id?: number | null
  sort_order: number
  created_at: string
  updated_at: string
  active_image?: ProjectEntityAsset | null
  versions?: ProjectEntityAsset[]
}

export interface PropCreateRequest {
  name: string
  description?: string
  visual_desc?: string
}

export interface PropUpdateRequest {
  name?: string
  description?: string
  visual_desc?: string
}

// =====================================================
// 分镜
// =====================================================

export interface ProjectShot {
  id: number
  project_id: number
  sequence_no: number
  title?: string | null
  shot_type?: string | null
  camera_movement?: string | null
  angle?: string | null
  dialogue?: string | null
  visual_desc?: string | null
  atmosphere?: string | null
  duration_ms?: number | null
  image_prompt?: string | null
  active_frame_image_id?: number | null
  active_video_id?: number | null
  created_at: string
  updated_at: string
  // 关联
  characters?: ProjectCharacter[]
  props?: ProjectProp[]
  frame_images?: ProjectFrameImage[]
  videos?: ProjectVideo[]
  active_frame_image?: ProjectFrameImage | null
  active_video?: ProjectVideo | null
}

export interface ShotCreateRequest {
  sequence_no?: number
  title?: string
  shot_type?: string
  camera_movement?: string
  angle?: string
  dialogue?: string
  visual_desc?: string
  atmosphere?: string
  duration_ms?: number
  image_prompt?: string
}

export interface ShotUpdateRequest {
  sequence_no?: number
  title?: string
  shot_type?: string
  camera_movement?: string
  angle?: string
  dialogue?: string
  visual_desc?: string
  atmosphere?: string
  duration_ms?: number
  image_prompt?: string
}

export interface ShotReorderRequest {
  ids: number[]
}

export interface ShotBindEntityRequest {
  entity_id: number
}

// =====================================================
// 帧图（多版本）
// =====================================================

export interface ProjectFrameImage {
  id: number
  shot_id: number
  version: number
  file_url?: string | null
  thumbnail_url?: string | null
  prompt?: string | null
  model?: string | null
  generation_id?: number | null
  reference_character_ids?: number[]
  width?: number | null
  height?: number | null
  file_size?: number | null
  is_manual: boolean
  is_active: boolean
  created_by?: string | null
  created_at: string
}

export interface GenerateFrameImageRequest {
  model?: string
  style_config?: Record<string, any>
  size?: string
}

export interface BatchGenerateFrameImagesRequest {
  ids: number[]
  model?: string
  style_config?: Record<string, any>
  size?: string
}

// =====================================================
// 视频（多版本）
// =====================================================

export interface ProjectVideo {
  id: number
  shot_id: number
  version: number
  file_url?: string | null
  thumbnail_url?: string | null
  frame_image_id?: number | null
  prompt?: string | null
  model?: string | null
  generation_id?: number | null
  duration_ms?: number | null
  width?: number | null
  height?: number | null
  file_size?: number | null
  is_manual: boolean
  is_active: boolean
  created_by?: string | null
  created_at: string
}

export interface GenerateVideoRequest {
  frame_image_id?: number
  model?: string
  duration_ms?: number
}

// =====================================================
// 资产桥接
// =====================================================

export interface ImportAssetRequest {
  asset_id: number
  entity_type: EntityType
}

export interface PromoteAssetRequest {
  entity_type: EntityType
  entity_id: number
}

// =====================================================
// 画布
// =====================================================

export interface CanvasDataUpdate {
  canvas_data: Record<string, any>
}

export interface CanvasLayoutResponse {
  canvas_data: Record<string, any>
}

// =====================================================
// 合成
// =====================================================

export interface MergeStatusResponse {
  status: ProjectStatus
  final_video_url?: string | null
  total_duration: number
  error?: string | null
}

// =====================================================
// 向导（Wizard）
// =====================================================

export interface WizardCreateRequest {
  template_id?: number
  category?: string
  title: string
  description?: string
  inputs: Record<string, any>
  aspect_ratio?: string
  resolution?: string
}

export interface WizardResumeRequest {
  resume_from: string
}

export interface WizardStepEvent {
  step_key: string
  step_name?: string
  status: 'started' | 'completed' | 'failed'
  error?: string
  data?: Record<string, any>
}

// =====================================================
// SSE 事件类型
// =====================================================

export type ProjectEventType =
  | 'state_snapshot'
  | 'wizard_step_started'
  | 'wizard_step_completed'
  | 'wizard_step_failed'
  | 'wizard_progress'
  | 'entity_updated'
  | 'generation_started'
  | 'generation_progress'
  | 'generation_completed'
  | 'generation_failed'
  | 'active_version_changed'
  | 'project_status_changed'
  | 'merge_progress'
  | 'merge_completed'
  | 'unauthorized'

export interface ProjectSSEPayload {
  event_type: ProjectEventType
  project_id: number
  data?: Record<string, any>
  timestamp?: string
}
