/* =====================================================
 * 画布分组工具
 * - 组框边界实时由成员包络计算（组无独立几何）
 * - 折叠胶囊几何固定，供组层与连线层共用锚点
 * - 资产类别推断（人物/物品/场景/分镜/脚本/生成视频…）
 * ===================================================== */

import type { CanvasGroup, CanvasPanel } from '@/stores/canvas'

/** 分组折叠态胶囊几何（组层渲染与连线锚点必须一致） */
export const GROUP_PILL = { width: 200, height: 36 }

/** 组框边界 */
export interface GroupBounds {
  left: number
  top: number
  width: number
  height: number
}

/** 计算分组包络（贴住所有成员；上侧留标题栏空间） */
export function calculateGroupBounds(group: Pick<CanvasGroup, 'panel_ids'>, panels: CanvasPanel[]): GroupBounds | null {
  const members = panels.filter((p) => group.panel_ids.includes(p.id))
  if (members.length === 0) return null
  const minX = Math.min(...members.map((p) => p.x))
  const minY = Math.min(...members.map((p) => p.y))
  const maxX = Math.max(...members.map((p) => p.x + p.width))
  const maxY = Math.max(...members.map((p) => p.y + p.height))
  return {
    left: minX - 12,
    top: minY - 44,
    width: maxX - minX + 24,
    height: maxY - minY + 56,
  }
}

/** 折叠组成员的胶囊锚点矩形（panelId → rect + groupId） */
export function collapsedGroupAnchors(
  groups: Pick<CanvasGroup, 'id' | 'panel_ids' | 'collapsed'>[],
  panels: CanvasPanel[],
): Map<string, { rect: { x: number; y: number; width: number; height: number }; groupId: string }> {
  const map = new Map<string, { rect: { x: number; y: number; width: number; height: number }; groupId: string }>()
  for (const group of groups) {
    if (!group.collapsed) continue
    const bounds = calculateGroupBounds(group, panels)
    if (!bounds) continue
    const rect = { x: bounds.left, y: bounds.top, width: GROUP_PILL.width, height: GROUP_PILL.height }
    for (const pid of group.panel_ids) map.set(pid, { rect, groupId: group.id })
  }
  return map
}

/** 组成员生成状态聚合（折叠胶囊状态点）：running > failed > success > idle */
export function groupStatus(
  group: Pick<CanvasGroup, 'panel_ids'>,
  panels: CanvasPanel[],
): 'running' | 'failed' | 'success' | 'idle' {
  const statuses = panels
    .filter((p) => group.panel_ids.includes(p.id))
    .map((p) => (p.content as Record<string, unknown>)?.status)
  if (statuses.some((s) => s === 'loading')) return 'running'
  if (statuses.some((s) => s === 'error')) return 'failed'
  if (statuses.length > 0 && statuses.every((s) => s === 'success')) return 'success'
  return 'idle'
}

/** 资产类别 */
export type AssetCategory =
  | 'script' | 'character' | 'prop' | 'scene' | 'storyboard' | 'video'
  | 'audio' | 'subtitle' | 'compose' | 'config' | 'image'

/** 资产类别规范排序（整理布局按此顺序分区：脚本 → 人物 → 物品 → 场景 → 分镜 → 生成视频 → 其余兜底） */
export const ASSET_CATEGORY_ORDER: AssetCategory[] = [
  'script', 'character', 'prop', 'scene', 'storyboard', 'video',
  'audio', 'subtitle', 'compose', 'config', 'image',
]

