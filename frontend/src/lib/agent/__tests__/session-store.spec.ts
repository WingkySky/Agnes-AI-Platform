/* Agent 会话同步层单测：消息投影 / meta 后端优先+本地合并兜底 / 同步创建回填与失败兜底 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/chat', () => ({
  getChatSessions: vi.fn(),
  createAgentSession: vi.fn(),
  syncAgentSession: vi.fn(),
  getAgentSession: vi.fn(),
  deleteChatSession: vi.fn(),
  updateChatSession: vi.fn(),
}))

import {
  setAgentSessionStorage, saveSessionsMeta,
  listSessionsMeta, syncSession, pullSession, toBackendMessages, deriveSessionTitle,
} from '../session-store'
import type { AgentKVStorage, ProjectableMessage } from '../session-store'
import { getChatSessions, createAgentSession, syncAgentSession, getAgentSession } from '@/api/chat'

const SCOPE = 'anon_default'

function memoryStorage(): AgentKVStorage {
  const map = new Map<string, unknown>()
  return {
    async getItem(key) { return map.get(key) },
    async setItem(key, value) { map.set(key, value) },
    async removeItem(key) { map.delete(key) },
  }
}

beforeEach(() => {
  vi.mocked(getChatSessions).mockReset()
  vi.mocked(createAgentSession).mockReset()
  vi.mocked(syncAgentSession).mockReset()
  vi.mocked(getAgentSession).mockReset()
  setAgentSessionStorage(memoryStorage())
})

describe('deriveSessionTitle', () => {
  it('压缩空白并截断 20 字加省略号', () => {
    expect(deriveSessionTitle('帮我把\n这个故事 做成连续短片，要求有起承转合')).toBe('帮我把 这个故事 做成连续短片，要求有起…')
  })

  it('短文本原样返回', () => {
    expect(deriveSessionTitle('  画一只猫  ')).toBe('画一只猫')
  })
})

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
})

describe('listSessionsMeta', () => {
  it('后端 canvas 会话按工作区过滤并映射 b{id}，未同步本地会话合并在前', async () => {
    vi.mocked(getChatSessions).mockResolvedValue({
      total: 2,
      page: 1,
      page_size: 100,
      items: [
        { id: 11, title: '画布 A', session_type: 'canvas', workspace_id: 'ws-1', created_at: '2026-01-02T00:00:00Z', updated_at: '2026-01-03T00:00:00Z' },
        { id: 12, title: '别的画布', session_type: 'canvas', workspace_id: 'ws-2', created_at: '2026-01-02T00:00:00Z', updated_at: '2026-01-03T00:00:00Z' },
        { id: 13, title: '对话页会话', session_type: 'chat', created_at: '2026-01-02T00:00:00Z', updated_at: '2026-01-03T00:00:00Z' },
      ],
    })
    // 本地有一份从未同步成功的会话
    await saveSessionsMeta(SCOPE, {
      activeId: 'local1',
      sessions: [{ id: 'local1', backendId: null, title: '离线新建', createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z' }],
    })

    const meta = await listSessionsMeta(SCOPE, 'ws-1')
    expect(meta.sessions.map((s) => s.id)).toEqual(['local1', 'b11'])
    expect(meta.sessions[1]).toMatchObject({ backendId: 11, title: '画布 A' })
    // activeId 命中未同步会话则保留
    expect(meta.activeId).toBe('local1')
  })

  it('activeId 失效时回退列表第一条', async () => {
    vi.mocked(getChatSessions).mockResolvedValue({
      total: 1, page: 1, page_size: 100,
      items: [{ id: 11, title: '画布 A', session_type: 'canvas', workspace_id: 'ws-1', created_at: '2026-01-02T00:00:00Z', updated_at: '2026-01-03T00:00:00Z' }],
    })
    const meta = await listSessionsMeta(SCOPE, 'ws-1')
    expect(meta.activeId).toBe('b11')
  })

  it('后端失败走本地缓存兜底（含未同步会话）', async () => {
    vi.mocked(getChatSessions).mockRejectedValue(new Error('网络不可用'))
    await saveSessionsMeta(SCOPE, {
      activeId: 'local1',
      sessions: [
        { id: 'local1', backendId: null, title: '离线', createdAt: '', updatedAt: '' },
        { id: 'b11', backendId: 11, title: '已同步缓存', createdAt: '', updatedAt: '' },
      ],
    })
    const meta = await listSessionsMeta(SCOPE, 'ws-1')
    expect(meta.sessions.map((s) => s.id)).toEqual(['local1', 'b11'])
    expect(meta.activeId).toBe('local1')
  })
})

describe('syncSession / pullSession', () => {
  const INPUT = {
    title: '画布 A',
    workspaceId: 'ws-1',
    context: { messages: [{ role: 'user', content: 'hi' }] },
    messages: [{ role: 'user' as const, content: 'hi' }],
  }

  it('无 backendId 时先创建再同步，回填 backendId 并写缓存', async () => {
    vi.mocked(createAgentSession).mockResolvedValue({ id: 77, title: '画布 A', created_at: '', updated_at: '' })
    vi.mocked(syncAgentSession).mockResolvedValue({ id: 77, title: '画布 A', created_at: '', updated_at: '' })

    const res = await syncSession(SCOPE, 'abc', INPUT, null)
    expect(res).toEqual({ backendId: 77, ok: true })
    expect(vi.mocked(createAgentSession)).toHaveBeenCalledWith({ title: '画布 A', workspace_id: 'ws-1' })
    expect(vi.mocked(syncAgentSession)).toHaveBeenCalledWith(77, {
      title: '画布 A',
      workspace_id: 'ws-1',
      context: INPUT.context,
      messages: INPUT.messages,
    })
    // 缓存已写：pullSession 无 backendId 也能读到 context
    const cached = await pullSession(SCOPE, 'abc', null)
    expect(cached).toEqual(INPUT.context)
  })

  it('同步失败返回 ok:false 并保留缓存兜底', async () => {
    vi.mocked(createAgentSession).mockResolvedValue({ id: 77, title: '', created_at: '', updated_at: '' })
    vi.mocked(syncAgentSession).mockRejectedValue(new Error('网络不可用'))

    const res = await syncSession(SCOPE, 'abc', INPUT, 77)
    expect(res).toEqual({ backendId: 77, ok: false })
    const cached = await pullSession(SCOPE, 'abc', 77)
    expect(cached).toEqual(INPUT.context)
  })

  it('恢复后端优先：getAgentSession 返回的 context 优先于本地缓存', async () => {
    vi.mocked(getAgentSession).mockResolvedValue({
      id: 77, title: '', created_at: '', updated_at: '',
      context: { messages: [{ role: 'user', content: 'from-backend' }] },
    })
    const ctx = await pullSession(SCOPE, 'abc', 77)
    expect(ctx).toEqual({ messages: [{ role: 'user', content: 'from-backend' }] })
  })

  it('后端拉取失败读本地缓存', async () => {
    vi.mocked(getAgentSession).mockRejectedValue(new Error('网络不可用'))
    await syncSession(SCOPE, 'abc', INPUT, 77) // 先写一份缓存
    vi.mocked(getAgentSession).mockRejectedValue(new Error('网络不可用'))
    const ctx = await pullSession(SCOPE, 'abc', 77)
    expect(ctx).toEqual(INPUT.context)
  })
})
