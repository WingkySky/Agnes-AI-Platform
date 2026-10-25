/* =====================================================
 * 聊天相关 API 封装
 * - 会话管理（创建/列表/删除/详情）
 * - 消息历史查询
 * - 媒体生成状态查询
 * （LLM 流式调用统一走 lib/storyboard/transport 的 /api/chat/completions 透传）
 * ===================================================== */

import client from './client'
import type {
  ChatSession,
  ChatSessionListResponse,
  ChatMessageListResponse,
  MediaCallbackRequest,
  MediaStatusResponse,
  AgentSessionSyncPayload
} from '@/types'

// =====================================================
// 辅助：为原生 fetch 读取 JWT Authorization 头
// =====================================================
/**
 * 为原生 fetch 读取 JWT Authorization 头（供 fetch 直调场景复用：
 * Agent provider、LLM 透传通道等，axios client 走拦截器无需此函数）
 */
export async function getAuthHeaders(): Promise<Record<string, string>> {
  try {
    // 优先从 localStorage 读取（与 client.ts 拦截器一致）
    const token = localStorage.getItem('agnes.platform.auth.token')
    if (token) {
      return { Authorization: `Bearer ${token}` }
    }
  } catch (_) { /* ignore */ }
  return {}
}

// =====================================================
// 会话管理
// =====================================================

/**
 * 创建新聊天会话（workspace_id 可选：画布面板创建时标记上下文）
 */
export function createChatSession(params: { title?: string; workspace_id?: string } = {}): Promise<ChatSession> {
  return client.post('/api/chat/sessions', params)
}

/**
 * 获取会话列表
 */
export function getChatSessions(
  { page = 1, page_size = 20 }: { page?: number; page_size?: number } = {}
): Promise<ChatSessionListResponse> {
  return client.get('/api/chat/sessions', { params: { page, page_size } })
}

// =====================================================
// 画布 Agent 会话同步（type=canvas，前端内核驱动）
// =====================================================

/** 创建画布会话（返回含 backend id 的会话 dict） */
export function createAgentSession(params: { title?: string; workspace_id?: string } = {}): Promise<ChatSession> {
  return client.post('/api/chat/agent-sessions', params)
}

/** 全量同步画布会话（context + 消息行整体替换，幂等） */
export function syncAgentSession(sessionId: number, payload: AgentSessionSyncPayload): Promise<ChatSession> {
  return client.put(`/api/chat/agent-sessions/${sessionId}`, payload)
}

/** 读取画布会话（context + 消息，恢复单请求） */
export function getAgentSession(sessionId: number): Promise<ChatSession & { context?: unknown }> {
  return client.get(`/api/chat/agent-sessions/${sessionId}`)
}

/**
 * 获取会话详情（含消息）
 */
export function getChatSession(sessionId: number): Promise<ChatSession> {
  return client.get(`/api/chat/sessions/${sessionId}`)
}

/**
 * 删除会话
 */
export function deleteChatSession(sessionId: number): Promise<null> {
  return client.delete(`/api/chat/sessions/${sessionId}`)
}

/**
 * 修改会话标题
 */
export function updateChatSession(sessionId: number, title: string): Promise<ChatSession> {
  return client.put(`/api/chat/sessions/${sessionId}`, { title })
}

/**
 * 使用 AI 自动总结会话主题（生成新标题）
 */
export function summarizeChatSession(sessionId: number): Promise<{ title: string }> {
  return client.post(`/api/chat/sessions/${sessionId}/summarize`)
}

// =====================================================
// 消息
// =====================================================

/**
 * 获取会话消息列表
 */
export function getChatMessages(sessionId: number): Promise<ChatMessageListResponse> {
  return client.get(`/api/chat/sessions/${sessionId}/messages`)
}

// =====================================================
// 媒体生成状态 & 回调
// =====================================================

/**
 * 查询媒体生成状态（图片/视频）
 */
export function getMediaStatus(taskId: string): Promise<MediaStatusResponse> {
  return client.get(`/api/chat/media-status/${taskId}`, { silent: true })
}

/**
 * 媒体生成完成回调 — 前端轮询到结果后调用此接口更新数据库中的 media_items
 */
export function mediaCallback(
  { message_id, task_id, media_url, status = 'success' }: MediaCallbackRequest & { status?: string }
): Promise<null> {
  return client.post('/api/chat/media-callback',
    { message_id, task_id, media_url, status },
    { silent: true }  // 静默模式：即使后端返回错误也不弹窗（由上层处理）
  )
}
