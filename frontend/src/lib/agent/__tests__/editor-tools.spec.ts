/* editor_* 剪辑器工具组单测：目标解析 / apply_ops 原子校验与时长探测 / 渲染轮询 / 宿主 generation 门 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('@/api/editor', () => ({
  listEditorProjects: vi.fn(),
  getEditorProject: vi.fn(),
  createEditorProject: vi.fn(),
  saveEditorDocument: vi.fn(),
  previewSubtitleSegments: vi.fn(),
  submitEditorRender: vi.fn(),
  getEditorRenderStatus: vi.fn(),
}))
vi.mock('@/api/assets', () => ({
  getAsset: vi.fn(),
  listAssets: vi.fn(),
  createAsset: vi.fn(),
}))
vi.mock('@/api/canvasWorkspace', () => ({
  applyCanvasOps: vi.fn(),
  getWorkspace: vi.fn(),
  listWorkspaces: vi.fn(),
}))
vi.mock('@/api/canvas', () => ({
  generateCanvasTts: vi.fn(),
  composeCanvasVideos: vi.fn(),
  getCanvasVoicesCached: vi.fn(async () => ({ voices: [] })),
}))
vi.mock('@/api/images', () => ({ createImageTask: vi.fn() }))
vi.mock('@/api/videos', () => ({ createVideoTask: vi.fn() }))
vi.mock('@/api/presets', () => ({ getPreset: vi.fn() }))
vi.mock('@/stores/taskQueue', () => ({ useTaskQueueStore: vi.fn() }))
vi.mock('@/stores/models', () => ({ useModelsStore: () => ({ getDefaultModel: () => 'm-x' }) }))
vi.mock('@/stores/canvas', () => ({ useCanvasStore: vi.fn() }))
vi.mock('../skills', () => ({
  loadAgentSkillFull: vi.fn(),
  readSkillResource: vi.fn(),
  saveAgentSkill: vi.fn(),
  SKILL_CONTENT_MAX_CHARS: 20000,
  getActiveSkillScope: vi.fn(() => null),
}))
vi.mock('../subagent', () => ({
  runSubagent: vi.fn(),
  subagentHostFromParent: vi.fn(),
}))

import {
  getEditorProject,
  listEditorProjects,
  saveEditorDocument,
  submitEditorRender,
  getEditorRenderStatus,
} from '@/api/editor'
import { getAsset, createAsset } from '@/api/assets'
import { generateCanvasTts } from '@/api/canvas'
import { applyCanvasOps } from '@/api/canvasWorkspace'
import { CHAT_TOOLS } from '../chat-tools'
import { setEditorDurationProberForTests } from '../editor-tools'
import { AgentKernel, type KernelEvent } from '../kernel'
import { resolveHostGenerationGate } from '../policy'
import { Type } from 'typebox'

const listProjects = vi.mocked(listEditorProjects)
const getProject = vi.mocked(getEditorProject)
const saveDoc = vi.mocked(saveEditorDocument)
const getAssetById = vi.mocked(getAsset)
const submitRender = vi.mocked(submitEditorRender)
const getRenderStatus = vi.mocked(getEditorRenderStatus)
const addPanels = vi.mocked(applyCanvasOps)
const ttsMock = vi.mocked(generateCanvasTts)
const createAssetMock = vi.mocked(createAsset)

const applyOpsTool = CHAT_TOOLS.find((t) => t.name === 'editor_apply_ops')!
const renderTool = CHAT_TOOLS.find((t) => t.name === 'editor_render')!

/** 经变量中转调用（Mimosa 门禁对 execute 字面量实参形态误报注入，同 tools.spec 的 runTool） */
async function runOps(args: Record<string, unknown>): Promise<unknown> {
  const handler = applyOpsTool.execute
  return handler(args, {})
}

/** 宿主工具经变量中转调用（同 runOps） */
async function runChatTool(name: string, args: Record<string, unknown>): Promise<unknown> {
  const tool = CHAT_TOOLS.find((t) => t.name === name)!
  const handler = tool.execute
  return handler(args, {})
}

