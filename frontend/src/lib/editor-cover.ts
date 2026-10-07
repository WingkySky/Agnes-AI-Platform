/* =====================================================
 * 剪辑工程封面（纯函数 + 候选派生）
 *
 * 封面 = 影片中某一帧（前端抽帧上传）或用户上传图；URL 挂 editing_projects.cover_url。
 * 取帧语义与预览/渲染一致：非 hidden 视频轨中激活且 order 最大（顶层）者，
 * gap 处为黑场（黑场帧同样允许做封面）。
 * ===================================================== */

import { clipEnd, type EditorClip, type EditorDocument } from './editor-types'

/** 影片总时长（全部片段最大末尾，下限 0.1 供滑杆） */
export function coverDocDuration(doc: EditorDocument): number {
  return Math.max(0.1, ...doc.clips.map(clipEnd))
}

/** 时刻 t 的封面取帧片段：非 hidden 视频轨激活片段中 order 最大者；gap 返回 null */
export function coverClipAt(doc: EditorDocument, t: number): EditorClip | null {
  let top: EditorClip | null = null
  let topOrder = -Infinity
  for (const track of doc.tracks) {
    if (track.kind !== 'video' || track.flags.hidden) continue
    const clip = doc.clips.find(
      (c) => c.trackId === track.id && t >= c.start && t < clipEnd(c),
    )
    if (clip && track.order > topOrder) {
      top = clip
      topOrder = track.order
    }
  }
  return top
}

/** 源内时刻（与预览 sourceTimeAt 同语义） */
export function coverSourceTime(clip: EditorClip, t: number): number {
  return clip.trimStart + (t - clip.start) * (clip.props.speed ?? 1)
}

/** 候选帧时刻：各视频片段首帧（+0.05 避开 0 点黑帧，钳片段内），升序去重 */
export function coverCandidates(doc: EditorDocument): number[] {
  const times: number[] = []
  for (const clip of doc.clips) {
    const track = doc.tracks.find((tr) => tr.id === clip.trackId)
    if (!track || track.kind !== 'video' || track.flags.hidden) continue
    const t = Math.min(clip.start + 0.05, clipEnd(clip) - 0.01)
    if (t >= clip.start) times.push(Math.round(t * 100) / 100)
  }
  return [...new Set(times)].sort((a, b) => a - b)
}
