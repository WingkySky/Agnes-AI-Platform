/* =====================================================
 * 对话页宿主工具组（三期内核统一，UI 无关）
 *
 * - generate_image / generate_video：前端提交生成任务（images/videos tasks
 *   端点自带积分扣减，画布生成同链路已验证）→ 注册 taskQueue → 立即返回
 *   pending（不阻塞回合）；媒体占位/轮询/media-callback 回写由 chat store
 *   沿用既有机制，工具不等待
 * - 参考图解析经 ChatToolContext（chat store 提供最近成功生成的媒体）
 * - agent_load_skill 复用 skills 模块缓存（与画布同款渐进披露）
 * ===================================================== */

import { Type } from 'typebox'
import { createImageTask } from '@/api/images'
import { createVideoTask } from '@/api/videos'
import { getPreset } from '@/api/presets'
import { useTaskQueueStore } from '@/stores/taskQueue'
import { useModelsStore } from '@/stores/models'
import type { ImageGenerationRequest, VideoGenerationRequest } from '@/types'
import type { AgentToolResult } from './tools'
import { loadAgentSkillFull, readSkillResource, saveAgentSkill, SKILL_CONTENT_MAX_CHARS } from './skills'

/** chat 工具执行上下文（chat store 提供）：会话连续性所需的媒体状态 */
export interface ChatToolContext {
  /** 最近一次成功生成的媒体 URL（图生图/图生视频默认参考） */
  getRecentMediaUrl(type: 'image' | 'video'): string | null
}

function isChatCtx(ctx: unknown): ctx is ChatToolContext {
  return typeof ctx === 'object' && ctx !== null && 'getRecentMediaUrl' in ctx
}

