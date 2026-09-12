/* =====================================================
 * 画布 Agent 工具层（UI 无关）
 *
 * - 每个工具 = OpenAI function calling schema + 执行器
 * - 执行器只操作 canvas store 与 canvas-generation.ts，不接触 UI；
 *   签名保持稳定，未来本地 MCP server 直接复用本模块桥接 CLI Agent
 * - 权限组：read（只读）/ write（写画布）/ generation（触发生成）
 * ===================================================== */

import type { CanvasPanel, CanvasConnection, CanvasStyleSelection } from '@/stores/canvas'
import { executeInNodeGeneration, executeInNodeVideoGeneration } from '@/lib/canvas-generation'
import { composeCanvasVideos } from '@/api/canvas'
import { useModelsStore } from '@/stores/models'
import type { ModelInfo } from '@/types'
import { Type } from 'typebox'
import type { TSchema } from 'typebox'
import { stageApprovedMessage } from './policy'
import { fetchPanelImageBase64 } from './attachments'
import { getCachedSkill, getCachedSkills } from './skills'
import type { AgentImageAttachment } from './attachments'
import { extractEntities, splitStoryboard } from '@/lib/storyboard/pipeline'
import { buildAssetPrompt } from '@/lib/storyboard/prompts'
import { listCameraVocabulary, listStyleEntries, resolveStyleConfig } from '@/lib/storyboard/library'
import type { StoryboardEntity, StyleConfig } from '@/lib/storyboard/schemas'
import { isEntityKind } from '@/lib/storyboard/schemas'

/** 工具执行结果：data 为回填给 LLM 的内容（JSON 序列化后发送）；images 为随结果给模型看的图（内核转 toolResult image 块） */
export interface AgentToolResult {
  ok: boolean
  data?: unknown
  error?: string
  images?: AgentImageAttachment[]
}

/** 工具权限组 */
export type AgentToolGroup = 'read' | 'write' | 'generation'

/** 工具层所需的最小画布 store 结构（真实 canvas store 结构化兼容） */
export interface AgentCanvasStore {
  panels: CanvasPanel[]
  connections: CanvasConnection[]
  selectedPanelIds: string[]
  activeWorkspaceId: string | null
  lastConnectionError: string | null
  /** 当前工作区生效风格配置（实体设定图/分镜图提示词统一取用） */
  activeStyleConfig: StyleConfig
  /** 写入工作区级风格选择（随画布持久化；Agent 对话式选定风格用） */
  setWorkspaceStyleConfig: (selection: CanvasStyleSelection | null) => void
  addPanel: (input: Partial<CanvasPanel> & { x: number; y: number; width: number; height: number }) => string
  updatePanel: (id: string, changes: Partial<CanvasPanel>) => void
  deletePanel: (id: string) => void
  addConnection: (conn: { source_panel_id: string; target_panel_id: string; type?: string }) => CanvasConnection | null
  deleteConnection: (id: string) => void
  selectPanel: (id: string | null, opts?: { append?: boolean }) => void
  pushSnapshot: () => void
}

/** agent_apply_ops 的单条操作 */
export interface AgentCanvasOp {
  op: 'add_panel' | 'update_panel' | 'delete_panel' | 'add_connection' | 'delete_connection'
  [key: string]: unknown
}

export interface AgentTool {
  name: string
  group: AgentToolGroup
  description: string
  /** TypeBox 定义（即 JSON Schema，单一来源）：机制层直接消费；OpenAI function 格式由 agentToolSchemasOpenAI 直出 */
  parameters: TSchema
  execute: (args: Record<string, unknown>, canvas: AgentCanvasStore) => Promise<AgentToolResult> | AgentToolResult
}

// ---------- 参数安全读取（不做类型断言） ----------

function asString(v: unknown, fallback = ''): string {
  return typeof v === 'string' ? v : fallback
}

function asNumber(v: unknown, fallback: number): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function asRecord(v: unknown): Record<string, unknown> {
  return isRecord(v) ? v : {}
}

/** update_panel 的 changes 守卫：只放行节点已知字段（不做类型断言） */
/** 工具层强制：剥离 LLM 传入的模型指定。模型只能走用户默认偏好或 run_generation 显式 model 参数，防止 LLM 静默换模型产生费用偏差 */
function withoutModel(content: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(content)) {
    if (k !== 'model') out[k] = v
  }
  return out
}

/** 文本节点内容字段归一：画布渲染字段是 content，LLM 常写 text——工具层强制兼容，不依赖 prompt 自觉 */
function normalizeTextContent(content: Record<string, unknown>, panelType: string): Record<string, unknown> {
  if (panelType !== 'text' || content.content !== undefined || content.text === undefined) return content
  const out = { ...content }
  delete out.text
  out.content = content.text
  return out
}

