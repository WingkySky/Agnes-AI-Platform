/* =====================================================
 * Chat Store（Pinia）— 三期内核统一后的对话页状态
 *
 * 引擎：前端 Agent 内核（AgentKernel + CHAT_TOOLS），后端只做 BFF 透传/落库/任务；
 * 与画布 Agent 同款机制：内核事件 → 消息/步骤投影、serialize/restore 切会话、
 * PUT agent-sessions 全量同步（session_type='chat'，数据库为准）。
 * 保留既有机制：媒体任务轮询（GET media-status）、taskQueue 集成、
 * 会话 CRUD/标题总结（读消息行）、localStorage 只存 activeSessionId。
 * ===================================================== */

import { defineStore } from 'pinia'
import {
  createChatSession,
  getChatSessions,
  deleteChatSession,
  updateChatSession,
  summarizeChatSession,
  getChatMessages,
  getMediaStatus,
  getAgentSession,
  syncAgentSession,
  getAuthHeaders,
} from '@/api/chat'
import { useTaskQueueStore } from '@/stores/taskQueue'
import { isMediaSuccess, isMediaFailed } from '@/lib/media-status'
import { t } from '@/i18n'
import { AgentKernel } from '@/lib/agent/kernel'
import type { KernelEvent, AgentImageAttachment } from '@/lib/agent/kernel'
import { createAgentModel } from '@/lib/agent/provider'
import { CHAT_TOOLS } from '@/lib/agent/chat-tools'
import { CHAT_SYSTEM_PROMPT_BASE, buildChatSystemPrompt } from '@/lib/agent/chat-system-prompt'
import { listAgentSkills } from '@/lib/agent/skills'
import { toBackendMessages } from '@/lib/agent/session-store'
import type {
  ProjectableMessage,
} from '@/lib/agent/session-store'
import type {
  ChatBubbleItem,
  ChatStepView,
} from '@/components/chat/types'
import type {
  ChatSession,
  ChatMessage,
  MediaItem,
  MessageAttachment,
  MediaStatusResponse,
  AgentStepRecord,
} from '@/types'

/** 内核投影消息（对话页时间线；落库/渲染共用） */
export interface ChatKernelMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  /** 用户输入附图（裸 base64，模型可见 + 落库 attachments） */
  images?: AgentImageAttachment[]
  /** 用户输入 URL 附件（图片/视频/文档链接，渲染卡片 + 落库） */
  urlAttachments?: MessageAttachment[]
  /** 生成产物（占位→轮询回填→随全量同步落库） */
  media: MediaItem[]
  steps: AgentStepRecord[]
  createdAt: string
}

// 媒体轮询间隔
const MEDIA_POLL_INTERVAL = 3000
// 轮询最大连续失败次数（超过后停止轮询）
const MAX_POLL_FAIL_COUNT = 5
// localStorage 持久化 key
const STORAGE_KEY = 'agnes_chat_state_v1'

function uid(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
}

