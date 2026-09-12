/* 画布 Agent 工具层单测：状态摘要、批量 ops、便捷工具、权限过滤 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('@/lib/canvas-generation', () => ({
  executeInNodeGeneration: vi.fn(async () => 'panel-1'),
  executeInNodeVideoGeneration: vi.fn(async () => 'panel-1'),
}))

vi.mock('@/api/canvas', () => ({
  composeCanvasVideos: vi.fn(async () => ({ video_url: 'https://example.com/final.mp4', duration_ms: 10000 })),
}))

vi.mock('@/stores/models', () => ({
  useModelsStore: () => ({
    models: [
      { id: 'agnes-video-2.5', name: 'Agnes Video 2.5', type: 'video', provider: 'Agnes', capabilities: ['text2video', 'image2video', 'video2video'], gen_params: { max_ref_images: 5 } },
      { id: 'agnes-image-2.1-flash', name: 'Agnes Image 2.1 Flash', type: 'image', provider: 'Agnes', capabilities: ['text2image', 'image2image'], gen_params: null },
    ],
    videoDurations: [3, 5, 7, 10, 15],
    defaultVideoDuration: 5,
    defaultVideoModel: 'agnes-video-2.5',
    defaultImageModel: 'agnes-image-2.1-flash',
    videoModels: [{ id: 'agnes-video-2.5', name: 'Agnes Video 2.5', type: 'video', provider: 'Agnes', capabilities: ['text2video', 'image2video', 'video2video'], gen_params: { max_ref_images: 5, video_durations: [5, 10] } }],
    imageModels: [{ id: 'agnes-image-2.1-flash', name: 'Agnes Image 2.1 Flash', type: 'image', provider: 'Agnes', capabilities: ['text2image', 'image2image'], gen_params: null }],
  }),
}))

vi.mock('@/lib/storyboard/pipeline', () => ({
  extractEntities: vi.fn(),
  splitStoryboard: vi.fn(),
}))

vi.mock('@/lib/agent/skills', () => ({
  getCachedSkill: vi.fn(),
  getCachedSkills: vi.fn(() => []),
}))

vi.mock('@/lib/storyboard/library', () => ({
  listCameraVocabulary: vi.fn(async () => ['缓推', '手持跟随']),
  listStyleEntries: vi.fn(async () => [{ id: 7, name: '日式动漫', description: '日系动漫画风', cover: 'https://i/cover.jpg', config: { prefix: '', suffix: '日式动漫风格', negativePrompt: '' } }]),
  resolveStyleConfig: vi.fn(async (id: number) => (id === 7 ? { prefix: '', suffix: '日式动漫风格', negativePrompt: '' } : null)),
}))

import { extractEntities, splitStoryboard } from '@/lib/storyboard/pipeline'
import { getCachedSkill, getCachedSkills } from '../skills'

import { AGENT_TOOLS, agentToolSchemasOpenAI, toolsForMode, findAgentTool } from '../tools'
import { resolveToolCall } from '../policy'
import type { AgentCanvasStore } from '../tools'
import type { CanvasPanel, CanvasConnection } from '@/stores/canvas'
import { executeInNodeGeneration, executeInNodeVideoGeneration } from '@/lib/canvas-generation'
import { composeCanvasVideos } from '@/api/canvas'

/** 内存版画布 store：按 canvas store 真实语义实现工具层所需成员 */
function makeCanvas(): AgentCanvasStore & { snapshots: number[] } {
  const panels: CanvasPanel[] = []
  const connections: CanvasConnection[] = []
  const selectedPanelIds: string[] = []
  let lastConnectionError: string | null = null
  let styleConfig: { prefix: string; suffix: string; negativePrompt: string } = { prefix: '胶片感', suffix: '', negativePrompt: '' }
  let seq = 0
  const id = () => `p${++seq}`
  const push = (type: string, content: Record<string, unknown>, x = 0, y = 0, name?: string): string => {
    const pid = id()
    panels.push({
      id: pid, type, name, content, x, y, width: 240, height: 180, zIndex: panels.length + 1,
      created_at: '', updated_at: '',
    })
    return pid
  }
  return {
    panels,
    connections,
    selectedPanelIds,
    activeWorkspaceId: 'ws1',
    get activeStyleConfig() { return styleConfig },
    setWorkspaceStyleConfig(sel) { styleConfig = sel?.config ?? { prefix: '', suffix: '', negativePrompt: '' } },
    get lastConnectionError() { return lastConnectionError },
    addPanel(input) {
      // 复刻真实行为：store.addPanel 只落节点，连线类型校验在 addConnection 内
      return push(input.type || 'text', input.content || {}, input.x, input.y, input.name)
    },
    updatePanel(pid, changes) {
      const p = panels.find((x) => x.id === pid)
      if (p) Object.assign(p, changes, { content: { ...p.content, ...(changes.content || {}) } })
    },
    deletePanel(pid) {
      for (let i = connections.length - 1; i >= 0; i--) {
        if (connections[i].source_panel_id === pid || connections[i].target_panel_id === pid) connections.splice(i, 1)
      }
      const idx = panels.findIndex((x) => x.id === pid)
      if (idx >= 0) panels.splice(idx, 1)
    },
    addConnection(conn) {
      const source = panels.find((p) => p.id === conn.source_panel_id)
      const target = panels.find((p) => p.id === conn.target_panel_id)
      // 复刻真实规则：tts/subtitle 只接受 text 入边
      const allowed: Record<string, string[]> = { tts: ['text'], subtitle: ['text'] }
      const targetAllows = allowed[target?.type || 'text']
      if (targetAllows && !targetAllows.includes(source?.type || 'text')) {
        lastConnectionError = '类型不允许连线'
        return null
      }
      const c: CanvasConnection = {
        id: `c${++seq}`, source_panel_id: conn.source_panel_id, target_panel_id: conn.target_panel_id,
        type: conn.type || 'manual', created_at: '',
      }
      connections.push(c)
      return c
    },
    deleteConnection(cid) {
      const idx = connections.findIndex((c) => c.id === cid)
      if (idx >= 0) connections.splice(idx, 1)
    },
    selectPanel(pid, opts) {
      if (pid === null) {
        selectedPanelIds.splice(0, selectedPanelIds.length)
        return
      }
      if (opts?.append) selectedPanelIds.push(pid)
      else selectedPanelIds.splice(0, selectedPanelIds.length, pid)
    },
    pushSnapshot() {
      this.snapshots.push(Date.now())
    },
    snapshots: [],
  }
}

