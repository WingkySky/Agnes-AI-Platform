/* =====================================================
 * 画布 Agent 内核（机制层装配，UI 无关）
 *
 * - 装配：画布工具（TypeBox）+ 策略钩子（beforeToolCall → policy）
 *   + LLM 通道（provider）+ 事件转译（机制层事件 → 内核事件，UI 不接触机制层类型）
 * - 语义与旧自研内核一致：三档权限、阶段门首次过门、停止转后台、回合上限 40
 * - 依赖经构造注入（canvas/档位/系统提示词/取 token），可直接单测
 * ===================================================== */

import { Agent } from '@earendil-works/pi-agent-core'
import type { AgentEvent, AgentTool as PiAgentTool, BeforeToolCallContext, BeforeToolCallResult, StreamFn } from '@earendil-works/pi-agent-core'
import type { ImageContent, Model } from '@earendil-works/pi-ai'
import type { TSchema } from 'typebox'
import { AGENT_TOOLS, toolsForMode } from './tools'
import type { AgentCanvasStore, AgentToolResult } from './tools'
import { resolveToolCall, gatedKindOf } from './policy'
import type { AgentMode } from './policy'
import { getActiveSkillScope } from './skills'
import { createAgentModel, agentStreamFn } from './provider'
import type { AgentImageAttachment } from './attachments'

/** 附件图片类型从 attachments 单源再导出（内核/工具/store 共用） */
export type { AgentImageAttachment }

/** 单轮对话回合上限（一轮 = 一次 LLM 调用） */
const MAX_TURNS = 40

/** 零值 usage（上游缺 usage 块时兜底，形状与 pi-ai Usage 一致） */
const EMPTY_USAGE = {
  input: 0,
  output: 0,
  cacheRead: 0,
  cacheWrite: 0,
  totalTokens: 0,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
}

export type KernelEvent =
  | { type: 'thinking'; active: boolean }
  | { type: 'round_start' }
  | { type: 'text_delta'; delta: string }
  | { type: 'tool_start'; callId: string; tool: string; args: Record<string, unknown> }
  | { type: 'tool_end'; callId: string; tool: string; ok: boolean; result: string }
  | { type: 'tool_rejected'; callId: string; tool: string; reason: string }
  | { type: 'confirm_request'; kind: 'stage'; tool: string; args: Record<string, unknown>; stage: string; summary: string; source?: string }
  | { type: 'done'; stopped: boolean; error: string | null }

/** 宿主自带工具（chat 宿主等）：结构与画布 AgentTool 对齐，execute 的 ctx 由 deps.toolContext 提供；
 *  callId 为机制层工具调用 id（子代理进度定位用） */
export interface HostTool {
  name: string
  description: string
  parameters: TSchema
  execute(args: Record<string, unknown>, ctx: unknown, callId?: string): AgentToolResult | Promise<AgentToolResult>
}

export interface AgentKernelDeps {
  /** 工具执行与阶段门 kind 推断所需的画布 store（画布宿主必传；自带工具组的宿主可省略） */
  getCanvas?: () => AgentCanvasStore
  /** 档位实时读取（画布宿主三档权限；宿主工具组模式可省略） */
  getMode?: () => AgentMode
  systemPrompt: string
  getAuthToken: () => Promise<string | null>
  /** LLM 流函数（缺省用 provider 适配；测试注入假流） */
  streamFn?: StreamFn
  /** 单回合 LLM 调用上限（缺省 40；子代理实例传更小值） */
  maxTurns?: number
  /** 宿主自带工具组：提供则不挂画布工具与阶段门策略（技能围栏仍生效，其余放行） */
  tools?: HostTool[]
  /** 宿主工具执行上下文（缺省用画布 store） */
  toolContext?: unknown
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

/** 守卫过滤有效图片附件（脏数据静默剔除，不让单张坏图拖垮整条消息） */
function validImages(images: AgentImageAttachment[] | undefined): AgentImageAttachment[] {
  return (images ?? []).filter((i) => typeof i.data === 'string' && i.data.length > 0 && typeof i.mimeType === 'string' && i.mimeType.startsWith('image/'))
}

function toPiImages(images: AgentImageAttachment[] | undefined): ImageContent[] | undefined {
  const list = validImages(images)
  return list.length ? list.map((i) => ({ type: 'image' as const, data: i.data, mimeType: i.mimeType })) : undefined
}

interface PendingConfirm {
  tool: string
  args: Record<string, unknown>
  stage: string
  summary: string
  resolve: (approved: boolean) => void
}

export class AgentKernel {
  private agent: Agent
  private listeners: Array<(e: KernelEvent) => void> = []
  /** 挂起确认 FIFO 队列：并行子代理同时撞门时按序唤醒，确认卡逐张展示 */
  private pendingQueue: PendingConfirm[] = []
  private stopRequested = false
  private lastError: string | null = null
  private turnCount = 0
  private gatedKinds: string[] = []
  private maxTurns: number
  /** 活跃子代理内核（运行期间注册）；requestStop 时全部一并中止 */
  private children = new Set<AgentKernel>()

