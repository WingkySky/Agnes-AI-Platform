/* =====================================================
 * 预览音频引擎纯函数测试
 * - audibleSpans：出声片段规则（轨类型/静音/音画分离/窗口裁剪）
 * - sourceTimeAt / timelineTimeAt：变速时间映射
 * - gainBreakpoints：fade 断点内插与端点取值
 * ===================================================== */

import { describe, expect, it } from 'vitest'

import { audibleSpans, gainBreakpoints, sourceTimeAt, timelineTimeAt } from '@/lib/editor-audio-engine'
import type { EditorClip, EditorDocument, EditorTrack, TrackFlag, TrackKind } from '@/lib/editor-types'

function track(id: string, kind: TrackKind, order = 0, flag: TrackFlag | null = null): EditorTrack {
  return { id, kind, order, flag }
}

function clip(id: string, trackId: string, start: number, duration: number, props: EditorClip['props'] = {}, assetId: number | null = 1): EditorClip {
  return { id, trackId, assetId, start, duration, trimStart: 0, props }
}

function doc(tracks: EditorTrack[], clips: EditorClip[]): EditorDocument {
  return { timebase: 30, width: 1920, height: 1080, tracks, clips }
}

describe('audibleSpans', () => {
  it('音频轨与视频轨片段出声，字幕轨不出声', () => {
    const d = doc(
      [track('tA', 'audio'), track('tV', 'video'), track('tS', 'subtitle')],
      [
        clip('ca', 'tA', 0, 4),
        clip('cv', 'tV', 0, 4),
        clip('cs', 'tS', 0, 4),
      ],
    )
    const spans = audibleSpans(d, 0, 10)
    expect(spans.map((s) => s.clip.id)).toEqual(['ca', 'cv'])
  })

  it('音频轨 muted flag 排除；视频片段 props.muted（音画分离源）排除', () => {
    const d = doc(
      [track('tA', 'audio', 0, 'muted'), track('tV', 'video')],
      [
        clip('ca', 'tA', 0, 4),
        clip('cv', 'tV', 0, 4, { muted: true }),
        clip('cv2', 'tV', 4, 4),
      ],
    )
    const spans = audibleSpans(d, 0, 10)
    expect(spans.map((s) => s.clip.id)).toEqual(['cv2'])
  })

  it('assetId 为空（未绑定素材）不出声', () => {
    const d = doc([track('tA', 'audio')], [clip('ca', 'tA', 0, 4, {}, null)])
    expect(audibleSpans(d, 0, 10)).toEqual([])
  })

  it('窗口裁剪：窗口与片段部分相交', () => {
    const d = doc([track('tA', 'audio')], [clip('ca', 'tA', 2, 4)])
    expect(audibleSpans(d, 0, 4)).toEqual([{ clip: d.clips[0]!, from: 2, to: 4 }])
    expect(audibleSpans(d, 4, 8)).toEqual([{ clip: d.clips[0]!, from: 4, to: 6 }])
    expect(audibleSpans(d, 10, 12)).toEqual([])
  })
})

describe('变速时间映射', () => {
  it('原速往返一致', () => {
    const c = clip('c', 't', 10, 4)
    c.trimStart = 5
    expect(sourceTimeAt(c, 12)).toBe(7)
    expect(timelineTimeAt(c, 7)).toBe(12)
  })
  it('speed=2：源内跨度是时间线跨度的 2 倍', () => {
    const c = clip('c', 't', 10, 2, { speed: 2 })
    c.trimStart = 5
    expect(sourceTimeAt(c, 11)).toBe(7)
    expect(timelineTimeAt(c, 7)).toBe(11)
  })
  it('speed=0.5：减速', () => {
    const c = clip('c', 't', 10, 4, { speed: 0.5 })
    c.trimStart = 5
    expect(sourceTimeAt(c, 11)).toBe(5.5)
    expect(timelineTimeAt(c, 5.5)).toBe(11)
  })
})

describe('gainBreakpoints', () => {
  it('无 fade：仅端点，值为 volume', () => {
    const c = clip('c', 't', 0, 4, { volume: 0.5 })
    const pts = gainBreakpoints(c, 1, 3)
    expect(pts).toEqual([
      { t: 1, v: 0.5 },
      { t: 3, v: 0.5 },
    ])
  })
  it('fadeIn 断点落在窗口内时插入', () => {
    const c = clip('c', 't', 0, 4, { fadeIn: 2 })
    const pts = gainBreakpoints(c, 1, 3)
    expect(pts.map((p) => p.t)).toEqual([1, 2, 3])
    expect(pts.map((p) => p.v)).toEqual([0.5, 1, 1])
  })
  it('fadeOut 断点落在窗口内时插入', () => {
    const c = clip('c', 't', 0, 4, { fadeOut: 2 })
    const pts = gainBreakpoints(c, 1, 3)
    expect(pts.map((p) => p.t)).toEqual([1, 2, 3])
    expect(pts.map((p) => p.v)).toEqual([1, 1, 0.5])
  })
  it('窗口截住 fade 起点：from 点取包络值（起播即正确渐入）', () => {
    const c = clip('c', 't', 0, 4, { fadeIn: 4 })
    const pts = gainBreakpoints(c, 1, 2)
    expect(pts).toEqual([
      { t: 1, v: 0.25 },
      { t: 2, v: 0.5 },
    ])
  })
})