function tool(name: string) {
  const t = findAgentTool(name)
  if (!t) throw new Error(`工具不存在: ${name}`)
  return t
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('agent_get_state', () => {
  it('返回节点/连线/选中摘要，超长内容被省略', () => {
    const canvas = makeCanvas()
    const pid = canvas.addPanel({ type: 'text', content: { text: '短文本' }, x: 10, y: 20, width: 240, height: 180 })
    canvas.addPanel({ type: 'text', content: { text: 'x'.repeat(400) }, x: 0, y: 0, width: 240, height: 180 })
    canvas.addConnection({ source_panel_id: pid, target_panel_id: canvas.panels[1].id })
    canvas.selectPanel(pid)

    const res = tool('agent_get_state').execute({}, canvas) as { ok: boolean; data: Record<string, unknown> }
    expect(res.ok).toBe(true)
    const data = res.data as Record<string, unknown>
    expect((data.panel_count as number)).toBe(2)
    expect((data.connections as unknown[]).length).toBe(1)
    expect((data.selected as string[])).toEqual([pid])
    const panels = data.panels as Record<string, unknown>[]
    expect(panels[0].content).toEqual({ text: '短文本' })
    expect(panels[1].content).toEqual({ text: '<400 字符，已省略>' })
  })
})

describe('agent_apply_ops', () => {
  it('批量建节点/连线并回填新 id；非法连线单条报错不中断', () => {
    const canvas = makeCanvas()
    const textId = canvas.addPanel({ type: 'text', content: { text: '提示词' }, x: 0, y: 0, width: 240, height: 180 })
    const res = tool('agent_apply_ops').execute({
      ops: [
        { op: 'add_panel', type: 'tts', content: {} },
        { op: 'add_connection', source_panel_id: textId, target_panel_id: '缺失' },
        { op: 'add_connection', source_panel_id: textId, target_panel_id: canvas.panels[canvas.panels.length - 1].id },
      ],
    }, canvas) as { ok: boolean; data: Record<string, unknown>; error?: string }

    const results = res.data.results as Record<string, unknown>[]
    expect(results[0].ok).toBe(true)
    expect(results[1].ok).toBe(false)
    expect(results[2].ok).toBe(true)
    expect(res.ok).toBe(false)
    expect(res.error).toContain('1 条操作失败')
    expect((res.data.new_panel_ids as string[]).length).toBe(1)
    expect(canvas.connections.length).toBe(1)
    expect(canvas.snapshots.length).toBe(1) // 整批一个撤销快照
  })

  it('delete_panel 同时清理相关连线', () => {
    const canvas = makeCanvas()
    const a = canvas.addPanel({ type: 'text', content: {}, x: 0, y: 0, width: 240, height: 180 })
    const b = canvas.addPanel({ type: 'text', content: {}, x: 0, y: 0, width: 240, height: 180 })
    const cid = canvas.addConnection({ source_panel_id: a, target_panel_id: b })?.id
    const res = tool('agent_apply_ops').execute({ ops: [{ op: 'delete_panel', panel_id: a }] }, canvas) as { ok: boolean }
    expect(res.ok).toBe(true)
    expect(canvas.panels.length).toBe(1)
    expect(canvas.connections.some((c) => c.id === cid)).toBe(false)
  })

  it('text 节点内容字段归一：LLM 写 text 自动落到渲染字段 content', () => {
    const canvas = makeCanvas()
    const res = tool('agent_apply_ops').execute({
      ops: [
        { op: 'add_panel', type: 'text', name: '剧本', content: { text: '初稿' } },
        { op: 'update_panel', panel_id: '剧本', changes: { content: { text: '二稿' } } },
      ],
    }, canvas) as { ok: boolean }
    expect(res.ok).toBe(true)
    const p = canvas.panels.find((x) => x.name === '剧本')
    expect(p?.content).toEqual({ content: '二稿' })
  })

  it('节点引用支持名称：同批次新建按名称连线、已有节点按名称连线', () => {
    const canvas = makeCanvas()
    const scriptId = canvas.addPanel({ type: 'text', name: '剧本', content: {}, x: 0, y: 0, width: 240, height: 180 })
    const res = tool('agent_apply_ops').execute({
      ops: [
        { op: 'add_panel', type: 'image', name: '分镜图1', content: { prompt: 'p1' } },
        { op: 'add_connection', source_panel_id: '剧本', target_panel_id: '分镜图1' },
        { op: 'add_connection', source_panel_id: '不存在', target_panel_id: '分镜图1' },
      ],
    }, canvas) as { ok: boolean; data: Record<string, unknown> }

    const results = res.data.results as Record<string, unknown>[]
    expect(results[0].ok).toBe(true)
    expect(results[1].ok).toBe(true)
    expect(results[2].ok).toBe(false)
    expect(results[2].error).toContain('节点不存在')
    // 剧本 → 分镜图1 的连线建在真实 id 上
    const shotId = res.data.new_panel_ids as string[]
    expect(canvas.connections.some((c) => c.source_panel_id === scriptId && c.target_panel_id === shotId[0])).toBe(true)
  })
})

describe('agent_run_generation', () => {
  it('compose：按摆放顺序（行带 y → 带内 x）拼接上游视频并写回节点', async () => {
    const canvas = makeCanvas()
    const v1 = canvas.addPanel({ type: 'video', content: { content: 'https://v/1.mp4', status: 'success' }, x: 0, y: 0, width: 400, height: 240 })
    const v2 = canvas.addPanel({ type: 'video', content: { content: 'https://v/2.mp4', status: 'success' }, x: 500, y: 0, width: 400, height: 240 })
    const img = canvas.addPanel({ type: 'image', content: { content: 'https://i/1.png' }, x: 1000, y: 0, width: 340, height: 240 })
    const composeId = canvas.addPanel({ type: 'compose', content: {}, x: 0, y: 400, width: 360, height: 240 })
    // 连线顺序故意打乱，验证按摆放位置排序
    canvas.addConnection({ source_panel_id: v2, target_panel_id: composeId })
    canvas.addConnection({ source_panel_id: v1, target_panel_id: composeId })
    canvas.addConnection({ source_panel_id: img, target_panel_id: composeId })

    const res = await tool('agent_run_generation').execute({ panel_id: composeId }, canvas) as { ok: boolean; data?: Record<string, unknown> }
    expect(res.ok).toBe(true)
    expect(res.data?.segments).toBe(2)
    // 成片写入独立结果节点（compose 节点自身不渲染视频）
    const resultNode = canvas.panels.find((p) => p.name === '成片')
    expect(resultNode?.content.content).toBe('https://example.com/final.mp4')
    expect(resultNode?.content.status).toBe('success')
    expect(canvas.connections.some((c) => c.source_panel_id === composeId && c.target_panel_id === resultNode?.id)).toBe(true)
    const composePanel = canvas.panels.find((p) => p.id === composeId)
    expect(composePanel?.content.status).toBe('idle')
    expect(composePanel?.content.result_panel_id).toBe(resultNode?.id)
  })

  it('compose：上游有未生成完成的视频段时报错且不拼接', async () => {
    const canvas = makeCanvas()
    const v1 = canvas.addPanel({ type: 'video', content: { content: 'https://v/1.mp4', status: 'success' }, x: 0, y: 0, width: 400, height: 240 })
    const v2 = canvas.addPanel({ type: 'video', content: { status: 'loading' }, x: 500, y: 0, width: 400, height: 240 })
    const composeId = canvas.addPanel({ type: 'compose', content: {}, x: 0, y: 400, width: 360, height: 240 })
    canvas.addConnection({ source_panel_id: v1, target_panel_id: composeId })
    canvas.addConnection({ source_panel_id: v2, target_panel_id: composeId })

    const res = await tool('agent_run_generation').execute({ panel_id: composeId }, canvas) as { ok: boolean; error?: string }
    expect(res.ok).toBe(false)
    expect(res.error).toContain('尚未生成完成')
    expect(composeCanvasVideos).not.toHaveBeenCalled()
  })

  it('video 生成失败时返回失败结果', async () => {
    const canvas = makeCanvas()
    const v = canvas.addPanel({ type: 'video', content: { prompt: '测试' }, x: 0, y: 0, width: 400, height: 240 })
    vi.mocked(executeInNodeVideoGeneration).mockResolvedValueOnce(null)
    const res = await tool('agent_run_generation').execute({ panel_id: v }, canvas) as { ok: boolean; error?: string }
    expect(res.ok).toBe(false)
    expect(res.error).toContain('生成失败')
  })

  it('compose：上游没有已生成视频时报错', async () => {
    const canvas = makeCanvas()
    const composeId = canvas.addPanel({ type: 'compose', content: {}, x: 0, y: 0, width: 360, height: 240 })
    const res = await tool('agent_run_generation').execute({ panel_id: composeId }, canvas) as { ok: boolean; error?: string }
    expect(res.ok).toBe(false)
    expect(res.error).toContain('没有上游视频节点')
  })
})

describe('agent_get_models', () => {
  it('返回时长档位、默认时长、默认模型与模型参考图上限；视频模型带自己的档位，未配置回落全局', () => {
    const res = tool('agent_get_models').execute({}, makeCanvas()) as { ok: boolean; data: Record<string, unknown> }
    expect(res.ok).toBe(true)
    expect(res.data.video_durations).toEqual([3, 5, 7, 10, 15])
    expect(res.data.default_video_duration).toBe(5)
    expect(res.data.default_video_model).toBe('agnes-video-2.5')
    expect(res.data.default_image_model).toBe('agnes-image-2.1-flash')
    const videos = res.data.video_models as Record<string, unknown>[]
    expect(videos.length).toBe(1)
    expect(videos[0].max_ref_images).toBe(5)
    expect(videos[0].is_default).toBe(true)
    expect(videos[0].video_durations).toEqual([5, 10])
    const images = res.data.image_models as Record<string, unknown>[]
    expect(images.length).toBe(1)
    expect(images[0].max_ref_images).toBeNull()
    expect(images[0].is_default).toBe(true)
  })
})

describe('模型指定强制（费用安全）', () => {
  it('add_panel 剥离 LLM 传入的 content.model，其余内容保留', () => {
    const canvas = makeCanvas()
    const res = tool('agent_apply_ops').execute({
      ops: [{ op: 'add_panel', type: 'video', name: '镜头1', content: { prompt: '城市夜景', model: 'seedance-pro', seconds: 5 } }],
    }, canvas) as { ok: boolean }
    expect(res.ok).toBe(true)
    const panel = canvas.panels[0]
    expect(panel.content.prompt).toBe('城市夜景')
    expect(panel.content.seconds).toBe(5)
    expect('model' in panel.content).toBe(false)
  })

  it('update_panel 剥离 changes.content.model，不得篡改已有节点模型', () => {
    const canvas = makeCanvas()
    const pid = canvas.addPanel({ type: 'video', content: { prompt: 'a', model: 'agnes-video-2.5' }, x: 0, y: 0, width: 240, height: 180 })
    const res = tool('agent_apply_ops').execute({
      ops: [{ op: 'update_panel', panel_id: pid, changes: { content: { prompt: 'b', model: 'seedance-pro' } } }],
    }, canvas) as { ok: boolean }
    expect(res.ok).toBe(true)
    const panel = canvas.panels[0]
    expect(panel.content.prompt).toBe('b')
    expect(panel.content.model).toBe('agnes-video-2.5')
  })

  it('run_generation 用户点名模型：合法 id 写入节点后生成', async () => {
    const canvas = makeCanvas()
    const v = canvas.addPanel({ type: 'video', content: { prompt: '测试' }, x: 0, y: 0, width: 400, height: 240 })
    const res = await tool('agent_run_generation').execute({ panel_id: v, model: 'agnes-video-2.5' }, canvas) as { ok: boolean }
    expect(res.ok).toBe(true)
    expect(canvas.panels[0].content.model).toBe('agnes-video-2.5')
    expect(executeInNodeVideoGeneration).toHaveBeenCalled()
  })

  it('run_generation 非法模型 id 报错且不触发生成', async () => {
    const canvas = makeCanvas()
    const v = canvas.addPanel({ type: 'video', content: { prompt: '测试' }, x: 0, y: 0, width: 400, height: 240 })
    const res = await tool('agent_run_generation').execute({ panel_id: v, model: 'seedance-pro' }, canvas) as { ok: boolean; error?: string }
    expect(res.ok).toBe(false)
    expect(res.error).toContain('模型不可用')
    expect(executeInNodeVideoGeneration).not.toHaveBeenCalled()
    expect('model' in canvas.panels[0].content).toBe(false)
  })
})

describe('便捷工具与权限', () => {
  it('agent_create_text_node 建文本节点并返回 id', () => {
    const canvas = makeCanvas()
    const res = tool('agent_create_text_node').execute({ text: ' hello ' }, canvas) as { ok: boolean; data: Record<string, unknown> }
    expect(res.ok).toBe(true)
    const p = canvas.panels.find((x) => x.id === res.data.panel_id)
    expect(p?.type).toBe('text')
    expect(p?.content).toEqual({ content: ' hello ' })
  })

  it('agent_select 目标不存在时报错', () => {
    const canvas = makeCanvas()
    const res = tool('agent_select').execute({ panel_id: 'nope' }, canvas) as { ok: boolean; error?: string }
    expect(res.ok).toBe(false)
    expect(res.error).toContain('nope')
  })

  it('只读档只保留 read 组工具', () => {
    const readonlyTools = toolsForMode('readonly')
    expect(readonlyTools.length).toBeGreaterThan(0)
    expect(readonlyTools.every((t) => t.group === 'read')).toBe(true)
    expect(toolsForMode('auto').length).toBe(AGENT_TOOLS.length)
  })

  it('schema 与工具一一对应且名称唯一', () => {
    const schemas = agentToolSchemasOpenAI()
    expect(schemas.length).toBe(AGENT_TOOLS.length)
    expect(new Set(schemas.map((s: { function: { name: string } }) => s.function.name)).size).toBe(AGENT_TOOLS.length)
    expect(agentToolSchemasOpenAI(toolsForMode('readonly')).length).toBe(toolsForMode('readonly').length)
  })
})

describe('storyboard_extract_entities', () => {
  it('返回实体清单并注入风格后的设定图提示词', async () => {
    vi.mocked(extractEntities).mockResolvedValueOnce({
      characters: [{ kind: 'character', name: '林小满', description: '红衣少女', refImageUrl: '' }],
      scenes: [],
      props: [{ kind: 'prop', name: '油纸伞', description: '褪色红伞', refImageUrl: '' }],
    })
    const canvas = makeCanvas()
    const res = await tool('storyboard_extract_entities').execute({ script_text: '剧本全文' }, canvas) as { ok: boolean; data: Record<string, unknown> }
    expect(res.ok).toBe(true)
    const characters = res.data.characters as Array<Record<string, unknown>>
    const props = res.data.props as Array<Record<string, unknown>>
    expect(characters[0].name).toBe('林小满')
    expect(String(characters[0].asset_prompt)).toContain('三视图')
    expect(String(characters[0].asset_prompt)).toContain('画面风格：胶片感')
    expect(String(props[0].asset_prompt)).toContain('物品单体')
    expect(res.data.style_applied).toBe(true)
  })

  it('script_text 为空报错', async () => {
    const res = await tool('storyboard_extract_entities').execute({ script_text: '  ' }, makeCanvas()) as { ok: boolean; error?: string }
    expect(res.ok).toBe(false)
    expect(res.error).toContain('为空')
  })

  it('管线抛错时回传错误信息', async () => {
    vi.mocked(extractEntities).mockRejectedValueOnce(new Error('分镜管线解析失败: x'))
    const res = await tool('storyboard_extract_entities').execute({ script_text: '剧本' }, makeCanvas()) as { ok: boolean; error?: string }
    expect(res.ok).toBe(false)
    expect(res.error).toContain('解析失败')
  })
})

describe('storyboard_split', () => {
  const entityCard = (name: string, kind: string, url = '') => ({
    type: 'image', name, x: 0, y: 0, width: 300, height: 320,
    content: { kind, entityName: name, entityDesc: `${name}设定`, status: url ? 'success' : 'pending', content: url },
  })

  it('收集实体卡调用拆分并回传成品 prompt；无实体卡报错', async () => {
    vi.mocked(splitStoryboard).mockResolvedValueOnce([
      { no: 1, shotSize: '近景', camera: '缓推', description: '雨夜回头', dialogue: '谁？', characters: ['林小满'], location: '巷口', props: [], prompt: '成品提示词' },
    ])
    const canvas = makeCanvas()
    canvas.addPanel(entityCard('林小满', 'character', 'https://i/x.png'))
    canvas.addPanel(entityCard('巷口', 'scene'))
    const res = await tool('storyboard_split').execute({ script_text: '剧本全文' }, canvas) as { ok: boolean; data: Record<string, unknown> }
    expect(res.ok).toBe(true)
    const shots = res.data.shots as Array<Record<string, unknown>>
    expect(shots[0].prompt).toBe('成品提示词')
    expect(shots[0].shot_size).toBe('近景')
    expect(res.data.entity_card_count).toBe(2)
    // 拆分收到画布上的实体卡与风格配置
    const call = vi.mocked(splitStoryboard).mock.calls[0]
    expect(call[1]?.characters[0]?.name).toBe('林小满')
    expect(call[2]?.styleConfig).toEqual({ prefix: '胶片感', suffix: '', negativePrompt: '' })
    expect(call[2]?.cameraVocabulary).toEqual(['缓推', '手持跟随'])

    const empty = await tool('storyboard_split').execute({ script_text: '剧本' }, makeCanvas()) as { ok: boolean; error?: string }
    expect(empty.ok).toBe(false)
    expect(empty.error).toContain('实体设定卡')
  })

  it('已成功生成的实体卡参考图 URL 传入拆分（沿用设定）', async () => {
    vi.mocked(splitStoryboard).mockResolvedValueOnce([])
    const canvas = makeCanvas()
    canvas.addPanel(entityCard('林小满', 'character', 'https://i/x.png'))
    await tool('storyboard_split').execute({ script_text: '剧本' }, canvas)
    const call = vi.mocked(splitStoryboard).mock.calls[0]
    expect(call[1]?.characters[0]?.refImageUrl).toBe('https://i/x.png')
  })
})

describe('实体设定图生成（kind=asset）', () => {
  it('asset 走图片生成分支', async () => {
    const canvas = makeCanvas()
    const card = canvas.addPanel({ type: 'image', content: { kind: 'character', entityName: '林小满', prompt: '设定图提示词' }, x: 0, y: 0, width: 300, height: 320 })
    const res = await tool('agent_run_generation').execute({ panel_id: card, kind: 'asset' }, canvas) as { ok: boolean }
    expect(res.ok).toBe(true)
    expect(executeInNodeGeneration).toHaveBeenCalled()
    expect(executeInNodeVideoGeneration).not.toHaveBeenCalled()
  })
})

describe('对话式风格选定（库条目写入画布）', () => {
  it('storyboard_list_styles 返回库条目（含描述与封面，供语义推荐与可视化卡片）', async () => {
    const res = await tool('storyboard_list_styles').execute({}, makeCanvas()) as { ok: boolean; data: Record<string, unknown> }
    expect(res.ok).toBe(true)
    const styles = res.data.styles as Array<Record<string, unknown>>
    expect(styles[0]).toEqual({ id: 7, name: '日式动漫', description: '日系动漫画风', cover_image: 'https://i/cover.jpg' })
  })

  it('style_preset_id 命中：写入画布风格且提示词带风格段', async () => {
    vi.mocked(extractEntities).mockResolvedValueOnce({
      characters: [{ kind: 'character', name: '林小满', description: '红衣少女', refImageUrl: '' }],
      scenes: [],
      props: [],
    })
    const canvas = makeCanvas()
    const res = await tool('storyboard_extract_entities').execute({ script_text: '剧本', style_preset_id: 7 }, canvas) as { ok: boolean; data: Record<string, unknown> }
    expect(res.ok).toBe(true)
    expect(res.data.style_applied).toBe(true)
    const characters = res.data.characters as Array<Record<string, unknown>>
    expect(String(characters[0].asset_prompt)).toContain('日式动漫风格')
  })

  it('style_preset_id 未命中报错且不写画布', async () => {
    const canvas = makeCanvas()
    const res = await tool('storyboard_extract_entities').execute({ script_text: '剧本', style_preset_id: 99 }, canvas) as { ok: boolean; error?: string }
    expect(res.ok).toBe(false)
    expect(res.error).toContain('风格条目不存在')
  })
})

describe('storyboard_set_style（自定义风格正路）', () => {
  it('style_text 写入画布自定义风格并回显配置', async () => {
    const canvas = makeCanvas()
    const res = await tool('storyboard_set_style').execute({ style_text: '日式真实电视剧质感，冷色调' }, canvas) as { ok: boolean; data: Record<string, unknown> }
    expect(res.ok).toBe(true)
    expect(res.data.style_config).toEqual({ prefix: '日式真实电视剧质感，冷色调', suffix: '', negativePrompt: '' })
    // 画布风格生效后，实体提取即带自定义风格段
    vi.mocked(extractEntities).mockResolvedValueOnce({
      characters: [{ kind: 'character', name: '慕照帝', description: '少年帝王', refImageUrl: '' }],
      scenes: [],
      props: [],
    })
    const out = await tool('storyboard_extract_entities').execute({ script_text: '剧本' }, canvas) as { ok: boolean; data: Record<string, unknown> }
    const characters = out.data.characters as Array<Record<string, unknown>>
    expect(String(characters[0].asset_prompt)).toContain('日式真实电视剧质感')
  })

  it('style_preset_id 走库条目；两个参数都缺报错', async () => {
    const canvas = makeCanvas()
    const viaPreset = await tool('storyboard_set_style').execute({ style_preset_id: 7 }, canvas) as { ok: boolean }
    expect(viaPreset.ok).toBe(true)
    const none = await tool('storyboard_set_style').execute({}, canvas) as { ok: boolean; error?: string }
    expect(none.ok).toBe(false)
    expect(none.error).toContain('至少提供一个')
  })
})

describe('agent_read_image', () => {
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

  function stubImageFetch() {
    vi.stubGlobal('FileReader', FakeFileReader)
    vi.stubGlobal('fetch', vi.fn(async () => new Response(new Blob(['abc'], { type: 'image/png' }), { status: 200, headers: { 'content-type': 'image/png' } })))
  }

  it('归 read 组：只读档可用', () => {
    expect(tool('agent_read_image').group).toBe('read')
    const r = resolveToolCall({ args: {}, gatedKinds: [], panelType: undefined, mode: 'readonly', toolName: 'agent_read_image', toolGroup: 'read' })
    expect(r.action).toBe('allow')
  })

  it('成功：拉图转附件，data 带节点名与 URL', async () => {
    stubImageFetch()
    try {
      const canvas = makeCanvas()
      const pid = canvas.addPanel({ type: 'image', name: '参考图', content: { status: 'success', content: 'https://cdn.example.com/a.png' }, x: 0, y: 0, width: 240, height: 180 })
      const res = await tool('agent_read_image').execute({ panel_id: pid }, canvas) as { ok: boolean; data: Record<string, unknown>; images?: Array<{ data: string; mimeType: string }> }
      expect(res.ok).toBe(true)
      expect(res.data.name).toBe('参考图')
      expect(res.data.image_url).toBe('https://cdn.example.com/a.png')
      expect(res.images).toEqual([{ data: 'QUJD', mimeType: 'image/png' }])
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('节点不存在 / 非图片节点 / 未生成完成 → 明确报错', async () => {
    const canvas = makeCanvas()
    canvas.addPanel({ type: 'text', content: { text: '文本' }, x: 0, y: 0, width: 240, height: 180 })
    canvas.addPanel({ type: 'image', name: '生成中', content: { status: 'running' }, x: 0, y: 0, width: 240, height: 180 })

    const missing = await tool('agent_read_image').execute({ panel_id: 'nope' }, canvas) as { ok: boolean; error?: string }
    expect(missing.ok).toBe(false)
    expect(missing.error).toContain('不存在')

    const notImage = await tool('agent_read_image').execute({ panel_id: canvas.panels[0].id }, canvas) as { ok: boolean; error?: string }
    expect(notImage.ok).toBe(false)
    expect(notImage.error).toContain('不是图片节点')

    const pending = await tool('agent_read_image').execute({ panel_id: canvas.panels[1].id }, canvas) as { ok: boolean; error?: string }
    expect(pending.ok).toBe(false)
    expect(pending.error).toContain('尚未生成完成')
  })
})

describe('agent_load_skill', () => {
  it('归 read 组：只读档可用；命中返回正文，未命中列可用技能', async () => {
    vi.mocked(getCachedSkill).mockReturnValueOnce(undefined)
    vi.mocked(getCachedSkills).mockReturnValueOnce([
      { name: '节奏技能', tag: '节奏', description: 'x', content: 'y' },
    ])
    const miss = await tool('agent_load_skill').execute({ name: '不存在' }, makeCanvas()) as { ok: boolean; error?: string }
    expect(miss.ok).toBe(false)
    expect(miss.error).toContain('节奏技能')

    vi.mocked(getCachedSkill).mockReturnValueOnce({ name: '节奏技能', tag: '节奏', description: 'x', content: '方法论全文' })
    const hit = await tool('agent_load_skill').execute({ name: '节奏技能' }, makeCanvas()) as { ok: boolean; data: Record<string, unknown> }
    expect(hit.ok).toBe(true)
    expect(hit.data.content).toBe('方法论全文')
  })
})
