/* 测试帮手：可编排的假 LLM 流（机制层 AssistantMessageEventStream 驱动）
 * 每次流调用弹出一条脚本并产出对应事件序列，供 kernel 直测与 store 投影测共用 */

import { AssistantMessageEventStream } from '@earendil-works/pi-ai/utils/event-stream'
import type { AssistantMessage, TextContent, ToolCall } from '@earendil-works/pi-ai'
import type { StreamFn } from '@earendil-works/pi-agent-core'
import type { Model } from '@earendil-works/pi-ai'

export interface FakeTurn {
  text?: string
  toolCalls?: Array<{ id: string; name: string; args: Record<string, unknown> }>
}

export function fakeAssistantMessage(content: AssistantMessage['content'], stopReason: AssistantMessage['stopReason']): AssistantMessage {
  return {
    role: 'assistant',
    content,
    api: 'openai-completions',
    provider: 'fake',
    model: 'fake-chat',
    usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
    stopReason,
    timestamp: Date.now(),
  }
}

export const fakeModel: Model<'openai-completions'> = {
  id: 'fake-chat',
  name: 'Fake Chat',
  api: 'openai-completions',
  provider: 'fake',
  baseUrl: 'http://fake.local/v1',
  reasoning: false,
  input: ['text'],
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  contextWindow: 128000,
  maxTokens: 8192,
}

function toolCallBlocks(calls: NonNullable<FakeTurn['toolCalls']>): ToolCall[] {
  return calls.map((c) => ({ type: 'toolCall', id: c.id, name: c.name, arguments: c.args }))
}

export interface FakeStreamFn {
  streamFn: StreamFn
  /** 每次真实流调用的入参快照（断言回填/上下文用） */
  calls: Array<{ systemPrompt?: string; messages: unknown[] }>
}

/** 脚本数组按引用捕获：测试 beforeEach 清空/重填即可换剧本 */
export function createFakeStreamFn(script: FakeTurn[]): FakeStreamFn {
  const calls: FakeStreamFn['calls'] = []
  const streamFn: StreamFn = (_model, context) => {
    calls.push({ systemPrompt: context.systemPrompt, messages: JSON.parse(JSON.stringify(context.messages)) })
    const turn = script.shift()
    const stream = new AssistantMessageEventStream()
    if (!turn) throw new Error('假 LLM 脚本已耗尽')
    if (turn.toolCalls && turn.toolCalls.length > 0) {
      const blocks = toolCallBlocks(turn.toolCalls)
      const msg = fakeAssistantMessage(blocks, 'toolUse')
      stream.push({ type: 'start', partial: msg })
      for (const tc of blocks) {
        stream.push({ type: 'toolcall_end', contentIndex: 0, toolCall: tc, partial: msg })
      }
      stream.push({ type: 'done', reason: 'toolUse', message: msg })
    } else {
      const block: TextContent = { type: 'text', text: turn.text ?? '' }
      const msg = fakeAssistantMessage([block], 'stop')
      stream.push({ type: 'start', partial: msg })
      stream.push({ type: 'text_delta', contentIndex: 0, delta: block.text, partial: msg })
      stream.push({ type: 'done', reason: 'stop', message: msg })
    }
    stream.end()
    return stream
  }
  return { streamFn, calls }
}
