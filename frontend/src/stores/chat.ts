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
import { setDelegateProgressSink } from '@/lib/agent/subagent'
import { buildMcpTools } from '@/lib/agent/mcp'
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
// 内核池容量上限（超出淘汰最旧的非运行内核，上下文可从后端恢复）
const MAX_KERNELS = 8
// 技能清单缓存（全局一份，套用到每个新内核的系统提示）
let skillsCache: Awaited<ReturnType<typeof listAgentSkills>> | null = null
// per-session 内核池（按 store 实例分池；类实例不进响应式 state，避免 Vue 类型解包破坏其私有结构）
const kernelPools = new WeakMap<object, Map<string, AgentKernel>>()
function poolOf(store: object): Map<string, AgentKernel> {
  let m = kernelPools.get(store)
  if (!m) {
    m = new Map()
    kernelPools.set(store, m)
  }
  return m
}

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

/** 新建 assistant 消息（内核 round_start / 兜底建条用） */
function newAssistantMessage(): ChatKernelMessage {
  return { id: uid(), role: 'assistant', content: '', media: [], steps: [], createdAt: new Date().toISOString() }
}

// =====================================================
// 视图映射：内核投影 → 共享气泡视图（纯函数）
// =====================================================

function imageDataUrl(img: { data: string; mimeType: string }): string {
  return `data:${img.mimeType};base64,${img.data}`
}

/** 工具步骤标签：复用画布 agent.act* 文案（两宿主同词） */
function toolLabel(tool: string, args?: Record<string, unknown>): string {
  if (tool === 'generate_image') return t('agent.actGenImage')
  if (tool === 'generate_video') return t('agent.actGenVideo')
  if (tool === 'agent_load_skill') {
    const name = args && typeof args.name === 'string' ? args.name : ''
    return name ? `${t('agent.actLoadSkill')}：${name}` : t('agent.actLoadSkill')
  }
  return tool
}

function toStepView(s: AgentStepRecord): ChatStepView {
  return { callId: s.callId, label: toolLabel(s.tool, s.args), tooltip: s.tool, status: toStepStatus(s.status), progress: delegateProgressText(s) }
}

/** agent_delegate 步骤的实时进度文本（running 态渲染，i18n 组装） */
function delegateProgressText(s: AgentStepRecord): string | undefined {
  if (s.status !== 'running' || !s.delegateProgress) return undefined
  const { round, tool } = s.delegateProgress
  return `${t('agent.delegateProgress', { n: round })}${tool ? ` · ${tool}` : ''}`
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
      // assistant 必须是 pi 内部消息形状：content 为块数组 + stopReason + usage，
      // 缺任一都会让机制层的上下文估算/消息转换在下一回合抛错（历史版本曾落库过字符串内容的坏形状）
      msgs.push({
        role: 'assistant',
        content: [{ type: 'text', text: r.content || '' }],
        stopReason: 'stop',
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
        timestamp: Date.now(),
      })
    }
  }
  return { messages: msgs }
}

// per-session 内核池：每会话一个内核实例（poolOf(this) 按 store 实例分池）

