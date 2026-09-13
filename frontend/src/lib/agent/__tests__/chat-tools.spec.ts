/* chat 宿主工具组单测：参数装配/参考图解析/预设合并/技能加载/内核宿主工具注入 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/images', () => ({ createImageTask: vi.fn() }))
vi.mock('@/api/videos', () => ({ createVideoTask: vi.fn() }))
vi.mock('@/api/presets', () => ({ getPreset: vi.fn() }))
vi.mock('@/stores/taskQueue', () => ({
  useTaskQueueStore: () => ({ registerChatTask: mocks.registerChatTask }),
}))
vi.mock('@/stores/models', () => ({
  useModelsStore: () => ({ getDefaultModel: (t: string) => (t === 'image' ? 'img-x' : 'vid-x') }),
}))
vi.mock('../skills', () => ({
  loadAgentSkillFull: vi.fn(),
  readSkillResource: vi.fn(),
  saveAgentSkill: vi.fn(),
  SKILL_CONTENT_MAX_CHARS: 20000,
  getActiveSkillScope: vi.fn(() => null),
}))

const mocks = vi.hoisted(() => ({
  registerChatTask: vi.fn(),
}))

import { createImageTask } from '@/api/images'
import { createVideoTask } from '@/api/videos'
import { getPreset } from '@/api/presets'
import { CHAT_TOOLS } from '../chat-tools'
import { AgentKernel } from '../kernel'
import { createFakeStreamFn, fakeModel } from './fake-llm'

const imageTool = CHAT_TOOLS[0]
const videoTool = CHAT_TOOLS[1]
const skillTool = CHAT_TOOLS[2]
const saveSkillTool = CHAT_TOOLS[3]

function imageResp(taskId = 'img_1') {
  return { task_id: taskId, status: 'pending' }
}

beforeEach(() => {
  vi.mocked(createImageTask).mockReset().mockResolvedValue(imageResp())
  vi.mocked(createVideoTask).mockReset().mockResolvedValue({
    task_id: 'vid_1', video_id: null, status: 'pending', prompt: '',
  } as never)
  vi.mocked(getPreset).mockReset()
  mocks.registerChatTask.mockReset()
})

describe('generate_image', () => {
  it('text2image：参数装配 + 队列注册，不带参考图', async () => {
    const r = await imageTool.execute({ prompt: 'a cat', size: '1024x768', camera_params: { enabled: true, camera_model: 'FX3' } }, null)
    expect(r.ok).toBe(true)
    expect(r.data).toMatchObject({ task_id: 'img_1', media_type: 'image', status: 'pending' })
    expect(vi.mocked(createImageTask)).toHaveBeenCalledWith(expect.objectContaining({
      prompt: 'a cat',
      model: 'img-x',
      size: '1024x768',
      mode: 'text2image',
      camera_params: { enabled: true, camera_model: 'FX3' },
    }))
    const params = vi.mocked(createImageTask).mock.calls[0][0]
    expect(params.image_urls).toBeUndefined()
    expect(mocks.registerChatTask).toHaveBeenCalledWith(expect.objectContaining({ taskId: 'img_1', type: 'image' }))
  })

  it('image2image：参考图来自 ctx 最近生成图；无参考图时给出引导性报错', async () => {
    const ctx = { getRecentMediaUrl: (t: string) => (t === 'image' ? 'https://cdn/x.png' : null) }
    await imageTool.execute({ prompt: '改颜色', mode: 'image2image' }, ctx)
    expect(vi.mocked(createImageTask).mock.calls[0][0].image_urls).toEqual(['https://cdn/x.png'])

    const r = await imageTool.execute({ prompt: '改颜色', mode: 'image2image' }, null)
    expect(r.ok).toBe(false)
    expect(r.error).toContain('没有可用的参考图')
  })

  it('preset_ref：预设 prompt_text 合并在前', async () => {
    vi.mocked(getPreset).mockResolvedValue({ id: 9, name: '水墨', prompt_text: '水墨风格指令' } as never)
    await imageTool.execute({ prompt: 'a cat', preset_ref: 9 }, null)
    expect(vi.mocked(createImageTask).mock.calls[0][0].prompt).toBe('水墨风格指令\n\na cat')
  })

  it('缺提示词报错', async () => {
    const r = await imageTool.execute({}, null)
    expect(r.ok).toBe(false)
  })
})

describe('generate_video', () => {
  it('text2video：默认 81 帧 + 默认视频模型', async () => {
    const r = await videoTool.execute({ prompt: 'a dog runs' }, null)
    expect(r.ok).toBe(true)
    expect(r.data).toMatchObject({ task_id: 'vid_1', media_type: 'video' })
    expect(vi.mocked(createVideoTask)).toHaveBeenCalledWith(expect.objectContaining({
      prompt: 'a dog runs',
      model: 'vid-x',
      num_frames: 81,
      mode: 'text2video',
    }))
  })

  it('image2video：参考图注入 image 字段', async () => {
    const ctx = { getRecentMediaUrl: (t: string) => (t === 'image' ? 'https://cdn/x.png' : null) }
    await videoTool.execute({ prompt: '让它动起来', mode: 'image2video' }, ctx)
    expect(vi.mocked(createVideoTask).mock.calls[0][0].image).toBe('https://cdn/x.png')
  })
})

describe('agent_load_skill / agent_read_skill_file', () => {
  it('load_skill 命中回传 loadAgentSkillFull 结果，未命中转 ok:false', async () => {
    const { loadAgentSkillFull } = await import('../skills')
    vi.mocked(loadAgentSkillFull).mockResolvedValueOnce({ name: '分镜节奏', description: 'x', content: '正文+资源清单' })
    const ok = await skillTool.execute({ name: '分镜节奏' }, null)
    expect(ok.ok).toBe(true)
    expect(ok.data).toMatchObject({ content: '正文+资源清单' })

    vi.mocked(loadAgentSkillFull).mockRejectedValueOnce(new Error('技能「不存在」不存在。可用技能：分镜节奏'))
    const miss = await skillTool.execute({ name: '不存在' }, null)
    expect(miss.ok).toBe(false)
    expect(miss.error).toContain('分镜节奏')
  })

  it('read_skill_file：回传资源原文，抛错转 ok:false', async () => {
    const { readSkillResource } = await import('../skills')
    const readFileTool = CHAT_TOOLS[4]
    expect(readFileTool.name).toBe('agent_read_skill_file')
    vi.mocked(readSkillResource).mockResolvedValueOnce({ path: 'references/x.md', content: '参考内容' })
    const ok = await readFileTool.execute({ skill: '分镜节奏', path: 'references/x.md' }, null)
    expect(ok.ok).toBe(true)
    expect(ok.data).toEqual({ path: 'references/x.md', content: '参考内容' })

    vi.mocked(readSkillResource).mockRejectedValueOnce(new Error('资源「nope」不存在'))
    const bad = await readFileTool.execute({ skill: '分镜节奏', path: 'nope' }, null)
    expect(bad.ok).toBe(false)
    expect(bad.error).toContain('不存在')
  })
})

describe('内核宿主工具组注入（无阶段门路径）', () => {
  it('deps.tools 生效且 ctx 透传，无确认卡片', async () => {
    const script = [
      { toolCalls: [{ id: 't1', name: 'echo', args: { v: 1 } }] },
      { text: 'done' },
    ]
    const fake = createFakeStreamFn(script as never[])
    const seenCtx: unknown[] = []
    const kernel = new AgentKernel({
      systemPrompt: 'test',
      getAuthToken: async () => null,
      streamFn: fake.streamFn,
      tools: [{
        name: 'echo',
        description: 'echo',
        parameters: { type: 'object', properties: {} },
        execute: async (args, ctx) => {
          seenCtx.push(ctx)
          return { ok: true, data: args }
        },
      }],
      toolContext: { marker: 'chat-ctx' },
    })
    // 走完一轮：模型先调工具再回复（fake 流需真实 model 形状）
    kernel.setModel(fakeModel)
    const events: string[] = []
    kernel.subscribe((e) => events.push(e.type))
    await kernel.send('hi')
    expect(seenCtx).toEqual([{ marker: 'chat-ctx' }])
    expect(events).toContain('done')
    expect(events).not.toContain('confirm_request')
  })
})

describe('agent_save_skill', () => {
  it('执行器透传参数，成功返回 name/tag', async () => {
    const { saveAgentSkill } = await import('../skills')
    vi.mocked(saveAgentSkill).mockResolvedValueOnce({ name: '台词师', tag: '台词' })
    const ok = await saveSkillTool.execute({ name: '台词师', description: 'd', content: 'c', tag: '台词' }, null)
    expect(ok.ok).toBe(true)
    expect(ok.data).toMatchObject({ name: '台词师', tag: '台词' })
    expect(vi.mocked(saveAgentSkill)).toHaveBeenCalledWith(expect.objectContaining({ name: '台词师', tag: '台词' }))
  })

  it('saveAgentSkill 抛错转 ok:false', async () => {
    const { saveAgentSkill } = await import('../skills')
    vi.mocked(saveAgentSkill).mockRejectedValueOnce(new Error('同名技能已存在：「X」'))
    const bad = await saveSkillTool.execute({ name: 'X', description: 'd', content: 'c' }, null)
    expect(bad.ok).toBe(false)
    expect(bad.error).toContain('同名技能已存在')
  })
})