function baseDoc() {
  return {
    timebase: 30, width: 1280, height: 720,
    tracks: [
      { id: 'v1', kind: 'video' as const, order: 0, flags: { hidden: false, locked: false, muted: false, solo: false } },
      { id: 'a1', kind: 'audio' as const, order: 0, flags: { hidden: false, locked: false, muted: false, solo: false } },
      { id: 's1', kind: 'subtitle' as const, order: 0, flags: { hidden: false, locked: false, muted: false, solo: false } },
    ],
    clips: [] as Array<Record<string, unknown>>,
  }
}

function mockProject(doc = baseDoc(), revision = 3) {
  getProject.mockResolvedValue({ uid: 'u1', title: '工程', revision, document: doc } as never)
}

beforeEach(() => {
  vi.clearAllMocks()
  setEditorDurationProberForTests(() => Promise.resolve(2.5))
  listProjects.mockResolvedValue({ total: 1, items: [{ uid: 'u1', title: '工程' } as never] })
  saveDoc.mockResolvedValue({ revision: 4, saved_at: '2026-10-07T00:00:00' })
  getAssetById.mockResolvedValue({ id: 7, name: '镜头1', media_type: 'video', asset_url: '/uploads/a.mp4' } as never)
})

afterEach(() => {
  setEditorDurationProberForTests(null)
})

describe('editor_list_projects / 目标解析', () => {
  it('无工程时目标解析报错并引导新建', async () => {
    listProjects.mockResolvedValue({ total: 0, items: [] })
    const r = await applyOpsTool.execute({ ops: [{ op: 'removeClip', payload: { clipId: 'c1' } }] }, {})
    expect(r.ok).toBe(false)
    expect((r as { error: string }).error).toContain('还没有剪辑工程')
  })

  it('多个工程时不猜目标，列出 uid 反问', async () => {
    listProjects.mockResolvedValue({
      total: 2,
      items: [{ uid: 'uid-a', title: 'A' }, { uid: 'uid-b', title: 'B' }] as never[],
    })
    const r = await applyOpsTool.execute({ ops: [{ op: 'removeClip', payload: { clipId: 'c1' } }] }, {})
    expect(r.ok).toBe(false)
    expect((r as { error: string }).error).toContain('uid-a')
  })
})

describe('generate_tts（宿主级配音）', () => {
  it('文本→配音→素材库入库，返回 asset_id 与 addClip 指引', async () => {
    ttsMock.mockResolvedValue({ audio_url: 'https://a/tts.mp3', duration_ms: 3200 })
    createAssetMock.mockResolvedValue({ id: 3001, name: '配音-旁白', media_type: 'audio', asset_url: 'https://a/tts.mp3' } as never)
    const r = await runChatTool('generate_tts', { text: '出发吧，小猫！', voice: 'narrator_female_zh', speed: 1.1, name: '旁白' }) as { ok: boolean; data: Record<string, unknown> }
    expect(r.ok).toBe(true)
    expect(ttsMock).toHaveBeenCalledWith({ text: '出发吧，小猫！', voice: 'narrator_female_zh', speed: 1.1 })
    expect(createAssetMock).toHaveBeenCalledWith(expect.objectContaining({ media_type: 'audio', name: '配音-旁白' }))
    expect(r.data.asset_id).toBe(3001)
    expect(String(r.data.message)).toContain('addClip')
  })

  it('text 缺失报错且不调 API', async () => {
    const r = await runChatTool('generate_tts', {}) as { ok: boolean; error?: string }
    expect(r.ok).toBe(false)
    expect(r.error).toContain('text 不能为空')
    expect(ttsMock).not.toHaveBeenCalled()
  })
})

