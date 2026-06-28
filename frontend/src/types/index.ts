/* =====================================================
 * 前后端共享类型定义 — 对齐后端 Pydantic Schema
 *
 * 命名规则：前端 Request/Response 类型与后端 Schema 一一对应
 * ===================================================== */

// =====================================================
// 通用类型
// =====================================================

/** 文件信息 — 用于组件间传递上传的文件数据 */
export interface FileInfo {
  /** 文件名 */
  name: string
  /** Base64 编码的文件内容（文件上传时使用） */
  base64: string | null
  /** 预览 URL（用于前端显示） */
  previewUrl: string
  /** MIME 类型 */
  mimeType: string
  /** 文件大小（字节） */
  size: number | null
  /** 数据来源：本地文件或远程 URL */
  source: 'file' | 'url'
  /** 原始 URL（当 source 为 'url' 时使用） */
  url?: string
}

/** 健康检查响应 — 对齐 HealthResponse */
export interface HealthResponse {
  status: string
  service: string
}

/** 模型信息 — 对齐 ModelInfo */
export interface ModelInfo {
  id: string          // 模型标识，如 agnes-image-2.1-flash
  name: string        // 显示名称，如 Agnes Image 2.1 Flash
  type: string        // 模型类型：image / video / chat
  provider: string    // 模型供应商，如 Agnes / 字节跳动 / OpenAI
  capabilities: string[]  // 能力标签，如 text2image, image2image, keyframes
}

/** 图片尺寸选项（含比例信息，供前端绘制比例图标） */
export interface ImageSizeOption {
  /** 传给 API 的尺寸值，如 1024x768 */
  value: string
  /** 宽高比宽分量 */
  w: number
  /** 宽高比高分量 */
  h: number
  /** 显示标签，如 16:9 横屏 */
  label: string
  /** 清晰度等级：sd=标清 / hd=超清 / 4k=4K */
  tier?: 'sd' | 'hd' | '4k'
  /** 实际输出像素数（用于 UI 展示） */
  pixels?: number
}

/** 视频宽高比选项 */
export interface VideoAspectRatioOption {
  /** 传给 API 的比例值，如 16:9 */
  value: string
  /** 宽高比宽分量 */
  w: number
  /** 宽高比高分量 */
  h: number
  /** 显示标签，如 16:9 横屏 */
  label: string
}

/** 视频分辨率选项（以高度为基准，宽度按比例计算） */
export interface VideoResolutionOption {
  /** 高度像素值，如 768 */
  value: number
  /** 显示标签，如 720p 高清 */
  label: string
  /** 16:9 下的参考宽度 */
  width_16_9: number
}

/** 前端可用配置 — 对齐 ConfigResponse */
export interface ConfigResponse {
  models: ModelInfo[]
  image_sizes: string[]
  image_size_options: ImageSizeOption[]
  default_image_size: string
  video_aspect_ratios: VideoAspectRatioOption[]
  default_video_aspect_ratio: string
  video_resolutions: VideoResolutionOption[]
  default_video_resolution: number
  video_num_frames: number[]
  video_durations: number[]
  default_video_duration: number
  video_frame_rates: number[]
  default_frame_rate: number
  default_video_width: number
  default_video_height: number
  max_upload_size_mb: number
  watermark?: WatermarkConfigPublic | null
}

/** 公开水印配置（前端 CSS 水印用） */
export interface WatermarkConfigPublic {
  enabled: boolean
  type: 'text' | 'image'
  text: string
  font_size: number
  color: string
  opacity: number
  position: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'center'
  margin: number
  image_url?: string | null
  image_width: number
}

