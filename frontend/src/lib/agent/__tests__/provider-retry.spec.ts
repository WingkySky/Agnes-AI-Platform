/* agentStreamFn 上游空响应韧性单测：占位文本/纯空补全自动重试一次，正常流直通不受影响 */

import { describe, it, expect, vi } from 'vitest'

import type { AssistantMessage, AssistantMessageEvent } from '@earendil-works/pi-ai'
import type { Model } from '@earendil-works/pi-ai'
import { createAssistantMessageEventStream } from '@earendil-works/pi-ai/utils/event-stream'
import { streamWithUpstreamRetry } from '../provider'

const model = {
  id: 'agnes-chat',
  api: 'openai-completions',
} as unknown as Model<'openai-completions'>

const context = { messages: [], systemPrompt: 'test', tools: [] } as never

function textEvent(type: AssistantMessageEvent['type'], fields: Record<string, unknown>): AssistantMessageEvent {
  return { type, ...fields } as unknown as AssistantMessageEvent
}

function messageOf(partial: Partial<AssistantMessage>): AssistantMessage {
  return {
    role: 'assistant',
    content: [],
    api: 'openai-completions',
    provider: 'agnes',
    model: 'agnes-3.0-flash',
    usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
    stopReason: 'stop',
    timestamp: Date.now(),
    ...partial,
  } as AssistantMessage
}

/** 构造一轮底层流：事件按序推入，done 后 result 以最后一条消息收尾 */
function fakeUpstream(events: AssistantMessageEvent[]): ReturnType<typeof createAssistantMessageEventStream> {
  const stream = createAssistantMessageEventStream()
  for (const ev of events) stream.push(ev)
  return stream
}

function collect(out: ReturnType<typeof createAssistantMessageEventStream>): Promise<{ types: string[]; text: string }> {
  return (async () => {
    const types: string[] = []
    let text = ''
    for await (const ev of out) {
      types.push(ev.type)
      if (ev.type === 'text_delta') text += ev.delta
    }
    return { types, text }
  })()
}

describe('streamWithUpstreamRetry：上游空响应韧性', () => {
  it('整轮命中网关占位文本 → 丢弃并重试，第二次正常透传', async () => {
    const underlying = vi.fn()
      .mockImplementationOnce(() => fakeUpstream([
        textEvent('start', {}),
        textEvent('text_start', { contentIndex: 0 }),
        textEvent('text_delta', { contentIndex: 0, delta: '[System: Empty response is not allowed]' }),
        textEvent('text_end', { contentIndex: 0, content: '[System: Empty response is not allowed]' }),
        textEvent('done', { reason: 'stop', message: messageOf({ content: [{ type: 'text', text: '[System: Empty response is not allowed]' }] }) }),
      ]))
      .mockImplementationOnce(() => fakeUpstream([
        textEvent('start', {}),
        textEvent('text_start', { contentIndex: 0 }),
        textEvent('text_delta', { contentIndex: 0, delta: '好的' }),
        textEvent('text_end', { contentIndex: 0, content: '好的' }),
        textEvent('done', { reason: 'stop', message: messageOf({ content: [{ type: 'text', text: '好的' }] }) }),
      ]))
    const out = streamWithUpstreamRetry(model, context, undefined, underlying as never)
    const r = await collect(out)
    expect(underlying).toHaveBeenCalledTimes(2)
    expect(r.text).toBe('好的')
    expect(r.types).not.toContain('error')
  })

  it('纯空补全（无文本/工具/思考）→ 同样自动重试', async () => {
    const underlying = vi.fn()
      .mockImplementationOnce(() => fakeUpstream([
        textEvent('start', {}),
        textEvent('done', { reason: 'stop', message: messageOf({}) }),
      ]))
      .mockImplementationOnce(() => fakeUpstream([
        textEvent('start', {}),
        textEvent('toolcall_start', { contentIndex: 0 }),
        textEvent('done', { reason: 'toolUse', message: messageOf({ content: [{ type: 'toolCall', id: 't1', name: 'editor_get_overview', arguments: {} }], stopReason: 'toolUse' }) }),
      ]))
    const out = streamWithUpstreamRetry(model, context, undefined, underlying as never)
    const r = await collect(out)
    expect(underlying).toHaveBeenCalledTimes(2)
    expect(r.types).toContain('toolcall_start')
  })

  it('正常回复首增量即直通，底层只调用一次', async () => {
    const underlying = vi.fn().mockImplementation(() => fakeUpstream([
      textEvent('start', {}),
      textEvent('text_start', { contentIndex: 0 }),
      textEvent('text_delta', { contentIndex: 0, delta: '你' }),
      textEvent('text_delta', { contentIndex: 0, delta: '好' }),
      textEvent('text_end', { contentIndex: 0, content: '你好' }),
      textEvent('done', { reason: 'stop', message: messageOf({ content: [{ type: 'text', text: '你好' }] }) }),
    ]))
    const out = streamWithUpstreamRetry(model, context, undefined, underlying as never)
    const r = await collect(out)
    expect(underlying).toHaveBeenCalledTimes(1)
    expect(r.text).toBe('你好')
    expect(r.types).toEqual(['start', 'text_start', 'text_delta', 'text_delta', 'text_end', 'done'])
  })

  it('重试后仍占位 → 末次按原样透传（优雅降级）', async () => {
    const events = [
      textEvent('start', {}),
      textEvent('text_start', { contentIndex: 0 }),
      textEvent('text_delta', { contentIndex: 0, delta: '[System: Empty response is not allowed]' }),
      textEvent('text_end', { contentIndex: 0, content: '[System: Empty response is not allowed]' }),
      textEvent('done', { reason: 'stop', message: messageOf({ content: [{ type: 'text', text: '[System: Empty response is not allowed]' }] }) }),
    ]
    const underlying = vi.fn().mockImplementation(() => fakeUpstream([...events]))
    const out = streamWithUpstreamRetry(model, context, undefined, underlying as never)
    const r = await collect(out)
    expect(underlying).toHaveBeenCalledTimes(2)
    expect(r.text).toBe('[System: Empty response is not allowed]')
    expect(r.types[r.types.length - 1]).toBe('done')
  })

  it('上游 error 事件原样透传，不重试', async () => {
    const underlying = vi.fn().mockImplementation(() => fakeUpstream([
      textEvent('start', {}),
      textEvent('error', { reason: 'error', error: messageOf({ content: [{ type: 'text', text: 'HTTP 502' }], stopReason: 'error' }) }),
    ]))
    const out = streamWithUpstreamRetry(model, context, undefined, underlying as never)
    const r = await collect(out)
    expect(underlying).toHaveBeenCalledTimes(1)
    expect(r.types[r.types.length - 1]).toBe('error')
  })
})
