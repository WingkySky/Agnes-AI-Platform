/* AgentKernel 直测：假 LLM 流 + 内存画布 store（不经过 Pinia） */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { AgentKernel, rebuildTimeline } from '../kernel'
import type { AgentKernelDeps, KernelEvent } from '../kernel'
import { AGENT_SYSTEM_PROMPT_BASE } from '../system-prompt'
import { createFakeStreamFn } from './fake-llm'
import type { FakeTurn } from './fake-llm'
import type { AgentMode } from '../policy'

const mocks = {
  panels: [] as Array<{ id: string; type?: string; content: Record<string, unknown> }>,
}

/** 内存版画布 store：按 canvas store 真实语义实现工具层所需成员 */
function makeCanvas() {
  return {
    activeWorkspaceId: 'ws-test',
    panels: mocks.panels as never[],
    connections: [] as never[],
    selectedPanelIds: [] as string[],
    lastConnectionError: null,
    activeStyleConfig: { prefix: '', suffix: '', negativePrompt: '' },
    setWorkspaceStyleConfig: () => {},
    addPanel(input: { type?: string; content?: Record<string, unknown> }) {
      const pid = `np${mocks.panels.length + 1}`
      mocks.panels.push({ id: pid, type: input.type, content: input.content || {} })
      return pid
    },
    updatePanel: () => {},
    deletePanel: () => {},
    addConnection: () => ({ id: 'c1', source_panel_id: 'a', target_panel_id: 'b', type: 'manual', created_at: '' }),
    deleteConnection: () => {},
    selectPanel: () => {},
    pushSnapshot: () => {},
  }
}

function makeKernel(script: FakeTurn[], mode: AgentMode) {
  const fake = createFakeStreamFn(script)
  const events: KernelEvent[] = []
  const modeRef = { current: mode }
  const deps: AgentKernelDeps = {
    getCanvas: makeCanvas,
    getMode: () => modeRef.current,
    systemPrompt: AGENT_SYSTEM_PROMPT_BASE,
    getAuthToken: async () => 'test-token',
    streamFn: fake.streamFn,
  }
  const kernel = new AgentKernel(deps)
  kernel.subscribe((e) => events.push(e))
  return { kernel, events, calls: fake.calls, modeRef }
}

beforeEach(() => {
  mocks.panels.length = 0
})

