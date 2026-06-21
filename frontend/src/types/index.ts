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

/** 前端可用配置 — 对齐 ConfigResponse */
export interface ConfigResponse {
  models: ModelInfo[]
  image_sizes: string[]
  image_size_options: ImageSizeOption[]
  default_image_size: string
  video_aspect_ratios: VideoAspectRatioOption[]
  default_video_aspect_ratio: string
  video_num_frames: number[]
  video_durations: number[]
  default_video_duration: number
  video_frame_rates: number[]
  default_frame_rate: number
  default_video_width: number
  default_video_height: number
  max_upload_size_mb: number
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
  created_at?: string | null
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
  source?: 'chat' | 'canvas' | null
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
  /** 邮箱（可选） */
  email?: string | null
  /** 密码（6-64 字符） */
  password: string
}

/** 登录请求体 — 对齐 LoginRequest */
export interface AuthLoginRequest {
  username: string
  password: string
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
  email?: string | null
  credits: number
  role: string
  is_active: boolean
  is_admin: boolean
  created_at?: string | null
  last_login_at?: string | null
}

// =====================================================
// 管理员：用户与角色管理
// =====================================================

/** 管理员看到的用户行 — 对齐 UserAdminRow */
export interface UserAdminRow {
  id: number
  username: string
  email?: string | null
  credits: number
  role: string
  is_active: boolean
  is_admin: boolean
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