/** 生成记录 — 对齐 GenerationRecord */
export interface GenerationRecord {
  id: number
  type: 'image' | 'video'
  prompt: string
  model?: string | null
  params?: Record<string, unknown> | null
  mode?: 'text2image' | 'image2image' | 'text2video' | 'image2video' | 'keyframes' | null
  result_url?: string | null
  status: string
  task_id?: string | null
  credits_consumed?: number       // 本次任务消耗的积分数（与积分流水 ref_id 对应）
  created_at?: string | null
  is_public?: boolean             // 是否已公开分享到广场（Plaza）
  public_shared_at?: string | null
  likes_count?: number
  views_count?: number
  moderation_status?: 'pending' | 'approved' | 'rejected'  // 审核状态
  moderation_reason?: string | null
  moderation_flags?: string[] | null
}

/** 历史列表响应 — 对齐 HistoryListResponse */
export interface HistoryListResponse {
  total: number
  page: number
  page_size: number
  items: GenerationRecord[]
  total_image_count: number
  total_video_count: number
}

/** 删除操作响应 — 对齐 DeleteResponse */
export interface DeleteResponse {
  success: boolean
  message: string
}

/** 批量删除请求 — 对齐 BatchDeleteRequest */
export interface BatchDeleteRequest {
  ids: number[]
}

/** 批量删除响应 — 对齐 BatchDeleteResponse */
export interface BatchDeleteResponse {
  success: boolean
  message: string
  deleted_count: number
  failed_ids: number[]
}

// =====================================================
// 图片生成类型
// =====================================================

/** 图片生成请求 — 对齐 ImageGenerationRequest */
export interface ImageGenerationRequest {
  prompt: string
  model: string
  size: string
  response_format: 'url' | 'b64_json'
  quality?: string | null
  mode?: 'text2image' | 'image2image' | null
  /** 多图参考（base64 data URI 或纯 base64 字符串） */
  base64_images?: string[] | null
  /** 多图参考（公网 URL） */
  image_urls?: string[] | null
  /** 旧字段：单张参考图 base64 */
  base64_image?: string | null
  /** 旧字段：单张参考图 URL */
  image_url?: string | null
  /** 蒙版局部编辑（inpainting） */
  mask?: string | null
}

/** 图片生成响应 — 对齐 ImageGenerationResponse */
export interface ImageGenerationResponse {
  id?: number | null
  status: string
  url?: string | null
  b64_json?: string | null
  model: string
  prompt: string
  size: string
  created_at?: string | null
  message?: string | null
}

/** 图片异步任务创建响应（内联 dict） */
export interface ImageTaskCreatedResponse {
  task_id: string
  id?: string
  status: string
  prompt?: string
  model?: string
  size?: string
  created_at?: string
  message?: string
}

/** 图片异步任务状态响应（内联 dict） */
export interface ImageTaskStatusResponse {
  task_id?: string
  status: string
  progress: number
  result_url?: string | null
  url?: string | null
  elapsed_sec?: number
  message?: string | null
}

/** 图片任务取消响应 */
export interface ImageTaskCancelResponse {
  success: boolean
  task_id: string
  status: string
  message: string
}

/** 单张图片记录响应 — 对齐 ImageRecordResponse */
export interface ImageRecordResponse {
  id: number
  type: 'image'
  prompt: string
  model?: string | null
  params?: Record<string, unknown> | null
  result_url?: string | null
  status: string
  created_at?: string | null
}

// =====================================================
// 视频生成类型
// =====================================================

/** 视频生成请求 — 对齐 VideoGenerationRequest */
export interface VideoGenerationRequest {
  prompt: string
  negative_prompt?: string | null
  model: string
  aspect_ratio?: string | null
  seconds?: number | null
  num_frames?: number | null
  frame_rate?: number | null
  width?: number | null
  height?: number | null
  mode?: 'text2video' | 'image2video' | 'keyframes' | null
  image?: string | null
  images?: string[] | null
  image_mime_type?: string | null
  image_mime_types?: string[] | null
  seed?: number | null
}

/** 视频任务创建响应 — 对齐 VideoTaskCreatedResponse */
export interface VideoTaskCreatedResponse {
  task_id?: string | null
  video_id?: string | null
  status: string
  prompt: string
  model: string
  num_frames: number
  frame_rate: number
  width: number
  height: number
  mode: string
  message?: string | null
}

