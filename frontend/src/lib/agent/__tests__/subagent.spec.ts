/* agent_delegate 子代理直测：父内核真装配 + 假 LLM 流共享剧本（父/子按调用顺序消费） */

import { describe, it, expect, vi } from 'vitest'
import { AgentKernel } from '../kernel'
import { AGENT_SYSTEM_PROMPT_BASE } from '../system-prompt'
import { createFakeStreamFn } from './fake-llm'
import type { FakeTurn } from './fake-llm'
import { runSubagent, subagentHostFromParent } from '../subagent'
import { AGENT_TOOLS, AGENT_TOOL_NAMES } from '../tools'
import type { AgentCanvasStore } from '../tools'
import { CHAT_TOOLS, CHAT_TOOL_NAMES } from '../chat-tools'
import type { AgentMode } from '../policy'

/** 内存版画布 store（对齐 kernel.spec 的结构化兼容写法） */
function makeCanvas(): AgentCanvasStore {
  const panels: Array<{ id: string; type?: string; content: Record<string, unknown> }> = []
  return {
    panels: panels as never[],
    connections: [] as never[],
    selectedPanelIds: [],
    activeWorkspaceId: 'ws-test',
    lastConnectionError: null,
    activeStyleConfig: { prefix: '', suffix: '', negativePrompt: '' },
    setWorkspaceStyleConfig: () => {},
    addPanel(input) {
      const pid = `np${panels.length + 1}`
      panels.push({ id: pid, type: input.type, content: input.content || {} })
      return pid
    },
    updatePanel: () => {},
    deletePanel: () => {},
    addConnection: () => null,
    deleteConnection: () => {},
    selectPanel: () => {},
    pushSnapshot: () => {},
  }
}

function makeParent(script: FakeTurn[], mode: AgentMode = 'confirm') {
  const fake = createFakeStreamFn(script)
  const canvas = makeCanvas()
  const modeRef = { current: mode }
  const kernel = new AgentKernel({
    getCanvas: () => canvas,
    getMode: () => modeRef.current,
    systemPrompt: AGENT_SYSTEM_PROMPT_BASE,
    getAuthToken: async () => 'test-token',
    streamFn: fake.streamFn,
  })
  return { kernel, fake, canvas, modeRef }
}

/** 记录父内核 authorizeTool 决策（不改变行为） */
function spyAuthorize(kernel: AgentKernel) {
  const calls: Array<{ tool: string; source?: string; allowed: boolean }> = []
  const orig = kernel.authorizeTool.bind(kernel)
  vi.spyOn(kernel, 'authorizeTool').mockImplementation(async (tool, args, source) => {
    const r = await orig(tool, args, source)
    calls.push({ tool, source, allowed: r.allowed })
    return r
  })
  return calls
}

/** 记录 createChildKernel 收到的子工具清单（不改变行为） */
function spyChildTools(kernel: AgentKernel) {
  const captured: string[][] = []
  const orig = kernel.createChildKernel.bind(kernel)
  vi.spyOn(kernel, 'createChildKernel').mockImplementation((input) => {
    captured.push(input.tools.map((t) => t.name))
    return orig(input)
  })
  return captured
}

function lastToolResultText(kernel: AgentKernel): string {
  const state = kernel.serializeState() as { messages: Array<{ role: string; content: unknown }> }
  const toolResults = state.messages.filter((m) => m.role === 'toolResult')
  const last = toolResults[toolResults.length - 1]
  if (!last || !Array.isArray(last.content)) return ''
  return last.content
    .filter((b): b is Record<string, unknown> => typeof b === 'object' && b !== null)
    .filter((b) => b.type === 'text' && typeof b.text === 'string')
    .map((b) => (typeof b.text === 'string' ? b.text : ''))
    .join('')
}

describe('agent_delegate：双宿主挂载', () => {
  it('画布工具组与对话工具组都注册 agent_delegate', () => {
    expect(AGENT_TOOLS.some((t) => t.name === 'agent_delegate' && t.group === 'write')).toBe(true)
    expect(AGENT_TOOL_NAMES).toContain('agent_delegate')
    expect(CHAT_TOOL_NAMES).toContain('agent_delegate')
  })

  it('chat 宿主 delegate 执行器：缺 parent 报错', async () => {
    const delegate = CHAT_TOOLS.find((t) => t.name === 'agent_delegate')
    expect(delegate).toBeDefined()
    const noParent = await delegate!.execute({ task: 'x' }, {}, 'c1', undefined)
    expect(noParent.ok).toBe(false)
    expect(noParent.error).toContain('父内核')
  })
})

