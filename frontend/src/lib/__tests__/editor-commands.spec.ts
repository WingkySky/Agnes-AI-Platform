/* =====================================================
 * 剪辑器命令状态机黄金测试
 * - 14 op 逐个：输入 doc + payload → 期望 doc（对表）
 * - fail-closed：未知 op / 非法 payload 抛错且不改状态
 * - 回放一致性：随机命令序列 JSON 序列化 → 重放 → 结果一致
 * - history：200 层截断 / undo / redo / 分支丢弃
 * ===================================================== */

import { describe, expect, it } from 'vitest'
import {
  EDITOR_OPS,
  EditorCommandError,
  applyCommand,
  cmd,
  type EditorCommand,
} from '@/lib/editor-commands'
import { EditorHistory, MAX_HISTORY_ENTRIES } from '@/lib/editor-history'
import { EMPTY_TRACK_FLAGS, type EditorDocument } from '@/lib/editor-types'

function baseDoc(): EditorDocument {
  return {
    timebase: 30,
    width: 1280,
    height: 720,
    tracks: [
      { id: 'v1', kind: 'video', order: 0, flags: { ...EMPTY_TRACK_FLAGS } },
      { id: 'v2', kind: 'video', order: 1, flags: { ...EMPTY_TRACK_FLAGS } },
      { id: 'a1', kind: 'audio', order: 0, flags: { ...EMPTY_TRACK_FLAGS } },
      { id: 's1', kind: 'subtitle', order: 0, flags: { ...EMPTY_TRACK_FLAGS } },
    ],
    clips: [
      { id: 'c1', trackId: 'v1', assetId: 10, start: 0, duration: 4, trimStart: 1, props: {} },
      { id: 'c2', trackId: 'v1', assetId: 11, start: 4, duration: 3, trimStart: 0, props: {} },
      { id: 'p1', trackId: 'v2', assetId: 12, start: 1, duration: 2, trimStart: 0, props: { rect: { x: 0.6, y: 0.6, w: 0.3, h: 0.3 } } },
      { id: 't1', trackId: 's1', assetId: null, start: 0.5, duration: 1.5, trimStart: 0, props: {}, text: '第一句' },
    ],
    subtitleStyle: { font: 'Noto Sans CJK SC', size: 48, color: '#FFFFFF', outline: true, position: 'bottom' },
  }
}

// ---------- 逐 op 对表 ----------

describe('addClip', () => {
  it('追加片段（新数组，原数组不变）', () => {
    const doc = baseDoc()
    const next = applyCommand(doc, cmd('addClip', {
      clip: { id: 'c3', trackId: 'a1', assetId: 20, start: 0, duration: 2, trimStart: 0, props: {} },
    }))
    expect(next.clips.map((c) => c.id)).toEqual(['c1', 'c2', 'p1', 't1', 'c3'])
    expect(doc.clips.map((c) => c.id)).toEqual(['c1', 'c2', 'p1', 't1']) // 不可变
  })
  it('duration=0 占位合法（草稿契约，healDurations/渲染 Plan 兜底）', () => {
    const next = applyCommand(baseDoc(), cmd('addClip', {
      clip: { id: 'c4', trackId: 'v1', assetId: 21, start: 9, duration: 0, trimStart: 0, props: {} },
    }))
    expect(next.clips.find((c) => c.id === 'c4')?.duration).toBe(0)
  })
  it('负 duration → 抛错', () => {
    expect(() => applyCommand(baseDoc(), cmd('addClip', {
      clip: { id: 'c9', trackId: 'v1', start: 9, duration: -1 },
    }))).toThrow(/invalid_payload/)
  })
  it('重复 id / 轨道不存在 / 锁定轨 → 抛错', () => {
    const doc = baseDoc()
    const locked = applyCommand(doc, cmd('setTrackFlags', { trackId: 'v1', flags: { locked: true } }))
    expect(() => applyCommand(doc, cmd('addClip', { clip: { id: 'c1', trackId: 'v1', start: 9, duration: 1 } })))
      .toThrow(EditorCommandError)
    expect(() => applyCommand(locked, cmd('addClip', { clip: { id: 'c9', trackId: 'v1', start: 9, duration: 1 } })))
      .toThrow(/track_locked/)
    expect(() => applyCommand(doc, cmd('addClip', { clip: { id: 'c9', trackId: 'vx', start: 9, duration: 1 } })))
      .toThrow(/track_not_found/)
  })
})

