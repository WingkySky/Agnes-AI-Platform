/* =====================================================
 * 轨道放置解析（纯函数）：碰撞判定 + 空闲轨道回退
 * - 碰撞语义：半开区间相交（相邻贴边不冲突），与渲染 Plan 的拼接/转场语义一致
 * - 碰撞只约束 video/audio 轨；字幕轨是 cue 语义可共存，豁免
 * - 命令层（editor-commands）用 canPlaceOnTrack 做 fail-closed 拒绝，
 *   组件/store 层用 findFreeTrack 做「占用轨 → 同类型空闲轨」回退
 * ===================================================== */

import { clipEnd, type EditorClip, type EditorDocument, type EditorTrack } from './editor-types'

/** 两个时间跨度是否重叠（贴边不算） */
export function spansOverlap(aStart: number, aEnd: number, bStart: number, bEnd: number): boolean {
  return aStart < bEnd && aEnd > bStart
}

export interface PlacementSpan {
  start: number
  duration: number
  /** 移动/裁剪场景排除自身 */
  excludeClipId?: string
}

/** 目标轨的片段集合上该跨度能否放置 */
export function canPlaceOnTrack(trackClips: EditorClip[], span: PlacementSpan): boolean {
  const start = span.start
  const end = span.start + span.duration
  return !trackClips.some((clip) => {
    if (clip.id === span.excludeClipId) return false
    return spansOverlap(start, end, clip.start, clipEnd(clip))
  })
}

/** 是否需要碰撞检查（字幕 cue 可共存，豁免） */
export function needsCollisionCheck(track: EditorTrack): boolean {
  return track.kind === 'video' || track.kind === 'audio'
}

/** 同类型第一个可放置的解锁轨（order 升序）；无则 null */
export function findFreeTrack(
  doc: EditorDocument,
  kind: 'video' | 'audio',
  span: PlacementSpan,
): EditorTrack | null {
  return (
    doc.tracks
      .filter((t) => t.kind === kind && !t.flags.locked)
      .sort((a, b) => a.order - b.order)
      .find((t) => canPlaceOnTrack(doc.clips.filter((c) => c.trackId === t.id), span)) ?? null
  )
}