function asPanelChanges(v: unknown): Partial<CanvasPanel> {
  const src = asRecord(v)
  const out: Partial<CanvasPanel> = {}
  if (typeof src.type === 'string') out.type = src.type
  if (typeof src.name === 'string') out.name = src.name
  if (typeof src.x === 'number') out.x = src.x
  if (typeof src.y === 'number') out.y = src.y
  if (typeof src.width === 'number') out.width = src.width
  if (typeof src.height === 'number') out.height = src.height
  if (typeof src.is_locked === 'boolean') out.is_locked = src.is_locked
  if (typeof src.is_hidden === 'boolean') out.is_hidden = src.is_hidden
  if (src.content !== undefined) out.content = withoutModel(asRecord(src.content))
  if (src.meta !== undefined) out.meta = asRecord(src.meta)
  return out
}

/** content 摘要：只保留原始类型字段，长字符串截断（base64 等超长值跳过） */
function summarizeContent(content: unknown): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(asRecord(content))) {
    if (typeof v === 'string') {
      if (v.length > 300) out[k] = `<${v.length} 字符，已省略>`
      else out[k] = v.length > 120 ? `${v.slice(0, 120)}…` : v
    } else if (typeof v === 'number' || typeof v === 'boolean' || v === null) {
      out[k] = v
    }
  }
  return out
}

function summarizePanel(p: CanvasPanel): Record<string, unknown> {
  return {
    id: p.id,
    type: p.type || 'text',
    name: p.name || '',
    x: Math.round(p.x),
    y: Math.round(p.y),
    width: Math.round(p.width),
    height: Math.round(p.height),
    content: summarizeContent(p.content),
  }
}

function summarizePanels(panels: CanvasPanel[]): Record<string, unknown>[] {
  return panels.map(summarizePanel)
}

/** 模型能力摘要（给 Agent 做时长/参考图规划用） */
function summarizeModel(m: ModelInfo): Record<string, unknown> {
  return {
    id: m.id,
    name: m.name,
    capabilities: m.capabilities,
    max_ref_images: m.gen_params?.max_ref_images ?? null,
  }
}

// ---------- 工具实现 ----------

/** 读画布状态：当前工作区节点 + 连线 + 选中摘要 */
function getState(canvas: AgentCanvasStore): AgentToolResult {
  return {
    ok: true,
    data: {
      workspace_id: canvas.activeWorkspaceId,
      panel_count: canvas.panels.length,
      panels: summarizePanels(canvas.panels),
      connections: canvas.connections.map((c) => ({
        id: c.id,
        from: c.source_panel_id,
        to: c.target_panel_id,
        type: c.type || 'manual',
      })),
      selected: [...canvas.selectedPanelIds],
    },
  }
}