function recentMediaUrl(ctx: unknown, type: 'image' | 'video'): string | null {
  return isChatCtx(ctx) ? ctx.getRecentMediaUrl(type) : null
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

/**
 * 预设合并（对齐后端 _execute_tool 语义）：preset_ref 有效时拉取预设，
 * prompt_text 合并进提示词（预设在前、模型补充在后）；拉取失败按原提示词继续
 */
async function promptWithPreset(prompt: string, args: Record<string, unknown>): Promise<string> {
  const presetRef = args.preset_ref
  if (typeof presetRef !== 'number' || !Number.isFinite(presetRef)) return prompt
  try {
    const preset = await getPreset(presetRef)
    if (preset.prompt_text) return `${preset.prompt_text}\n\n${prompt}`
  } catch {
    // 预设拉取失败不阻断生成
  }
  return prompt
}

/** camera_params 守卫提取：enabled=true 才透传 */
function cameraParamsOf(args: Record<string, unknown>): Record<string, unknown> | null {
  const cp = args.camera_params
  if (!isRecord(cp) || cp.enabled !== true) return null
  return cp
}

/** 注册到全局任务队列（仅展示；轮询由 chat store 负责） */
function registerGenerationTask(taskId: string, type: 'image' | 'video', prompt: string): void {
  try {
    useTaskQueueStore().registerChatTask({
      taskId,
      type,
      prompt,
      resultUrl: null,
      backendTaskId: taskId,
    })
  } catch {
    // 队列不可用不阻断生成
  }
}

// ---------- generate_image ----------

const imageTool = {
  name: 'generate_image',
  description:
    '当用户明确要求生成、创建、绘制图片时调用此工具。' +
    '用户可能说"帮我画一张图"、"生成一张风景图"、"画一个猫咪"等。' +
    '请将用户的描述转化为详细的英文图片提示词。' +
    '注意：用户上传图片或提供图片链接不代表要生成图片，只有用户明确使用"生成"、"画"、"创建"等动作词时才调用。' +
    '如果用户提供了参考图且明确要求基于参考图生成，将 mode 设置为 "image2image"。' +
    '如果用户明确说"忽略图片，直接画图"，请将 use_reference_image 设置为 false。',
  parameters: Type.Object({
    prompt: Type.String({ description: '图片生成的英文提示词，需要详细描述主体、场景、风格、光照、构图等' }),
    size: Type.Optional(Type.Union([
      Type.Literal('1024x1024'),
      Type.Literal('1024x768'),
      Type.Literal('768x1024'),
    ], { description: '图片尺寸，默认 1024x1024' })),
    mode: Type.Optional(Type.Union([
      Type.Literal('text2image'),
      Type.Literal('image2image'),
    ], { description: '生成模式：text2image（纯文生图）或 image2image（基于参考图）' })),
    use_reference_image: Type.Optional(Type.Boolean({ description: '是否使用参考图（有参考图时默认 true；用户明确说忽略则设为 false）' })),
    camera_params: Type.Optional(Type.Object({
      enabled: Type.Boolean({ description: '是否启用摄像机参数' }),
      camera_model: Type.Optional(Type.String()),
      focal_length: Type.Optional(Type.String()),
      aperture: Type.Optional(Type.String()),
      depth_of_field: Type.Optional(Type.String()),
      shutter_speed: Type.Optional(Type.String()),
      shutter_angle: Type.Optional(Type.String()),
      camera_movement: Type.Optional(Type.String()),
      camera_angle: Type.Optional(Type.String()),
      aspect_ratio: Type.Optional(Type.String()),
      visual_style: Type.Optional(Type.String()),
    }, { description: '摄像机参数（可选），用户提到镜头/运镜/画幅相关描述时填充' })),
    preset_ref: Type.Optional(Type.Number({ description: '预设 ID（用户按名称引用预设时传入；不确定则省略）' })),
  }),
  execute: async (args: Record<string, unknown>, ctx: unknown): Promise<AgentToolResult> => {
    const rawPrompt = typeof args.prompt === 'string' ? args.prompt.trim() : ''
    if (!rawPrompt) return { ok: false, error: '缺少图片生成提示词' }
    const prompt = await promptWithPreset(rawPrompt, args)
    const size = typeof args.size === 'string' ? args.size : '1024x1024'
    const mode = args.mode === 'image2image' ? 'image2image' : 'text2image'
    const ms = useModelsStore()
    const params: ImageGenerationRequest = {
      prompt,
      model: ms.getDefaultModel('image'),
      size,
      response_format: 'url',
      mode,
      camera_params: cameraParamsOf(args),
    }
    if (mode === 'image2image' && args.use_reference_image !== false) {
      const ref = recentMediaUrl(ctx, 'image')
      if (!ref) return { ok: false, error: '没有可用的参考图：会话中还没有成功生成过图片，请改用 text2image 或让用户上传图片' }
      params.image_urls = [ref]
    }
    try {
      const resp = await createImageTask(params)
      registerGenerationTask(resp.task_id, 'image', prompt)
      return {
        ok: true,
        data: {
          task_id: resp.task_id,
          media_type: 'image',
          status: 'pending',
          message: '图片生成任务已提交，完成后会自动展示给用户，不要在回复中输出任何图片链接',
        },
      }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  },
}

// ---------- generate_video ----------

const videoTool = {
  name: 'generate_video',
  description:
    '当用户明确要求生成、创建视频时调用此工具。' +
    '用户可能说"帮我生成一段视频"、"创建一个短视频"、"做个视频"等。' +
    '请将用户的描述转化为详细的英文视频提示词。' +
    '注意：用户上传图片或提供图片链接不代表要生成视频，只有用户明确使用"生成"、"创建"等动作词时才调用。' +
    '如果用户提供了 1 张参考图且明确要求生成视频，将 mode 设置为 "image2video"；' +
    '如果用户提供了 2 张或多张参考图且明确要求生成视频，将 mode 设置为 "keyframes" 以制作过渡动画。',
  parameters: Type.Object({
    prompt: Type.String({ description: '视频生成的英文提示词，需要详细描述主体、动作、场景、镜头运动、光照、风格等' }),
    num_frames: Type.Optional(Type.Union([
      Type.Literal(81),
      Type.Literal(121),
      Type.Literal(161),
      Type.Literal(241),
      Type.Literal(441),
    ], { description: '视频总帧数，必须满足 8n+1（如 81 约3秒, 121 约5秒, 241 约10秒），默认 81' })),
    mode: Type.Optional(Type.Union([
      Type.Literal('text2video'),
      Type.Literal('image2video'),
      Type.Literal('keyframes'),
      Type.Literal('video2video'),
    ], { description: '生成模式：text2video / image2video（单参考图）/ keyframes（多参考图过渡）/ video2video' })),
    reference_videos: Type.Optional(Type.Array(Type.String(), { description: '参考视频 URL 列表（video2video 模式，最多 5 个）' })),
    reference_audios: Type.Optional(Type.Array(Type.String(), { description: '参考音频 URL 列表（可选，video2video 模式）' })),
    camera_params: Type.Optional(Type.Object({
      enabled: Type.Boolean({ description: '是否启用摄像机参数' }),
    }, { description: '摄像机参数（可选），用户提到镜头/运镜相关描述时填充' })),
    preset_ref: Type.Optional(Type.Number({ description: '预设 ID（用户按名称引用预设时传入；不确定则省略）' })),
  }),
  execute: async (args: Record<string, unknown>, ctx: unknown): Promise<AgentToolResult> => {
    const rawPrompt = typeof args.prompt === 'string' ? args.prompt.trim() : ''
    if (!rawPrompt) return { ok: false, error: '缺少视频生成提示词' }
    const prompt = await promptWithPreset(rawPrompt, args)
    const numFrames = typeof args.num_frames === 'number' ? args.num_frames : 81
    let mode: VideoGenerationRequest['mode'] = 'text2video'
    switch (args.mode) {
      case 'image2video':
      case 'keyframes':
      case 'video2video':
        mode = args.mode
        break
    }
    const ms = useModelsStore()
    const params: VideoGenerationRequest = {
      prompt,
      model: ms.getDefaultModel('video'),
      num_frames: numFrames,
      mode,
      camera_params: cameraParamsOf(args),
    }
    if (mode === 'image2video' || mode === 'keyframes') {
      const ref = recentMediaUrl(ctx, 'image')
      if (!ref) return { ok: false, error: '没有可用的参考图：会话中还没有成功生成过图片，请先文生视频或让用户提供图片' }
      if (mode === 'image2video') {
        params.image = ref
      } else {
        params.images = [ref]
      }
    }
    if (mode === 'video2video' && Array.isArray(args.reference_videos)) {
      params.reference_videos = args.reference_videos.filter((v): v is string => typeof v === 'string').slice(0, 5)
    }
    if (mode === 'video2video' && Array.isArray(args.reference_audios)) {
      params.reference_audios = args.reference_audios.filter((v): v is string => typeof v === 'string')
    }
    try {
      const resp = await createVideoTask(params)
      const taskId = resp.task_id || resp.video_id || ''
      if (!taskId) return { ok: false, error: '视频任务创建失败：服务端未返回任务 ID' }
      registerGenerationTask(taskId, 'video', prompt)
      return {
        ok: true,
        data: {
          task_id: taskId,
          media_type: 'video',
          status: 'pending',
          message: '视频生成任务已提交（通常需要 1-3 分钟），完成后自动展示，不要在回复中输出任何视频链接',
        },
      }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  },
}

// ---------- agent_load_skill ----------

const loadSkillTool = {
  name: 'agent_load_skill',
  description: '加载技能全文。当用户消息带【使用技能：名称】标记，或任务与可用技能清单中某技能高度相关时调用，把技能方法论注入你的工作上下文。结果含附件资源清单，需要时用 agent_read_skill_file 按需读取（脚本只存档，不会被执行）。',
  parameters: Type.Object({
    name: Type.String({ description: '技能名称（来自可用技能清单）' }),
  }),
  execute: async (args: Record<string, unknown>): Promise<AgentToolResult> => {
    const name = typeof args.name === 'string' ? args.name.trim() : ''
    if (!name) return { ok: false, error: '缺少技能名称' }
    try {
      return { ok: true, data: await loadAgentSkillFull(name) }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  },
}

// ---------- agent_read_skill_file ----------

const readSkillFileTool = {
  name: 'agent_read_skill_file',
  description: '读取技能附件资源的原文（agent_load_skill 结果里列出的资源文件）。仅用于查看参考文档、脚本等内容；脚本只是文本存档，本产品不会执行任何技能脚本。',
  parameters: Type.Object({
    skill: Type.String({ description: '技能名称' }),
    path: Type.String({ description: '资源路径（与资源清单一致）' }),
  }),
  execute: async (args: Record<string, unknown>): Promise<AgentToolResult> => {
    const skill = typeof args.skill === 'string' ? args.skill.trim() : ''
    const path = typeof args.path === 'string' ? args.path.trim() : ''
    if (!skill) return { ok: false, error: '缺少技能名称' }
    if (!path) return { ok: false, error: '缺少资源路径' }
    try {
      return { ok: true, data: await readSkillResource(skill, path) }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  },
}

// ---------- agent_save_skill ----------

const saveSkillTool = {
  name: 'agent_save_skill',
  description: '把技能保存到用户个人技能库（保存后当前会话即可 agent_load_skill 加载）。流程：先在回复中完整展示草稿（name/tag/description/content）并征得用户同意，再调用本工具；保存成功后告知用户可用 /tag 快速调用、预设中心可编辑或投稿广场。与已有技能同名会被拒绝。技能是纯文本方法论包（无代码执行），正文不要写脚本或对外部工具的调用指引。',
  parameters: Type.Object({
    name: Type.String({ description: '技能名（唯一，与已有技能不得同名）' }),
    description: Type.String({ description: '"何时使用"触发行：技能清单只列名称+本行，模型据此决定是否加载；用"当用户……时使用"句式，≤60 字' }),
    tag: Type.Optional(Type.String({ description: '短标识（/ 快速清单对齐用，2-4 字，可选）' })),
    content: Type.String({ description: `技能正文方法论，结构=适用场景/步骤/约束/示例，上限 ${SKILL_CONTENT_MAX_CHARS} 字符` }),
    import_meta: Type.Optional(Type.Record(Type.String(), Type.Unknown(), { description: '转译溯源（来源格式、原始名称、丢弃清单等），仅技能转译时传' })),
  }),
  execute: async (args: Record<string, unknown>): Promise<AgentToolResult> => {
    const meta = args.import_meta
    try {
      const r = await saveAgentSkill({
        name: typeof args.name === 'string' ? args.name : '',
        description: typeof args.description === 'string' ? args.description : '',
        content: typeof args.content === 'string' ? args.content : '',
        tag: typeof args.tag === 'string' && args.tag.trim() ? args.tag : undefined,
        importMeta: isRecord(meta) ? meta : undefined,
      })
      return { ok: true, data: { name: r.name, tag: r.tag, message: `技能「${r.name}」已保存到个人技能库，可用 /${r.tag || r.name} 快速调用` } }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  },
}

/** chat 宿主工具组（经内核 HostTool 包装后挂载；追加新工具放末尾，测试按索引取用） */
export const CHAT_TOOLS = [imageTool, videoTool, loadSkillTool, saveSkillTool, readSkillFileTool]

/** 工具名清单（allowed-tools 白名单映射目标） */
export const CHAT_TOOL_NAMES = CHAT_TOOLS.map((t) => t.name)
