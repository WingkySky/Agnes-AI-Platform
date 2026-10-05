/* =====================================================
 * 时间线吸附（纯函数）
 * - 候选点：时间 0 点 + 播放头 + 全部片段首尾边（可排除手势中的自身）
 * - 阈值按像素定义、随缩放换算成秒：放大吸附越精确、缩小越宽松
 * - 手势中按住 Shift 临时禁用（组件层负责），开关偏好持久化在 store
 * ===================================================== */

import { clipEnd, type EditorDocument } from './editor-types'

export type SnapPointType = 'zero' | 'playhead' | 'clip-start' | 'clip-end'

export interface SnapPoint {
  time: number
  type: SnapPointType
}

export interface SnapResult {
  time: number
  point: SnapPoint | null
}

/** 吸附像素阈值 */
export const SNAP_THRESHOLD_PX = 10

/** 像素阈值 → 当前缩放下的秒阈值 */
export function snapThresholdSec(pxPerSec: number, px: number = SNAP_THRESHOLD_PX): number {
  return px / pxPerSec
}

/** 收集候选吸附点；excludeClipId：拖拽/裁剪中的片段自身不作为候选 */
export function buildSnapPoints(
  doc: EditorDocument,
  opts: { excludeClipId?: string; playhead?: number } = {},
): SnapPoint[] {
  const points: SnapPoint[] = [{ time: 0, type: 'zero' }]
  if (opts.playhead !== undefined) points.push({ time: opts.playhead, type: 'playhead' })
  for (const clip of doc.clips) {
    if (clip.id === opts.excludeClipId) continue
    points.push({ time: clip.start, type: 'clip-start' })
    points.push({ time: clipEnd(clip), type: 'clip-end' })
  }
  return points
}

/** 最近点吸附：阈值内取距离最小的候选；无命中则原值返回（point=null） */
export function resolveSnap(target: number, points: SnapPoint[], maxDistance: number): SnapResult {
  let best: SnapPoint | null = null
  let bestDist = Infinity
  for (const point of points) {
    const dist = Math.abs(target - point.time)
    if (dist <= maxDistance && dist < bestDist) {
      bestDist = dist
      best = point
    }
  }
  return best ? { time: best.time, point: best } : { time: target, point: null }
}
