/* =====================================================
 * 画布媒体工具
 * - compose 节点把上游 SRT 文本节点解析回片段数组供合成烧录
 * ===================================================== */

import type { CanvasSubtitleSegment } from '@/api/canvas'

/** SRT 时间 "00:00:01,500" → 秒 */
function srtTimeToSeconds(value: string): number {
  const m = value.trim().match(/(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})/)
  if (!m) return 0
  return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]) + Number(m[4]) / 1000
}

/** 解析 SRT 文本为字幕片段数组（start_time / duration / text） */
export function parseSrt(srt: string): CanvasSubtitleSegment[] {
  const segments: CanvasSubtitleSegment[] = []
  const blocks = (srt || '').replace(/\r\n/g, '\n').trim().split(/\n{2,}/)
  for (const block of blocks) {
    const lines = block.split('\n').filter((l) => l.trim() !== '')
    const timeLineIdx = lines.findIndex((l) => l.includes('-->'))
    if (timeLineIdx < 0) continue
    const [startStr, endStr] = lines[timeLineIdx].split('-->')
    const start = srtTimeToSeconds(startStr)
    const end = srtTimeToSeconds(endStr)
    const text = lines.slice(timeLineIdx + 1).join('\n').trim()
    if (!text) continue
    segments.push({ start_time: start, duration: Math.max(0.1, end - start), text })
  }
  return segments
}
