/* =====================================================
 * 预览合成器 planFrame 纯函数测试
 * - 轨序（order 大=上层）、hidden 跳过、激活判定、rect→像素换算
 * ===================================================== */

import { describe, expect, it } from 'vitest'

import { planFrame } from '@/lib/editor-compositor'
import type { EditorClip, EditorDocument, EditorTrack } from '@/lib/editor-types'

function track(id: string, kind: EditorTrack['kind'], order: number, flag: EditorTrack['flag'] = null): EditorTrack {
  return { id, kind, order, flag }
}

function clip(id: string, trackId: string, start: number, duration: number, props: EditorClip['props'] = {}, assetId: number | null = 1): EditorClip {
  return { id, trackId, assetId, start, duration, trimStart: 0, props }
}

function doc(tracks: EditorTrack[], clips: EditorClip[]): EditorDocument {
  return { timebase: 30, width: 1920, height: 1080, tracks, clips }
}

describe('planFrame', () => {
  it('按轨 order 自底向上，只含激活片段', () => {
    const d = doc(
      [track('tTop', 'video', 1), track('tBase', 'video', 0)],
      [
        clip('top', 'tTop', 0, 4, {}, 2),
        clip('base', 'tBase', 0, 4, {}, 1),
      ],
    )
    expect(planFrame(d, 2, 1920, 1080)).toEqual([
      { clipId: 'base', assetId: 1, x: 0, y: 0, w: 1920, h: 1080 },
      { clipId: 'top', assetId: 2, x: 0, y: 0, w: 1920, h: 1080 },
    ])
  })

  it('hidden 轨跳过；播放头不在片段内跳过', () => {
    const d = doc(
      [track('tH', 'video', 1, 'hidden'), track('tV', 'video', 0)],
      [
        clip('hid', 'tH', 0, 4),
        clip('before', 'tV', 4, 2),
      ],
    )
    expect(planFrame(d, 1, 1920, 1080)).toEqual([])
  })

  it('rect 换算为 stage 像素（PIP）', () => {
    const d = doc(
      [track('tV', 'video', 0)],
      [clip('pip', 'tV', 0, 4, { rect: { x: 0.5, y: 0.25, w: 0.5, h: 0.5 } })],
    )
    expect(planFrame(d, 1, 200, 100)).toEqual([
      { clipId: 'pip', assetId: 1, x: 100, y: 25, w: 100, h: 50 },
    ])
  })

  it('assetId 为空的片段跳过；音频/字幕轨永不进清单', () => {
    const d = doc(
      [track('tV', 'video', 0), track('tA', 'audio', 0), track('tS', 'subtitle', 0)],
      [
        clip('novideo', 'tV', 0, 4, {}, null),
        clip('audio', 'tA', 0, 4),
        clip('sub', 'tS', 0, 4),
      ],
    )
    expect(planFrame(d, 1, 1920, 1080)).toEqual([])
  })
})