  constructor(private deps: AgentKernelDeps) {
    this.maxTurns = deps.maxTurns ?? MAX_TURNS
    this.agent = new Agent({
      streamFn: deps.streamFn ?? agentStreamFn,
      initialState: {
        systemPrompt: deps.systemPrompt,
        model: createAgentModel(),
        messages: [],
        tools: deps.tools ? this.wrapTools(deps.tools) : this.piTools(deps.getMode?.() ?? 'confirm'),
      },
      getApiKey: async () => (await deps.getAuthToken()) || 'anonymous',
      toolExecution: 'parallel',
      // beforeToolCall 始终挂载：先做技能工具围栏（两种宿主生效），画布宿主再走 policy 档位策略
      beforeToolCall: (ctx) => this.handleBeforeToolCall(ctx),
      // 阶段门拒绝/阶段汇报暂停/停止/回合上限：当前回合收尾后不再发起下一次 LLM 调用
      shouldStopAfterTurn: () => this.stopRequested,
    })
    this.agent.subscribe((event) => this.handleEvent(event))
  }

  subscribe(listener: (e: KernelEvent) => void): () => void {
    this.listeners.push(listener)
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener)
    }
  }

  private emit(e: KernelEvent): void {
    for (const l of this.listeners) l(e)
  }

  /** 注册子代理内核（运行期间），返回注销函数；requestStop 时全部子代理一并中止 */
  registerChild(child: AgentKernel): () => void {
    this.children.add(child)
    return () => {
      this.children.delete(child)
    }
  }

  /** 档位切换：同步机制层工具清单（只读档仅挂 read 组；策略层在 beforeToolCall 兜底）。宿主工具组模式无档位，no-op */
  setMode(mode: AgentMode): void {
    if (!this.deps.tools) this.agent.state.tools = this.piTools(mode)
  }

  /** 会话建立时刷新系统提示（技能清单快照；对齐 setMode 的状态直改模式） */
  setSystemPrompt(prompt: string): void {
    this.agent.state.systemPrompt = prompt
  }

  /** 切换对话模型（下一回合生效；id 为后端 chat 注册表内的模型 id） */
  setModel(model: Model<'openai-completions'>): void {
    this.agent.state.model = model
  }

  /** 当前对话模型 id（面板模型胶囊展示用） */
  get currentModelId(): string {
    return this.agent.state.model.id
  }

  /** 工具 → 机制层工具：ok:false 转 throw（机制层惯例：工具抛错而非返回错误内容）；ctx 由宿主提供 */
  private wrapTools(tools: HostTool[]): PiAgentTool[] {
    return tools.map((tool) => ({
      name: tool.name,
      label: tool.name,
      description: tool.description,
      parameters: tool.parameters,
      execute: async (toolCallId: string, params: unknown) => {
        const args = isRecord(params) ? params : {}
        const r = await tool.execute(args, this.deps.toolContext ?? this.deps.getCanvas?.(), toolCallId)
        if (!r.ok) throw new Error(r.error || '工具执行失败')
        const imageBlocks: ImageContent[] = validImages(r.images).map((i) => ({ type: 'image' as const, data: i.data, mimeType: i.mimeType }))
        return {
          content: [{ type: 'text' as const, text: JSON.stringify(r.data ?? {}) }, ...imageBlocks],
          details: r.data ?? {},
        }
      },
    }))
  }

  private piTools(mode: AgentMode): PiAgentTool[] {
    return this.wrapTools(toolsForMode(mode))
  }

  private async handleBeforeToolCall(ctx: BeforeToolCallContext): Promise<BeforeToolCallResult | undefined> {
    const toolName = ctx.toolCall.name
    const args = isRecord(ctx.args) ? ctx.args : {}
    // 技能工具围栏：allowed_tools 非空的技能加载后，白名单外工具一律拒绝（画布/对话/子代理宿主都生效）
    const scope = getActiveSkillScope()
    if (scope && !scope.has(toolName)) {
      const reason = `当前技能限定了可用工具白名单，禁止调用 ${toolName}（允许：${[...scope].join('、')}）`
      this.emit({ type: 'tool_rejected', callId: ctx.toolCall.id, tool: toolName, reason })
      return { block: true, reason }
    }
    const decision = await this.authorizeTool(toolName, args)
    if (decision.allowed) return undefined
    this.emit({ type: 'tool_rejected', callId: ctx.toolCall.id, tool: toolName, reason: decision.reason ?? '工具调用被拒绝' })
    return { block: true, reason: decision.reason, terminate: decision.stop }
  }

  /** 门决策唯一入口：父工具循环（beforeToolCall）与子代理门请求共用。
   *  宿主工具组模式无档位策略（围栏由各宿主 beforeToolCall 负责）；画布宿主走 policy 三档，
   *  阶段门确认卡入 FIFO 队列，confirm 按序唤醒。source 标记来自子任务的请求，确认卡据此展示来源。 */
  async authorizeTool(toolName: string, args: Record<string, unknown>, source?: string): Promise<{ allowed: boolean; reason?: string; stop: boolean }> {
    if (this.deps.tools) return { allowed: true, stop: false }
    const tool = AGENT_TOOLS.find((t) => t.name === toolName)
    const panelId = typeof args.panel_id === 'string' ? args.panel_id : ''
    const panelType = panelId ? this.deps.getCanvas?.().panels.find((p) => p.id === panelId)?.type : undefined

    const decision = resolveToolCall({
      mode: this.deps.getMode?.() ?? 'confirm',
      toolName,
      toolGroup: tool?.group ?? 'write',
      args,
      gatedKinds: this.gatedKinds,
      panelType,
    })

    if (decision.action === 'allow') {
      this.recordGatedKind(toolName, args, panelType)
      return { allowed: true, stop: false }
    }
    if (decision.action === 'reject') {
      if (decision.stop) this.stopRequested = true
      return { allowed: false, reason: decision.reason, stop: decision.stop }
    }

    // 阶段门/阶段汇报：发确认卡片事件并入队等用户确认；confirm(false) 或 requestStop 唤醒
    this.emit({
      type: 'confirm_request',
      kind: decision.kind,
      tool: toolName,
      args,
      stage: decision.stage,
      summary: decision.summary,
      source,
    })
    const approved = await new Promise<boolean>((resolve) => {
      this.pendingQueue.push({ tool: toolName, args, stage: decision.stage, summary: decision.summary, resolve })
    })
    if (!approved) {
      this.stopRequested = true
      return { allowed: false, reason: decision.onReject, stop: true }
    }
    this.recordGatedKind(toolName, args, panelType)
    return { allowed: true, stop: false }
  }

  private recordGatedKind(toolName: string, args: Record<string, unknown>, panelType: string | undefined): void {
    const kind = gatedKindOf(toolName, args, panelType)
    if (kind && !this.gatedKinds.includes(kind)) this.gatedKinds.push(kind)
  }

  private handleEvent(event: AgentEvent): void {
    switch (event.type) {
      case 'agent_start':
        break
      case 'turn_start':
        this.turnCount++
        // LLM 回合开始（含请求 latency 期）：点亮"思考中"指示，UI 据此给出工作反馈
        this.emit({ type: 'thinking', active: true })
        if (this.turnCount > this.maxTurns) {
          this.lastError = `已达单轮工具调用上限（${this.maxTurns} 轮），请拆分任务后重试`
          this.stopRequested = true
          this.agent.abort()
        }
        break
      case 'message_start':
        // 机制层对用户消息/assistant/toolResult 都发 message_start；仅 assistant 开启新时间线回合
        if (isRecord(event.message) && event.message.role === 'assistant') {
          this.emit({ type: 'round_start' })
        }
        break
      case 'message_update':
        // 正文增量进时间线；思考流点亮指示（不透传思考文本）
        if (event.assistantMessageEvent.type === 'text_delta') {
          this.emit({ type: 'text_delta', delta: event.assistantMessageEvent.delta })
        } else if (event.assistantMessageEvent.type === 'thinking_delta') {
          this.emit({ type: 'thinking', active: true })
        }
        break
      case 'message_end': {
        // LLM 调用失败：机制层以 stopReason 'error' 收尾（不抛异常），此处转内核错误
        const m = event.message
        if (isRecord(m) && m.role === 'assistant' && m.stopReason === 'error') {
          this.lastError = typeof m.errorMessage === 'string' && m.errorMessage ? m.errorMessage : 'LLM 调用失败'
        }
        this.normalizeContext()
        break
      }
      case 'tool_execution_start':
        this.emit({ type: 'tool_start', callId: event.toolCallId, tool: event.toolName, args: isRecord(event.args) ? event.args : {} })
        break
      case 'tool_execution_end': {
        const r = event.result
        const text =
          isRecord(r) && Array.isArray(r.content) && isRecord(r.content[0]) && typeof r.content[0].text === 'string'
            ? r.content[0].text
            : ''
        this.emit({ type: 'tool_end', callId: event.toolCallId, tool: event.toolName, ok: !event.isError, result: text })
        break
      }
      default:
        break
    }
  }

  /** 用户确认（阶段门/阶段汇报卡片）：按 FIFO 唤醒队首；true 放行、false 拒绝并停止 */
  confirm(approved: boolean): void {
    this.pendingQueue.shift()?.resolve(approved)
  }

  /** 停止：挂起确认（含子代理门请求）全部按拒绝放行，中止本内核与全部子代理；生成中任务由 taskQueue 转后台继续 */
  requestStop(): void {
    if (!this.agent.state.isStreaming && this.pendingQueue.length === 0) return
    this.stopRequested = true
    for (const p of this.pendingQueue) p.resolve(false)
    this.pendingQueue = []
    for (const child of this.children) child.requestStop()
    this.agent.abort()
  }

  /** 用户消息：text 必填、images 可选（裸 base64，prompt 原生第二参数） */
  async send(text: string, images?: AgentImageAttachment[]): Promise<void> {
    // 机制层异常路径可能把 isStreaming 卡在 true（pi 的复位不在 finally 里）：
    // 静默 return 会让该会话后续每条消息无声消失，abort 走机制层正式复位后正常发起
    if (this.agent.state.isStreaming) this.agent.abort()
    this.stopRequested = false
    this.lastError = null
    this.turnCount = 0
    this.gatedKinds = []
    this.pendingQueue = []
    try {
      await this.agent.prompt(text, toPiImages(images))
    } catch (e) {
      this.lastError = e instanceof Error ? e.message : String(e)
    } finally {
      this.normalizeContext()
      this.emit({ type: 'done', stopped: this.stopRequested, error: this.lastError })
    }
  }

  /** 持久化：内核消息数组（LLM 上下文唯一来源，恢复时直接注入并重建时间线） */
  serializeState(): unknown {
    return { messages: JSON.parse(JSON.stringify(this.agent.state.messages)) }
  }

  /** 会话恢复：守卫解析失败返回 false（调用方清空会话重新开始） */
  restore(data: unknown): boolean {
    if (!isRecord(data) || !Array.isArray(data.messages)) return false
    this.agent.state.messages = data.messages
    this.normalizeContext()
    return true
  }

  /** 上下文归一化：上游偶发不回传 usage 块、历史版本落库过字符串内容的 assistant 消息——
   *  任一缺失都会让机制层的上下文估算/消息转换在下一回合抛 TypeError（如读 usage.totalTokens、
   *  content.length），整个会话从下一跳起静默停摆。restore/message_end/send 收尾三处兜底。 */
  private normalizeContext(): void {
    for (const m of this.agent.state.messages) {
      if (!m || typeof m !== 'object') continue
      if (m.role === 'assistant') {
        if (typeof m.content === 'string') {
          m.content = [{ type: 'text', text: m.content }]
        }
        if (!m.stopReason) m.stopReason = 'stop'
        if (!m.usage) m.usage = { ...EMPTY_USAGE }
      } else if (m.role === 'user' && typeof m.content === 'string') {
        // user 字符串内容 pi-ai 能消费，保持原样
      }
    }
  }

  reset(): void {
    this.agent.reset()
    for (const p of this.pendingQueue) p.resolve(false)
    this.pendingQueue = []
    this.stopRequested = false
    this.lastError = null
    this.turnCount = 0
    this.gatedKinds = []
  }
}

