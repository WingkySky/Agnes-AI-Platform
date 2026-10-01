/* =====================================================
 * 画布拖放落点布局
 *  - 计算一批媒体节点拖放后的世界坐标（节点左上角）
 *  - 首个节点以落点为中心，横向排列，每行 perRow 个后换行
 * ===================================================== */

export interface DropSize {
  width: number
  height: number
}

export interface DropPosition {
  x: number
  y: number
}

/** 规划拖放节点的世界坐标（sizes 顺序与文件一一对应；worldX/worldY 为首个节点的中心落点） */
export function planDropLayout(
  sizes: DropSize[],
  worldX: number,
  worldY: number,
  perRow = 4,
  gap = 16,
): DropPosition[] {
  return sizes.map((size, i) => {
    const row = Math.floor(i / perRow)
    const rowStart = row * perRow
    // 行高取该行最大高度，保证混合 image/video 尺寸时不重叠
    const rowHeight = Math.max(...sizes.slice(rowStart, rowStart + perRow).map((s) => s.height))
    const colOffset = sizes.slice(rowStart, i).reduce((sum, s) => sum + s.width + gap, 0)
    return {
      x: worldX - size.width / 2 + colOffset,
      y: worldY - size.height / 2 + row * (rowHeight + gap),
    }
  })
}