/** 批量应用画布操作：整批一个撤销快照，逐条执行并收集结果 */
function applyOps(args: Record<string, unknown>, canvas: AgentCanvasStore): AgentToolResult {
  const opsRaw = Array.isArray(args.ops) ? args.ops : []
  if (opsRaw.length === 0) return { ok: false, error: 'ops 为空' }

  canvas.pushSnapshot()
  const results: Record<string, unknown>[] = []
  const newPanelIds: string[] = []
  // 本批次新建节点 name → id：让后续 op 能按名称引用同批新建的节点（一拍完成建点+连线）
  const newPanelByName = new Map<string, string>()

  // 节点引用解析：id 优先，其次节点名称（含本批次新建）；解析失败返回 null
  const resolveRef = (ref: unknown): string | null => {
    if (typeof ref !== 'string' || !ref) return null
    const batchId = newPanelByName.get(ref)
    if (batchId) return batchId
    if (canvas.panels.some((p) => p.id === ref)) return ref
    const byName = canvas.panels.find((p) => (p.name || '') === ref)
    return byName ? byName.id : null
  }

  opsRaw.forEach((raw, i) => {
    const op = asRecord(raw)
    const kind = asString(op.op)
    try {
      if (kind === 'add_panel') {
        const n = canvas.panels.length
        const name = asString(op.name) || undefined
        const panelType = asString(op.type, 'text')
        const id = canvas.addPanel({
          type: panelType,
          name,
          content: normalizeTextContent(withoutModel(asRecord(op.content)), panelType),
          x: asNumber(op.x, 120 + (n % 8) * 40),
          y: asNumber(op.y, 120 + (n % 8) * 40),
          width: asNumber(op.width, 240),
          height: asNumber(op.height, 180),
        })
        if (name) newPanelByName.set(name, id)
        newPanelIds.push(id)
        results.push({ index: i, op: kind, ok: true, panel_id: id })
      } else if (kind === 'update_panel') {
        const panelId = resolveRef(op.panel_id)
        if (!panelId) {
          results.push({ index: i, op: kind, ok: false, error: `节点不存在: ${asString(op.panel_id)}（可用节点名称或 agent_get_state 返回的 id）` })
        } else {
          const changes = asPanelChanges(op.changes)
          const targetType = canvas.panels.find((p) => p.id === panelId)?.type || 'text'
          if (changes.content) changes.content = normalizeTextContent(changes.content, targetType)
          canvas.updatePanel(panelId, changes)
          results.push({ index: i, op: kind, ok: true })
        }
      } else if (kind === 'delete_panel') {
        const panelId = resolveRef(op.panel_id)
        if (!panelId) {
          results.push({ index: i, op: kind, ok: false, error: `节点不存在: ${asString(op.panel_id)}（可用节点名称或 agent_get_state 返回的 id）` })
        } else {
          canvas.deletePanel(panelId)
          results.push({ index: i, op: kind, ok: true })
        }
      } else if (kind === 'add_connection') {
        const sourceId = resolveRef(op.source_panel_id)
        const targetId = resolveRef(op.target_panel_id)
        const missing = [
          [asString(op.source_panel_id), sourceId],
          [asString(op.target_panel_id), targetId],
        ].filter(([, id]) => !id).map(([ref]) => ref)
        if (!sourceId || !targetId) {
          results.push({ index: i, op: kind, ok: false, error: `节点不存在: ${missing.join('、')}（可用节点名称或 agent_get_state 返回的 id）` })
        } else {
          const conn = canvas.addConnection({ source_panel_id: sourceId, target_panel_id: targetId })
          if (conn) results.push({ index: i, op: kind, ok: true, connection_id: conn.id })
          else results.push({ index: i, op: kind, ok: false, error: canvas.lastConnectionError || '连线创建失败' })
        }
      } else if (kind === 'delete_connection') {
        const connId = asString(op.connection_id)
        if (!canvas.connections.some((c) => c.id === connId)) {
          results.push({ index: i, op: kind, ok: false, error: `连线不存在: ${connId}` })
        } else {
          canvas.deleteConnection(connId)
          results.push({ index: i, op: kind, ok: true })
        }
      } else {
        results.push({ index: i, op: kind, ok: false, error: `未知操作类型: ${kind}` })
      }
    } catch (e) {
      results.push({ index: i, op: kind, ok: false, error: e instanceof Error ? e.message : String(e) })
    }
  })

  const failed = results.filter((r) => r.ok === false)
  return { ok: failed.length === 0, data: { results, new_panel_ids: newPanelIds }, error: failed.length ? `${failed.length} 条操作失败` : undefined }
}

// ---------- 分镜管线工具（实体卡收集 + 实体提取/分镜拆分） ----------

/** 从画布收集实体设定卡（image 节点 content.kind 标记）；设定图已成功时带上参考图 URL */
function collectEntityCards(canvas: AgentCanvasStore): StoryboardEntity[] {
  const out: StoryboardEntity[] = []
  for (const p of canvas.panels) {
    if ((p.type || 'text') !== 'image') continue
    const kind = p.content?.kind
    if (!isEntityKind(kind)) continue
    const name = typeof p.content?.entityName === 'string' && p.content.entityName.trim()
      ? p.content.entityName.trim()
      : (p.name || '').trim()
    const desc = typeof p.content?.entityDesc === 'string' ? p.content.entityDesc.trim() : ''
    const url = p.content?.status === 'success' && typeof p.content?.content === 'string' ? p.content.content : ''
    if (!name && !desc) continue
    out.push({ kind, name, description: desc, refImageUrl: url })
  }
  return out
}

function groupByKind(cards: StoryboardEntity[]) {
  return {
    characters: cards.filter((c) => c.kind === 'character'),
    scenes: cards.filter((c) => c.kind === 'scene'),
    props: cards.filter((c) => c.kind === 'prop'),
  }
}

