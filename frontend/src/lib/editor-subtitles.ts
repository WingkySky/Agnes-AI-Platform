/* =====================================================
 * 字幕工作区草稿组装（纯函数）
 * - 转写/SRT 导入的草稿行 → rebuildSubtitleClips 的 cue 列表
 * - 草稿时间是时间线域时间（whisper 时间戳与语音对齐，SRT 导入自带时间基），
 *   追加语义 = 既有 cue 保留、草稿原位合并，不做平移
 * ===================================================== */

export interface SubtitleDraftRow {
  start: number
  end: number
  text: string
}

export interface SubtitleCue {
  id: string
  start: number
  duration: number
  text: string
}

/** 草稿 → cue 列表（id 由调用方注入生成器，保证与 store.newId 同源） */
export function draftToCues(draft: SubtitleDraftRow[], newId: () => string): SubtitleCue[] {
  return draft.map((d) => ({
    id: newId(),
    start: d.start,
    duration: Math.max(d.end - d.start, 0),
    text: d.text,
  }))
}

/** 追加：既有字幕片段与草稿 cue 按 start 合并排序（既有 id/时间不动） */
export function mergeSubtitleCues(
  existing: Array<{ id: string; start: number; duration: number; text?: string }>,
  draftCues: SubtitleCue[],
): SubtitleCue[] {
  const base = existing.map((c) => ({ id: c.id, start: c.start, duration: c.duration, text: c.text ?? '' }))
  return [...base, ...draftCues].sort((a, b) => a.start - b.start)
}
