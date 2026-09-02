/* =====================================================
 * 分镜批量派生编排（无限画布 script 节点，LibTV P0 复刻）
 * - prompt 拼装 / config 节点派生 / 网格布局 / lineage 记录
 * - 生成复用 canvas-generation 执行器（waitFor + 并发池限流）
 * - 数据全部存画布节点 content（localforage），后端无状态
 * ===================================================== */

import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from '@/i18n'
import { useCanvasStore, type CanvasPanel } from '@/stores/canvas'
import { usePreferencesStore } from '@/stores/preferences'
import { getModelParams } from '@/config/model-params'
import { composeCanvasVideos } from '@/api/canvas'
import {
  executeInNodeGeneration,
  executeInNodeVideoGeneration,
  getUpstreamNodes,
  readPanelGenParams,
} from '@/lib/canvas-generation'
import { estimateCanvasCost, checkCreditsBeforeGenerate } from '@/lib/canvas-credits'
import { getErrorMessage } from '@/lib/type-helpers'

/** 单个分镜（存于 script 节点 content.shots；characters/location 与资产卡按名关联） */
export interface CanvasShot {
  id: string
  no: number
  /** 时长（秒，视频生成用，4–12） */
  duration: number
  shotSize: string
  camera: string
  description: string
  dialogue: string
  /** 出场角色名列表（资产卡按名命中） */
  characters: string[]
  /** 场景名（资产卡按名命中） */
  location: string
  /** 跨镜头衔接：本镜头首帧以上一镜尾帧为底图续接生成（第 1 镜无效） */
  linkPrev: boolean
}

/** 资产卡（角色/场景参考，存于 script 节点 content.assets，画布本地） */
export interface ShotAsset {
  id: string
  name: string
  description: string
  imageUrl: string
}

/** 脚本节点资产集合 */
export interface ScriptAssets {
  characters: ShotAsset[]
  scenes: ShotAsset[]
}

/** 派生节点出处（存于派生出的节点自身 content.lineage：分镜图为直出 image 节点，视频为 config 节点） */
export interface ShotLineage {
  kind: 'image' | 'video'
  scriptPanelId: string
  shotId: string
  shotNo: number
  /**
   * 帧角色（仅 image lineage）：first=首帧（缺省），last=尾帧（keyframes 结束帧 + 跨镜头衔接底图），
   * prev=前段帧（动作开始前的画面时间推演），chain=后向链帧（画面链长视频的分段锚点）
   */
  role?: 'first' | 'last' | 'prev' | 'chain'
  /** 链上时间序号：首帧 seq 0、尾帧 seq 1、链帧 seq = 2,3,…（'prev' 视为 seq -1）；视频分段节点复用记录段序 */
  chainSeq?: number
}

/* ---------- 常量 ---------- */
const MAX_SHOTS = 30
const IMAGE_CONCURRENCY = 3
const VIDEO_CONCURRENCY = 2
// 网格布局：script 节点右侧 3 列；分镜直出后每镜头只有 1 个节点，列距按节点宽 + 间隙
const GRID_COLS = 3
const IMG_CONFIG_W = 300
const IMG_CONFIG_H = 320
const IMG_PITCH_X = 400
const IMG_PITCH_Y = 380
const VIDEO_CONFIG_W = 320
const VIDEO_CONFIG_H = 300
// 视频直出节点列距（B2 将改为覆盖在源图上，此处为网格过渡方案）
const VIDEO_PITCH_X = VIDEO_CONFIG_W + 40

/* script 节点 content 上三套生成参数的分区键：向导参数栏写入，批量派生读取 */
export const ASSET_IMAGE_PARAMS_KEY = 'asset_image_params'
export const SHOT_IMAGE_PARAMS_KEY = 'shot_image_params'
export const SHOT_VIDEO_PARAMS_KEY = 'shot_video_params'

/* ---------- content 读取（持久化边界，用类型守卫收敛） ---------- */

/** 类型守卫：任意值是否为普通对象（可按 Record<string, unknown> 安全读取） */
function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null
}

function readString(content: Record<string, unknown> | undefined, key: string): string {
  const v = content?.[key]
  return typeof v === 'string' ? v : ''
}

/** 读取派生 config 节点的 lineage，结构不符返回 null（非法 role/chainSeq 忽略） */
export function readLineage(panel: { content?: Record<string, unknown> }): ShotLineage | null {
  const v = panel.content?.lineage
  if (!isRecord(v)) return null
  const kind = v.kind
  if (kind !== 'image' && kind !== 'video') return null
  if (typeof v.scriptPanelId !== 'string' || typeof v.shotId !== 'string' || typeof v.shotNo !== 'number') return null
  const role = v.role === 'first' || v.role === 'last' || v.role === 'prev' || v.role === 'chain' ? v.role : undefined
  const chainSeq = typeof v.chainSeq === 'number' && Number.isFinite(v.chainSeq) ? v.chainSeq : undefined
  return { kind, scriptPanelId: v.scriptPanelId, shotId: v.shotId, shotNo: v.shotNo, role, ...(chainSeq !== undefined ? { chainSeq } : {}) }
}

/** 读取 script 节点的分镜列表（结构异常的条目跳过，序号/时长缺失按顺序补齐） */
export function readShots(panel: { content?: Record<string, unknown> }): CanvasShot[] {
  const raw = panel.content?.shots
  if (!Array.isArray(raw)) return []
  const shots: CanvasShot[] = []
  for (const item of raw) {
    if (!isRecord(item)) continue
    if (typeof item.id !== 'string' || typeof item.description !== 'string') continue
    shots.push({
      id: item.id,
      no: typeof item.no === 'number' ? item.no : shots.length + 1,
      duration: typeof item.duration === 'number' ? item.duration : 5,
      shotSize: typeof item.shotSize === 'string' ? item.shotSize : '中景',
      camera: typeof item.camera === 'string' ? item.camera : '',
      description: item.description,
      dialogue: typeof item.dialogue === 'string' ? item.dialogue : '',
      characters: Array.isArray(item.characters)
        ? item.characters.filter((c): c is string => typeof c === 'string')
        : [],
      location: typeof item.location === 'string' ? item.location : '',
      linkPrev: item.linkPrev === true,
    })
  }
  return shots
}

/** 读取 script 节点资产（角色/场景，结构异常条目跳过） */
export function readAssets(panel: { content?: Record<string, unknown> }): ScriptAssets {
  const out: ScriptAssets = { characters: [], scenes: [] }
  const raw = panel.content?.assets
  if (!isRecord(raw)) return out
  for (const key of ['characters', 'scenes'] as const) {
    const list = raw[key]
    if (!Array.isArray(list)) continue
    for (const item of list) {
      if (!isRecord(item) || typeof item.id !== 'string') continue
      out[key].push({
        id: item.id,
        name: typeof item.name === 'string' ? item.name : '',
        description: typeof item.description === 'string' ? item.description : '',
        imageUrl: typeof item.imageUrl === 'string' ? item.imageUrl : '',
      })
    }
  }
  return out
}

/* ---------- prompt 拼装 ---------- */

/** 资产卡 -> 设定文本（"名称：描述"） */
function assetText(a: ShotAsset): string {
  return a.name ? `${a.name}：${a.description}` : a.description
}

/** 资产集合 -> prompt 设定文本上下文（派生与向导预览共用） */
function buildAssetContexts(assets: ScriptAssets): { characters: string[]; scenes: string[] } {
  return {
    characters: assets.characters.map(assetText).filter(Boolean),
    scenes: assets.scenes.map(assetText).filter(Boolean),
  }
}

/* ---------- 分镜与资产的关联（LLM 提取预填 + 按镜头命中注入） ---------- */

function newAssetId(): string {
  return `asset_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`
}

/** 把 LLM 提取的资产按名（trim 后）去重追加到已有卡；无新增时返回 null，调用方跳过写入 */
export function mergeExtractedAssets(
  current: ScriptAssets,
  extracted?: { characters?: Array<{ name?: unknown; description?: unknown }>; scenes?: Array<{ name?: unknown; description?: unknown }> } | null,
): ScriptAssets | null {
  const trim = (v: unknown) => (typeof v === 'string' ? v.trim() : '')
  const pick = (existing: ShotAsset[], items?: Array<{ name?: unknown; description?: unknown }>): ShotAsset[] =>
    (items || [])
      .map((item) => ({ name: trim(item?.name), description: trim(item?.description) }))
      .filter((item) => item.name && !existing.some((a) => a.name.trim() === item.name))
      .map((item) => ({ id: newAssetId(), name: item.name, description: item.description, imageUrl: '' }))
  const characters = pick(current.characters, extracted?.characters)
  const scenes = pick(current.scenes, extracted?.scenes)
  if (characters.length === 0 && scenes.length === 0) return null
  return { characters: [...current.characters, ...characters], scenes: [...current.scenes, ...scenes] }
}

