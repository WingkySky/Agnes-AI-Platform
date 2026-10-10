/* =====================================================
 * AI 粗剪纯函数：segments → 时间线片段（顺序排布 + trim 映射）
 * - 后端分析合同 segments: [{start, end}]（秒，升序不重叠）
 * - 落时间线 = 顺序首尾相接排布：clip.start 逐段推进、duration=段长、trimStart=段起点
 * ===================================================== */

import type { EditorClip } from './editor-types'
import type { RoughCutSegment } from '@/api/editor'

export interface RoughCutClipOptions {
  trackId: string
  assetId: number
  /** 时间线起始落点（秒），缺省 0（轨尾追加由调用方传轨尾时间） */
  offset?: number
  /** 过滤短于此的段（秒），与后端 min_keep 口径一致 */
  minSeg?: number
}

/** 保留段 → addClip 载荷的 clips（顺序排布；id 由 idFn 生成，调用方接 store.newId） */
export function segmentsToClips(
  segments: RoughCutSegment[],
  opts: RoughCutClipOptions,
  idFn: (prefix: string) => string,
): EditorClip[] {
  const minSeg = opts.minSeg ?? 0.2
  const clips: EditorClip[] = []
  let cursor = opts.offset ?? 0
  for (const seg of segments) {
    const duration = seg.end - seg.start
    if (duration < minSeg) continue
    clips.push({
      id: idFn('clip'),
      trackId: opts.trackId,
      assetId: opts.assetId,
      start: round3(cursor),
      duration: round3(duration),
      trimStart: round3(seg.start),
      props: {},
    })
    cursor += duration
  }
  return clips
}

/** 毫秒圆整（浮点推进噪声不出现在落库片段上） */
function round3(v: number): number {
  return Math.round(v * 1000) / 1000
}

/** 保留总时长（秒） */
export function segmentsDuration(segments: RoughCutSegment[]): number {
  return segments.reduce((acc, s) => acc + (s.end - s.start), 0)
}