/** 视频任务状态响应 — 对齐 VideoStatusResponse */
export interface VideoStatusResponse {
  task_id?: string | null
  video_id?: string | null
  status: string
  progress: number
  video_url?: string | null
  message?: string | null
  elapsed_sec: number
}

// =====================================================
// 聊天类型
// =====================================================

/** 聊天会话 */
export interface ChatSession {
  id: number
  title: string
  created_at: string
  updated_at?: string
  messages?: ChatMessage[]
}

/** 聊天消息 */
export interface ChatMessage {
  id: number
  session_id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  media_items?: MediaItem[]
  attachments?: MessageAttachment[]
  tool_calls?: unknown
  created_at: string
  /** 前端内部标记：是否正在流式更新 */
  _streaming?: boolean
  /** 前端内部标记：id 是否为临时值（Date.now()） */
  _tempId?: boolean
}

/** 消息中的媒体项 */
export interface MediaItem {
  type: 'image' | 'video'
  url: string
  task_id: string
  status: 'pending' | 'processing' | 'success' | 'failed'
}

/** 消息附件 */
export interface MessageAttachment {
  name: string
  base64?: string
  base64_image?: string
  image_url?: string
  video_url?: string
  doc_url?: string
  url?: string
  size: number
  mime_type: string
  source?: 'url' | 'upload'
  _link_type?: 'image' | 'video' | 'document' | 'webpage'
}

/** 创建会话请求 — 对齐 CreateSessionRequest */
export interface CreateSessionRequest {
  title?: string
}

/** 更新会话标题请求 — 对齐 UpdateSessionRequest */
export interface UpdateSessionRequest {
  title: string
}

/** 发送消息请求 — 对齐 SendMessageRequest */
export interface SendMessageRequest {
  content: string
  attachments?: MessageAttachment[] | null
  camera_params?: Record<string, any> | null
}

/** 媒体回调请求 — 对齐 MediaCallbackRequest */
export interface MediaCallbackRequest {
  message_id: number
  task_id: string
  media_url: string
  status: string
}

/** 媒体生成状态响应 */
export interface MediaStatusResponse {
  status: string
  result_url?: string | null
  video_url?: string | null
  url?: string | null
  image_url?: string | null
  progress?: number
  message?: string | null
}

/** SSE 事件类型 */
export interface SSEEvent {
  type: 'user_message' | 'text' | 'tool_call' | 'tool_result' | 'assistant_message' | 'assistant_message_created' | 'title_updated' | 'error' | 'done'
  content?: string
  message?: ChatMessage
  tool?: string
  args?: Record<string, unknown>
  result?: ToolResult
  title?: string
}

/** 工具调用结果 */
export interface ToolResult {
  media_type: 'image' | 'video'
  url?: string
  task_id?: string
  video_id?: string
  status?: string
  prompt?: string
  error?: string
}

/** 会话列表响应 */
export interface ChatSessionListResponse {
  total: number
  page: number
  page_size: number
  items: ChatSession[]
}

/** 消息列表响应 */
export interface ChatMessageListResponse {
  items: ChatMessage[]
}

// =====================================================
// 用户偏好设置类型（对齐后端 DEFAULT_PREFERENCES）
// =====================================================

/** 生成偏好 */
export interface GenerationPreferences {
  default_model_id: string
  default_aspect_ratio: string
  auto_copy_prompt: boolean
  default_image_count: number
}

/** 下载偏好 */
export interface DownloadPreferences {
  auto_download: boolean
  download_directory: string        // 空=默认下载目录；非空=File System Access API 指定目录
  file_naming_pattern: string      // 支持 {type}/{timestamp}/{model}/{uuid}
  classify_by: 'type' | 'date' | 'none'  // type=按图片/视频分类，date=按日期分类，none=不分类
  default_format: 'original' | 'png' | 'jpg' | 'webp'
}