/** 某资产卡在分镜中的出场镜头号（角色按 characters 含名，场景按 location 同名） */
export function shotNosForAsset(shots: CanvasShot[], kind: 'characters' | 'scenes', name: string): number[] {
  const trimmed = name.trim()
  if (!trimmed) return []
  return shots
    .filter((s) => (kind === 'characters' ? s.characters.includes(trimmed) : s.location.trim() === trimmed))
    .map((s) => s.no)
}

/** 镜头级上下文：设定文本 + 命中资产参考图（未标注维取全量；标注后命中为空时文本回退全量、图片不并入，避免带错人） */
export interface ShotContexts {
  characters: string[]
  scenes: string[]
  characterImages: string[]
  sceneImages: string[]
}

export function buildShotContexts(shot: CanvasShot, assets: ScriptAssets, extraCharacters: string[] = []): ShotContexts {
  const all = buildAssetContexts(assets)
  const extras = extraCharacters.filter(Boolean)
  const shotNames = shot.characters.map((c) => c.trim()).filter(Boolean)
  const location = shot.location.trim()

  const hitCharacters = shotNames.length > 0
    ? assets.characters.filter((a) => shotNames.includes(a.name.trim()))
    : assets.characters
  const hitScenes = location
    ? assets.scenes.filter((a) => a.name.trim() === location)
    : assets.scenes
  const hitCharacterTexts = hitCharacters.map(assetText).filter(Boolean)
  const hitSceneTexts = hitScenes.map(assetText).filter(Boolean)

  return {
    characters: [...extras, ...(hitCharacterTexts.length > 0 ? hitCharacterTexts : all.characters)],
    scenes: hitSceneTexts.length > 0 ? hitSceneTexts : all.scenes,
    characterImages: hitCharacters.map((a) => a.imageUrl).filter(Boolean),
    sceneImages: hitScenes.map((a) => a.imageUrl).filter(Boolean),
  }
}

/** 资产参考图 prompt：纯设定图——角色三视图（正/侧/背）、场景空镜无人物（不注入剧情，避免把其他角色/动作污染进参考图） */
export function buildAssetImagePrompt(
  scriptPanel: CanvasPanel,
  asset: ShotAsset,
  kind: 'characters' | 'scenes',
  label: string,
): string {
  const style = readString(scriptPanel.content, 'style')
  const purity = kind === 'characters'
    ? '同一角色三视图设定图：正面、侧面、背面全身立绘并排排列，三个视角为同一人物，发型服装完全一致，纯色简洁背景，画面中只有这一个角色，无其他人物，无文字'
    : '空场景环境全景，画面中无人物出现，无文字'
  const lines = [`${label}：${asset.name || ''}`.trim(), asset.description.trim(), purity]
  if (style) lines.push(`画面风格：${style}`)
  return lines.filter(Boolean).join('\n')
}

/** 分镜图 prompt：画面描述 + 景别/运镜 + 风格 + 角色/场景设定 */
export function buildShotImagePrompt(scriptPanel: CanvasPanel, shot: CanvasShot, contexts: { characters: string[]; scenes: string[] }): string {
  const lines = [shot.description]
  if (shot.shotSize) lines.push(`景别：${shot.shotSize}`)
  if (shot.camera) lines.push(`运镜：${shot.camera}`)
  const style = readString(scriptPanel.content, 'style')
  if (style) lines.push(`画面风格：${style}`)
  if (contexts.characters.length > 0) lines.push(`角色设定：${contexts.characters.join('；')}`)
  if (contexts.scenes.length > 0) lines.push(`场景设定：${contexts.scenes.join('；')}`)
  return lines.filter(Boolean).join('\n')
}

/** 分镜视频 prompt：画面描述 + 运镜 */
export function buildShotVideoPrompt(shot: CanvasShot): string {
  const lines = [shot.description]
  if (shot.camera) lines.push(`运镜：${shot.camera}`)
  return lines.join('\n')
}

/** 尾帧图 prompt 附加行：动作结束瞬间的收尾状态 */
const TAIL_PROMPT_LINE = '此图为该镜头动作的结束瞬间：与首帧同场景、同人物、同机位，人物动作处于收尾状态'
/** 衔接首帧 prompt 附加行：承接上一镜尾帧 */
const LINK_PROMPT_LINE = '画面承接首张参考图的场景、人物与状态，为本镜头的开始瞬间'
/** 前段帧 prompt 附加行：动作开始前的起始前状态（N = 镜头时长，画面时间推演向前延展） */
const prevPromptLine = (n: number) => `此画面为该镜头动作开始前约${n}秒的瞬间：与主画面同场景、同人物、同机位，动作处于尚未开始的起始前状态`
/** 链帧 prompt 附加行：动作结束后第 k 个时段的自然延续（k = chainSeq - 1，每段一个视频时长档位） */
const chainPromptLine = (k: number) => `此画面为该镜头动作结束后第${k}个时段的画面：同场景、同人物、同机位，动作从上一时刻状态自然继续推进`
/** 分段视频 prompt 附加行：段序标注（相邻链帧互为首尾帧，段间共享帧保证 concat 连续） */
const segmentPromptLine = (i: number, total: number) => `本段为该动作的第${i}/${total}段，从起始帧动作状态自然延续到结束帧动作状态`

/* ---------- 派生节点查找 ---------- */

/**
 * 某脚本节点指定 kind 的全部派生节点（自身带 lineage）
 * - image：直出的分镜图节点（type === 'image'）与存量/手搭场景的 config 派生节点并存，两者都识别
 * - video：config 节点（本期视频派生仍走 config，第二阶段再变）
 */
export function findDerivedPanels(scriptPanelId: string, kind: 'image' | 'video'): Array<{ panel: CanvasPanel; lineage: ShotLineage }> {
  const store = useCanvasStore()
  const result: Array<{ panel: CanvasPanel; lineage: ShotLineage }> = []
  for (const p of store.panels) {
    const matches = kind === 'image'
      ? p.type === 'image' || p.type === 'config'
      : p.type === 'config'
    if (!matches) continue
    const lineage = readLineage(p)
    if (lineage && lineage.scriptPanelId === scriptPanelId && lineage.kind === kind) {
      result.push({ panel: p, lineage })
    }
  }
  return result
}

/** 某镜头的首帧图节点（role 为 first/缺省；前段帧/尾帧/链帧不算，无则 null） */
export function findFirstFramePanel(scriptPanelId: string, shotId: string): CanvasPanel | null {
  const hit = findDerivedPanels(scriptPanelId, 'image').find(
    (d) => d.lineage.shotId === shotId && (d.lineage.role === undefined || d.lineage.role === 'first'),
  )
  return hit?.panel || null
}

/** 某镜头的尾帧图节点（无则 null） */
export function findTailFramePanel(scriptPanelId: string, shotId: string): CanvasPanel | null {
  const hit = findDerivedPanels(scriptPanelId, 'image').find((d) => d.lineage.shotId === shotId && d.lineage.role === 'last')
  return hit?.panel || null
}

/** 某镜头的前段帧图节点（无则 null） */
export function findPrevFramePanel(scriptPanelId: string, shotId: string): CanvasPanel | null {
  const hit = findDerivedPanels(scriptPanelId, 'image').find((d) => d.lineage.shotId === shotId && d.lineage.role === 'prev')
  return hit?.panel || null
}

/** 某镜头指定序号的后向链帧图节点（无则 null） */
function findChainFramePanel(scriptPanelId: string, shotId: string, chainSeq: number): CanvasPanel | null {
  const hit = findDerivedPanels(scriptPanelId, 'image').find(
    (d) => d.lineage.shotId === shotId && d.lineage.role === 'chain' && d.lineage.chainSeq === chainSeq,
  )
  return hit?.panel || null
}