describe('AgentKernel：工具循环', () => {
  it('自动档：执行工具并回填结果，下一轮上下文含 toolResult', async () => {
    const { kernel, events, calls } = makeKernel(
      [
        { toolCalls: [{ id: 't1', name: 'agent_create_text_node', args: { text: '开场' } }] },
        { text: '已创建完成' },
      ],
      'auto',
    )
    await kernel.send('帮我建节点')

    expect(calls.length).toBe(2)
    expect(mocks.panels.some((p) => p.content.content === '开场')).toBe(true)
    const toolResult = calls[1].messages.find((m) => (m as { role?: string }).role === 'toolResult') as
      | { toolCallId: string; content: Array<{ text: string }> }
      | undefined
    expect(toolResult?.toolCallId).toBe('t1')
    expect(toolResult?.content[0].text).toContain('panel_id')

    expect(events.some((e) => e.type === 'tool_start' && e.tool === 'agent_create_text_node')).toBe(true)
    const end = events.find((e) => e.type === 'tool_end')
    expect(end && end.ok).toBe(true)
    const done = events.find((e) => e.type === 'done')
    expect(done && !done.stopped && done.error === null).toBe(true)
  })

  it('确认档：阶段汇报转审阅挂起，放行后机械给出下一阶段指引', async () => {
    const { kernel, events, calls } = makeKernel(
      [
        { toolCalls: [{ id: 't1', name: 'agent_stage_review', args: { stage: '剧本', summary: '已生成剧本节点' } }] },
        { text: '继续' },
      ],
      'confirm',
    )
    const sendPromise = kernel.send('继续')
    await new Promise((r) => setTimeout(r, 0))
    const confirmReq = events.find((e) => e.type === 'confirm_request')
    expect(confirmReq && confirmReq.kind === 'stage' && confirmReq.stage === '剧本').toBe(true)

    kernel.confirm(true)
    await sendPromise
    expect(calls.length).toBe(2)
    const end = events.find((e) => e.type === 'tool_end')
    expect(end && end.ok && end.result).toContain('下一阶段：实体设定')
  })

  it('确认档：阶段汇报被暂停则终止回合，不再发起 LLM 调用', async () => {
    const { kernel, events, calls } = makeKernel(
      [{ toolCalls: [{ id: 't1', name: 'agent_stage_review', args: { stage: '剧本', summary: '初稿' } }] }],
      'confirm',
    )
    const sendPromise = kernel.send('写剧本')
    await new Promise((r) => setTimeout(r, 0))
    kernel.confirm(false)
    await sendPromise

    expect(calls.length).toBe(1)
    const rejected = events.find((e) => e.type === 'tool_rejected')
    expect(rejected?.reason).toContain('暂停')
    const done = events.find((e) => e.type === 'done')
    expect(done?.stopped).toBe(true)
  })

  it('确认档：生成阶段首次强制过门，同回合放行后不重复拦', async () => {
    const { kernel, events, calls } = makeKernel(
      [
        { toolCalls: [{ id: 't1', name: 'agent_run_generation', args: { panel_id: 'p1', kind: 'image' } }] },
        { toolCalls: [{ id: 't2', name: 'agent_run_generation', args: { panel_id: 'p1', kind: 'image' } }] },
        { text: 'ok' },
      ],
      'confirm',
    )
    const sendPromise = kernel.send('生成分镜图')
    await new Promise((r) => setTimeout(r, 0))
    expect(events.filter((e) => e.type === 'confirm_request').length).toBe(1)
    const firstConfirm = events.find((e) => e.type === 'confirm_request')
    expect(firstConfirm && firstConfirm.stage === '分镜图').toBe(true)

    kernel.confirm(true)
    await sendPromise
    // 两轮 run_generation 都执行了（节点不存在报错），但只拦一次
    expect(calls.length).toBe(3)
    const errors = events.filter((e) => e.type === 'tool_end' && !e.ok)
    expect(errors.length).toBe(2)
  })

  it('确认档：拒绝生成阶段则流程停止', async () => {
    const { kernel, events, calls } = makeKernel(
      [{ toolCalls: [{ id: 't1', name: 'agent_run_generation', args: { panel_id: 'p1', kind: 'video' } }] }],
      'confirm',
    )
    const sendPromise = kernel.send('生成视频')
    await new Promise((r) => setTimeout(r, 0))
    const confirmReq = events.find((e) => e.type === 'confirm_request')
    expect(confirmReq && confirmReq.stage === '分段视频').toBe(true)
    kernel.confirm(false)
    await sendPromise
    expect(calls.length).toBe(1)
    const done = events.find((e) => e.type === 'done')
    expect(done?.stopped).toBe(true)
  })

  it('运行时切到只读档：已注册的写工具由策略层拦截且回合继续', async () => {
    const { kernel, events, calls, modeRef } = makeKernel(
      [
        { toolCalls: [{ id: 't1', name: 'agent_create_text_node', args: { text: 'A' } }] },
        { text: '只读模式无法执行' },
      ],
      'confirm',
    )
    modeRef.current = 'readonly'
    await kernel.send('建节点')
    expect(events.some((e) => e.type === 'confirm_request')).toBe(false)
    const rejected = events.find((e) => e.type === 'tool_rejected')
    expect(rejected?.reason).toContain('只读')
    expect(mocks.panels.length).toBe(0)
    expect(calls.length).toBe(2)
  })

  it('自动档：阶段汇报直通不弹确认，工具兜底执行返回指引', async () => {
    const { kernel, events, calls } = makeKernel(
      [
        { toolCalls: [{ id: 't1', name: 'agent_stage_review', args: { stage: '剧本', summary: '初稿' } }] },
        { text: '继续' },
      ],
      'auto',
    )
    await kernel.send('全自动')
    expect(events.some((e) => e.type === 'confirm_request')).toBe(false)
    const end = events.find((e) => e.type === 'tool_end')
    expect(end && end.ok && end.result).toContain('下一阶段')
    expect(calls.length).toBe(2)
  })

  it('达到回合上限时中止并报错（第 41 轮 turn_start 触发 abort，该轮工具被跳过）', async () => {
    const script: FakeTurn[] = []
    for (let i = 0; i < 41; i++) {
      script.push({ toolCalls: [{ id: `t${i}`, name: 'agent_get_state', args: {} }] })
    }
    const { kernel, events, calls } = makeKernel(script, 'auto')
    await kernel.send('循环测试')
    const done = events.find((e) => e.type === 'done')
    expect(done?.error).toContain('上限')
    expect(calls.length).toBe(41)
  })

  it('serializeState/restore 往返：消息完整、时间线可重建', async () => {
    const { kernel } = makeKernel(
      [
        { toolCalls: [{ id: 't1', name: 'agent_create_text_node', args: { text: '开场' } }] },
        { text: '完成' },
      ],
      'auto',
    )
    await kernel.send('建节点')

    const data = kernel.serializeState()
    const restored = new AgentKernel({
      getCanvas: makeCanvas,
      getMode: () => 'confirm',
      systemPrompt: AGENT_SYSTEM_PROMPT_BASE,
      getAuthToken: async () => null,
      streamFn: createFakeStreamFn([]).streamFn,
    })
    expect(restored.restore(data)).toBe(true)
    expect(restored.serializeState()).toEqual(data)
  })

  it('restore 损坏数据返回 false', () => {
    const kernel = new AgentKernel({
      getCanvas: makeCanvas,
      getMode: () => 'confirm',
      systemPrompt: AGENT_SYSTEM_PROMPT_BASE,
      getAuthToken: async () => null,
      streamFn: createFakeStreamFn([]).streamFn,
    })
    expect(kernel.restore({ messages: 'bad' })).toBe(false)
    expect(kernel.restore(null)).toBe(false)
  })
})

