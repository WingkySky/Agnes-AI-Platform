/* =====================================================
 * Agent 消息投影（宿主统一后剩余职责：内核消息 → chat_messages 行载荷）
 *
 * - 原画布 Agent 会话持久化（localforage scope + canvas 会话同步）已随宿主统一退役；
 *   统一宿主（stores/chat.ts）走 chat_sessions 全量同步链路（session_type='chat'，
 *   workspace_id 列保留作画布上下文标记）
 * - ProjectableMessage 结构兼容画布 AgentMessage 与对话页内核投影消息，避免循环依赖
 * ===================================================== */

import type { AgentSessionSyncPayload } from '@/types'

/** 消息投影入参（结构兼容画布 AgentMessage 与对话页内核投影消息，避免循环依赖） */
export interface ProjectableMessage {
  role: 'user' | 'assistant'
  content: string
  images?: Array<{ data: string; mimeType: string }>
  steps: Array<{ callId: string; tool: string; args?: Record<string, unknown>; status: string; result?: string | null }>
  createdAt?: string
  /** 生成产物（对话页内核投影；写消息行 media_items 列） */
  media?: Array<{ type: string; url: string; task_id?: string; status: string }>
  /** 用户输入的 URL 附件（对话页：图片/视频/文档链接，并入 attachments 行） */
  urlAttachments?: Array<{ name: string; url: string; mime_type?: string }>
}

/** 消息投影：内核消息 → chat_messages 行（展示/总结用，不参与恢复） */
export function toBackendMessages(messages: ProjectableMessage[]): AgentSessionSyncPayload['messages'] {
  const out: AgentSessionSyncPayload['messages'] = []
  for (const m of messages) {
    const attachments = [
      ...(m.images ?? []).map((img) => ({
        name: 'image',
        base64_image: `data:${img.mimeType};base64,${img.data}`,
        mime_type: img.mimeType,
        size: 0,
      })),
      ...(m.urlAttachments ?? []).map((att) => ({
        name: att.name,
        url: att.url,
        mime_type: att.mime_type || 'application/url',
        size: 0,
      })),
    ]
    out.push({
      role: m.role,
      content: m.content ?? '',
      attachments: attachments.length ? attachments : undefined,
      steps: m.steps.length
        ? m.steps.map((s) => ({ callId: s.callId, tool: s.tool, args: s.args, status: s.status, result: s.result }))
        : undefined,
      media_items: m.media?.length
        ? m.media.map((item) => ({ type: item.type, url: item.url, task_id: item.task_id, status: item.status }))
        : undefined,
    })
  }
  return out
}
