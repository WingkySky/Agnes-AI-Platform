/* Agent 统一宿主（chat store 并入画布 Agent 能力）单测：
 * - 全局档位：localStorage 记忆 + 切档
 * - 画布深度工具挂载开关：setExtraTools 热更 + 系统提示画布段
 * - 确认卡链路：confirm_request 事件接入（带归属会话）+ confirmPending 解析 + done 清理
 * - extraTools 装配：MCP 工具与画布深度工具合并注入 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mocks = vi.hoisted(() => {
  const canvasState = {
    activeWorkspaceId: null as string | null,
    workspaces: [] as { id: string; name: string }[],
    _storageReady: false,
    createWorkspace: (name: string) => {
      canvasState.workspaces.push({ id: 'ws_new', name })
      canvasState.activeWorkspaceId = 'ws_new'
    },
  }
  const kernels: FakeKernel[] = []
  class FakeKernel {
    setModel = vi.fn()
    setExtraTools = vi.fn()
    setSystemPrompt = vi.fn()
    subscribe = vi.fn(() => vi.fn())
    restore = vi.fn(() => false)
    reset = vi.fn()
    confirm = vi.fn()
    requestStop = vi.fn()
    constructor() { kernels.push(this) }
  }
  return {
    kernels, FakeKernel, canvasState,
    applyCanvasOps: vi.fn(async () => ({ results: [], new_panel_ids: [], failed: 0, revision: 2 })),
    isCloudChannel: vi.fn(() => true),
    getPreferences: vi.fn(async () => ({ preferences: { ui: { canvas_active_workspace_id: '' } } })),
    patchPreferences: vi.fn(async () => ({})),
    getWorkspaceRevision: vi.fn(async () => ({ revision: 1 })),
    listWorkspaces: vi.fn(async () => [] as { id: string; name: string; updated_at: string }[]),
    createWorkspaceApi: vi.fn(async () => ({ id: 'ws_api_created', name: 'Chat Canvas', revision: 1 })),
  }
})

vi.mock('@/lib/agent/kernel', () => ({
  AgentKernel: mocks.FakeKernel,
}))

vi.mock('@/lib/agent/chat-tools', () => {
  const markerTool = { name: 'canvas_marker_tool', description: 'marker', parameters: {}, execute: () => ({ ok: true, data: {} }) }
  return {
    CHAT_TOOLS: [],
    CHAT_TOOL_NAMES: [],
    canvasHostTools: () => [markerTool],
  }
})

vi.mock('@/lib/agent/chat-system-prompt', () => ({
  CHAT_SYSTEM_PROMPT_BASE: 'BASE',
  buildChatSystemPrompt: () => 'BASE',
}))

vi.mock('@/lib/agent/system-prompt', () => ({
  CANVAS_CONTEXT_SECTION: 'CANVAS_SECTION',
}))

vi.mock('@/lib/agent/skills', () => ({
  listAgentSkills: vi.fn(async () => []),
}))

vi.mock('@/lib/agent/mcp', () => ({
  fetchMcpBundle: vi.fn(async () => ({ tools: [{ name: 'mcp__1__t', description: 'm', parameters: {}, execute: () => ({ ok: true, data: {} }) }], summary: 'MCPSUM', capabilities: [{ name: 'demo', tools: ['t'] }] })),
}))

vi.mock('@/lib/agent/memory', () => ({
  fetchMemoryState: vi.fn(async () => ({ section: 'MEM', available: true, preferences: ['p1'] })),
}))

vi.mock('@/lib/agent/bridge', () => ({
  listBridgeTargets: vi.fn(async () => []),
  relayCall: vi.fn(),
}))

vi.mock('@/lib/agent/session-store', () => ({
  toBackendMessages: () => [],
}))

vi.mock('@/lib/agent/subagent', () => ({
  setDelegateProgressSink: vi.fn(),
}))

vi.mock('@/lib/agent/provider', () => ({
  createAgentModel: () => ({ id: 'model-x' }),
}))

vi.mock('@/api/chat', () => ({
  getAuthHeaders: vi.fn(async () => ({})),
  createChatSession: vi.fn(),
  getChatSessions: vi.fn(async () => ({ items: [] })),
  deleteChatSession: vi.fn(),
  updateChatSession: vi.fn(),
  summarizeChatSession: vi.fn(),
  getChatMessages: vi.fn(async () => ({ items: [] })),
  getAgentSession: vi.fn(async () => { throw new Error('no session') }),
  syncAgentSession: vi.fn(),
  getMediaStatus: vi.fn(),
}))

vi.mock('@/api/mcp', () => ({
  deleteMemoryPreference: vi.fn(),
  clearMemoryPreferences: vi.fn(),
}))

vi.mock('@/stores/taskQueue', () => ({
  useTaskQueueStore: () => ({ registerChatTask: vi.fn() }),
}))

vi.mock('@/stores/preferences', () => ({
  usePreferencesStore: () => ({ ui: { canvas_active_workspace_id: 'ws_active' } }),
}))

vi.mock('@/stores/canvas', () => ({
  useCanvasStore: () => mocks.canvasState,
}))

vi.mock('@/lib/canvas-storage', () => ({
  isCloudChannel: mocks.isCloudChannel,
}))

vi.mock('@/api/preferences', () => ({
  getPreferences: mocks.getPreferences,
  patchPreferences: mocks.patchPreferences,
}))

vi.mock('@/api/canvasWorkspace', () => ({
  applyCanvasOps: mocks.applyCanvasOps,
  getWorkspaceRevision: mocks.getWorkspaceRevision,
  listWorkspaces: mocks.listWorkspaces,
  createWorkspace: mocks.createWorkspaceApi,
}))

import { useChatStore, chatContextFromRows } from '../chat'

// node 测试环境无 localStorage：内存实现打桩（chat store 与档位记忆共用）
const lsMap = new Map<string, string>()
const localStorageStub = {
  getItem: (k: string) => lsMap.get(k) ?? null,
  setItem: (k: string, v: string) => { lsMap.set(k, v) },
  removeItem: (k: string) => { lsMap.delete(k) },
}

beforeEach(() => {
  vi.stubGlobal('localStorage', localStorageStub)
  lsMap.clear()
  lsMap.set('agnes_agent_mode', 'auto')
  setActivePinia(createPinia())
  mocks.kernels.length = 0
  mocks.canvasState.activeWorkspaceId = null
  mocks.canvasState.workspaces = []
  mocks.canvasState._storageReady = false
  vi.mocked(mocks.isCloudChannel).mockReturnValue(true)
  vi.mocked(mocks.getPreferences).mockReset().mockResolvedValue({ preferences: { ui: { canvas_active_workspace_id: '' } } })
  vi.mocked(mocks.patchPreferences).mockReset().mockResolvedValue({})
  vi.mocked(mocks.getWorkspaceRevision).mockReset().mockResolvedValue({ revision: 1 })
  vi.mocked(mocks.listWorkspaces).mockReset().mockResolvedValue([])
  vi.mocked(mocks.createWorkspaceApi).mockReset().mockResolvedValue({ id: 'ws_api_created', name: 'Chat Canvas', revision: 1 })
})

describe('Agent 统一宿主：全局档位', () => {
  it('初始档位读 localStorage 记忆', () => {
    const store = useChatStore()
    expect(store.agentMode).toBe('auto')
  })

  it('setAgentMode 切档并持久化；内核 getMode 实时读到新档位', async () => {
    const store = useChatStore()
    await store._kernelFor(1)
    expect(store.agentMode).toBe('auto')
    store.setAgentMode('readonly')
    expect(store.agentMode).toBe('readonly')
    expect(lsMap.get('agnes_agent_mode')).toBe('readonly')
    // 内核经 deps.getMode 闭包读 store（创建时注入），这里验证切档不重建内核
    expect(mocks.kernels).toHaveLength(1)
  })
})

describe('Agent 统一宿主：scope 注册制（宿主深度工具挂载）', () => {
  it('registerAgentScope(canvas)：池内内核 setExtraTools 注入画布工具，系统提示附加画布段', async () => {
    const store = useChatStore()
    await store._kernelFor(1)
    const k = mocks.kernels[0]
    // 创建时画布未注册：extraTools 仅 MCP 工具
    const createdArgs = k.setExtraTools.mock.calls[0][0] as { name: string }[]
    expect(createdArgs.map((t) => t.name)).toEqual(['mcp__1__t'])

    store.registerAgentScope({ host: 'canvas' })
    const lastArgs = k.setExtraTools.mock.calls[k.setExtraTools.mock.calls.length - 1]![0] as { name: string }[]
    expect(lastArgs.map((t) => t.name)).toContain('canvas_marker_tool')
    expect(lastArgs.map((t) => t.name)).toContain('mcp__1__t')
    // 系统提示附加画布段
    const prompts = k.setSystemPrompt.mock.calls.map((c) => String(c[0]))
    expect(prompts.some((p) => p.includes('CANVAS_SECTION'))).toBe(true)

    store.unregisterAgentScope('canvas')
    const offArgs = k.setExtraTools.mock.calls[k.setExtraTools.mock.calls.length - 1]![0] as { name: string }[]
    expect(offArgs.map((t) => t.name)).toEqual(['mcp__1__t'])
  })

  it('registerAgentScope 幂等：同 host 同元数据重复注册不重复热更内核', async () => {
    const store = useChatStore()
    await store._kernelFor(1)
    const k = mocks.kernels[0]
    const callsBefore = k.setExtraTools.mock.calls.length
    store.registerAgentScope({ host: 'canvas' })
    const afterFirst = k.setExtraTools.mock.calls.length
    expect(afterFirst).toBeGreaterThan(callsBefore)
    store.registerAgentScope({ host: 'canvas' })
    expect(k.setExtraTools.mock.calls.length).toBe(afterFirst)
  })

  it('editor scope 只注册元数据：不注入画布工具，不附加画布提示段', async () => {
    const store = useChatStore()
    await store._kernelFor(1)
    const k = mocks.kernels[0]
    k.setExtraTools.mockClear()
    k.setSystemPrompt.mockClear()
    store.registerAgentScope({ host: 'editor', projectId: 'proj_1' })
    expect(store.agentScopes.editor?.projectId).toBe('proj_1')
    expect(k.setExtraTools).toHaveBeenCalledTimes(1)
    const args = k.setExtraTools.mock.calls[0][0] as { name: string }[]
    expect(args.map((t) => t.name)).toEqual(['mcp__1__t'])
    const prompts = k.setSystemPrompt.mock.calls.map((c) => String(c[0]))
    expect(prompts.every((p) => !p.includes('CANVAS_SECTION'))).toBe(true)
    store.unregisterAgentScope('editor')
    expect(store.agentScopes.editor).toBeUndefined()
  })
})

describe('Agent 统一宿主：确认卡链路', () => {
  it('confirm_request 接入 pendingConfirm（带归属会话），confirmPending 解析对应内核', async () => {
    const store = useChatStore()
    await store._kernelFor(1)
    store.sessions = [{ id: 1, title: '', created_at: '' } as never]
    store._onKernelEvent(1, {
      type: 'confirm_request', kind: 'stage', tool: 'agent_run_generation',
      args: { kind: 'image' }, stage: '分镜图', summary: '进入分镜图生成阶段',
    } as never)
    expect(store.pendingConfirm?.sessionId).toBe(1)
    expect(store.pendingConfirm?.stage).toBe('分镜图')

    store.confirmPending(true)
    expect(mocks.kernels[0].confirm).toHaveBeenCalledWith(true)
    expect(store.pendingConfirm).toBeNull()
  })

  it('done 事件清理归属会话的待确认卡', async () => {
    const store = useChatStore()
    await store._kernelFor(2)
    store.sessions = [{ id: 2, title: '', created_at: '' } as never]
    store._onKernelEvent(2, {
      type: 'confirm_request', kind: 'tool', tool: 'mcp__1__t',
      args: {}, stage: 'mcp__1__t', summary: '首次调用外部工具',
    } as never)
    expect(store.pendingConfirm?.sessionId).toBe(2)
    store._onKernelEvent(2, { type: 'done', stopped: false, error: null })
    expect(store.pendingConfirm).toBeNull()
  })
})

describe('Agent 统一宿主：画布目标解析链', () => {
  it('显式参数直通（不做任何解析调用）', async () => {
    const store = useChatStore()
    const target = await store._resolveCanvasTarget('ws_explicit')
    expect(target).toEqual({ workspaceId: 'ws_explicit', workspaceName: '' })
    expect(mocks.getPreferences).not.toHaveBeenCalled()
    expect(mocks.listWorkspaces).not.toHaveBeenCalled()
  })

  it('画布页实时激活优先（store 内存在该工作区）', async () => {
    mocks.canvasState.activeWorkspaceId = 'ws_live'
    mocks.canvasState.workspaces = [{ id: 'ws_live', name: '实况画布' }]
    const store = useChatStore()
    const target = await store._resolveCanvasTarget()
    expect(target).toEqual({ workspaceId: 'ws_live', workspaceName: '实况画布' })
    expect(mocks.getPreferences).not.toHaveBeenCalled()
  })

  it('偏好有效：revision 验证通过即采用（现拉现读，不信旧快照）', async () => {
    vi.mocked(mocks.getPreferences).mockResolvedValue({ preferences: { ui: { canvas_active_workspace_id: 'ws_pref' } } })
    const store = useChatStore()
    const target = await store._resolveCanvasTarget()
    expect(target).toEqual({ workspaceId: 'ws_pref', workspaceName: '' })
    expect(mocks.getWorkspaceRevision).toHaveBeenCalledWith('ws_pref')
    expect(mocks.patchPreferences).not.toHaveBeenCalled()
  })

  it('偏好失效（已删除）：清除旧值并回退到最近使用的画布', async () => {
    vi.mocked(mocks.getPreferences).mockResolvedValue({ preferences: { ui: { canvas_active_workspace_id: 'ws_dead' } } })
    vi.mocked(mocks.getWorkspaceRevision).mockRejectedValue(new Error('404'))
    vi.mocked(mocks.listWorkspaces).mockResolvedValue([
      { id: 'ws_latest', name: '最近的画布', updated_at: '2026-10-02' },
    ])
    const store = useChatStore()
    const target = await store._resolveCanvasTarget()
    expect(target).toEqual({ workspaceId: 'ws_latest', workspaceName: '最近的画布' })
    expect(mocks.patchPreferences).toHaveBeenCalledWith({ ui: { canvas_active_workspace_id: '' } })
  })

  it('一个画布都没有且画布 store 已 hydrate：走 store 自动建「对话画布」', async () => {
    mocks.canvasState._storageReady = true
    const store = useChatStore()
    const target = await store._resolveCanvasTarget()
    expect(target?.created).toBe(true)
    expect(target?.workspaceId).toBe('ws_new')
    expect(mocks.canvasState.workspaces.some((w) => w.name === 'Chat Canvas')).toBe(true)
  })

  it('画布 store 未 hydrate：走 API 自动建并写偏好激活', async () => {
    const store = useChatStore()
    const target = await store._resolveCanvasTarget()
    expect(target?.created).toBe(true)
    expect(target?.workspaceId).toBe('ws_api_created')
    expect(mocks.createWorkspaceApi).toHaveBeenCalled()
    expect(mocks.patchPreferences).toHaveBeenCalledWith({ ui: { canvas_active_workspace_id: 'ws_api_created' } })
  })

  it('未登录（非云通道）：返回 null（唯一报错场景）', async () => {
    vi.mocked(mocks.isCloudChannel).mockReturnValue(false)
    const store = useChatStore()
    expect(await store._resolveCanvasTarget()).toBeNull()
  })
})

describe('chatContextFromRows：上下文重建保真', () => {
  const baseRow = {
    id: 1, session_id: 1, created_at: '',
    attachments: [], media_items: [],
  }

  it('assistant 带 steps：重建 toolCall 块 + 成对 toolResult（含 isError 映射）', () => {
    const ctx = chatContextFromRows([
      { ...baseRow, role: 'user', content: '画只猫' } as never,
      {
        ...baseRow, role: 'assistant', content: '', steps: [
          { callId: 'c1', tool: 'generate_image', args: { prompt: 'a cat' }, status: 'done', result: '{"ok":true}' },
          { callId: 'c2', tool: 'canvas_add_panels', args: {}, status: 'error', result: null },
        ],
      } as never,
      { ...baseRow, role: 'assistant', content: '图片生成好了', steps: [] } as never,
    ]) as { messages: Array<Record<string, unknown>> }

    const msgs = ctx.messages
    // user → assistant(toolUse) → toolResult ×2 → assistant(stop)
    expect(msgs.map((m) => m.role)).toEqual(['user', 'assistant', 'toolResult', 'toolResult', 'assistant'])

    const toolRound = msgs[1] as { stopReason: string; content: Array<Record<string, unknown>> }
    expect(toolRound.stopReason).toBe('toolUse')
    // 空文本不生成占位 text 块，content[0] 直接是 toolCall
    expect(toolRound.content[0]).toEqual({ type: 'toolCall', id: 'c1', name: 'generate_image', arguments: { prompt: 'a cat' } })
    expect(toolRound.content[1]).toMatchObject({ type: 'toolCall', id: 'c2', name: 'canvas_add_panels' })

    const r1 = msgs[2] as { toolCallId: string; isError: boolean; content: Array<Record<string, unknown>> }
    expect(r1).toMatchObject({ toolCallId: 'c1', isError: false })
    expect(r1.content[0]).toEqual({ type: 'text', text: '{"ok":true}' })
    const r2 = msgs[3] as { toolCallId: string; isError: boolean; content: Array<Record<string, unknown>> }
    expect(r2.isError).toBe(true)
    expect((r2.content[0] as { text: string }).text).toContain('无结果记录')

    const final = msgs[4] as { stopReason: string; content: Array<Record<string, unknown>> }
    expect(final.stopReason).toBe('stop')
    expect(final.content).toEqual([{ type: 'text', text: '图片生成好了' }])
  })

  it('user 附图块保留（base64 → image 块）', () => {
    const ctx = chatContextFromRows([
      {
        ...baseRow, role: 'user', content: '看这张图',
        attachments: [{ name: 'a.png', base64_image: 'data:image/png;base64,QQ==', mime_type: 'image/png' }],
      } as never,
    ]) as { messages: Array<{ content: Array<Record<string, unknown>> }> }
    const content = ctx.messages[0].content
    expect(content).toHaveLength(2)
    expect(content[1]).toMatchObject({ type: 'image', mimeType: 'image/png' })
  })
})