describe('moveClip', () => {
  it('同轨移动 + 跨轨移动（同 kind）', () => {
    const doc = baseDoc()
    const moved = applyCommand(doc, cmd('moveClip', { clipId: 'p1', start: 2.5 }))
    expect(moved.clips.find((c) => c.id === 'p1')).toMatchObject({ start: 2.5, trackId: 'v2' })
    const cross = applyCommand(doc, cmd('moveClip', { clipId: 'p1', trackId: 'v1', start: 8 }))
    expect(cross.clips.find((c) => c.id === 'p1')).toMatchObject({ start: 8, trackId: 'v1' })
  })
  it('跨 kind 移动 → 抛错', () => {
    const doc = baseDoc()
    expect(() => applyCommand(doc, cmd('moveClip', { clipId: 'c1', trackId: 'a1', start: 1 })))
      .toThrow(/cross-kind|invalid_payload/)
  })
})

describe('trimClip', () => {
  it('改 start/duration/trimStart，最短时长截底', () => {
    const doc = baseDoc()
    const trimmed = applyCommand(doc, cmd('trimClip', { clipId: 'c1', start: 0.5, duration: 0.01, trimStart: 2 }))
    expect(trimmed.clips.find((c) => c.id === 'c1')).toMatchObject({ start: 0.5, duration: 0.1, trimStart: 2 })
  })
  it('负值 → 抛错', () => {
    const doc = baseDoc()
    expect(() => applyCommand(doc, cmd('trimClip', { clipId: 'c1', duration: -1 }))).toThrow(/invalid_payload/)
  })
})

describe('splitClip', () => {
  it('前后半段：属性留前半段，后半段默认；trimStart 按变速换算', () => {
    const doc = baseDoc()
    // 变速派生时长：c1 duration 4 → speed 2 → 2（块 0~2）
    const speeded = applyCommand(doc, cmd('setClipProperty', { clipId: 'c1', props: { speed: 2 } }))
    const split = applyCommand(speeded, cmd('splitClip', { clipId: 'c1', at: 1, newId: 'c1b' }))
    const first = split.clips.find((c) => c.id === 'c1')
    const second = split.clips.find((c) => c.id === 'c1b')
    expect(first).toMatchObject({ start: 0, duration: 1, props: { speed: 2 } })
    expect(second).toMatchObject({ start: 1, duration: 1, trimStart: 1 + 1 * 2, props: {} })
  })
  it('字幕片段分割保留文本', () => {
    const doc = baseDoc()
    const split = applyCommand(doc, cmd('splitClip', { clipId: 't1', at: 1.2, newId: 't1b' }))
    expect(split.clips.find((c) => c.id === 't1b')?.text).toBe('第一句')
  })
  it('切点在片段外 → 抛错', () => {
    const doc = baseDoc()
    expect(() => applyCommand(doc, cmd('splitClip', { clipId: 'c1', at: 4, newId: 'x' }))).toThrow(/split_outside_clip/)
  })
  it('切点距边缘 < 最短时长 → split_too_close；恰好最短时长放行', () => {
    const doc = baseDoc()
    expect(() => applyCommand(doc, cmd('splitClip', { clipId: 'c1', at: 0.05, newId: 'x' }))).toThrow(/split_too_close/)
    expect(() => applyCommand(doc, cmd('splitClip', { clipId: 'c1', at: 3.95, newId: 'x' }))).toThrow(/split_too_close/)
    expect(applyCommand(doc, cmd('splitClip', { clipId: 'c1', at: 0.1, newId: 'x' })).clips.some((c) => c.id === 'x')).toBe(true)
  })
})

