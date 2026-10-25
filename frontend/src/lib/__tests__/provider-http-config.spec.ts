// 声明式 HTTP 渠道配置层纯函数测试
import { describe, expect, it } from 'vitest'
import {
  buildHttpConfigPayload,
  emptyHttpForm,
  formFromHttpConfig,
  parseHttpConfigFromAI,
  stripCodeFence,
} from '../provider-http-config'

describe('formFromHttpConfig / buildHttpConfigPayload 往返', () => {
  it('后端配置回填表单再构建，还原等价载荷', () => {
    const backend = {
      models_mode: 'static',
      static_models: [{ id: 'm1', type: 'image' }],
      image_create: {
        path: '/img', method: 'POST',
        body: '{"prompt": "{{prompt}}"}',
        url_path: 'data.0.url', b64_path: 'data.0.b64_json', timeout_sec: 300,
        headers: { 'X-K': 'v' },
      },
      video_create: { path: '/v', method: 'POST', body: '{}', task_id_path: 'id', video_id_path: '', timeout_sec: 60 },
      video_poll: {
        path: '/p', method: 'GET', status_path: 's',
        status_map: { OK: 'success' },
        video_url_path: 'u', progress_path: 'p', error_path: 'e', timeout_sec: 15,
      },
    }
    const form = formFromHttpConfig(backend)
    expect(form.models_mode).toBe('static')
    expect(JSON.parse(form.static_models)).toEqual([{ id: 'm1', type: 'image' }])
    expect(form.video_poll.status_map).toContain('"OK"')

    const { config, error } = buildHttpConfigPayload(form)
    expect(error).toBeUndefined()
    expect(config).toEqual(backend)
  })

  it('path 为空的动作不纳入载荷', () => {
    const form = emptyHttpForm()
    form.models_mode = 'openai'
    form.image_create.path = '/img'
    form.image_create.body = '{"p": "{{prompt}}"}'
    const { config, error } = buildHttpConfigPayload(form)
    expect(error).toBeUndefined()
    expect(config?.image_create).toBeTruthy()
    expect(config?.video_create).toBeUndefined()
  })

  it('非法 static_models JSON 报错', () => {
    const form = emptyHttpForm()
    form.models_mode = 'static'
    form.static_models = 'not-json'
    form.image_create.path = '/img'
    form.image_create.body = '{}'
    const { error } = buildHttpConfigPayload(form)
    expect(error).toContain('JSON')
  })

  it('video_poll 有但 video_create 无 → 报两段式错误', () => {
    const form = emptyHttpForm()
    form.image_create.path = '/img'
    form.image_create.body = '{}'
    form.video_poll.path = '/p'
    form.video_poll.status_path = 's'
    form.video_poll.status_map = '{"X": "processing"}'
    const { error } = buildHttpConfigPayload(form)
    expect(error).toContain('两段式')
  })

  it('无任何动作 → 报至少一组', () => {
    const { error } = buildHttpConfigPayload(emptyHttpForm())
    expect(error).toContain('至少')
  })
})

describe('parseHttpConfigFromAI', () => {
  const validConfig = '{"models_mode": "openai", "image_create": {"path": "/img", "body": "{}", "url_path": "u"}}'

  it('剥离代码围栏并解析', () => {
    const { config, error } = parseHttpConfigFromAI('```json\n' + validConfig + '\n```')
    expect(error).toBeUndefined()
    expect(config?.image_create).toBeTruthy()
  })

  it('容忍 JSON 后附带的说明文字（括号配对截取）', () => {
    const { config, error } = parseHttpConfigFromAI(validConfig + '\n以上是配置。')
    expect(error).toBeUndefined()
    expect((config as Record<string, unknown>).models_mode).toBe('openai')
  })

  it('缺少动作模板报错', () => {
    const { error } = parseHttpConfigFromAI('{"models_mode": "openai"}')
    expect(error).toContain('image_create')
  })

  it('非 JSON 输出报错', () => {
    const { error } = parseHttpConfigFromAI('抱歉，我无法完成该任务。')
    expect(error).toBeTruthy()
  })
})

describe('stripCodeFence', () => {
  it('剥离 json 围栏', () => {
    expect(stripCodeFence('```json\n{"a":1}\n```')).toBe('{"a":1}')
  })
  it('无围栏原样返回', () => {
    expect(stripCodeFence('{"a":1}')).toBe('{"a":1}')
  })
})
