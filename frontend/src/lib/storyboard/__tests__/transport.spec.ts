/* 通用 LLM 透传通道单测：fetch 打桩走 SSE 流，
 * 验证消息组装（含多模态 content parts）/ onDelta 增量 / 空回复与非 200 报错 */

import { describe, it, expect, vi, afterEach } from 'vitest'
import { sseChatComplete, type ChatMessage } from '../transport'

function sseResponse(lines: string[], status = 200): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream({
    start(controller) {
      for (const line of lines) controller.enqueue(encoder.encode(line))
      controller.close()
    },
  })
  return new Response(stream, { status, headers: { 'Content-Type': 'text/event-stream' } })
}

function sseChunks(texts: string[]): string[] {
  return texts.map((t) => `data: ${JSON.stringify({ choices: [{ delta: { content: t } }] })}\n\n`)
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('sseChatComplete 透传通道', () => {
  it('组装 messages/stream/model 并累积全文', async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body))
      expect(body.stream).toBe(true)
      expect(body.model).toBe('m1')
      expect(body.messages).toEqual([{ role: 'user', content: 'hi' }])
      return sseResponse([...sseChunks(['你好', '，世界']), 'data: [DONE]\n\n'])
    })
    vi.stubGlobal('fetch', fetchMock)
    const out = await sseChatComplete([{ role: 'user', content: 'hi' }], { model: 'm1' })
    expect(out).toBe('你好，世界')
  })

  it('onDelta 逐段回调增量文本', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse([...sseChunks(['a', 'b', 'c']), 'data: [DONE]\n\n'])))
    const chunks: string[] = []
    const out = await sseChatComplete([{ role: 'user', content: 'x' }], { onDelta: (c) => chunks.push(c) })
    expect(chunks).toEqual(['a', 'b', 'c'])
    expect(out).toBe('abc')
  })

  it('多模态 content 数组原样进请求体（图片反推形状）', async () => {
    let body: { messages?: Array<{ content: unknown }> } = {}
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
      body = JSON.parse(String(init?.body))
      return sseResponse([...sseChunks(['a red cat']), 'data: [DONE]\n\n'])
    }))
    const messages: ChatMessage[] = [
      {
        role: 'user',
        content: [
          { type: 'text', text: '反推提示词' },
          { type: 'image_url', image_url: { url: 'data:image/png;base64,QQ==' } },
        ],
      },
    ]
    const out = await sseChatComplete(messages)
    expect(out).toBe('a red cat')
    expect(body.messages?.[0]?.content).toEqual([
      { type: 'text', text: '反推提示词' },
      { type: 'image_url', image_url: { url: 'data:image/png;base64,QQ==' } },
    ])
  })

  it('空回复抛错（上游静默不可伪装成功）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse(['data: [DONE]\n\n'])))
    await expect(sseChatComplete([{ role: 'user', content: 'x' }])).rejects.toThrow('LLM 返回为空')
  })

  it('非 200 抛通道错误', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse(['err'], 502)))
    await expect(sseChatComplete([{ role: 'user', content: 'x' }])).rejects.toThrow('LLM 通道错误')
  })
})