describe('runSubagent：独立上下文与摘要回填', () => {
  it('基本委派：子内核跑完返回摘要，父上下文只收摘要；子内核用任务模板系统提示', async () => {
    const { kernel, fake } = makeParent(
      [
        { toolCalls: [{ id: 'd1', name: 'agent_delegate', args: { task: '评审这场戏的节奏' } }] },
        { text: '结论：节奏紧凑，第二拍偏慢' },
        { text: '已汇总子任务结论' },
      ],
      'auto',
    )
    await kernel.send('委派评审')

    expect(fake.calls.length).toBe(3)
    // 子内核系统提示 = 任务模板（含"子代理"），区别于父
    expect(fake.calls[1].systemPrompt).toContain('子代理')
    // delegate 工具结果回填摘要与子回合数
    const text = lastToolResultText(kernel)
    expect(text).toContain('节奏紧凑')
    expect(text).toContain('"turns":1')
  })

  it('门请求前移父内核：子工具调用带子任务来源标签', async () => {
    const { kernel } = makeParent([
      { toolCalls: [{ id: 'd1', name: 'agent_delegate', args: { task: '建节点' } }] },
      { toolCalls: [{ id: 'c1', name: 'agent_create_text_node', args: { text: '子任务节点' } }] },
      { text: '子任务完成' },
      { text: '父收尾' },
    ])
    const gates = spyAuthorize(kernel)
    await kernel.send('委派建节点')

    const hit = gates.find((g) => g.tool === 'agent_create_text_node')
    expect(hit).toBeDefined()
    expect(hit!.source).toBe('子任务:建节点')
    expect(hit!.allowed).toBe(true)
  })

  it('readonly 档：子代理内部写工具被父门拒绝，子任务把结果汇报回父', async () => {
    const { kernel, modeRef, canvas } = makeParent([
      { toolCalls: [{ id: 'd1', name: 'agent_delegate', args: { task: '尝试建节点' } }] },
      { toolCalls: [{ id: 'c1', name: 'agent_create_text_node', args: { text: 'X' } }] },
      { text: '只读模式下无法建节点' },
      { text: '父收尾' },
    ])
    modeRef.current = 'readonly'
    const gates = spyAuthorize(kernel)
    await kernel.send('委派建节点')

    const hit = gates.find((g) => g.tool === 'agent_create_text_node')
    expect(hit && hit.allowed).toBe(false)
    expect(canvas.panels.length).toBe(0)
  })

  it('禁递归与 tools_allowed 收窄：子工具清单剔除 delegate、按白名单收窄', async () => {
    const { kernel } = makeParent([
      { toolCalls: [{ id: 'd1', name: 'agent_delegate', args: { task: '查状态', tools_allowed: ['agent_get_state'] } }] },
      { text: '子任务完成' },
      { text: '父收尾' },
    ])
    const captured = spyChildTools(kernel)
    await kernel.send('委派查状态')
    expect(captured.length).toBe(1)
    expect(captured[0]).toEqual(['agent_get_state'])

    // 不传 tools_allowed：继承全组但无 delegate
    const { kernel: k2 } = makeParent([
      { toolCalls: [{ id: 'd1', name: 'agent_delegate', args: { task: '自由任务' } }] },
      { text: 'done' },
      { text: '父收尾' },
    ])
    const captured2 = spyChildTools(k2)
    await k2.send('委派自由任务')
    expect(captured2[0].includes('agent_delegate')).toBe(false)
    expect(captured2[0].length).toBeGreaterThan(1)
  })

  it('摘要超限截断', async () => {
    const { kernel } = makeParent([
      { toolCalls: [{ id: 'd1', name: 'agent_delegate', args: { task: '长输出任务' } }] },
      { text: 'x'.repeat(5000) },
      { text: '父收尾' },
    ])
    await kernel.send('委派长任务')
    const text = lastToolResultText(kernel)
    expect(text).toContain('超限截断')
    expect(text.length).toBeLessThan(4200)
  })
})

describe('runSubagent：入参守卫与并发信号量', () => {
  it('task 必填；tools_allowed 含 agent_delegate 拒绝（禁嵌套派生）', async () => {
    const { kernel } = makeParent([])
    const host = subagentHostFromParent(kernel, { tools: [] })
    const noTask = await runSubagent({ task: '   ' }, host)
    expect(noTask.ok).toBe(false)
    const nested = await runSubagent({ task: 'x', tools_allowed: ['agent_delegate'] }, host)
    expect(nested.ok).toBe(false)
    expect(nested.error).toContain('嵌套')
  })

  it('并发 4 个子任务：信号量排队后全部完成', async () => {
    const { kernel, fake } = makeParent([{ text: '结论一' }, { text: '结论二' }, { text: '结论三' }, { text: '结论四' }])
    const host = subagentHostFromParent(kernel, { tools: [] })
    const results = await Promise.all([1, 2, 3, 4].map((i) => runSubagent({ task: `并行任务${i}` }, host)))
    expect(results.every((r) => r.ok)).toBe(true)
    expect(fake.calls.length).toBe(4)
    const first = results[0].data as { summary: string; turns: number }
    expect(first.summary).toMatch(/结论/)
    expect(first.turns).toBe(1)
  })
})