/** Agent 版 compose 成片：按摆放顺序收集上游已生成视频，拼接为连续成片写回节点 */
async function runCompose(panel: CanvasPanel, canvas: AgentCanvasStore): Promise<AgentToolResult> {
  const connectedVideos = canvas.connections
    .filter((c) => c.target_panel_id === panel.id)
    .map((c) => canvas.panels.find((p) => p.id === c.source_panel_id))
    .filter((p): p is CanvasPanel => !!p && (p.type || 'text') === 'video')
  // 不静默跳过未完成的段：缺一段成片就是错的，必须让 LLM 知道并等待/重试
  const pending = connectedVideos.filter((p) => !(typeof p.content?.content === 'string' && p.content.content))
  if (pending.length > 0) {
    return { ok: false, error: `有 ${pending.length} 段上游视频尚未生成完成（节点: ${pending.map((p) => p.name || p.id).join('、')}），等它们生成完成后再调用拼接` }
  }
  // 摆放顺序：行带（y 聚类，容差 = 节点高度一半）→ 带内按 x（与画布 compose 执行同规则）
  const sorted = [...connectedVideos].sort((a, b) => a.y - b.y || a.x - b.x)
  const bands: CanvasPanel[][] = []
  for (const p of sorted) {
    const band = bands.find((arr) => Math.abs(p.y - arr[0].y) <= Math.max(p.height, arr[0].height) / 2)
    if (band) band.push(p)
    else bands.push([p])
  }
  const videos = bands.flatMap((band) => band.sort((a, b) => a.x - b.x))
  if (videos.length === 0) {
    return { ok: false, error: 'compose 节点没有上游视频节点（先建好各段视频节点并连线）' }
  }
  // 成片写入独立结果节点（与画布手动执行同语义）：compose 节点自身不渲染视频，写自身用户看不见
  let resultId = typeof panel.content?.result_panel_id === 'string' ? panel.content.result_panel_id : ''
  if (resultId && !canvas.panels.some((p) => p.id === resultId)) resultId = ''
  if (!resultId) {
    resultId = canvas.addPanel({
      type: 'video',
      name: '成片',
      x: panel.x + panel.width + 60,
      y: panel.y,
      width: 420,
      height: 236,
      content: { content: '', status: 'loading' },
    })
    canvas.addConnection({ source_panel_id: panel.id, target_panel_id: resultId })
    canvas.updatePanel(panel.id, { content: { result_panel_id: resultId } })
    canvas.pushSnapshot()
  } else {
    canvas.updatePanel(resultId, { content: { content: '', status: 'loading', errorDetails: null } })
  }
  canvas.updatePanel(panel.id, { content: { status: 'loading', errorDetails: null } })
  try {
    const res = await composeCanvasVideos({ video_urls: videos.map((p) => String(p.content?.content)) })
    canvas.updatePanel(resultId, { content: { content: res.video_url, status: 'success' } })
    canvas.updatePanel(panel.id, { content: { status: 'idle' } })
    return {
      ok: true,
      data: { panel_id: resultId, kind: 'compose', video_url: res.video_url, segments: videos.length, message: `已按摆放顺序拼接 ${videos.length} 段视频，成片已写入「成片」结果节点` },
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    canvas.updatePanel(resultId, { content: { status: 'error', errorDetails: msg } })
    return { ok: false, error: `拼接失败: ${msg}` }
  }
}

async function runGeneration(args: Record<string, unknown>, canvas: AgentCanvasStore): Promise<AgentToolResult> {
  const panelId = asString(args.panel_id)
  const panel = canvas.panels.find((p) => p.id === panelId)
  if (!panel) return { ok: false, error: `节点不存在: ${panelId}` }

  const fallbackKind = panel.type === 'video' ? 'video' : panel.type === 'compose' ? 'compose' : 'image'
  const kind = asString(args.kind) || fallbackKind
  // 用户点名模型时的唯一入口：校验后在生成前写入节点（UI 与任务记录均可见）；未传则跟随用户默认偏好
  const modelArg = asString(args.model)
  if (modelArg && (kind === 'video' || kind === 'image' || kind === 'asset')) {
    const ms = useModelsStore()
    const list = kind === 'video' ? ms.videoModels : ms.imageModels
    if (!list.some((m) => m.id === modelArg)) {
      return { ok: false, error: `模型不可用: ${modelArg}（用 agent_get_models 查询该类型的可用模型 id）` }
    }
    canvas.updatePanel(panelId, { content: { model: modelArg } })
  }
  try {
    // waitFor：等生成完成再返回，保证后续 compose 执行时各段视频都已就绪
    if (kind === 'video') {
      const ok = await executeInNodeVideoGeneration(panel, canvas, { waitFor: true })
      if (!ok) return { ok: false, error: '视频生成失败，错误详情已写入该节点' }
    } else if (kind === 'compose') {
      return await runCompose(panel, canvas)
    } else {
      const ok = await executeInNodeGeneration(panel, canvas, { waitFor: true })
      if (!ok) return { ok: false, error: '图片生成失败，错误详情已写入该节点' }
    }
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) }
  }
  return {
    ok: true,
    data: {
      panel_id: panelId,
      kind,
      message: '生成完成，结果已写回该节点',
    },
  }
}

// ---------- 工具清单 ----------