describe('碰撞拒绝（video/audio 轨半开区间，字幕豁免）', () => {
  it('addClip 落入占用区间 → overlap；贴边衔接放行；字幕轨共存放行', () => {
    const doc = baseDoc()
    expect(() => applyCommand(doc, cmd('addClip', {
      clip: { id: 'cx', trackId: 'v1', start: 2, duration: 3, trimStart: 0, props: {} },
    }))).toThrow(/overlap/)
    expect(applyCommand(doc, cmd('addClip', {
      clip: { id: 'cx', trackId: 'v1', start: 7, duration: 2, trimStart: 0, props: {} },
    })).clips.some((c) => c.id === 'cx')).toBe(true)
    expect(applyCommand(doc, cmd('addSubtitle', {
      clip: { id: 't9', trackId: 's1', start: 1, duration: 1, trimStart: 0, props: {}, text: '共存' },
    })).clips.some((c) => c.id === 't9')).toBe(true)
  })
  it('moveClip 同轨/跨轨撞邻 → overlap；贴边与空档放行', () => {
    const doc = baseDoc()
    expect(() => applyCommand(doc, cmd('moveClip', { clipId: 'c1', start: 5 }))).toThrow(/overlap/)
    expect(() => applyCommand(doc, cmd('moveClip', { clipId: 'p1', trackId: 'v1', start: 2 }))).toThrow(/overlap/)
    expect(applyCommand(doc, cmd('moveClip', { clipId: 'c1', start: 7 })).clips.find((c) => c.id === 'c1'))
      .toMatchObject({ start: 7 })
  })
  it('trimClip 拉长撞邻 → overlap；裁到贴边放行', () => {
    const doc = baseDoc()
    expect(() => applyCommand(doc, cmd('trimClip', { clipId: 'c1', duration: 5 }))).toThrow(/overlap/)
    expect(applyCommand(doc, cmd('trimClip', { clipId: 'c1', duration: 4 })).clips.find((c) => c.id === 'c1'))
      .toMatchObject({ duration: 4 })
  })
})

describe('removeClip / setClipProperty', () => {
  it('removeClip 删除目标', () => {
    const doc = baseDoc()
    const next = applyCommand(doc, cmd('removeClip', { clipId: 'p1' }))
    expect(next.clips.map((c) => c.id)).toEqual(['c1', 'c2', 't1'])
  })
  it('setClipProperty 合并 + null 删除键 + 非法值抛错', () => {
    const doc = baseDoc()
    const next = applyCommand(doc, cmd('setClipProperty', {
      clipId: 'p1', props: { volume: 0.5, rect: null },
    }))
    const clip = next.clips.find((c) => c.id === 'p1')
    expect(clip?.props.volume).toBe(0.5)
    expect(clip?.props.rect).toBeUndefined()
    expect(() => applyCommand(doc, cmd('setClipProperty', { clipId: 'p1', props: { volume: 9 } }))).toThrow()
    expect(() => applyCommand(doc, cmd('setClipProperty', { clipId: 'p1', props: { evil: 1 } }))).toThrow(/unknown prop/)
  })
  it('muted 仅接受布尔值', () => {
    expect(applyCommand(baseDoc(), cmd('setClipProperty', { clipId: 'c1', props: { muted: true } }))
      .clips.find((c) => c.id === 'c1')?.props.muted).toBe(true)
    expect(() => applyCommand(baseDoc(), cmd('setClipProperty', { clipId: 'c1', props: { muted: 1 } }))).toThrow(/invalid_payload/)
  })
})

describe('detachAudio', () => {
  it('视频片段静音 + 自带音频转投音频轨（仅带变速）', () => {
    const doc = baseDoc()
    const next = applyCommand(doc, cmd('detachAudio', { clipId: 'c1', newId: 'ad1', trackId: 'a1' }))
    expect(next.clips.find((c) => c.id === 'c1')?.props.muted).toBe(true)
    expect(next.clips.find((c) => c.id === 'ad1')).toMatchObject({
      trackId: 'a1', assetId: 10, start: 0, duration: 4, trimStart: 1, props: {},
    })
    expect(next.clips.length).toBe(5)
  })
  it('变速片段分离后音频片段带同速', () => {
    const doc = applyCommand(baseDoc(), cmd('setClipProperty', { clipId: 'c1', props: { speed: 2 } }))
    const next = applyCommand(doc, cmd('detachAudio', { clipId: 'c1', newId: 'ad1', trackId: 'a1' }))
    expect(next.clips.find((c) => c.id === 'ad1')?.props.speed).toBe(2)
  })
  it('非视频片段 / 目标非音频轨 → 抛错', () => {
    const doc = baseDoc()
    expect(() => applyCommand(doc, cmd('detachAudio', { clipId: 't1', newId: 'x', trackId: 'a1' }))).toThrow(/invalid_payload/)
    expect(() => applyCommand(doc, cmd('detachAudio', { clipId: 'c1', newId: 'x', trackId: 'v2' }))).toThrow(/not_audio_track/)
  })
  it('目标音频轨重叠 → overlap', () => {
    const doc = applyCommand(baseDoc(), cmd('addClip', {
      clip: { id: 'm1', trackId: 'a1', assetId: 30, start: 1, duration: 5, trimStart: 0, props: {} },
    }))
    expect(() => applyCommand(doc, cmd('detachAudio', { clipId: 'c1', newId: 'x', trackId: 'a1' }))).toThrow(/overlap/)
  })
})

