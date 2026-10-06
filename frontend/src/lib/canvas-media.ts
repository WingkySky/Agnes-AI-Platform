/* =====================================================
 * 画布媒体工具
 * - compose 节点把上游 SRT 文本节点解析回片段数组供合成烧录
 * - 媒体节点框体按素材真实比例适配（保宽定高）
 * ===================================================== */

import type { CanvasSubtitleSegment } from '@/api/canvas'

export interface NodeFitSize {
  width: number
  height: number
}

/**
 * 计算节点框体适配媒体真实比例后的尺寸（保宽定高 + 高度上下限钳制）。
 * 框体比例与媒体比例已一致（误差 < 1%）或尺寸非法时返回 null，表示无需调整。
 * 上下限钳制时反算另一维，保证钳制后框体比例仍与媒体一致（不会二次触发）。
 */
export function fitNodeToMedia(
  frameWidth: number,
  frameHeight: number,
  naturalWidth: number,
  naturalHeight: number,
  maxHeight: number,
  minHeight: number,
): NodeFitSize | null {
  if (!frameWidth || !frameHeight || !naturalWidth || !naturalHeight) return null
  const mediaRatio = naturalWidth / naturalHeight
  const frameRatio = frameWidth / frameHeight
  if (Math.abs(frameRatio - mediaRatio) / mediaRatio < 0.01) return null
  let width = frameWidth
  let height = width / mediaRatio
  if (height > maxHeight) {
    height = maxHeight
    width = height * mediaRatio
  }
  if (height < minHeight) {
    height = minHeight
    width = height * mediaRatio
  }
  return { width: Math.round(width), height: Math.round(height) }
}

/** SRT 时间 "00:00:01,500" → 秒 */
function srtTimeToSeconds(value: string): number {
  const m = value.trim().match(/(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})/)
  if (!m) return 0
  return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]) + Number(m[4]) / 1000
}

/** 秒 → SRT 时间 "00:00:01,500" */
function srtSecondsToTime(total: number): string {
  const totalMs = Math.max(0, Math.round(total * 1000))
  const p2 = (n: number) => String(n).padStart(2, '0')
  return `${p2(Math.floor(totalMs / 3600000))}:${p2(Math.floor((totalMs % 3600000) / 60000))}:${p2(Math.floor((totalMs % 60000) / 1000))},${String(totalMs % 1000).padStart(3, '0')}`
}

/** 字幕片段数组 → SRT 文本（parseSrt 的对称输出，按 start_time 排序） */
export function formatSrtCues(segments: CanvasSubtitleSegment[]): string {
  return [...segments]
    .sort((a, b) => a.start_time - b.start_time)
    .map((seg, i) => `${i + 1}\n${srtSecondsToTime(seg.start_time)} --> ${srtSecondsToTime(seg.start_time + seg.duration)}\n${seg.text}`)
    .join('\n\n')
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
