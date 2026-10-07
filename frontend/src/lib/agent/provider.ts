/* =====================================================
 * 画布 Agent LLM 通道（OpenAI 兼容流式适配）
 *
 * - 复用 openai-completions 适配（OpenAI SDK dangerouslyAllowBrowser，
 *   自带 SSE 解析与 tool_calls 增量聚合）
 * - baseURL 指向后端 BFF 透传端点（OpenAI SDK 自动拼接 /chat/completions），
 *   apiKey 由 kernel 经 getApiKey 注入 JWT（匿名时传占位串，后端可选鉴权容错）
 * - 上游空响应韧性：网关偶发把空补全替换为占位文本（[System: Empty response
 *   is not allowed]）并以 200 原样返回——首段文本按前缀探测，命中即整轮丢弃
 *   自动重试一次；纯空补全（无文本/工具/思考）同样重试。正常回复只在首个
 *   文本增量处做一次前缀判定即直通，流式体验不受影响
 * ===================================================== */

import { streamSimple } from '@earendil-works/pi-ai/api/openai-completions'
import { createAssistantMessageEventStream } from '@earendil-works/pi-ai/utils/event-stream'
import type {
  AssistantMessage,
  AssistantMessageEvent,
  AssistantMessageEventStream,
  Context,
  SimpleStreamOptions,
} from '@earendil-works/pi-ai'
import type { Model, Api } from '@earendil-works/pi-ai'
import type { StreamFn } from '@earendil-works/pi-agent-core'

export function createAgentModel(id?: string): Model<'openai-completions'> {
  const base = import.meta.env.VITE_API_BASE_URL || ''
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return {
    // 默认占位 id（后端解析链决定真实模型）；传入注册表内的 chat 模型 id 时后端直接采用
    id: id || 'agnes-chat',
    name: 'Agnes Chat',
    api: 'openai-completions',
    provider: 'agnes',
    // OpenAI SDK 在 baseURL 后拼接 /chat/completions → 命中后端透传端点
    baseUrl: `${origin}${base}/api`,
    reasoning: false,
    input: ['text', 'image'],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 128000,
    maxTokens: 8192,
  }
}

/** StreamFn 的 model 参数是 Model<Api>（全联合），收窄后交给 openai-completions 适配；内核只注册本模型，收窄失败分支实际不可达 */
function isOpenAiCompletionsModel(m: Model<Api>): m is Model<'openai-completions'> {
  return m.api === 'openai-completions'
}

/** 上游网关空补全时回填的占位文本（实测自 Agnes 网关；精确匹配防误伤） */
const UPSTREAM_EMPTY_SENTINEL = '[System: Empty response is not allowed]'
const UPSTREAM_EMPTY_RETRY_LIMIT = 1

const ZERO_USAGE = {
  input: 0,
  output: 0,
  cacheRead: 0,
  cacheWrite: 0,
  totalTokens: 0,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
}

/** 是否值得重试的空响应：网关占位文本，或整轮无任何文本/工具/思考内容 */
function isEmptyResponse(message: AssistantMessage): boolean {
  const blocks = Array.isArray(message.content) ? message.content : []
  const text = blocks.map((b) => (b.type === 'text' ? b.text : '')).join('')
  if (text === UPSTREAM_EMPTY_SENTINEL) return true
  return !blocks.some((b) => b.type === 'text' || b.type === 'thinking' || b.type === 'toolCall')
}

function isFinalStopReason(r: AssistantMessage['stopReason']): r is 'stop' | 'length' | 'toolUse' | 'deferred' {
  return r === 'stop' || r === 'length' || r === 'toolUse' || r === 'deferred'
}

/** 底层流函数窄化签名（streamSimple 原生形态，避免宽 StreamFn 逆变的模型参数不兼容） */
type OpenAiStreamFn = (
  model: Model<'openai-completions'>,
  context: Context,
  options?: SimpleStreamOptions,
) => AssistantMessageEventStream

type ProbeMode = 'pending' | 'pass' | 'discard'

/** 空响应韧性：包装底层流，命中占位/空补全时丢弃本轮并自动重试一次（测试注入 underlying） */
export function streamWithUpstreamRetry(
  model: Model<'openai-completions'>,
  context: Context,
  options: SimpleStreamOptions | undefined,
  underlying: OpenAiStreamFn,
): AssistantMessageEventStream {
  const out = createAssistantMessageEventStream()
  void (async () => {
    for (let attempt = 0; attempt <= UPSTREAM_EMPTY_RETRY_LIMIT; attempt++) {
      const lastAttempt = attempt === UPSTREAM_EMPTY_RETRY_LIMIT
      const upstream = await underlying(model, context, options)
      const buffered: AssistantMessageEvent[] = []
      let mode: ProbeMode = 'pending'
      let head = ''
      let retryable = false
      let terminalPushed = false
      const flush = () => {
        for (const ev of buffered) {
          if (ev.type === 'done' || ev.type === 'error') terminalPushed = true
          out.push(ev)
        }
        buffered.length = 0
      }
      for await (const ev of upstream) {
        if (ev.type === 'done' || ev.type === 'error') {
          // 终态事件：discard/pending 态也要判定是否重试（discard 吞流不能吞掉重试决策）
          if (ev.type === 'done' && mode === 'discard') {
            if (!lastAttempt) {
              retryable = true
              break
            }
            mode = 'pass' // 末次重试仍异常：原样透传（优雅降级）
          } else if (ev.type === 'done' && mode === 'pending') {
            if (!lastAttempt && isEmptyResponse(ev.message)) {
              retryable = true
              break
            }
            mode = 'pass'
          } else {
            // error（含用户中止）原样透传不重试；pass 态正常透传
            mode = 'pass'
          }
        } else if (mode === 'pending') {
          if (ev.type === 'text_delta') {
            head += ev.delta
            // 首个增量即前缀失配 → 立刻直通（正常回复只缓冲 1 个增量）
            if (!UPSTREAM_EMPTY_SENTINEL.startsWith(head)) mode = 'pass'
          } else if (ev.type === 'text_end') {
            if (ev.content === UPSTREAM_EMPTY_SENTINEL) mode = 'discard'
            else mode = 'pass'
          } else if (ev.type === 'toolcall_start' || ev.type === 'toolcall_delta' || ev.type === 'thinking_start' || ev.type === 'thinking_delta') {
            mode = 'pass'
          }
        }
        if (mode === 'discard') continue
        buffered.push(ev)
        if (mode === 'pass') flush()
      }
      if (!retryable) {
        flush()
        // 防御：底层流未给终态事件就结束（人为 end）——取 result 补发 done，避免消费端悬挂
        if (!terminalPushed) {
          const final = await upstream.result()
          out.push({
            type: 'done',
            reason: isFinalStopReason(final.stopReason) ? final.stopReason : 'stop',
            message: final,
          })
        }
        return
      }
    }
  })().catch((err: unknown) => {
    // 底层流异常（如同步抛错）：合成 error 事件收尾，避免消费端悬挂
    const message = err instanceof Error ? err.message : String(err)
    out.push({
      type: 'error',
      reason: 'error',
      error: {
        role: 'assistant',
        content: [{ type: 'text', text: message }],
        api: 'openai-completions',
        provider: 'agnes',
        model: model.id,
        usage: ZERO_USAGE,
        stopReason: 'error',
        timestamp: Date.now(),
      },
    })
  })
  return out
}

export const agentStreamFn: StreamFn = (model, context, options) => {
  if (!isOpenAiCompletionsModel(model)) throw new Error(`不支持的 LLM API: ${model.api}`)
  return streamWithUpstreamRetry(model, context, options, streamSimple)
}