/** 图片提示词 → 类别的关键词推断（按序首个命中生效） */
const CATEGORY_KEYWORDS: Array<[AssetCategory, RegExp]> = [
  ['character', /角色|人物|主角|男主|女主|配角|形象|character|portrait/i],
  ['scene', /场景|背景|环境|建筑|街道|房间|风景|scene|background|environment/i],
  ['prop', /道具|物品|服装|服饰|武器|产品|食物|prop|item|product|outfit/i],
]

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** 判定节点资产类别：手动标记(meta.category) > 派生血缘 > 提示词关键词 > 类型兜底 */
export function detectAssetCategory(panel: CanvasPanel): AssetCategory {
  if (panel.type === 'script' || panel.type === 'text') return 'script'
  if (panel.type === 'video') return 'video'
  if (panel.type === 'audio' || panel.type === 'tts') return 'audio'
  if (panel.type === 'subtitle') return 'subtitle'
  if (panel.type === 'compose') return 'compose'
  if (panel.type === 'config') return 'config'

  const content = isRecord(panel.content) ? panel.content : undefined
  const meta = isRecord(panel.meta) ? panel.meta : undefined
  const tagged = meta?.category
  const matched = ASSET_CATEGORY_ORDER.find((c) => c === tagged)
  if (matched) return matched

  const lineage = isRecord(content?.lineage) ? content?.lineage : undefined
  if (lineage && typeof lineage.scriptPanelId === 'string') return 'storyboard'

  if (panel.type === 'image') {
    const prompt = typeof content?.prompt === 'string' ? content.prompt : ''
    for (const [category, pattern] of CATEGORY_KEYWORDS) {
      if (pattern.test(prompt)) return category
    }
  }
  return 'image'
}

/** 分类分组建议 */
export interface GroupSuggestion {
  category: AssetCategory
  panelIds: string[]
  /** 生成链条组：来源脚本名（view 层拼组名用） */
  chainScriptName?: string
}

/** 分类分组建议：按生成链条和/或资产类别对未分组节点建组（模式可多选叠加，链条优先）
 * - 生成链条：同一脚本派生的节点（lineage.scriptPanelId 相同）+ 该脚本节点为一组
 * - 资产类别：按 detectAssetCategory 聚类，每类 ≥2 个节点成一组
 */
export function suggestGroups(
  panels: CanvasPanel[],
  groups: Pick<CanvasGroup, 'panel_ids'>[],
  modes: { byChain: boolean; byCategory: boolean },
): GroupSuggestion[] {
  const grouped = new Set(groups.flatMap((g) => g.panel_ids))
  const free = panels.filter((p) => !grouped.has(p.id))
  const used = new Set<string>()
  const suggestions: GroupSuggestion[] = []

  if (modes.byChain) {
    const byScript = new Map<string, string[]>()
    for (const p of free) {
      const content = isRecord(p.content) ? p.content : undefined
      const lineage = isRecord(content?.lineage) ? content?.lineage : undefined
      const scriptId = lineage && typeof lineage.scriptPanelId === 'string' ? lineage.scriptPanelId : null
      if (!scriptId) continue
      const list = byScript.get(scriptId)
      if (list) list.push(p.id)
      else byScript.set(scriptId, [p.id])
    }
    for (const [scriptId, derivedIds] of byScript) {
      const scriptPanel = panels.find((p) => p.id === scriptId)
      const members = [...derivedIds]
      if (scriptPanel && !grouped.has(scriptPanel.id) && !used.has(scriptPanel.id)) {
        members.unshift(scriptPanel.id)
      }
      if (members.length < 2) continue
      for (const id of members) used.add(id)
      suggestions.push({
        category: 'storyboard',
        panelIds: members,
        chainScriptName: scriptPanel?.name || undefined,
      })
    }
  }

  if (modes.byCategory) {
    const byCategory = new Map<AssetCategory, string[]>()
    for (const p of free) {
      if (used.has(p.id)) continue
      const category = detectAssetCategory(p)
      const list = byCategory.get(category)
      if (list) list.push(p.id)
      else byCategory.set(category, [p.id])
    }
    for (const [category, panelIds] of byCategory) {
      if (panelIds.length < 2) continue
      suggestions.push({ category, panelIds })
    }
  }

  return suggestions
}