/** 某镜头的全部后向链帧图节点（按 chainSeq 升序） */
export function findChainFramePanels(scriptPanelId: string, shotId: string): CanvasPanel[] {
  return findDerivedPanels(scriptPanelId, 'image')
    .filter((d) => d.lineage.shotId === shotId && d.lineage.role === 'chain' && typeof d.lineage.chainSeq === 'number')
    .sort((a, b) => (a.lineage.chainSeq || 0) - (b.lineage.chainSeq || 0))
    .map((d) => d.panel)
}

/** 某脚本节点各镜头的派生状态（shotId -> 是否已派生首帧/视频，供面板状态点显示） */
export function getDerivedShotIds(scriptPanelId: string): { image: Set<string>; video: Set<string> } {
  return {
    image: new Set(
      findDerivedPanels(scriptPanelId, 'image')
        .filter((d) => d.lineage.role === undefined || d.lineage.role === 'first')
        .map((d) => d.lineage.shotId),
    ),
    video: new Set(findDerivedPanels(scriptPanelId, 'video').map((d) => d.lineage.shotId)),
  }
}

/** 派生 config 节点已生成成功的结果媒体节点 */
function findResultNode(configPanelId: string, type: 'image' | 'video'): CanvasPanel | null {
  const store = useCanvasStore()
  return store.panels.find(
    (p) => p.type === type && p.content?.sourceFrom === configPanelId && p.content?.status === 'success',
  ) || null
}

/**
 * 节点 -> 其分镜 lineage 信息（供工具栏/视图识别分镜派生节点）
 * - 直出节点（分镜图/视频自身带 lineage）：configPanel 即节点自身
 * - 其余：按 content.sourceFrom 反查来源 config 节点
 */
export function getShotLineageInfo(
  panel: { id?: string; content?: Record<string, unknown> },
): { configPanel: CanvasPanel; lineage: ShotLineage } | null {
  const store = useCanvasStore()
  const own = readLineage(panel)
  if (own) {
    const self = panel.id ? store.panels.find((p) => p.id === panel.id) : undefined
    return self ? { configPanel: self, lineage: own } : null
  }
  const sourceFrom = panel.content?.sourceFrom
  if (typeof sourceFrom !== 'string') return null
  const configPanel = store.panels.find((p) => p.id === sourceFrom)
  if (!configPanel || configPanel.type !== 'config') return null
  const lineage = readLineage(configPanel)
  return lineage ? { configPanel, lineage } : null
}

/* ---------- 工具 ---------- */

/** 并发池：limit 个任务同时执行 */
async function runPool(tasks: Array<() => Promise<void>>, limit: number): Promise<void> {
  const executing = new Set<Promise<void>>()
  for (const task of tasks) {
    const p = task().finally(() => executing.delete(p))
    executing.add(p)
    if (executing.size >= limit) await Promise.race(executing)
  }
  await Promise.all(executing)
}

/** 默认图片尺寸：跟随用户偏好比例（与画布文生图一致） */
function defaultImageSize(): string {
  const prefsStore = usePreferencesStore()
  const ratio = prefsStore.generation.default_aspect_ratio || '1:1'
  const [rw, rh] = ratio.split(':').map(Number)
  const matched = rw && rh ? getModelParams().imageSizes.find((o) => o.w === rw && o.h === rh) : null
  return matched?.value || '1024x1024'
}

/** 批量生成前积分预估确认（多组模式混合时分别估后汇总，一次确认） */
async function confirmGroupedCost(
  groups: Array<{ type: 'image' | 'video'; mode?: string; size?: string; seconds?: number; count: number }>,
): Promise<boolean> {
  const { t } = useI18n()
  let total = 0
  let balance = Number.POSITIVE_INFINITY
  let count = 0
  let estimated = false
  for (const group of groups) {
    if (group.count <= 0) continue
    count += group.count
    const est = await estimateCanvasCost(group)
    if (!est) continue // 单组预估失败不阻塞，让生成接口自行处理
    estimated = true
    total += est.cost * group.count
    balance = Math.min(balance, est.balance)
  }
  if (!estimated) return true
  if (balance < total) {
    ElMessage.error(t('canvas.messages.batchInsufficient', { cost: total, balance }))
    return false
  }
  try {
    await ElMessageBox.confirm(
      t('canvas.messages.batchConfirm', { n: count, cost: total }),
      t('canvas.messages.batchConfirmTitle'),
      { confirmButtonText: t('canvas.script.confirm'), cancelButtonText: t('canvas.script.cancel') },
    )
    return true
  } catch {
    return false
  }
}

/** 批量生成前积分预估确认（单组便捷封装） */
async function confirmBatchCost(params: { type: 'image' | 'video'; mode?: string; size?: string; seconds?: number }, count: number): Promise<boolean> {
  return confirmGroupedCost([{ ...params, count }])
}

/** 脚本节点的分镜步骤组（StepGroup）：复用已有组，id 记录在节点 content.stepId */
function ensureShotStep(scriptPanel: CanvasPanel): string {
  const store = useCanvasStore()
  const stepId = readString(scriptPanel.content, 'stepId')
  if (stepId && store.steps.some((s) => s.id === stepId)) {
    store.addPanelToStep(stepId, scriptPanel.id)
    return stepId
  }
  const newId = store.addStep({
    name: `${scriptPanel.name || '脚本'} · 分镜`,
    panel_ids: [scriptPanel.id],
  })
  store.updatePanel(scriptPanel.id, { content: { stepId: newId } })
  return newId
}

/* ---------- 批量派生分镜图 / 尾帧图 ---------- */

/** 单项派生任务：镜头 + 帧角色 + 锚点/衔接信息 */
interface PendingFrame {
  shot: CanvasShot
  role: 'first' | 'last' | 'prev' | 'chain'
  /** 链帧时间序号（role='chain' 时使用，≥2） */
  chainSeq?: number
  /** 锚点分镜图 URL（前段帧/链帧派生：排参考图首位，最大化对构图的约束） */
  anchorUrl?: string
  /** 衔接底图：上一镜尾帧已成功时直接取 URL */
  linkUrl?: string
  /** 衔接底图本批自动补生成：指向上一镜尾帧的派生项（任务内等待其完成拿 URL） */
  tailFrom?: PendingFrame
  /** 本项完成句柄（生成完成后 resolve 为结果 URL 或 null，供衔接首帧 await） */
  done?: Promise<string | null>
}