describe('setClipProperty 变速派生时长', () => {
  it('保持源内跨度：duration = 源跨度 / speed（加速缩短，减速拉长）', () => {
    const doc = baseDoc()
    const speeded = applyCommand(doc, cmd('setClipProperty', { clipId: 'p1', props: { speed: 2 } }))
    expect(speeded.clips.find((c) => c.id === 'p1')).toMatchObject({ duration: 1, props: { speed: 2 } })
    const slowed = applyCommand(doc, cmd('setClipProperty', { clipId: 'p1', props: { speed: 0.5 } }))
    expect(slowed.clips.find((c) => c.id === 'p1')).toMatchObject({ duration: 4, props: { speed: 0.5 } })
    // 链式换算以当前速率为基准：duration 1 @2x（跨度 2）→ 0.25x → 1*2/0.25 = 8，跨度仍 2
    const chained = applyCommand(speeded, cmd('setClipProperty', { clipId: 'p1', props: { speed: 0.25 } }))
    expect(chained.clips.find((c) => c.id === 'p1')?.duration).toBe(8)
  })
  it('减速拉长撞同轨邻接片段 → overlap', () => {
    // c1(0~4) 与 c2(4~7) 贴边：任何减速都会撞上 c2
    expect(() => applyCommand(baseDoc(), cmd('setClipProperty', { clipId: 'c1', props: { speed: 0.5 } })))
      .toThrow(/overlap/)
  })
  it('加速到碎片化截底 MIN_CLIP_DURATION', () => {
    const doc = applyCommand(baseDoc(), cmd('trimClip', { clipId: 'p1', duration: 0.3 }))
    const next = applyCommand(doc, cmd('setClipProperty', { clipId: 'p1', props: { speed: 4 } }))
    expect(next.clips.find((c) => c.id === 'p1')?.duration).toBe(0.1)
  })
})

describe('addSubtitle / removeSubtitle / rebuildSubtitleClips', () => {
  it('addSubtitle 要求字幕轨 + 非空文本', () => {
    const doc = baseDoc()
    const next = applyCommand(doc, cmd('addSubtitle', {
      clip: { id: 't2', trackId: 's1', start: 3, duration: 1, trimStart: 0, props: {}, text: '第二句' },
    }))
    expect(next.clips.find((c) => c.id === 't2')?.text).toBe('第二句')
    expect(() => applyCommand(doc, cmd('addSubtitle', {
      clip: { id: 't9', trackId: 'v1', start: 3, duration: 1, trimStart: 0, props: {}, text: 'x' },
    }))).toThrow(/not_subtitle_track/)
    expect(() => applyCommand(doc, cmd('addSubtitle', {
      clip: { id: 't9', trackId: 's1', start: 3, duration: 1, trimStart: 0, props: {}, text: '  ' },
    }))).toThrow(/invalid_payload/)
  })
  it('removeSubtitle 只删字幕片段', () => {
    const doc = baseDoc()
    expect(() => applyCommand(doc, cmd('removeSubtitle', { clipId: 'c1' }))).toThrow(/not_subtitle_track/)
    const next = applyCommand(doc, cmd('removeSubtitle', { clipId: 't1' }))
    expect(next.clips.map((c) => c.id)).toEqual(['c1', 'c2', 'p1'])
  })
  it('rebuildSubtitleClips 整轨替换', () => {
    const doc = baseDoc()
    const next = applyCommand(doc, cmd('rebuildSubtitleClips', {
      trackId: 's1',
      clips: [
        { id: 'n1', start: 0, duration: 1, text: '转写A' },
        { id: 'n2', start: 2, duration: 1.4, text: '转写B' },
      ],
    }))
    expect(next.clips.filter((c) => c.trackId === 's1').map((c) => c.id)).toEqual(['n1', 'n2'])
    expect(next.clips.filter((c) => c.trackId !== 's1').map((c) => c.id)).toEqual(['c1', 'c2', 'p1'])
  })
})

