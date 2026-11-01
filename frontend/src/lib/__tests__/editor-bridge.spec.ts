/* 剪辑器选区引用桥单测：编号块构建（引用行/选中/播放头/历史重放）+ 落库恢复往返 */
import { describe, it, expect } from 'vitest'
import {
  buildEditorRefBlock,
  editorRefLine,
  editorRefTimecode,
  type EditorRefPayload,
} from '@/lib/agent/editor-bridge'
import { toBackendMessages } from '@/lib/agent/session-store'
import { chatContextFromRows, toChatBubbleItems } from '@/stores/chat'

const clipRef: EditorRefPayload = {
  kind: 'clip',
  projectId: 'p1',
  clipId: 'clip_abc',
  trackId: 'v2',
  assetId: 12,
  assetName: '夕阳.mp4',
  trackKind: 'video',
  start: 0.5,
  end: 3.2,
  label: '夕阳.mp4 0:00.5-0:03.2',
}

const trackRef: EditorRefPayload = {
  kind: 'track',
  projectId: 'p1',
  trackId: 'a1',
  trackKind: 'audio',
  label: 'a1（音频）',
}

describe('editorRefTimecode', () => {
  it('秒转 m:ss.d', () => {
    expect(editorRefTimecode(0.5)).toBe('0:00.5')
    expect(editorRefTimecode(12.44)).toBe('0:12.4')
    expect(editorRefTimecode(75)).toBe('1:15.0')
    expect(editorRefTimecode(undefined)).toBe('0:00.0')
  })
})

describe('buildEditorRefBlock', () => {
  it('无引用无选中返回空串', () => {
    expect(buildEditorRefBlock([])).toBe('')
    expect(buildEditorRefBlock([], { playhead: 0 })).toBe('')
  })

  it('片段引用行含 id/素材名/区间/轨/assetId', () => {
    const block = buildEditorRefBlock([clipRef], { projectId: 'p1' })
    expect(block).toContain('[1] 片段 clip_abc「夕阳.mp4」 0:00.5-0:03.2 · 视频轨 v2 · assetId=12')
    expect(block).toContain('工程 uid=p1')
  })

  it('轨道引用行', () => {
    const block = buildEditorRefBlock([trackRef])
    expect(block).toContain('[1] 轨道 a1（音频）')
  })

  it('选中与播放头行（无引用时也注入）', () => {
    const block = buildEditorRefBlock([], { selectedClipId: 'clip_abc', playhead: 12.44 })
    expect(block).toContain('当前选中：片段 clip_abc')
    expect(block).toContain('播放头：0:12.4')
    expect(block).not.toContain('[1]')
  })

  it('混合引用 + 选中', () => {
    const block = buildEditorRefBlock([clipRef, trackRef], { selectedTrackId: 'a1', playhead: 0 })
    expect(block).toContain('[1] 片段 clip_abc')
    expect(block).toContain('[2] 轨道 a1（音频）')
    expect(block).toContain('当前选中：轨道 a1')
    // playhead=0 不注入
    expect(block).not.toContain('播放头')
  })

  it('历史重放（无 ctx）只放编号行', () => {
    const block = buildEditorRefBlock([clipRef])
    expect(block).toContain('[1] 片段 clip_abc')
    expect(block).not.toContain('当前选中')
    expect(editorRefLine(clipRef, 3)).toContain('[3] 片段 clip_abc')
  })

  it('I/O 区间引用行', () => {
    const rangeRef: EditorRefPayload = {
      kind: 'range', projectId: 'p1', start: 2, end: 6.5, label: '区间 0:02.0-0:06.5',
    }
    const block = buildEditorRefBlock([rangeRef, trackRef])
    expect(block).toContain('[1] 时间段 0:02.0-0:06.5（I/O 区间）')
    expect(block).toContain('[2] 轨道 a1（音频）')
  })
})

describe('引用落库与恢复往返', () => {
  it('toBackendMessages 把 editorRefs 写进 attachments 行', () => {
    const rows = toBackendMessages([
      { role: 'user', content: '帮我删掉它', editorRefs: [clipRef], steps: [] },
    ])
    expect(rows[0].attachments).toHaveLength(1)
    expect(rows[0].attachments?.[0].editor_ref).toEqual(clipRef)
    expect(rows[0].attachments?.[0].name).toBe(clipRef.label)
  })

  it('chatContextFromRows 重建用户内容时重放引用编号块', () => {
    const ctx = chatContextFromRows([
      {
        id: 1, session_id: 1, role: 'user', content: '帮我删掉它', created_at: '',
        attachments: [{ name: clipRef.label, editor_ref: clipRef, mime_type: 'editor/ref', size: 0 }],
      },
    ]) as { messages: Array<{ role: string; content: unknown }> }
    const user = ctx.messages[0]
    const texts = (user.content as Array<{ type: string; text?: string }>).filter((c) => c.type === 'text')
    expect(texts.some((t) => t.text?.includes('[1] 片段 clip_abc'))).toBe(true)
  })

  it('toChatBubbleItems 把 editorRefs 投影为 refs 芯片视图', () => {
    const items = toChatBubbleItems([
      {
        id: 'm1', role: 'user', content: '帮我删掉它', editorRefs: [clipRef],
        media: [], steps: [], createdAt: '',
      },
    ], false)
    expect(items[0].refs).toEqual([{ label: clipRef.label, thumb: undefined }])
  })
})
