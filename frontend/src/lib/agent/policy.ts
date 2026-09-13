/* =====================================================
 * 画布 Agent 策略层（纯函数，UI 无关）
 *
 * - 三档权限（readonly/confirm/auto）与阶段门判定
 * - 从内核循环拆出：可独立单测；未来 MCP 桥复用同一套策略
 * ===================================================== */

export type AgentMode = 'readonly' | 'confirm' | 'auto'

/** 阶段顺序表：阶段门通过后机械提示下一阶段，避免 LLM 把"满意"误解为任务结束 */
export const STAGE_FLOW: Array<{ key: string; next: string | null }> = [
  { key: '剧本', next: '实体设定' },
  { key: '实体设定', next: '分镜提示词' },
  { key: '分镜提示词', next: '分镜图' },
  { key: '分镜图', next: '分段视频' },
  { key: '分段视频', next: '成片合成' },
  { key: '成片', next: null },
]

export function stageApprovedMessage(stage: string): string {
  const hit = STAGE_FLOW.find((s) => stage.includes(s.key))
  if (!hit) return '用户确认满意，继续标准管线下一阶段；若成片已完成则可总结收尾'
  if (hit.next === null) return '用户确认满意。成片已完成，全部阶段结束，可向用户总结成果'
  return `用户确认满意（仅验收当前阶段）。请立即执行下一阶段：${hit.next}`
}

/** 生成阶段归类：与 agent_run_generation 的 kind 一致（args 显式优先，缺省按节点类型推断；asset=实体设定图） */
export type GenerationKind = 'image' | 'video' | 'compose' | 'asset'

export function inferGenerationKind(argKind: string, panelType: string | undefined): GenerationKind {
  if (argKind === 'video' || argKind === 'image' || argKind === 'compose' || argKind === 'asset') return argKind
  return panelType === 'video' ? 'video' : panelType === 'compose' ? 'compose' : 'image'
}

export function stageNameOfKind(kind: GenerationKind): string {
  return kind === 'asset' ? '实体设定' : kind === 'image' ? '分镜图' : kind === 'video' ? '分段视频' : '成片合成'
}

export type PolicyDecision =
  | { action: 'allow' }
  /** 过门：等用户确认；拒绝时回填 onReject 并停止流程交还用户（stage=阶段卡，tool=MCP 工具卡） */
  | { action: 'gate'; kind: 'stage' | 'tool'; stage: string; summary: string; onReject: string }
  /** 拒绝：reason 回填 LLM；stop=true 时内核强制终止本回合 */
  | { action: 'reject'; reason: string; stop: boolean }

export interface PolicyInput {
  mode: AgentMode
  toolName: string
  /** mcp 组（mcp__ 前缀约定，见 kernel.authorizeTool）：副作用不可预测，confirm 档每工具首次过门 */
  toolGroup: 'read' | 'write' | 'generation' | 'mcp'
  args: Record<string, unknown>
  /** 本回合已过门的生成阶段（image/video/compose）与 MCP 工具名 */
  gatedKinds: string[]
  /** args.panel_id 对应节点类型（kind 推断用，由内核注入） */
  panelType: string | undefined
}

const STAGE_REVIEW_PAUSE_MESSAGE =
  '用户暂停了流程（对当前阶段不满意或想调整），停止后续执行，等用户给出调整意见后再继续'

export function resolveToolCall(input: PolicyInput): PolicyDecision {
  const { mode, toolName, toolGroup, args, gatedKinds, panelType } = input

  // 只读档：read 组之外全部拒绝（不停止回合，由 LLM 向用户说明）
  if (mode === 'readonly') {
    if (toolGroup === 'read') return { action: 'allow' }
    return { action: 'reject', reason: '当前为只读模式，不允许执行写操作或生成', stop: false }
  }

  // 阶段汇报工具：需确认档转用户审阅（gate），自动档放行（execute 兜底直通）
  if (toolName === 'agent_stage_review') {
    if (mode === 'auto') return { action: 'allow' }
    const stage = typeof args.stage === 'string' ? args.stage : ''
    const summary = typeof args.summary === 'string' ? args.summary : ''
    return { action: 'gate', kind: 'stage', stage, summary, onReject: STAGE_REVIEW_PAUSE_MESSAGE }
  }

  // 需确认档内核强制关卡：每种生成阶段首次执行前必须过门，不依赖 LLM 自觉调用阶段汇报
  if (toolName === 'agent_run_generation' && mode === 'confirm') {
    const kind = inferGenerationKind(typeof args.kind === 'string' ? args.kind : '', panelType)
    if (!gatedKinds.includes(kind)) {
      const stageName = stageNameOfKind(kind)
      return {
        action: 'gate',
        kind: 'stage',
        stage: stageName,
        summary: `Agent 即将开始「${stageName}」阶段的生成，请确认`,
        onReject: `用户不同意进入「${stageName}」生成阶段，流程已停止，等用户调整后再试`,
      }
    }
  }

  // 需确认档 MCP 工具关卡：每个外部工具首次执行前必须过门（gatedKinds 记工具名本身），不依赖 LLM 自觉
  if (toolGroup === 'mcp' && mode === 'confirm' && !gatedKinds.includes(toolName)) {
    return {
      action: 'gate',
      kind: 'tool',
      stage: toolName,
      summary: `Agent 即将调用外部 MCP 工具「${toolName}」，请确认`,
      onReject: `用户未允许调用 MCP 工具 ${toolName}，流程已停止，等用户调整后再试`,
    }
  }

  return { action: 'allow' }
}

/** 阶段门放行后应记录的 kind（MCP 工具记工具名本身，生成类记 kind，其余返回 null） */
export function gatedKindOf(toolName: string, args: Record<string, unknown>, panelType: string | undefined): string | null {
  if (toolName.startsWith('mcp__')) return toolName
  if (toolName !== 'agent_run_generation') return null
  return inferGenerationKind(typeof args.kind === 'string' ? args.kind : '', panelType)
}
