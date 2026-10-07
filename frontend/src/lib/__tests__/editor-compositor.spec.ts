/* =====================================================
 * 预览合成器 planFrame 纯函数测试
 * - 轨序（order 大=上层）、hidden 跳过、激活判定、rect→像素换算
 * - 画中画直接操作几何：拾取/角点命中/移动钳制/缩放锚定
 * ===================================================== */

import { describe, expect, it } from 'vitest'

import { cornerHit, moveRect, pickDrawItem, planFrame, resizeRect } from '@/lib/editor-compositor'
import type { DrawItem } from '@/lib/editor-compositor'
import { EMPTY_TRACK_FLAGS, type EditorClip, type EditorDocument, type EditorTrack, type TrackFlags } from '@/lib/editor-types'

function track(id: string, kind: EditorTrack['kind'], order: number, flags: Partial<TrackFlags> = {}): EditorTrack {
  return { id, kind, order, flags: { ...EMPTY_TRACK_FLAGS, ...flags } }
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
      [track('tH', 'video', 1, { hidden: true }), track('tV', 'video', 0)],
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

  it('转场窗口：前片段尾部追加后片段 blend 项（进度归一化）', () => {
    const t = track('tV', 'video', 0)
    t.transitions = [{ id: 'tr1', afterClipId: 'a', type: 'crossfade', duration: 1 }]
    const d = doc([t], [clip('a', 'tV', 0, 4, {}, 1), clip('b', 'tV', 4, 3, {}, 2)])
    // 窗口前：只有前段
    expect(planFrame(d, 2.5, 1920, 1080)).toEqual([
      { clipId: 'a', assetId: 1, x: 0, y: 0, w: 1920, h: 1080 },
    ])
    // 窗口内（3.5s，进度 0.5）：a 在下 + b blend 项
    expect(planFrame(d, 3.5, 1920, 1080)).toEqual([
      { clipId: 'a', assetId: 1, x: 0, y: 0, w: 1920, h: 1080 },
      { clipId: 'b', assetId: 2, x: 0, y: 0, w: 1920, h: 1080, blend: { type: 'crossfade', progress: 0.5, duration: 1 } },
    ])
    // 进度钳到 1：播放头贴衔接点
    expect(planFrame(d, 3.99, 1920, 1080)[1].blend!.progress).toBeCloseTo(0.99)
  })

  it('转场窗口外/PIP 片段/无后段不产生 blend 项', () => {
    const t = track('tV', 'video', 0)
    t.transitions = [{ id: 'tr1', afterClipId: 'a', type: 'wipe', duration: 1 }]
    // 后段是 PIP → 不混合
    const pipNext = doc([t], [
      clip('a', 'tV', 0, 4, {}, 1),
      clip('b', 'tV', 4, 3, { rect: { x: 0.5, y: 0.5, w: 0.4, h: 0.4 } }, 2),
    ])
    expect(planFrame(pipNext, 3.5, 1920, 1080)).toHaveLength(1)
    // 前段是 PIP → 不混合
    const pipPrev = doc([t], [
      clip('a', 'tV', 0, 4, { rect: { x: 0.5, y: 0.5, w: 0.4, h: 0.4 } }, 1),
      clip('b', 'tV', 4, 3, {}, 2),
    ])
    expect(planFrame(pipPrev, 3.5, 1920, 1080)).toHaveLength(1)
    // a 是末段（无后段）
    const last = doc([t], [clip('a', 'tV', 0, 4, {}, 1)])
    expect(planFrame(last, 3.5, 1920, 1080)).toHaveLength(1)
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

describe('pickDrawItem', () => {
  const items: DrawItem[] = [
    { clipId: 'base', assetId: 1, x: 0, y: 0, w: 200, h: 100 },
    { clipId: 'pip', assetId: 2, x: 100, y: 25, w: 100, h: 50 },
  ]
  it('PIP 覆盖区命中顶层，其余区域命中底层', () => {
    expect(pickDrawItem(items, 150, 50)?.clipId).toBe('pip')
    expect(pickDrawItem(items, 50, 50)?.clipId).toBe('base')
  })
  it('空白处返回 null', () => {
    expect(pickDrawItem(items, 250, 50)).toBeNull()
  })
})

describe('cornerHit', () => {
  const item: DrawItem = { clipId: 'c', assetId: 1, x: 100, y: 50, w: 100, h: 50 }
  it('角点半径内命中对应角', () => {
    expect(cornerHit(item, 100, 50, 8)).toBe('nw')
    expect(cornerHit(item, 205, 105, 8)).toBe('se')
    expect(cornerHit(item, 193, 50, 8)).toBe('ne')
    expect(cornerHit(item, 100, 93, 8)).toBe('sw')
  })
  it('中心与超出半径不命中', () => {
    expect(cornerHit(item, 150, 75, 8)).toBeNull()
    expect(cornerHit(item, 120, 50, 8)).toBeNull()
  })
})

describe('moveRect', () => {
  it('自由移动', () => {
    expect(moveRect({ x: 0.2, y: 0.2, w: 0.5, h: 0.5 }, 0.1, -0.05)).toEqual({ x: 0.3, y: 0.15, w: 0.5, h: 0.5 })
  })
  it('钳制在画幅内', () => {
    expect(moveRect({ x: 0.8, y: 0.1, w: 0.5, h: 0.5 }, 0.5, 0)).toEqual({ x: 0.5, y: 0.1, w: 0.5, h: 0.5 })
    expect(moveRect({ x: 0.2, y: 0, w: 0.5, h: 0.5 }, -1, 0.9)).toEqual({ x: 0, y: 0.5, w: 0.5, h: 0.5 })
  })
})

describe('resizeRect', () => {
  it('se 角缩放：左上角锚定，等比', () => {
    const r = resizeRect({ x: 0.25, y: 0.25, w: 0.5, h: 0.25 }, 'se', 0.25, 0.125)
    expect(r).toEqual({ x: 0.25, y: 0.25, w: 0.75, h: 0.375 })
  })
  it('nw 角缩放：右下角锚定，向左上拖为放大', () => {
    const r = resizeRect({ x: 0.25, y: 0.25, w: 0.5, h: 0.25 }, 'nw', -0.25, -0.125)
    expect(r).toEqual({ x: 0, y: 0.125, w: 0.75, h: 0.375 })
  })
  it('钳制画幅边界：se 拖出右边按对角锚定收敛', () => {
    const r = resizeRect({ x: 0.5, y: 0.5, w: 0.5, h: 0.5 }, 'se', 2, 2)
    expect(r).toEqual({ x: 0.5, y: 0.5, w: 0.5, h: 0.5 })
  })
  it('最小边长下限', () => {
    const r = resizeRect({ x: 0.25, y: 0.25, w: 0.5, h: 0.5 }, 'se', -0.9, -0.9)
    expect(r?.w).toBe(0.05)
    expect(r?.h).toBe(0.05)
  })
  it('纵横比锁定：只拖一个轴也按等比缩放', () => {
    const r = resizeRect({ x: 0, y: 0, w: 0.5, h: 0.25 }, 'se', 0.25, 0)
    expect(r).toEqual({ x: 0, y: 0, w: 0.75, h: 0.375 })
  })
})
