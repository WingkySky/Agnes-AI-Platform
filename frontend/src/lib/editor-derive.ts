/* =====================================================
 * 文档派生字段补正（纯函数）
 * - 「送进剪辑器」草稿契约：duration=0 占位片段，加载后用媒体元数据回填
 * - 视频轨占位按轨内原 start 序从最早占位处顺序铺开（只重排占位片段，
 *   用户已摆放的片段不动）；音频占位按原 start 直接定位不重排
 * - 取整纪律：光标累计不逐级取整、仅输出取整，避免多片段累积漂移
 * ===================================================== */

import { type EditorClip, type EditorDocument } from './editor-types'

function round3(v: number): number {
  return Math.round(v * 1000) / 1000
}

/** healed：占位片段 id → 探测到的媒体时长（秒）；未命中的片段原样保留 */
export function reflowPlaceholders(doc: EditorDocument, healed: Map<string, number>): EditorClip[] {
  if (!healed.size) return doc.clips
  const videoTrackIds = new Set(doc.tracks.filter((t) => t.kind === 'video').map((t) => t.id))

  const filled = new Map<string, EditorClip>()
  const placeholdersByTrack = new Map<string, EditorClip[]>()
  for (const clip of doc.clips) {
    const duration = healed.get(clip.id)
    if (duration === undefined) continue
    const filledClip = { ...clip, duration: round3(duration) }
    filled.set(clip.id, filledClip)
    if (videoTrackIds.has(clip.trackId)) {
      const list = placeholdersByTrack.get(clip.trackId) ?? []
      list.push(filledClip)
      placeholdersByTrack.set(clip.trackId, list)
    }
  }
  if (!filled.size) return doc.clips

  const newStart = new Map<string, number>()
  for (const list of placeholdersByTrack.values()) {
    list.sort((a, b) => a.start - b.start)
    let cursor = Math.max(0, list[0].start)
    for (const clip of list) {
      newStart.set(clip.id, cursor)
      cursor += clip.duration
    }
  }

  return doc.clips.map((clip) => {
    const filledClip = filled.get(clip.id)
    if (!filledClip) return clip
    const start = newStart.get(clip.id)
    return start === undefined ? filledClip : { ...filledClip, start: round3(start) }
  })
}