// =====================================================
// 时间线重建：从内核消息数组恢复 UI 时间线（会话恢复用，守卫式解析）
// =====================================================

export interface KernelTimelineStep {
  callId: string
  tool: string
  args: Record<string, unknown>
  status: 'pending' | 'done' | 'error'
  result: string | null
}

export interface KernelTimelineMessage {
  role: 'user' | 'assistant'
  content: string
  /** 用户消息附图（会话恢复时还原缩略图；assistant 恒为空） */
  images?: AgentImageAttachment[]
  steps: KernelTimelineStep[]
  createdAt: string
}

function blockText(blocks: unknown): string {
  if (!Array.isArray(blocks)) return ''
  return blocks
    .filter(isRecord)
    .filter((b) => b.type === 'text' && typeof b.text === 'string')
    .map((b) => b.text as string)
    .join('')
}

function tsToIso(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? new Date(v).toISOString() : new Date().toISOString()
}

/** 用户消息 content 数组里的 image 块 → 附件（守卫式，缺字段丢弃） */
function userImageBlocks(blocks: unknown): AgentImageAttachment[] | undefined {
  if (!Array.isArray(blocks)) return undefined
  const out: AgentImageAttachment[] = []
  for (const b of blocks) {
    if (!isRecord(b) || b.type !== 'image') continue
    const data = typeof b.data === 'string' ? b.data : ''
    const mimeType = typeof b.mimeType === 'string' ? b.mimeType : ''
    if (data && mimeType) out.push({ data, mimeType })
  }
  return out.length ? out : undefined
}

