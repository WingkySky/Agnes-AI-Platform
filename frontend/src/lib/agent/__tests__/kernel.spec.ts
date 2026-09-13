/* AgentKernel 直测：假 LLM 流 + 内存画布 store（不经过 Pinia） */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { Type } from 'typebox'
import { AgentKernel, rebuildTimeline } from '../kernel'
import type { AgentKernelDeps, KernelEvent } from '../kernel'
import { AGENT_SYSTEM_PROMPT_BASE } from '../system-prompt'
import { setActiveSkillScope } from '../skills'
import { setLocale } from '@/i18n'

// 阶段门 stage 断言依赖中文文案，固定测试语言
setLocale('zh-CN')
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

  it('恢复坏形状上下文后续发不炸（历史落库：字符串内容 + 缺 stopReason/usage）', async () => {
    const { kernel, events } = makeKernel([{ text: '续上了' }], 'auto')
    const brokenContext = {
      messages: [
        { role: 'user', content: '第一问', timestamp: Date.now() - 1000 },
        { role: 'assistant', content: '第一答', timestamp: Date.now() },
      ],
    }
    expect(kernel.restore(brokenContext)).toBe(true)
    // 修复前：下一回合上下文估算读 usage.totalTokens 对 undefined 抛 TypeError，send 直接失败
    await kernel.send('继续')
    const doneEvent = events.find((e) => e.type === 'done')
    expect(doneEvent && 'error' in doneEvent && doneEvent.error).toBeNull()
    const data = kernel.serializeState() as {
      messages: Array<{ role: string; content: unknown; stopReason?: string; usage?: { totalTokens: number } }>
    }
    const assistants = data.messages.filter((m) => m.role === 'assistant')
    expect(assistants.length).toBeGreaterThanOrEqual(2)
    for (const a of assistants) {
      expect(Array.isArray(a.content)).toBe(true)
      expect(a.stopReason).toBeDefined()
      expect(a.usage).toBeDefined()
    }
  })
})

describe('AgentKernel：技能工具围栏', () => {
  it('allowed_tools 白名单外的工具被拒绝（画布宿主），回合继续收尾', async () => {
    setActiveSkillScope(['agent_get_state'])
    try {
      const { kernel, events, calls } = makeKernel(
        [
          { toolCalls: [{ id: 't1', name: 'agent_create_text_node', args: { text: '越权' } }] },
          { text: '被围栏拦下' },
        ],
        'auto',
      )
      await kernel.send('越权建节点')
      const rejected = events.find((e) => e.type === 'tool_rejected')
      expect(rejected?.reason).toContain('白名单')
      expect(mocks.panels.length).toBe(0)
      expect(calls.length).toBe(2)
    } finally {
      setActiveSkillScope([])
    }
  })

  it('白名单内的工具正常执行；清空围栏后恢复不限制', async () => {
    setActiveSkillScope(['agent_create_text_node'])
    try {
      const { kernel, events } = makeKernel(
        [
          { toolCalls: [{ id: 't1', name: 'agent_create_text_node', args: { text: '圈内' } }] },
          { text: '完成' },
        ],
        'auto',
      )
      await kernel.send('建节点')
      expect(events.some((e) => e.type === 'tool_rejected')).toBe(false)
      expect(mocks.panels.some((p) => p.content.content === '圈内')).toBe(true)
    } finally {
      setActiveSkillScope([])
    }
  })
})