/** 派生分镜图/尾帧图（批量/单镜头共用）：上游收集 -> 积分确认 -> 创建直出 image 节点并入队 */
async function deriveImagesInternal(scriptPanel: CanvasPanel, items: PendingFrame[]): Promise<void> {
  const { t } = useI18n()
  const store = useCanvasStore()
  const allShots = readShots(scriptPanel)

  // 上游收集：图片节点=参考图，文本节点=设定；资产卡按镜头命中注入（未标注镜头回退全量）
  const upstreams = getUpstreamNodes(scriptPanel.id, store.panels, store.connections)
  const assets = readAssets(scriptPanel)
  const upstreamRefImages = upstreams
    .filter((p) => p.type === 'image')
    .map((p) => readString(p.content, 'content'))
    .filter(Boolean)
  const upstreamTexts = upstreams
    .filter((p) => p.type === 'text')
    .map((p) => readString(p.content, 'content'))
    .filter(Boolean)

  // 积分预估：任一素材来源、锚点帧或衔接底图存在即按 image2image 估算（部分镜头可能命中为空，轻微高估可接受）
  const mayReference = upstreamRefImages.length > 0 ||
    [...assets.characters, ...assets.scenes].some((a) => a.imageUrl) ||
    items.some((item) => item.linkUrl || item.tailFrom || item.anchorUrl)
  // 尺寸默认沿用偏好比例，向导参数栏显式选择后以选择为准
  const imageParams = readPanelGenParams(scriptPanel, 'image', SHOT_IMAGE_PARAMS_KEY, { size: defaultImageSize() })
  const ok = await confirmBatchCost({ type: 'image', mode: mayReference ? 'image2image' : 'text2image', size: imageParams.size }, items.length)
  if (!ok) return

  store.pushSnapshot()
  const stepId = ensureShotStep(scriptPanel)
  const baseX = scriptPanel.x + scriptPanel.width + 80
  // 前段帧行带基线：分镜网格下方独立行带；尾帧在其下一行带，链帧再按 seq 向下延伸（均与其首帧同列）
  const tailBaseY = scriptPanel.y + Math.ceil(allShots.length / GRID_COLS) * IMG_PITCH_Y + 60
  const tasks: Array<() => Promise<void>> = []
  let failedCount = 0
  let linkSkipped = 0

  for (const item of items) {
    const shot = item.shot
    // 用全量镜头序号布局，保持网格位置稳定
    const idx = allShots.findIndex((s) => s.id === shot.id)
    const contexts = buildShotContexts(shot, assets, upstreamTexts)
    const baseRefs = [...upstreamRefImages, ...contexts.characterImages, ...contexts.sceneImages].filter(Boolean)
    const promptLines = [buildShotImagePrompt(scriptPanel, shot, contexts)]
    if (item.role === 'last') promptLines.push(TAIL_PROMPT_LINE)
    if (item.role === 'prev') promptLines.push(prevPromptLine(shot.duration))
    if (item.role === 'chain') promptLines.push(chainPromptLine((item.chainSeq || 2) - 1))
    if (item.role === 'first' && (item.linkUrl || item.tailFrom)) promptLines.push(LINK_PROMPT_LINE)
    const x = baseX + (idx % GRID_COLS) * IMG_PITCH_X
    // 帧角色行带：首帧网格 -> 前段帧行带 -> 尾帧行带 -> 链帧按 seq 依次向下；带内与其首帧同列
    const bandY = item.role === 'prev'
      ? tailBaseY
      : item.role === 'last'
        ? tailBaseY + IMG_PITCH_Y
        : item.role === 'chain'
          ? tailBaseY + (item.chainSeq || 2) * IMG_PITCH_Y
          : scriptPanel.y
    const y = bandY + Math.floor(idx / GRID_COLS) * IMG_PITCH_Y
    const name = item.role === 'last'
      ? `#${shot.no} ${t('canvas.script.tailSuffix')}`
      : item.role === 'prev'
        ? `#${shot.no} ${t('canvas.script.prevSuffix')}`
        : item.role === 'chain'
          ? `#${shot.no} ${t('canvas.script.chainSuffix', { k: (item.chainSeq || 2) - 1 })}`
          : `#${shot.no} ${scriptPanel.name || ''}`.trim()
    const lineage = {
      kind: 'image',
      scriptPanelId: scriptPanel.id,
      shotId: shot.id,
      shotNo: shot.no,
      role: item.role,
      ...(item.chainSeq !== undefined ? { chainSeq: item.chainSeq } : {}),
    }

    // 衔接底图本批补生成：等上一镜尾帧成功后再建节点（参考图必须在 addPanel 时一次性写入，deepMerge 数组约束）
    if (item.tailFrom) {
      const tailFrom = item.tailFrom
      tasks.push(async () => {
        const base = (await tailFrom.done) || ''
        if (!base) {
          linkSkipped++
          return
        }
        // 参考图必须在 addPanel 时一次性写入：updatePanel 的 deepMerge 会把数组转成索引对象
        const referenceImages = [base, ...baseRefs]
        const panelId = store.addPanel({
          type: 'image',
          name,
          x,
          y,
          width: IMG_CONFIG_W,
          height: IMG_CONFIG_H,
          content: {
            status: 'pending',
            model: imageParams.model,
            size: imageParams.size,
            prompt: promptLines.join('\n'),
            referenceImages,
            lineage,
          },
        })
        store.addPanelToStep(stepId, panelId)
        const target = store.panels.find((p) => p.id === panelId)
        if (!target) return
        const generatedId = await executeInNodeGeneration(target, store, { waitFor: true })
        if (!generatedId) failedCount++
      })
      continue
    }

    // 常规（首帧 / 已就绪底图的衔接首帧 / 尾帧）：底图排参考图首位，节点立即创建
    // 前段帧/链帧（画面时间推演）：锚点分镜图排首位 + 按镜头命中的资产图
    const referenceImages = item.anchorUrl
      ? [item.anchorUrl, ...contexts.characterImages, ...contexts.sceneImages].filter(Boolean)
      : item.linkUrl
        ? [item.linkUrl, ...baseRefs]
        : baseRefs
    const panelId = store.addPanel({
      type: 'image',
      name,
      x,
      y,
      width: IMG_CONFIG_W,
      height: IMG_CONFIG_H,
      content: {
        status: 'pending',
        model: imageParams.model,
        size: imageParams.size,
        prompt: promptLines.join('\n'),
        referenceImages,
        lineage,
      },
    })
    store.addPanelToStep(stepId, panelId)
    if (item.role === 'last') {
      // 完成句柄：供下游衔接首帧 await 拿底图 URL
      let settle: (url: string | null) => void = () => {}
      item.done = new Promise<string | null>((resolve) => { settle = resolve })
      tasks.push(async () => {
        const target = store.panels.find((p) => p.id === panelId)
        if (!target) {
          settle(null)
          return
        }
        const generatedId = await executeInNodeGeneration(target, store, { waitFor: true })
        if (!generatedId) {
          failedCount++
          settle(null)
          return
        }
        settle(readString(target.content, 'content') || null)
      })
      continue
    }
    tasks.push(async () => {
      const target = store.panels.find((p) => p.id === panelId)
      if (!target) return
      const generatedId = await executeInNodeGeneration(target, store, { waitFor: true })
      if (!generatedId) failedCount++
    })
  }

  // 汇总提示：按本批帧角色选文案（尾帧批 / 前段帧批 / 常规分镜图批）
  const allLast = items.length > 0 && items.every((item) => item.role === 'last')
  const allPrev = !allLast && items.length > 0 && items.every((item) => item.role === 'prev')
  const queuedKey = allLast
    ? 'canvas.messages.batchTailsQueued'
    : allPrev
      ? 'canvas.messages.batchPrevsQueued'
      : 'canvas.messages.batchImagesQueued'
  const failedKey = allLast
    ? 'canvas.messages.batchTailsFailed'
    : allPrev
      ? 'canvas.messages.batchPrevsFailed'
      : 'canvas.messages.batchImagesFailed'
  ElMessage.success(`${t(queuedKey)} (${items.length})`)
  // 后台并发池执行，不阻塞交互；异常在 waitFor 内部已转节点 error 态，这里补一条汇总提示
  void runPool(tasks, IMAGE_CONCURRENCY).then(() => {
    if (failedCount > 0) ElMessage.warning(t(failedKey, { n: failedCount }))
    if (linkSkipped > 0) ElMessage.warning(t('canvas.messages.linkSkipped', { n: linkSkipped }))
  })
}

/** 批量派生分镜图（幂等：跳过已有首帧的镜头；衔接镜头按需自动补上一镜尾帧作底图） */
export async function deriveStoryboardImages(scriptPanel: CanvasPanel): Promise<void> {
  const { t } = useI18n()
  const shots = readShots(scriptPanel).slice(0, MAX_SHOTS)
  if (shots.length === 0) {
    ElMessage.warning(t('canvas.messages.shotsEmpty'))
    return
  }
  const items: PendingFrame[] = []
  const tailItems = new Map<string, PendingFrame>()
  let linkBlocked = 0
  for (const shot of shots) {
    if (findFirstFramePanel(scriptPanel.id, shot.id)) continue
    // 跨镜头衔接：以上一镜尾帧为底图续接（上一镜按镜号定位，第 1 镜无衔接）
    const prev = shot.linkPrev && shot.no > 1 ? shots.find((s) => s.no === shot.no - 1) : undefined
    if (!prev) {
      items.push({ shot, role: 'first' })
      continue
    }
    const tail = findTailFramePanel(scriptPanel.id, prev.id)
    const tailUrl = tail && tail.content?.status === 'success' ? readString(tail.content, 'content') : ''
    if (tailUrl) {
      items.push({ shot, role: 'first', linkUrl: tailUrl })
      continue
    }
    if (tail) {
      // 上一镜尾帧存在但未成功：跳过该镜头，不静默降级为纯文本生成
      linkBlocked++
      continue
    }
    // 上一镜尾帧缺失：本批自动补生成，衔接首帧在其完成后建节点
    let tailItem = tailItems.get(prev.id)
    if (!tailItem) {
      tailItem = { shot: prev, role: 'last' }
      tailItems.set(prev.id, tailItem)
      items.push(tailItem)
    }
    items.push({ shot, role: 'first', tailFrom: tailItem })
  }
  if (items.length === 0 && linkBlocked === 0) {
    ElMessage.info(t('canvas.messages.batchAllDerived'))
    return
  }
  await deriveImagesInternal(scriptPanel, items)
  if (linkBlocked > 0) ElMessage.info(t('canvas.messages.linkSkipped', { n: linkBlocked }))
}

