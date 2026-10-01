/* fitNodeToMedia 单测：保宽定高、上下限钳制、已贴合免触发 */

import { describe, it, expect } from 'vitest'
import { fitNodeToMedia } from '../canvas-media'

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
