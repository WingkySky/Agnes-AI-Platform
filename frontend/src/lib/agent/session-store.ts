/* =====================================================
 * 画布 Agent 会话持久化（二期：数据库为准 + localforage 兜底）
 *
 * - meta 列表：后端 GET /chat/sessions 过滤 session_type=canvas + workspace；
 *   activeId 属纯 UI 状态，存 localforage meta key（同时作会话列表缓存）
 * - 数据：PUT /chat/agent-sessions/{id} 全量同步（context=内核序列化 + 消息行投影）；
 *   失败静默降级写 localforage，成功回写缓存；恢复后端优先、失败读缓存
 * - 会话 id：本地 uid 为主键；后端恢复的会话 id = `b{backendId}`（跨设备稳定）；
 *   AgentSessionMeta.backendId 为 null 表示尚未同步成功过
 * - 存储接口可注入（vitest 用内存实现）
 * ===================================================== */

import {
  createAgentSession, syncAgentSession, getAgentSession,
  getChatSessions, deleteChatSession, updateChatSession,
} from '@/api/chat'
import type { AgentSessionSyncPayload } from '@/types'

export interface AgentSessionMeta {
  /** 会话主键：本地 uid 或 `b{backendId}`（后端恢复） */
  id: string
  /** 后端 chat_sessions.id；null = 尚未同步成功 */
  backendId: number | null
  title: string
  createdAt: string
  updatedAt: string
}

export interface AgentSessionsMeta {
  activeId: string | null
  sessions: AgentSessionMeta[]
}

/** 画布会话全量同步所需的载荷（context 由内核 serializeState 提供） */
export interface AgentSessionSyncInput {
  title: string
  workspaceId: string
  context: unknown
  messages: AgentSessionSyncPayload['messages']
}

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

export interface AgentKVStorage {
  getItem(key: string): Promise<unknown>
  setItem(key: string, value: unknown): Promise<unknown>
  removeItem(key: string): Promise<unknown>
}

let storage: AgentKVStorage | null = null

/** 测试注入内存存储；传 null 恢复默认 localforage */
export function setAgentSessionStorage(s: AgentKVStorage | null): void {
  storage = s
}

async function getStorage(): Promise<AgentKVStorage> {
  if (!storage) {
    const localforage = await import('localforage')
    storage = localforage.default.createInstance({ name: 'agnes_agent' })
  }
  return storage
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

export function sessionsMetaKey(scope: string): string {
  return `agent_sessions_${scope}`
}

export function sessionDataKey(scope: string, sessionId: string): string {
  return `agent_session_data_${scope}_${sessionId}`
}

/** 首条用户消息 → 会话标题（截断 20 字，压缩空白） */
export function deriveSessionTitle(text: string): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.length > 20 ? `${flat.slice(0, 20)}…` : flat
}

// =====================================================
// 消息投影：AgentMessage → chat_messages 行（展示/总结用，不参与恢复）
// =====================================================

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

// =====================================================
// meta 读取：后端为准 + 本地缓存合并/兜底
// =====================================================

function toMeta(v: unknown): AgentSessionMeta | null {
  if (!isRecord(v)) return null
  const id = typeof v.id === 'string' ? v.id : ''
  if (!id) return null
  const backendId = typeof v.backendId === 'number' ? v.backendId : null
  return {
    id,
    backendId,
    title: typeof v.title === 'string' ? v.title : '',
    createdAt: typeof v.createdAt === 'string' ? v.createdAt : new Date().toISOString(),
    updatedAt: typeof v.updatedAt === 'string' ? v.updatedAt : new Date().toISOString(),
  }
}

/** 本地缓存 meta（activeId + 会话列表缓存 + 离线新建的未同步会话） */
async function readLocalMeta(scope: string): Promise<AgentSessionsMeta> {
  try {
    const raw = await (await getStorage()).getItem(sessionsMetaKey(scope))
    if (!isRecord(raw) || !Array.isArray(raw.sessions)) return { activeId: null, sessions: [] }
    const sessions = raw.sessions.map(toMeta).filter((s): s is AgentSessionMeta => s !== null)
    const activeId = typeof raw.activeId === 'string' ? raw.activeId : null
    return { activeId, sessions }
  } catch {
    return { activeId: null, sessions: [] }
  }
}