/** 界面偏好 */
export interface UIPreferences {
  theme: 'dark' | 'light' | 'system'
  canvas_grid_visible: boolean
  canvas_grid_size: number
  canvas_snap_to_grid: boolean
}

/** 通知偏好 */
export interface NotificationPreferences {
  sound_on_complete: boolean
  browser_notification: boolean
}

/** 用户全部偏好设置 */
export interface UserPreferences {
  user_id: number
  preferences: {
    generation: GenerationPreferences
    download: DownloadPreferences
    ui: UIPreferences
    notification: NotificationPreferences
  }
  updated_at: string | null
}

/** 更新偏好时的请求结构（支持部分更新，深层每个字段均可选） */
export type UserPreferencesUpdate = {
  generation?: Partial<GenerationPreferences>
  download?: Partial<DownloadPreferences>
  ui?: Partial<UIPreferences>
  notification?: Partial<NotificationPreferences>
}


// =====================================================
// 任务队列类型
// =====================================================

/** 任务类型 */
export type TaskType = 'image' | 'video'

/** 任务状态 */
export type TaskStatus = 'queued' | 'pending' | 'processing' | 'success' | 'failed' | 'cancelled'

/** 任务队列中的单个任务 */
export interface QueueTask {
  taskId: string
  type: TaskType
  status: TaskStatus
  prompt: string
  params: Record<string, unknown>
  resultUrl: string | null
  posterUrl: string | null
  progress: number
  errorMessage: string
  createdAt: number
  updatedAt: number
  pollIntervalMs: number
  rawResponse: unknown
  backendTaskId: string | null
  source?: 'chat' | 'canvas' | 'pipeline' | null
  /** 画布来源任务的节点 ID，用于任务完成后回填结果 */
  panelId?: string | null
}

/** 注册聊天任务参数 */
export interface RegisterChatTaskParams {
  taskId: string
  type: 'image' | 'video'
  prompt?: string
  resultUrl?: string | null
  backendTaskId?: string
}

/** 更新聊天任务参数 */
export interface UpdateChatTaskParams {
  status?: TaskStatus
  resultUrl?: string | null
  progress?: number
}

/** 注册画布任务参数 */
export interface RegisterCanvasTaskParams {
  taskId: string
  type: 'image' | 'video'
  prompt?: string
  resultUrl?: string | null
  backendTaskId?: string
  /** 画布节点 ID，用于任务完成后回填结果 */
  panelId?: string
}

// =====================================================
// Provider 与模型管理类型
// =====================================================

/** API Provider — 对齐 ProviderResponse */
export interface ApiProvider {
  id: number
  name: string
  /** agn-sdk adapter 标识：agnes / volcengine_cv / kling / runway / pika 等 */
  provider_type: string
  base_url: string
  /** API Key 脱敏后的展示值，如 sk-a****b123 */
  api_key: string
  poll_url: string
  is_active: boolean
  is_default: boolean
  sort_order: number
  created_at?: string | null
  updated_at?: string | null
}

/** Provider 列表响应 — 对齐 ProviderListResponse */
export interface ProviderListResponse {
  total: number
  items: ApiProvider[]
}

/** 创建 Provider 请求 — 对齐 ProviderCreateRequest */
export interface ProviderCreateRequest {
  name: string
  /** agn-sdk adapter 标识（默认 agnes） */
  provider_type?: string
  base_url: string
  api_key: string
  poll_url?: string
  is_active?: boolean
  is_default?: boolean
  sort_order?: number
}

/** 更新 Provider 请求 — 对齐 ProviderUpdateRequest */
export interface ProviderUpdateRequest {
  name?: string
  /** agn-sdk adapter 标识（变更后重建 client） */
  provider_type?: string
  base_url?: string
  /** 留空表示不修改 */
  api_key?: string
  poll_url?: string
  is_active?: boolean
  is_default?: boolean
  sort_order?: number
}

