/* Agent 消息投影单测（宿主统一后 session-store 仅保留 toBackendMessages）：
 * 图片转 attachments data URL / URL 附件并入 / 媒体行投影 / 空值省略 */

import { describe, it, expect } from 'vitest'

import { toBackendMessages } from '../session-store'
import type { ProjectableMessage } from '../session-store'

describe('toBackendMessages', () => {
  it('图片转 attachments data URL，步骤透传，空值省略', () => {
    const rows = toBackendMessages([
      {
        role: 'user',
        content: '画一只猫',
        images: [{ data: 'QQ==', mimeType: 'image/png' }],
        steps: [],
      },
      {
        role: 'assistant',
        content: '好的',
        steps: [{ callId: 't1', tool: 'agent_apply_ops', args: { ops: [] }, status: 'done', result: '{}' }],
      },
    ] satisfies ProjectableMessage[])
    expect(rows).toHaveLength(2)
    expect(rows[0]).toEqual({
      role: 'user',
      content: '画一只猫',
      attachments: [{ name: 'image', base64_image: 'data:image/png;base64,QQ==', mime_type: 'image/png', size: 0 }],
      steps: undefined,
    })
    expect(rows[1]).toEqual({
      role: 'assistant',
      content: '好的',
      attachments: undefined,
      steps: [{ callId: 't1', tool: 'agent_apply_ops', args: { ops: [] }, status: 'done', result: '{}' }],
    })
  })

  it('URL 附件并入 attachments；media 投影为 media_items', () => {
    const rows = toBackendMessages([
      {
        role: 'user',
        content: '看这个链接',
        urlAttachments: [{ name: '参考页', url: 'https://x.example/a', mime_type: 'text/html' }],
        steps: [],
      },
      {
        role: 'assistant',
        content: '',
        steps: [],
        media: [{ type: 'image', url: 'http://cdn/x.png', task_id: 'img_1', status: 'success' }],
      },
    ] satisfies ProjectableMessage[])
    expect(rows[0].attachments).toEqual([
      { name: '参考页', url: 'https://x.example/a', mime_type: 'text/html', size: 0 },
    ])
    expect(rows[1].media_items).toEqual([
      { type: 'image', url: 'http://cdn/x.png', task_id: 'img_1', status: 'success' },
    ])
  })
})
