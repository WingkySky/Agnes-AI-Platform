/* =====================================================
 * 分镜管线原子函数（lib/storyboard）
 *
 * - extractEntities：剧本 → 实体清单（角色/场景/物品）
 * - extractProjectEntities / generateScript：项目制编排用（实体草稿带项目字段、剧本生成）
 * - splitStoryboard：给定实体 → 分镜列表（每镜带成品分镜图提示词）
 * - planStoryboard：一枪出（实体沿用上游 + 提取补全 + 分镜），向导/Composer 快速路径
 * - LLM 子调用经 transport（默认 SSE 透传通道），解析失败重试一次
 * ===================================================== */

import type { ChatTransport } from './transport'
import { sseChatComplete } from './transport'
import type { StoryboardEntity, StoryboardShot, StyleConfig } from './schemas'
import { parseEntities, parseJsonObject, parseProjectEntities, parseShot } from './schemas'
import type { ProjectEntityDraftGroup } from './schemas'
import type { WizardCategory } from './prompts'
import {
  buildFramePrompt,
  extractEntitiesPrompt,
  planStoryboardPrompt,
  projectEntitiesPrompt,
  scriptPrompt,
  splitStoryboardPrompt,
} from './prompts'

export interface PipelineOptions {
  temperature?: number
  /** 透传 model 提示（后端校验聊天注册表，未命中走默认解析链） */
  model?: string
  /** LLM 通道替身（单测注入） */
  transport?: ChatTransport
}

export interface EntityGroup {
  characters: StoryboardEntity[]
  scenes: StoryboardEntity[]
  props: StoryboardEntity[]
}

export interface SplitOptions extends PipelineOptions {
  shotCountMin?: number
  shotCountMax?: number
  /** 运镜词表（库 camera 条目名；为空时模板回退自由描述） */
  cameraVocabulary?: string[]
}

export interface PlanOptions extends SplitOptions {
  /** 给定实体（上游节点/已有资产卡，LLM 必须沿用） */
  characters?: StoryboardEntity[]
  scenes?: StoryboardEntity[]
  /** 自定义风格文本（与 StyleConfig 二选一，自由文本直接入风格段） */
  style?: string
  /** 画布级风格配置（库条目解析产物），优先于 style 自由文本 */
  styleConfig?: StyleConfig
}

const DEFAULT_SHOT_MIN = 3
const DEFAULT_SHOT_MAX = 8
const MAX_ATTEMPTS = 2

function shotRange(opts: SplitOptions): { min: number; max: number } {
  const min = typeof opts.shotCountMin === 'number' && opts.shotCountMin >= 1 ? Math.floor(opts.shotCountMin) : DEFAULT_SHOT_MIN
  const max = typeof opts.shotCountMax === 'number' && opts.shotCountMax >= min ? Math.floor(opts.shotCountMax) : DEFAULT_SHOT_MAX
  return { min, max }
}

/** LLM 调用 + JSON 解析重试（两尝试，对齐原后端行为） */
async function callWithRetry<T>(opts: PipelineOptions, messages: Parameters<ChatTransport>[0], parse: (content: string) => T): Promise<T> {
  const transport = opts.transport || sseChatComplete
  const temperature = opts.temperature ?? 0.7
  let lastError: unknown = null
  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    const content = await transport(messages, { temperature, model: opts.model })
    try {
      return parse(content)
    } catch (e) {
      lastError = e
    }
  }
  throw new Error(`分镜管线解析失败: ${lastError instanceof Error ? lastError.message : String(lastError)}`)
}

/** 实体提取：剧本 → 角色/场景/物品清单 */
export async function extractEntities(scriptText: string, opts: PipelineOptions = {}): Promise<EntityGroup> {
  const data = await callWithRetry(opts, [{ role: 'user', content: extractEntitiesPrompt(scriptText) }], parseJsonObject)
  return {
    characters: parseEntities(data, 'character'),
    scenes: parseEntities(data, 'scene'),
    props: parseEntities(data, 'prop'),
  }
}

/** 项目制实体提取：剧本 → 带项目字段的实体草稿（对齐原后端 extract_entities_from_script 行为） */
export async function extractProjectEntities(
  scriptText: string,
  opts: PipelineOptions = {},
): Promise<ProjectEntityDraftGroup> {
  const data = await callWithRetry(
    { ...opts, temperature: opts.temperature ?? 0.5 },
    [{ role: 'user', content: projectEntitiesPrompt(scriptText) }],
    parseJsonObject,
  )
  return parseProjectEntities(data)
}

/** 项目制剧本生成：模板类别 + 参数 → 纯文本剧本（对齐原后端 wizard 第 1 步，temperature 0.8） */
export async function generateScript(
  category: WizardCategory,
  inputs: Record<string, unknown>,
  opts: PipelineOptions = {},
): Promise<string> {
  const content = await callWithRetry(
    { ...opts, temperature: opts.temperature ?? 0.8 },
    [{ role: 'user', content: scriptPrompt(category, inputs) }],
    (text) => text.trim(),
  )
  if (!content) throw new Error('剧本生成结果为空，可重试或调整参数')
  return content
}

