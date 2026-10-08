/* 反向控制桥单测：relayCall 路由语义 / startBridgeClient 收发分发 / 白名单一致性 / 深度工具三分派 */

import { describe, it, expect, vi, beforeEach, afterEach, assert } from 'vitest'

vi.mock('@/api/client', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('@/api/images', () => ({ createImageTask: vi.fn() }))
vi.mock('@/api/videos', () => ({ createVideoTask: vi.fn() }))
vi.mock('@/api/presets', () => ({ getPreset: vi.fn() }))
vi.mock('@/api/canvasWorkspace', () => ({
  applyCanvasOps: vi.fn(),
  getWorkspace: vi.fn(),
  listWorkspaces: vi.fn(),
}))
vi.mock('@/api/canvas', () => ({ generateCanvasTts: vi.fn(), getCanvasVoicesCached: vi.fn(async () => ({ voices: [] })) }))
vi.mock('@/api/assets', () => ({ getAsset: vi.fn(), listAssets: vi.fn(), createAsset: vi.fn() }))
vi.mock('@/stores/taskQueue', () => ({ useTaskQueueStore: vi.fn() }))
vi.mock('@/stores/canvas', () => ({ useCanvasStore: () => fakeCanvasStore }))
vi.mock('../skills', () => ({
  loadAgentSkillFull: vi.fn(),
  readSkillResource: vi.fn(),
  saveAgentSkill: vi.fn(),
  SKILL_CONTENT_MAX_CHARS: 20000,
  getActiveSkillScope: vi.fn(() => null),
}))
vi.mock('../subagent', () => ({ runSubagent: vi.fn(), subagentHostFromParent: vi.fn() }))

import client from '@/api/client'
import { AGENT_TOOLS } from '../tools'
import { canvasHostTools, CHAT_TOOL_NAMES } from '../chat-tools'
import {
  relayCall,
  startBridgeClient,
  listBridgeTargets,
  BRIDGE_CANVAS_TOOLS,
  BRIDGE_EDITOR_TOOLS,
} from '../bridge'
import { EDITOR_TOOLS } from '../editor-tools'

const postMock = vi.mocked(client.post)
const getMock = vi.mocked(client.get)

/** 最小画布 store 替身（local 分派路径 agent_get_state 消费） */
const fakeCanvasStore = {
  activeWorkspaceId: 'ws_local',
  panels: [{ id: 'p1', type: 'text', content: {} }],
  connections: [],
  selectedPanelIds: [],
}

beforeEach(() => {
  vi.stubGlobal('localStorage', {
    getItem: () => 'token-abc',
    setItem: () => {},
    removeItem: () => {},
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('relayCall 路由语义', () => {
  it('offline → routed:offline（调用方走既有回退）', async () => {
    postMock.mockResolvedValueOnce({ routed: 'offline' })
    const r = await relayCall('canvas', 'ws_1', 'agent_apply_ops', { ops: [] })
    assert(r.routed === 'offline')
    expect(postMock).toHaveBeenCalledWith(
      '/api/agent/relay/call',
      { host: 'canvas', target_id: 'ws_1', tool: 'agent_apply_ops', args: { ops: [] } },
      { timeout: 0 },
    )
  })

  it('relay → 页面回执原样透传', async () => {
    postMock.mockResolvedValueOnce({ routed: 'relay', result: { ok: true, data: { x: 1 } } })
    const r = await relayCall('editor', 'proj_1', 'editor_apply_ops', { ops: [] })
    assert(r.routed === 'relay')
    if (r.routed === 'relay') expect(r.result).toEqual({ ok: true, data: { x: 1 } })
  })

  it('504 超时 → relay 失败结果（明确提示勿重试），绝不回退', async () => {
    postMock.mockRejectedValueOnce({ response: { status: 504 } })
    const r = await relayCall('canvas', 'ws_1', 'agent_get_state', {})
    assert(r.routed === 'relay')
    if (r.routed === 'relay') {
      expect(r.result.ok).toBe(false)
      expect(r.result.error).toContain('请勿原样重试')
    }
  })

  it('回执格式异常 → 结构化失败', async () => {
    postMock.mockResolvedValueOnce({ routed: 'relay', result: 'garbage' })
    const r = await relayCall('canvas', 'ws_1', 'agent_get_state', {})
    assert(r.routed === 'relay')
    if (r.routed === 'relay') expect(r.result.ok).toBe(false)
  })
})

describe('listBridgeTargets', () => {
  it('解包 targets，异常形状返回空数组', async () => {
    getMock.mockResolvedValueOnce({ targets: [{ host: 'canvas', target_id: 'ws_9' }] })
    expect(await listBridgeTargets()).toEqual([{ host: 'canvas', target_id: 'ws_9' }])
    getMock.mockResolvedValueOnce({})
    expect(await listBridgeTargets()).toEqual([])
  })
})

describe('startBridgeClient', () => {
  class FakeWebSocket {
    static OPEN = 1
    static instances: FakeWebSocket[] = []
    readyState = 1
    sent: string[] = []
    onopen: (() => void) | null = null
    onmessage: ((ev: { data: string }) => void) | null = null
    onclose: (() => void) | null = null
    onerror: (() => void) | null = null
    constructor(public url: string) {
      FakeWebSocket.instances.push(this)
    }
    send(data: string) {
      this.sent.push(data)
    }
    close() {
      this.readyState = 3
      this.onclose?.()
    }
    /** 测试辅助：服务端消息进入 */
    serverSend(payload: unknown) {
      this.onmessage?.({ data: JSON.stringify(payload) })
    }
  }

  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal('location', { protocol: 'http:', host: 'test' })
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('连接后注册（token 查询参 + host/target）并按心跳保活', async () => {
    const handle = startBridgeClient({
      host: 'canvas',
      getTargetId: () => 'ws_x',
      executors: {},
    })
    await Promise.resolve()
    const ws = FakeWebSocket.instances[0]
    expect(ws.url).toContain('/api/agent/relay/ws?token=token-abc')
    ws.onopen?.()
    const registerMsg = JSON.parse(ws.sent[0])
    expect(registerMsg).toEqual({ type: 'register', host: 'canvas', target_id: 'ws_x' })
    handle.stop()
  })

  it('relay_call 分发本地执行器并回执 payload；未知工具回执结构化失败', async () => {
    const executor = vi.fn(async () => ({ ok: true, data: { done: 1 } }))
    const handle = startBridgeClient({
      host: 'editor',
      getTargetId: () => 'proj_1',
      executors: { editor_apply_ops: executor },
    })
    await Promise.resolve()
    const ws = FakeWebSocket.instances[0]
    ws.onopen?.()
    ws.serverSend({ type: 'relay_call', call_id: 'c1', tool: 'editor_apply_ops', args: { ops: [] } })
    await vi.waitFor(() => {
      const result = ws.sent.map((s) => JSON.parse(s)).find((m) => m.type === 'relay_result')
      expect(result).toEqual({ type: 'relay_result', call_id: 'c1', payload: { ok: true, data: { done: 1 } } })
    })
    expect(executor).toHaveBeenCalledWith({ ops: [] })

    ws.serverSend({ type: 'relay_call', call_id: 'c2', tool: 'agent_delegate', args: {} })
    await vi.waitFor(() => {
      const result = ws.sent.map((s) => JSON.parse(s)).find((m) => m.call_id === 'c2')
      expect(result?.payload.ok).toBe(false)
    })
    handle.stop()
  })

  it('异常断开后指数退避重连', async () => {
    vi.useFakeTimers()
    const handle = startBridgeClient({ host: 'canvas', getTargetId: () => 'ws_x', executors: {} })
    expect(FakeWebSocket.instances).toHaveLength(1)
    FakeWebSocket.instances[0].onclose?.()
    await vi.advanceTimersByTimeAsync(1000)
    expect(FakeWebSocket.instances).toHaveLength(2)
    FakeWebSocket.instances[1].onclose?.()
    await vi.advanceTimersByTimeAsync(2000)
    expect(FakeWebSocket.instances).toHaveLength(3)
    handle.stop()
    vi.useRealTimers()
  })
})

describe('桥白名单一致性', () => {
  it('BRIDGE_CANVAS_TOOLS 全部是 canvasHostTools 输出且不在 CHAT_TOOLS 内', () => {
    const hostNames = canvasHostTools().map((t) => t.name)
    for (const name of BRIDGE_CANVAS_TOOLS) {
      expect(hostNames).toContain(name)
      expect(CHAT_TOOL_NAMES).not.toContain(name)
      expect(AGENT_TOOLS.some((t) => t.name === name)).toBe(true)
    }
    expect(hostNames).not.toContain('agent_delegate')
  })

  it('BRIDGE_EDITOR_TOOLS 全部存在于 EDITOR_TOOLS', () => {
    for (const name of BRIDGE_EDITOR_TOOLS) {
      expect(EDITOR_TOOLS.some((t) => t.name === name)).toBe(true)
    }
  })
})

describe('canvasHostTools 深度工具三分派', () => {
  const getStateTool = canvasHostTools().find((t) => t.name === 'agent_get_state')!

  it('local → 直执行页内 store', async () => {
    const r = await getStateTool.execute({}, { resolveCanvasExecution: () => ({ mode: 'local' }) })
    expect(r.ok).toBe(true)
    expect((r.data as { workspace_id?: string }).workspace_id).toBe('ws_local')
  })

  it('bridge → 中继并透传页面回执', async () => {
    postMock.mockResolvedValueOnce({ routed: 'relay', result: { ok: true, data: { via: 'bridge' } } })
    const r = await getStateTool.execute({}, { resolveCanvasExecution: () => ({ mode: 'bridge', targetId: 'ws_remote' }) })
    expect(r.ok).toBe(true)
    expect((r.data as { via?: string }).via).toBe('bridge')
    expect(postMock).toHaveBeenCalledWith(
      '/api/agent/relay/call',
      { host: 'canvas', target_id: 'ws_remote', tool: 'agent_get_state', args: {} },
      { timeout: 0 },
    )
  })

  it('none → 不可达结构化报错（不触中继）', async () => {
    const r = await getStateTool.execute({}, { resolveCanvasExecution: () => ({ mode: 'none' }) })
    expect(r.ok).toBe(false)
    expect(r.error).toContain('画布页未打开')
    expect(postMock).not.toHaveBeenCalled()
  })
})