/** 单镜头派生分镜图（已派生时提示跳过；衔接镜头需上一镜尾帧已就绪） */
export async function deriveImageForShot(scriptPanel: CanvasPanel, shot: CanvasShot): Promise<void> {
  const { t } = useI18n()
  if (findFirstFramePanel(scriptPanel.id, shot.id)) {
    ElMessage.info(t('canvas.messages.batchAllDerived'))
    return
  }
  const prev = shot.linkPrev && shot.no > 1 ? readShots(scriptPanel).find((s) => s.no === shot.no - 1) : undefined
  if (prev) {
    const tail = findTailFramePanel(scriptPanel.id, prev.id)
    const tailUrl = tail && tail.content?.status === 'success' ? readString(tail.content, 'content') : ''
    if (!tailUrl) {
      ElMessage.warning(t('canvas.messages.linkNeedsTail'))
      return
    }
    await deriveImagesInternal(scriptPanel, [{ shot, role: 'first', linkUrl: tailUrl }])
    return
  }
  await deriveImagesInternal(scriptPanel, [{ shot, role: 'first' }])
}

/** 单镜头重拍：分镜图节点就地重新生成（保留节点上的模型/尺寸/参考图，供向导与工具栏复用） */
export async function reshootImagePanel(target: CanvasPanel): Promise<void> {
  const { t } = useI18n()
  const refs = Array.isArray(target.content?.referenceImages)
    ? target.content.referenceImages.filter((u): u is string => typeof u === 'string')
    : []
  const ok = await checkCreditsBeforeGenerate({
    type: 'image',
    mode: refs.length > 0 ? 'image2image' : 'text2image',
    size: typeof target.content?.size === 'string' ? target.content.size : undefined,
  })
  if (!ok) return
  ElMessage.info(t('canvas.messages.regenerate'))
  await executeInNodeGeneration(target, useCanvasStore())
}

/* ---------- 尾帧图派生（keyframes 结束帧 + 跨镜头衔接底图） ---------- */

/** 批量补尾帧：只处理"首帧已成功且尚无尾帧"的镜头 */
export async function deriveTailFrames(scriptPanel: CanvasPanel): Promise<void> {
  const { t } = useI18n()
  const shots = readShots(scriptPanel).slice(0, MAX_SHOTS)
  if (shots.length === 0) {
    ElMessage.warning(t('canvas.messages.shotsEmpty'))
    return
  }
  const items: PendingFrame[] = []
  let notReady = 0
  for (const shot of shots) {
    if (findTailFramePanel(scriptPanel.id, shot.id)) continue
    const first = findFirstFramePanel(scriptPanel.id, shot.id)
    if (!first || first.content?.status !== 'success') {
      notReady++
      continue
    }
    items.push({ shot, role: 'last' })
  }
  if (items.length === 0) {
    ElMessage.warning(notReady > 0 ? t('canvas.messages.imagesNotReady') : t('canvas.messages.batchAllDerived'))
    return
  }
  await deriveImagesInternal(scriptPanel, items)
}

/** 单镜头生成尾帧（首帧已成功且尚无尾帧；向导行内入口） */
export async function deriveTailFrameForShot(scriptPanel: CanvasPanel, shot: CanvasShot): Promise<void> {
  const { t } = useI18n()
  const first = findFirstFramePanel(scriptPanel.id, shot.id)
  if (!first || first.content?.status !== 'success') {
    ElMessage.info(t('canvas.messages.imagesNotReady'))
    return
  }
  if (findTailFramePanel(scriptPanel.id, shot.id)) {
    ElMessage.info(t('canvas.messages.batchAllDerived'))
    return
  }
  await deriveImagesInternal(scriptPanel, [{ shot, role: 'last' }])
}

/** 分镜图节点一键生成尾帧（悬浮工具栏入口：仅首帧节点有效） */
export async function deriveTailFrameFromImageNode(imageResultPanel: CanvasPanel): Promise<void> {
  const { t } = useI18n()
  const store = useCanvasStore()
  const info = getShotLineageInfo(imageResultPanel)
  if (!info || info.lineage.kind !== 'image' || !(info.lineage.role === undefined || info.lineage.role === 'first')) return
  if (imageResultPanel.content?.status !== 'success') {
    ElMessage.info(t('canvas.messages.imagesNotReady'))
    return
  }
  const scriptPanel = store.panels.find((p) => p.id === info.lineage.scriptPanelId)
  const shot = scriptPanel ? readShots(scriptPanel).find((s) => s.id === info.lineage.shotId) : undefined
  if (!scriptPanel || !shot) return
  if (findTailFramePanel(scriptPanel.id, shot.id)) {
    ElMessage.info(t('canvas.messages.batchAllDerived'))
    return
  }
  await deriveImagesInternal(scriptPanel, [{ shot, role: 'last' }])
}

/* ---------- 前段帧派生（画面时间推演：动作开始前的向前延展帧，与尾帧对称） ---------- */

/** 单镜头生成前段帧（首帧已成功且尚无前段帧；向导行内入口） */
export async function derivePrevFrameForShot(scriptPanel: CanvasPanel, shot: CanvasShot): Promise<void> {
  const { t } = useI18n()
  const first = findFirstFramePanel(scriptPanel.id, shot.id)
  if (!first || first.content?.status !== 'success') {
    ElMessage.info(t('canvas.messages.imagesNotReady'))
    return
  }
  if (findPrevFramePanel(scriptPanel.id, shot.id)) {
    ElMessage.info(t('canvas.messages.batchAllDerived'))
    return
  }
  await deriveImagesInternal(scriptPanel, [{ shot, role: 'prev', anchorUrl: readString(first.content, 'content') }])
}

/** 分镜图节点一键生成前段帧（悬浮工具栏入口：仅首帧节点有效） */
export async function derivePrevFrameFromImageNode(imageResultPanel: CanvasPanel): Promise<void> {
  const { t } = useI18n()
  const store = useCanvasStore()
  const info = getShotLineageInfo(imageResultPanel)
  if (!info || info.lineage.kind !== 'image' || !(info.lineage.role === undefined || info.lineage.role === 'first')) return
  if (imageResultPanel.content?.status !== 'success') {
    ElMessage.info(t('canvas.messages.imagesNotReady'))
    return
  }
  const scriptPanel = store.panels.find((p) => p.id === info.lineage.scriptPanelId)
  const shot = scriptPanel ? readShots(scriptPanel).find((s) => s.id === info.lineage.shotId) : undefined
  if (!scriptPanel || !shot) return
  if (findPrevFramePanel(scriptPanel.id, shot.id)) {
    ElMessage.info(t('canvas.messages.batchAllDerived'))
    return
  }
  const first = findFirstFramePanel(scriptPanel.id, shot.id)
  const anchorUrl = first && first.content?.status === 'success'
    ? readString(first.content, 'content')
    : readString(imageResultPanel.content, 'content')
  await deriveImagesInternal(scriptPanel, [{ shot, role: 'prev', anchorUrl }])
}

/* ---------- 批量派生视频（图生视频 / 首尾帧） ---------- */

/** script 节点视频参数里的 refAssets 开关（默认开：未显式关闭即并入资产参考图；仅全能参考模式生效） */
export function readRefAssets(scriptPanel: CanvasPanel): boolean {
  const scoped = scriptPanel.content?.[SHOT_VIDEO_PARAMS_KEY]
  return !(isRecord(scoped) && scoped.refAssets === false)
}

/** script 视频参数：视频生成模式（keyframe=关键帧参考（缺省）/ reference=全能参考），上游两 mode 互斥 */
export type ShotVideoMode = 'keyframe' | 'reference'

export function readShotVideoMode(scriptPanel: CanvasPanel): ShotVideoMode {
  const scoped = scriptPanel.content?.[SHOT_VIDEO_PARAMS_KEY]
  return isRecord(scoped) && scoped.videoMode === 'reference' ? 'reference' : 'keyframe'
}

/** script 视频参数：长镜头分段数（0 = 不启用，合法值 1–4） */
export function readChainSegments(scriptPanel: CanvasPanel): number {
  const scoped = scriptPanel.content?.[SHOT_VIDEO_PARAMS_KEY]
  const v = isRecord(scoped) ? scoped.chainSegments : undefined
  return typeof v === 'number' && Number.isInteger(v) && v >= 1 && v <= 4 ? v : 0
}