/** agent_apply_ops 的单条操作 schema（TypeBox，即 JSON Schema） */
const applyOpSchema = Type.Object({
  op: Type.Union(
    [
      Type.Literal('add_panel'),
      Type.Literal('update_panel'),
      Type.Literal('delete_panel'),
      Type.Literal('add_connection'),
      Type.Literal('delete_connection'),
    ],
    { description: '操作类型' },
  ),
  type: Type.Optional(Type.String({ description: 'add_panel：节点类型' })),
  name: Type.Optional(Type.String({ description: 'add_panel：节点名称' })),
  content: Type.Optional(Type.Record(Type.String(), Type.Unknown(), { description: 'add_panel：初始内容' })),
  x: Type.Optional(Type.Number({ description: 'add_panel：画布坐标' })),
  y: Type.Optional(Type.Number({ description: 'add_panel：画布坐标' })),
  width: Type.Optional(Type.Number()),
  height: Type.Optional(Type.Number()),
  panel_id: Type.Optional(Type.String({ description: 'update_panel/delete_panel：目标节点 id' })),
  changes: Type.Optional(Type.Record(Type.String(), Type.Unknown(), { description: 'update_panel：要合并的变更' })),
  source_panel_id: Type.Optional(Type.String({ description: 'add_connection：上游节点 id' })),
  target_panel_id: Type.Optional(Type.String({ description: 'add_connection：下游节点 id' })),
  connection_id: Type.Optional(Type.String({ description: 'delete_connection：连线 id' })),
})

