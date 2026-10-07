/* =====================================================
 * 对话页宿主工具组（三期内核统一，UI 无关）
 *
 * - generate_image / generate_video：前端提交生成任务（images/videos tasks
 *   端点自带积分扣减，画布生成同链路已验证）→ 注册 taskQueue → 立即返回
 *   pending（不阻塞回合）；媒体占位/轮询/media-callback 回写由 chat store
 *   沿用既有机制，工具不等待；place_on_canvas 走「完成后落画布」计划
 * - 画布工具组（canvas_*）：全部走云端 canvas_workspaces ops 端点增量写入，
 *   与前端内存态画布互不干扰（CLI/MCP 化同一地基，见 .zcode/plans 设计文档）
 * - 参考图解析经 ChatToolContext（chat store 提供最近成功生成的媒体）
 * - agent_load_skill 复用 skills 模块缓存（与画布同款渐进披露）
 * ===================================================== */

import { Type } from 'typebox'
import { createImageTask } from '@/api/images'
import { createVideoTask } from '@/api/videos'
import { getPreset } from '@/api/presets'
import { applyCanvasOps, getWorkspace, listWorkspaces } from '@/api/canvasWorkspace'
import { generateCanvasTts } from '@/api/canvas'
import { createAsset } from '@/api/assets'
import { useTaskQueueStore } from '@/stores/taskQueue'
import { useModelsStore } from '@/stores/models'
import { useCanvasStore } from '@/stores/canvas'
import type { ImageGenerationRequest, VideoGenerationRequest } from '@/types'
import type { AgentToolResult } from './tools'
import { AGENT_TOOLS } from './tools'
import type { AgentKernel, HostTool } from './kernel'
import { runSubagent, subagentHostFromParent } from './subagent'
import { loadAgentSkillFull, readSkillResource, saveAgentSkill, SKILL_CONTENT_MAX_CHARS } from './skills'
import { EDITOR_TOOLS } from './editor-tools'

/** 媒体完成后落画布的计划（工具注册 → chat store 媒体轮询成功时消费） */
export interface CanvasPlacementPlan {
  taskId: string
  workspaceId: string
  workspaceName: string
  created: boolean
  mediaType: 'image' | 'video'
  prompt: string
}

/** 画布落点解析结果（created=true 表示本次自动新建） */
export interface CanvasTarget {
  workspaceId: string
  workspaceName: string
  created?: boolean
}

/** chat 工具执行上下文（chat store 提供）：会话连续性所需的媒体状态 */
export interface ChatToolContext {
  /** 最近一次成功生成的媒体 URL（图生图/图生视频默认参考） */
  getRecentMediaUrl(type: 'image' | 'video'): string | null
  /** 画布目标解析（多级兜底：显式 → 画布页实时激活 → 偏好 → 最近使用 → 自动建；anon 返回 null） */
  resolveCanvasTarget?(explicitId?: string): Promise<CanvasTarget | null>
  /** 「生成后自动放入画布」偏好开关（place_on_canvas 未传时的默认值） */
  isAutoPlaceMedia?(): Promise<boolean>
  /** 注册「媒体完成后落画布」计划（媒体轮询成功时由 chat store 消费） */
  registerCanvasPlacement?(plan: CanvasPlacementPlan): void
}

const NO_CANVAS_WORKSPACE_HINT =
  '没有可用的云端画布工作区：请先让用户在画布页登录并选择工作区，或不指定落画布直接生成'

function isChatCtx(ctx: unknown): ctx is ChatToolContext {
  return typeof ctx === 'object' && ctx !== null && 'getRecentMediaUrl' in ctx
}

function recentMediaUrl(ctx: unknown, type: 'image' | 'video'): string | null {
  return isChatCtx(ctx) ? ctx.getRecentMediaUrl(type) : null
}

/** 目标工作区解析：显式参数优先，缺省走 ctx 的多级兜底链（画布页实时态 → 偏好 → 最近 → 自动建） */
export async function resolveTarget(ctx: unknown, explicit: unknown): Promise<CanvasTarget | null> {
  if (typeof explicit === 'string' && explicit.trim()) return { workspaceId: explicit.trim(), workspaceName: '' }
  if (isChatCtx(ctx) && typeof ctx.resolveCanvasTarget === 'function') return ctx.resolveCanvasTarget()
  return null
}