/**
 * 镜头视频取图（按 script 视频参数的生成模式，keyframe 与 reference 上游互斥）：
 * - 关键帧参考（默认）：时间锚点语义——有尾帧取 [首帧, 尾帧]、无尾帧取 [首帧] 单图直出，
 *   use_keyframes=true（2.5 契约 first_frame 必填、last_frame 可选），不注入资产图（资产一致性由生图阶段保障）
 * - 全能参考：多图内容参考——并入全部已生成锚点帧（分镜图/尾帧/链帧，按 lineage 时间序），
 *   refAssets 开启时并入命中资产图，use_keyframes=false；张数由执行链路按所选模型 gen_params 截断
 * - 尾帧存在但未成功（关键帧模式）→ null（未就绪，调用方跳过，不静默降级单图）
 */
function collectShotVideoRefs(scriptPanel: CanvasPanel, shot: CanvasShot, firstUrl: string): { images: string[]; useKeyframes: boolean } | null {
  if (readShotVideoMode(scriptPanel) === 'reference') {
    const images = [firstUrl]
    const tail = findTailFramePanel(scriptPanel.id, shot.id)
    if (tail && tail.content?.status === 'success') {
      const url = readString(tail.content, 'content')
      if (url) images.push(url)
    }
    for (const chain of findChainFramePanels(scriptPanel.id, shot.id)) {
      if (chain.content?.status !== 'success') continue
      const url = readString(chain.content, 'content')
      if (url && !images.includes(url)) images.push(url)
    }
    if (readRefAssets(scriptPanel)) {
      const contexts = buildShotContexts(shot, readAssets(scriptPanel))
      for (const url of [...contexts.characterImages, ...contexts.sceneImages]) {
        if (url && !images.includes(url)) images.push(url)
      }
    }
    return { images, useKeyframes: false }
  }
  const tail = findTailFramePanel(scriptPanel.id, shot.id)
  if (tail) {
    if (tail.content?.status !== 'success') return null
    return { images: [firstUrl, readString(tail.content, 'content')].filter(Boolean), useKeyframes: true }
  }
  return { images: [firstUrl], useKeyframes: true }
}

export async function deriveStoryboardVideos(scriptPanel: CanvasPanel): Promise<void> {
  const { t } = useI18n()
  const store = useCanvasStore()
  const shots = readShots(scriptPanel).slice(0, MAX_SHOTS)
  if (shots.length === 0) {
    ElMessage.warning(t('canvas.messages.shotsEmpty'))
    return
  }

  const videoShotIds = new Set(findDerivedPanels(scriptPanel.id, 'video').map((d) => d.lineage.shotId))
  const derivedImages = findDerivedPanels(scriptPanel.id, 'image')

  // 只处理"已有成功首帧"且未派生过视频的镜头；尾帧未就绪同样跳过
  const items: Array<{ shot: CanvasShot; imgConfig: CanvasPanel; imageNodeId: string; images: string[]; useKeyframes: boolean }> = []
  let notReady = 0
  for (const shot of shots) {
    if (videoShotIds.has(shot.id)) continue
    const entry = derivedImages.find(
      (d) => d.lineage.shotId === shot.id && (d.lineage.role === undefined || d.lineage.role === 'first'),
    )
    // 直出节点：源图即节点自身（结果写在自己的 content.content）；存量/手搭 config：反查其结果节点
    const resultNode = entry
      ? (entry.panel.type === 'image'
          ? (entry.panel.content?.status === 'success' ? entry.panel : null)
          : findResultNode(entry.panel.id, 'image'))
      : null
    const imageUrl = resultNode ? readString(resultNode.content, 'content') : ''
    if (!entry || !resultNode || !imageUrl) {
      notReady++
      continue
    }
    const refs = collectShotVideoRefs(scriptPanel, shot, imageUrl)
    if (!refs) {
      notReady++
      continue
    }
    items.push({ shot, imgConfig: entry.panel, imageNodeId: resultNode.id, images: refs.images, useKeyframes: refs.useKeyframes })
  }

  if (items.length === 0) {
    ElMessage.warning(notReady > 0 ? t('canvas.messages.imagesNotReady') : t('canvas.messages.batchAllDerived'))
    return
  }

  const videoParams = readPanelGenParams(scriptPanel, 'video', SHOT_VIDEO_PARAMS_KEY)
  // 积分预估：keyframes 组与 image2video 组分别估后汇总（批量内两种模式可能混合）
  const keyframeCount = items.filter((i) => i.useKeyframes).length
  const ok = await confirmGroupedCost([
    { type: 'video', mode: 'keyframes', seconds: videoParams.seconds, count: keyframeCount },
    { type: 'video', mode: 'image2video', seconds: videoParams.seconds, count: items.length - keyframeCount },
  ])
  if (!ok) return

  store.pushSnapshot()
  const stepId = ensureShotStep(scriptPanel)
  const tasks: Array<() => Promise<void>> = []
  let failedCount = 0

  // 视频直出节点排在分镜网格右侧专属区，同行按镜头列位横向排开（B2 将改为覆盖在源图上）
  const videoBaseX = scriptPanel.x + scriptPanel.width + 80 + GRID_COLS * IMG_PITCH_X + 40

  for (const item of items) {
    // 时长：参数栏显式选择优先，未选择时沿用该镜头在表格里设的时长
    const params = readPanelGenParams(scriptPanel, 'video', SHOT_VIDEO_PARAMS_KEY, {
      seconds: item.shot.duration || 5,
    })
    const colIdx = Math.max(0, Math.round((item.imgConfig.x - scriptPanel.x - scriptPanel.width - 80) / IMG_PITCH_X))
    const panelId = store.addPanel({
      type: 'video',
      name: `#${item.shot.no} ${t('canvas.script.videoSuffix')}`,
      x: videoBaseX + colIdx * VIDEO_PITCH_X,
      y: item.imgConfig.y,
      width: VIDEO_CONFIG_W,
      height: VIDEO_CONFIG_H,
      content: {
        status: 'pending',
        mode: 'image2video',
        model: params.model,
        prompt: buildShotVideoPrompt(item.shot),
        aspect_ratio: params.aspect_ratio,
        resolution: params.resolution,
        frame_rate: params.frame_rate,
        seconds: params.seconds,
        // 参考图必须在 addPanel 时一次性写入：updatePanel 的 deepMerge 会把数组转成索引对象
        referenceImages: item.images,
        // 首尾帧模式（有尾帧）：执行器据此路由 keyframes，Agnes 契约 keyframe/reference 互斥
        ...(item.useKeyframes ? { use_keyframes: true } : {}),
        lineage: { kind: 'video', scriptPanelId: scriptPanel.id, shotId: item.shot.id, shotNo: item.shot.no },
      },
    })
    // 连线：源分镜图 -> 视频节点（视觉血缘；image -> video 连线校验允许）
    store.addConnection({ source_panel_id: item.imageNodeId, target_panel_id: panelId, type: 'auto' })
    store.addPanelToStep(stepId, panelId)
    tasks.push(async () => {
      const target = store.panels.find((p) => p.id === panelId)
      if (!target) return
      const generatedId = await executeInNodeVideoGeneration(target, store, { waitFor: true })
      if (!generatedId) failedCount++
    })
  }

  ElMessage.success(`${t('canvas.messages.batchVideosQueued')} (${items.length})`)
  if (notReady > 0) ElMessage.info(`${t('canvas.messages.imagesNotReady')} (${notReady})`)
  // 后台并发池执行，不阻塞交互；异常在 waitFor 内部已转节点 error 态，这里补一条汇总提示
  void runPool(tasks, VIDEO_CONCURRENCY).then(() => {
    if (failedCount > 0) ElMessage.warning(t('canvas.messages.batchVideosFailed', { n: failedCount }))
  })
}

/* ---------- 单镜头派生视频（分镜图节点一键图生视频 / 首尾帧） ---------- */