export const AGENT_TOOLS: AgentTool[] = [
  {
    name: 'agent_get_state',
    group: 'read',
    description: '读取画布当前状态：所有节点（类型/名称/坐标/内容摘要）、连线关系、当前选中。回答画布相关问题或操作前先调用。',
    parameters: Type.Object({}),
    execute: (_args, canvas) => getState(canvas),
  },
  {
    name: 'agent_get_selection',
    group: 'read',
    description: '读取用户当前在画布上选中的节点列表。',
    parameters: Type.Object({}),
    execute: (_args, canvas) => ({
      ok: true,
      data: { selected: summarizePanels(canvas.panels.filter((p) => canvas.selectedPanelIds.includes(p.id))) },
    }),
  },
  {
    name: 'agent_get_models',
    group: 'read',
    description: '读取生成模型能力：默认模型（default_video_model / default_image_model，用户在偏好设置中选择的）、视频时长档位（全局 + 各模型自己的档位，秒）、默认时长、各模型参考图上限。规划分镜视频时长、决定参考图连线数量前先调用；某模型的 content.seconds 必须从该模型自己的 video_durations 档位中选取。用户没有点名模型时一律跟随默认模型，不要自行挑选。',
    parameters: Type.Object({}),
    execute: () => {
      const ms = useModelsStore()
      const globalDurations = [...ms.videoDurations]
      const defaultVideo = ms.defaultVideoModel
      const defaultImage = ms.defaultImageModel
      return {
        ok: true,
        data: {
          video_durations: globalDurations,
          default_video_duration: ms.defaultVideoDuration,
          default_video_model: defaultVideo,
          default_image_model: defaultImage,
          video_models: ms.videoModels.map((m) => ({
            ...summarizeModel(m),
            is_default: m.id === defaultVideo,
            // 按模型档位（gen_params.video_durations）优先，未配置回落全局
            video_durations: m.gen_params?.video_durations?.length ? m.gen_params.video_durations : globalDurations,
          })),
          image_models: ms.imageModels.map((m) => ({ ...summarizeModel(m), is_default: m.id === defaultImage })),
        },
      }
    },
  },
  {
    name: 'agent_read_image',
    group: 'read',
    description: '读取画布图片节点的图像内容并把图给模型看。用户要求分析、参考、检查某张画布图片（生成结果、参考图等）的画面内容时必须先调用本工具；节点的文字信息（名称/描述/prompt）用 agent_get_state 即可，无需看图。',
    parameters: Type.Object({
      panel_id: Type.String({ description: '图片节点 id' }),
    }),
    execute: async (args, canvas) => {
      const panelId = asString(args.panel_id)
      const panel = canvas.panels.find((p) => p.id === panelId)
      if (!panel) return { ok: false, error: `节点不存在: ${panelId}` }
      if ((panel.type || 'text') !== 'image') return { ok: false, error: `节点「${panel.name || panelId}」不是图片节点，无法读取图像内容` }
      const url = panel.content?.status === 'success' && typeof panel.content?.content === 'string' ? panel.content.content : ''
      if (!url) return { ok: false, error: `图片「${panel.name || panelId}」尚未生成完成，暂无可读内容` }
      const image = await fetchPanelImageBase64(url)
      return { ok: true, data: { panel_id: panelId, name: (panel.name || '').trim(), image_url: url }, images: [image] }
    },
  },
  {
    name: 'agent_load_skill',
    group: 'read',
    description: '加载技能全文。系统提示「可用技能」清单里的技能适用当前任务时，先调用本工具获取完整方法论再回答或动手；技能名必须与清单一致。',
    parameters: Type.Object({
      name: Type.String({ description: '技能名称（须与可用技能清单一致）' }),
    }),
    execute: async (args) => {
      const name = asString(args.name).trim()
      if (!name) return { ok: false, error: 'name 为空' }
      const skill = getCachedSkill(name)
      if (!skill) {
        const known = getCachedSkills().map((s) => s.name).join('、') || '无'
        return { ok: false, error: `技能不存在: ${name}（可用技能：${known}）` }
      }
      return { ok: true, data: { name: skill.name, description: skill.description, content: skill.content } }
    },
  },
  {
    name: 'agent_apply_ops',
    group: 'write',
    description: '批量应用画布操作（整批一个撤销快照）。可用 op：add_panel（建节点，type 可选 text/image/video/config/tts/subtitle/compose，content 里 text 节点放 content 字段、媒体节点放 prompt 字段）、update_panel（改节点，changes 与节点结构一致）、delete_panel、add_connection（连线方向 = 数据流向，从上游资源指向下游生成）、delete_connection。节点引用（panel_id/source_panel_id/target_panel_id）可直接写节点名称（推荐，同批次新建的节点也能按名称引用），或用 agent_get_state 返回的 id。',
    parameters: Type.Object({
      ops: Type.Array(applyOpSchema, { description: '操作列表，按顺序执行' }),
    }),
    execute: applyOps,
  },
  {
    name: 'agent_create_text_node',
    group: 'write',
    description: '创建一个文本节点（agent_apply_ops add_panel 的便捷形式）。',
    parameters: Type.Object({
      text: Type.String({ description: '文本内容' }),
      name: Type.Optional(Type.String({ description: '节点名称（可选）' })),
      x: Type.Optional(Type.Number({ description: '画布坐标（可选）' })),
      y: Type.Optional(Type.Number({ description: '画布坐标（可选）' })),
    }),
    execute: (args, canvas) => {
      const n = canvas.panels.length
      const id = canvas.addPanel({
        type: 'text',
        name: asString(args.name) || undefined,
        content: { content: asString(args.text) },
        x: asNumber(args.x, 120 + (n % 8) * 40),
        y: asNumber(args.y, 120 + (n % 8) * 40),
        width: 240,
        height: 180,
      })
      return { ok: true, data: { panel_id: id } }
    },
  },
  {
    name: 'agent_select',
    group: 'write',
    description: '选中画布上的一个节点（可追加选中）。',
    parameters: Type.Object({
      panel_id: Type.String({ description: '目标节点 id' }),
      append: Type.Optional(Type.Boolean({ description: '是否追加选中（默认替换）' })),
    }),
    execute: (args, canvas) => {
      const panelId = asString(args.panel_id)
      if (!canvas.panels.some((p) => p.id === panelId)) return { ok: false, error: `节点不存在: ${panelId}` }
      canvas.selectPanel(panelId, { append: args.append === true })
      return { ok: true, data: { panel_id: panelId } }
    },
  },
  {
    name: 'storyboard_set_style',
    group: 'write',
    description: '设置画布画面风格（用户想要的风格库里没有时用）：style_text 写自定义风格描述、style_preset_id 选库条目，二选一。风格写入画布后所有实体设定图/分镜图提示词统一带风格段——这是风格统一的唯一正路，禁止把风格描述写进实体 description 代替。设置成功后必须重新调用 storyboard_extract_entities 拿带风格的新提示词。',
    parameters: Type.Object({
      style_text: Type.Optional(Type.String({ description: '自定义风格描述（库里没有的风格，如"日式真实电视剧质感，冷色调"）' })),
      style_preset_id: Type.Optional(Type.Number({ description: '风格库条目 id' })),
    }),
    execute: async (args, canvas) => {
      const presetId = typeof args.style_preset_id === 'number' ? args.style_preset_id : null
      const text = asString(args.style_text).trim()
      if (presetId == null && !text) return { ok: false, error: 'style_text 与 style_preset_id 至少提供一个' }
      let config: StyleConfig
      const applied = presetId != null ? `库条目 #${presetId}` : `自定义风格「${text.slice(0, 40)}」`
      if (presetId != null) {
        const resolved = await resolveStyleConfig(presetId)
        if (!resolved) return { ok: false, error: `风格条目不存在: ${presetId}（用 storyboard_list_styles 查有效 id）` }
        config = resolved
      } else {
        config = { prefix: text, suffix: '', negativePrompt: '' }
      }
      canvas.setWorkspaceStyleConfig({ presetId, customText: presetId == null ? text : '', config })
      return {
        ok: true,
        data: { style_config: config, message: `${applied} 已写入画布风格；请重新调用 storyboard_extract_entities（带剧本全文）获取带风格段的实体提示词` },
      }
    },
  },
  {
    name: 'storyboard_list_styles',
    group: 'read',
    description: '列出风格库条目（id/名称/描述/封面）。用户没定画面风格、或说的风格库里没有/语义宽泛时调用——面板会把条目渲染成可点选的风格卡片，并把语义最接近的 2-3 个条目推荐给用户（说明推荐理由），同时告知可添加为自定义风格。用户选定后用 storyboard_set_style 写入。',
    parameters: Type.Object({}),
    execute: async () => {
      try {
        const entries = await listStyleEntries()
        if (entries.length === 0) return { ok: false, error: '风格库为空或不可用：可让用户在分镜向导的风格选择器里自定义风格文本' }
        return {
          ok: true,
          data: {
            styles: entries.map((s) => ({ id: s.id, name: s.name, description: s.description, cover_image: s.cover })),
          },
        }
      } catch (e) {
        return { ok: false, error: e instanceof Error ? e.message : String(e) }
      }
    },
  },
  {
    name: 'storyboard_extract_entities',
    group: 'read',
    description: '实体提取：从剧本文本提取角色/场景/物品清单，并返回每张实体设定卡的生成提示词 asset_prompt（已注入画布当前风格，禁止改动）。实体设定阶段使用：拿到清单后用 agent_apply_ops 建 image 节点（content 带 kind=character/scene/prop、entityName、entityDesc、prompt=asset_prompt），连线到剧本节点，再对每个实体卡节点调用 agent_run_generation(kind=asset) 生成设定图。画布上已有同角色/场景实体卡时不要重复提取建卡。用户想要的风格库里没有时，先用 storyboard_set_style 写入自定义风格再调用本工具。',
    parameters: Type.Object({
      script_text: Type.String({ description: '剧本文本' }),
      style_preset_id: Type.Optional(Type.Number({ description: '用户选定的风格库条目 id（先 storyboard_list_styles 给用户挑）；传入后写入画布风格再提取' })),
    }),
    execute: async (args, canvas) => {
      const scriptText = asString(args.script_text).trim()
      if (!scriptText) return { ok: false, error: 'script_text 为空' }
      try {
        // 用户在对话里选定风格：先写入画布级风格（随工作区持久化），提示词即带上风格段
        if (typeof args.style_preset_id === 'number') {
          const config = await resolveStyleConfig(args.style_preset_id)
          if (!config) return { ok: false, error: `风格条目不存在: ${args.style_preset_id}（用 storyboard_list_styles 查有效 id）` }
          canvas.setWorkspaceStyleConfig({ presetId: args.style_preset_id, customText: '', config })
        }
        const group = await extractEntities(scriptText)
        const style = canvas.activeStyleConfig
        const withPrompt = (list: StoryboardEntity[]) =>
          list.map((e) => ({ kind: e.kind, name: e.name, description: e.description, asset_prompt: buildAssetPrompt(e, style) }))
        const styleApplied = Boolean(style.prefix || style.suffix || style.negativePrompt)
        return {
          ok: true,
          data: {
            characters: withPrompt(group.characters),
            scenes: withPrompt(group.scenes),
            props: withPrompt(group.props),
            style_applied: styleApplied,
            message: styleApplied ? '已注入画布当前风格' : '画布未选风格：请先让用户选定风格（storyboard_list_styles），确认前不要生成任何图片',
          },
        }
      } catch (e) {
        return { ok: false, error: e instanceof Error ? e.message : String(e) }
      }
    },
  },
  {
    name: 'storyboard_split',
    group: 'read',
    description: '分镜拆分：按画布上的实体设定卡把剧本文本拆成单镜分镜列表，每镜返回成品分镜图提示词 prompt（已含单帧约束/景别运镜/风格/实体设定，禁止改动直接用）。分镜提示词阶段使用：用 agent_apply_ops 建分镜图 image 节点（prompt 字段，name 用 #序号），连线到剧本节点与命中的实体卡节点。需先完成实体设定（画布上有实体卡）。',
    parameters: Type.Object({
      script_text: Type.String({ description: '剧本文本' }),
      shot_count_min: Type.Optional(Type.Number({ description: '最少镜头数（缺省 3）' })),
      shot_count_max: Type.Optional(Type.Number({ description: '最多镜头数（缺省 8）' })),
    }),
    execute: async (args, canvas) => {
      const scriptText = asString(args.script_text).trim()
      if (!scriptText) return { ok: false, error: 'script_text 为空' }
      const cards = collectEntityCards(canvas)
      if (cards.length === 0) return { ok: false, error: '画布上没有实体设定卡：先执行实体设定阶段（storyboard_extract_entities 建卡），或用户手动建带 kind 的 image 节点' }
      try {
        const shots = await splitStoryboard(scriptText, groupByKind(cards), {
          cameraVocabulary: await listCameraVocabulary(),
          shotCountMin: typeof args.shot_count_min === 'number' ? args.shot_count_min : undefined,
          shotCountMax: typeof args.shot_count_max === 'number' ? args.shot_count_max : undefined,
          styleConfig: canvas.activeStyleConfig,
        })
        if (shots.length === 0) return { ok: false, error: '分镜拆分结果为空，可重试或让用户调整剧本' }
        return {
          ok: true,
          data: {
            entity_card_count: cards.length,
            shots: shots.map((s) => ({
              no: s.no,
              shot_size: s.shotSize,
              camera: s.camera,
              location: s.location,
              characters: s.characters,
              props: s.props,
              description: s.description,
              dialogue: s.dialogue,
              prompt: s.prompt,
            })),
          },
        }
      } catch (e) {
        return { ok: false, error: e instanceof Error ? e.message : String(e) }
      }
    },
  },
  {
    name: 'agent_run_generation',
    group: 'generation',
    description: '对画布节点触发生成，会阻塞等待生成完成并返回成败。image：对分镜图节点就地生成（自动收集节点自身内容与上游连线资源作参考）。asset：对实体设定卡节点（image 节点带 kind）生成设定图。video：对目标视频节点就地生成（content.seconds 指定该段时长，须从 agent_get_models 的时长档位中按分镜节奏选取，多数视频模型一次只吃 1-2 张参考图——多分镜连续视频必须每分镜一段、最后 compose 拼接，不要挤进一个节点）。model：仅当用户明确点名生成模型时才传，必须是 agent_get_models 列出的对应类型模型 id；其余情况一律省略，跟随用户默认偏好。compose：对成片合成节点执行拼接，把上游各段视频按画布摆放顺序拼成连续成片；若有上游视频未生成完成会返回错误，此时等待/重试失败的分段即可。',
    parameters: Type.Object({
      panel_id: Type.String({ description: '目标节点 id' }),
      kind: Type.Optional(Type.Union([Type.Literal('image'), Type.Literal('asset'), Type.Literal('video'), Type.Literal('compose')], { description: 'asset=实体设定图；缺省按节点类型推断' })),
      model: Type.Optional(Type.String({ description: '仅用户点名模型时传；必须是 agent_get_models 中该类型的可用模型 id' })),
    }),
    execute: runGeneration,
  },
  {
    name: 'agent_stage_review',
    group: 'write',
    description: '阶段汇报：每完成一个创作阶段（剧本/实体设定/分镜提示词/分镜图/分段视频/成片）调用一次，向用户展示该阶段成果并等待确认。用户"满意"仅代表当前阶段验收通过——返回结果会给出下一阶段名，立即执行它；成片合成是最后一个阶段，成片未完成不得结束任务。用户暂停时停止执行，等用户给调整意见后再继续。',
    parameters: Type.Object({
      stage: Type.String({ description: '阶段名：剧本 / 实体设定 / 分镜提示词 / 分镜图 / 分段视频 / 成片' }),
      summary: Type.String({ description: '本阶段成果摘要（做了什么、产出哪些节点、建议下一步）' }),
    }),
    // 执行由内核拦截（confirm 档弹阶段确认卡片、auto 档直通），此处兜底并机械给出下一阶段指引
    execute: (args) => ({
      ok: true,
      data: { stage: asString(args.stage), approved: true, message: stageApprovedMessage(asString(args.stage)) },
    }),
  },
]

/** OpenAI function calling 格式的工具定义（TypeBox schema 即 JSON Schema，直出；未来 MCP server 复用） */
export function agentToolSchemasOpenAI(tools: AgentTool[] = AGENT_TOOLS) {
  return tools.map((t) => ({
    type: 'function',
    function: { name: t.name, description: t.description, parameters: t.parameters },
  }))
}

/** 按权限档位过滤工具：只读档只挂 read 组 */
export function toolsForMode(mode: 'readonly' | 'confirm' | 'auto', tools: AgentTool[] = AGENT_TOOLS) {
  if (mode === 'readonly') return tools.filter((t) => t.group === 'read')
  return tools
}

export function findAgentTool(name: string, tools: AgentTool[] = AGENT_TOOLS): AgentTool | undefined {
  return tools.find((t) => t.name === name)
}
