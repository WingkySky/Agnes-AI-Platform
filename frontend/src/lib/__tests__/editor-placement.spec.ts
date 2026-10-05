/* =====================================================
 * 轨道放置解析纯函数测试
 * - 半开区间碰撞判定（贴边不冲突）/ 排除自身 / 空闲轨回退
 * ===================================================== */

import { describe, expect, it } from 'vitest'

import { canPlaceOnTrack, findFreeTrack, spansOverlap } from '@/lib/editor-placement'
import type { EditorDocument } from '@/lib/editor-types'

function baseDoc(): EditorDocument {
  return {
    timebase: 30,
    width: 1280,
    height: 720,
    tracks: [
      { id: 'v1', kind: 'video', order: 0, flag: null },
      { id: 'v2', kind: 'video', order: 1, flag: 'locked' },
      { id: 'v3', kind: 'video', order: 2, flag: null },
      { id: 'a1', kind: 'audio', order: 0, flag: null },
    ],
    clips: [
      { id: 'c1', trackId: 'v1', assetId: 1, start: 0, duration: 4, trimStart: 0, props: {} },
      { id: 'c2', trackId: 'v1', assetId: 2, start: 4, duration: 3, trimStart: 0, props: {} },
    ],
  }
}

describe('spansOverlap', () => {
  it('半开区间相交判定：贴边不算、相交才算', () => {
    expect(spansOverlap(0, 4, 4, 7)).toBe(false)
    expect(spansOverlap(0, 4, 3.9, 7)).toBe(true)
    expect(spansOverlap(0, 4, -1, 0.5)).toBe(true)
    expect(spansOverlap(0, 4, 4.5, 5)).toBe(false)
  })
})

describe('canPlaceOnTrack', () => {
  it('占用区间内拒绝；排除自身后放行；空档放行', () => {
    const clips = baseDoc().clips
    expect(canPlaceOnTrack(clips, { start: 2, duration: 3 })).toBe(false)
    expect(canPlaceOnTrack(clips, { start: 4, duration: 3, excludeClipId: 'c2' })).toBe(true)
    expect(canPlaceOnTrack(clips, { start: 7, duration: 2 })).toBe(true)
    expect(canPlaceOnTrack([], { start: 0, duration: 10 })).toBe(true)
  })
})

describe('findFreeTrack', () => {
  it('回退同类型第一个可放置的解锁轨；锁定轨跳过；无可用返回 null', () => {
    const doc = baseDoc()
    // v1 该段被占、v2 锁定 → 回退 v3
    expect(findFreeTrack(doc, 'video', { start: 1, duration: 2 })?.id).toBe('v3')
    // v1 有贴边空档 → 命中 v1
    expect(findFreeTrack(doc, 'video', { start: 7, duration: 2 })?.id).toBe('v1')
    // 音频轨独占命中 a1；音频轨被占满后无处可放 → null
    expect(findFreeTrack(doc, 'audio', { start: 5, duration: 2 })?.id).toBe('a1')
    const occupied = {
      ...doc,
      clips: [...doc.clips, { id: 'm1', trackId: 'a1', assetId: 9, start: 0, duration: 5, trimStart: 0, props: {} }],
    }
    expect(findFreeTrack(occupied, 'audio', { start: 1, duration: 2 })).toBeNull()
  })
})
