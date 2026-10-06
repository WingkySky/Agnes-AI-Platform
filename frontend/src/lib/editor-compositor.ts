/* =====================================================
 * 预览合成器（纯函数）
 * - planFrame：文档 + 播放头 → 自底向上的绘制清单（视频轨激活片段，归一化 rect
 *   换算为 stage 像素）；字幕走 DOM 层不进清单；执行层只做 drawImage
 * - 与渲染端语义对齐：轨 order 大 = 上层；hidden 轨跳过；无激活片段输出黑底 * ===================================================== */

import { clipEnd, FULL_RECT, type ClipRect, type EditorDocument } from './editor-types'

/** 绘制清单项：assetId 由执行层解析为视频帧（media sink）或图片位图；clipId 供执行层维护解码状态 */
export interface DrawItem {
  clipId: string
  assetId: number
  x: number
  y: number
  w: number
  h: number
}

/** 当前播放头一帧的绘制清单（自底向上；stage 尺寸为 CSS 像素，dpr 由执行层处理） */
export function planFrame(
  doc: EditorDocument,
  playhead: number,
  stageW: number,
  stageH: number,
): DrawItem[] {
  const videoTracks = doc.tracks
    .filter((tr) => tr.kind === 'video' && !tr.flags.hidden)
    .sort((a, b) => a.order - b.order)
  const items: DrawItem[] = []
  for (const track of videoTracks) {
    const clip = doc.clips.find(
      (c) => c.trackId === track.id && playhead >= c.start && playhead < clipEnd(c),
    )
    if (!clip || clip.assetId == null) continue
    const rect = clip.props.rect ?? FULL_RECT
    items.push({
      clipId: clip.id,
      assetId: clip.assetId,
      x: rect.x * stageW,
      y: rect.y * stageH,
      w: rect.w * stageW,
      h: rect.h * stageH,
    })
  }
  return items
}

// ---------- 画中画直接操作（预览窗拖动/缩放的几何纯函数） ----------

export type RectCorner = 'nw' | 'ne' | 'sw' | 'se'

/** PIP 最小归一化边长 */
export const MIN_RECT_EDGE = 0.05

/** 顶层优先命中：绘制清单自顶向下找第一个包含点的项（px 坐标） */
export function pickDrawItem(items: DrawItem[], px: number, py: number): DrawItem | null {
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i]!
    if (px >= it.x && px < it.x + it.w && py >= it.y && py < it.y + it.h) return it
  }
  return null
}

/** 选中片段的角点手柄命中（px 坐标，radius 为手柄半径）；未命中返回 null */
export function cornerHit(item: DrawItem, px: number, py: number, radius: number): RectCorner | null {
  const corners: Array<[RectCorner, number, number]> = [
    ['nw', item.x, item.y],
    ['ne', item.x + item.w, item.y],
    ['sw', item.x, item.y + item.h],
    ['se', item.x + item.w, item.y + item.h],
  ]
  for (const [c, cx, cy] of corners) {
    if (Math.abs(px - cx) <= radius && Math.abs(py - cy) <= radius) return c
  }
  return null
}

/** 移动：位移为归一化增量，钳制在画幅内 */
export function moveRect(rect: ClipRect, dx: number, dy: number): ClipRect {
  const round = (v: number): number => Math.round(v * 10000) / 10000
  const x = Math.min(Math.max(rect.x + dx, 0), 1 - rect.w)
  const y = Math.min(Math.max(rect.y + dy, 0), 1 - rect.h)
  return { x: round(x), y: round(y), w: rect.w, h: rect.h }
}

/** 角点等比缩放：对角锚定，最小边 MIN_RECT_EDGE，钳制在画幅内（归一化增量） */
export function resizeRect(rect: ClipRect, corner: RectCorner, dx: number, dy: number): ClipRect {
  const w0 = Math.max(rect.w, 1e-6)
  const h0 = Math.max(rect.h, 1e-6)
  // 拖离锚点方向为放大：右/下角 +，左/上角取反
  const gx = corner === 'ne' || corner === 'se' ? dx : -dx
  const gy = corner === 'sw' || corner === 'se' ? dy : -dy
  let s = Math.max((w0 + gx) / w0, (h0 + gy) / h0)
  s = Math.max(s, Math.max(MIN_RECT_EDGE / w0, MIN_RECT_EDGE / h0))
  // 对角锚定下画幅边界允许的最大缩放
  const sMaxByX = corner === 'nw' || corner === 'sw' ? (rect.x + w0) / w0 : (1 - rect.x) / w0
  const sMaxByY = corner === 'nw' || corner === 'ne' ? (rect.y + h0) / h0 : (1 - rect.y) / h0
  s = Math.min(s, sMaxByX, sMaxByY)
  const w = s * w0
  const h = s * h0
  const round = (v: number): number => Math.round(v * 10000) / 10000
  return {
    x: round(corner === 'nw' || corner === 'sw' ? rect.x + w0 - w : rect.x),
    y: round(corner === 'nw' || corner === 'ne' ? rect.y + h0 - h : rect.y),
    w: round(w),
    h: round(h),
  }
}
