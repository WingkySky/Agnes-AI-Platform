/* AI 粗剪纯函数：segments → addClip 载荷（顺序排布 + trim 映射 + 碎段过滤） */

import { describe, it, expect } from 'vitest'
import { segmentsToClips, segmentsDuration } from '../editor-rough-cut'

const idFn = (p: string) => `${p}_1`

describe('segmentsToClips', () => {
  it('顺序排布：start 逐段推进，duration=段长，trimStart=段起点', () => {
    const clips = segmentsToClips(
      [{ start: 0, end: 3.1 }, { start: 3.1, end: 6.1 }, { start: 6.1, end: 9 }],
      { trackId: 'v1', assetId: 7, offset: 0 },
      idFn,
    )
    expect(clips.map((c) => [c.start, c.duration, c.trimStart])).toEqual([
      [0, 3.1, 0], [3.1, 3.0, 3.1], [6.1, 2.9, 6.1],
    ])
    expect(clips.every((c) => c.trackId === 'v1' && c.assetId === 7)).toBe(true)
  })

  it('offset 从轨尾继续排布；碎段（< minSeg）过滤', () => {
    const clips = segmentsToClips(
      [{ start: 2, end: 4 }, { start: 4, end: 4.1 }, { start: 8, end: 10 }],
      { trackId: 'a1', assetId: 3, offset: 12, minSeg: 0.5 },
      idFn,
    )
    expect(clips.map((c) => [c.start, c.duration, c.trimStart])).toEqual([
      [12, 2, 2], [14, 2, 8],
    ])
  })

  it('空段 → 空 clips', () => {
    expect(segmentsToClips([], { trackId: 'v1', assetId: 1 }, idFn)).toEqual([])
  })
})

describe('segmentsDuration', () => {
  it('求和保留总时长', () => {
    expect(segmentsDuration([{ start: 0, end: 3 }, { start: 5, end: 9 }])).toBeCloseTo(7)
  })
})
