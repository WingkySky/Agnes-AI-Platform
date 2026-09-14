/* MCP 工具转译直测：命名约定 / schema 透传 / 失败降级 / 内核注入与门 */

import { describe, it, expect, vi } from 'vitest'
import { buildMcpTools, mcpToolName, MCP_TOOL_PREFIX } from '../mcp'
import type { McpServerTools } from '@/api/mcp'
import { AgentKernel } from '../kernel'
import type { KernelEvent } from '../kernel'
import { AGENT_SYSTEM_PROMPT_BASE } from '../system-prompt'
import { createFakeStreamFn } from './fake-llm'
import type { AgentCanvasStore } from '../tools'

vi.mock('@/api/mcp', () => ({
  callMcpTool: vi.fn(async (serverId: number, tool: string, args?: Record<string, unknown>) => {
    return { text: `called ${serverId}.${tool} ${JSON.stringify(args ?? {})}`, is_error: false }
  }),
  fetchMcpAgentTools: vi.fn(async () => mockedAgentTools),
}))

let mockedAgentTools: McpServerTools[] = []

function makeCanvas(): AgentCanvasStore {
  return {
    panels: [] as never[],
    connections: [] as never[],
    selectedPanelIds: [],
    activeWorkspaceId: 'ws',
    lastConnectionError: null,
    activeStyleConfig: { prefix: '', suffix: '', negativePrompt: '' },
    setWorkspaceStyleConfig: () => {},
    addPanel: () => 'p1',
    updatePanel: () => {},
    deletePanel: () => {},
    addConnection: () => null,
    deleteConnection: () => {},
    selectPanel: () => {},
    pushSnapshot: () => {},
  }
}

describe('mcp 工具转译', () => {
  it('命名约定 mcp__{serverId}__{tool}', () => {
    expect(mcpToolName(3, 'read_file')).toBe('mcp__3__read_file')
    expect(MCP_TOOL_PREFIX).toBe('mcp__')
  })

  it('buildMcpTools：schema 透传 + description 前缀服务器名 + execute 走 BFF', async () => {
    mockedAgentTools = [
      {
        server_id: 3,
        server_name: '文件系统',
        tools: [{ name: 'read_file', description: '读取文件', input_schema: { type: 'object', properties: { path: { type: 'string' } } } }],
      },
    ]
    const tools = await buildMcpTools()
    expect(tools.length).toBe(1)
    expect(tools[0].name).toBe('mcp__3__read_file')
    expect(tools[0].description).toContain('文件系统')
    expect(tools[0].description).toContain('读取文件')
    // schema 原样透传（parameters 序列化后含 properties.path）
    expect(JSON.stringify(tools[0].parameters)).toContain('"path"')
    // execute → BFF 结果回填
    const r = await tools[0].execute({ path: '/tmp/a' }, null)
    expect(r.ok).toBe(true)
    expect(JSON.stringify(r.data)).toContain('called 3.read_file')
  })

  it('buildMcpTools：接口失败降级为空数组', async () => {
    const { fetchMcpAgentTools } = await import('@/api/mcp')
    vi.mocked(fetchMcpAgentTools).mockRejectedValueOnce(new Error('网络错误'))
    expect(await buildMcpTools()).toEqual([])
  })

  it('schema 剥 format：中文 URL 不被内核 format:uri 拒绝（2026-09-13 fetch 失败回归）', async () => {
    mockedAgentTools = [
      {
        server_id: 3,
        server_name: '网页抓取',
        tools: [
          { name: 'fetch', description: '抓取网页', input_schema: { type: 'object', properties: { url: { type: 'string', format: 'uri', description: 'URL' } }, required: ['url'] } },
        ],
      },
    ]
    const tools = await buildMcpTools()
    expect(JSON.stringify(tools[0].parameters)).not.toContain('"format"')
    const fake = createFakeStreamFn([
      { toolCalls: [{ id: 't1', name: 'mcp__3__fetch', args: { url: 'https://zh.wikipedia.org/wiki/三英战吕布' } }] },
      { text: 'ok' },
    ])
    const events: KernelEvent[] = []
    const kernel = new AgentKernel({
      getCanvas: () => makeCanvas(),
      getMode: () => 'auto',
      systemPrompt: AGENT_SYSTEM_PROMPT_BASE,
      getAuthToken: async () => 't',
      streamFn: fake.streamFn,
      extraTools: tools,
    })
    kernel.subscribe((e) => events.push(e))
    await kernel.send('查资料')
    const end = events.find((e) => e.type === 'tool_end')
    expect(end && 'ok' in end && end.ok).toBe(true)
  })
})

