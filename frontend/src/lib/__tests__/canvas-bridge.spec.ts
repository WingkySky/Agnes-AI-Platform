/* 画布节点引用桥单测：编号块构建 + 落库恢复往返 */
import { describe, it, expect } from 'vitest'
import {
  buildCanvasRefBlock,
  canvasRefLine,
  canvasNodeTypeLabel,
  type CanvasRefPayload,
} from '@/lib/agent/canvas-bridge'
import { toBackendMessages } from '@/lib/agent/session-store'
import { chatContextFromRows, toChatBubbleItems } from '@/stores/chat'

const videoRef: CanvasRefPayload = {
  kind: 'node',
  workspaceId: 'ws1',
  nodeId: 'n-abc',
  nodeType: 'video',
  name: '城市夜景',
  label: '城市夜景（视频）',
  mediaUrl: '/uploads/canvas/x.mp4',
}

const textRef: CanvasRefPayload = {
  kind: 'node',
  workspaceId: 'ws1',
  nodeId: 'n-def',
  nodeType: 'text',
  name: '剧本大纲',
  label: '剧本大纲（文本）',
}

describe('canvasRefLine / buildCanvasRefBlock', () => {
  it('媒体节点行：类型/名称/媒体可读提示', () => {
    const line = canvasRefLine(videoRef, 1)
    expect(line).toContain('[1] 节点 n-abc（视频）「城市夜景」')
    expect(line).toContain('agent_read_image')
  })

  it('文本节点行：正文位置提示', () => {
    expect(canvasRefLine(textRef, 2)).toContain('[2] 节点 n-def（文本）「剧本大纲」 — 正文在 content.content')
  })

  it('空引用返回空串；块头带工作区', () => {
    expect(buildCanvasRefBlock([])).toBe('')
    const block = buildCanvasRefBlock([videoRef, textRef])
    expect(block).toContain('[画布节点引用]')
    expect(block).toContain('工作区 ws1')
    expect(block).toContain('[2] 节点 n-def')
  })

  it('类型标签中文映射，未知类型原样', () => {
    expect(canvasNodeTypeLabel('image')).toBe('图片')
    expect(canvasNodeTypeLabel('compose')).toBe('合成')
    expect(canvasNodeTypeLabel('weird')).toBe('weird')
  })
})

describe('画布引用落库与恢复往返', () => {
  it('toBackendMessages 把 canvasRefs 写进 attachments 行', () => {
    const rows = toBackendMessages([
      { role: 'user', content: '把 @城市夜景 生成视频', canvasRefs: [videoRef], steps: [] },
    ])
    expect(rows[0].attachments).toHaveLength(1)
    expect(rows[0].attachments?.[0].canvas_ref).toEqual(videoRef)
    expect(rows[0].attachments?.[0].name).toBe(videoRef.label)
  })

  it('chatContextFromRows 重建用户内容时重放画布引用编号块', () => {
    const ctx = chatContextFromRows([
      {
        id: 1, session_id: 1, role: 'user', content: '把它生成视频', created_at: '',
        attachments: [{ name: videoRef.label, canvas_ref: videoRef, mime_type: 'canvas/ref', size: 0 }],
      },
    ]) as { messages: Array<{ role: string; content: unknown }> }
    const texts = (ctx.messages[0].content as Array<{ type: string; text?: string }>).filter((c) => c.type === 'text')
    expect(texts.some((t) => t.text?.includes('[1] 节点 n-abc（视频）'))).toBe(true)
  })

  it('toChatBubbleItems 把 canvasRefs 投影为 refs 芯片（thumb=mediaUrl）', () => {
    const items = toChatBubbleItems([
      {
        id: 'm1', role: 'user', content: '把它生成视频', canvasRefs: [videoRef],
        media: [], steps: [], createdAt: '',
      },
    ], false)
    expect(items[0].refs).toEqual([{ label: videoRef.label, thumb: videoRef.mediaUrl }])
  })
})