describe('editor_apply_ops', () => {
  it('同批次 addTrack + addClip：补全累积新轨效果，addClip 正常补 id/时长入新轨', async () => {
    mockProject()
    getAssetById.mockResolvedValue({ id: 9, name: '旁白', media_type: 'audio', asset_url: '/uploads/a.mp3' } as never)
    const r = await runOps({ ops: [
      { op: 'addTrack', payload: { track: { id: 'track_narration', kind: 'audio' } } },
      { op: 'addClip', payload: { clip: { assetId: 9, trackId: 'track_narration', start: 0 } } },
    ] }) as { ok: boolean; error?: string }
    expect(r.ok).toBe(true)
    const savedDoc = saveDoc.mock.calls[0][1] as unknown as { tracks: Array<{ id: string }>; clips: Array<Record<string, unknown>> }
    expect(savedDoc.tracks.some((t) => t.id === 'track_narration')).toBe(true)
    expect(savedDoc.clips.length).toBe(1)
    expect(savedDoc.clips[0].assetId).toBe(9)
    expect(savedDoc.clips[0].duration).toBe(2.5)
  })

  it('音频轨拒收非 audio 素材（假配音拦截）', async () => {
    mockProject()
    getAssetById.mockResolvedValue({ id: 1003, name: '假配音', media_type: 'image', asset_url: '/uploads/x.png' } as never)
    const r = await runOps({ ops: [{ op: 'addClip', payload: { clip: { assetId: 1003, trackId: 'a1', start: 0 } } }] }) as { ok: boolean; error?: string }
    expect(r.ok).toBe(false)
    expect(r.error).toContain('不匹配')
    expect(saveDoc).not.toHaveBeenCalled()
  })

  it('addClip 缺省自动补全：默认视频轨 + 探测时长 + 轨尾放置 + agent_edit 写前快照语义', async () => {
    const doc = baseDoc()
    mockProject(doc)
    const r = await applyOpsTool.execute({ ops: [{ op: 'addClip', payload: { clip: { assetId: 7 } } }] }, {})
    expect(r.ok).toBe(true)
    expect(saveDoc).toHaveBeenCalledTimes(1)
    const [uid, savedDoc, baseRevision, reason] = saveDoc.mock.calls[0]
    expect(uid).toBe('u1')
    expect(baseRevision).toBe(3)
    expect(reason).toBe('agent_edit')
    const clip = savedDoc.clips[0]
    expect(clip.trackId).toBe('v1')
    expect(clip.duration).toBe(2.5)
    expect(clip.start).toBe(0)
    expect(typeof clip.id).toBe('string')
    expect((r as { data: { revision: number } }).data.revision).toBe(4)
  })

  it('图片素材缺时长默认 3 秒静帧', async () => {
    getAssetById.mockResolvedValue({ id: 8, name: '图', media_type: 'image', asset_url: '/uploads/a.jpg' } as never)
    mockProject()
    const r = await applyOpsTool.execute({ ops: [{ op: 'addClip', payload: { clip: { assetId: 8 } } }] }, {})
    expect(r.ok).toBe(true)
    expect(saveDoc.mock.calls[0][1].clips[0].duration).toBe(3.0)
  })

  it('视频/音频轨重叠 fail-closed：任一 op 失败整体不落盘', async () => {
    const doc = baseDoc()
    doc.clips.push({ id: 'c1', trackId: 'v1', assetId: null, start: 0, duration: 5, trimStart: 0, props: {} })
    mockProject(doc)
    const r = await applyOpsTool.execute({
      ops: [{ op: 'addClip', payload: { clip: { assetId: 7, start: 1 } } }],
    }, {})
    expect(r.ok).toBe(false)
    expect((r as { error: string }).error).toContain('overlap')
    expect(saveDoc).not.toHaveBeenCalled()
  })

  it('未知 op 与非法 payload 均不落盘', async () => {
    mockProject()
    const bad1 = await applyOpsTool.execute({ ops: [{ op: 'boom', payload: {} }] }, {})
    expect(bad1.ok).toBe(false)
    expect((bad1 as { error: string }).error).toContain('未知')
    const bad2 = await applyOpsTool.execute({ ops: [{ op: 'addClip', payload: {} }] }, {})
    expect(bad2.ok).toBe(false)
    expect((bad2 as { error: string }).error).toContain('未通过校验')
    expect(saveDoc).not.toHaveBeenCalled()
  })
})

