/* fitNodeToMedia 单测：保宽定高、上下限钳制、已贴合免触发；SRT 格式化与往返 */

import { describe, it, expect } from 'vitest'
import { fitNodeToMedia, formatSrtCues, parseSrt } from '../canvas-media'

const MAX_H = 560
const MIN_H = 160

describe('fitNodeToMedia', () => {
  it('尺寸非法返回 null', () => {
    expect(fitNodeToMedia(340, 240, 0, 100, MAX_H, MIN_H)).toBeNull()
    expect(fitNodeToMedia(340, 0, 100, 100, MAX_H, MIN_H)).toBeNull()
  })

  it('方图保宽定高：340×240 → 340×340', () => {
    expect(fitNodeToMedia(340, 240, 1024, 1024, MAX_H, MIN_H)).toEqual({ width: 340, height: 340 })
  })

  it('16:9 图保宽定高：340×240 → 340×191', () => {
    expect(fitNodeToMedia(340, 240, 1920, 1080, MAX_H, MIN_H)).toEqual({ width: 340, height: 191 })
  })

  it('9:16 竖版超上限锁高反算宽：340 宽 → 315×560', () => {
    expect(fitNodeToMedia(340, 240, 1080, 1920, MAX_H, MIN_H)).toEqual({ width: 315, height: 560 })
  })

  it('超宽全景低于下限锁高反算宽：340 宽 → 800×160', () => {
    expect(fitNodeToMedia(340, 240, 2500, 500, MAX_H, MIN_H)).toEqual({ width: 800, height: 160 })
  })

  it('框体比例已与媒体一致时返回 null（不触发无意义的 store 更新）', () => {
    expect(fitNodeToMedia(340, 340, 1024, 1024, MAX_H, MIN_H)).toBeNull()
    expect(fitNodeToMedia(315, 560, 1080, 1920, MAX_H, MIN_H)).toBeNull()
  })

  it('比例误差在 1% 内视为已贴合', () => {
    expect(fitNodeToMedia(341, 192, 1920, 1080, MAX_H, MIN_H)).toBeNull()
  })
})

describe('formatSrtCues / parseSrt 往返', () => {
  it('格式化输出标准 SRT 块（序号 + 逗号毫秒时间轴）', () => {
    const srt = formatSrtCues([
      { start_time: 1.5, duration: 2, text: '第一句' },
      { start_time: 0, duration: 1, text: '开头' },
    ])
    expect(srt).toBe('1\n00:00:00,000 --> 00:00:01,000\n开头\n\n2\n00:00:01,500 --> 00:00:03,500\n第一句')
  })

  it('毫秒边界进位正确（999.9ms 不产出 1000）', () => {
    const srt = formatSrtCues([{ start_time: 0.9999, duration: 1.0001, text: 'x' }])
    expect(srt).toContain('00:00:01,000 --> 00:00:02,000')
  })

  it('与 parseSrt 往返一致（含 , 毫秒分隔与多行文本）', () => {
    const sample = '1\n00:00:01,500 --> 00:00:03,000\nHello\nWorld\n\n2\n00:00:04,000 --> 00:00:05,250\n第二句'
    const cues = parseSrt(sample)
    expect(cues).toEqual([
      { start_time: 1.5, duration: 1.5, text: 'Hello\nWorld' },
      { start_time: 4, duration: 1.25, text: '第二句' },
    ])
    expect(parseSrt(formatSrtCues(cues))).toEqual(cues)
  })
})