describe('内核 MCP 工具注入与门', () => {
  it('extraTools 注入后可执行；confirm 档每工具首次过门（kind=tool），同回合不重复拦', async () => {
    mockedAgentTools = [
      { server_id: 5, server_name: 'S', tools: [{ name: 'ping', description: 'd', input_schema: { type: 'object' } }] },
    ]
    const tools = await buildMcpTools()
    const fake = createFakeStreamFn([
      { toolCalls: [{ id: 't1', name: 'mcp__5__ping', args: {} }] },
      { toolCalls: [{ id: 't2', name: 'mcp__5__ping', args: {} }] },
      { text: 'ok' },
    ])
    const events: KernelEvent[] = []
    const kernel = new AgentKernel({
      getCanvas: () => makeCanvas(),
      getMode: () => 'confirm',
      systemPrompt: AGENT_SYSTEM_PROMPT_BASE,
      getAuthToken: async () => 't',
      streamFn: fake.streamFn,
      extraTools: tools,
    })
    kernel.subscribe((e) => events.push(e))
    const sendPromise = kernel.send('调 MCP 工具')
    await new Promise((r) => setTimeout(r, 0))
    const req = events.find((e) => e.type === 'confirm_request')
    expect(req && 'kind' in req && req.kind === 'tool').toBe(true)
    kernel.confirm(true)
    await sendPromise
    // 第二次同工具调用不再过门（只弹一次）
    expect(events.filter((e) => e.type === 'confirm_request').length).toBe(1)
    const end = events.find((e) => e.type === 'tool_end')
    expect(end && 'ok' in end && end.ok).toBe(true)
  })

  it('readonly 档：mcp 工具已注册但仍被策略拒绝（明确只读提示而非未知工具）', async () => {
    mockedAgentTools = [
      { server_id: 5, server_name: 'S', tools: [{ name: 'ping', description: 'd', input_schema: { type: 'object' } }] },
    ]
    const tools = await buildMcpTools()
    const modeRef = { current: 'confirm' as 'confirm' | 'readonly' }
    const fake = createFakeStreamFn([
      { toolCalls: [{ id: 't1', name: 'mcp__5__ping', args: {} }] },
      { text: '只读模式无法调用' },
    ])
    const events: KernelEvent[] = []
    const kernel = new AgentKernel({
      getCanvas: () => makeCanvas(),
      getMode: () => modeRef.current,
      systemPrompt: AGENT_SYSTEM_PROMPT_BASE,
      getAuthToken: async () => 't',
      streamFn: fake.streamFn,
      extraTools: tools,
    })
    kernel.subscribe((e) => events.push(e))
    modeRef.current = 'readonly'
    await kernel.send('调 MCP 工具')
    const rejected = events.find((e) => e.type === 'tool_rejected')
    expect(rejected && 'reason' in rejected && rejected.reason?.includes('只读')).toBe(true)
  })

  it('setExtraTools：非流式更新后工具可执行', async () => {
    const fake = createFakeStreamFn([
      { toolCalls: [{ id: 't1', name: 'mcp__1__a', args: {} }] },
      { text: 'ok' },
    ])
    const events: KernelEvent[] = []
    const kernel = new AgentKernel({
      getCanvas: () => makeCanvas(),
      getMode: () => 'auto',
      systemPrompt: AGENT_SYSTEM_PROMPT_BASE,
      getAuthToken: async () => 't',
      streamFn: fake.streamFn,
    })
    kernel.subscribe((e) => events.push(e))
    kernel.setExtraTools([
      { name: 'mcp__1__a', description: 'd', parameters: { type: 'object' }, execute: async () => ({ ok: true, data: { v: 1 } }) },
    ])
    await kernel.send('hi')
    const end = events.find((e) => e.type === 'tool_end')
    expect(end && 'ok' in end && end.ok).toBe(true)
  })
})