export function rebuildTimeline(raw: unknown): KernelTimelineMessage[] | null {
  if (!isRecord(raw) || !Array.isArray(raw.messages)) return null
  const out: KernelTimelineMessage[] = []
  /** toolCallId → 步骤（同一条 assistant 消息内） */
  let currentSteps: KernelTimelineStep[] = []
  for (const m of raw.messages) {
    if (!isRecord(m)) continue
    if (m.role === 'user') {
      const content = typeof m.content === 'string' ? m.content : blockText(m.content)
      const images = typeof m.content === 'string' ? undefined : userImageBlocks(m.content)
      out.push({ role: 'user', content, images, steps: [], createdAt: tsToIso(m.timestamp) })
      continue
    }
    if (m.role === 'assistant') {
      currentSteps = []
      const content = blockText(m.content)
      if (Array.isArray(m.content)) {
        for (const b of m.content.filter(isRecord)) {
          if (b.type === 'toolCall' && typeof b.id === 'string' && typeof b.name === 'string') {
            currentSteps.push({
              callId: b.id,
              tool: b.name,
              args: isRecord(b.arguments) ? b.arguments : {},
              status: 'pending',
              result: null,
            })
          }
        }
      }
      out.push({ role: 'assistant', content, steps: currentSteps, createdAt: tsToIso(m.timestamp) })
      continue
    }
    if (m.role === 'toolResult') {
      // 回填到对应步骤：多个 toolCall 的结果按 callId 匹配（可能跨 assistant 消息，全局找）
      const callId = typeof m.toolCallId === 'string' ? m.toolCallId : ''
      const step = [...out].reverse().flatMap((x) => x.steps).find((s) => s.callId === callId)
      if (step) {
        step.status = m.isError === true ? 'error' : 'done'
        step.result = blockText(m.content) || null
      }
    }
  }
  return out
}