export async function deriveVideoForShot(imageResultPanel: CanvasPanel): Promise<void> {
  const { t } = useI18n()
  const store = useCanvasStore()
  const info = getShotLineageInfo(imageResultPanel)
  if (!info || info.lineage.kind !== 'image') return

  const scriptPanel = store.panels.find((p) => p.id === info.lineage.scriptPanelId)
  const shot = scriptPanel ? readShots(scriptPanel).find((s) => s.id === info.lineage.shotId) : undefined
  if (!scriptPanel || !shot) return

  // 源图：优先取该镜头首帧（从尾帧节点入口触发时也回到首帧作源图）
  const firstPanel = findFirstFramePanel(scriptPanel.id, shot.id)
  const firstUrl = firstPanel && firstPanel.content?.status === 'success'
    ? readString(firstPanel.content, 'content')
    : readString(imageResultPanel.content, 'content')
  if (!firstUrl) return

  const refs = collectShotVideoRefs(scriptPanel, shot, firstUrl)
  if (!refs) {
    ElMessage.info(t('canvas.messages.tailNotReady'))
    return
  }

  // 与批量派生同源：脚本节点上的视频参数，时长未选择时沿用镜头时长
  const params = readPanelGenParams(scriptPanel, 'video', SHOT_VIDEO_PARAMS_KEY, {
    seconds: shot.duration || 5,
  })
  const canGenerate = await checkCreditsBeforeGenerate({ type: 'video', mode: refs.useKeyframes ? 'keyframes' : 'image2video', seconds: params.seconds })
  if (!canGenerate) return

  store.pushSnapshot()
  const stepId = ensureShotStep(scriptPanel)
  const panelId = store.addPanel({
    type: 'video',
    name: `#${shot.no} ${t('canvas.script.videoSuffix')}`,
    x: imageResultPanel.x + imageResultPanel.width + 80,
    y: imageResultPanel.y,
    width: VIDEO_CONFIG_W,
    height: VIDEO_CONFIG_H,
    content: {
      status: 'pending',
      mode: 'image2video',
      model: params.model,
      prompt: buildShotVideoPrompt(shot),
      aspect_ratio: params.aspect_ratio,
      resolution: params.resolution,
      frame_rate: params.frame_rate,
      seconds: params.seconds,
      // 参考图必须在 addPanel 时一次性写入：updatePanel 的 deepMerge 会把数组转成索引对象
      referenceImages: refs.images,
      // 首尾帧模式（有尾帧）：执行器据此路由 keyframes
      ...(refs.useKeyframes ? { use_keyframes: true } : {}),
      lineage: { kind: 'video', scriptPanelId: scriptPanel.id, shotId: shot.id, shotNo: shot.no },
    },
  })
  const sourceNode = firstPanel || imageResultPanel
  store.addConnection({ source_panel_id: sourceNode.id, target_panel_id: panelId, type: 'auto' })
  store.addPanelToStep(stepId, panelId)
  const target = store.panels.find((p) => p.id === panelId)
  if (target) await executeInNodeVideoGeneration(target, store)
  ElMessage.success(t('canvas.messages.videoDerived'))
}

/* ---------- P2：画面链长视频（补齐链帧 → 相邻帧分段 keyframes 视频 → compose 合成） ---------- */

/** 链帧补齐的等待上限：已处于生成中的帧轮询落定，与 pollImageTask 的 5 分钟超时对齐 */
const CHAIN_FRAME_WAIT_MS = 300000

/** 等待节点生成落定（pending/loading -> success/error），超时返回 */
async function waitForPanelSettled(panelId: string, timeoutMs: number): Promise<void> {
  const store = useCanvasStore()
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const panel = store.panels.find((p) => p.id === panelId)
    if (!panel) return
    const status = panel.content?.status
    if (status === 'success' || status === 'error') return
    await new Promise((resolve) => setTimeout(resolve, 2000))
  }
}

/**
 * 单镜头画面链长视频编排（向导行内 / 分镜图工具栏共用）：
 * 1. 画面链 = [seq0 首帧, seq1 尾帧, seq2..(1+n) 链帧]（n = chainSegments），缺帧/失败帧自动补齐
 * 2. 积分预估一次性确认"补齐帧数 + (1+n) 段视频"两笔消耗
 * 3. 相邻帧两两生成 keyframes 分段视频（段间共享帧保证 concat 连续），全部成功后自动建 compose 合成长镜头
 * 失败语义：缺帧/失败段明确提示、不静默降级；任一段未成功则不建 compose
 */
