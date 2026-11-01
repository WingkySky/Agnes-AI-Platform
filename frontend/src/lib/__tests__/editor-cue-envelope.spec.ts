/* 音量包络插值 + splitClip 包络重映射 + 逐 cue 样式合并 单测 */
import { describe, it, expect } from 'vitest'
import { clipGainAt, volumeEnvelopeAt, clipFadeAlphaAt } from '@/lib/editor-audio'
import { applyCommand, cmd } from '@/lib/editor-commands'
import { EMPTY_TRACK_FLAGS, type EditorClip, type EditorDocument } from '@/lib/editor-types'

function baseDoc(): EditorDocument {
  return {
    timebase: 30, width: 1280, height: 720,
    tracks: [
      { id: 'v1', kind: 'video', order: 0, flags: { ...EMPTY_TRACK_FLAGS } },
      { id: 'a1', kind: 'audio', order: 0, flags: { ...EMPTY_TRACK_FLAGS } },
      { id: 's1', kind: 'subtitle', order: 0, flags: { ...EMPTY_TRACK_FLAGS } },
    ],
    clips: [
      { id: 'c1', trackId: 'v1', assetId: 1, start: 0, duration: 4, trimStart: 0, props: {} },
      { id: 't1', trackId: 's1', assetId: null, start: 0.5, duration: 2, trimStart: 0, props: {}, text: '你好' },
    ],
  }
}

const envClip = (points: Array<{ t: number; v: number }>): EditorClip => ({
  id: 'c', trackId: 'v1', assetId: 1, start: 2, duration: 4, trimStart: 0,
  props: { volumePoints: points },
})

describe('volumeEnvelopeAt / clipGainAt', () => {
  it('无包络恒 1；段外持端点值', () => {
    const plain = envClip([])
    expect(volumeEnvelopeAt(plain, 0)).toBe(1)
    expect(volumeEnvelopeAt(plain, 99)).toBe(1)
    const pts = envClip([{ t: 0.25, v: 1.0 }, { t: 0.75, v: 0.2 }])
    expect(volumeEnvelopeAt(pts, 2)).toBe(1.0)   // 片段起点（frac 0）持左端点
    expect(volumeEnvelopeAt(pts, 6)).toBe(0.2)   // 片段终点（frac 1）持右端点
  })

  it('线性插值：t=0.5 处两点中点 (1.0+0.2)/2', () => {
    const pts = envClip([{ t: 0.25, v: 1.0 }, { t: 0.75, v: 0.2 }])
    expect(volumeEnvelopeAt(pts, 4)).toBeCloseTo(0.6, 6) // now=4s → frac 0.5
  })

  it('clipGainAt = volume × 包络 × fadeAlpha', () => {
    const clip = envClip([{ t: 0, v: 1 }, { t: 1, v: 1 }])
    clip.props.volume = 0.5
    clip.props.fadeIn = 2 // 前 2s fade 楔子
    expect(clipGainAt(clip, 5)).toBeCloseTo(0.5, 6)  // frac 0.75→env 1, fade 1（(5-2)/2 钳 1）
    expect(clipGainAt(clip, 3)).toBeCloseTo(0.25, 6) // fade 0.5 × env 1 × volume 0.5
  })
})

describe('splitClip 新语义（属性继承+包络重映射+fade 拆分）', () => {
  it('包络点按切分比例重映射；fade 按半段归属拆分', () => {
    const doc = baseDoc()
    doc.clips[0]!.props = {
      speed: 1.5,
      fadeIn: 1, fadeOut: 1,
      volumePoints: [{ t: 0.2, v: 1.5 }, { t: 0.6, v: 0.5 }, { t: 0.8, v: 1.0 }],
    }
    const next = applyCommand(doc, cmd('splitClip', { clipId: 'c1', at: 2, newId: 'c2' })) // 切在 0.5
    const first = next.clips.find((c) => c.id === 'c1')!
    const second = next.clips.find((c) => c.id === 'c2')!
    // 前半：speed 继承、fadeOut 删、包络 [0,0.5] 内点重映射（t 0.2→0.4）
    expect(first.props.speed).toBe(1.5)
    expect(first.props.fadeOut).toBeUndefined()
    expect(first.props.fadeIn).toBe(1)
    expect(first.props.volumePoints).toEqual([{ t: 0.4, v: 1.5 }])
    // 后半：fadeIn 删、fadeOut 继承、包络 [0.5,1] 内点重映射（0.6→0.2、0.8→0.6）
    expect(second.props.speed).toBe(1.5)
    expect(second.props.fadeIn).toBeUndefined()
    expect(second.props.fadeOut).toBe(1)
    expect(second.props.volumePoints).toEqual([{ t: 0.2, v: 0.5 }, { t: 0.6, v: 1.0 }])
  })

  it('无包络无 fade：split 后两半 props 相等（继承）', () => {
    const doc = baseDoc()
    doc.clips[0]!.props = { volume: 0.8 }
    const next = applyCommand(doc, cmd('splitClip', { clipId: 'c1', at: 2, newId: 'c2' }))
    expect(next.clips.find((c) => c.id === 'c2')!.props).toEqual({ volume: 0.8 })
  })
})

