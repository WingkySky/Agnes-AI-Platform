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
  script_id: number
  episode_no: number | null
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
  script_id: number
  episode_no: number | null
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
  script_id: number
  episode_no: number | null
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
  script_id: number
  episode_no: number | null
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
  active_audio_id?: number | null
  created_at: string
  updated_at: string
  // 关联
  characters?: ProjectCharacter[]
  props?: ProjectProp[]
  frame_images?: ProjectFrameImage[]
  videos?: ProjectVideo[]
  audios?: ProjectShotAudio[]
  active_frame_image?: ProjectFrameImage | null
  active_video?: ProjectVideo | null
  active_audio?: ProjectShotAudio | null
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
  // Phase 2 — TTS / 字幕 / 时间线 / 音频激活
  | 'tts_progress'
  | 'tts_completed'
  | 'subtitle_progress'
  | 'subtitle_completed'
  | 'audio_activated'
  | 'timeline_clip_created'
  | 'timeline_clip_updated'
  | 'timeline_clip_deleted'
  | 'unauthorized'

export interface ProjectSSEPayload {
  event_type: ProjectEventType
  project_id: number
  data?: Record<string, any>
  timestamp?: string
}

// =====================================================
// Phase 2 — 配音 / 音色 / 字幕 / 时间线 / BGM
// =====================================================

// ---------- 配音（多版本） ----------

export interface ProjectShotAudio {
  id: number
  shot_id: number
  version: number
  is_active: boolean
  is_manual: boolean
  file_url?: string | null
  text?: string | null
  voice_id?: string | null
  voice_name?: string | null
  character_id?: number | null
  provider?: string | null
  model?: string | null
  duration_ms?: number | null
  file_size?: number | null
  created_by: string
  created_at?: string | null
}

export interface GenerateTTSRequest {
  voice_id?: string
  character_id?: number
  text?: string
  model?: string
  provider?: string
}

export interface BatchGenerateTTSRequest {
  shot_ids: number[]
  voice_id?: string
}

// ---------- 音色 ----------

export interface VoiceOption {
  voice_id: string
  name: string
  gender: 'male' | 'female' | 'neutral'
  suitable_for?: string
}

export interface CharacterVoice {
  id: number
  project_id: number
  character_id: number
  voice_id: string
  voice_name?: string | null
  assigned_at?: string | null
}

export interface AssignCharacterVoiceRequest {
  voice_id: string
  voice_name?: string
}

// ---------- 字幕 ----------

export interface SubtitleStyle {
  font_family: string
  font_size: number
  font_color: string
  outline_color: string
  outline_width: number
  position: 'bottom' | 'top' | 'center'
  margin_vertical: number
}

export interface GenerateSubtitleRequest {
  shot_ids?: number[]
  style?: Record<string, any>
}

export interface GenerateSubtitleAdvancedRequest {
  shot_ids?: number[]
  mode?: 'llm' | 'whisper'
  whisper_model_size?: string
}

export interface SubtitleGenerateResult {
  clips: Array<{
    shot_id: number
    start_time: number
    duration: number
    text: string
  }>
  count: number
  mode: 'llm' | 'whisper'
  whisper_available?: boolean
}

// ---------- 时间线 ----------

export type TimelineTrackType = 'video' | 'audio' | 'subtitle'

export type TransitionType = 'none' | 'fade' | 'slide' | 'wipe' | 'dissolve'

export interface TimelineClip {
  id: number
  project_id: number
  track_type: TimelineTrackType
  track_index: number
  source_type?: string | null
  source_id?: number | null
  shot_id?: number | null
  start_time: number
  duration: number
  trim_start: number
  trim_end?: number | null
  transition_type: TransitionType
  transition_duration: number
  subtitle_text?: string | null
  sort_order: number
  created_at?: string | null
  updated_at?: string | null
  // 源文件信息（后端 get_timeline_data 关联注入，供前端预览使用）
  source_file_url?: string | null
  source_duration_ms?: number | null
  source_width?: number | null
  source_height?: number | null
  source_thumbnail_url?: string | null
  source_ref?: string | null  // BGM 字符串 id 引用（source_id 是 Integer 不够用时使用）
}

export interface TimelineClipCreateRequest {
  track_type: TimelineTrackType
  track_index?: number
  source_type?: string
  source_id?: number
  shot_id?: number
  start_time: number
  duration: number
  trim_start?: number
  trim_end?: number
  transition_type?: TransitionType
  transition_duration?: number
  subtitle_text?: string
  sort_order?: number
  source_ref?: string  // BGM 字符串 id 引用
}

export interface TimelineClipUpdateRequest {
  start_time?: number
  duration?: number
  trim_start?: number
  trim_end?: number
  transition_type?: TransitionType
  transition_duration?: number
  subtitle_text?: string
  track_index?: number
  sort_order?: number
}

export interface TimelineDataResponse {
  clips: TimelineClip[]
  subtitle_style?: Record<string, any>
  total_duration: number
}

export interface TimelineDataUpdateRequest {
  subtitle_style?: Record<string, any>
  draft?: Record<string, any>
}

// ---------- BGM 库 ----------

export type BGMMood = 'calm' | 'corporate' | 'dramatic' | 'uplifting' | 'sad'

export interface BGMItem {
  id: string
  name: string
  mood: BGMMood
  duration: number
  available: boolean
}

// ---------- 高级合成 ----------

export interface MergeAdvancedRequest {
  with_audio?: boolean
  with_subtitle?: boolean
  with_bgm?: boolean
  bgm_id?: string
  use_timeline?: boolean
}

// =====================================================
// 素材库 / 标记 / 轨道状态 / 布局状态（Phase 2 增强）
// =====================================================

/** 素材库项类型 */
export type MediaItemType = 'shot_video' | 'shot_audio' | 'shot_frame_image' | 'bgm'

/** 素材库统一项结构（用于拖拽到时间线） */
export interface MediaLibraryItem {
  id: number
  type: MediaItemType
  name: string
  file_url: string
  thumbnail_url?: string | null
  duration_ms: number
  width?: number | null
  height?: number | null
  shot_id?: number | null
  meta?: {
    voice_name?: string
    mood?: string
    is_static_image?: boolean
    bgm_id?: string  // BGM 字符串 id
  }
}

/** 素材库按类型分组的响应 */
export interface MediaLibraryResponse {
  videos: MediaLibraryItem[]
  audios: MediaLibraryItem[]
  frame_images: MediaLibraryItem[]
  bgms: MediaLibraryItem[]
}

/** 项目标记 */
export interface ProjectMarker {
  id: number
  project_id: number
  time: number
  name?: string | null
  color: string
  created_at?: string
}

/** 标记创建请求 */
export interface MarkerCreateRequest {
  time: number
  name?: string
  color?: string
}

/** 轨道状态（会话级 UI 状态） */
export interface TrackState {
  muted: boolean
  locked: boolean
}

/** 时间线布局状态（localforage 持久化） */
export interface TimelineLayoutState {
  libraryWidth: number
  libraryHidden: boolean
  timelineHeight: number
}
