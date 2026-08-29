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
import {
  executeInNodeGeneration,
  executeInNodeVideoGeneration,
  getUpstreamNodes,
  readPanelGenParams,
} from '@/lib/canvas-generation'
import { estimateCanvasCost, checkCreditsBeforeGenerate } from '@/lib/canvas-credits'

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

/** 读取派生 config 节点的 lineage，结构不符返回 null */
export function readLineage(panel: { content?: Record<string, unknown> }): ShotLineage | null {
  const v = panel.content?.lineage
  if (!isRecord(v)) return null
  const kind = v.kind
  if (kind !== 'image' && kind !== 'video') return null
  if (typeof v.scriptPanelId !== 'string' || typeof v.shotId !== 'string' || typeof v.shotNo !== 'number') return null
  return { kind, scriptPanelId: v.scriptPanelId, shotId: v.shotId, shotNo: v.shotNo }
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
export function buildAssetContexts(assets: ScriptAssets): { characters: string[]; scenes: string[] } {
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

/* ---------- 派生节点查找 ---------- */

/**
 * 某脚本节点指定 kind 的全部派生节点（自身带 lineage）
 * - image：直出的分镜图节点（type === 'image'）与存量/手搭场景的 config 派生节点并存，两者都识别
 * - video：config 节点（本期视频派生仍走 config，第二阶段再变）
 */
function findDerivedPanels(scriptPanelId: string, kind: 'image' | 'video'): Array<{ panel: CanvasPanel; lineage: ShotLineage }> {
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

/** 某脚本节点是否已有指定 kind 的派生节点 */
export function hasDerivedConfigs(scriptPanelId: string, kind: 'image' | 'video'): boolean {
  return findDerivedPanels(scriptPanelId, kind).length > 0
}

/** 某脚本节点各镜头的派生状态（shotId -> 是否已派生分镜图/视频，供面板状态点显示） */
export function getDerivedShotIds(scriptPanelId: string): { image: Set<string>; video: Set<string> } {
  return {
    image: new Set(findDerivedPanels(scriptPanelId, 'image').map((d) => d.lineage.shotId)),
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

/** 批量生成前积分预估确认（汇总 count 个任务的总消耗） */
async function confirmBatchCost(params: { type: 'image' | 'video'; mode?: string; size?: string; seconds?: number }, count: number): Promise<boolean> {
  const { t } = useI18n()
  const est = await estimateCanvasCost(params)
  if (!est) return true // 预估失败不阻塞，让生成接口自行处理
  const total = est.cost * count
  if (est.balance < total) {
    ElMessage.error(t('canvas.messages.batchInsufficient', { cost: total, balance: est.balance }))
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

/* ---------- 批量派生分镜图 ---------- */

/** 派生指定镜头的分镜图（批量/单镜头共用）：上游收集 -> 积分确认 -> 创建直出 image 节点并入队 */
async function deriveImagesInternal(scriptPanel: CanvasPanel, pending: CanvasShot[]): Promise<void> {
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

  // 积分预估：任一素材来源存在即按 image2image 估算（部分镜头可能命中为空，轻微高估可接受）
  const mayReference = upstreamRefImages.length > 0 ||
    [...assets.characters, ...assets.scenes].some((a) => a.imageUrl)
  // 尺寸默认沿用偏好比例，向导参数栏显式选择后以选择为准
  const imageParams = readPanelGenParams(scriptPanel, 'image', SHOT_IMAGE_PARAMS_KEY, { size: defaultImageSize() })
  const ok = await confirmBatchCost({ type: 'image', mode: mayReference ? 'image2image' : 'text2image', size: imageParams.size }, pending.length)
  if (!ok) return

  store.pushSnapshot()
  const stepId = ensureShotStep(scriptPanel)
  const baseX = scriptPanel.x + scriptPanel.width + 80
  const tasks: Array<() => Promise<void>> = []
  let failedCount = 0

  for (const shot of pending) {
    // 用全量镜头序号布局，保持网格位置稳定
    const idx = allShots.findIndex((s) => s.id === shot.id)
    const contexts = buildShotContexts(shot, assets, upstreamTexts)
    // 参考图必须在 addPanel 时一次性写入：updatePanel 的 deepMerge 会把数组转成索引对象
    const referenceImages = [...upstreamRefImages, ...contexts.characterImages, ...contexts.sceneImages].filter(Boolean)
    // 直出分镜图：节点自身同时承载配置与结果，lineage 记录出处，不再建 script -> image 连线（连线校验也不允许）
    const panelId = store.addPanel({
      type: 'image',
      name: `#${shot.no} ${scriptPanel.name || ''}`.trim(),
      x: baseX + (idx % GRID_COLS) * IMG_PITCH_X,
      y: scriptPanel.y + Math.floor(idx / GRID_COLS) * IMG_PITCH_Y,
      width: IMG_CONFIG_W,
      height: IMG_CONFIG_H,
      content: {
        status: 'pending',
        model: imageParams.model,
        size: imageParams.size,
        prompt: buildShotImagePrompt(scriptPanel, shot, contexts),
        referenceImages,
        lineage: { kind: 'image', scriptPanelId: scriptPanel.id, shotId: shot.id, shotNo: shot.no },
      },
    })
    store.addPanelToStep(stepId, panelId)
    tasks.push(async () => {
      const target = store.panels.find((p) => p.id === panelId)
      if (!target) return
      const generatedId = await executeInNodeGeneration(target, store, { waitFor: true })
      if (!generatedId) failedCount++
    })
  }

  ElMessage.success(`${t('canvas.messages.batchImagesQueued')} (${pending.length})`)
  // 后台并发池执行，不阻塞交互；异常在 waitFor 内部已转节点 error 态，这里补一条汇总提示
  void runPool(tasks, IMAGE_CONCURRENCY).then(() => {
    if (failedCount > 0) ElMessage.warning(t('canvas.messages.batchImagesFailed', { n: failedCount }))
  })
}

/** 批量派生分镜图（幂等：跳过已派生镜头，重做单个镜头用单镜头入口） */
export async function deriveStoryboardImages(scriptPanel: CanvasPanel): Promise<void> {
  const { t } = useI18n()
  const shots = readShots(scriptPanel).slice(0, MAX_SHOTS)
  if (shots.length === 0) {
    ElMessage.warning(t('canvas.messages.shotsEmpty'))
    return
  }
  const derivedShotIds = new Set(findDerivedPanels(scriptPanel.id, 'image').map((d) => d.lineage.shotId))
  const pending = shots.filter((s) => !derivedShotIds.has(s.id))
  if (pending.length === 0) {
    ElMessage.info(t('canvas.messages.batchAllDerived'))
    return
  }
  await deriveImagesInternal(scriptPanel, pending)
}

/** 单镜头派生分镜图（脚本面板内逐镜头生成，已派生时提示跳过） */
export async function deriveImageForShot(scriptPanel: CanvasPanel, shot: CanvasShot): Promise<void> {
  const { t } = useI18n()
  if (findDerivedPanels(scriptPanel.id, 'image').some((d) => d.lineage.shotId === shot.id)) {
    ElMessage.info(t('canvas.messages.batchAllDerived'))
    return
  }
  await deriveImagesInternal(scriptPanel, [shot])
}

/* ---------- 批量派生视频（图生视频） ---------- */

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

  // 只处理"已有成功分镜图"且未派生过视频的镜头
  const items: Array<{ shot: CanvasShot; imgConfig: CanvasPanel; imageNodeId: string; imageUrl: string }> = []
  let notReady = 0
  for (const shot of shots) {
    if (videoShotIds.has(shot.id)) continue
    const entry = derivedImages.find((d) => d.lineage.shotId === shot.id)
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
    items.push({ shot, imgConfig: entry.panel, imageNodeId: resultNode.id, imageUrl })
  }

  if (items.length === 0) {
    ElMessage.warning(notReady > 0 ? t('canvas.messages.imagesNotReady') : t('canvas.messages.batchAllDerived'))
    return
  }

  const videoParams = readPanelGenParams(scriptPanel, 'video', SHOT_VIDEO_PARAMS_KEY)
  const ok = await confirmBatchCost({ type: 'video', mode: 'image2video', seconds: videoParams.seconds }, items.length)
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
        referenceImages: [item.imageUrl],
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

/* ---------- 单镜头派生视频（分镜图节点一键图生视频） ---------- */

export async function deriveVideoForShot(imageResultPanel: CanvasPanel): Promise<void> {
  const { t } = useI18n()
  const store = useCanvasStore()
  const info = getShotLineageInfo(imageResultPanel)
  if (!info || info.lineage.kind !== 'image') return

  const scriptPanel = store.panels.find((p) => p.id === info.lineage.scriptPanelId)
  const shot = scriptPanel ? readShots(scriptPanel).find((s) => s.id === info.lineage.shotId) : undefined
  if (!scriptPanel || !shot) return

  const imageUrl = readString(imageResultPanel.content, 'content')
  if (!imageUrl) return

  // 与批量派生同源：脚本节点上的视频参数，时长未选择时沿用镜头时长
  const params = readPanelGenParams(scriptPanel, 'video', SHOT_VIDEO_PARAMS_KEY, {
    seconds: shot.duration || 5,
  })
  const canGenerate = await checkCreditsBeforeGenerate({ type: 'video', mode: 'image2video', seconds: params.seconds })
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
      referenceImages: [imageUrl],
      lineage: { kind: 'video', scriptPanelId: scriptPanel.id, shotId: shot.id, shotNo: shot.no },
    },
  })
  store.addConnection({ source_panel_id: imageResultPanel.id, target_panel_id: panelId, type: 'auto' })
  store.addPanelToStep(stepId, panelId)
  const target = store.panels.find((p) => p.id === panelId)
  if (target) await executeInNodeVideoGeneration(target, store)
  ElMessage.success(t('canvas.messages.videoDerived'))
}
