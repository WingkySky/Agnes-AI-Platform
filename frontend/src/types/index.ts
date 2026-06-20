/* =====================================================
 * 前后端共享类型定义 — 对齐后端 Pydantic Schema
 *
 * 命名规则：前端 Request/Response 类型与后端 Schema 一一对应
 * ===================================================== */

// =====================================================
// 通用类型
// =====================================================

/** 健康检查响应 — 对齐 HealthResponse */
export interface HealthResponse {
  status: string
  service: string
}

/** 前端可用配置 — 对齐 ConfigResponse */
export interface ConfigResponse {
  image_sizes: string[]
  image_models: string[]
  video_models: string[]
  video_num_frames: number[]
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
