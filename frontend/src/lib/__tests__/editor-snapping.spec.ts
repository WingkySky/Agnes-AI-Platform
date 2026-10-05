/* =====================================================
 * 时间线吸附纯函数测试
 * - 阈值换算 / 候选点收集（含排除自身）/ 最近点吸附
 * ===================================================== */

import { describe, expect, it } from 'vitest'

import { buildSnapPoints, resolveSnap, snapThresholdSec } from '@/lib/editor-snapping'
import type { EditorDocument } from '@/lib/editor-types'

function baseDoc(): EditorDocument {
  return {
    timebase: 30,
    width: 1280,
    height: 720,
    tracks: [{ id: 'v1', kind: 'video', order: 0, flag: null }],
    clips: [
      { id: 'a', trackId: 'v1', assetId: 1, start: 2, duration: 3, trimStart: 0, props: {} },
      { id: 'b', trackId: 'v1', assetId: 2, start: 8, duration: 1, trimStart: 0, props: {} },
    ],
  }
}

describe('snapThresholdSec', () => {
  it('像素阈值随缩放换算成秒（放大更精确）', () => {
    expect(snapThresholdSec(80)).toBeCloseTo(0.125)
    expect(snapThresholdSec(160)).toBeCloseTo(0.0625)
    expect(snapThresholdSec(40, 5)).toBeCloseTo(0.125)
  })
})

describe('buildSnapPoints', () => {
  it('候选 = 时间 0 点 + 播放头 + 全部片段首尾边', () => {
    const pts = buildSnapPoints(baseDoc(), { playhead: 5 })
    expect(pts.map((p) => p.time).sort((a, b) => a - b)).toEqual([0, 2, 5, 5, 8, 9])
  })
  it('excludeClipId 排除手势中的自身片段', () => {
    const pts = buildSnapPoints(baseDoc(), { excludeClipId: 'a' })
    expect(pts.map((p) => p.time).sort((a, b) => a - b)).toEqual([0, 8, 9])
  })
})

describe('resolveSnap', () => {
  const pts = buildSnapPoints(baseDoc(), { playhead: 5 })
  it('阈值内吸附到最近候选', () => {
    const r = resolveSnap(5.08, pts, 0.125)
    expect(r.time).toBe(5)
    expect(r.point?.type).toBe('playhead')
  })
  it('多个候选命中取距离最小者', () => {
    expect(resolveSnap(1.95, pts, 0.125).time).toBe(2)
    expect(resolveSnap(4.92, pts, 0.125).time).toBe(5)
  })
  it('阈值外不吸附（原值返回，point=null）', () => {
    const r = resolveSnap(5.5, pts, 0.125)
    expect(r.time).toBe(5.5)
    expect(r.point).toBeNull()
  })
  it('贴边值吸附后与候选完全相等（对齐不留浮点尾巴）', () => {
    expect(resolveSnap(2.0000001, pts, 0.125).time).toBe(2)
  })
})
