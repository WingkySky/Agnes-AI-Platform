/* =====================================================
 * 声明式 HTTP 渠道（provider_type=http_custom）配置层纯函数
 * 表单状态 ⇄ 后端 http_config JSON 双向转换 + AI 生成输出解析
 * ===================================================== */

export type HttpModelsMode = 'static' | 'openai' | 'custom'

export interface HttpActionForm {
  path: string
  method: string
  body: string
  headers: string
  timeout_sec: number
  url_path?: string
  b64_path?: string
  task_id_path?: string
  video_id_path?: string
  status_path?: string
  status_map?: string
  video_url_path?: string
  progress_path?: string
  error_path?: string
}

export interface HttpFormState {
  models_mode: HttpModelsMode
  static_models: string
  models_path: string
  image_create: HttpActionForm
  video_create: HttpActionForm
  video_poll: HttpActionForm
}

/** 后端 schemas/providers.py HttpConfigModel 的占位符与映射说明（AI 生成 system prompt 用） */
export const HTTP_CONFIG_PROMPT_DOC = `输出一个 JSON 对象（http_config），字段：
{
  "models_mode": "static | openai | custom",   // 模型目录：static=静态列表；openai=GET {base}/models；custom=自定义端点
  "static_models": [{"id": "模型ID", "type": "image|video"}],   // 仅 static 模式
  "models_endpoint": {"path": "/xxx", "method": "GET"},          // 仅 custom 模式
  "image_create": {                                              // 同步图片（可选，无图片能力则省略）
    "path": "/v1/images/generations", "method": "POST",
    "body": "{\\"model\\": \\"{{model}}\\", \\"prompt\\": \\"{{prompt}}\\", \\"size\\": \\"{{size}}\\"}",
    "url_path": "data.0.url",         // 响应中图片 URL 的点路径
    "b64_path": "data.0.b64_json",    // 响应中 base64 的点路径（可选）
    "timeout_sec": 300
  },
  "video_create": {                                              // 视频提交（可选）
    "path": "...", "method": "POST", "body": "...",
    "task_id_path": "data.task_id",   // 响应中任务 ID 点路径
    "video_id_path": "",              // 视频 ID 点路径（与 task_id 至少一个）
    "timeout_sec": 60
  },
  "video_poll": {                                                // 视频轮询（与 video_create 成对出现）
    "path": "/status?task_id={{task_id}}", "method": "GET",
    "status_path": "status",
    "status_map": {"上游状态值": "success|processing|failed|cancelled"},
    "video_url_path": "data.video_url", "progress_path": "progress", "error_path": "message",
    "timeout_sec": 15
  }
}
占位符：图片 {{prompt}} {{model}} {{size}} {{image}} {{images}}；视频 {{prompt}} {{model}} {{width}} {{height}} {{seconds}} {{aspect_ratio}} {{image}} {{images}} {{negative_prompt}}；轮询路径 {{task_id}}。字符串占位在模板中带引号、数组占位不带引号。`

/** 空表单（新建声明式渠道的默认值） */
export function emptyHttpForm(): HttpFormState {
  return {
    models_mode: 'openai',
    static_models: '',
    models_path: '',
    image_create: { path: '', method: 'POST', body: '', headers: '', timeout_sec: 300, url_path: 'data.0.url', b64_path: 'data.0.b64_json' },
    video_create: { path: '', method: 'POST', body: '', headers: '', timeout_sec: 60, task_id_path: 'data.task_id', video_id_path: '' },
    video_poll: { path: '', method: 'GET', body: '', headers: '', timeout_sec: 15, status_path: 'status', status_map: '', video_url_path: 'data.video_url', progress_path: 'data.progress', error_path: 'message' },
  }
}

function parseJsonField(raw: string): { value?: unknown; error?: string } {
  const trimmed = (raw || '').trim()
  if (!trimmed) return { value: undefined }
  try {
    return { value: JSON.parse(trimmed) }
  } catch {
    return { error: '不是合法 JSON' }
  }
}

function actionFromConfig(action: unknown): HttpActionForm {
  const a = (action || {}) as Record<string, unknown>
  return {
    path: (a.path as string) || '',
    method: (a.method as string) || 'POST',
    body: (a.body as string) || '',
    headers: a.headers && Object.keys(a.headers as object).length ? JSON.stringify(a.headers, null, 2) : '',
    timeout_sec: (a.timeout_sec as number) || 60,
    url_path: (a.url_path as string) || '',
    b64_path: (a.b64_path as string) || '',
    task_id_path: (a.task_id_path as string) || '',
    video_id_path: (a.video_id_path as string) || '',
    status_path: (a.status_path as string) || '',
    status_map: a.status_map && Object.keys(a.status_map as object).length ? JSON.stringify(a.status_map, null, 2) : '',
    video_url_path: (a.video_url_path as string) || '',
    progress_path: (a.progress_path as string) || '',
    error_path: (a.error_path as string) || '',
  }
}

/** 后端 http_config → 表单（编辑回填） */
export function formFromHttpConfig(cfg: Record<string, unknown> | null | undefined): HttpFormState {
  const form = emptyHttpForm()
  if (!cfg) return form
  form.models_mode = (cfg.models_mode as HttpModelsMode) || 'openai'
  if (Array.isArray(cfg.static_models)) {
    form.static_models = JSON.stringify(cfg.static_models, null, 2)
  }
  const endpoint = cfg.models_endpoint as Record<string, unknown> | undefined
  form.models_path = (endpoint?.path as string) || ''
  form.image_create = actionFromConfig(cfg.image_create)
  form.video_create = actionFromConfig(cfg.video_create)
  form.video_poll = actionFromConfig(cfg.video_poll)
  return form
}

