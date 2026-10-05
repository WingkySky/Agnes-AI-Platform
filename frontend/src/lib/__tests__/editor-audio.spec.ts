/* =====================================================
 * 预览音频增益纯函数测试
 * - volume / fadeIn / fadeOut 包络（时间线域，变速不影响）
 * ===================================================== */

import { describe, expect, it } from 'vitest'

import { clipGainAt } from '@/lib/editor-audio'
import type { EditorClip } from '@/lib/editor-types'

function clip(props: EditorClip['props'] = {}, start = 0, duration = 4): EditorClip {
  return { id: 'c1', trackId: 'a1', assetId: 1, start, duration, trimStart: 0, props }
}

describe('clipGainAt', () => {
  it('无 fade：恒等于 volume', () => {
    expect(clipGainAt(clip(), 2)).toBe(1)
    expect(clipGainAt(clip({ volume: 0.3 }), 2)).toBeCloseTo(0.3)
  })
  it('fadeIn 线性上升，窗口内按比例', () => {
    const c = clip({ fadeIn: 2 })
    expect(clipGainAt(c, 0)).toBe(0)
    expect(clipGainAt(c, 1)).toBeCloseTo(0.5)
    expect(clipGainAt(c, 2)).toBe(1)
    expect(clipGainAt(c, 3)).toBe(1)
  })
  it('fadeOut 线性下降到片段结束', () => {
    const c = clip({ fadeOut: 2 }, 0, 4)
    expect(clipGainAt(c, 2)).toBe(1)
    expect(clipGainAt(c, 3)).toBeCloseTo(0.5)
    expect(clipGainAt(c, 4)).toBe(0)
  })
  it('双 fade 相乘；volume 提升量不钳制（由 GainNode 承载）', () => {
    const c = clip({ fadeIn: 1, fadeOut: 1, volume: 2 }, 0, 4)
    expect(clipGainAt(c, 0.5)).toBeCloseTo(1)
    expect(clipGainAt(c, 2)).toBeCloseTo(2)
    expect(clipGainAt(c, 3.5)).toBeCloseTo(1)
  })
  it('变速不影响包络（fade 在时间线域）', () => {
    const fast = clip({ fadeIn: 2, speed: 2 })
    const slow = clip({ fadeIn: 2, speed: 0.5 })
    expect(clipGainAt(fast, 1)).toBe(clipGainAt(slow, 1))
  })
  it('volume=0 静音；片段窗口外钳制为 0', () => {
    expect(clipGainAt(clip({ volume: 0 }), 1)).toBe(0)
    const c = clip({ fadeOut: 1 }, 0, 4)
    expect(clipGainAt(c, 5)).toBe(0)
  })
})
