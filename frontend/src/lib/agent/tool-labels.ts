/* =====================================================
 * 工具步骤标签注册表（用户可读文案单一来源）
 *
 * - 两宿主（画布面板/对话列表）与确认卡、子任务进度统一走 toolStepLabel，
 *   不再各自维护 tool → 文案 switch（原 CanvasAgentPanel.stepAction /
 *   stores/chat.toolLabel 已收敛至此）
 * - key 复用 i18n agent.act*；带参数的富文案由 detail 返回完整最终文案
 * - mcp__{serverId}__{tool} 走通用兜底模板（短名 = 末段 __ 之后）；
 *   未注册工具兜底返回原始名，未来新工具零配置可用
 * ===================================================== */

import { t } from '@/i18n'

/** 标签格式化参数：nodeNameOf 由画布宿主注入（panel_id → 节点名） */
export interface ToolLabelOpts {
  nodeNameOf?: (ref: unknown) => string
}

interface ToolLabelEntry {
  key: string
  /** 缺省时用 t(key)；定义时返回完整最终文案 */
  detail?: (args: Record<string, unknown>, opts: ToolLabelOpts) => string
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function labelJoiner(): string {
  return t('agent.labelJoiner')
}

/** 节点引用 → 显示名：宿主注入解析回调；无回调或非字符串时原样/空 */
function nodeName(ref: unknown, opts: ToolLabelOpts): string {
  if (typeof ref !== 'string' || !ref) return ''
  return opts.nodeNameOf ? opts.nodeNameOf(ref) : ref
}

/** 基础文案 + 可选「：名称」后缀 */
function withName(label: string, name: string): string {
  return name ? `${label}${labelJoiner()}${name}` : label
}

/** agent_apply_ops：按操作类型计数拆解（新增节点 ×2、连线 ×1…） */
function applyOpsDetail(args: Record<string, unknown>): string {
  const ops = Array.isArray(args.ops) ? args.ops : []
  const count = (kind: string) => ops.filter((o) => isRecord(o) && o.op === kind).length
  const parts: string[] = []
  if (count('add_panel')) parts.push(`${t('agent.opsAddPanel')} ×${count('add_panel')}`)
  if (count('add_connection')) parts.push(`${t('agent.opsConnect')} ×${count('add_connection')}`)
  if (count('update_panel')) parts.push(`${t('agent.opsUpdatePanel')} ×${count('update_panel')}`)
  if (count('delete_panel') || count('delete_connection')) parts.push(`${t('agent.opsDelete')} ×${count('delete_panel') + count('delete_connection')}`)
  return parts.length ? `${t('agent.actApplyOps')}${labelJoiner()}${parts.join(t('agent.opsJoiner'))}` : t('agent.actApplyOps')
}

/** agent_run_generation：按 kind 选文案（asset 归入生成图片，与画布层原口径一致） */
function runGenerationDetail(args: Record<string, unknown>, opts: ToolLabelOpts): string {
  const kind = typeof args.kind === 'string' ? args.kind : ''
  const label = kind === 'video' ? t('agent.actGenVideo') : kind === 'compose' ? t('agent.actCompose') : t('agent.actGenImage')
  return withName(label, nodeName(args.panel_id, opts))
}

/** 完整性测试消费：注册表必须覆盖 AGENT_TOOLS ∪ CHAT_TOOLS 全部工具名 */
export const TOOL_LABELS: Record<string, ToolLabelEntry> = {
  // 画布宿主（tools.ts AGENT_TOOLS）
  agent_get_state: { key: 'agent.actGetState' },
  agent_get_selection: { key: 'agent.actGetSelection' },
  agent_get_models: { key: 'agent.actGetModels' },
  agent_select: { key: 'agent.actSelect', detail: (a, o) => withName(t('agent.actSelect'), nodeName(a.panel_id, o)) },
  agent_read_image: { key: 'agent.actReadImage', detail: (a, o) => withName(t('agent.actReadImage'), nodeName(a.panel_id, o)) },
  agent_create_text_node: { key: 'agent.actCreateText', detail: (a) => withName(t('agent.actCreateText'), typeof a.name === 'string' ? a.name : '') },
  agent_apply_ops: { key: 'agent.actApplyOps', detail: applyOpsDetail },
  agent_run_generation: { key: 'agent.actGenImage', detail: runGenerationDetail },
  agent_stage_review: { key: 'agent.actStageReview', detail: (a) => withName(t('agent.actStageReview'), typeof a.stage === 'string' ? a.stage : '') },
  agent_load_skill: { key: 'agent.actLoadSkill', detail: (a) => withName(t('agent.actLoadSkill'), typeof a.name === 'string' ? a.name : '') },
  agent_read_skill_file: { key: 'agent.actReadSkillFile' },
  agent_save_skill: { key: 'agent.actSaveSkill' },
  agent_delegate: { key: 'agent.actDelegate' },
  storyboard_set_style: { key: 'agent.actSetStyle' },
  storyboard_list_styles: { key: 'agent.actListStyles' },
  storyboard_extract_entities: { key: 'agent.actExtractEntities' },
  storyboard_split: { key: 'agent.actSplitStoryboard' },
  // 对话宿主（chat-tools.ts CHAT_TOOLS）
  generate_image: { key: 'agent.actGenImage' },
  generate_video: { key: 'agent.actGenVideo' },
}

/** mcp__{serverId}__{tool} 的短名（末段；非 mcp 工具原样返回） */
export function mcpShortName(tool: string): string {
  return tool.startsWith('mcp__') ? tool.slice(tool.lastIndexOf('__') + 2) : tool
}

/** 工具步骤的用户可读标签：注册表 → detail/t(key)；mcp 兜底模板；未知兜底原始名 */
export function toolStepLabel(tool: string, args?: Record<string, unknown>, opts?: ToolLabelOpts): string {
  if (tool.startsWith('mcp__')) return t('agent.mcpToolLabel', { tool: mcpShortName(tool) })
  const entry = TOOL_LABELS[tool]
  if (!entry) return tool
  return entry.detail ? entry.detail(args ?? {}, opts ?? {}) : t(entry.key)
}