function buildAction(form: HttpActionForm, extra: Record<string, unknown>): Record<string, unknown> | null {
  if (!form.path.trim()) return null
  const action: Record<string, unknown> = {
    path: form.path.trim(),
    method: form.method || 'POST',
    timeout_sec: form.timeout_sec || 60,
    ...extra,
  }
  const headers = parseJsonField(form.headers)
  if (headers.error) throw new Error(`额外请求头${headers.error}`)
  if (headers.value && Object.keys(headers.value as object).length) action.headers = headers.value
  return action
}

/**
 * 表单 → 后端 http_config 载荷。返回 { config } 或 { error }（错误文案可直接提示）。
 * path 为空的动作不纳入；至少需要一组动作，否则 error。
 */
export function buildHttpConfigPayload(form: HttpFormState): { config?: Record<string, unknown>; error?: string } {
  const config: Record<string, unknown> = { models_mode: form.models_mode }
  try {
    if (form.models_mode === 'static') {
      const parsed = parseJsonField(form.static_models)
      if (parsed.error) return { error: `静态模型目录${parsed.error}` }
      if (!Array.isArray(parsed.value)) return { error: '静态模型目录必须是数组，如 [{"id": "model-id", "type": "image"}]' }
      config.static_models = parsed.value
    } else if (form.models_mode === 'custom') {
      if (!form.models_path.trim()) return { error: '自定义模型目录端点未填写' }
      config.models_endpoint = { path: form.models_path.trim(), method: 'GET' }
    }

    const image = buildAction(form.image_create, {
      body: form.image_create.body,
      url_path: (form.image_create.url_path || '').trim(),
      b64_path: (form.image_create.b64_path || '').trim(),
    })
    if (image && !form.image_create.body.trim()) return { error: '图片创建请求体模板未填写' }
    if (image) config.image_create = image

    const videoCreate = buildAction(form.video_create, {
      body: form.video_create.body,
      task_id_path: (form.video_create.task_id_path || '').trim(),
      video_id_path: (form.video_create.video_id_path || '').trim(),
    })
    const videoPoll = buildAction(form.video_poll, {
      status_path: (form.video_poll.status_path || '').trim(),
      video_url_path: (form.video_poll.video_url_path || '').trim(),
      progress_path: (form.video_poll.progress_path || '').trim(),
      error_path: (form.video_poll.error_path || '').trim(),
    })
    if (videoCreate) {
      if (!form.video_create.body.trim()) return { error: '视频提交请求体模板未填写' }
      if (!videoPoll) return { error: '视频为两段式：填写了提交模板但未填写轮询模板' }
      const statusMap = parseJsonField(form.video_poll.status_map || '')
      if (statusMap.error) return { error: `状态映射${statusMap.error}` }
      if (!statusMap.value || !Object.keys(statusMap.value as object).length) return { error: '视频轮询状态映射不能为空' }
      videoPoll.status_map = statusMap.value
      config.video_create = videoCreate
      config.video_poll = videoPoll
    } else if (videoPoll) {
      return { error: '视频为两段式：填写了轮询模板但未填写提交模板' }
    }

    if (!config.image_create && !config.video_create) {
      return { error: '至少配置图片创建或视频提交模板之一' }
    }
    return { config }
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) }
  }
}

/** 剥离 LLM 输出中的 markdown 代码围栏 */
export function stripCodeFence(text: string): string {
  const trimmed = (text || '').trim()
  const fenced = trimmed.match(/^```(?:json)?\s*\n([\s\S]*?)\n\s*```$/)
  return (fenced ? fenced[1] : trimmed).trim()
}

/** AI 生成输出 → http_config JSON（剥围栏 + 提取首个 JSON 对象 + 轻校验） */
export function parseHttpConfigFromAI(text: string): { config?: Record<string, unknown>; error?: string } {
  const stripped = stripCodeFence(text)
  const start = stripped.indexOf('{')
  if (start < 0) return { error: '输出中未找到 JSON 对象' }
  // 从第一个 { 起做括号配对截取（容忍模型在 JSON 后补说明文字）
  let depth = 0
  let inString = false
  let escape = false
  for (let i = start; i < stripped.length; i++) {
    const ch = stripped[i]
    if (escape) { escape = false; continue }
    if (ch === '\\') { escape = true; continue }
    if (ch === '"') { inString = !inString; continue }
    if (inString) continue
    if (ch === '{') depth++
    if (ch === '}') {
      depth--
      if (depth === 0) {
        try {
          const config = JSON.parse(stripped.slice(start, i + 1))
          if (typeof config !== 'object' || config === null || Array.isArray(config)) {
            return { error: '解析结果不是 JSON 对象' }
          }
          const c = config as Record<string, unknown>
          if (!['static', 'openai', 'custom'].includes(String(c.models_mode || 'openai'))) {
            return { error: 'models_mode 缺失或非法' }
          }
          if (!c.image_create && !c.video_create) return { error: '缺少 image_create 或 video_create 模板' }
          return { config: c }
        } catch {
          return { error: '输出不是合法 JSON（可重试生成或手动修正）' }
        }
      }
    }
  }
  return { error: 'JSON 对象不完整（括号未闭合）' }
}