/** 模型定义 — 对齐 ModelDefinitionResponse */
export interface ModelDefinition {
  id: number
  provider_id: number
  model_id: string
  display_name: string
  type: string
  provider_name: string
  capabilities: string[]
  is_active: boolean
  is_custom: boolean
  sort_order: number
}

/** 模型定义列表响应 — 对齐 ModelListResponse */
export interface ModelListResponse {
  total: number
  items: ModelDefinition[]
}

/** 添加自定义模型请求 — 对齐 CustomModelCreateRequest */
export interface CustomModelCreateRequest {
  provider_id: number
  model_id: string
  display_name?: string
  model_type?: string
  provider_name?: string
  capabilities?: string[] | null
  sort_order?: number
}

/** 更新模型定义请求 — 对齐 ModelUpdateRequest */
export interface ModelUpdateRequest {
  display_name?: string
  model_type?: string
  provider_name?: string
  capabilities?: string[] | null
  is_active?: boolean
  sort_order?: number
}

/** 模型同步结果 — 对齐 SyncModelsResponse */
export interface SyncModelsResponse {
  provider_id: number
  added: number
  updated: number
  deactivated: number
  total: number
  error?: string | null
}

/** 同步所有 Provider 模型响应 — 对齐 SyncAllResponse */
export interface SyncAllResponse {
  results: SyncModelsResponse[]
}

/* =====================================================
 * 用户认证相关类型
 * ===================================================== */

/** 注册请求体 — 对齐 RegisterRequest */
export interface AuthRegisterRequest {
  /** 用户名（3-32 字符） */
  username: string
  /** 邮箱（必填） */
  email: string
  /** 密码（6-64 字符） */
  password: string
  /** 图片验证码 ID（可选，前端应传） */
  captcha_id?: string
  /** 图片验证码（可选，前端应传） */
  captcha_code?: string
}

/** 登录请求体 — 对齐 LoginRequest */
export interface AuthLoginRequest {
  username: string
  password: string
  /** 图片验证码 ID（可选，前端应传） */
  captcha_id?: string
  /** 图片验证码（可选，前端应传） */
  captcha_code?: string
}

/** 图片验证码响应 — 对齐 CaptchaResponse */
export interface CaptchaResponse {
  captcha_id: string
  image_base64: string
}

/** 发送邮箱验证码请求 — 对齐 SendEmailCodeRequest */
export interface SendEmailCodeRequest {
  email: string
  purpose?: string
}

/** 重置密码请求 — 对齐 ResetPasswordRequest */
export interface ResetPasswordRequest {
  email: string
  code: string
  new_password: string
}

/** 登录/注册成功返回的 token 响应 — 对齐 TokenResponse */
export interface AuthTokenResponse {
  /** JWT access token — 需存储并在后续请求的 Authorization 头使用 */
  access_token: string
  /** token 类型，固定为 'bearer' */
  token_type: string
  /** token 有效期（秒） */
  expires_in: number
}

/** 当前用户信息响应 — 对齐 UserInfoResponse */
export interface UserInfoResponse {
  id: number
  username: string
  nickname?: string | null
  email?: string | null
  avatar_url?: string | null
  credits: number
  role: string
  is_active: boolean
  is_admin: boolean
  watermark_enabled: boolean
  content_safety_strict: boolean
  created_at?: string | null
  last_login_at?: string | null
}

/** 更新个人资料请求体 */
export interface UpdateProfileRequest {
  nickname?: string | null
  email?: string | null
}

// =====================================================
// 管理员：用户与角色管理
// =====================================================

/** 管理员看到的用户行 — 对齐 UserAdminRow */
export interface UserAdminRow {
  id: number
  username: string
  nickname?: string | null
  email?: string | null
  avatar_url?: string | null
  credits: number
  role: string
  is_active: boolean
  is_admin: boolean
  watermark_enabled: boolean
  content_safety_strict: boolean
  created_at?: string | null
  last_login_at?: string | null
}

