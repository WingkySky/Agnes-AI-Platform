/* =====================================================
 * editor_* 剪辑器工具组（批次 3A 对话式剪辑，UI 无关）
 *
 * - 架构=前端工具层复用 lib/editor-commands 命令表（fail-closed 与 UI 编辑零分叉）：
 *   GET 文档 → applyCommands 逐条校验 → PUT 单文档（base_revision 乐观锁）
 * - editor_apply_ops 单一批量工具：全部 op 校验通过才保存（任一失败不落盘，原子）
 * - addClip 缺时长时探测真实时长补齐：duration=0 是「送进剪辑器」草稿占位契约，
 *   编辑器不打开就渲染会被渲染 Plan 剔除 0 片段——agent 链路必须补真值
 * - snapshot_reason 仅本工具层携带：服务端写前快照，兜底整盘还原
 *   （还原=拉快照 data 走本层 applyOps 同款保存链路，无独立还原端点）
 * ===================================================== */

import { Type } from 'typebox'
import type { TSchema } from 'typebox'
import {
  createEditorProject,
  getEditorProject,
  getEditorRenderStatus,
  listEditorProjects,
  previewSubtitleSegments,
  saveEditorDocument,
  submitEditorRender,
} from '@/api/editor'
import { getAsset, listAssets, type UnifiedAsset } from '@/api/assets'
import { applyCanvasOps } from '@/api/canvasWorkspace'
import { applyCommand, cmd, EditorCommandError, EDITOR_OPS, type EditorOp } from '@/lib/editor-commands'
import { probeMediaDuration, probeElementDuration } from '@/lib/editor-media'
import type { EditorClip, EditorDocument, EditorTrack } from '@/lib/editor-types'
import type { AgentToolResult } from './tools'
import { noteToolRoute } from './tools'
import { autoPlacePref, resolveTarget, type CanvasTarget } from './chat-tools'
import { relayCall, listBridgeTargets } from './bridge'
import { useEditorStore } from '@/stores/editor'

const IMAGE_DEFAULT_DURATION = 3.0
const RENDER_POLL_MS = 3000
const RENDER_POLL_MAX = 300 // 3s × 300 = 15 分钟上限，超时返回可续查状态
const OVERVIEW_CLIP_LIMIT = 120
const ASSET_SUMMARY_LIMIT = 50

