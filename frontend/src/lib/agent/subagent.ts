/* =====================================================
 * 子代理执行器（agent_delegate）
 *
 * - 复用 AgentKernel 作受限子运行时：宿主工具组模式（无档位策略）+
 *   门请求前移父内核 authorizeTool（readonly 拒 / confirm 过门 / auto 直通，无旁路）
 * - 硬上限：并发 ≤3（信号量排队）、子回合 ≤20、摘要 ≤4000 字符
 * - 上下文隔离：子消息不进父上下文，父只收结论摘要
 * - 禁递归：子工具清单剔除 agent_delegate，tools_allowed 白名单亦不允许
 * ===================================================== */

import type { AgentKernel, HostTool } from './kernel'
import type { AgentToolResult } from './tools'

/** 子代理硬上限 */
const SUB_MAX_TURNS = 20
const SUB_SUMMARY_MAX_CHARS = 4000
const SUB_CONCURRENCY = 3

export interface DelegateInput {
  task: string
  context?: string
  tools_allowed?: string[]
}

/** 子代理宿主（由工具执行器从父内核组装） */
export interface SubagentHost {
  /** 父内核：门请求经 authorizeTool 前移；子内核经 createChildKernel 创建（自动注册停止传导） */
  parent: AgentKernel
  /** 子代理可用工具组（父宿主工具组；delegate 剔除与 tools_allowed 收窄在执行器内做） */
  getTools: () => HostTool[]
  /** 进度上报（store 更新父时间线步骤行） */
  onProgress?: (text: string) => void
  /** 父流程已请求停止（子工具直接拒执行，防僵尸子循环） */
  isStopped?: () => boolean
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

// ---------- 并发信号量（≤3，超出排队） ----------

let activeChildren = 0
const slotWaiters: Array<() => void> = []

async function acquireSlot(): Promise<() => void> {
  if (activeChildren >= SUB_CONCURRENCY) {
    await new Promise<void>((resolve) => slotWaiters.push(resolve))
  }
  activeChildren++
  let released = false
  return () => {
    if (released) return
    released = true
    activeChildren--
    slotWaiters.shift()?.()
  }
}

// ---------- 子任务组装 ----------

function buildSubPrompt(context?: string): string {
  const lines = [
    '你是任务执行子代理，独立完成主代理委派的单一子任务，过程中不与用户交互。',
    '完成后在最终回复中输出结论摘要：结果、关键数据、未尽事项，控制在 1000 字以内。',
  ]
  if (context) lines.push(`背景材料：\n${context}`)
  return lines.join('\n\n')
}

/** 子工具包装：执行前经父内核门决策（readonly 拒 / confirm 过门 / auto 直通） */
function gateChildTool(tool: HostTool, host: SubagentHost, source: string): HostTool {
  return {
    ...tool,
    execute: async (args, ctx, callId) => {
      if (host.isStopped?.()) return { ok: false, error: '流程已停止，子任务中止执行' }
      const decision = await host.parent.authorizeTool(tool.name, args, source)
      if (!decision.allowed) return { ok: false, error: decision.reason ?? '工具调用被拒绝' }
      return tool.execute(args, ctx, callId)
    },
  }
}

/** 取子内核最后一条 assistant 文本作结论摘要（守卫式解析） */
function lastAssistantText(child: AgentKernel): string {
  const state = child.serializeState()
  if (!isRecord(state) || !Array.isArray(state.messages)) return ''
  for (let i = state.messages.length - 1; i >= 0; i--) {
    const m = state.messages[i]
    if (!isRecord(m) || m.role !== 'assistant' || !Array.isArray(m.content)) continue
    const text = m.content
      .filter(isRecord)
      .filter((b) => b.type === 'text' && typeof b.text === 'string')
      .map((b) => (typeof b.text === 'string' ? b.text : ''))
      .join('')
    if (text) return text
  }
  return ''
}

/** 从父内核组装子代理宿主（isStopped 缺省读父内核停止标记） */
export function subagentHostFromParent(
  parent: AgentKernel,
  opts: { tools: HostTool[]; onProgress?: (text: string) => void; isStopped?: () => boolean },
): SubagentHost {
  return {
    parent,
    getTools: () => opts.tools,
    onProgress: opts.onProgress,
    isStopped: opts.isStopped ?? (() => parent.isStopRequested),
  }
}

/** 运行子代理：独立上下文跑到底，返回结论摘要（data.summary）与子回合数（data.turns） */
export async function runSubagent(input: DelegateInput, host: SubagentHost): Promise<AgentToolResult> {
  const task = (input.task || '').trim()
  if (!task) return { ok: false, error: 'task 必填' }
  if (input.tools_allowed?.includes('agent_delegate')) {
    return { ok: false, error: '子任务工具白名单不允许包含 agent_delegate（禁止嵌套派生）' }
  }
  const source = `子任务:${task.slice(0, 12)}`
  const release = await acquireSlot()
  try {
    const tools = host
      .getTools()
      .filter((t) => t.name !== 'agent_delegate')
      .filter((t) => !input.tools_allowed?.length || input.tools_allowed.includes(t.name))
      .map((t) => gateChildTool(t, host, source))
    const { kernel: child, unregister } = host.parent.createChildKernel({
      systemPrompt: buildSubPrompt(input.context),
      maxTurns: SUB_MAX_TURNS,
      tools,
    })

    let round = 0
    let currentTool = ''
    let stopped = false
    let childError: string | null = null
    const report = () => host.onProgress?.(`子任务运行中 · 第 ${Math.max(round, 1)} 回合${currentTool ? ` · ${currentTool}` : ''}`)
    const off = child.subscribe((e) => {
      if (e.type === 'round_start') {
        round++
        report()
      } else if (e.type === 'tool_start') {
        currentTool = e.tool
        report()
      } else if (e.type === 'tool_end') {
        currentTool = ''
        report()
      } else if (e.type === 'done') {
        stopped = e.stopped
        childError = e.error
      }
    })
    try {
      await child.send(task)
    } finally {
      off()
      unregister()
    }

    const summary = lastAssistantText(child).trim()
    if (!summary) {
      if (childError) return { ok: false, error: `子任务失败：${childError}` }
      return { ok: false, error: stopped ? '子任务已被用户停止' : '子任务未产出结论摘要' }
    }
    const note = stopped ? '（用户已停止，摘要可能不完整）' : childError ? '（子任务中途出错，摘要可能不完整）' : ''
    const truncated = summary.length > SUB_SUMMARY_MAX_CHARS ? `${summary.slice(0, SUB_SUMMARY_MAX_CHARS)}…（超限截断）` : summary
    return { ok: true, data: { summary: truncated + note, turns: Math.max(round, 1) } }
  } finally {
    release()
  }
}
