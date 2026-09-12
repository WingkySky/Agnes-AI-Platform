/* =====================================================
 * 分镜管线 LLM 子调用通道（lib/storyboard）
 *
 * - 走后端 /api/chat/completions 流式透传（与画布 Agent 内核同一通道）
 * - SSE 行解析累积 delta.content；model 可选（后端校验聊天注册表，未命中走默认解析链）
 * - pipeline 函数全部接受 transport 参数：单测注入假 transport，不经网络
 * ===================================================== */

import { getAuthHeaders } from '@/api/chat'

export interface ChatMessage {
  role: 'user' | 'system' | 'assistant'
  content: string
}

export interface ChatCallOptions {
  temperature?: number
  model?: string
}

/** LLM 子调用通道：输入消息序列，返回全文 */
export type ChatTransport = (messages: ChatMessage[], opts?: ChatCallOptions) => Promise<string>

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null
}

/** 从 SSE chunk 提取增量文本（守卫式解析，不做类型断言） */
function deltaText(parsed: unknown): string {
  if (!isRecord(parsed)) return ''
  const choices = parsed.choices
  if (!Array.isArray(choices) || choices.length === 0) return ''
  const first = choices[0]
  if (!isRecord(first)) return ''
  const delta = first.delta
  if (!isRecord(delta)) return ''
  return typeof delta.content === 'string' ? delta.content : ''
}

/** 默认 transport：fetch POST + SSE 增量累积 */
export const sseChatComplete: ChatTransport = async (messages, opts) => {
  const base = import.meta.env.VITE_API_BASE_URL || ''
  const body: Record<string, unknown> = { messages, stream: true, max_tokens: 4096 }
  if (opts?.temperature !== undefined) body.temperature = opts.temperature
  if (opts?.model) body.model = opts.model
  const resp = await fetch(`${base}/api/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await getAuthHeaders()) },
    body: JSON.stringify(body),
  })
  if (!resp.ok || !resp.body) throw new Error(`LLM 通道错误 (HTTP ${resp.status})`)
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let text = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data: ')) continue
      const payload = trimmed.slice(6)
      if (payload === '[DONE]') continue
      try {
        text += deltaText(JSON.parse(payload))
      } catch {
        // 非 JSON 行忽略
      }
    }
  }
  const out = text.trim()
  if (!out) throw new Error('LLM 返回为空')
  return out
}
