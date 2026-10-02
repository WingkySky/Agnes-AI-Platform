/* Agent 统一宿主（chat store 并入画布 Agent 能力）单测：
 * - 全局档位：localStorage 记忆 + 切档
 * - 画布深度工具挂载开关：setExtraTools 热更 + 系统提示画布段
 * - 确认卡链路：confirm_request 事件接入（带归属会话）+ confirmPending 解析 + done 清理
 * - extraTools 装配：MCP 工具与画布深度工具合并注入 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mocks = vi.hoisted(() => {
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
  return { kernels, FakeKernel }
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

vi.mock('@/api/canvasWorkspace', () => ({
  applyCanvasOps: vi.fn(),
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

import { useChatStore } from '../chat'

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

describe('Agent 统一宿主：画布深度工具挂载', () => {
  it('setCanvasToolsActive(true)：池内内核 setExtraTools 注入画布工具，系统提示附加画布段', async () => {
    const store = useChatStore()
    await store._kernelFor(1)
    const k = mocks.kernels[0]
    // 创建时画布未激活：extraTools 仅 MCP 工具
    const createdArgs = k.setExtraTools.mock.calls[0][0] as { name: string }[]
    expect(createdArgs.map((t) => t.name)).toEqual(['mcp__1__t'])

    store.setCanvasToolsActive(true)
    const lastArgs = k.setExtraTools.mock.calls[k.setExtraTools.mock.calls.length - 1]![0] as { name: string }[]
    expect(lastArgs.map((t) => t.name)).toContain('canvas_marker_tool')
    expect(lastArgs.map((t) => t.name)).toContain('mcp__1__t')
    // 系统提示附加画布段
    const prompts = k.setSystemPrompt.mock.calls.map((c) => String(c[0]))
    expect(prompts.some((p) => p.includes('CANVAS_SECTION'))).toBe(true)

    store.setCanvasToolsActive(false)
    const offArgs = k.setExtraTools.mock.calls[k.setExtraTools.mock.calls.length - 1]![0] as { name: string }[]
    expect(offArgs.map((t) => t.name)).toEqual(['mcp__1__t'])
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
