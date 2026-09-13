/* =====================================================
 * 画布 Agent store（UI 投影层）
 *
 * - 内核在 lib/agent/kernel.ts（内核装配 + 策略 + 事件转译）
 * - 本 store 只做：面板状态、内核事件 → 消息/时间线投影、确认卡片中转、
 *   多会话管理（列表/切换/删除，持久化走 lib/agent/session-store，
 *   按 用户 + 工作区 隔离到 localforage，跟画布同生命周期）
 * - 会话切换 = 内核序列化/恢复 + 时间线重建；busy 时禁止切换
 * ===================================================== */

import { defineStore } from 'pinia'
import { useCanvasStore } from '@/stores/canvas'
import { useUserStore } from '@/stores/user'
import { AgentKernel, rebuildTimeline } from '@/lib/agent/kernel'
import type { KernelEvent, KernelTimelineMessage, AgentImageAttachment } from '@/lib/agent/kernel'
import { setDelegateProgressSink } from '@/lib/agent/subagent'
import { buildMcpTools } from '@/lib/agent/mcp'
import { MAX_IMAGES_PER_MESSAGE } from '@/lib/agent/attachments'
import { AGENT_SYSTEM_PROMPT_BASE, buildAgentSystemPrompt } from '@/lib/agent/system-prompt'
import { listAgentSkills } from '@/lib/agent/skills'
import { createAgentModel } from '@/lib/agent/provider'
import {
  listSessionsMeta, saveSessionsMeta, pullSession, syncSession,
  deleteBackendSession, renameBackendSession, clearSessionCache,
  deriveSessionTitle, toBackendMessages,
} from '@/lib/agent/session-store'
import type { AgentSessionMeta } from '@/lib/agent/session-store'
import { getAuthHeaders } from '@/api/chat'
import type { AgentMode } from '@/lib/agent/policy'

export type { AgentMode }

/** 时间线上的单次工具调用 */
export interface AgentToolStep {
  callId: string
  tool: string
  args: Record<string, unknown>
  status: 'pending' | 'running' | 'done' | 'error' | 'rejected'
  /** 回填给 LLM 的结果 JSON（恢复会话时重建上下文用） */
  result: string | null
  /** agent_delegate 步骤的实时子任务进度（running 态渲染，结束后不清理由结果覆盖展示） */
  delegateProgress?: { round: number; tool: string | null }
}

export interface AgentMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  /** 用户消息附图（裸 base64，气泡缩略图与恢复会话用） */
  images?: AgentImageAttachment[]
  steps: AgentToolStep[]
  createdAt: string
}

export interface AgentPendingConfirm {
  kind: 'stage' | 'tool'
  tool: string
  args: Record<string, unknown>
  stage: string
  summary: string
  /** 子代理门请求的来源标签（确认卡展示"来自子任务"） */
  source?: string
}

const STOPPED_NOTICE = '已停止执行。进行中的生成任务会继续在后台完成，结果仍会写回对应节点；你可以随时继续对话。'

function uid(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
}

function userKey(): string {
  try {
    const userStore = useUserStore()
    return userStore?.userId != null ? 'u_' + String(userStore.userId) : 'anon'
  } catch {
    return 'anon'
  }
}

/** 对话模型选择记忆（空 = 跟随后端默认解析链） */
function readChatModel(): string {
  try {
    return localStorage.getItem('agnes_agent_chat_model') ?? ''
  } catch {
    return ''
  }
}

/** 内核单例：与 store 同生命周期（工具执行需要 canvas store，经 getter 注入）；
 * 事件与档位读取都经 boundStore 分发——store 实例可被替换（测试/HMR），内核无需重建 */
let kernel: AgentKernel | null = null
let boundStore: { mode: AgentMode; _onKernelEvent: (e: KernelEvent) => void } | null = null