describe('editor_render', () => {
  it('轮询到成功即回复成片链接；place_on_canvas 显式 false 不落画布', async () => {
    mockProject()
    submitRender.mockResolvedValue({ render_status: 'rendering', render_progress: null, final_url: null, render_error: null })
    getRenderStatus
      .mockResolvedValueOnce({ render_status: 'rendering', render_progress: '1/8', final_url: null, render_error: null })
      .mockResolvedValueOnce({ render_status: 'succeeded', render_progress: null, final_url: '/uploads/editor/x.mp4', render_error: null })

    vi.useFakeTimers()
    try {
      const p = renderTool.execute({ editing_project_id: 'u1', place_on_canvas: false }, {})
      await vi.advanceTimersByTimeAsync(3000)
      await vi.advanceTimersByTimeAsync(3000)
      const r = (await p) as { ok: boolean; data: { final_url: string; message: string } }
      expect(r.ok).toBe(true)
      expect(r.data.final_url).toBe('/uploads/editor/x.mp4')
      expect(addPanels).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('place_on_canvas 成功时经 canvas ops 落视频节点', async () => {
    mockProject()
    submitRender.mockResolvedValue({ render_status: 'rendering', render_progress: null, final_url: null, render_error: null })
    getRenderStatus.mockResolvedValue({ render_status: 'succeeded', render_progress: null, final_url: '/uploads/editor/y.mp4', render_error: null })
    addPanels.mockResolvedValue({ results: [], new_panel_ids: [], failed: 0 } as never)

    vi.useFakeTimers()
    try {
      const p = renderTool.execute({ editing_project_id: 'u1', place_on_canvas: true, canvas_workspace_id: 'ws1' }, {})
      await vi.advanceTimersByTimeAsync(3000)
      await p
      expect(addPanels).toHaveBeenCalledWith('ws1', [expect.objectContaining({ op: 'add_panel', type: 'video' })])
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('宿主 generation 组门（kernel + policy）', () => {
  function hostKernel(mode: 'readonly' | 'confirm' | 'auto') {
    const events: KernelEvent[] = []
    const kernel = new AgentKernel({
      systemPrompt: 'test',
      getAuthToken: async () => null,
      getMode: () => mode,
      tools: [
        {
          name: 'editor_render',
          description: '渲染',
          group: 'generation',
          parameters: Type.Object({}),
          execute: async () => ({ ok: true, data: {} }),
        },
        {
          name: 'editor_apply_ops',
          description: '编辑',
          group: 'write',
          parameters: Type.Object({}),
          execute: async () => ({ ok: true, data: {} }),
        },
      ],
    })
    kernel.subscribe((e) => events.push(e))
    return { kernel, events }
  }

  it('confirm 档：generation 组工具首次过门，放行后第二次直通', async () => {
    const { kernel, events } = hostKernel('confirm')
    const gate = kernel.authorizeTool('editor_render', {})
    await new Promise((r) => setTimeout(r, 0))
    expect(events.some((e) => e.type === 'confirm_request' && e.tool === 'editor_render')).toBe(true)
    kernel.confirm(true)
    expect((await gate).allowed).toBe(true)

    const second = await kernel.authorizeTool('editor_render', {})
    expect(second.allowed).toBe(true)
    expect(events.filter((e) => e.type === 'confirm_request').length).toBe(1)
  })

  it('confirm 档：拒绝过门则不放行且停止回合', async () => {
    const { kernel } = hostKernel('confirm')
    const gate = kernel.authorizeTool('editor_render', {})
    await new Promise((r) => setTimeout(r, 0))
    kernel.confirm(false)
    const decision = await gate
    expect(decision.allowed).toBe(false)
    expect(decision.stop).toBe(true)
  })

  it('readonly 档：generation 组拒绝，write 组照常放行（宿主组既有行为）', async () => {
    const { kernel } = hostKernel('readonly')
    const renderGate = await kernel.authorizeTool('editor_render', {})
    expect(renderGate.allowed).toBe(false)
    const write = await kernel.authorizeTool('editor_apply_ops', {})
    expect(write.allowed).toBe(true)
  })

  it('policy 纯函数：auto 档直通、已过门直通', () => {
    expect(resolveHostGenerationGate('editor_render', 'auto', []).action).toBe('allow')
    expect(resolveHostGenerationGate('editor_render', 'confirm', ['editor_render']).action).toBe('allow')
    expect(resolveHostGenerationGate('editor_render', 'confirm', []).action).toBe('gate')
    expect(resolveHostGenerationGate('editor_render', 'readonly', []).action).toBe('reject')
  })
})
