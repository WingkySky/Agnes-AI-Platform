/* =====================================================
 * 草稿占位补正纯函数测试
 * - duration 回填 + 视频轨顺序铺开 / 音频占位不重排 / 已摆放片段不动
 * ===================================================== */

import { describe, expect, it } from 'vitest'

import { reflowPlaceholders } from '@/lib/editor-derive'
import { EMPTY_TRACK_FLAGS, type EditorDocument } from '@/lib/editor-types'

function baseDoc(): EditorDocument {
  return {
    timebase: 30,
    width: 1280,
    height: 720,
    tracks: [
      { id: 'v1', kind: 'video', order: 0, flags: { ...EMPTY_TRACK_FLAGS } },
      { id: 'a1', kind: 'audio', order: 0, flags: { ...EMPTY_TRACK_FLAGS } },
    ],
    clips: [
      { id: 'real', trackId: 'v1', assetId: 1, start: 0, duration: 2, trimStart: 0, props: {} },
      { id: 'd2', trackId: 'v1', assetId: 2, start: 10, duration: 0, trimStart: 0, props: {} },
      { id: 'd1', trackId: 'v1', assetId: 3, start: 2, duration: 0, trimStart: 0, props: {} },
      { id: 'da', trackId: 'a1', assetId: 4, start: 5, duration: 0, trimStart: 0, props: {} },
    ],
  }
}

describe('reflowPlaceholders', () => {
  it('视频占位回填时长并从最早占位处按 start 序铺开', () => {
    const healed = new Map([['d1', 1.0004], ['d2', 2]])
    const next = reflowPlaceholders(baseDoc(), healed)
    expect(next.find((c) => c.id === 'd1')).toMatchObject({ start: 2, duration: 1 })
    // 光标累计不逐级取整：d2.start = 2 + 1.0004 → 输出取整 3
    expect(next.find((c) => c.id === 'd2')).toMatchObject({ start: 3, duration: 2 })
  })
  it('音频占位只回填时长，start 不动', () => {
    const next = reflowPlaceholders(baseDoc(), new Map([['da', 3.5]]))
    expect(next.find((c) => c.id === 'da')).toMatchObject({ start: 5, duration: 3.5 })
  })
  it('已摆放片段与其他轨片段原样保留（不可变）', () => {
    const doc = baseDoc()
    const next = reflowPlaceholders(doc, new Map([['d1', 1]]))
    expect(next.find((c) => c.id === 'real')).toBe(doc.clips[0])
    expect(doc.clips.find((c) => c.id === 'd1')?.duration).toBe(0) // 原 doc 不变
  })
  it('无回填目标时原样返回', () => {
    const doc = baseDoc()
    expect(reflowPlaceholders(doc, new Map())).toBe(doc.clips)
  })
})