export const useAgentStore = defineStore('agent', {
  state: (): {
    open: boolean
    mode: AgentMode
    /** 对话模型 id（空 = 跟随后端默认解析链；面板模型胶囊可见可切换） */
    chatModelId: string
    /** 当前 scope 的会话列表（按 updatedAt 倒序维护，活跃在最前） */
    sessions: AgentSessionMeta[]
    activeSessionId: string | null
    messages: AgentMessage[]
    busy: boolean
    /** 模型思考/调用期（turn_start 起点亮，正文/工具开始后熄灭），供面板工作指示 */
    thinking: boolean
    error: string | null
    pendingConfirm: AgentPendingConfirm | null
    /** 已加载的 用户_工作区 scope（跨会话复用，切 scope 才重载） */
    loadedKey: string
  } => ({
    open: false,
    mode: 'confirm',
    chatModelId: readChatModel(),
    sessions: [],
    activeSessionId: null,
    messages: [],
    busy: false,
    thinking: false,
    error: null,
    pendingConfirm: null,
    loadedKey: '',
  }),

  actions: {
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

    /** 懒建内核并接事件投影（store 首次用到时调用）；每次调用重绑事件目标 store */
    _ensureKernel(): AgentKernel {
      const store = this
      boundStore = store
      if (kernel) return kernel
      kernel = new AgentKernel({
        getCanvas: () => useCanvasStore(),
        // 档位读 boundStore（实时），避免捕获创建时 store 实例导致档位失效
        getMode: () => boundStore?.mode ?? store.mode,
        systemPrompt: AGENT_SYSTEM_PROMPT_BASE,
        getAuthToken: async () => {
          const headers = await getAuthHeaders()
          const auth = headers.Authorization
          return typeof auth === 'string' && auth.startsWith('Bearer ') ? auth.slice(7) : null
        },
      })
      kernel.subscribe((e) => boundStore?._onKernelEvent(e))
      // 子代理进度 sink：delegate 步骤行实时更新（running 态）
      setDelegateProgressSink(kernel, (callId, info) => {
        const step = store._findStep(callId)
        if (step && step.status === 'running') step.delegateProgress = info
      })
      // 面板直接改 store.mode：同步内核工具清单
      this.$subscribe(() => {
        kernel?.setMode(store.mode)
      })
      return kernel
    },

    _lastAssistant(): AgentMessage | null {
      const last = this.messages[this.messages.length - 1]
      return last && last.role === 'assistant' ? last : null
    },

    _onKernelEvent(e: KernelEvent): void {
      switch (e.type) {
        case 'thinking': {
          this.thinking = e.active
          break
        }
        case 'round_start': {
          this.thinking = true
          this.messages.push({ id: uid(), role: 'assistant', content: '', steps: [], createdAt: new Date().toISOString() })
          break
        }
        case 'text_delta': {
          this.thinking = false
          const msg = this._lastAssistant() ?? this.messages[this.messages.push({ id: uid(), role: 'assistant', content: '', steps: [], createdAt: new Date().toISOString() }) - 1]
          msg.content += e.delta
          break
        }
        case 'tool_start': {
          this.thinking = false
          const msg = this._lastAssistant() ?? this.messages[this.messages.push({ id: uid(), role: 'assistant', content: '', steps: [], createdAt: new Date().toISOString() }) - 1]
          msg.steps.push({ callId: e.callId, tool: e.tool, args: e.args, status: 'running', result: null })
          break
        }
        case 'tool_end': {
          const step = this._findStep(e.callId)
          // 阶段门/停止/只读拒绝的步骤保持 rejected，不被机制层 error 结果覆盖
          if (step && step.status !== 'rejected') {
            step.status = e.ok ? 'done' : 'error'
            step.result = e.result
          }
          break
        }
        case 'tool_rejected': {
          const msg = this._lastAssistant() ?? this.messages[this.messages.push({ id: uid(), role: 'assistant', content: '', steps: [], createdAt: new Date().toISOString() }) - 1]
          if (!msg.steps.some((s) => s.callId === e.callId)) {
            msg.steps.push({ callId: e.callId, tool: e.tool, args: {}, status: 'rejected', result: e.reason })
          } else {
            const step = this._findStep(e.callId)
            if (step) {
              step.status = 'rejected'
              step.result = e.reason
            }
          }
          break
        }
        case 'confirm_request': {
          this.pendingConfirm = { kind: e.kind, tool: e.tool, args: e.args, stage: e.stage, summary: e.summary, source: e.source }
          break
        }
        case 'done': {
          this.busy = false
          this.thinking = false
          this.pendingConfirm = null
          if (e.error) this.error = e.error
          if (e.stopped && !e.error) {
            this.messages.push({ id: uid(), role: 'assistant', content: STOPPED_NOTICE, steps: [], createdAt: new Date().toISOString() })
          }
          // 清掉尾部空回合（无文本无步骤的 assistant 占位）
          const last = this._lastAssistant()
          if (last && !last.content && last.steps.length === 0) this.messages.pop()
          void this._persist()
          break
        }
      }
    },

    _findStep(callId: string): AgentToolStep | null {
      for (let i = this.messages.length - 1; i >= 0; i--) {
        const msg = this.messages[i]
        const step = msg.steps.find((s) => s.callId === callId)
        if (step) return step
        if (msg.role === 'user') break
      }
      return null
    },

    /** 用户请求停止：内核中止循环；进行中的生成任务转后台继续（结果仍写回节点） */
    requestStop(): void {
      this._ensureKernel().requestStop()
    },

    /** 确认卡片放行/拒绝（阶段门与阶段汇报共用） */
    confirmPending(approved: boolean): void {
      this._ensureKernel().confirm(approved)
      this.pendingConfirm = null
      void this._persist()
    },

    /** 当前 用户_工作区 存储 scope */
    _scope(): string {
      const canvas = useCanvasStore()
      return `${userKey()}_${canvas.activeWorkspaceId || 'default'}`
    },

    /** 面板打开与工作区切换时调用：恢复该 scope 的会话列表与活跃会话（无则新建空会话） */
    async ensureSession() {
      const canvas = useCanvasStore()
      const workspaceId = canvas.activeWorkspaceId || 'default'
      const scope = this._scope()
      if (this.loadedKey === scope) return
      const k = this._ensureKernel()
      // MCP 工具清单：会话建立时后台刷新（失败降级为空；流式中内核侧跳过，下次刷新生效）
      if (!this.busy) void buildMcpTools().then((tools) => k.setExtraTools(tools))
      // 恢复用户选定的对话模型（无选择则保持占位 id 走后端默认解析链）
      if (this.chatModelId) k.setModel(createAgentModel(this.chatModelId))
      // 会话建立时快照技能清单进系统提示（技能库不可用则沿用基础提示，不阻塞对话）
      const skills = await listAgentSkills()
      k.setSystemPrompt(buildAgentSystemPrompt(skills))
      const meta = await listSessionsMeta(scope, workspaceId)
      this.sessions = meta.sessions
      const active = meta.sessions.find((s) => s.id === meta.activeId) ?? meta.sessions[0]
      if (active) {
        await this._loadIntoKernel(scope, active.id)
        this.activeSessionId = active.id
      } else {
        this._startSession()
        await this._saveMeta()
      }
      this.loadedKey = scope
      this.pendingConfirm = null
    },

    /** 载入指定会话：先重置内核防脏残留，再恢复内核上下文（后端为准、本地兜底）并重建时间线 */
    async _loadIntoKernel(scope: string, sessionId: string): Promise<void> {
      const k = this._ensureKernel()
      k.reset()
      this.messages = []
      this.error = null
      const backendId = this.sessions.find((s) => s.id === sessionId)?.backendId ?? null
      const raw = await pullSession(scope, sessionId, backendId)
      const restored = k.restore(raw)
      const timeline = restored ? rebuildTimeline(raw) : null
      this.messages = timeline
        ? timeline.map((t: KernelTimelineMessage) => ({ ...t, id: uid() }))
        : []
    },

    /** 按 backendId 定位并切换会话（全局对话列表跳转画布用）；返回是否命中 */
    async openSessionByBackendId(backendId: number): Promise<boolean> {
      await this.ensureSession()
      const target = this.sessions.find((s) => s.backendId === backendId)
      if (!target) return false
      await this.switchSession(target.id)
      return true
    },

    /** 内存开新空会话：kernel 重置 + 时间线清空 + 新 meta 置顶（落盘由调用方负责） */
    _startSession(): string {
      this._ensureKernel().reset()
      this.messages = []
      this.error = null
      const now = new Date().toISOString()
      const meta: AgentSessionMeta = { id: uid(), backendId: null, title: '', createdAt: now, updatedAt: now }
      this.sessions = [meta, ...this.sessions]
      this.activeSessionId = meta.id
      return meta.id
    },

    /** 新建会话：当前会话落盘后切到空会话（busy 时忽略） */
    async createSession() {
      if (this.busy) return
      const scope = this._scope()
      await this._persistCurrent(scope)
      this._startSession()
      await this._saveMeta()
    },

    /** 切换会话：当前落盘 → 恢复目标（busy 时禁止，避免内核流式中被换血） */
    async switchSession(sessionId: string) {
      if (this.busy || sessionId === this.activeSessionId) return
      if (!this.sessions.some((s) => s.id === sessionId)) return
      const scope = this._scope()
      await this._persistCurrent(scope)
      await this._loadIntoKernel(scope, sessionId)
      this.activeSessionId = sessionId
      this.pendingConfirm = null
      await this._saveMeta()
    },

    /** 删除会话；删的是活跃会话时自动切到最近一条，没有则新建空会话 */
    async deleteSession(sessionId: string) {
      if (this.busy) return
      const scope = this._scope()
      const wasActive = sessionId === this.activeSessionId
      const target = this.sessions.find((s) => s.id === sessionId)
      this.sessions = this.sessions.filter((s) => s.id !== sessionId)
      try {
        await clearSessionCache(scope, sessionId)
      } catch {
        // 缓存删除失败不影响列表收敛
      }
      // 已同步过的会话连后端一起删（静默）
      if (target?.backendId != null) void deleteBackendSession(target.backendId)
      if (wasActive) {
        const next = this.sessions[0]
        if (next) {
          await this._loadIntoKernel(scope, next.id)
          this.activeSessionId = next.id
        } else {
          this._startSession()
        }
        this.pendingConfirm = null
      }
      await this._saveMeta()
    },

    /** 重命名会话（已同步的异步调后端，静默） */
    async renameSession(sessionId: string, title: string) {
      const s = this.sessions.find((x) => x.id === sessionId)
      const trimmed = title.trim()
      if (!s || !trimmed) return
      s.title = trimmed
      s.updatedAt = new Date().toISOString()
      if (s.backendId != null) void renameBackendSession(s.backendId, trimmed)
      await this._saveMeta()
    },

    /** 应用后端生成的标题（AI 总结：后端已落库，这里只同步本地 meta） */
    applyTitle(sessionId: string, title: string): void {
      const s = this.sessions.find((x) => x.id === sessionId)
      const trimmed = title.trim()
      if (!s || !trimmed) return
      s.title = trimmed
      s.updatedAt = new Date().toISOString()
      void this._saveMeta()
    },

    /** 清空当前会话内容（保留会话身份，等价于重新开始本轮对话） */
    async clearSession() {
      this._ensureKernel().reset()
      this.messages = []
      this.error = null
      this.pendingConfirm = null
      const s = this.sessions.find((x) => x.id === this.activeSessionId)
      if (s) {
        s.title = ''
        s.updatedAt = new Date().toISOString()
      }
      await this._saveMeta()
      await this._persist()
    },

    /** 活跃会话 meta 触碰：更新时间 + 首条用户消息派生标题（无标题时） */
    _touchActiveMeta(): void {
      const s = this.sessions.find((x) => x.id === this.activeSessionId)
      if (!s) return
      s.updatedAt = new Date().toISOString()
      if (!s.title) {
        const first = this.messages.find((m) => m.role === 'user' && m.content.trim())
        if (first) s.title = deriveSessionTitle(first.content)
      }
    },

    async _saveMeta() {
      try {
        await saveSessionsMeta(this._scope(), { activeId: this.activeSessionId, sessions: this.sessions })
      } catch {
        // 持久化失败不阻断对话（内存态仍可用）
      }
    },

    /** 落盘当前会话：内核消息数组写 data key + meta 写列表 key */
    async _persistCurrent(scope: string) {
      if (!this.activeSessionId) return
      try {
        this._touchActiveMeta()
        const s = this.sessions.find((x) => x.id === this.activeSessionId)
        if (!s) return
        const canvas = useCanvasStore()
        // 数据库为准：无 backendId 先创建再全量同步；失败静默（syncSession 内已写本地缓存兜底）
        const res = await syncSession(
          scope,
          s.id,
          {
            title: s.title || '新对话',
            workspaceId: canvas.activeWorkspaceId || 'default',
            context: this._ensureKernel().serializeState(),
            messages: toBackendMessages(this.messages),
          },
          s.backendId,
        )
        if (res.backendId !== s.backendId) {
          s.backendId = res.backendId
        }
        await saveSessionsMeta(scope, { activeId: this.activeSessionId, sessions: this.sessions })
      } catch {
        // 同步失败不阻断对话（内存态与本地缓存仍可用）
      }
    },

    async _persist() {
      await this._persistCurrent(this._scope())
    },

    /** 发送用户消息：text 可为空但 images 至少一项；文件文本已由面板拼进 text */
    async send(text: string, images?: AgentImageAttachment[]) {
      const trimmed = text.trim()
      const imgs = (images ?? []).slice(0, MAX_IMAGES_PER_MESSAGE)
      if (this.busy || (!trimmed && imgs.length === 0)) return
      this.open = true
      this.busy = true
      this.thinking = true
      this.error = null
      try {
        await this.ensureSession()
        this.messages.push({
          id: uid(),
          role: 'user',
          content: trimmed,
          images: imgs.length ? imgs : undefined,
          steps: [],
          createdAt: new Date().toISOString(),
        })
        await this._persist()
        await this._ensureKernel().send(trimmed, imgs)
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      } finally {
        this.busy = false
        await this._persist()
      }
    },
  },
})