describe('addTrack / removeTrack / setTrackFlags / moveTrack', () => {
  it('addTrack 默认 order 同类递增、flags 全关', () => {
    const next = applyCommand(baseDoc(), cmd('addTrack', { track: { id: 'v3', kind: 'video' } }))
    expect(next.tracks.find((t) => t.id === 'v3')).toMatchObject({ order: 2, flags: { hidden: false, locked: false, muted: false, solo: false } })
  })
  it('removeTrack 仅允许空轨', () => {
    const doc = baseDoc()
    expect(() => applyCommand(doc, cmd('removeTrack', { trackId: 'v1' }))).toThrow(/track_not_empty/)
    const emptied = applyCommand(doc, cmd('removeClip', { clipId: 't1' }))
    const next = applyCommand(emptied, cmd('removeTrack', { trackId: 's1' }))
    expect(next.tracks.map((t) => t.id)).toEqual(['v1', 'v2', 'a1'])
  })
  it('setTrackFlags 部分合并：多开可并存，未提及键保持原值', () => {
    const next = applyCommand(baseDoc(), cmd('setTrackFlags', { trackId: 'v1', flags: { hidden: true, locked: true } }))
    expect(next.tracks.find((t) => t.id === 'v1')?.flags).toMatchObject({ hidden: true, locked: true, muted: false, solo: false })
    const reset = applyCommand(next, cmd('setTrackFlags', { trackId: 'v1', flags: { hidden: false } }))
    expect(reset.tracks.find((t) => t.id === 'v1')?.flags).toMatchObject({ hidden: false, locked: true })
    expect(() => applyCommand(baseDoc(), cmd('setTrackFlags', { trackId: 'v1', flags: { boom: true } }))).toThrow(/invalid_payload/)
    expect(() => applyCommand(baseDoc(), cmd('setTrackFlags', { trackId: 'v1', flags: { locked: 1 } }))).toThrow(/invalid_payload/)
  })
  it('moveTrack 同类型内重排（显示序 0=顶），order 重编号稠密', () => {
    const doc = baseDoc() // v2 order1 在顶、v1 order0 在底；把 v1 拖到顶
    const next = applyCommand(doc, cmd('moveTrack', { trackId: 'v1', toIndex: 0 }))
    expect(next.tracks.find((t) => t.id === 'v1')!.order).toBe(1)
    expect(next.tracks.find((t) => t.id === 'v2')!.order).toBe(0)
  })
  it('toIndex 相对移除后的序列：拖到底落到末位', () => {
    const doc = baseDoc() // 显示序 [v2, v1]，v2 拖到底：移除后 [v1] 插入位 1
    const next = applyCommand(doc, cmd('moveTrack', { trackId: 'v2', toIndex: 1 }))
    expect(next.tracks.find((t) => t.id === 'v2')!.order).toBe(0)
    expect(next.tracks.find((t) => t.id === 'v1')!.order).toBe(1)
  })
  it('原位放置返回同引用；只动同类型轨（其他类型引用相等）', () => {
    const doc = baseDoc()
    expect(applyCommand(doc, cmd('moveTrack', { trackId: 'v1', toIndex: 1 }))).toBe(doc)
    const moved = applyCommand(doc, cmd('moveTrack', { trackId: 'v1', toIndex: 0 }))
    expect(moved.tracks.find((t) => t.id === 'a1')).toBe(doc.tracks.find((t) => t.id === 'a1'))
    expect(moved.tracks.find((t) => t.id === 'v1')).not.toBe(doc.tracks.find((t) => t.id === 'v1'))
  })
  it('越界钳位；track 不存在 / toIndex 非法 → 抛错', () => {
    const doc = baseDoc()
    expect(applyCommand(doc, cmd('moveTrack', { trackId: 'v1', toIndex: 99 }))).toBe(doc) // 钳到末位 = 原位
    expect(() => applyCommand(doc, cmd('moveTrack', { trackId: 'vx', toIndex: 0 }))).toThrow(/track_not_found/)
    expect(() => applyCommand(doc, cmd('moveTrack', { trackId: 'v1', toIndex: -1 }))).toThrow(/invalid_payload/)
    expect(() => applyCommand(doc, cmd('moveTrack', { trackId: 'v1', toIndex: 0.5 }))).toThrow(/invalid_payload/)
  })
})

// ---------- fail-closed 与回放 ----------