export const useChatStore = defineStore('chat', {
  state: (): {
    sessions: ChatSession[]
    sessionsTotal: number
    activeSessionId: number | null
    /** 活跃会话的消息数组（与 sessionMessages[activeId] 同一引用） */
    messages: ChatKernelMessage[]
    loadingMessages: boolean
    /** 各会话最近一次运行错误（key=会话 id；活跃会话经 activeError 暴露给视图） */
    errors: Record<string, string>
    /** 各会话的内存消息数组（key=会话 id；后台运行的会话事件写这里，切回即见） */
    sessionMessages: Record<string, ChatKernelMessage[]>
    /** 进行中的运行（key=会话 id；多会话可同时各跑一轮） */
    runningSessions: Record<string, { thinking: boolean }>
    /** 对话模型 id（空 = 后端默认解析链；输入条模型胶囊可见可切换） */
    chatModelId: string
    // 媒体任务轮询（taskId -> timer）
    mediaPollTimers: Record<string, ReturnType<typeof setInterval>>
    mediaPollFailCounts: Record<string, number>
    // taskId -> 本地消息 id（轮询回填定位）
    mediaTaskToMessageId: Record<string, string>
    // taskId -> 归属会话 id（后台轮询终端态按归属落库）
    mediaTaskSession: Record<string, number>
    // 是否已完成初始化（配合 keep-alive）
    _initialized: boolean
  } => ({
    sessions: [],
    sessionsTotal: 0,
    activeSessionId: null,
    messages: [],
    errors: {},
    loadingMessages: false,
    sessionMessages: {},
    runningSessions: {},
    chatModelId: readChatModel(),
    mediaPollTimers: {},
    mediaPollFailCounts: {},
    mediaTaskToMessageId: {},
    mediaTaskSession: {},
    _initialized: false,
  }),

  getters: {
    activeSession(state): ChatSession | null {
      return state.sessions.find(s => s.id === state.activeSessionId) || null
    },
    hasActiveSession(state): boolean {
      return state.activeSessionId !== null
    },
    /** 活跃会话是否有进行中的运行 */
    busy(): boolean {
      const sid = this.activeSessionId
      return sid !== null && String(sid) in this.runningSessions
    },
    /** 活跃会话的运行是否处于思考阶段 */
    thinking(): boolean {
      const sid = this.activeSessionId
      return sid !== null ? (this.runningSessions[String(sid)]?.thinking ?? false) : false
    },
    /** 指定会话是否有进行中的运行（侧栏角标） */
    isRunning(): (id: number | string) => boolean {
      return (id: number | string) => String(id) in this.runningSessions
    },
    /** 活跃会话最近一次运行错误（消息区尾部展示） */
    activeError(): string | null {
      const sid = this.activeSessionId
      return sid !== null ? (this.errors[String(sid)] ?? null) : null
    },
    messageItems(state): ChatBubbleItem[] {
      return toChatBubbleItems(state.messages, this.busy)
    },
  },

  actions: {
    // =====================================================
    // 内核装配
    // =====================================================

    /** per-session 内核：每个会话一个内核实例，各自持有 LLM 上下文（多会话可同时各跑一轮） */
    _createKernel(sessionId: number): AgentKernel {
      const k = new AgentKernel({
        systemPrompt: CHAT_SYSTEM_PROMPT_BASE,
        getAuthToken: async () => {
          const headers = await getAuthHeaders()
          const auth = headers.Authorization
          return typeof auth === 'string' && auth.startsWith('Bearer ') ? auth.slice(7) : null
        },
        tools: CHAT_TOOLS,
        toolContext: {
          getRecentMediaUrl: (type: 'image' | 'video') => this.recentMediaUrl(sessionId, type),
        },
      })
      // 恢复用户选定的对话模型（与画布共用同一偏好）
      if (this.chatModelId) k.setModel(createAgentModel(this.chatModelId))
      // 技能清单快照（已取过则直接套用；失败沿用基础提示，不阻断内核创建）
      if (skillsCache) {
        try {
          k.setSystemPrompt(buildChatSystemPrompt(skillsCache))
        } catch {
          // 忽略
        }
      }
      k.subscribe((e) => this._onKernelEvent(sessionId, e))
      // 子代理进度 sink：delegate 步骤行实时更新（running 态）
      setDelegateProgressSink(k, (callId, info) => {
        if (!this.sessions.some((s) => s.id === sessionId)) return
        const step = this._findStep(this._messagesOf(sessionId), callId)
        if (step && step.status === 'running') step.delegateProgress = info
      })
      return k
    },

    /** 取会话内核（缺席则创建并从后端恢复上下文；容量上限淘汰最旧的非运行内核） */
    async _kernelFor(sessionId: number): Promise<AgentKernel> {
      const pool = poolOf(this)
      const key = String(sessionId)
      const existing = pool.get(key)
      if (existing) return existing
      if (pool.size >= MAX_KERNELS) {
        for (const [oldKey, oldKernel] of pool) {
          if (!this.runningSessions[oldKey]) {
            oldKernel.reset()
            pool.delete(oldKey)
            break
          }
        }
      }
      const k = this._createKernel(sessionId)
      pool.set(key, k)
      // MCP 工具清单：会话建立时后台刷新（失败降级为空；流式中内核侧跳过，下次刷新生效）
      void buildMcpTools().then((tools) => k.setExtraTools(tools))
      try {
        const [detail, rowsResp] = await Promise.all([
          getAgentSession(sessionId).catch(() => null),
          getChatMessages(sessionId).catch(() => ({ items: [] as ChatMessage[] })),
        ])
        const context = detail?.context
        const restored = k.restore(isRecord(context) ? context : chatContextFromRows(rowsResp.items || []))
        if (!restored) k.reset()
      } catch {
        k.reset()
      }
      return k
    },

    /** 切换对话模型：记忆选择并热更新所有内核（下一回合生效；空串 = 回默认解析链） */
    setChatModel(id: string): void {
      this.chatModelId = id
      try {
        if (id) localStorage.setItem('agnes_agent_chat_model', id)
        else localStorage.removeItem('agnes_agent_chat_model')
      } catch {
        // 记忆失败不影响切换
      }
      const model = id ? createAgentModel(id) : null
      if (!model) return
      for (const [, k] of poolOf(this)) {
        k.setModel(model)
      }
    },

    /** 技能清单快照进系统提示（缓存清单；新内核创建时直接套用） */
    async _applySkillsPrompt(k: AgentKernel): Promise<void> {
      try {
        if (!skillsCache) {
          skillsCache = await listAgentSkills()
        }
        k.setSystemPrompt(buildChatSystemPrompt(skillsCache))
      } catch {
        // 技能库不可用沿用基础提示
      }
    },

    /** 指定会话最近一次成功生成的媒体 URL（会话连续性：图生图/图生视频默认参考） */
    recentMediaUrl(sessionId: number, type: 'image' | 'video'): string | null {
      const arr = this._messagesOf(sessionId)
      for (let i = arr.length - 1; i >= 0; i--) {
        const m = arr[i]
        for (let j = m.media.length - 1; j >= 0; j--) {
          const item = m.media[j]
          if (item.type === type && item.status === 'success' && item.url) return item.url
        }
      }
      return null
    },

    _onKernelEvent(sessionId: number, e: KernelEvent): void {
      // 会话已被删除：忽略残余事件（停止/删除竞态）
      if (!this.sessions.some((s) => s.id === sessionId)) return
      const arr = this._messagesOf(sessionId)
      switch (e.type) {
        case 'thinking': {
          this._runState(sessionId).thinking = e.active
          break
        }
        case 'round_start': {
          this._runState(sessionId).thinking = true
          arr.push(newAssistantMessage())
          break
        }
        case 'text_delta': {
          this._runState(sessionId).thinking = false
          this._ensureAssistant(arr).content += e.delta
          break
        }
        case 'tool_start': {
          this._runState(sessionId).thinking = false
          this._ensureAssistant(arr).steps.push({ callId: e.callId, tool: e.tool, args: e.args, status: 'running', result: null })
          break
        }
        case 'tool_end': {
          const step = this._findStep(arr, e.callId)
          if (step && step.status !== 'rejected') {
            step.status = e.ok ? 'done' : 'error'
            step.result = e.result
          }
          // 生成工具：结果含 task_id → 挂媒体占位并启动轮询（占位/回填机制沿用）
          if (e.ok && (e.tool === 'generate_image' || e.tool === 'generate_video')) {
            this._attachPendingMedia(sessionId, arr, e.tool, e.callId, e.result)
          }
          break
        }
        case 'tool_rejected': {
          // chat 宿主无阶段门；占位处理保持与 agent store 同构
          const msg = this._ensureAssistant(arr)
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
          this._runState(sessionId).thinking = false
          const last = arr[arr.length - 1]
          if (last && last.role === 'assistant' && !last.content && last.steps.length === 0 && last.media.length === 0) arr.pop()
          delete this.runningSessions[String(sessionId)]
          if (e.error) this.errors[String(sessionId)] = e.error
          void this._persist(sessionId, arr)
          // 自动总结标题：首轮回复后标题仍为默认时调一次（读已落库消息行）
          if (!e.error) {
            const session = this.sessions.find((s) => s.id === sessionId)
            if (session && !session.title) void this.autoSummarizeSession(sessionId).catch(() => {})
          }
          break
        }
      }
    },

    /** 取当前轮的 assistant 消息（数组末条），没有则新建 */
    _ensureAssistant(arr: ChatKernelMessage[]): ChatKernelMessage {
      const last = arr[arr.length - 1]
      if (last && last.role === 'assistant') return last
      const msg = newAssistantMessage()
      arr.push(msg)
      return msg
    },

    _findStep(arr: ChatKernelMessage[], callId: string): AgentStepRecord | null {
      for (let i = arr.length - 1; i >= 0; i--) {
        const msg = arr[i]
        const step = msg.steps.find((s) => s.callId === callId)
        if (step) return step
        if (msg.role === 'user') break
      }
      return null
    },

    /** 会话消息数组（缺席则建空数组并缓存；活跃会话与 this.messages 同引用） */
    _messagesOf(sessionId: number): ChatKernelMessage[] {
      const key = String(sessionId)
      let arr = this.sessionMessages[key]
      if (!arr) {
        arr = []
        this.sessionMessages[key] = arr
      }
      return arr
    },

    /** 运行状态（缺席则建） */
    _runState(sessionId: number): { thinking: boolean } {
      const key = String(sessionId)
      if (!this.runningSessions[key]) this.runningSessions[key] = { thinking: false }
      return this.runningSessions[key]
    },

    /** 生成工具完成 → 当前 assistant 消息挂 pending 媒体占位 + 启动轮询 */
    _attachPendingMedia(sessionId: number, arr: ChatKernelMessage[], tool: string, callId: string, resultJson: string): void {
      try {
        const parsed: unknown = JSON.parse(resultJson)
        if (!isRecord(parsed) || typeof parsed.task_id !== 'string') return
        const taskId = parsed.task_id
        const type: MediaItem['type'] = tool === 'generate_video' ? 'video' : 'image'
        const msg = arr.find((m) => m.steps.some((s) => s.callId === callId))
        if (!msg) return
        if (msg.media.some((m) => m.task_id === taskId)) return
        msg.media.push({ type, url: '', task_id: taskId, status: 'pending' })
        this.mediaTaskToMessageId[taskId] = msg.id
        this.mediaTaskSession[taskId] = sessionId
        this._startMediaPoll(taskId)
      } catch {
        // 结果非 JSON（异常信息）忽略
      }
    },

    // =====================================================
    // 发送
    // =====================================================

    /** 发送用户消息（attachments：粘贴/上传/URL 识别的附件）；各会话独立内核，可多会话同时生成 */
    async send(text: string, attachments: MessageAttachment[] = []): Promise<void> {
      const trimmed = text.trim()
      if (!trimmed && attachments.length === 0) return
      if (!this.activeSessionId) {
        await this.newSession()
      }
      const sessionId = this.activeSessionId as number
      // 该会话已有运行中的一轮（其他会话不受影响）
      if (this.runningSessions[String(sessionId)]) return
      // 不变量：视图数组与归属会话的缓存数组同引用
      this.messages = this._messagesOf(sessionId)
      this.runningSessions[String(sessionId)] = { thinking: true }
      delete this.errors[String(sessionId)]
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
      this._messagesOf(sessionId).push({
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
        const k = await this._kernelFor(sessionId)
        await this._applySkillsPrompt(k)
        await this._persist(sessionId)
        await k.send(trimmed, images)
      } catch (e) {
        this.errors[String(sessionId)] = e instanceof Error ? e.message : String(e)
      } finally {
        delete this.runningSessions[String(sessionId)]
        await this._persist(sessionId)
      }
    },

    /** 用户请求停止（停止活跃会话的当前轮；其他会话运行不受影响） */
    requestStop(): void {
      const sid = this.activeSessionId
      if (sid === null) return
      poolOf(this).get(String(sid))?.requestStop()
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
        const arr: ChatKernelMessage[] = []
        this.sessionMessages[String(session.id)] = arr
        this.messages = arr
        this._saveToStorage()
        return session
      } catch (e: unknown) {
        console.error('[Chat] 创建会话失败:', e)
        throw e
      }
    },

    async switchSession(sessionId: number): Promise<void> {
      if (sessionId === this.activeSessionId) return
      // 纯视图切换：各会话独立内核，其他会话的后台运行不受影响
      this.activeSessionId = sessionId
      await this._loadSession(sessionId)
      this._saveToStorage()
    },

    async removeSession(sessionId: number): Promise<void> {
      // 会话有运行中的内核：先停再删；残余事件由 _onKernelEvent 的会话存在性检查忽略
      const k = poolOf(this).get(String(sessionId))
      if (k) {
        if (this.runningSessions[String(sessionId)]) k.requestStop()
        k.reset()
        poolOf(this).delete(String(sessionId))
      }
      delete this.sessionMessages[String(sessionId)]
      delete this.runningSessions[String(sessionId)]
      try {
        await deleteChatSession(sessionId)
        this.sessions = this.sessions.filter(s => s.id !== sessionId)
        if (this.activeSessionId === sessionId) {
          this.activeSessionId = null
          this.messages = []
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

    /** 载入会话视图：内存缓存优先（含后台运行中的会话），否则拉消息行投影；恢复在途媒体轮询。
     *  不触碰内核——各会话内核独立持有上下文，缺席时在发送前按需恢复。 */
    async _loadSession(sessionId: number): Promise<void> {
      this.loadingMessages = true
      try {
        const cached = this.sessionMessages[String(sessionId)]
        if (cached) {
          this.messages = cached
        } else {
          const rowsResp = await getChatMessages(sessionId)
          const rows: ChatMessage[] = rowsResp.items || []
          const arr = messagesFromRows(rows)
          this.sessionMessages[String(sessionId)] = arr
          this.messages = arr
        }
        // 在途媒体任务继续轮询
        for (const m of this.messages) {
          for (const item of m.media) {
            if (item.task_id && (item.status === 'pending' || item.status === 'processing')) {
              this.mediaTaskToMessageId[item.task_id] = m.id
              this.mediaTaskSession[item.task_id] = sessionId
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

    /** 按taskId定位消息：归属会话的消息数组（mediaTaskSession 登记归属） */
    _findMessageByTask(taskId: string): ChatKernelMessage | null {
      const owner = this.mediaTaskSession[taskId]
      const arr = owner !== undefined ? this._messagesOf(owner) : this.messages
      return arr.find((m) => m.media.some((i) => i.task_id === taskId)) ?? null
    },

    _startMediaPoll(taskId: string): void {
      if (this.mediaPollTimers[taskId]) return
      this.mediaPollFailCounts[taskId] = 0
      const poll = async (): Promise<void> => {
        try {
          const data: MediaStatusResponse = await getMediaStatus(taskId)
          this.mediaPollFailCounts[taskId] = 0
          const msg = this._findMessageByTask(taskId)
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
            // 终端态落库（全量同步消息行，按归属会话）
            this._persistMediaOwner(taskId, msg)
          } else if (isMediaFailed(rawStatus)) {
            item.status = 'failed'
            this._stopMediaPoll(taskId)
            this._updateTaskQueueItem(taskId, 'failed', '')
            this._persistMediaOwner(taskId, msg)
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
            const msg = this._findMessageByTask(taskId)
            const item = msg?.media.find((i) => i.task_id === taskId)
            if (item && item.status !== 'success') item.status = 'failed'
          }
        }
      }
      void poll()
      this.mediaPollTimers[taskId] = setInterval(poll, MEDIA_POLL_INTERVAL)
    },

    /** 媒体终端态落库：按归属会话同步其消息数组 */
    _persistMediaOwner(taskId: string, msg: ChatKernelMessage | null): void {
      const owner = this.mediaTaskSession[taskId] ?? this.activeSessionId
      if (owner !== null && owner !== undefined) void this._persist(owner, this._messagesOf(owner))
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

    /** 全量同步落库：默认落当前视图；后台完成时按归属会话落其缓冲 */
    async _persist(sessionId?: number | null, messages?: ChatKernelMessage[]): Promise<void> {
      const sid = sessionId ?? this.activeSessionId
      if (!sid) return
      const projectable: ProjectableMessage[] = (messages ?? this.messages).map((m) => ({
        role: m.role,
        content: m.content,
        images: m.images,
        urlAttachments: m.urlAttachments?.filter((a): a is MessageAttachment & { url: string } => typeof a?.url === 'string'),
        media: m.media,
        steps: m.steps,
        createdAt: m.createdAt,
      }))
      try {
        await syncAgentSession(sid, {
          title: this.sessions.find((s) => s.id === sid)?.title || '新对话',
          workspace_id: null,
          context: poolOf(this).get(String(sid))?.serializeState() ?? null,
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
      // 中止全部运行与媒体轮询；清空内核池（不残留上一个用户的上下文）
      try { this.requestStop() } catch { /* 忽略 */ }
      this.stopAllMediaPolls()
      for (const [, k] of poolOf(this)) {
        try { k.reset() } catch { /* 忽略 */ }
      }
      poolOf(this).clear()
      skillsCache = null
      this.sessionMessages = {}
      this.runningSessions = {}
      this.sessions = []
      this.sessionsTotal = 0
      this.activeSessionId = null
      this.messages = []
      this.errors = {}
      this.mediaTaskToMessageId = {}
      try { localStorage.removeItem(STORAGE_KEY) } catch { /* 忽略 */ }
      if (isLogin && userId) {
        await this.loadSessions()
      }
    },
  },
})