describe('AgentKernel：子代理门扩展', () => {
  it('门请求 FIFO：confirm 按入队顺序逐个唤醒，放行后同阶段不再重复拦', async () => {
    const { kernel, events } = makeKernel([], 'confirm')
    const p1 = kernel.authorizeTool('agent_run_generation', { panel_id: 'p1', kind: 'image' })
    const p2 = kernel.authorizeTool('agent_run_generation', { panel_id: 'p2', kind: 'image' })
    await new Promise((r) => setTimeout(r, 0))
    // 门未决阶段不共享门状态，两个请求都弹卡入队
    expect(events.filter((e) => e.type === 'confirm_request').length).toBe(2)

    kernel.confirm(true)
    expect((await p1).allowed).toBe(true)
    // FIFO：第一个确认后第二个仍在队中等待，不会被误唤醒
    const secondSettled = await Promise.race([p2.then(() => true), new Promise((r) => setTimeout(() => r(false), 10))])
    expect(secondSettled).toBe(false)

    kernel.confirm(true)
    expect((await p2).allowed).toBe(true)
    // 门状态父回合共享：同 kind 已过门，第三个同阶段请求直通
    const p3 = await kernel.authorizeTool('agent_run_generation', { panel_id: 'p3', kind: 'image' })
    expect(p3.allowed).toBe(true)
    expect(events.filter((e) => e.type === 'confirm_request').length).toBe(2)
  })

  it('子代理门请求带 source 标签透传到确认卡事件', async () => {
    const { kernel, events } = makeKernel([], 'confirm')
    const gate = kernel.authorizeTool('agent_run_generation', { panel_id: 'p1', kind: 'image' }, '子任务:分镜1')
    await new Promise((r) => setTimeout(r, 0))
    const req = events.find((e) => e.type === 'confirm_request')
    expect(req && 'source' in req && req.source === '子任务:分镜1').toBe(true)
    kernel.confirm(true)
    expect((await gate).allowed).toBe(true)
  })

  it('requestStop：挂起门按拒绝放行（stop 语义），注册的子代理内核一并中止', async () => {
    const { kernel } = makeKernel([], 'confirm')
    const gate = kernel.authorizeTool('agent_run_generation', { panel_id: 'p1', kind: 'image' }, '子任务:分镜1')
    await new Promise((r) => setTimeout(r, 0))

    const child = new AgentKernel({
      systemPrompt: '子代理',
      getAuthToken: async () => null,
      streamFn: createFakeStreamFn([]).streamFn,
    })
    const childStopSpy = vi.spyOn(child, 'requestStop')
    const unregister = kernel.registerChild(child)

    kernel.requestStop()
    expect(childStopSpy).toHaveBeenCalledTimes(1)
    const decision = await gate
    expect(decision.allowed).toBe(false)
    expect(decision.stop).toBe(true)
    expect(decision.reason).toContain('停止')

    unregister()
    kernel.requestStop()
    expect(childStopSpy).toHaveBeenCalledTimes(1)
  })

  it('maxTurns 可配：上限 2 时第 3 轮触发中止并报错', async () => {
    const fake = createFakeStreamFn([
      { toolCalls: [{ id: 't1', name: 'agent_get_state', args: {} }] },
      { toolCalls: [{ id: 't2', name: 'agent_get_state', args: {} }] },
      { toolCalls: [{ id: 't3', name: 'agent_get_state', args: {} }] },
    ])
    const kernel = new AgentKernel({
      getCanvas: makeCanvas,
      getMode: () => 'auto',
      systemPrompt: AGENT_SYSTEM_PROMPT_BASE,
      getAuthToken: async () => 'test-token',
      streamFn: fake.streamFn,
      maxTurns: 2,
    })
    const events: KernelEvent[] = []
    kernel.subscribe((e) => events.push(e))
    await kernel.send('子任务循环')
    const done = events.find((e) => e.type === 'done')
    expect(done?.error).toContain('上限（2 轮）')
    expect(fake.calls.length).toBe(3)
  })

  it('宿主工具 execute 收到机制层 callId（子代理进度定位用）', async () => {
    const seen: string[] = []
    const kernel = new AgentKernel({
      systemPrompt: AGENT_SYSTEM_PROMPT_BASE,
      getAuthToken: async () => null,
      streamFn: createFakeStreamFn([
        { toolCalls: [{ id: 'host-1', name: 'probe', args: {} }] },
        { text: 'ok' },
      ]).streamFn,
      tools: [
        {
          name: 'probe',
          description: '探针',
          parameters: Type.Object({}),
          execute: async (_args, _ctx, callId) => {
            seen.push(callId ?? '')
            return { ok: true, data: {} }
          },
        },
      ],
    })
    await kernel.send('探针调用')
    expect(seen).toEqual(['host-1'])
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
