/* Chat store 内核投影单测：发送流/生成工具挂占位与轮询回填/切换恢复/存量上下文重建 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mocks = vi.hoisted(() => {
  const script: unknown[] = []
  const calls: unknown[] = []
  // i18n 模块加载期读 localStorage；node 的内置 localStorage 不可用（缺 --localstorage-file），无条件覆盖
  const store = new Map<string, string>()
  ;(globalThis as { localStorage?: unknown }).localStorage = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => { store.set(k, v) },
    removeItem: (k: string) => { store.delete(k) },
    clear: () => store.clear(),
  }
  return { script, calls }
})

vi.mock('@/lib/agent/provider', async () => {
  const { createFakeStreamFn, fakeModel } = await import('../../lib/agent/__tests__/fake-llm')
  const fake = createFakeStreamFn(mocks.script as never[])
  mocks.calls = fake.calls as never
  return { createAgentModel: () => fakeModel, agentStreamFn: fake.streamFn }
})

vi.mock('@/api/chat', () => ({
  getAuthHeaders: async () => ({}),
  createChatSession: vi.fn(),
  getChatSessions: vi.fn(),
  deleteChatSession: vi.fn(),
  updateChatSession: vi.fn(),
  summarizeChatSession: vi.fn(),
  getChatMessages: vi.fn(),
  getMediaStatus: vi.fn(),
  getAgentSession: vi.fn(),
  syncAgentSession: vi.fn(),
}))
vi.mock('@/api/images', () => ({ createImageTask: vi.fn() }))
vi.mock('@/api/videos', () => ({ createVideoTask: vi.fn() }))
vi.mock('@/api/presets', () => ({ getPreset: vi.fn() }))
vi.mock('@/stores/taskQueue', () => ({
  useTaskQueueStore: () => ({ registerChatTask: vi.fn(), updateChatTask: vi.fn() }),
}))
vi.mock('@/stores/models', () => ({
  useModelsStore: () => ({ getDefaultModel: () => 'm-x' }),
}))
vi.mock('@/lib/agent/skills', () => ({
  listAgentSkills: vi.fn(async () => []),
}))

import { useChatStore, chatContextFromRows } from '../chat'
import {
  createChatSession, getChatSessions, summarizeChatSession,
  getChatMessages, getMediaStatus, getAgentSession, syncAgentSession,
} from '@/api/chat'
import { createImageTask } from '@/api/images'

function textTurn(content: string) {
  return { text: content }
}
function toolTurn(calls: Array<{ id: string; name: string; args: Record<string, unknown> }>) {
  return { toolCalls: calls }
}

const api = vi.mocked({
  createChatSession,
  getChatSessions,
  summarizeChatSession,
  getChatMessages,
  getMediaStatus,
  getAgentSession,
  syncAgentSession,
})

beforeEach(() => {
  setActivePinia(createPinia())
  mocks.script.length = 0
  mocks.calls.length = 0
  api.createChatSession.mockReset().mockResolvedValue({ id: 1, title: '新对话', created_at: '', updated_at: '' })
  api.getChatSessions.mockReset().mockResolvedValue({ total: 1, page: 1, page_size: 50, items: [{ id: 1, title: '新对话', created_at: '', updated_at: '' }] })
  api.summarizeChatSession.mockReset().mockResolvedValue({ title: '总结标题' })
  api.getChatMessages.mockReset().mockResolvedValue({ items: [] })
  api.getMediaStatus.mockReset().mockRejectedValue(new Error('no poll'))
  api.getAgentSession.mockReset().mockRejectedValue(new Error('no ctx'))
  api.syncAgentSession.mockReset().mockResolvedValue({ id: 1, title: '', created_at: '', updated_at: '' })
  vi.mocked(createImageTask).mockReset().mockResolvedValue({ task_id: 'img_1', status: 'pending' } as never)
})

describe('chat store：内核投影', () => {
  it('发送纯文本：user/assistant 投影 + 全量同步（含内核 context）', async () => {
    mocks.script.push(textTurn('你好呀'))
    const chat = useChatStore()
    await chat.send('你好')

    expect(chat.error).toBeNull()
    expect(chat.busy).toBe(false)
    expect(chat.messages.map((m) => m.role)).toEqual(['user', 'assistant'])
    expect(chat.messages[1].content).toBe('你好呀')
    // messageItems 视图：最后一条 assistant 带 streaming=false（busy 已结束）
    expect(chat.messageItems).toHaveLength(2)

    expect(api.syncAgentSession).toHaveBeenCalled()
    const payload = api.syncAgentSession.mock.calls[api.syncAgentSession.mock.calls.length - 1][1]
    expect(payload.messages.map((m) => m.role)).toEqual(['user', 'assistant'])
    expect(payload.context).toHaveProperty('messages')
  })

  it('生成工具：tool_end 挂 pending 占位，轮询 success 回填 URL', async () => {
    mocks.script.push(
      toolTurn([{ id: 't1', name: 'generate_image', args: { prompt: 'a cat', mode: 'text2image' } }]),
      textTurn('已提交生成'),
    )
    api.getMediaStatus.mockResolvedValue({ status: 'success', result_url: 'https://cdn/cat.png' })

    const chat = useChatStore()
    await chat.send('画一只猫')

    const assistant = chat.messages[1]
    expect(assistant.media).toHaveLength(1)
    expect(assistant.media[0]).toMatchObject({ type: 'image', task_id: 'img_1' })

    await vi.waitFor(() => expect(assistant.media[0].status).toBe('success'))
    expect(assistant.media[0].url).toBe('https://cdn/cat.png')
    chat.stopAllMediaPolls()
  })

  it('首轮 done 后标题为空自动总结', async () => {
    api.createChatSession.mockResolvedValue({ id: 1, title: '', created_at: '', updated_at: '' })
    api.getChatSessions.mockResolvedValue({ total: 1, page: 1, page_size: 50, items: [{ id: 1, title: '', created_at: '', updated_at: '' }] })
    mocks.script.push(textTurn('好'))
    const chat = useChatStore()
    await chat.send('帮我想个标题')
    await vi.waitFor(() => expect(api.summarizeChatSession).toHaveBeenCalledWith(1))
    await vi.waitFor(() => expect(chat.sessions[0]?.title).toBe('总结标题'))
  })
})

describe('chat store：切换与存量兼容', () => {
  it('切换会话：context 恢复优先，消息行投影（附图/媒体/步骤）', async () => {
    api.getChatSessions.mockResolvedValue({
      total: 1, page: 1, page_size: 50,
      items: [
        { id: 1, title: '新对话', created_at: '', updated_at: '' },
        { id: 2, title: '旧会话', created_at: '', updated_at: '' },
      ],
    })
    api.getAgentSession.mockResolvedValue({
      id: 2, title: '旧会话', created_at: '', updated_at: '',
      context: { messages: [{ role: 'user', content: '历史上下文' }] },
    })
    api.getChatMessages.mockResolvedValue({
      items: [
        {
          id: 1, session_id: 2, role: 'user', content: '画一只猫', created_at: '',
          attachments: [{ name: 'ref.png', base64_image: 'data:image/png;base64,QQ==', mime_type: 'image/png', size: 1 }],
        },
        {
          id: 2, session_id: 2, role: 'assistant', content: '完成', created_at: '',
          media_items: [{ type: 'image', url: 'https://cdn/old.png', task_id: 'img_9', status: 'success' }],
          steps: [{ callId: 't9', tool: 'generate_image', args: {}, status: 'done', result: '{}' }],
        },
      ],
    })

    const chat = useChatStore()
    await chat.init()
    await chat.switchSession(2)

    expect(chat.activeSessionId).toBe(2)
    expect(chat.messages).toHaveLength(2)
    expect(chat.messages[0].images).toEqual([{ data: 'QQ==', mimeType: 'image/png' }])
    expect(chat.messages[1].media[0]).toMatchObject({ url: 'https://cdn/old.png', status: 'success' })
    expect(chat.messages[1].steps[0]).toMatchObject({ tool: 'generate_image', status: 'done' })
  })

  it('存量会话无 context 时从消息行重建（chatContextFromRows）', () => {
    const ctx = chatContextFromRows([
      {
        id: 1, session_id: 1, role: 'user', content: '看这张', created_at: '',
        attachments: [{ name: 'a.png', base64_image: 'data:image/jpeg;base64,QQ==', mime_type: 'image/jpeg', size: 1 }],
      },
      { id: 2, session_id: 1, role: 'assistant', content: '好的', created_at: '' },
    ] as never[] as never)
    const messages = (ctx as { messages: Array<{ role: string; content: unknown }> }).messages
    expect(messages).toHaveLength(2)
    const userContent = messages[0].content as Array<{ type: string }>
    expect(userContent.some((b) => b.type === 'image')).toBe(true)
    expect(messages[1].content).toBe('好的')
  })
})
