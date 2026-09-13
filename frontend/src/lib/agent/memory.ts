/* =====================================================
 * 用户记忆库（单一记忆库方案）
 *
 * - 偏好 = 用户 MCP 记忆图谱里「创作偏好」实体的 observations（"类别：内容"）
 * - 写入由 Agent 按系统提示记忆守则用现成 memory 工具完成；本模块只负责
 *   会话建立时拉取摘要拼系统提示段（免查找注入）与管理接口封装
 * - 未安装/故障静默降级为空段，不阻断会话
 * ===================================================== */

import { fetchMemorySummary } from '@/api/mcp'

/** 记忆状态（面板记忆胶囊 + 系统提示注入共用一次拉取） */
export interface MemoryState {
  available: boolean
  preferences: string[]
  /** 系统提示注入段（含记忆守则；不可用/未启用时为空串） */
  section: string
}

function buildSection(preferences: string[]): string {
  const lines = [
    '## 用户创作偏好（记忆库）',
    '',
    ...(preferences.length ? preferences.map((p) => `- ${p}`) : ['（暂无记录）']),
    '',
    '创作时优先遵循以上偏好。',
    '当对话中确认到用户稳定的创作偏好（画幅/风格/模型/题材/节奏等）时，主动调用记忆工具 add_observations 记入「创作偏好」实体：格式「类别：内容」，一条一条记录，不重复已有条目；用户明确说"不要再记"时停止记录。',
  ]
  return lines.join('\n')
}

/** 拉取记忆状态并组装注入段；不可用/失败返回 available:false 空段 */
export async function fetchMemoryState(): Promise<MemoryState> {
  try {
    const summary = await fetchMemorySummary()
    if (!summary.available) return { available: false, preferences: [], section: '' }
    return { available: true, preferences: summary.preferences ?? [], section: buildSection(summary.preferences ?? []) }
  } catch {
    return { available: false, preferences: [], section: '' }
  }
}