describe('setClipProperty style / volumePoints', () => {
  it('style 增量合并进既有 style；内键 null 删除', () => {
    const doc = baseDoc()
    let next = applyCommand(doc, cmd('setClipProperty', { clipId: 't1', props: { style: { color: '#FF0000', size: 24 } } }))
    expect(next.clips.find((c) => c.id === 't1')!.props.style).toEqual({ color: '#FF0000', size: 24 })
    next = applyCommand(next, cmd('setClipProperty', { clipId: 't1', props: { style: { color: null } } }))
    expect(next.clips.find((c) => c.id === 't1')!.props.style).toEqual({ size: 24 })
  })

  it('style 全内键删空后整键删除；fail-closed 非法键/值', () => {
    let doc = baseDoc()
    doc = applyCommand(doc, cmd('setClipProperty', { clipId: 't1', props: { style: { color: '#FF0000' } } }))
    doc = applyCommand(doc, cmd('setClipProperty', { clipId: 't1', props: { style: { color: null } } }))
    expect(doc.clips.find((c) => c.id === 't1')!.props.style).toBeUndefined()
    expect(() => applyCommand(doc, cmd('setClipProperty', { clipId: 't1', props: { style: { color: 'red' } } }))).toThrow(/invalid_payload/)
    expect(() => applyCommand(doc, cmd('setClipProperty', { clipId: 't1', props: { style: { font: '   ' } } }))).toThrow(/invalid_payload/)
  })

  it('volumePoints 校验：t 升序/值域/点数', () => {
    const doc = baseDoc()
    const ok = applyCommand(doc, cmd('setClipProperty', { clipId: 'c1', props: { volumePoints: [{ t: 0.25, v: 1.2 }, { t: 0.75, v: 0.3 }] } }))
    expect(ok.clips.find((c) => c.id === 'c1')!.props.volumePoints).toEqual([{ t: 0.25, v: 1.2 }, { t: 0.75, v: 0.3 }])
    expect(() => applyCommand(doc, cmd('setClipProperty', { clipId: 'c1', props: { volumePoints: [{ t: 0.8, v: 1 }, { t: 0.5, v: 1 }] } }))).toThrow(/invalid_payload/)
    expect(() => applyCommand(doc, cmd('setClipProperty', { clipId: 'c1', props: { volumePoints: [{ t: 1.2, v: 1 }] } }))).toThrow(/invalid_payload/)
  })
})

describe('clipFadeAlphaAt 不受包络影响', () => {
  it('fade 纯楔子（渲染端 afade 链序相乘语义对齐）', () => {
    const clip = envClip([{ t: 0, v: 0 }])
    clip.props.fadeIn = 2
    expect(clipFadeAlphaAt(clip, 3)).toBe(0.5)
    expect(volumeEnvelopeAt(clip, 3)).toBe(0) // 包络独立计算
  })
})

describe('setSubtitleStyle / style.font', () => {
  it('工程字幕样式整体替换 + fail-closed', () => {
    let doc = baseDoc()
    doc = applyCommand(doc, cmd('setSubtitleStyle', { style: { font: 'Noto Serif CJK SC', size: 56, color: '#FFEE00', outline: false, position: 'top' } }))
    expect(doc.subtitleStyle).toEqual({ font: 'Noto Serif CJK SC', size: 56, color: '#FFEE00', outline: false, position: 'top' })
    expect(() => applyCommand(doc, cmd('setSubtitleStyle', { style: { font: '', size: 48, color: '#FFFFFF', outline: true, position: 'bottom' } }))).toThrow(/invalid_payload/)
    expect(() => applyCommand(doc, cmd('setSubtitleStyle', { style: { font: 'F', size: 300, color: '#FFFFFF', outline: true, position: 'bottom' } }))).toThrow(/invalid_payload/)
  })

  it('逐 cue style.font 校验 + 特殊字符清洗', () => {
    let doc = baseDoc()
    doc = applyCommand(doc, cmd('setClipProperty', { clipId: 't1', props: { style: { font: 'Noto Serif CJK SC' } } }))
    expect(doc.clips.find((c) => c.id === 't1')!.props.style!.font).toBe('Noto Serif CJK SC')
    doc = applyCommand(doc, cmd('setClipProperty', { clipId: 't1', props: { style: { font: '  Fancy{Font}\\' } } }))
    expect(doc.clips.find((c) => c.id === 't1')!.props.style!.font).toBe('FancyFont')
    expect(() => applyCommand(doc, cmd('setClipProperty', { clipId: 't1', props: { style: { font: '' } } }))).toThrow(/invalid_payload/)
  })
})
