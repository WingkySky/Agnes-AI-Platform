/* =====================================================
 * 画布 Agent LLM 通道（OpenAI 兼容流式适配）
 *
 * - 复用 openai-completions 适配（OpenAI SDK dangerouslyAllowBrowser，
 *   自带 SSE 解析与 tool_calls 增量聚合）
 * - baseURL 指向后端 BFF 透传端点（OpenAI SDK 自动拼接 /chat/completions），
 *   apiKey 由 kernel 经 getApiKey 注入 JWT（匿名时传占位串，后端可选鉴权容错）
 * ===================================================== */

import { streamSimple } from '@earendil-works/pi-ai/api/openai-completions'
import type { Api, Model } from '@earendil-works/pi-ai'
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

export const agentStreamFn: StreamFn = (model, context, options) => {
  if (!isOpenAiCompletionsModel(model)) throw new Error(`不支持的 LLM API: ${model.api}`)
  return streamSimple(model, context, options)
}