export async function deriveChainVideosForShot(scriptPanel: CanvasPanel, shot: CanvasShot): Promise<void> {
  const { t } = useI18n()
  const store = useCanvasStore()
  const segments = readChainSegments(scriptPanel)
  if (segments <= 0) {
    ElMessage.info(t('canvas.messages.chainDisabled'))
    return
  }
  // 幂等：该镜头已有分段视频（lineage.chainSeq）时跳过
  if (findDerivedPanels(scriptPanel.id, 'video').some((d) => d.lineage.shotId === shot.id && d.lineage.chainSeq !== undefined)) {
    ElMessage.info(t('canvas.messages.batchAllDerived'))
    return
  }
  const first = findFirstFramePanel(scriptPanel.id, shot.id)
  const firstUrl = first && first.content?.status === 'success' ? readString(first.content, 'content') : ''
  if (!first || !firstUrl) {
    ElMessage.warning(t('canvas.messages.chainNeedsFirst'))
    return
  }

  // 画面链盘点：缺帧 -> 新建补齐；error -> 就地重拍；pending/loading -> 等待落定（不重复扣积分）
  const total = 1 + segments
  const chainIds: Array<string | null> = [first.id]
  const fillItems: PendingFrame[] = []
  const reshootPanels: CanvasPanel[] = []
  const busyIds: string[] = []
  for (let seq = 1; seq <= total; seq++) {
    const isTail = seq === 1
    const panel = isTail ? findTailFramePanel(scriptPanel.id, shot.id) : findChainFramePanel(scriptPanel.id, shot.id, seq)
    chainIds.push(panel?.id || null)
    if (!panel) {
      fillItems.push({ shot, role: isTail ? 'last' : 'chain', chainSeq: isTail ? undefined : seq, anchorUrl: firstUrl })
    } else if (panel.content?.status === 'pending' || panel.content?.status === 'loading') {
      busyIds.push(panel.id)
    } else if (panel.content?.status === 'error') {
      reshootPanels.push(panel)
    }
  }

  // 积分预估：一次性确认"补齐帧数 + 分段视频数"两笔消耗
  const videoParams = readPanelGenParams(scriptPanel, 'video', SHOT_VIDEO_PARAMS_KEY, { seconds: shot.duration || 5 })
  const imageParams = readPanelGenParams(scriptPanel, 'image', SHOT_IMAGE_PARAMS_KEY, { size: defaultImageSize() })
  const ok = await confirmGroupedCost([
    { type: 'image', mode: 'image2image', size: imageParams.size, count: fillItems.length + reshootPanels.length },
    { type: 'video', mode: 'keyframes', seconds: videoParams.seconds, count: total },
  ])
  if (!ok) return

  store.pushSnapshot()
  const stepId = ensureShotStep(scriptPanel)
  if (fillItems.length + reshootPanels.length > 0) {
    ElMessage.info(t('canvas.messages.chainFillingFrames', { n: fillItems.length + reshootPanels.length }))
  }

  // 补帧任务：锚点分镜图排参考图首位（沿用尾帧/前段帧的派生规格），进图片并发池（池内无相互依赖）
  const allShots = readShots(scriptPanel)
  const idx = Math.max(0, allShots.findIndex((s) => s.id === shot.id))
  const baseX = scriptPanel.x + scriptPanel.width + 80
  const tailBaseY = scriptPanel.y + Math.ceil(allShots.length / GRID_COLS) * IMG_PITCH_Y + 60
  const x = baseX + (idx % GRID_COLS) * IMG_PITCH_X
  const contexts = buildShotContexts(shot, readAssets(scriptPanel))
  const referenceImages = [firstUrl, ...contexts.characterImages, ...contexts.sceneImages].filter(Boolean)
  const fillTasks: Array<() => Promise<void>> = []
  for (const item of fillItems) {
    const isTail = item.role === 'last'
    const seq = isTail ? 1 : item.chainSeq || 2
    const y = (isTail ? tailBaseY + IMG_PITCH_Y : tailBaseY + seq * IMG_PITCH_Y) + Math.floor(idx / GRID_COLS) * IMG_PITCH_Y
    const promptLines = [
      buildShotImagePrompt(scriptPanel, shot, contexts),
      isTail ? TAIL_PROMPT_LINE : chainPromptLine(seq - 1),
    ]
    const name = isTail
      ? `#${shot.no} ${t('canvas.script.tailSuffix')}`
      : `#${shot.no} ${t('canvas.script.chainSuffix', { k: seq - 1 })}`
    const lineage = { kind: 'image', scriptPanelId: scriptPanel.id, shotId: shot.id, shotNo: shot.no, role: item.role, ...(isTail ? {} : { chainSeq: seq }) }
    fillTasks.push(async () => {
      const panelId = store.addPanel({
        type: 'image',
        name,
        x,
        y,
        width: IMG_CONFIG_W,
        height: IMG_CONFIG_H,
        content: {
          status: 'pending',
          model: imageParams.model,
          size: imageParams.size,
          prompt: promptLines.join('\n'),
          referenceImages,
          lineage,
        },
      })
      chainIds[seq] = panelId
      store.addPanelToStep(stepId, panelId)
      const target = store.panels.find((p) => p.id === panelId)
      if (!target) return
      await executeInNodeGeneration(target, store, { waitFor: true })
    })
  }
  for (const target of reshootPanels) {
    // 失败链帧就地重拍：保留节点上的模型/尺寸/参考图
    fillTasks.push(async () => {
      await executeInNodeGeneration(target, store, { waitFor: true })
    })
  }
  // 已在生成中的帧先等待落定，再统一补帧
  await Promise.all(busyIds.map((id) => waitForPanelSettled(id, CHAIN_FRAME_WAIT_MS)))
  if (fillTasks.length > 0) await runPool(fillTasks, IMAGE_CONCURRENCY)

  // 收集链帧结果 URL：任一帧缺失 -> 依赖它的分段跳过（失败帧保留 error 态可在节点上重试）
  const urls: Array<string | null> = [firstUrl]
  for (let seq = 1; seq <= total; seq++) {
    const id = chainIds[seq]
    const panel = id ? store.panels.find((p) => p.id === id) : null
    urls.push(panel && panel.content?.status === 'success' ? readString(panel.content, 'content') || null : null)
  }

  // 分段视频：相邻帧 [seq i-1, seq i] 两两一段；同一行按段序横排（compose 按摆放顺序取段）
  const videoBaseX = scriptPanel.x + scriptPanel.width + 80 + GRID_COLS * IMG_PITCH_X + 40
  const videosY = tailBaseY + (total + 1) * IMG_PITCH_Y
  const skippedSegs: number[] = []
  const segPanelIds: string[] = []
  const segTasks: Array<() => Promise<void>> = []
  let segFailed = 0
  for (let i = 1; i <= total; i++) {
    const startUrl = urls[i - 1]
    const endUrl = urls[i]
    if (!startUrl || !endUrl || !chainIds[i - 1] || !chainIds[i]) {
      skippedSegs.push(i)
      continue
    }
    const panelId = store.addPanel({
      type: 'video',
      name: `#${shot.no} ${t('canvas.script.segmentSuffix', { seg: i })}`,
      x: videoBaseX + (i - 1) * VIDEO_PITCH_X,
      y: videosY,
      width: VIDEO_CONFIG_W,
      height: VIDEO_CONFIG_H,
      content: {
        status: 'pending',
        mode: 'image2video',
        model: videoParams.model,
        prompt: [buildShotVideoPrompt(shot), segmentPromptLine(i, total)].join('\n'),
        aspect_ratio: videoParams.aspect_ratio,
        resolution: videoParams.resolution,
        frame_rate: videoParams.frame_rate,
        seconds: videoParams.seconds,
        // 参考图必须在 addPanel 时一次性写入：updatePanel 的 deepMerge 会把数组转成索引对象
        referenceImages: [startUrl, endUrl],
        // 画面链分段：相邻帧互为首尾帧（keyframe/reference 互斥，不带资产图）
        use_keyframes: true,
        lineage: { kind: 'video', scriptPanelId: scriptPanel.id, shotId: shot.id, shotNo: shot.no, chainSeq: i },
      },
    })
    segPanelIds.push(panelId)
    store.addConnection({ source_panel_id: chainIds[i - 1]!, target_panel_id: panelId, type: 'auto' })
    store.addConnection({ source_panel_id: chainIds[i]!, target_panel_id: panelId, type: 'auto' })
    store.addPanelToStep(stepId, panelId)
    segTasks.push(async () => {
      const target = store.panels.find((p) => p.id === panelId)
      if (!target) return
      const generatedId = await executeInNodeVideoGeneration(target, store, { waitFor: true })
      if (!generatedId) segFailed++
    })
  }

  if (segPanelIds.length > 0) ElMessage.success(`${t('canvas.messages.chainSegmentsQueued')} (${segPanelIds.length})`)
  // 段视频进视频并发池（段间无依赖）
  await runPool(segTasks, VIDEO_CONCURRENCY)

  // 失败汇总：缺帧/失败段明确提示，不降级为"部分段 + compose"
  if (skippedSegs.length > 0) {
    ElMessage.warning(t('canvas.messages.chainSegmentsSkipped', { segs: skippedSegs.join('/') }))
  }
  if (segFailed > 0) {
    ElMessage.warning(t('canvas.messages.chainSegmentsFailed', { n: segFailed }))
  }
  if (segPanelIds.length === 0 || skippedSegs.length > 0 || segFailed > 0) return

  // 全部分段成功：自动创建 compose 节点，按段序连线各段视频并执行成片
  const composeId = store.addPanel({
    type: 'compose',
    name: `#${shot.no} ${t('canvas.script.composeSuffix')}`,
    x: videoBaseX,
    y: videosY + VIDEO_CONFIG_H + 80,
    width: 360,
    height: 240,
    content: { from_node: null, with_subtitle: false, audio_from_node: null, subtitle_from_node: null },
  })
  for (const segId of segPanelIds) {
    store.addConnection({ source_panel_id: segId, target_panel_id: composeId, type: 'auto' })
  }
  store.addPanelToStep(stepId, composeId)
  await runChainCompose(composeId, segPanelIds)
}

/** 执行画面链 compose 节点：按段序合成完整长镜头并回填结果视频节点（复用现有成片能力） */
async function runChainCompose(composeId: string, segPanelIds: string[]): Promise<void> {
  const { t } = useI18n()
  const store = useCanvasStore()
  const compose = store.panels.find((p) => p.id === composeId)
  if (!compose) return
  const segUrls = segPanelIds
    .map((id) => store.panels.find((p) => p.id === id))
    .filter((p): p is CanvasPanel => !!p && p.content?.status === 'success')
    .map((p) => readString(p.content, 'content'))
    .filter(Boolean)
  if (segUrls.length === 0) return
  store.updatePanel(composeId, { content: { status: 'loading', errorDetails: null } })
  try {
    const res = await composeCanvasVideos({ video_urls: segUrls, with_subtitle: false })
    const resultId = store.addPanel({
      type: 'video',
      x: compose.x + compose.width + 60,
      y: compose.y,
      width: 420,
      height: 236,
      content: { content: res.video_url, status: 'success' },
    })
    store.addConnection({ source_panel_id: composeId, target_panel_id: resultId, type: 'auto' })
    store.updatePanel(composeId, { content: { status: 'idle', result_panel_id: resultId } })
    store.pushSnapshot()
    ElMessage.success(t('canvas.messages.chainComposeDone'))
  } catch (err) {
    store.updatePanel(composeId, { content: { status: 'error', errorDetails: getErrorMessage(err) } })
    ElMessage.error(`${t('canvas.messages.chainComposeFailed')}: ${getErrorMessage(err)}`)
  }
}

/** 分镜图节点一键生成分段视频（悬浮工具栏入口：仅首帧节点有效，是否可用由 chainSegments 参数决定） */
export async function deriveChainVideosFromImageNode(imageResultPanel: CanvasPanel): Promise<void> {
  const store = useCanvasStore()
  const info = getShotLineageInfo(imageResultPanel)
  if (!info || info.lineage.kind !== 'image' || !(info.lineage.role === undefined || info.lineage.role === 'first')) return
  const scriptPanel = store.panels.find((p) => p.id === info.lineage.scriptPanelId)
  const shot = scriptPanel ? readShots(scriptPanel).find((s) => s.id === info.lineage.shotId) : undefined
  if (!scriptPanel || !shot) return
  await deriveChainVideosForShot(scriptPanel, shot)
}