describe('fail-closed', () => {
  it('未知 op 抛错不改状态', () => {
    const doc = baseDoc()
    const broken = { op: 'explode', payload: {} } as unknown as EditorCommand
    expect(() => applyCommand(doc, broken)).toThrow(/unknown_op/)
    expect(doc.clips.length).toBe(4)
  })
  it('op 表恰好 14 个', () => {
    expect(EDITOR_OPS.length).toBe(14)
  })
})

describe('回放一致性', () => {
  it('命令序列 JSON 序列化 → 重放 → 结果一致', () => {
    const script: EditorCommand[] = [
      cmd('addTrack', { track: { id: 'a2', kind: 'audio' } }),
      cmd('addClip', { clip: { id: 'm1', trackId: 'a2', assetId: 30, start: 0, duration: 5, trimStart: 0, props: {} } }),
      cmd('setClipProperty', { clipId: 'm1', props: { volume: 0.8, fadeIn: 0.3, fadeOut: 0.5, rect: { x: 0.1, y: 0.1, w: 0.5, h: 0.5 } } }),
      cmd('moveClip', { clipId: 'c1', trackId: 'v2', start: 3 }),
      cmd('trimClip', { clipId: 'c2', duration: 2 }),
      cmd('splitClip', { clipId: 'c1', at: 5, newId: 'c1b' }),
      cmd('setTrackFlags', { trackId: 'v2', flags: { muted: true } }),
      cmd('moveTrack', { trackId: 'v1', toIndex: 0 }),
      cmd('rebuildSubtitleClips', { trackId: 's1', clips: [{ id: 'r1', start: 0, duration: 1, text: '重放' }] }),
      cmd('removeClip', { clipId: 'c1b' }),
    ]
    const run = (commands: EditorCommand[]): EditorDocument =>
      commands.reduce((doc, c) => applyCommand(doc, c), baseDoc())
    const direct = run(script)
    const replay = run(JSON.parse(JSON.stringify(script)) as EditorCommand[])
    expect(replay).toEqual(direct)
    expect(direct.clips.map((c) => c.id)).toEqual(['c1', 'c2', 'p1', 'm1', 'r1'])
  })
})

describe('EditorHistory', () => {
  it('undo/redo 往返', () => {
    const history = new EditorHistory()
    const d0 = baseDoc()
    const d1 = applyCommand(d0, cmd('setTrackFlags', { trackId: 'v1', flags: { hidden: true } }))
    const d2 = applyCommand(d1, cmd('addTrack', { track: { id: 'a9', kind: 'audio' } }))
    history.push({ undoDoc: d0, redoDoc: d1, label: 'a' })
    history.push({ undoDoc: d1, redoDoc: d2, label: 'b' })
    expect(history.canUndo && history.canRedo === false).toBe(true)
    expect(history.undo()?.undoDoc).toBe(d1)
    expect(history.undo()?.undoDoc).toBe(d0)
    expect(history.canUndo).toBe(false)
    expect(history.redo()?.redoDoc).toBe(d1)
    expect(history.redo()?.redoDoc).toBe(d2)
    expect(history.canRedo).toBe(false)
  })
  it(`满 ${MAX_HISTORY_ENTRIES} 层丢最旧`, () => {
    const history = new EditorHistory()
    let doc = baseDoc()
    for (let i = 0; i < MAX_HISTORY_ENTRIES + 10; i += 1) {
      const prev = doc
      doc = applyCommand(doc, cmd('addTrack', { track: { id: `t${i}`, kind: 'audio' } }))
      history.push({ undoDoc: prev, redoDoc: doc, label: String(i) })
    }
    expect(history.depth).toBe(MAX_HISTORY_ENTRIES)
    // 最旧 10 条被丢：连 undo 到底后第一条应是 t10
    let last = ''
    while (history.canUndo) last = history.undo()!.label
    expect(last).toBe('10')
  })
  it('中间 undo 后 push 丢弃 redo 分支', () => {
    const history = new EditorHistory()
    const d0 = baseDoc()
    const d1 = applyCommand(d0, cmd('removeClip', { clipId: 'p1' }))
    history.push({ undoDoc: d0, redoDoc: d1, label: 'a' })
    history.undo()
    const d2 = applyCommand(d0, cmd('removeClip', { clipId: 't1' }))
    history.push({ undoDoc: d0, redoDoc: d2, label: 'b' })
    expect(history.canRedo).toBe(false)
    expect(history.depth).toBe(1)
  })
})