/** 「生成后自动放入画布」偏好（place_on_canvas 未传时的默认值；非 chat 宿主返回 false） */
export async function autoPlacePref(ctx: unknown): Promise<boolean> {
  return isChatCtx(ctx) && typeof ctx.isAutoPlaceMedia === 'function' ? await ctx.isAutoPlaceMedia() : false
}

/** 落点告知文案：自动建与已有画布措辞区分 */
function targetWhere(target: CanvasTarget): string {
  return target.created
    ? `已新建画布「${target.workspaceName || target.workspaceId}」`
    : `画布「${target.workspaceName || target.workspaceId}」`
}

function registerCanvasPlacement(ctx: unknown, plan: CanvasPlacementPlan): void {
  if (isChatCtx(ctx) && typeof ctx.registerCanvasPlacement === 'function') ctx.registerCanvasPlacement(plan)
}

/** 画布 ops 失败信息：优先取后端逐条错误（400 detail.results），否则退回 Error message */
function canvasOpsErrorMessage(e: unknown): string {
  const err = e as Error & { detail?: unknown }
  const d = err?.detail
  if (isRecord(d) && Array.isArray(d.results)) {
    const errs = d.results
      .filter((r): r is Record<string, unknown> => isRecord(r) && r.ok === false && typeof r.error === 'string')
      .map((r) => r.error as string)
    if (errs.length) return errs.slice(0, 3).join('；')
  }
  if (isRecord(d) && typeof d.message === 'string') return d.message
  return err?.message || String(e)
}

