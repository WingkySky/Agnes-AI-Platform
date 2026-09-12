/* =====================================================
 * 分镜管线统一数据结构（lib/storyboard，唯一 TS 源）
 * - 实体/分镜/风格三套类型 + 守卫式解析（容错 LLM JSON 输出）
 * - 画布 entity 节点（image 节点 content.kind 标记）、Agent 工具、向导共用
 * ===================================================== */

/** 实体类别：角色 / 场景 / 物品 */
export type EntityKind = 'character' | 'scene' | 'prop'

/** 统一实体（画布实体卡、Agent 工具出参、项目制字段对齐） */
export interface StoryboardEntity {
  kind: EntityKind
  name: string
  description: string
  /** 激活设定图 URL（角色三视图/空场景/物品图） */
  refImageUrl: string
}

/** 统一分镜（对齐画布 CanvasShot 字段；prompt 为成品分镜图提示词） */
export interface StoryboardShot {
  no: number
  /** 景别（从词表取值） */
  shotSize: string
  /** 运镜（从库词表取值） */
  camera: string
  /** 画面描述（单帧、可直接生图） */
  description: string
  /** 台词（不入图，视频阶段配音/字幕用） */
  dialogue: string
  /** 出场角色名（按名命中实体卡） */
  characters: string[]
  /** 场景名（按名命中实体卡） */
  location: string
  /** 出场物品名（按名命中实体卡） */
  props: string[]
  /** 成品分镜图提示词（含单帧约束/景别运镜/风格/设定上下文） */
  prompt: string
}

/** 运行时风格配置（来自 prompt_presets 库条目 prompt_config 或自定义文本） */
export interface StyleConfig {
  prefix: string
  suffix: string
  negativePrompt: string
}

/** 空风格（未选择时不注入风格段，流程不阻塞） */
export const EMPTY_STYLE: StyleConfig = { prefix: '', suffix: '', negativePrompt: '' }

/** 景别词表（拆分 LLM 只能取词表值） */
export const SHOT_SIZES = ['远景', '全景', '中景', '近景', '特写'] as const

export function isEntityKind(v: unknown): v is EntityKind {
  return v === 'character' || v === 'scene' || v === 'prop'
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function readString(v: unknown, fallback = ''): string {
  return typeof v === 'string' ? v : fallback
}

function readStringArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
}

/** 剥离 markdown 代码栅栏，容忍前后杂文（对齐原后端 _extract_json 行为） */
export function extractJsonText(content: string): string {
  const fence = /```(?:json)?\s*([\s\S]*?)\s*```/.exec(content.trim())
  return fence ? fence[1] : content.trim()
}

/** 从 LLM 输出解析 JSON 对象；失败抛错（由 pipeline 重试） */
export function parseJsonObject(content: string): Record<string, unknown> {
  const parsed: unknown = JSON.parse(extractJsonText(content))
  if (!isRecord(parsed)) throw new Error('LLM 输出不是 JSON 对象')
  return parsed
}

/** 守卫式解析实体清单（缺字段补默认，非法条目跳过） */
export function parseEntities(raw: Record<string, unknown>, kind: EntityKind): StoryboardEntity[] {
  const list = raw[kind === 'character' ? 'characters' : kind === 'scene' ? 'scenes' : 'props']
  if (!Array.isArray(list)) return []
  const out: StoryboardEntity[] = []
  for (const item of list) {
    if (!isRecord(item)) continue
    const name = readString(item.name).trim()
    if (!name) continue
    out.push({
      kind,
      name,
      description: readString(item.description).trim(),
      refImageUrl: readString(item.ref_image_url ?? item.refImageUrl).trim(),
    })
  }
  return out
}

/** 守卫式解析单条分镜（prompt 由调用方经 buildFramePrompt 补齐） */
export function parseShot(raw: Record<string, unknown>, fallbackNo: number): Omit<StoryboardShot, 'prompt'> {
  const shotSize = readString(raw.shot_size ?? raw.shotSize).trim()
  const sizes: readonly string[] = SHOT_SIZES
  return {
    no: typeof raw.no === 'number' && raw.no >= 1 ? raw.no : fallbackNo,
    shotSize: sizes.includes(shotSize) ? shotSize : '中景',
    camera: readString(raw.camera).trim(),
    description: readString(raw.description).trim(),
    dialogue: readString(raw.dialogue).trim(),
    characters: readStringArray(raw.characters),
    location: readString(raw.location).trim(),
    props: readStringArray(raw.props),
  }
}

/** 守卫式解析风格配置（未知结构回退空风格） */
export function parseStyleConfig(raw: unknown): StyleConfig {
  if (!isRecord(raw)) return { ...EMPTY_STYLE }
  return {
    prefix: readString(raw.prefix).trim(),
    suffix: readString(raw.suffix).trim(),
    negativePrompt: readString(raw.negative_prompt ?? raw.negativePrompt).trim(),
  }
}

/* =====================================================
 * 项目制实体草稿（字段对齐 ProjectCharacter/Scene/Prop 列）
 * ===================================================== */

/** 项目制实体草稿（提取结果，落库前由调用方映射到对应实体列） */
export interface ProjectEntityDraft {
  name: string
  description: string
  /** 仅角色：外观描述（用于生图） */
  appearanceDesc: string
  /** 仅角色：main/supporting/minor */
  roleType: string
  /** 仅场景：地点 */
  location: string
  /** 仅场景：白天/夜晚/黄昏 */
  timeOfDay: string
  /** 仅场景：氛围 */
  atmosphere: string
  /** 仅道具：视觉描述（用于生图） */
  visualDesc: string
}

export interface ProjectEntityDraftGroup {
  characters: ProjectEntityDraft[]
  scenes: ProjectEntityDraft[]
  props: ProjectEntityDraft[]
}

/** 守卫式解析项目制实体清单（缺字段补默认，非法条目跳过） */
export function parseProjectEntities(raw: Record<string, unknown>): ProjectEntityDraftGroup {
  const readList = (key: string): ProjectEntityDraft[] => {
    const list = raw[key]
    if (!Array.isArray(list)) return []
    const out: ProjectEntityDraft[] = []
    for (const item of list) {
      if (!isRecord(item)) continue
      const name = readString(item.name).trim()
      if (!name) continue
      out.push({
        name,
        description: readString(item.description).trim(),
        appearanceDesc: readString(item.appearance_desc ?? item.appearanceDesc).trim(),
        roleType: readString(item.role_type ?? item.roleType, 'supporting').trim(),
        location: readString(item.location).trim(),
        timeOfDay: readString(item.time_of_day ?? item.timeOfDay).trim(),
        atmosphere: readString(item.atmosphere).trim(),
        visualDesc: readString(item.visual_desc ?? item.visualDesc).trim(),
      })
    }
    return out
  }
  return { characters: readList('characters'), scenes: readList('scenes'), props: readList('props') }
}