/** meta 列表：后端 canvas 会话（按工作区过滤）+ 本地未同步会话合并；后端失败整体走本地缓存 */
export async function listSessionsMeta(scope: string, workspaceId: string): Promise<AgentSessionsMeta> {
  const local = await readLocalMeta(scope)
  try {
    const data = await getChatSessions({ page: 1, page_size: 100 })
    const backendSessions: AgentSessionMeta[] = (data.items || [])
      .filter((s) => s.session_type === 'canvas' && (s.workspace_id ?? '') === workspaceId)
      .map((s) => ({
        id: `b${s.id}`,
        backendId: s.id,
        title: s.title || '',
        createdAt: s.created_at,
        updatedAt: s.updated_at || s.created_at,
      }))
    // 本地从未同步成功的会话保留（离线新建场景），已同步的不与后端重复
    const unsynced = local.sessions.filter((s) => s.backendId === null)
    const sessions = [...unsynced, ...backendSessions]
    const activeId = local.activeId && sessions.some((s) => s.id === local.activeId)
      ? local.activeId
      : sessions[0]?.id ?? null
    return { activeId, sessions }
  } catch {
    // 后端不可用：本地缓存兜底（含未同步会话）
    const activeId = local.activeId && local.sessions.some((s) => s.id === local.activeId)
      ? local.activeId
      : local.sessions[0]?.id ?? null
    return { activeId, sessions: local.sessions }
  }
}

/** meta 写入本地缓存（activeId + 离线未同步会话载体；后端列表每次拉取不落盘） */
export async function saveSessionsMeta(scope: string, meta: AgentSessionsMeta): Promise<void> {
  await (await getStorage()).setItem(sessionsMetaKey(scope), meta)
}

// =====================================================
// 数据同步：PUT 全量覆盖（成功回写缓存；失败/未同步写缓存兜底）
// =====================================================

export async function syncSession(
  scope: string,
  sessionId: string,
  input: AgentSessionSyncInput,
  backendId: number | null,
): Promise<{ backendId: number | null; ok: boolean }> {
  const storageRef = await getStorage()
  // 无论后端成败都写本地缓存（兜底恢复用，存内核 context 原样）
  try {
    await storageRef.setItem(sessionDataKey(scope, sessionId), input.context)
  } catch {
    // 缓存失败不阻断
  }
  let id = backendId
  try {
    if (!id) {
      const created = await createAgentSession({ title: input.title, workspace_id: input.workspaceId })
      id = created.id
    }
    await syncAgentSession(id, {
      title: input.title,
      workspace_id: input.workspaceId,
      context: input.context,
      messages: input.messages,
    })
    return { backendId: id, ok: true }
  } catch {
    // 后端不可达：缓存已写，下次同步重试（未创建成功则 backendId 仍 null）
    return { backendId, ok: false }
  }
}

/** 恢复：后端 context 优先，失败读本地缓存（返回内核可 restore 的 {messages} 形状或 null） */
export async function pullSession(scope: string, sessionId: string, backendId: number | null): Promise<unknown | null> {
  if (backendId !== null) {
    try {
      const data = await getAgentSession(backendId)
      if (data.context && isRecord(data.context)) return data.context
    } catch {
      // 后端失败 → 本地缓存兜底
    }
  }
  try {
    return await (await getStorage()).getItem(sessionDataKey(scope, sessionId))
  } catch {
    return null
  }
}

/** 删除后端会话（静默；本地清理由调用方负责） */
export async function deleteBackendSession(backendId: number): Promise<void> {
  try {
    await deleteChatSession(backendId)
  } catch {
    // 删除失败不阻断本地收敛
  }
}

/** 清理本地缓存数据（删除会话时；meta 缓存由调用方 _saveMeta 收敛） */
export async function clearSessionCache(scope: string, sessionId: string): Promise<void> {
  await (await getStorage()).removeItem(sessionDataKey(scope, sessionId))
}

/** 重命名后端会话（静默） */
export async function renameBackendSession(backendId: number, title: string): Promise<void> {
  try {
    await updateChatSession(backendId, title)
  } catch {
    // 失败不影响本地 meta
  }
}