/** 用户列表响应 */
export interface UserListResponse {
  items: UserAdminRow[]
  total: number
}

/** 修改用户角色请求 */
export interface UpdateRoleRequest {
  role: string
}

/** 修改用户积分请求 */
export interface UpdateCreditsRequest {
  credits: number
}

/** 启用/禁用用户请求 */
export interface UpdateActiveRequest {
  is_active: boolean
}

// =====================================================
// 管理员：积分规则管理
// =====================================================

/** 积分规则响应 — 对齐 CreditRuleResponse */
export interface CreditRuleResponse {
  id?: number
  rule_key: string
  name: string
  value: number
  description?: string
  updated_at?: string
}

/** 修改积分规则请求 — 对齐 CreditRuleUpdateRequest */
export interface CreditRuleUpdateRequest {
  value: number
  name?: string | null
  description?: string | null
}

// =====================================================
// 创意流水线（Creative Pipeline）类型
// 注意：字段命名保持 snake_case，与后端 API 返回一致
// =====================================================

/** 流水线步骤类型（与后端 steps/*.py 的 step_type 一致） */
export type PipelineStepType =
  | 'llm_generate'
  | 'image_batch'
  | 'video_batch'
  | 'ffmpeg_composite'
  | 'tts_generate'
  | 'human_review'

/** 流水线运行状态 */
export type PipelineRunStatus =
  | 'pending' | 'running' | 'success' | 'failed' | 'cancelled' | 'waiting_review'

/** 步骤状态 */
export type PipelineStepStatus =
  | 'pending' | 'running' | 'success' | 'failed' | 'skipped' | 'waiting_review'

/** 资产类型（与后端 VALID_ASSET_TYPES 一致） */
export type AssetType = 'character' | 'prop' | 'scene' | 'brand'

/** 流水线输入配置项 */
export interface PipelineInputConfig {
  key: string
  label: string
  type: 'text' | 'number' | 'style_select' | 'boolean' | 'select' | 'textarea' | 'image_upload'
  required?: boolean
  default?: any
  placeholder?: string
  min?: number
  max?: number
  description?: string
  options?: Array<{ label: string; value: any }>
}

/** 流水线模板 */
export interface PipelineTemplate {
  id: number
  key: string
  name: string
  description: string
  category: string
  thumbnail: string
  thumbnail_url?: string | null
  estimated_credits: number
  estimated_time: string
  estimated_time_minutes?: number
  is_builtin: boolean
  is_public: boolean
  is_approved: boolean
  is_rejected: boolean
  has_pending_revision?: boolean
  submit_reason?: string
  reject_reason?: string
  author_id?: number
  inputs_config: PipelineInputConfig[]
  steps_config: any[]
  tags: string[]
  output_mapping?: Record<string, any> | null
  script_template_id?: number | null
  use_count?: number
  likes_count?: number
  created_at: string
  updated_at: string
}

/** 流水线模板修订草稿（公开模板编辑后 pending revision） */
export interface PipelineTemplateRevision {
  id: number
  template_id: number
  name: string
  description?: string | null
  category: string
  thumbnail_url?: string | null
  inputs_config: Record<string, any>[]
  steps_config: Record<string, any>[]
  output_mapping?: Record<string, any> | null
  script_template_id?: number | null
  estimated_credits: number
  estimated_time_minutes: number
  tags: string[]
  is_approved: boolean
  is_rejected: boolean
  submit_reason?: string | null
  reject_reason?: string | null
  edited_by?: number | null
  created_at?: string | null
  reviewed_at?: string | null
}

