/* =====================================================
 * 字幕工作区草稿组装纯函数测试
 * ===================================================== */

import { describe, expect, it } from 'vitest'

import { draftToCues, mergeSubtitleCues } from '@/lib/editor-subtitles'

describe('draftToCues', () => {
  it('草稿行转 cue：id 注入、duration=end-start', () => {
    let n = 0
    const cues = draftToCues(
      [
        { start: 1, end: 2.5, text: '你好' },
        { start: 3, end: 4, text: '世界' },
      ],
      () => `sub${++n}`,
    )
    expect(cues).toEqual([
      { id: 'sub1', start: 1, duration: 1.5, text: '你好' },
      { id: 'sub2', start: 3, duration: 1, text: '世界' },
    ])
  })
  it('end < start 时 duration 钳 0（不产生负时长）', () => {
    const cues = draftToCues([{ start: 3, end: 2, text: 'x' }], () => 'a')
    expect(cues[0]!.duration).toBe(0)
  })
})

describe('mergeSubtitleCues', () => {
  it('既有 cue 保留原 id/时间，草稿按 start 合并排序', () => {
    const merged = mergeSubtitleCues(
      [
        { id: 'e2', start: 5, duration: 1, text: '既有后' },
        { id: 'e1', start: 0, duration: 2, text: '既有前' },
      ],
      [
        { id: 'd1', start: 3, duration: 1, text: '草稿' },
        { id: 'd2', start: 0.5, duration: 1, text: '更早草稿' },
      ],
    )
    expect(merged.map((c) => c.id)).toEqual(['e1', 'd2', 'd1', 'e2'])
    expect(merged[0]).toEqual({ id: 'e1', start: 0, duration: 2, text: '既有前' })
  })
  it('既有 text 缺省兜底空串', () => {
    const merged = mergeSubtitleCues([{ id: 'e1', start: 0, duration: 1 }], [])
    expect(merged[0]!.text).toBe('')
  })
})
