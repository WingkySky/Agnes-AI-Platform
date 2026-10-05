/* =====================================================
 * 时间线几何换算收口
 * - px↔秒 的所有换算只允许经此模块，轨头宽/0 点偏移不再散落各处
 *   （0 点错位类 bug 的根治手段：刻度/播放头/片段块共用同一组函数）
 * - TRACK_HEAD_W / TIMELINE_PAD 必须与 EditorTimeline 的 CSS 保持一致
 * ===================================================== */

/** 轨头列宽（.track-head / .ruler-head 的 width，含右边框） */
export const TRACK_HEAD_W = 168

/** lane 内时间 0 点的左偏移：片段块/刻度/播放头统一由此定位 */
export const TIMELINE_PAD = 8

export const PX_PER_SEC_MIN = 30
export const PX_PER_SEC_MAX = 200

/** 标尺刻度步长（秒）：放大用 1s 细刻度，缩小切换 5s */
export function rulerStepSec(pxPerSec: number): number {
  return pxPerSec >= 60 ? 1 : 5
}

/** 秒 → lane 相对 px（含 0 点偏移） */
export function timeToX(sec: number, pxPerSec: number): number {
  return TIMELINE_PAD + sec * pxPerSec
}

/** lane 相对 px → 秒（负值截断为 0） */
export function xToTime(x: number, pxPerSec: number): number {
  return Math.max(0, (x - TIMELINE_PAD) / pxPerSec)
}