/** 流水线运行实例 */
export interface PipelineRun {
  id: number
  template_id: number
  template_name?: string
  name: string
  status: PipelineRunStatus | string
  total_credits: number
  inputs: Record<string, any>
  current_step: string | null
  current_step_key?: string
  progress: number
  error_message: string | null
  output_summary?: Record<string, any>
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

/** 步骤执行记录 */
export interface PipelineStep {
  id: number
  run_id: number
  step_key: string
  name: string
  step_type: PipelineStepType | string
  status: PipelineStepStatus | string
  depends_on: string[]
  sort_order: number
  output_data: Record<string, any>
  input_data?: Record<string, any>
  error_message: string | null
  retry_count: number
  max_retries: number
  timeout_sec?: number
  credits_consumed: number
  started_at: string | null
  finished_at: string | null
  created_at: string
  // ===== 以下字段由 SSE 实时推送，API 返回的 step 不含这些字段 =====
  /** 步骤内整体百分比（0~1 或 0~100，取决于后端实现；前端做兼容处理） */
  progress?: number
  /** 步骤内逐元素进度详情（current/total/phase/phase_text 等） */
  progress_detail?: {
    current?: number
    total?: number
    percent?: number
    phase?: string
    phase_text?: string
    message?: string
  }
  /** 步骤输出摘要文案（运行中显示阶段描述，完成时显示统计摘要） */
  output_summary?: string
}

/** 风格预设 */
export interface StylePreset {
  id: number
  key: string
  name: string
  category: string
  description: string
  visual_prefix: string
  lighting: string
  color_palette: string
  quality_suffix: string
  negative_prompt: string
  camera_language: string
  mood_keywords: string
  preview_image: string
  tags: string[]
  is_builtin: boolean
  is_public?: boolean
  use_count: number
  created_at: string
}

/** 剧本模板 */
export interface ScriptTemplate {
  id: number
  key: string
  name: string
  category: string
  structure: string
  description: string
  prompt_template: string
  scenes_min: number
  scenes_max: number
  default_scene_duration: number
  tags: string[]
  is_builtin: boolean
  created_at: string
}

/** 创意资产（流水线资产库，区别于画布素材库 AssetItem） */
export interface Asset {
  id: number
  type: AssetType | string
  name: string
  description: string
  visual_description: string
  reference_images: string[]
  style_id: number | null
  user_id: number | null
  is_public: boolean
  tags: string[]
  version: number
  parent_id?: number | null
  moderation_status?: string
  likes_count?: number
  views_count?: number
  use_count?: number
  created_at: string
  updated_at: string
}

/** 积分预估结果 */
export interface CreditEstimateResult {
  estimated_total: number
  breakdown: Array<{
    step_key: string
    step_name: string
    step_type: string
    estimated_credits: number
  }>
  note: string
}

/** 创建运行请求 */
export interface CreateRunRequest {
  template_id: number
  inputs: Record<string, any>
  name?: string
}

/** 从生成结果保存到资产库 */
export interface SaveAssetFromGenerationRequest {
  generation_id: number
  type: AssetType | string
  name: string
  description?: string
  visual_description?: string
  style_id?: number
  tags?: string[]
}

/** 列表查询参数 */
export interface PipelineListParams {
  page?: number
  page_size?: number
  category?: string
  search?: string
  is_builtin?: boolean
  scope?: 'market' | 'my'
}

/** 列表返回结果 */
export interface ListResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/** SSE 事件类型 */
export type PipelineSSEEventType =
  | 'state_snapshot' | 'pipeline_started' | 'step_started'
  | 'step_progress' | 'step_completed' | 'step_failed'
  | 'step_skipped' | 'pipeline_completed' | 'pipeline_failed'

/** pipeline 任务注册参数（taskQueue 用） */
export interface RegisterPipelineTaskParams {
  runId: number
  templateName: string
}

/** pipeline 任务更新参数（taskQueue 用） */
export interface UpdatePipelineTaskParams {
  status?: PipelineRunStatus | string
  progress?: number
  currentStep?: string
  totalSteps?: number
  completedSteps?: number
  // 元素级进度（步骤内逐个产物计数，如"3/8 视频已生成"）
  itemCurrent?: number
  itemTotal?: number
  phaseText?: string
}