/** 分镜拆分：给定实体 → 分镜列表（成品 prompt 经 buildFramePrompt 注入，风格走画布级 styleConfig） */
export async function splitStoryboard(
  scriptText: string,
  entities: EntityGroup,
  opts: SplitOptions & { styleConfig?: StyleConfig } = {},
): Promise<StoryboardShot[]> {
  const { min, max } = shotRange(opts)
  const data = await callWithRetry(
    opts,
    [{
      role: 'user',
      content: splitStoryboardPrompt({
        scriptText,
        characters: entities.characters,
        scenes: entities.scenes,
        props: entities.props,
        cameraVocabulary: opts.cameraVocabulary || [],
        shotCountMin: min,
        shotCountMax: max,
      }),
    }],
    parseJsonObject,
  )
  return shotsFromRaw(data, opts.styleConfig, entities)
}

/** 一枪出：给定实体沿用 + LLM 提取补全 + 分镜（对齐原 Composer/向导路径） */
export async function planStoryboard(
  scriptText: string,
  opts: PlanOptions = {},
): Promise<{ assets: EntityGroup; shots: StoryboardShot[] }> {
  const { min, max } = shotRange(opts)
  const styleText = opts.styleConfig
    ? [opts.styleConfig.prefix, opts.styleConfig.suffix].map((s) => s.trim()).filter(Boolean).join('，')
    : opts.style || ''
  const data = await callWithRetry(
    opts,
    [{
      role: 'user',
      content: planStoryboardPrompt({
        scriptText,
        characters: opts.characters || [],
        scenes: opts.scenes || [],
        style: styleText,
        cameraVocabulary: opts.cameraVocabulary || [],
        shotCountMin: min,
        shotCountMax: max,
      }),
    }],
    parseJsonObject,
  )
  const assetsRaw = isRecord(data.assets) ? data.assets : {}
  const assets: EntityGroup = {
    characters: parseEntities(assetsRaw, 'character'),
    scenes: parseEntities(assetsRaw, 'scene'),
    props: parseEntities(assetsRaw, 'prop'),
  }
  // 镜头上下文池 = 给定实体 + 提取实体按名合并（给定优先），保证新提取实体也进设定上下文
  const pool: EntityGroup = {
    characters: mergeByName(opts.characters || [], assets.characters),
    scenes: mergeByName(opts.scenes || [], assets.scenes),
    props: assets.props,
  }
  return { assets, shots: shotsFromRaw(data, opts.styleConfig, pool) }
}

/** 按名合并实体（keep 组优先，add 组中同名跳过） */
function mergeByName(keep: StoryboardEntity[], add: StoryboardEntity[]): StoryboardEntity[] {
  const names = new Set(keep.map((e) => e.name.trim()))
  const extra = add.filter((e) => e.name.trim() && !names.has(e.name.trim()))
  return [...keep, ...extra]
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

/** 解析 shots 数组并逐镜注入成品提示词（LLM 词表外运镜/景别回退已由 parseShot 收敛） */
function shotsFromRaw(
  data: Record<string, unknown>,
  style: StyleConfig | undefined,
  entities: EntityGroup,
): StoryboardShot[] {
  const rawShots = Array.isArray(data.shots) ? data.shots : []
  const shots: Omit<StoryboardShot, 'prompt'>[] = []
  for (const item of rawShots) {
    if (!isRecord(item)) continue
    shots.push(parseShot(item, shots.length + 1))
  }
  const byKind = (name: string): StoryboardEntity[] => {
    const lower = name.trim().toLowerCase()
    if (lower === 'character') return entities.characters
    if (lower === 'scene') return entities.scenes
    if (lower === 'prop') return entities.props
    return []
  }
  const empty: string[] = []
  return shots.map((shot) => {
    // 按镜头命中实体设定文本（未标注角色时回退全量，与原 buildShotContexts 语义一致）
    const hitTexts = (names: string[], kind: string): string[] => {
      const pool = byKind(kind)
      const wanted = names.map((n) => n.trim()).filter(Boolean)
      const hit = wanted.length > 0 ? pool.filter((e) => wanted.includes(e.name.trim())) : pool
      return hit.map((e) => (e.name ? `${e.name}：${e.description}` : e.description)).filter(Boolean)
    }
    const characterTexts = hitTexts(shot.characters, 'character')
    const sceneTexts = hitTexts(shot.location ? [shot.location] : empty, 'scene')
    const propTexts = hitTexts(shot.props, 'prop')
    return {
      ...shot,
      prompt: buildFramePrompt(shot, { characters: characterTexts, scenes: sceneTexts, props: propTexts }, style),
    }
  })
}

export { buildFramePrompt, buildAssetPrompt } from './prompts'
