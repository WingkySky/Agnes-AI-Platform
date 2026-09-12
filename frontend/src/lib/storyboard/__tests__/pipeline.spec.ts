/* 分镜管线模块单测：SSE transport 解析、实体提取/分镜拆分/一枪出、成品提示词拼装 */

import { describe, it, expect, vi } from 'vitest'
import { sseChatComplete } from '../transport'
import {
  extractEntities, splitStoryboard, planStoryboard, buildFramePrompt,
  generateScript, extractProjectEntities,
} from '../pipeline'
import { parseEntities, parseShot, parseStyleConfig, extractJsonText, EMPTY_STYLE } from '../schemas'
import { SINGLE_FRAME_PROMPT_LINE, buildAssetPrompt, scriptPrompt, fillTemplate } from '../prompts'
import type { StoryboardEntity, StyleConfig } from '../schemas'

/** SSE 逐帧响应流 */
function sseResponse(chunks: unknown[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(c)}\n\n`))
      }
      controller.enqueue(encoder.encode('data: [DONE]\n\n'))
      controller.close()
    },
  })
  return new Response(stream, { status: 200 })
}

describe('sseChatComplete', () => {
  it('跨 chunk 累积增量文本并在 [DONE] 收尾', async () => {
    const fetchMock = vi.fn(async (_url: string | URL, _init?: RequestInit) =>
      sseResponse([
        { choices: [{ delta: { content: '第一段' } }] },
        { choices: [{ delta: { content: '第二段' } }] },
        { choices: [{ delta: {} } ] },
      ]),
    )
    vi.stubGlobal('fetch', fetchMock)
    const text = await sseChatComplete([{ role: 'user', content: 'hi' }])
    expect(text).toBe('第一段第二段')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/chat/completions')
    const body = JSON.parse(String(init?.body))
    expect(body.stream).toBe(true)
    vi.unstubAllGlobals()
  })

  it('HTTP 错误抛错', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('boom', { status: 502 })))
    await expect(sseChatComplete([{ role: 'user', content: 'hi' }])).rejects.toThrow('502')
    vi.unstubAllGlobals()
  })
})

describe('schemas 解析容错', () => {
  it('extractJsonText 剥代码栅栏', () => {
    expect(extractJsonText('前言```json\n{"a":1}\n```后记')).toBe('{"a":1}')
    expect(extractJsonText('{"a":1}')).toBe('{"a":1}')
  })

  it('parseEntities 跳过无名条目、读取参考图', () => {
    const list = parseEntities(
      { characters: [{ name: ' 林小满 ', description: '红衣少女' }, { description: '无名' }, { name: '图图', ref_image_url: 'http://x/1.png' }] },
      'character',
    )
    expect(list).toHaveLength(2)
    expect(list[0].name).toBe('林小满')
    expect(list[1].refImageUrl).toBe('http://x/1.png')
  })

  it('parseShot 景别词表外回退中景、序号非法回退', () => {
    const shot = parseShot({ shot_size: '大远景', no: -1, description: '雨夜巷口', characters: ['A'], props: ['伞'], camera: '缓推' }, 3)
    expect(shot.shotSize).toBe('中景')
    expect(shot.no).toBe(3)
    expect(shot.props).toEqual(['伞'])
  })

  it('parseStyleConfig 两种键名等价', () => {
    expect(parseStyleConfig({ prefix: 'a', negative_prompt: 'b' })).toEqual({ prefix: 'a', suffix: '', negativePrompt: 'b' })
    expect(parseStyleConfig(null)).toEqual(EMPTY_STYLE)
  })
})

describe('buildFramePrompt / buildAssetPrompt', () => {
  it('成品提示词含单帧约束、景别运镜、实体上下文', () => {
    const prompt = buildFramePrompt(
      { description: '林小满在雨夜巷口回头', shotSize: '近景', camera: '缓推' },
      { characters: ['林小满：红衣少女'], scenes: ['雨夜巷口：湿漉石板'], props: ['油纸伞：褪色红伞'] },
    )
    expect(prompt).toContain('林小满在雨夜巷口回头')
    expect(prompt).toContain(SINGLE_FRAME_PROMPT_LINE)
    expect(prompt).toContain('景别：近景')
    expect(prompt).toContain('运镜：缓推')
    expect(prompt).toContain('角色设定：林小满：红衣少女')
    expect(prompt).toContain('物品设定：油纸伞：褪色红伞')
    expect(prompt).not.toContain('画面风格')
  })

  it('风格配置注入 prefix/suffix 与避免行；空风格无风格段', () => {
    const style: StyleConfig = { prefix: '赛博朋克', suffix: '霓虹光', negativePrompt: '低质量' }
    const prompt = buildFramePrompt({ description: 'x', shotSize: '', camera: '' }, { characters: [], scenes: [] }, style)
    expect(prompt).toContain('画面风格：赛博朋克，霓虹光')
    expect(prompt).toContain('画面避免：低质量')
    expect(buildAssetPrompt({ kind: 'prop', name: '伞', description: '红伞', refImageUrl: '' }, style)).toContain('画面风格：赛博朋克，霓虹光')
  })

  it('资产图提示词按类别带纯净度约束', () => {
    expect(buildAssetPrompt({ kind: 'character', name: '林小满', description: '红衣少女', refImageUrl: '' })).toContain('三视图')
    expect(buildAssetPrompt({ kind: 'scene', name: '巷口', description: '雨夜', refImageUrl: '' })).toContain('无人物')
    expect(buildAssetPrompt({ kind: 'prop', name: '伞', description: '红伞', refImageUrl: '' })).toContain('物品单体')
  })
})

describe('管线函数（假 transport）', () => {
  const entity: StoryboardEntity = { kind: 'character', name: '林小满', description: '红衣少女', refImageUrl: '' }

  it('extractEntities 解析三类实体', async () => {
    const transport = vi.fn(async () => JSON.stringify({
      characters: [{ name: '林小满', description: '红衣少女' }],
      scenes: [{ name: '巷口', description: '雨夜' }],
      props: [{ name: '油纸伞', description: '褪色红伞' }],
    }))
    const out = await extractEntities('剧本全文', { transport })
    expect(out.characters[0].name).toBe('林小满')
    expect(out.props[0].name).toBe('油纸伞')
  })

  it('splitStoryboard 每镜带成品提示词（风格+命中实体注入）', async () => {
    const transport = vi.fn(async () => JSON.stringify({
      shots: [
        { no: 1, shot_size: '近景', camera: '缓推', location: '巷口', characters: ['林小满'], props: [], description: '雨夜回头', dialogue: '谁？' },
      ],
    }))
    const shots = await splitStoryboard('剧本全文', { characters: [entity], scenes: [{ kind: 'scene', name: '巷口', description: '雨夜', refImageUrl: '' }], props: [] }, { transport, styleConfig: { prefix: '胶片感', suffix: '', negativePrompt: '' } })
    expect(shots).toHaveLength(1)
    expect(shots[0].prompt).toContain(SINGLE_FRAME_PROMPT_LINE)
    expect(shots[0].prompt).toContain('画面风格：胶片感')
    expect(shots[0].prompt).toContain('林小满：红衣少女')
    expect(shots[0].dialogue).toBe('谁？')
  })

  it('planStoryboard 返回资产清单与分镜（给定实体沿用）', async () => {
    const transport = vi.fn(async () => JSON.stringify({
      assets: { characters: [{ name: '林小满', description: '红衣少女' }], scenes: [], props: [] },
      shots: [{ no: 1, shot_size: '中景', camera: '', location: '', characters: ['林小满'], props: [], description: '开场', dialogue: '' }],
    }))
    const out = await planStoryboard('剧本全文', { characters: [entity], transport })
    expect(out.assets.characters[0].name).toBe('林小满')
    expect(out.shots[0].prompt).toContain('林小满：红衣少女')
  })

  it('解析失败重试一次后成功', async () => {
    const transport = vi.fn()
      .mockResolvedValueOnce('不是 JSON')
      .mockResolvedValueOnce(JSON.stringify({ shots: [{ no: 1, description: 'ok', characters: [], props: [] }] }))
    const shots = await splitStoryboard('剧本', { characters: [], scenes: [], props: [] }, { transport })
    expect(shots[0].description).toBe('ok')
    expect(transport).toHaveBeenCalledTimes(2)
  })

  it('两次解析失败抛错', async () => {
    const transport = vi.fn(async () => '不是 JSON')
    await expect(splitStoryboard('剧本', { characters: [], scenes: [], props: [] }, { transport })).rejects.toThrow('分镜管线解析失败')
  })
})

describe('项目制编排（generateScript / extractProjectEntities）', () => {
  it('scriptPrompt 按类别填充占位符，未知 key 原样保留', () => {
    const p = scriptPrompt('drama', { topic: '都市爱情', style: '写实', episodes: 2 })
    expect(p).toContain('主题：都市爱情')
    expect(p).toContain('集数：2 集')
    expect(p).not.toContain('{style}')
    expect(fillTemplate('你好 {name} / {missing}', { name: '小明' })).toBe('你好 小明 / {missing}')
  })

  it('generateScript 返回非空文本；空结果抛错', async () => {
    const ok = await generateScript('ad', { product: '手机' }, { transport: async () => '  剧本正文  ' })
    expect(ok).toBe('剧本正文')
    await expect(
      generateScript('ad', {}, { transport: async () => '  ' }),
    ).rejects.toThrow('剧本生成结果为空')
  })

  it('extractProjectEntities 解析项目字段（缺省回退对齐后端列默认值）', async () => {
    const transport = vi.fn(async () => JSON.stringify({
      characters: [{ name: '林小满', description: '红衣少女', appearance_desc: '红裙', role_type: 'main' }],
      scenes: [{ name: '巷口', description: '雨夜' }],
      props: [{ name: '油纸伞', visual_desc: '褪色红伞' }, { description: '无名跳过' }],
    }))
    const out = await extractProjectEntities('剧本全文', { transport })
    expect(out.characters[0]).toEqual({ name: '林小满', description: '红衣少女', appearanceDesc: '红裙', roleType: 'main', location: '', timeOfDay: '', atmosphere: '', visualDesc: '' })
    expect(out.scenes[0].roleType).toBe('supporting')
    expect(out.props).toHaveLength(1)
    expect(out.props[0].visualDesc).toBe('褪色红伞')
  })

  it('extractProjectEntities 解析失败重试后成功', async () => {
    const transport = vi.fn().mockResolvedValueOnce('不是 JSON').mockResolvedValueOnce(JSON.stringify({ characters: [{ name: 'A' }] }))
    const out = await extractProjectEntities('剧本', { transport })
    expect(out.characters[0].name).toBe('A')
    expect(transport).toHaveBeenCalledTimes(2)
  })
})
