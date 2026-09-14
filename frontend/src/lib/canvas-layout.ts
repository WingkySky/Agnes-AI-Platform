/* =====================================================
 * 画布一键整理布局（产出管线分区排列）
 * - 剧本 → 独立分区；人物+物品 → 5 列堆；背景图 → 另一个 5 列堆；三区横向并排、区间留大间隔
 * - 分镜图 → 账本竖排：一行一张紧凑排列，读满 LEDGER_MAX_ROWS 行换下一列；视频不穿插在账本里
 * - 全部视频 → 账本右侧统一的视频区（横排散带）；配音/字幕/兜底随后；合成视频（成片）排最右
 * - 行/行序按上游连线质心校正，让"谁产出谁"相邻；平局回退创建序（与坐标无关，重复整理稳定）
 * - 已有分组 = 一个块（成员相对位置不变整块搬；锁定组/锁定节点不动）
 * ===================================================== */

import type { CanvasPanel, CanvasGroup, CanvasConnection } from '@/stores/canvas'
import { ASSET_CATEGORY_ORDER, detectAssetCategory, type AssetCategory } from '@/lib/canvas-groups'

/** 列内条目垂直间距 */
const ITEM_GAP_Y = 80
/** 行架条目水平间距 */
const ITEM_GAP_X = 24
/** 相邻生产阶段带间距 */
const COLUMN_GAP = 260
/** 分镜账本行距（紧凑竖排） */
const LEDGER_ROW_GAP = 28
/** 分镜账本列间距 */
const LEDGER_GAP = 160
/** 资产堆（剧本/人物+物品 / 背景）最大宽度：约 5 个标准节点一行，成 5 列块 */
const PILE_MAX_WIDTH = 1820
/** 尾部散带（零散视频/音频/字幕/兜底/合成）最大宽度 */
const TRAILING_MAX_WIDTH = 2800
/** 分镜账本每列最大行数（竖排读满一列再开下一列） */
const LEDGER_MAX_ROWS = 10
/** 异常尺寸兜底（旧数据/导入数据可能缺宽高，防 NaN 污染整带布局） */
const FALLBACK_WIDTH = 200
const FALLBACK_HEIGHT = 160
/** 行主序字典序键的缩放系数：y * SCALE + x，使上游的"第几行第几个"可参与质心排序 */
const KEY_SCALE = 1e7

interface Position {
  x: number
  y: number
}

/** 布局单元：单个未分组节点或一个分组块 */
interface Unit {
  ids: string[]
  width: number
  height: number
  /** 成员 panelId → 相对块左上角偏移 */
  offsets: Map<string, Position>
  /** 创建序（panels 数组下标最小值；与坐标无关，保证整理幂等） */
  index: number
  /** 管线阶段位次（ASSET_CATEGORY_ORDER 下标） */
  stage: number
  /** 布局后左上角（放置阶段回填） */
  pos: Position
}

function categoryRank(category: AssetCategory): number {
  const index = ASSET_CATEGORY_ORDER.indexOf(category)
  return index === -1 ? ASSET_CATEGORY_ORDER.length : index
}

/** 尺寸清洗：非法/缺失值回退默认，避免 NaN 沿列光标扩散成堆叠 */
const px = (p: CanvasPanel) => (Number.isFinite(p.x) ? p.x : 0)
const py = (p: CanvasPanel) => (Number.isFinite(p.y) ? p.y : 0)
const pw = (p: CanvasPanel) => (Number.isFinite(p.width) && p.width > 0 ? p.width : FALLBACK_WIDTH)
const ph = (p: CanvasPanel) => (Number.isFinite(p.height) && p.height > 0 ? p.height : FALLBACK_HEIGHT)

/** 由一组成员构建分组块单元：几何包络 + 多数类别定阶段 */
function buildBlockUnit(members: CanvasPanel[], indexOf: Map<string, number>): Unit {
  const left = Math.min(...members.map(px))
  const top = Math.min(...members.map(py))
  const counts = new Map<AssetCategory, number>()
  for (const m of members) {
    const category = detectAssetCategory(m)
    counts.set(category, (counts.get(category) || 0) + 1)
  }
  const category = [...counts.entries()].sort((a, b) =>
    b[1] - a[1] || categoryRank(a[0]) - categoryRank(b[0]),
  )[0][0]
  return {
    ids: members.map((m) => m.id),
    width: Math.max(...members.map((m) => px(m) + pw(m))) - left,
    height: Math.max(...members.map((m) => py(m) + ph(m))) - top,
    offsets: new Map(members.map((m) => [m.id, { x: px(m) - left, y: py(m) - top }])),
    index: Math.min(...members.map((m) => indexOf.get(m.id) ?? 0)),
    stage: categoryRank(category),
    pos: { x: 0, y: 0 },
  }
}