describe('rebuildTimeline：内核消息 → UI 时间线', () => {
  it('从序列化状态重建消息与步骤状态', async () => {
    const { kernel } = makeKernel(
      [
        { toolCalls: [{ id: 't1', name: 'agent_create_text_node', args: { text: '开场' } }] },
        { text: '完成' },
      ],
      'auto',
    )
    await kernel.send('建节点')
    const timeline = kernel.serializeState()
    const ui = rebuildTimeline(timeline)
    expect(ui).not.toBeNull()
    // user / assistant(toolCall 折叠为步骤) / assistant(最终回复)
    expect(ui!.length).toBe(3)
    expect(ui![0].role).toBe('user')
    expect(ui![1].steps[0].tool).toBe('agent_create_text_node')
    expect(ui![1].steps[0].status).toBe('done')
    expect(ui![2].content).toBe('完成')
  })

  it('损坏输入返回 null', () => {
    expect(rebuildTimeline(null)).toBeNull()
    expect(rebuildTimeline({})).toBeNull()
    expect(rebuildTimeline({ messages: 42 })).toBeNull()
  })
})

describe('AgentKernel：多模态输入', () => {
  class FakeFileReader {
    result: string | null = null
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    readAsDataURL(): void {
      this.result = 'data:image/png;base64,QUJD'
      this.onload?.()
    }
    readAsText(): void {
      this.onload?.()
    }
  }

  it('send 带 images：LLM 首条用户消息含 image 块', async () => {
    const { kernel, calls } = makeKernel([{ text: '这是海报' }], 'auto')
    await kernel.send('这是什么', [{ data: 'QUJD', mimeType: 'image/png' }])
    expect(calls.length).toBe(1)
    const userMsg = calls[0].messages[0] as { role: string; content: Array<{ type: string; text?: string; data?: string; mimeType?: string }> }
    expect(userMsg.role).toBe('user')
    expect(userMsg.content.some((b) => b.type === 'text' && b.text === '这是什么')).toBe(true)
    expect(userMsg.content.some((b) => b.type === 'image' && b.data === 'QUJD' && b.mimeType === 'image/png')).toBe(true)
  })

  it('无效图片附件被守卫剔除，退化为纯文本消息', async () => {
    const { kernel, calls } = makeKernel([{ text: '收到' }], 'auto')
    await kernel.send('看图', [
      { data: '', mimeType: 'image/png' },
      { data: 'QUJD', mimeType: 'application/octet-stream' },
    ])
    const userMsg = calls[0].messages[0] as { role: string; content: Array<{ type: string }> }
    expect(userMsg.content.every((b) => b.type === 'text')).toBe(true)
  })

  it('agent_read_image 工具结果带图：toolResult 含 image 块', async () => {
    vi.stubGlobal('FileReader', FakeFileReader)
    vi.stubGlobal('fetch', vi.fn(async () => new Response(new Blob(['abc'], { type: 'image/png' }), { status: 200, headers: { 'content-type': 'image/png' } })))
    try {
      mocks.panels.push({ id: 'p1', type: 'image', content: { status: 'success', content: 'https://cdn.example.com/a.png' } })
      const { kernel, calls } = makeKernel(
        [
          { toolCalls: [{ id: 't1', name: 'agent_read_image', args: { panel_id: 'p1' } }] },
          { text: '图里是一张海报' },
        ],
        'auto',
      )
      await kernel.send('看看这张图')
      const toolResult = calls[1].messages.find((m) => (m as { role?: string }).role === 'toolResult') as
        | { toolCallId: string; content: Array<{ type: string; data?: string; mimeType?: string }> }
        | undefined
      expect(toolResult?.toolCallId).toBe('t1')
      expect(toolResult?.content.some((b) => b.type === 'image' && b.data === 'QUJD' && b.mimeType === 'image/png')).toBe(true)
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('rebuildTimeline：还原用户消息里的 image 块，纯文本用户消息无 images', () => {
    const tl = rebuildTimeline({
      messages: [
        { role: 'user', content: [{ type: 'text', text: '看' }, { type: 'image', data: 'QQ==', mimeType: 'image/jpeg' }], timestamp: Date.now() },
        { role: 'user', content: '纯文本', timestamp: Date.now() },
      ],
    })
    expect(tl).not.toBeNull()
    expect(tl![0].images).toEqual([{ data: 'QQ==', mimeType: 'image/jpeg' }])
    expect(tl![1].images).toBeUndefined()
  })
})
