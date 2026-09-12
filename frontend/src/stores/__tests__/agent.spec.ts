/* 画布 Agent store 投影层单测：mock 内核 LLM 流（@/lib/agent/provider）+ 内存 localforage + 假画布 store
 * 内核循环语义的详细断言在 lib/agent/__tests__/kernel.spec.ts，此处聚焦事件 → UI 投影 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// ---------- hoisted 共享 mock 状态 ----------

const mocks = vi.hoisted(() => {
  const script: unknown[] = []
  const calls: unknown[] = []
  const storage = new Map<string, unknown>()
  const canvasPanels: Array<{ id: string; type?: string; content: Record<string, unknown> }> = []
  const api = {
    getChatSessions: vi.fn(),
    createAgentSession: vi.fn(),
    syncAgentSession: vi.fn(),
    getAgentSession: vi.fn(),
    deleteChatSession: vi.fn(),
    updateChatSession: vi.fn(),
  }
  return { script, calls, storage, canvasPanels, api }
})

vi.mock('@/lib/agent/provider', async () => {
  const { createFakeStreamFn, fakeModel } = await import('../../lib/agent/__tests__/fake-llm')
  const fake = createFakeStreamFn(mocks.script as never[])
  mocks.calls = fake.calls as never
  // 透传 id：setChatModel 热更新内核模型后可断言 currentModelId
  return {
    createAgentModel: (id?: string) => ({ ...fakeModel, id: id || fakeModel.id }),
    agentStreamFn: fake.streamFn,
  }
})

vi.mock('localforage', () => ({
  default: {
    createInstance: () => ({
      getItem: (key: string) => Promise.resolve(mocks.storage.get(key) ?? null),
      setItem: (key: string, value: unknown) => { mocks.storage.set(key, value); return Promise.resolve(value) },
      removeItem: (key: string) => { mocks.storage.delete(key); return Promise.resolve() },
    }),
  },
}))

vi.mock('@/api/chat', () => ({
  getAuthHeaders: async () => ({}),
  ...mocks.api,
}))

vi.mock('@/stores/user', () => ({
  useUserStore: () => null,
}))

vi.mock('@/stores/canvas', () => ({
  useCanvasStore: () => ({
    activeWorkspaceId: 'ws-test',
    panels: mocks.canvasPanels,
    connections: [],
    selectedPanelIds: [],
    lastConnectionError: null,
    activeStyleConfig: { prefix: '', suffix: '', negativePrompt: '' },
    setWorkspaceStyleConfig: () => {},
    addPanel(input: { type?: string; content?: Record<string, unknown> }) {
      const pid = `np${mocks.canvasPanels.length + 1}`
      mocks.canvasPanels.push({ id: pid, type: input.type, content: input.content || {} })
      return pid
    },
    updatePanel: () => {},
    deletePanel: () => {},
    addConnection: () => ({ id: 'c1', source_panel_id: 'a', target_panel_id: 'b', type: 'manual', created_at: '' }),
    deleteConnection: () => {},
    selectPanel: () => {},
    pushSnapshot: () => {},
  }),
}))

import { useAgentStore } from '../agent'

function textTurn(content: string) {
  return { text: content }
}
function toolTurn(calls: Array<{ id: string; name: string; args: Record<string, unknown> }>) {
  return { toolCalls: calls }
}

beforeEach(() => {
  setActivePinia(createPinia())
  mocks.script.length = 0
  mocks.calls.length = 0
  mocks.storage.clear()
  mocks.canvasPanels.length = 0
  // 后端默认不可用：存量用例走本地缓存兜底语义；同步用例内再 mock 成功
  for (const fn of Object.values(mocks.api)) fn.mockReset()
  mocks.api.getChatSessions.mockRejectedValue(new Error('backend 不可用'))
  mocks.api.createAgentSession.mockRejectedValue(new Error('backend 不可用'))
  mocks.api.syncAgentSession.mockRejectedValue(new Error('backend 不可用'))
  mocks.api.getAgentSession.mockRejectedValue(new Error('backend 不可用'))
  // 内核是模块单例：清空 transcript 并把事件重绑到当前 store 实例
  useAgentStore()._ensureKernel().reset()
})

describe('Agent store：事件投影', () => {
  it('自动档：工具步骤与最终回复按时间线投影，画布真实写入', async () => {
    mocks.script.push(
      toolTurn([{ id: 't1', name: 'agent_create_text_node', args: { text: '开场' } }]),
      textTurn('已创建完成'),
    )
    const agent = useAgentStore()
    agent.mode = 'auto'
    await agent.send('帮我建一个文本节点')

    expect(agent.error).toBeNull()
    expect(agent.busy).toBe(false)
    expect(agent.messages.length).toBe(3)
    expect(agent.messages[1].steps.length).toBe(1)
    expect(agent.messages[1].steps[0].status).toBe('done')
    expect(agent.messages[2].content).toBe('已创建完成')
    expect(mocks.canvasPanels.some((p) => p.content.content === '开场')).toBe(true)

    // 会话已持久化（meta + data 双 key）
    expect([...mocks.storage.keys()].some((k) => k.startsWith('agent_session'))).toBe(true)
  })

  it('确认档：写操作随阶段门放行语义直接执行，不弹卡片', async () => {
    mocks.script.push(
      toolTurn([{ id: 't1', name: 'agent_apply_ops', args: { ops: [{ op: 'add_panel', type: 'text', content: { text: 'X' } }] } }]),
      textTurn('done'),
    )
    const agent = useAgentStore()
    await agent.send('建节点')
    expect(agent.pendingConfirm).toBeNull()
    expect(agent.messages[1].steps[0].status).toBe('done')
    expect(agent.error).toBeNull()
    expect(mocks.canvasPanels.length).toBe(1)
  })

  it('确认档：阶段门弹卡片等待审阅，放行后步骤完成', async () => {
    mocks.script.push(
      toolTurn([{ id: 't1', name: 'agent_stage_review', args: { stage: '剧本', summary: '已生成剧本节点' } }]),
      textTurn('继续下一阶段'),
    )
    const agent = useAgentStore()
    const sendPromise = agent.send('继续')
    await vi.waitFor(() => expect(agent.pendingConfirm).toBeTruthy())
    expect(agent.pendingConfirm?.kind).toBe('stage')
    expect(agent.pendingConfirm?.stage).toBe('剧本')
    expect(agent.messages[1].steps[0].status).toBe('running')

    agent.confirmPending(true)
    await sendPromise
    expect(agent.pendingConfirm).toBeNull()
    expect(agent.messages[1].steps[0].status).toBe('done')
    // 通过的阶段门机械提示下一阶段，避免 LLM 把"满意"误解为任务结束
    expect(agent.messages[1].steps[0].result).toContain('下一阶段：实体设定')
    expect(agent.messages[2].content).toBe('继续下一阶段')
  })

  it('确认档：阶段门被暂停则流程停止并给出交代', async () => {
    mocks.script.push(
      toolTurn([{ id: 't1', name: 'agent_stage_review', args: { stage: '剧本', summary: '初稿' } }]),
    )
    const agent = useAgentStore()
    const sendPromise = agent.send('写剧本')
    await vi.waitFor(() => expect(agent.pendingConfirm).toBeTruthy())
    agent.confirmPending(false)
    await sendPromise

    expect(agent.messages[1].steps[0].status).toBe('rejected')
    expect(agent.messages[1].steps[0].result).toContain('暂停')
    // 停止交代是最后一条，且不再有后续 LLM 回复
    expect(agent.messages[agent.messages.length - 1].content).toContain('已停止执行')
    expect(agent.busy).toBe(false)
  })

  it('自动档：阶段门直通不再弹确认', async () => {
    mocks.script.push(
      toolTurn([{ id: 't1', name: 'agent_stage_review', args: { stage: '剧本', summary: '初稿' } }]),
      textTurn('继续'),
    )
    const agent = useAgentStore()
    agent.mode = 'auto'
    await agent.send('全自动跑')
    expect(agent.pendingConfirm).toBeNull()
    expect(agent.messages[1].steps[0].status).toBe('done')
    expect(agent.messages[1].steps[0].result).toContain('下一阶段')
  })

  it('停止：阶段等待中 requestStop 结束当前回合并给出交代', async () => {
    mocks.script.push(
      toolTurn([{ id: 't1', name: 'agent_stage_review', args: { stage: '剧本', summary: '初稿' } }]),
    )
    const agent = useAgentStore()
    const sendPromise = agent.send('写剧本')
    await vi.waitFor(() => expect(agent.pendingConfirm).toBeTruthy())

    agent.requestStop()
    await sendPromise
    expect(agent.busy).toBe(false)
    expect(agent.messages[1].steps[0].status).toBe('rejected')
    expect(agent.messages[agent.messages.length - 1].content).toContain('已停止执行')
  })

  it('空闲时 requestStop 不产生任何效果', async () => {
    const agent = useAgentStore()
    agent.requestStop()
    expect(agent.busy).toBe(false)
    expect(agent.messages.length).toBe(0)
  })

  it('确认档：生成阶段首次执行前内核强制过门', async () => {
    mocks.script.push(
      toolTurn([{ id: 't1', name: 'agent_run_generation', args: { panel_id: 'p1', kind: 'image' } }]),
      textTurn('ok'),
    )
    const agent = useAgentStore()
    const sendPromise = agent.send('生成分镜图')
    await vi.waitFor(() => expect(agent.pendingConfirm).toBeTruthy())
    expect(agent.pendingConfirm?.kind).toBe('stage')
    expect(agent.pendingConfirm?.stage).toBe('分镜图')

    agent.confirmPending(true)
    await sendPromise
    // 门已放行并执行（假画布无该节点故工具报错），但不再二次拦截
    expect(agent.messages[1].steps[0].status).toBe('error')
    expect(agent.error).toBeNull()
    expect(agent.messages[2].content).toBe('ok')
  })

  it('确认档：拒绝生成阶段则整个流程停止', async () => {
    mocks.script.push(
      toolTurn([{ id: 't1', name: 'agent_run_generation', args: { panel_id: 'p1', kind: 'video' } }]),
    )
    const agent = useAgentStore()
    const sendPromise = agent.send('生成视频')
    await vi.waitFor(() => expect(agent.pendingConfirm).toBeTruthy())
    expect(agent.pendingConfirm?.stage).toBe('分段视频')

    agent.confirmPending(false)
    await sendPromise
    expect(agent.messages[1].steps[0].status).toBe('rejected')
    expect(agent.messages[agent.messages.length - 1].content).toContain('已停止执行')
    expect(mocks.canvasPanels.length).toBe(0)
  })

  it('只读档：写工具直接拒绝且不弹确认', async () => {
    mocks.script.push(
      toolTurn([{ id: 't1', name: 'agent_create_text_node', args: { text: 'A' } }]),
      textTurn('只读模式无法执行'),
    )
    const agent = useAgentStore()
    agent.mode = 'readonly'
    await agent.send('建节点')

    expect(agent.pendingConfirm).toBeNull()
    expect(agent.messages[1].steps[0].status).toBe('rejected')
    expect(mocks.canvasPanels.length).toBe(0)
    expect(agent.messages[2].content).toBe('只读模式无法执行')
  })

  it('达到回合上限时终止并报错', async () => {
    for (let i = 0; i < 41; i++) {
      mocks.script.push(toolTurn([{ id: `t${i}`, name: 'agent_get_state', args: {} }]))
    }
    const agent = useAgentStore()
    await agent.send('循环测试')
    expect(agent.error).toContain('上限')
    expect(mocks.calls.length).toBe(41)
  })

  it('LLM 流异常时记录 error 且不崩溃', async () => {
    // 脚本为空 → 假流抛错 → done(error)
    const agent = useAgentStore()
    await agent.send('随便说说')
    expect(agent.error).toContain('脚本')
    expect(agent.busy).toBe(false)
  })

  it('clearSession 清空当前会话内容并保留会话身份', async () => {
    mocks.script.push(textTurn('hi'))
    const agent = useAgentStore()
    await agent.send('你好')
    expect(agent.messages.length).toBe(2)
    await agent.clearSession()
    expect(agent.messages.length).toBe(0)
    // 会话身份保留：仍是同一活跃会话，标题重置待重新派生
    expect(agent.sessions).toHaveLength(1)
    expect(agent.sessions[0]?.id).toBe(agent.activeSessionId)
    expect(agent.sessions[0]?.title).toBe('')
  })

  it('会话恢复：持久化状态重建时间线（步骤回填完成态）', async () => {
    mocks.script.push(
      toolTurn([{ id: 't1', name: 'agent_create_text_node', args: { text: '开场' } }]),
      textTurn('完成'),
    )
    const first = useAgentStore()
    await first.send('建节点')
    expect(mocks.storage.size).toBeGreaterThan(0)

    // 新 pinia（模拟刷新页面）：内核单例被 restore 覆盖状态，时间线重建
    setActivePinia(createPinia())
    const second = useAgentStore()
    await second.ensureSession()
    // user / assistant(toolCall 折叠为步骤) / assistant(最终回复)
    expect(second.messages.length).toBe(3)
    expect(second.messages[0].role).toBe('user')
    expect(second.messages[1].steps[0].status).toBe('done')
    expect(second.messages[2].content).toBe('完成')

    // 恢复后继续对话，上下文连续（下一轮 LLM 收到完整历史：4 条恢复 + 新 user）
    mocks.script.push(textTurn('好的'))
    await second.send('继续')
    const ctx = (mocks.calls[mocks.calls.length - 1] as { messages: unknown[] }).messages
    expect(ctx.length).toBe(5)
    expect(second.messages.length).toBe(5)
  })
})

describe('Agent store：多模态输入', () => {
  it('send 带图：用户气泡带图并透传内核', async () => {
    mocks.script.push(textTurn('这是一张海报'))
    const agent = useAgentStore()
    agent.mode = 'auto'
    await agent.send('这是什么', [{ data: 'QUJD', mimeType: 'image/png' }])

    expect(agent.error).toBeNull()
    expect(agent.messages[0].role).toBe('user')
    expect(agent.messages[0].images).toEqual([{ data: 'QUJD', mimeType: 'image/png' }])
    const firstCall = mocks.calls[0] as { messages: Array<{ role: string; content: Array<{ type: string; data?: string }> }> }
    const userMsg = firstCall.messages.find((m) => m.role === 'user')
    expect(userMsg?.content.some((b) => b.type === 'image' && b.data === 'QUJD')).toBe(true)
  })

  it('空文本带图允许发送；纯文本空消息仍被拦截', async () => {
    mocks.script.push(textTurn('收到'))
    const agent = useAgentStore()
    await agent.send('', [{ data: 'QQ==', mimeType: 'image/jpeg' }])
    expect(agent.messages[0].content).toBe('')
    expect(agent.messages[0].images?.length).toBe(1)

    await agent.send('   ')
    expect(agent.messages.length).toBe(2)
  })

  it('会话恢复：用户消息里的图片块还原为 images', async () => {
    mocks.storage.set('agent_sessions_anon_ws-test', {
      activeId: 's1',
      sessions: [{ id: 's1', title: '看图', createdAt: '', updatedAt: '' }],
    })
    mocks.storage.set('agent_session_data_anon_ws-test_s1', {
      messages: [
        { role: 'user', content: [{ type: 'text', text: '看' }, { type: 'image', data: 'QQ==', mimeType: 'image/png' }], timestamp: Date.now() },
      ],
    })
    const agent = useAgentStore()
    await agent.ensureSession()
    expect(agent.messages.length).toBe(1)
    expect(agent.messages[0].images).toEqual([{ data: 'QQ==', mimeType: 'image/png' }])
  })
})

describe('Agent store：对话模型选择', () => {
  it('setChatModel 热更新内核模型；空串回默认占位', () => {
    const agent = useAgentStore()
    agent.setChatModel('m-chat-pro')
    expect(agent.chatModelId).toBe('m-chat-pro')
    expect(agent._ensureKernel().currentModelId).toBe('m-chat-pro')

    agent.setChatModel('')
    expect(agent.chatModelId).toBe('')
    expect(agent._ensureKernel().currentModelId).toBe('fake-chat')
  })
})

describe('Agent store：会话落库同步', () => {
  it('首轮 persist 创建后端会话并回填 backendId，消息按投影同步', async () => {
    mocks.api.createAgentSession.mockResolvedValue({ id: 501, title: '', created_at: '', updated_at: '' })
    mocks.api.syncAgentSession.mockResolvedValue({ id: 501, title: '', created_at: '', updated_at: '' })
    mocks.script.push(textTurn('好的'))
    const agent = useAgentStore()
    await agent.send('画一只猫')

    expect(agent.sessions[0]?.backendId).toBe(501)
    expect(mocks.api.createAgentSession).toHaveBeenCalledWith({ title: '画一只猫', workspace_id: 'ws-test' })
    expect(mocks.api.syncAgentSession).toHaveBeenCalled()
    // send 流程会同步两次（用户消息乐观落盘 + done 收尾），取最后一次（含完整消息）
    const calls = mocks.api.syncAgentSession.mock.calls
    const payload = calls[calls.length - 1][1] as {
      messages: Array<{ role: string; content: string }>
      context: { messages?: unknown[] }
    }
    expect(payload.messages.map((m) => m.role)).toEqual(['user', 'assistant'])
    expect(payload.context).toHaveProperty('messages')
  })

  it('后端不可用时同步静默降级，不阻断对话', async () => {
    mocks.script.push(textTurn('好的'))
    const agent = useAgentStore()
    await agent.send('你好')
    expect(agent.error).toBeNull()
    expect(agent.messages.length).toBe(2)
    expect(agent.sessions[0]?.backendId).toBeNull()
    // 本地缓存已兜底写入
    expect(mocks.storage.has('agent_session_data_anon_ws-test_' + agent.sessions[0]?.id)).toBe(true)
  })

  it('openSessionByBackendId 按 backendId 定位切换', async () => {
    mocks.api.getChatSessions.mockResolvedValue({
      total: 1, page: 1, page_size: 100,
      items: [{ id: 501, title: '画布 A', session_type: 'canvas', workspace_id: 'ws-test', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }],
    })
    const agent = useAgentStore()
    expect(await agent.openSessionByBackendId(501)).toBe(true)
    expect(agent.activeSessionId).toBe('b501')
    expect(await agent.openSessionByBackendId(999)).toBe(false)
  })

  it('删除已同步会话时连后端一起删', async () => {
    const agent = useAgentStore()
    await agent.ensureSession()
    const id = agent.activeSessionId!
    agent.sessions[0]!.backendId = 501
    await agent.deleteSession(id)
    expect(mocks.api.deleteChatSession).toHaveBeenCalledWith(501)
  })
})