/** 构建布局单元：解锁组=块，未组节点=单块；锁定不参与 */
function buildUnits(
  panels: CanvasPanel[],
  groups: Pick<CanvasGroup, 'panel_ids' | 'locked'>[],
): Unit[] {
  const indexOf = new Map(panels.map((p, i) => [p.id, i]))
  const groupedIds = new Set(groups.flatMap((g) => g.panel_ids))
  const units: Unit[] = []
  for (const group of groups) {
    const members = panels.filter((p) => group.panel_ids.includes(p.id))
    if (members.length === 0 || group.locked || members.some((m) => m.is_locked)) continue
    units.push(buildBlockUnit(members, indexOf))
  }
  const free = panels.filter((p) => !groupedIds.has(p.id) && !p.is_locked)
  for (const p of free) {
    units.push({
      ids: [p.id],
      width: pw(p),
      height: ph(p),
      offsets: new Map([[p.id, { x: 0, y: 0 }]]),
      index: indexOf.get(p.id) ?? 0,
      stage: categoryRank(detectAssetCategory(p)),
      pos: { x: 0, y: 0 },
    })
  }
  return units
}

/** 计算整理后的节点位置表（只含需要移动的节点；空表 = 无可整理） */
export function computeArrangedLayout(
  panels: CanvasPanel[],
  groups: Pick<CanvasGroup, 'panel_ids' | 'locked'>[],
  connections: Pick<CanvasConnection, 'source_panel_id' | 'target_panel_id'>[] = [],
): Record<string, Position> {
  const byId = new Map(panels.map((p) => [p.id, p]))
  const units = buildUnits(panels, groups)
  if (units.length === 0) return {}
  const unitByPanel = new Map<string, Unit>()
  for (const u of units) for (const id of u.ids) unitByPanel.set(id, u)

  // ---- 分阶段带（只保留非空阶段，按管线序处理）----
  const stages = new Map<number, Unit[]>()
  for (const u of units) {
    const list = stages.get(u.stage)
    if (list) list.push(u)
    else stages.set(u.stage, [u])
  }

  // ---- 分区：剧本（独立）→ 人物+物品堆（5 列成块）→ 背景堆（5 列成块）→ 分镜账本 → 尾部散带（合成最后/最右）----
  const scriptRank = categoryRank('script')
  const sceneRank = categoryRank('scene')
  const storyboardRank = categoryRank('storyboard')
  const scriptPile: Unit[] = []
  const pileA: Unit[] = []
  const pileB: Unit[] = []
  const ledgerUnits: Unit[] = []
  const trailing = new Map<number, Unit[]>()
  for (const [stage, list] of stages) {
    if (stage === scriptRank) scriptPile.push(...list)
    else if (stage < sceneRank) pileA.push(...list)
    else if (stage === sceneRank) pileB.push(...list)
    else if (stage === storyboardRank) ledgerUnits.push(...list)
    else trailing.set(stage, list)
  }

  const placedKey = new Map<string, number>()

  /** 上游质心键校正 + 排序（阶段优先，其次上游质心，再按创建序） */
  const orderedByUpstream = (list: Unit[], estimated: Map<Unit, number>): Unit[] => {
    const byIndex = [...list].sort((a, b) => a.index - b.index)
    const keys = new Map<Unit, number>()
    for (const u of byIndex) {
      let sum = 0
      let n = 0
      for (const conn of connections) {
        const srcUnit = unitByPanel.get(conn.source_panel_id)
        if (!srcUnit || srcUnit === u || srcUnit.stage >= u.stage) continue
        const key = placedKey.get(conn.source_panel_id)
        if (key !== undefined && u.ids.includes(conn.target_panel_id)) {
          sum += key
          n += 1
        }
      }
      keys.set(u, n > 0 ? sum / n : estimated.get(u)!)
    }
    return byIndex.sort((a, b) => a.stage - b.stage || keys.get(a)! - keys.get(b)! || a.index - b.index)
  }

  /** 模拟行架得到的估计落点（无上游参照时参与比较，避免与质心键尺度脱节） */
  const simulateGrid = (list: Unit[], maxRowWidth: number): Map<Unit, number> => {
    const estimated = new Map<Unit, number>()
    let ex = 0
    let ey = 0
    let eh = 0
    for (const u of [...list].sort((a, b) => a.stage - b.stage || a.index - b.index)) {
      if (ex > 0 && ex + u.width > maxRowWidth) {
        ex = 0
        ey += eh + ITEM_GAP_Y
        eh = 0
      }
      estimated.set(u, ey * KEY_SCALE + ex)
      ex += u.width + ITEM_GAP_X
      eh = Math.max(eh, u.height)
    }
    return estimated
  }

  const simulateLedger = (list: Unit[]): Map<Unit, number> => {
    const estimated = new Map<Unit, number>()
    let ey = 0
    for (const u of [...list].sort((a, b) => a.index - b.index)) {
      estimated.set(u, ey * KEY_SCALE)
      ey += u.height + LEDGER_ROW_GAP
    }
    return estimated
  }

  /** 行架放置（返回区域宽度） */
  const placeGrid = (list: Unit[], startX: number, maxRowWidth: number): number => {
    let rowX = 0
    let rowY = 0
    let rowH = 0
    let regionWidth = 0
    for (const u of list) {
      if (rowX > 0 && rowX + u.width > maxRowWidth) {
        rowX = 0
        rowY += rowH + ITEM_GAP_Y
        rowH = 0
      }
      u.pos = { x: startX + rowX, y: rowY }
      for (const id of u.ids) {
        const offset = u.offsets.get(id)!
        placedKey.set(id, (rowY + offset.y) * KEY_SCALE + (startX + rowX + offset.x))
      }
      rowX += u.width + ITEM_GAP_X
      rowH = Math.max(rowH, u.height)
      regionWidth = Math.max(regionWidth, rowX - ITEM_GAP_X)
    }
    return regionWidth
  }

  /** 账本竖排放置（紧凑行距；返回区域宽度） */
  const placeLedger = (list: Unit[], startX: number): number => {
    let colX = startX
    let colWidth = 0
    let y = 0
    let row = 0
    for (const u of list) {
      if (row > 0 && row % LEDGER_MAX_ROWS === 0) {
        colX += colWidth + LEDGER_GAP
        y = 0
        colWidth = 0
      }
      u.pos = { x: colX, y }
      for (const id of u.ids) {
        const offset = u.offsets.get(id)!
        placedKey.set(id, (y + offset.y) * KEY_SCALE + (colX + offset.x))
      }
      y += u.height + LEDGER_ROW_GAP
      colWidth = Math.max(colWidth, u.width)
      row += 1
    }
    return colX + colWidth - startX
  }

  let cursorX = 0
  if (scriptPile.length) cursorX += placeGrid(orderedByUpstream(scriptPile, simulateGrid(scriptPile, PILE_MAX_WIDTH)), cursorX, PILE_MAX_WIDTH) + COLUMN_GAP
  if (pileA.length) cursorX += placeGrid(orderedByUpstream(pileA, simulateGrid(pileA, PILE_MAX_WIDTH)), cursorX, PILE_MAX_WIDTH) + COLUMN_GAP
  if (pileB.length) cursorX += placeGrid(orderedByUpstream(pileB, simulateGrid(pileB, PILE_MAX_WIDTH)), cursorX, PILE_MAX_WIDTH) + COLUMN_GAP
  if (ledgerUnits.length) cursorX += placeLedger(orderedByUpstream(ledgerUnits, simulateLedger(ledgerUnits)), cursorX) + COLUMN_GAP
  for (const stage of [...trailing.keys()].sort((a, b) => a - b)) {
    const list = trailing.get(stage)!
    cursorX += placeGrid(orderedByUpstream(list, simulateGrid(list, TRAILING_MAX_WIDTH)), cursorX, TRAILING_MAX_WIDTH) + COLUMN_GAP
  }

  // ---- 平移对齐：布局后内容左上角对齐原内容左上角（不搬家） ----
  const moved = units.flatMap((u) => u.ids.map((id) => byId.get(id)!))
  const originX = Math.min(...moved.map(px))
  const originY = Math.min(...moved.map(py))
  const rawMinX = Math.min(...units.map((u) => u.pos.x))
  const rawMinY = Math.min(...units.map((u) => u.pos.y))
  const offsetX = originX - rawMinX
  const offsetY = originY - rawMinY

  const result: Record<string, Position> = {}
  for (const u of units) {
    for (const [id, offset] of u.offsets) {
      const panel = byId.get(id)!
      const x = u.pos.x + offset.x + offsetX
      const y = u.pos.y + offset.y + offsetY
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue
      if (panel.x !== x || panel.y !== y) result[id] = { x, y }
    }
  }
  return result
}
