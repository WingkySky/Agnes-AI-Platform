/* =====================================================
 * 画布一键整理布局（面板摆放位置优化，按资产类别分区排放）
 * - 每个已有分组 = 一个区（成员相对位置不变，整块平移；锁定组不动）
 * - 未分组节点按资产类别聚成区（区内行架网格）
 * - 区按创作管线规范顺序排放：脚本 → 人物 → 物品 → 场景 → 分镜 → 生成视频 → 兜底类
 * - 每行最多 2 个区（看板式两列，超宽的区独占），整体对齐原内容不搬家
 * ===================================================== */

import type { CanvasPanel, CanvasGroup } from '@/stores/canvas'
import {
  ASSET_CATEGORY_ORDER,
  calculateGroupBounds,
  detectAssetCategory,
  type AssetCategory,
} from '@/lib/canvas-groups'

/** 区内行架宽度上限（约 5-6 列） */
const SHELF_WIDTH = 2400
/** 区内条目间距 */
const ITEM_GAP_X = 120
const ITEM_GAP_Y = 60
/** 每行区数（看板两列） */
const ZONES_PER_ROW = 2
/** 区间距 */
const ZONE_GAP = 300

interface Position {
  x: number
  y: number
}

interface Zone {
  category: AssetCategory
  width: number
  height: number
  /** 面板 id → 区内局部坐标 */
  local: Map<string, Position>
  target: Position
}

function categoryRank(category: AssetCategory): number {
  const index = ASSET_CATEGORY_ORDER.indexOf(category)
  return index === -1 ? ASSET_CATEGORY_ORDER.length : index
}

/** 计算整理后的节点位置表（只含需要移动的节点；空表 = 无可整理） */
export function computeArrangedLayout(
  panels: CanvasPanel[],
  groups: Pick<CanvasGroup, 'panel_ids' | 'locked'>[],
): Record<string, Position> {
  const byId = new Map(panels.map((p) => [p.id, p]))
  const groupedIds = new Set(groups.flatMap((g) => g.panel_ids))
  const zones: Zone[] = []

  // ---- 已有分组作为区：成员相对位置保持整块平移；类别取成员多数（锁定组跳过） ----
  for (const group of groups) {
    const members = panels.filter((p) => group.panel_ids.includes(p.id))
    if (members.length === 0 || group.locked || members.some((m) => m.is_locked)) continue
    const bounds = calculateGroupBounds(group, panels)
    if (!bounds) continue
    const counts = new Map<AssetCategory, number>()
    for (const m of members) {
      const category = detectAssetCategory(m)
      counts.set(category, (counts.get(category) || 0) + 1)
    }
    const category = [...counts.entries()].sort((a, b) =>
      b[1] - a[1] || categoryRank(a[0]) - categoryRank(b[0]),
    )[0][0]
    const local = new Map<string, Position>()
    for (const m of members) {
      local.set(m.id, { x: m.x - bounds.left, y: m.y - bounds.top })
    }
    zones.push({ category, width: bounds.width, height: bounds.height, local, target: { x: 0, y: 0 } })
  }

  // ---- 未分组节点按资产类别聚区（锁定节点跳过），区内行架 ----
  const freePanels = panels.filter((p) => !groupedIds.has(p.id) && !p.is_locked)
  const byCategory = new Map<AssetCategory, CanvasPanel[]>()
  for (const p of freePanels) {
    const category = detectAssetCategory(p)
    const list = byCategory.get(category)
    if (list) list.push(p)
    else byCategory.set(category, [p])
  }
  for (const [category, members] of byCategory) {
    const sorted = [...members].sort((a, b) => a.y - b.y || a.x - b.x)
    const local = new Map<string, Position>()
    let rowX = 0
    let rowY = 0
    let rowHeight = 0
    for (const p of sorted) {
      if (rowX > 0 && rowX + p.width > SHELF_WIDTH) {
        rowX = 0
        rowY += rowHeight + ITEM_GAP_Y
        rowHeight = 0
      }
      local.set(p.id, { x: rowX, y: rowY })
      rowX += p.width + ITEM_GAP_X
      rowHeight = Math.max(rowHeight, p.height)
    }
    zones.push({
      category,
      width: Math.max(...[...local.values()].map((pos) => pos.x)) + Math.max(...sorted.map((p) => p.width)),
      height: rowY + rowHeight,
      local,
      target: { x: 0, y: 0 },
    })
  }

  if (zones.length === 0) return {}

  // ---- 区排序：类别规范序 → 同类别按原始内容最上方 y ----
  const zoneMinY = (zone: Zone): number => {
    let min = Number.POSITIVE_INFINITY
    for (const id of zone.local.keys()) min = Math.min(min, byId.get(id)!.y)
    return min
  }
  zones.sort((a, b) => categoryRank(a.category) - categoryRank(b.category) || zoneMinY(a) - zoneMinY(b))

  // ---- 看板式两列排放（超宽区独占一行，不重叠） ----
  let rowY = 0
  let rowMaxHeight = 0
  let col = 0
  let nextColumnX = 0
  for (const zone of zones) {
    zone.target = { x: col === 0 ? 0 : nextColumnX + ZONE_GAP, y: rowY }
    rowMaxHeight = Math.max(rowMaxHeight, zone.height)
    col += 1
    if (col === ZONES_PER_ROW) {
      rowY += rowMaxHeight + ZONE_GAP
      rowMaxHeight = 0
      col = 0
      nextColumnX = 0
    } else {
      nextColumnX = zone.target.x + zone.width
    }
  }

  // ---- 平移对齐：布局后的面板级左上角对齐原内容左上角（不搬家） ----
  const moved: CanvasPanel[] = []
  for (const zone of zones) {
    for (const id of zone.local.keys()) moved.push(byId.get(id)!)
  }
  const originX = Math.min(...moved.map((p) => p.x))
  const originY = Math.min(...moved.map((p) => p.y))
  const raw = new Map<string, Position>()
  for (const zone of zones) {
    for (const [id, local] of zone.local) {
      raw.set(id, { x: zone.target.x + local.x, y: zone.target.y + local.y })
    }
  }
  const rawMinX = Math.min(...[...raw.values()].map((pos) => pos.x))
  const rawMinY = Math.min(...[...raw.values()].map((pos) => pos.y))
  const offsetX = originX - rawMinX
  const offsetY = originY - rawMinY

  const result: Record<string, Position> = {}
  for (const [id, pos] of raw) {
    const panel = byId.get(id)!
    const x = pos.x + offsetX
    const y = pos.y + offsetY
    if (panel.x !== x || panel.y !== y) result[id] = { x, y }
  }
  return result
}