interface ToolOp {
  op: string
  payload: Record<string, unknown>
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function isEditorOp(v: unknown): v is EditorOp {
  return typeof v === 'string' && (EDITOR_OPS as readonly string[]).includes(v)
}

function round3(n: number): number {
  return Math.round(n * 1000) / 1000
}

function totalDuration(doc: EditorDocument): number {
  return round3(doc.clips.reduce((max, c) => Math.max(max, c.start + c.duration), 0))
}

function trackOf(doc: EditorDocument, trackId: unknown): EditorTrack | undefined {
  return doc.tracks.find((t) => t.id === trackId)
}

function trackEnd(doc: EditorDocument, trackId: string): number {
  return doc.clips
    .filter((c) => c.trackId === trackId)
    .reduce((max, c) => Math.max(max, c.start + c.duration), 0)
}

function genClipId(doc: EditorDocument): string {
  let id = ''
  do {
    id = `clip_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`
  } while (doc.clips.some((c) => c.id === id))
  return id
}

/** 工具层时长探测（可测试注入；缺省=mediabunny → 元素三级探测） */
let durationProber: (url: string) => Promise<number> = (url) => probeMediaDuration(url, probeElementDuration)

/** 测试注入探测桩（传 null 恢复默认） */
export function setEditorDurationProberForTests(prober: ((url: string) => Promise<number>) | null): void {
  durationProber = prober ?? ((url) => probeMediaDuration(url, probeElementDuration))
}

/** 目标解析：显式 uid → 用户名下恰好一个工程 → 报错列工程反问（不猜、不自动建，建走 editor_create_project） */
async function resolveEditorTarget(explicit: unknown): Promise<{ uid: string; title: string } | { error: string }> {
  if (typeof explicit === 'string' && explicit.trim()) {
    return { uid: explicit.trim(), title: explicit.trim() }
  }
  const items = (await listEditorProjects()).items
  if (!items.length) {
    return { error: '还没有剪辑工程：可让我新建（editor_create_project，需提供标题/素材），或让用户在「视频剪辑」页创建' }
  }
  if (items.length === 1) return { uid: items[0].uid, title: items[0].title }
  const lines = items.slice(0, 10).map((p) => `- ${p.uid}「${p.title}」（更新于 ${p.updated_at?.slice(0, 16).replace('T', ' ') ?? '未知'}，成片状态 ${p.render_status}）`)
  return { error: `有 ${items.length} 个剪辑工程，请用户确认要操作哪一个，之后 editing_project_id 传完整 uid 重试：\n${lines.join('\n')}` }
}

function hasTarget(r: { uid: string; title: string } | { error: string }): r is { uid: string; title: string } {
  return !('error' in r)
}

/** 拉素材详情（带缓存；404/无权按缺失败处理，由调用方报错） */
async function fetchAssetMap(ids: number[]): Promise<Map<number, UnifiedAsset>> {
  const map = new Map<number, UnifiedAsset>()
  await Promise.all(
    [...new Set(ids)].map(async (id) => {
      try {
        map.set(id, await getAsset(id))
      } catch {
        /* 素材缺失：调用方按 null 处理 */
      }
    }),
  )
  return map
}

/** apply_ops 核心链路：探测补全 → 命令表 fail-closed 校验（任一失败不落盘）→ PUT（写前快照） */
export async function applyOpsToProject(
  uid: string,
  ops: ToolOp[],
  snapshotReason: string,
): Promise<{ ok: true; doc: EditorDocument; revision: number } | { ok: false; error: string }> {
  const detail = await getEditorProject(uid)
  const doc = detail.document

  // 探测补全（先于命令表校验，使校验面向真实值）：addClip 的轨道/位置/时长缺省值。
  // 同批次 addTrack/removeTrack 的效果累积进工作轨表——否则新轨上的 addClip 看不到轨，
  // 跳过 id/时长补全，命令表报 invalid_payload（真实链路撞过）
  const workingTracks: EditorTrack[] = doc.tracks.map((t) => ({ ...t }))
  const assetCache = new Map<number, UnifiedAsset | null>()
  const assetOf = async (assetId: number): Promise<UnifiedAsset | null> => {
    if (!assetCache.has(assetId)) {
      try {
        assetCache.set(assetId, await getAsset(assetId))
      } catch {
        assetCache.set(assetId, null)
      }
    }
    return assetCache.get(assetId) ?? null
  }
  for (const toolOp of ops) {
    if (toolOp.op === 'addTrack' || toolOp.op === 'removeTrack') {
      const t = isRecord(toolOp.payload.track) ? toolOp.payload.track : null
      if (toolOp.op === 'addTrack' && t && typeof t.id === 'string' && t.id && !workingTracks.some((x) => x.id === t.id)) {
        const kind = t.kind === 'audio' || t.kind === 'subtitle' ? t.kind : 'video'
        workingTracks.push({
          id: t.id, kind, order: workingTracks.length,
          flags: { hidden: false, locked: false, muted: false, solo: false },
        })
      }
      if (toolOp.op === 'removeTrack' && t && typeof t.id === 'string') {
        const i = workingTracks.findIndex((x) => x.id === t.id)
        if (i >= 0) workingTracks.splice(i, 1)
      }
      continue
    }
    if (toolOp.op !== 'addClip') continue
    const clip = toolOp.payload.clip
    if (!isRecord(clip)) continue // 交给命令表 fail-closed
    if (typeof clip.trackId !== 'string' || !clip.trackId) {
      const assetId = typeof clip.assetId === 'number' ? clip.assetId : null
      const kind = assetId != null ? (await assetOf(assetId))?.media_type : null
      const target = workingTracks.find((t) => (kind === 'audio' ? t.kind === 'audio' : t.kind === 'video'))
      if (!target) return { ok: false, error: `没有可用于该素材的轨道（素材类型 ${kind ?? '未知'}），请先用 addTrack 建轨` }
      clip.trackId = target.id
    }
    const track = workingTracks.find((t) => t.id === clip.trackId)
    if (!track) continue // 交给命令表 fail-closed（track_not_found）
    // 音轨/视频轨素材类型守卫：图片 URL 假配音这类错配在入轨前拦下，不给渲染链埋雷
    const guardAssetId = typeof clip.assetId === 'number' ? clip.assetId : null
    if (guardAssetId != null) {
      const asset = await assetOf(guardAssetId)
      if (asset && ((track.kind === 'audio' && asset.media_type !== 'audio') || (track.kind === 'video' && asset.media_type !== 'video' && asset.media_type !== 'image'))) {
        return { ok: false, error: `素材 ${guardAssetId}（${asset.name || '未命名'}）类型为 ${asset.media_type}，与 ${track.kind} 轨不匹配（音频轨只收 audio，视频轨收 video/image）` }
      }
    }
    if (typeof clip.id !== 'string' || !clip.id) clip.id = genClipId(doc)
    if (clip.start === undefined) clip.start = round3(trackEnd(doc, track.id))
    if (!(typeof clip.duration === 'number' && clip.duration > 0)) {
      if (track.kind === 'subtitle') continue // 字幕片段时长必填，交给命令表校验报错
      const assetId = typeof clip.assetId === 'number' ? clip.assetId : null
      if (assetId == null) {
        return { ok: false, error: 'addClip 缺少 duration 且未提供 assetId，无法探测时长（0 时长片段会被渲染剔除）；请从素材库选择 assetId' }
      }
      const asset = await assetOf(assetId)
      if (!asset) return { ok: false, error: `素材 ${assetId} 不存在或无权访问` }
      if (asset.media_type === 'image') {
        clip.duration = IMAGE_DEFAULT_DURATION
      } else {
        const dur = await durationProber(asset.asset_url)
        if (!(dur > 0)) return { ok: false, error: `素材「${asset.name || assetId}」时长探测失败，无法排入时间线（0 时长片段会被渲染剔除）` }
        clip.duration = round3(dur)
      }
    }
  }

  // 命令表统一校验（fail-closed）：任一失败即整体不保存
  let next = doc
  for (let i = 0; i < ops.length; i++) {
    const toolOp = ops[i]
    if (!isEditorOp(toolOp.op)) {
      return { ok: false, error: `第 ${i + 1} 条 op「${String(toolOp.op)}」未知；可用 op：${EDITOR_OPS.join(' / ')}` }
    }
    try {
      next = applyCommand(next, cmd(toolOp.op, toolOp.payload))
    } catch (e) {
      if (e instanceof EditorCommandError) {
        return { ok: false, error: `第 ${i + 1} 条 op「${toolOp.op}」未通过校验（${e.code}）：${e.message}；时间线未做任何修改，可修正后重试` }
      }
      throw e
    }
  }
  const saved = await saveEditorDocument(uid, next, detail.revision, snapshotReason)
  return { ok: true, doc: next, revision: saved.revision }
}

export function applyOpsSummary(doc: EditorDocument, revision: number, okMessage: string): AgentToolResult {
  return {
    ok: true,
    data: {
      revision,
      tracks: doc.tracks.length,
      clips: doc.clips.length,
      total_duration: totalDuration(doc),
      message: okMessage,
    },
  }
}

/** 写类工具执行路由（批次 2 反向控制桥）：
 *  本地已加载该工程（聊天宿主开在剪辑器页）→ 现实现 + 即时远端合并（免等 5s 轮询）；
 *  桥上有该工程（剪辑器页在别的标签页开着）→ 中继到页面执行（页面侧同函数，实时可见）；
 *  离线 → 现实现（editor 工具本就页外可执行，3A 语义不变）。 */
async function runEditorWrite(
  uid: string,
  bridgeTool: string,
  bridgeArgs: Record<string, unknown>,
  httpImpl: () => Promise<AgentToolResult>,
  callId?: string,
  ctx?: unknown,
): Promise<AgentToolResult> {
  let store: ReturnType<typeof useEditorStore> | null = null
  try {
    store = useEditorStore()
  } catch {
    // 无活动 pinia（单测环境）按离线路径走
  }
  if (store && store.uid === uid) {
    noteToolRoute(ctx, callId, 'local')
    const r = await httpImpl()
    if (r.ok) store.pollRemoteNow()
    return r
  }
  noteToolRoute(ctx, callId, 'bridge')
  try {
    const targets = await listBridgeTargets()
    if (targets.some((t) => t.host === 'editor' && t.target_id === uid)) {
      const outcome = await relayCall('editor', uid, bridgeTool, bridgeArgs)
      if (outcome.routed === 'relay') return outcome.result
    }
  } catch {
    // targets 不可用退回直连实现
  }
  noteToolRoute(ctx, callId, 'server')
  return httpImpl()
}

// ---------- editor_list_projects ----------

const editorListProjectsTool = {
  name: 'editor_list_projects',
  group: 'read' as const,
  description:
    '列出用户的剪辑工程（uid/标题/更新时间/成片状态）。用户提到"剪辑工程/时间线/成片"但不确定操作哪个工程时，' +
    '或剪辑器工具提示需确认目标工程时调用。',
  parameters: Type.Object({}),
  execute: async (): Promise<AgentToolResult> => {
    try {
      const { items } = await listEditorProjects()
      return {
        ok: true,
        data: {
          projects: items.map((p) => ({
            uid: p.uid,
            title: p.title,
            revision: p.revision,
            render_status: p.render_status,
            final_url: p.final_url,
            updated_at: p.updated_at,
          })),
          message: items.length
            ? `共 ${items.length} 个剪辑工程；后续工具的 editing_project_id 传其中的 uid`
            : '还没有剪辑工程（可在「视频剪辑」页创建，或让我用 editor_create_project 新建）',
        },
      }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  },
}

// ---------- editor_get_overview ----------

const editorGetOverviewTool = {
  name: 'editor_get_overview',
  group: 'read' as const,
  description:
    '读取剪辑工程全貌：轨道与片段（位置/时长/属性摘要）、素材引用映射（assetId→名称/类型）、素材库摘要（选取新素材用）。' +
    '在做任何时间线修改（editor_apply_ops）、生成字幕或回答工程内容问题前先调用。',
  parameters: Type.Object({
    editing_project_id: Type.Optional(Type.String({ description: '剪辑工程 uid（缺省=用户名下唯一工程）' })),
    media_type: Type.Optional(Type.String({ description: '素材库摘要按类型筛选：image / video / audio' })),
  }),
  execute: async (args: Record<string, unknown>): Promise<AgentToolResult> => {
    const target = await resolveEditorTarget(args.editing_project_id)
    if (!hasTarget(target)) return { ok: false, error: target.error }
    try {
      const uid = target.uid
      const detail = await getEditorProject(uid)
      const doc = detail.document
      const clipOf = (c: EditorClip) => ({
        id: c.id,
        track: c.trackId,
        asset_id: c.assetId,
        start: c.start,
        duration: c.duration,
        ...(c.trimStart ? { trim_start: c.trimStart } : {}),
        ...(Object.keys(c.props ?? {}).length ? { props: c.props } : {}),
        ...(typeof c.text === 'string' ? { text: c.text } : {}),
      })
      const referencedIds = [...new Set(doc.clips.map((c) => c.assetId).filter((v): v is number => typeof v === 'number'))]
      const library = await listAssets({ page_size: 100 })
      const nameOf = (id: number): string | undefined => library.items.find((a) => a.id === id)?.name
      const libraryItems = library.items
        .filter((a) => !args.media_type || a.media_type === args.media_type)
        .slice(0, ASSET_SUMMARY_LIMIT)
        .map((a) => ({ asset_id: a.id, name: a.name, media_type: a.media_type }))
      return {
        ok: true,
        data: {
          editing_project_id: uid,
          title: detail.title,
          revision: detail.revision,
          render_status: detail.render_status,
          ...(detail.final_url ? { final_url: detail.final_url } : {}),
          timebase: doc.timebase,
          tracks: doc.tracks.map((t) => ({
            id: t.id,
            kind: t.kind,
            order: t.order,
            ...((t.flags.hidden || t.flags.locked || t.flags.muted || t.flags.solo) ? { flags: t.flags } : {}),
            ...(t.transitions?.length ? { transitions: t.transitions } : {}),
          })),
          clips: doc.clips.slice(0, OVERVIEW_CLIP_LIMIT).map(clipOf),
          ...(doc.clips.length > OVERVIEW_CLIP_LIMIT
            ? { note: `仅列前 ${OVERVIEW_CLIP_LIMIT} 个片段，共 ${doc.clips.length} 个` } : {}),
          total_duration: totalDuration(doc),
          referenced_assets: referencedIds.map((id) => ({ asset_id: id, name: nameOf(id) ?? '(超出摘要范围)' })),
          asset_library: {
            total: library.total,
            items: libraryItems,
            message: 'addClip 的 clip.assetId 从 asset_library 或 referenced_assets 中选取',
          },
        },
      }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  },
}

// ---------- editor_create_project ----------

const editorCreateProjectTool = {
  name: 'editor_create_project',
  group: 'write' as const,
  description:
    '新建剪辑工程。title 必填；asset_ids 可选（素材库 asset_id 按播放顺序列出，视频/图片排主轨、音频排音频轨自动成草稿）。' +
    '创建后返回 uid，后续工具用该 uid 操作；草稿片段时长在打开编辑器时自动补正。',
  parameters: Type.Object({
    title: Type.String({ description: '工程标题' }),
    work_id: Type.Optional(Type.Number({ description: '挂靠作品 id（可选）' })),
    asset_ids: Type.Optional(Type.Array(Type.Number(), { maxItems: 50, description: '按顺序排入时间线的素材 id（素材库 asset_id，非片段 id）' })),
  }),
  execute: async (args: Record<string, unknown>): Promise<AgentToolResult> => {
    const title = typeof args.title === 'string' ? args.title.trim() : ''
    if (!title) return { ok: false, error: '缺少工程标题 title' }
    const assetIds = Array.isArray(args.asset_ids) ? args.asset_ids.filter((v): v is number => typeof v === 'number') : []
    try {
      const project = await createEditorProject({
        title,
        work_id: typeof args.work_id === 'number' ? args.work_id : undefined,
        asset_ids: assetIds.length ? assetIds : undefined,
      })
      return {
        ok: true,
        data: {
          editing_project_id: project.uid,
          title: project.title,
          clips: project.document.clips.length,
          message: `剪辑工程「${project.title}」已创建（uid ${project.uid}），后续工具 editing_project_id 传该 uid`,
        },
      }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  },
}

// ---------- editor_apply_ops ----------

const editorApplyOpsTool = {
  name: 'editor_apply_ops',
  group: 'write' as const,
  description:
    '对剪辑工程时间线批量执行命令（唯一写入口）。先 editor_get_overview 读取现状，再一次性提交全部 ops；' +
    '全部校验通过才保存（任一失败整体不落盘）。op 与 payload：' +
    'addClip {"clip":{assetId, trackId?, start?, duration?, trimStart?, props?}}（trackId/start/id 可省——自动选轨并排在轨尾；' +
    '视频/音频 duration 可省自动探测真实时长，图片默认 3 秒；assetId 必须是素材库已有素材——agent 生成的配音/成片会自动入库并返回 asset_id；' +
    '音频素材只能进音频轨、视频/图片素材进视频轨，类型不符会被拒绝）；' +
    'moveClip {clipId,start,trackId?}；trimClip {clipId,start?,duration?,trimStart?}；splitClip {clipId,at,newId}；' +
    'removeClip {clipId}；detachAudio {clipId,trackId,newId}（视频片段音画分离，trackId=目标音频轨）；' +
    'setClipProperty {clipId,props:{speed?,volume?,fadeIn?,fadeOut?,muted?,rect?}}（键传 null 删除）；' +
    'addSubtitle {clip:{id,trackId,start,duration,text}}；removeSubtitle {clipId}；' +
    'rebuildSubtitleClips {trackId,clips:[{id,start,duration,text}]}（全量替换该字幕轨）；' +
    'addTrack {track:{id,kind,order?}}；removeTrack {trackId}（非空轨拒绝）；' +
    'setTrackFlags {trackId,flags:{hidden?,locked?,muted?,solo?}}；moveTrack {trackId,toIndex}；' +
    'setTransition {trackId,afterClipId,type:crossfade|fade|wipe,duration,transitionId}（同轨紧随片段衔接点）；' +
    'removeTransition {trackId,afterClipId}；setClipEffects {clipId,effects:[{id,type:grayscale|blur,strength}]}。' +
    '注意：视频/音频轨禁止重叠（overlap 拒绝）；转场只对同轨相邻片段生效。',
  parameters: Type.Object({
    editing_project_id: Type.Optional(Type.String({ description: '剪辑工程 uid（缺省=用户名下唯一工程）' })),
    ops: Type.Array(Type.Object({
      op: Type.String({ description: '命令名，见工具描述的 op 清单' }),
      payload: Type.Record(Type.String(), Type.Unknown(), { description: '命令参数（addClip 传 {"clip":{...}}）' }),
    }), { minItems: 1, maxItems: 40, description: '按顺序执行的批量命令' }),
  }),
  execute: async (args: Record<string, unknown>, ctx: unknown, callId?: string): Promise<AgentToolResult> => {
    const target = await resolveEditorTarget(args.editing_project_id)
    if (!hasTarget(target)) return { ok: false, error: target.error }
    const ops = (Array.isArray(args.ops) ? args.ops : []).filter(isRecord).map((o) => ({
      op: typeof o.op === 'string' ? o.op : '',
      payload: isRecord(o.payload) ? o.payload : {},
    }))
    if (!ops.length) return { ok: false, error: '缺少 ops 参数' }
    return runEditorWrite(target.uid, 'editor_apply_ops', { editing_project_id: target.uid, ops }, async () => {
      const r = await applyOpsToProject(target.uid, ops, 'agent_edit')
      if (!r.ok) return { ok: false, error: r.error }
      return applyOpsSummary(r.doc, r.revision, `已应用 ${ops.length} 条命令并保存（revision ${r.revision}）`)
    }, callId, ctx)
  },
}

// ---------- editor_generate_subtitles ----------

const editorGenerateSubtitlesTool = {
  name: 'editor_generate_subtitles',
  group: 'write' as const,
  description:
    '对剪辑工程的音频轨做 whisper 转写并生成字幕片段（全量替换字幕轨内容）。' +
    '音频轨不唯一时用 track_id 指定（editor_get_overview 可查）。生成后可用 editor_apply_ops 的 rebuildSubtitleClips 微调文本。',
  parameters: Type.Object({
    editing_project_id: Type.Optional(Type.String({ description: '剪辑工程 uid（缺省=用户名下唯一工程）' })),
    track_id: Type.Optional(Type.String({ description: '要转写的音频轨 id（缺省=唯一音频轨）' })),
  }),
  execute: async (args: Record<string, unknown>, ctx: unknown, callId?: string): Promise<AgentToolResult> => {
    const target = await resolveEditorTarget(args.editing_project_id)
    if (!hasTarget(target)) return { ok: false, error: target.error }
    return runEditorWrite(target.uid, 'editor_generate_subtitles', { editing_project_id: target.uid, track_id: args.track_id }, async () => {
      const uid = target.uid
      const detail = await getEditorProject(uid)
      const audioTracks = detail.document.tracks.filter((t) => t.kind === 'audio')
      const wanted = typeof args.track_id === 'string' ? args.track_id : ''
      const audioTrack = wanted
        ? audioTracks.find((t) => t.id === wanted)
        : audioTracks.length === 1 ? audioTracks[0] : undefined
      if (!audioTrack) {
        return {
          ok: false,
          error: wanted
            ? `音频轨 ${wanted} 不存在；现有音频轨：${audioTracks.map((t) => t.id).join('、') || '无'}`
            : `工程有 ${audioTracks.length} 条音频轨，请用 track_id 指定：${audioTracks.map((t) => t.id).join('、')}`,
        }
      }
      const subtitleTrack = detail.document.tracks.find((t) => t.kind === 'subtitle')
      if (!subtitleTrack) return { ok: false, error: '工程没有字幕轨，请先 editor_apply_ops 执行 addTrack 新建 subtitle 轨' }
      const { segments } = await previewSubtitleSegments(uid, audioTrack.id)
      if (!segments.length) return { ok: false, error: '该音频轨没有转写出任何语音内容' }
      const cues = segments.map((s, i) => ({
        id: `sub_${i + 1}_${Date.now().toString(36)}`,
        start: round3(s.start),
        duration: round3(Math.max(0.1, s.end - s.start)),
        text: s.text,
      }))
      const r = await applyOpsToProject(uid, [
        { op: 'rebuildSubtitleClips', payload: { trackId: subtitleTrack.id, clips: cues } },
      ], 'agent_subtitles')
      if (!r.ok) return { ok: false, error: r.error }
      return applyOpsSummary(r.doc, r.revision, `已按转写生成 ${cues.length} 条字幕（轨 ${subtitleTrack.id}，revision ${r.revision}）`)
    }, callId, ctx)
  },
}

// ---------- editor_render ----------

const editorRenderTool = {
  name: 'editor_render',
  group: 'generation' as const,
  description:
    '提交剪辑工程渲染成片（服务端 ffmpeg，耗时数分钟），等待完成后回复成片链接。' +
    'place_on_canvas 传 true 时成片同时放入云端画布（缺省按用户「生成后自动放入画布」偏好）。' +
    '渲染前建议先 editor_get_overview 确认时间线内容符合预期。',
  parameters: Type.Object({
    editing_project_id: Type.Optional(Type.String({ description: '剪辑工程 uid（缺省=用户名下唯一工程）' })),
    place_on_canvas: Type.Optional(Type.Boolean({ description: '是否把成片放入云端画布（缺省按用户偏好开关）' })),
    canvas_workspace_id: Type.Optional(Type.String({ description: '落画布的目标工作区 id（缺省系统自动解析）' })),
  }),
  execute: async (args: Record<string, unknown>, ctx: unknown): Promise<AgentToolResult> => {
    const target = await resolveEditorTarget(args.editing_project_id)
    if (!hasTarget(target)) return { ok: false, error: target.error }
    try {
      const uid = target.uid
      const autoPlace = await autoPlacePref(ctx)
      const placeOnCanvas = typeof args.place_on_canvas === 'boolean' ? args.place_on_canvas : autoPlace
      let canvasTarget: Awaited<ReturnType<typeof resolveTarget>> = null
      if (placeOnCanvas) {
        canvasTarget = await resolveTarget(ctx, args.canvas_workspace_id)
        if (!canvasTarget) return { ok: false, error: '没有可用的云端画布工作区：请先让用户在画布页登录并选择工作区，或不落画布直接渲染' }
      }
      await submitEditorRender(uid)
      for (let i = 0; i < RENDER_POLL_MAX; i++) {
        await new Promise((resolve) => setTimeout(resolve, RENDER_POLL_MS))
        const status = await getEditorRenderStatus(uid)
        if (status.render_status === 'succeeded') {
          const finalUrl = status.final_url ?? ''
          const absolute = typeof location !== 'undefined' && finalUrl
            ? new URL(finalUrl, location.origin).href
            : finalUrl
          let placedMessage = ''
          if (canvasTarget && finalUrl) {
            try {
              await applyCanvasOps(canvasTarget.workspaceId, [{
                op: 'add_panel',
                type: 'video',
                name: target.title || '剪辑成片',
                content: { status: 'success', content: finalUrl },
              }])
              placedMessage = `，成片已放入画布「${canvasTarget.workspaceName || canvasTarget.workspaceId}」`
            } catch {
              placedMessage = '（落画布失败，成片链接仍有效）'
            }
          }
          return {
            ok: true,
            data: {
              render_status: 'succeeded',
              final_url: absolute,
              message: `渲染完成：${absolute}${placedMessage}`,
            },
          }
        }
        if (status.render_status === 'failed') {
          return { ok: false, error: `渲染失败：${status.render_error ?? '未知错误'}` }
        }
      }
      return {
        ok: true,
        data: {
          render_status: 'rendering',
          message: `渲染仍在进行中（已等待超时），可稍后用 editor_get_render_status 查询结果`,
        },
      }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  },
}

// ---------- editor_get_render_status ----------

const editorGetRenderStatusTool = {
  name: 'editor_get_render_status',
  group: 'read' as const,
  description: '查询剪辑工程渲染状态（idle/rendering/succeeded/failed）与成片链接。',
  parameters: Type.Object({
    editing_project_id: Type.Optional(Type.String({ description: '剪辑工程 uid（缺省=用户名下唯一工程）' })),
  }),
  execute: async (args: Record<string, unknown>): Promise<AgentToolResult> => {
    const target = await resolveEditorTarget(args.editing_project_id)
    if (!hasTarget(target)) return { ok: false, error: target.error }
    try {
      const status = await getEditorRenderStatus(target.uid)
      return {
        ok: true,
        data: {
          ...status,
          message: status.render_status === 'succeeded' && status.final_url
            ? `成片：${status.final_url}`
            : `渲染状态：${status.render_status}`,
        },
      }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  },
}

/** 剪辑器工具组统一形状（ctx 可选：页外 HTTP 路径不依赖宿主上下文；桥执行器按名单分发用） */
export interface EditorHostTool {
  name: string
  group: 'read' | 'write' | 'generation'
  description: string
  parameters: TSchema
  execute: (args: Record<string, unknown>, ctx?: unknown) => Promise<AgentToolResult>
}

/** 剪辑器工具组（追加到 CHAT_TOOLS 末尾，测试按索引取用） */
export const EDITOR_TOOLS: EditorHostTool[] = [
  editorListProjectsTool,
  editorGetOverviewTool,
  editorCreateProjectTool,
  editorApplyOpsTool,
  editorGenerateSubtitlesTool,
  editorRenderTool,
  editorGetRenderStatusTool,
]