/** 对话模型选择记忆（与画布 Agent 共用一键：两宿主偏好一致；空 = 后端默认解析链） */
function readChatModel(): string {
  try {
    return localStorage.getItem('agnes_agent_chat_model') ?? ''
  } catch {
    return ''
  }
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

// =====================================================
// 视图映射：内核投影 → 共享气泡视图（纯函数）
// =====================================================

function imageDataUrl(img: { data: string; mimeType: string }): string {
  return `data:${img.mimeType};base64,${img.data}`
}

function toolLabel(tool: string): string {
  if (tool === 'generate_image') return t('chat.toolGenerateImage')
  if (tool === 'generate_video') return t('chat.toolGenerateVideo')
  if (tool === 'agent_load_skill') return t('chat.toolLoadSkill')
  return tool
}

function toStepView(s: AgentStepRecord): ChatStepView {
  return { callId: s.callId, label: toolLabel(s.tool), tooltip: s.tool, status: toStepStatus(s.status) }
}

function toStepStatus(status: string): ChatStepView['status'] {
  switch (status) {
    case 'running':
    case 'pending':
      return 'running'
    case 'done':
      return 'done'
    case 'error':
      return 'error'
    case 'rejected':
      return 'rejected'
    default:
      return 'pending'
  }
}

function attachmentKind(att: MessageAttachment): 'image' | 'video' | 'document' {
  if (!att) return 'image'
  if (att._link_type === 'video' || att.video_url) return 'video'
  if (att._link_type === 'document' || att.doc_url) return 'document'
  return 'image'
}

function attachmentUrl(att: MessageAttachment): string {
  if (!att) return ''
  if (att.video_url) return att.video_url
  if (att.doc_url) return att.doc_url
  if (att.image_url) return att.image_url
  return att.url || att.base64 || att.base64_image || ''
}

/** 消息行/投影 → 气泡视图列表（流式光标由 getter 依据 busy 标注） */
export function toChatBubbleItems(messages: ChatKernelMessage[], streaming: boolean): ChatBubbleItem[] {
  return messages.map((m, idx) => {
    const isLast = idx === messages.length - 1
    return {
      id: m.id,
      role: m.role,
      content: m.content,
      streaming: streaming && isLast && m.role === 'assistant',
      images: m.images?.length ? m.images.map((i) => ({ src: imageDataUrl(i) })) : undefined,
      attachments: m.urlAttachments?.length
        ? m.urlAttachments
            .filter((a) => a && (a.url || a.base64 || a.base64_image))
            .map((a) => ({
              kind: attachmentKind(a),
              name: a.name || 'link',
              url: attachmentUrl(a),
            }))
        : undefined,
      media: m.media.length
        ? m.media.map((item) => ({ type: item.type, url: item.url || '', taskId: item.task_id, status: item.status }))
        : undefined,
      steps: m.steps.length ? m.steps.map(toStepView) : undefined,
      createdAt: m.createdAt,
    }
  })
}

/** 消息行 → 内核投影（存量会话恢复；媒体随行回填，上下文另行重建） */
function messagesFromRows(rows: ChatMessage[]): ChatKernelMessage[] {
  const out: ChatKernelMessage[] = []
  for (const r of rows) {
    if (r.role !== 'user' && r.role !== 'assistant') continue
    const images: AgentImageAttachment[] = []
    const urlAttachments: MessageAttachment[] = []
    for (const att of r.attachments ?? []) {
      if (!att) continue
      const b64 = typeof att.base64_image === 'string' ? att.base64_image : att.base64
      if (typeof b64 === 'string' && b64.startsWith('data:')) {
        const mime = b64.slice(5, b64.indexOf(';'))
        images.push({ data: b64.slice(b64.indexOf(',') + 1), mimeType: mime || 'image/png' })
      } else {
        urlAttachments.push(att)
      }
    }
    out.push({
      id: uid(),
      role: r.role,
      content: r.content || '',
      images: images.length ? images : undefined,
      urlAttachments: urlAttachments.length ? urlAttachments : undefined,
      media: (r.media_items ?? []).filter((m) => m && typeof m.type === 'string'),
      steps: (r.steps ?? []).filter((s): s is AgentStepRecord => isRecord(s) && typeof s.callId === 'string'),
      createdAt: r.created_at,
    })
  }
  return out
}

/** 存量会话上下文重建：消息行 → 内核消息数组（文本 + 用户附图块） */
export function chatContextFromRows(rows: ChatMessage[]): unknown {
  const msgs: Array<Record<string, unknown>> = []
  for (const r of rows) {
    if (r.role !== 'user' && r.role !== 'assistant') continue
    if (r.role === 'user') {
      const content: Array<Record<string, unknown>> = []
      if (r.content) content.push({ type: 'text', text: r.content })
      for (const att of r.attachments ?? []) {
        const b64 = typeof att?.base64_image === 'string' ? att.base64_image : att?.base64
        if (typeof b64 === 'string' && b64.startsWith('data:')) {
          const mime = b64.slice(5, b64.indexOf(';'))
          content.push({ type: 'image', data: b64.slice(b64.indexOf(',') + 1), mimeType: mime || 'image/png' })
        }
      }
      msgs.push({ role: 'user', content: content.length ? content : '', timestamp: Date.now() })
    } else {
      msgs.push({ role: 'assistant', content: r.content || '', timestamp: Date.now() })
    }
  }
  return { messages: msgs }
}

// 内核单例：跨会话复用，切换 = serialize/restore（与画布同模式）
let kernel: AgentKernel | null = null
let boundStore: { _onKernelEvent: (e: KernelEvent) => void } | null = null

export const useChatStore = defineStore('chat', {
  state: (): {
    sessions: ChatSession[]
    sessionsTotal: number
    activeSessionId: number | null
    messages: ChatKernelMessage[]
    busy: boolean
    thinking: boolean
    error: string | null
    loadingMessages: boolean
    /** 对话模型 id（空 = 后端默认解析链；输入条模型胶囊可见可切换） */
    chatModelId: string
    // 媒体任务轮询（taskId -> timer）
    mediaPollTimers: Record<string, ReturnType<typeof setInterval>>
    mediaPollFailCounts: Record<string, number>
    // taskId -> 本地消息 id（轮询回填定位）
    mediaTaskToMessageId: Record<string, string>
    // 是否已完成初始化（配合 keep-alive）
    _initialized: boolean
    // 技能清单是否已快照进系统提示
    _skillsApplied: boolean
  } => ({
    sessions: [],
    sessionsTotal: 0,
    activeSessionId: null,
    messages: [],
    busy: false,
    thinking: false,
    error: null,
    loadingMessages: false,
    chatModelId: readChatModel(),
    mediaPollTimers: {},
    mediaPollFailCounts: {},
    mediaTaskToMessageId: {},
    _initialized: false,
    _skillsApplied: false,
  }),

  getters: {
    activeSession(state): ChatSession | null {
      return state.sessions.find(s => s.id === state.activeSessionId) || null
    },
    hasActiveSession(state): boolean {
      return state.activeSessionId !== null
    },
    messageItems(state): ChatBubbleItem[] {
      return toChatBubbleItems(state.messages, state.busy)
    },
  },

  actions: {
    // =====================================================
    // 内核装配
    // =====================================================

    _ensureKernel(): AgentKernel {
      boundStore = this
      if (kernel) return kernel
      kernel = new AgentKernel({
        systemPrompt: CHAT_SYSTEM_PROMPT_BASE,
        getAuthToken: async () => {
          const headers = await getAuthHeaders()
          const auth = headers.Authorization
          return typeof auth === 'string' && auth.startsWith('Bearer ') ? auth.slice(7) : null
        },
        tools: CHAT_TOOLS,
        toolContext: {
          getRecentMediaUrl: (type: 'image' | 'video') => this.recentMediaUrl(type),
        },
      })
      // 恢复用户选定的对话模型（与画布共用同一偏好）
      if (this.chatModelId) kernel.setModel(createAgentModel(this.chatModelId))
      kernel.subscribe((e) => boundStore?._onKernelEvent(e))
      return kernel
    },

    /** 切换对话模型：记忆选择并热更新内核模型（下一回合生效；空串 = 回默认解析链） */
    setChatModel(id: string): void {
      this.chatModelId = id
      try {
        if (id) localStorage.setItem('agnes_agent_chat_model', id)
        else localStorage.removeItem('agnes_agent_chat_model')
      } catch {
        // 记忆失败不影响切换
      }
      this._ensureKernel().setModel(createAgentModel(id))
    },

    /** 技能清单快照进系统提示（一次；失败降级基础提示） */
    async _applySkillsPrompt(): Promise<void> {
      if (this._skillsApplied) return
      this._skillsApplied = true
      try {
        const skills = await listAgentSkills()
        kernel?.setSystemPrompt(buildChatSystemPrompt(skills))
      } catch {
        // 技能库不可用沿用基础提示
      }
    },

    /** 最近一次成功生成的媒体 URL（会话连续性：图生图/图生视频默认参考） */
    recentMediaUrl(type: 'image' | 'video'): string | null {
      for (let i = this.messages.length - 1; i >= 0; i--) {
        const m = this.messages[i]
        for (let j = m.media.length - 1; j >= 0; j--) {
          const item = m.media[j]
          if (item.type === type && item.status === 'success' && item.url) return item.url
        }
      }
      return null
    },

    _onKernelEvent(e: KernelEvent): void {
      switch (e.type) {
        case 'thinking': {
          this.thinking = e.active
          break
        }
        case 'round_start': {
          this.thinking = true
          this.messages.push({ id: uid(), role: 'assistant', content: '', media: [], steps: [], createdAt: new Date().toISOString() })
          break
        }
        case 'text_delta': {
          this.thinking = false
          const msg = this._lastAssistant() ?? this.messages[this.messages.push({ id: uid(), role: 'assistant', content: '', media: [], steps: [], createdAt: new Date().toISOString() }) - 1]
          msg.content += e.delta
          break
        }
        case 'tool_start': {
          this.thinking = false
          const msg = this._lastAssistant() ?? this.messages[this.messages.push({ id: uid(), role: 'assistant', content: '', media: [], steps: [], createdAt: new Date().toISOString() }) - 1]
          msg.steps.push({ callId: e.callId, tool: e.tool, args: e.args, status: 'running', result: null })
          break
        }
        case 'tool_end': {
          const step = this._findStep(e.callId)
          if (step && step.status !== 'rejected') {
            step.status = e.ok ? 'done' : 'error'
            step.result = e.result
          }
          // 生成工具：结果含 task_id → 挂媒体占位并启动轮询（占位/回填机制沿用）
          if (e.ok && (e.tool === 'generate_image' || e.tool === 'generate_video')) {
            this._attachPendingMedia(e.tool, e.callId, e.result)
          }
          break
        }
        case 'tool_rejected': {
          // chat 宿主无阶段门；占位处理保持与 agent store 同构
          const msg = this._lastAssistant() ?? this.messages[this.messages.push({ id: uid(), role: 'assistant', content: '', media: [], steps: [], createdAt: new Date().toISOString() }) - 1]
          if (!msg.steps.some((s) => s.callId === e.callId)) {
            msg.steps.push({ callId: e.callId, tool: e.tool, args: {}, status: 'rejected', result: e.reason })
          }
          break
        }
        case 'confirm_request': {
          // chat 宿主无阶段门，不应出现；忽略
          break
        }
        case 'done': {
          this.busy = false
          this.thinking = false
          if (e.error) this.error = e.error
          const last = this._lastAssistant()
          if (last && !last.content && last.steps.length === 0 && last.media.length === 0) this.messages.pop()
          void this._persist()
          // 自动总结标题：首轮回复后标题仍为默认时调一次（读已落库消息行）
          if (!e.error && this.activeSessionId) {
            const session = this.sessions.find((s) => s.id === this.activeSessionId)
            if (session && !session.title) void this.autoSummarizeSession(this.activeSessionId).catch(() => {})
          }
          break
        }
      }
    },

    _lastAssistant(): ChatKernelMessage | null {
      const last = this.messages[this.messages.length - 1]
      return last && last.role === 'assistant' ? last : null
    },

    _findStep(callId: string): AgentStepRecord | null {
      for (let i = this.messages.length - 1; i >= 0; i--) {
        const msg = this.messages[i]
        const step = msg.steps.find((s) => s.callId === callId)
        if (step) return step
        if (msg.role === 'user') break
      }
      return null
    },

    /** 生成工具完成 → 当前 assistant 消息挂 pending 媒体占位 + 启动轮询 */
    _attachPendingMedia(tool: string, callId: string, resultJson: string): void {
      try {
        const parsed: unknown = JSON.parse(resultJson)
        if (!isRecord(parsed) || typeof parsed.task_id !== 'string') return
        const taskId = parsed.task_id
        const type: MediaItem['type'] = tool === 'generate_video' ? 'video' : 'image'
        const msg = this.messages.find((m) => m.steps.some((s) => s.callId === callId))
        if (!msg) return
        if (msg.media.some((m) => m.task_id === taskId)) return
        msg.media.push({ type, url: '', task_id: taskId, status: 'pending' })
        this.mediaTaskToMessageId[taskId] = msg.id
        this._startMediaPoll(taskId)
      } catch {
        // 结果非 JSON（异常信息）忽略
      }
    },

    // =====================================================
    // 发送
    // =====================================================

    /** 发送用户消息（attachments：粘贴/上传/URL 识别的附件） */
    async send(text: string, attachments: MessageAttachment[] = []): Promise<void> {
      const trimmed = text.trim()
      if (this.busy || (!trimmed && attachments.length === 0)) return
      if (!this.activeSessionId) {
        await this.newSession()
      }
      this.busy = true
      this.thinking = true
      this.error = null
      // 附件分流：base64 图片进内核（模型可见），URL/文档类渲染卡片并随行落库
      const images: AgentImageAttachment[] = []
      const urlAttachments: MessageAttachment[] = []
      for (const att of attachments) {
        const b64 = typeof att.base64_image === 'string' ? att.base64_image : att.base64
        if (typeof b64 === 'string' && b64.startsWith('data:')) {
          const mime = att.mime_type || b64.slice(5, b64.indexOf(';'))
          images.push({ data: b64.slice(b64.indexOf(',') + 1), mimeType: mime || 'image/png' })
        } else if (att.url) {
          urlAttachments.push(att)
        }
      }
      this.messages.push({
        id: uid(),
        role: 'user',
        content: trimmed,
        images: images.length ? images : undefined,
        urlAttachments: urlAttachments.length ? urlAttachments : undefined,
        media: [],
        steps: [],
        createdAt: new Date().toISOString(),
      })
      try {
        await this._applySkillsPrompt()
        await this._persist()
        await this._ensureKernel().send(trimmed, images)
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      } finally {
        this.busy = false
        await this._persist()
      }
    },

    /** 用户请求停止 */
    requestStop(): void {
      this._ensureKernel().requestStop()
    },

    // =====================================================
    // 会话管理（CRUD 沿用现有端点；消息存储走全量同步）
    // =====================================================

    async loadSessions(): Promise<void> {
      try {
        const data: { items?: ChatSession[]; total?: number } = await getChatSessions({ page: 1, page_size: 50 })
        this.sessions = data.items || []
        this.sessionsTotal = data.total || 0
      } catch (e: unknown) {
        console.error('[Chat] 加载会话列表失败:', e)
      }
    },

    async newSession(title?: string): Promise<ChatSession> {
      try {
        const session = await createChatSession({ title }) as ChatSession
        this.sessions.unshift(session)
        this.activeSessionId = session.id
        this.messages = []
        this.error = null
        this._saveToStorage()
        return session
      } catch (e: unknown) {
        console.error('[Chat] 创建会话失败:', e)
        throw e
      }
    },

    async switchSession(sessionId: number): Promise<void> {
      if (sessionId === this.activeSessionId) return
      // 切换前：停当前轮（内核 abort）与媒体轮询；已生成内容随 _persist 落库
      this.requestStop()
      this.stopAllMediaPolls()
      this.activeSessionId = sessionId
      await this._loadSession(sessionId)
      this._saveToStorage()
    },

    async removeSession(sessionId: number): Promise<void> {
      try {
        await deleteChatSession(sessionId)
        this.sessions = this.sessions.filter(s => s.id !== sessionId)
        if (this.activeSessionId === sessionId) {
          this.activeSessionId = null
          this.messages = []
          this.error = null
        }
        this._saveToStorage()
      } catch (e: unknown) {
        console.error('[Chat] 删除会话失败:', e)
        throw e
      }
    },

    async updateSessionTitle(sessionId: number, newTitle: string): Promise<ChatSession> {
      try {
        const updated = await updateChatSession(sessionId, newTitle) as ChatSession
        const session = this.sessions.find(s => s.id === sessionId)
        if (session) {
          session.title = updated.title
          session.updated_at = updated.updated_at
        }
        return updated
      } catch (e: unknown) {
        console.error('[Chat] 修改会话标题失败:', e)
        throw e
      }
    },

    async autoSummarizeSession(sessionId: number): Promise<ChatSession> {
      try {
        const updated = await summarizeChatSession(sessionId) as unknown as ChatSession
        const session = this.sessions.find(s => s.id === sessionId)
        if (session) {
          session.title = updated.title
          session.updated_at = updated.updated_at
        }
        return updated
      } catch (e: unknown) {
        console.error('[Chat] 自动总结会话失败:', e)
        throw e
      }
    },

    /** 载入会话：context（内核上下文）优先，空则从消息行重建；投影消息 + 恢复在途媒体轮询 */
    async _loadSession(sessionId: number): Promise<void> {
      this.messages = []
      this.error = null
      this.loadingMessages = true
      try {
        const [rowsResp, detail] = await Promise.all([
          getChatMessages(sessionId),
          getAgentSession(sessionId).catch(() => null),
        ])
        const rows: ChatMessage[] = rowsResp.items || []
        const context = detail?.context
        const k = this._ensureKernel()
        const restored = k.restore(isRecord(context) ? context : chatContextFromRows(rows))
        this.messages = messagesFromRows(rows)
        if (!restored) k.reset()
        // 在途媒体任务继续轮询
        for (const m of this.messages) {
          for (const item of m.media) {
            if (item.task_id && (item.status === 'pending' || item.status === 'processing')) {
              this.mediaTaskToMessageId[item.task_id] = m.id
              this._startMediaPoll(item.task_id)
            }
          }
        }
      } catch (e: unknown) {
        const errMsg = e instanceof Error ? e.message : String(e)
        if (errMsg.includes('会话不存在') || errMsg.includes('not found') || errMsg.includes('404')) {
          this.activeSessionId = null
          this.messages = []
          this._saveToStorage()
        } else {
          console.error('[Chat] 加载消息失败:', e)
        }
      } finally {
        this.loadingMessages = false
      }
    },

    // =====================================================
    // 媒体任务轮询（回填本地投影；终端态随全量同步落库）
    // =====================================================

    _startMediaPoll(taskId: string): void {
      if (this.mediaPollTimers[taskId]) return
      this.mediaPollFailCounts[taskId] = 0
      const poll = async (): Promise<void> => {
        try {
          const data: MediaStatusResponse = await getMediaStatus(taskId)
          this.mediaPollFailCounts[taskId] = 0
          const msg = this.messages.find((m) => m.media.some((i) => i.task_id === taskId))
          const item = msg?.media.find((i) => i.task_id === taskId)
          if (!item) {
            this._stopMediaPoll(taskId)
            return
          }
          const rawStatus = String(data.status || '').toLowerCase()
          if (isMediaSuccess(rawStatus)) {
            item.status = 'success'
            item.url = data.result_url || data.video_url || data.url || data.image_url || ''
            this._stopMediaPoll(taskId)
            this._updateTaskQueueItem(taskId, 'success', item.url)
            // 终端态落库（全量同步消息行）
            void this._persist()
          } else if (isMediaFailed(rawStatus)) {
            item.status = 'failed'
            this._stopMediaPoll(taskId)
            this._updateTaskQueueItem(taskId, 'failed', '')
            void this._persist()
          } else if (rawStatus === 'unknown') {
            console.warn('[Chat] 任务不存在或已过期，停止轮询: taskId=%s', taskId)
            this._stopMediaPoll(taskId)
            if (item.status !== 'success') item.status = 'failed'
          } else {
            item.status = 'processing'
          }
        } catch (e: unknown) {
          this.mediaPollFailCounts[taskId] = (this.mediaPollFailCounts[taskId] || 0) + 1
          if (this.mediaPollFailCounts[taskId] >= MAX_POLL_FAIL_COUNT) {
            console.warn('[Chat] 媒体轮询连续失败 %d 次，停止轮询: taskId=%s', this.mediaPollFailCounts[taskId], taskId)
            this._stopMediaPoll(taskId)
            const msg = this.messages.find((m) => m.media.some((i) => i.task_id === taskId))
            const item = msg?.media.find((i) => i.task_id === taskId)
            if (item && item.status !== 'success') item.status = 'failed'
          }
        }
      }
      void poll()
      this.mediaPollTimers[taskId] = setInterval(poll, MEDIA_POLL_INTERVAL)
    },

    _stopMediaPoll(taskId: string): void {
      if (this.mediaPollTimers[taskId]) {
        clearInterval(this.mediaPollTimers[taskId])
        delete this.mediaPollTimers[taskId]
      }
    },

    stopAllMediaPolls(): void {
      for (const taskId of Object.keys(this.mediaPollTimers)) {
        this._stopMediaPoll(taskId)
      }
    },

    _updateTaskQueueItem(taskId: string, status: string, resultUrl: string): void {
      try {
        useTaskQueueStore().updateChatTask(taskId, { status: status as 'success' | 'failed', resultUrl })
      } catch {
        // 忽略
      }
    },

    // =====================================================
    // 落库：PUT agent-sessions 全量同步（session_type='chat'）
    // =====================================================

    async _persist(): Promise<void> {
      if (!this.activeSessionId) return
      const projectable: ProjectableMessage[] = this.messages.map((m) => ({
        role: m.role,
        content: m.content,
        images: m.images,
        urlAttachments: m.urlAttachments?.filter((a): a is MessageAttachment & { url: string } => typeof a?.url === 'string'),
        media: m.media,
        steps: m.steps,
        createdAt: m.createdAt,
      }))
      try {
        await syncAgentSession(this.activeSessionId, {
          title: this.activeSession?.title || '新对话',
          workspace_id: null,
          context: this._ensureKernel().serializeState(),
          messages: toBackendMessages(projectable),
        })
      } catch (e: unknown) {
        // 同步失败不阻断对话（后端异常时提示排查，下一轮再试）
        console.warn('[Chat] 会话同步失败:', e instanceof Error ? e.message : e)
      }
    },

    // =====================================================
    // 持久化/初始化
    // =====================================================

    _saveToStorage(): void {
      if (typeof localStorage === 'undefined') return
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ activeSessionId: this.activeSessionId, savedAt: Date.now() }))
      } catch {
        // 忽略
      }
    },

    _restoreFromStorage(): void {
      if (typeof localStorage === 'undefined') return
      try {
        const raw = localStorage.getItem(STORAGE_KEY)
        if (!raw) return
        const data = JSON.parse(raw) as { activeSessionId?: number }
        if (data?.activeSessionId) this.activeSessionId = data.activeSessionId
      } catch {
        // 忽略
      }
    },

    async init(): Promise<void> {
      if (this._initialized) return
      this._initialized = true

      if (typeof window !== 'undefined') {
        window.addEventListener('agnes:user-login', (e: Event) => {
          const ce = e as CustomEvent
          const userId: number | null = (ce?.detail?.id as number) ?? null
          this._switchUserStorage(userId, true)
        })
        window.addEventListener('agnes:user-logout', () => {
          this._switchUserStorage(null, false)
        })
      }

      this._restoreFromStorage()
      await this.loadSessions()

      if (this.activeSessionId) {
        const exists = this.sessions.some(s => s.id === this.activeSessionId)
        if (exists) {
          await this._loadSession(this.activeSessionId)
        } else {
          this.activeSessionId = null
          this.messages = []
          this._saveToStorage()
        }
      }
    },

    async _switchUserStorage(userId: number | null, isLogin: boolean): Promise<void> {
      // 中止当前轮与全部媒体轮询；内核单例重置（不残留上一个用户的上下文）
      try { this.requestStop() } catch { /* 忽略 */ }
      this.stopAllMediaPolls()
      try { kernel?.reset() } catch { /* 忽略 */ }
      this._skillsApplied = false
      this.sessions = []
      this.sessionsTotal = 0
      this.activeSessionId = null
      this.messages = []
      this.busy = false
      this.thinking = false
      this.error = null
      this.mediaTaskToMessageId = {}
      try { localStorage.removeItem(STORAGE_KEY) } catch { /* 忽略 */ }
      if (isLogin && userId) {
        await this.loadSessions()
      }
    },
  },
})