/** 解析目标工作区并执行批量 ops（画布工具组共用；结果带落点画布名） */
async function runCanvasOps(
  ctx: unknown,
  workspaceIdArg: unknown,
  ops: Record<string, unknown>[],
  okMessage: string,
): Promise<AgentToolResult> {
  const target = await resolveTarget(ctx, workspaceIdArg)
  if (!target) return { ok: false, error: NO_CANVAS_WORKSPACE_HINT }
  try {
    const r = await applyCanvasOps(target.workspaceId, ops)
    const where = targetWhere(target)
    return {
      ok: true,
      data: {
        workspace_id: target.workspaceId,
        results: r.results,
        new_panel_ids: r.new_panel_ids,
        message: r.failed ? `${okMessage}（${where}，${r.failed} 条失败详见 results）` : `${okMessage}（${where}）`,
      },
    }
  } catch (e) {
    return { ok: false, error: canvasOpsErrorMessage(e) }
  }
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
    place_on_canvas: Type.Optional(Type.Boolean({ description: '是否自动放入云端画布：用户说"画到画布上/放到画布"传 true；说"不放画布/只发在对话里"传 false；不传时按用户偏好「生成后自动放入画布」的开关决定' })),
    canvas_workspace_id: Type.Optional(Type.String({ description: '落画布的目标工作区 id（缺省由系统自动解析为当前画布，一般无需传）' })),
  }),
  execute: async (args: Record<string, unknown>, ctx: unknown): Promise<AgentToolResult> => {
    const rawPrompt = typeof args.prompt === 'string' ? args.prompt.trim() : ''
    if (!rawPrompt) return { ok: false, error: '缺少图片生成提示词' }
    // 落画布默认值：显式参数优先（false 可覆盖偏好开启），未传按偏好开关
    const autoPlace = isChatCtx(ctx) && typeof ctx.isAutoPlaceMedia === 'function' ? await ctx.isAutoPlaceMedia() : false
    const placeOnCanvas = typeof args.place_on_canvas === 'boolean' ? args.place_on_canvas : autoPlace
    let canvasTarget: CanvasTarget | null = null
    if (placeOnCanvas) {
      canvasTarget = await resolveTarget(ctx, args.canvas_workspace_id)
      if (!canvasTarget) return { ok: false, error: NO_CANVAS_WORKSPACE_HINT }
    }
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
      if (canvasTarget) {
        registerCanvasPlacement(ctx, {
          taskId: resp.task_id, workspaceId: canvasTarget.workspaceId,
          workspaceName: canvasTarget.workspaceName, created: canvasTarget.created === true,
          mediaType: 'image', prompt,
        })
      }
      return {
        ok: true,
        data: {
          task_id: resp.task_id,
          media_type: 'image',
          status: 'pending',
          message: '图片生成任务已提交，完成后会自动展示给用户'
            + (canvasTarget ? `，并自动放入${targetWhere(canvasTarget)}（无需再调用画布工具）` : '')
            + '，不要在回复中输出任何图片链接',
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
    place_on_canvas: Type.Optional(Type.Boolean({ description: '是否自动放入云端画布：用户说"放到画布上"传 true；说"不放画布"传 false；不传时按用户偏好「生成后自动放入画布」的开关决定' })),
    canvas_workspace_id: Type.Optional(Type.String({ description: '落画布的目标工作区 id（缺省由系统自动解析为当前画布，一般无需传）' })),
  }),
  execute: async (args: Record<string, unknown>, ctx: unknown): Promise<AgentToolResult> => {
    const rawPrompt = typeof args.prompt === 'string' ? args.prompt.trim() : ''
    if (!rawPrompt) return { ok: false, error: '缺少视频生成提示词' }
    const autoPlace = isChatCtx(ctx) && typeof ctx.isAutoPlaceMedia === 'function' ? await ctx.isAutoPlaceMedia() : false
    const placeOnCanvas = typeof args.place_on_canvas === 'boolean' ? args.place_on_canvas : autoPlace
    let canvasTarget: CanvasTarget | null = null
    if (placeOnCanvas) {
      canvasTarget = await resolveTarget(ctx, args.canvas_workspace_id)
      if (!canvasTarget) return { ok: false, error: NO_CANVAS_WORKSPACE_HINT }
    }
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
      if (canvasTarget) {
        registerCanvasPlacement(ctx, {
          taskId, workspaceId: canvasTarget.workspaceId,
          workspaceName: canvasTarget.workspaceName, created: canvasTarget.created === true,
          mediaType: 'video', prompt,
        })
      }
      return {
        ok: true,
        data: {
          task_id: taskId,
          media_type: 'video',
          status: 'pending',
          message: '视频生成任务已提交（通常需要 1-3 分钟），完成后自动展示'
            + (canvasTarget ? `，并自动放入${targetWhere(canvasTarget)}（无需再调用画布工具）` : '')
            + '，不要在回复中输出任何视频链接',
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

// ---------- agent_delegate ----------

const delegateTool = {
  name: 'agent_delegate',
  description: '把可独立完成的子任务委派给子代理执行：子代理继承对话工具但拥有独立上下文，过程细节不进入主对话，只返回结论摘要。适合：长任务上下文隔离（长文分析、多步调研）、多视角并行评审（不同角色视角各派一个）、批量重复性子任务。一次委派只做一件事；并行场景在同一条消息里发多个委派。',
  parameters: Type.Object({
    task: Type.String({ description: '子任务目标（一句话说清做什么、产出什么）' }),
    context: Type.Optional(Type.String({ description: '子任务需要的背景材料（原文片段/约束/已确认的设定）' })),
    tools_allowed: Type.Optional(Type.Array(Type.String(), { description: '可选：收窄子代理可用工具名清单（只能收窄不能放大，禁止包含 agent_delegate）' })),
  }),
  execute: async (args: Record<string, unknown>, _ctx: unknown, callId?: string, parent?: AgentKernel): Promise<AgentToolResult> => {
    if (!parent) return { ok: false, error: '子代理不可用（缺少父内核上下文）' }
    return runSubagent(
      {
        task: typeof args.task === 'string' ? args.task : '',
        context: typeof args.context === 'string' ? args.context : undefined,
        tools_allowed: Array.isArray(args.tools_allowed) ? args.tools_allowed.filter((x): x is string => typeof x === 'string') : undefined,
      },
      subagentHostFromParent(parent, { tools: CHAT_TOOLS, callId }),
    )
  },
}

// ---------- canvas_* 画布工具组（云端 ops 增量写入，CLI/MCP 化同一地基） ----------

/** 节点内容摘要（overview 用）：文本取正文，媒体取状态+prompt，其余截断 JSON */
function panelContentSummary(p: Record<string, unknown>): string {
  const content = isRecord(p.content) ? p.content : {}
  const truncate = (s: string, n = 120) => (s.length > n ? `${s.slice(0, n)}…` : s)
  const type = typeof p.type === 'string' ? p.type : 'text'
  if (type === 'text') return typeof content.content === 'string' ? truncate(content.content) : ''
  const parts: string[] = []
  if (typeof content.status === 'string') parts.push(`status=${content.status}`)
  if (typeof content.prompt === 'string' && content.prompt) parts.push(`prompt=${truncate(content.prompt, 60)}`)
  if (typeof content.content === 'string' && content.content) parts.push('有媒体内容')
  return parts.join(' ')
}

const canvasListWorkspacesTool = {
  name: 'canvas_list_workspaces',
  description:
    '列出用户的云端画布工作区（id/名称/更新时间）。用户提到"画布"但不确定操作哪个工作区时，' +
    '或画布工具报"没有可用工作区"需要列出供用户选择时调用。',
  parameters: Type.Object({}),
  execute: async (): Promise<AgentToolResult> => {
    try {
      const items = await listWorkspaces()
      return {
        ok: true,
        data: {
          workspaces: items.map((w) => ({ id: w.id, name: w.name, updated_at: w.updated_at })),
          message: items.length
            ? '共 ' + items.length + ' 个工作区；canvas_get_overview / canvas_add_panels 的 canvas_workspace_id 可传其中的 id'
            : '还没有云端画布工作区（需在画布页登录并保存过一次）',
        },
      }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  },
}

const canvasGetOverviewTool = {
  name: 'canvas_get_overview',
  description:
    '读取云端画布工作区概要：节点（id/类型/名称/坐标/内容摘要）与连线关系（按名称标注上下游）。' +
    '在引用已有节点、连线或回答画布内容问题前先调用；不返回图片/视频的二进制内容。',
  parameters: Type.Object({
    canvas_workspace_id: Type.Optional(Type.String({ description: '工作区 id（缺省用当前激活工作区）' })),
  }),
  execute: async (args: Record<string, unknown>, ctx: unknown): Promise<AgentToolResult> => {
    const target = await resolveTarget(ctx, args.canvas_workspace_id)
    if (!target) return { ok: false, error: NO_CANVAS_WORKSPACE_HINT }
    try {
      const detail = await getWorkspace(target.workspaceId)
      const data = (detail.data ?? {}) as Record<string, unknown>
      const panels = Array.isArray(data.panels) ? (data.panels as Record<string, unknown>[]) : []
      const connections = Array.isArray(data.connections) ? (data.connections as Record<string, unknown>[]) : []
      const nameOf = (id: unknown): string => {
        const found = panels.find((p) => p.id === id)
        return found ? String(found.name || found.id) : String(id ?? '')
      }
      const OVERVIEW_LIMIT = 80
      return {
        ok: true,
        data: {
          workspace_id: target.workspaceId,
          name: detail.name,
          panel_count: panels.length,
          panels: panels.slice(0, OVERVIEW_LIMIT).map((p) => ({
            id: p.id,
            type: typeof p.type === 'string' ? p.type : 'text',
            name: typeof p.name === 'string' ? p.name : '',
            x: p.x,
            y: p.y,
            summary: panelContentSummary(p),
          })),
          ...(panels.length > OVERVIEW_LIMIT ? { note: `仅列前 ${OVERVIEW_LIMIT} 个节点，共 ${panels.length} 个` } : {}),
          connections: connections.map((c) => ({
            id: c.id,
            source: nameOf(c.source_panel_id),
            target: nameOf(c.target_panel_id),
          })),
        },
      }
    } catch (e) {
      return { ok: false, error: canvasOpsErrorMessage(e) }
    }
  },
}

const canvasAddPanelsTool = {
  name: 'canvas_add_panels',
  description:
    '在云端画布工作区批量新建节点（只增不改不删）。panels 每项：type（text/image/video/audio 等，缺省 text）、' +
    'name（建议命名，后续连线可按名引用）、content（文本节点写 {"content":"文字"}；媒体节点也可直接给 url）、' +
    'x/y/width/height 可选（缺省自动排布）。' +
    '注意：要把对话生成的图片/视频放入画布，请用 generate_image / generate_video 的 place_on_canvas 参数（完成后自动落画布），' +
    '本工具适合已有 URL 的素材或纯文本节点。',
  parameters: Type.Object({
    canvas_workspace_id: Type.Optional(Type.String({ description: '工作区 id（缺省用当前激活工作区）' })),
    panels: Type.Array(Type.Object({
      type: Type.Optional(Type.String({ description: '节点类型，缺省 text；给 url 的图片/视频请对应写 image/video' })),
      name: Type.Optional(Type.String({ description: '节点名称' })),
      content: Type.Optional(Type.Record(Type.String(), Type.Unknown(), { description: '初始内容（文本节点 {"content":"文字"}）' })),
      url: Type.Optional(Type.String({ description: '图片/视频直链（传入后按已就绪媒体内容写入）' })),
      x: Type.Optional(Type.Number()),
      y: Type.Optional(Type.Number()),
      width: Type.Optional(Type.Number()),
      height: Type.Optional(Type.Number()),
    }), { minItems: 1, maxItems: 20, description: '要新建的节点列表' }),
  }),
  execute: async (args: Record<string, unknown>, ctx: unknown): Promise<AgentToolResult> => {
    const arr = Array.isArray(args.panels) ? args.panels.filter(isRecord) : []
    if (!arr.length) return { ok: false, error: '缺少 panels 参数' }
    const ops = arr.map((p) => {
      const url = typeof p.url === 'string' && p.url.trim() ? p.url.trim() : ''
      const content: Record<string, unknown> = { ...(isRecord(p.content) ? p.content : {}) }
      if (url) {
        content.status = 'success'
        content.content = url
      }
      return {
        op: 'add_panel',
        type: typeof p.type === 'string' && p.type ? p.type : url ? 'image' : 'text',
        name: typeof p.name === 'string' ? p.name : undefined,
        content: Object.keys(content).length ? content : undefined,
        x: typeof p.x === 'number' ? p.x : undefined,
        y: typeof p.y === 'number' ? p.y : undefined,
        width: typeof p.width === 'number' ? p.width : undefined,
        height: typeof p.height === 'number' ? p.height : undefined,
      }
    })
    return runCanvasOps(ctx, args.canvas_workspace_id, ops, '节点已添加到画布')
  },
}

const canvasConnectTool = {
  name: 'canvas_connect',
  description:
    '在云端画布工作区批量创建连线（方向=数据流向，从上游资源指向下游生成节点）。' +
    'source_panel_id / target_panel_id 可传节点 id 或节点名称（先 canvas_get_overview 获取）。' +
    '类型规则：tts/subtitle 只接受文本入边；compose 只接受 video/tts/subtitle 入边；脚本节点只能连到配置节点，违规会被拒绝。',
  parameters: Type.Object({
    canvas_workspace_id: Type.Optional(Type.String({ description: '工作区 id（缺省用当前激活工作区）' })),
    connections: Type.Array(Type.Object({
      source_panel_id: Type.String({ description: '上游节点 id 或名称' }),
      target_panel_id: Type.String({ description: '下游节点 id 或名称' }),
    }), { minItems: 1, maxItems: 20, description: '要创建的连线列表' }),
  }),
  execute: async (args: Record<string, unknown>, ctx: unknown): Promise<AgentToolResult> => {
    const arr = Array.isArray(args.connections) ? args.connections.filter(isRecord) : []
    if (!arr.length) return { ok: false, error: '缺少 connections 参数' }
    const ops = arr.map((c) => ({
      op: 'add_connection',
      source_panel_id: typeof c.source_panel_id === 'string' ? c.source_panel_id : '',
      target_panel_id: typeof c.target_panel_id === 'string' ? c.target_panel_id : '',
    }))
    return runCanvasOps(ctx, args.canvas_workspace_id, ops, '连线已创建')
  },
}

/** 文本转配音宿主工具（Edge TTS 免费入口）：画布 tts 节点之外的通用 TTS——剪辑工程/对话页配音靠它。
 *  与画布 agent_run_generation(kind=tts) 的差异：不依赖画布节点，直接文本→音频→素材库 asset_id */
const generateTtsTool = {
  name: 'generate_tts',
  description:
    '文本转语音配音（免费）：把台词/旁白文案合成为音频并入素材库，返回 asset_id、audio_url 与时长。' +
    '剪辑工程配音链路：editor_get_overview 拿字幕/片段的时间点与文案 → 按段调本工具生成 → editor_apply_ops 的 addClip {assetId} 加进音频轨对齐时间。' +
    'voice 音色按角色/场景选：default 阳光男声（缺省）/female 标准女声/male，或内置音色 id：' +
    'narrator_male_zh 男声旁白、narrator_female_zh 女声旁白、young_male_zh 年轻男声、young_female_zh 年轻女声、' +
    'mature_male_zh 成熟男声、mature_female_zh 成熟女声、child_zh 童声、elder_zh 老年声；speed 语速倍率缺省 1.0。',
  parameters: Type.Object({
    text: Type.String({ description: '要合成的台词/旁白文本' }),
    voice: Type.Optional(Type.String({ description: '音色（见工具描述），缺省 default' })),
    speed: Type.Optional(Type.Number({ description: '语速倍率，缺省 1.0' })),
    name: Type.Optional(Type.String({ description: '素材名（缺省「配音-TTS」）' })),
  }),
  execute: async (args: Record<string, unknown>): Promise<AgentToolResult> => {
    const text = typeof args.text === 'string' ? args.text.trim() : ''
    if (!text) return { ok: false, error: 'text 不能为空：把要合成的台词/旁白文本传进来' }
    const voice = typeof args.voice === 'string' && args.voice.trim() ? args.voice.trim() : 'default'
    const speed = typeof args.speed === 'number' && args.speed > 0 ? args.speed : 1.0
    const name = typeof args.name === 'string' && args.name.trim() ? `配音-${args.name.trim().slice(0, 24)}` : '配音-TTS'
    try {
      const res = await generateCanvasTts({ text, voice, speed })
      // 统一素材库入库：editor_apply_ops 的 addClip 只认 assetId，不入库配音进不了剪辑工程
      let assetId: number | null = null
      try {
        const asset = await createAsset({ url: res.audio_url, media_type: 'audio', name })
        assetId = asset.id
      } catch {
        /* 入库失败不阻塞返回：audio_url 仍可用于画布 compose，缺少 asset_id 时结果里说明 */
      }
      return {
        ok: true,
        data: {
          asset_id: assetId,
          audio_url: res.audio_url,
          duration_ms: res.duration_ms ?? null,
          message: assetId != null
            ? `配音已生成并入素材库（asset_id ${assetId}）：剪辑工程用 editor_apply_ops 的 addClip {assetId: ${assetId}} 加进音频轨；画布 compose 可直接用 audio_url`
            : `配音已生成但素材库入库失败（可重试本工具）：audio_url ${res.audio_url}`,
        },
      }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  },
}

/** chat 宿主工具组（经内核 HostTool 包装后挂载；追加新工具放末尾，测试按索引取用） */
export const CHAT_TOOLS = [
  imageTool,
  videoTool,
  loadSkillTool,
  saveSkillTool,
  readSkillFileTool,
  delegateTool,
  canvasListWorkspacesTool,
  canvasGetOverviewTool,
  canvasAddPanelsTool,
  canvasConnectTool,
  ...EDITOR_TOOLS,
  generateTtsTool,
]

/** 工具名清单（allowed-tools 白名单映射目标） */
export const CHAT_TOOL_NAMES = CHAT_TOOLS.map((t) => t.name)

/** 画布深度工具 → 宿主工具适配（Agent 统一宿主：仅画布页挂载）。
 *  AGENT_TOOLS 的 execute 第二参吃画布 store，而 chat 内核传 toolContext，故在此改写；
 *  剔除与 CHAT_TOOLS 重名的四个通用工具，避免内核按名冲突；callId/parent 透传（delegate/子代理进度用）。 */
export function canvasHostTools(): HostTool[] {
  return AGENT_TOOLS.filter((t) => !CHAT_TOOL_NAMES.includes(t.name)).map((t) => ({
    name: t.name,
    description: t.description,
    parameters: t.parameters,
    execute: (args, _ctx, callId, parent) => t.execute(args, useCanvasStore(), callId, parent),
  }))
}
