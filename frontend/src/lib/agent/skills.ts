/* =====================================================
 * Agent 技能（lib/agent，UI 无关）
 *
 * - 技能 = prompt_presets type='skill' 行：name=技能名、description=何时使用、prompt_text=正文
 * - 渐进披露：L1 系统提示只列名称+用途（buildSkillsSection）；L2 正文经 agent_load_skill 按需加载；
 *   L3 附件资源（prompt_config.resources）按需经 agent_read_skill_file 读取（脚本仅存档不执行）
 * - allowed_tools 非空的技能加载时设置工具围栏（内核 beforeToolCall 强制收窄）
 * - Agent 创建/转译的技能经 saveAgentSkill 落库（校验 + 同名拒重 + 刷缓存），画布/对话工具共用
 * ===================================================== */

import client from '@/api/client'
import { createPreset, getPreset } from '@/api/presets'
import type { PromptPreset, SkillResource } from '@/types/preset'

export interface AgentSkill {
  id: number
  name: string
  /** 短标识（/ 快速对齐用；prompt_config.tag） */
  tag: string
  description: string
  content: string
  /** 我的技能停用标记（停用后不进技能清单） */
  disabled: boolean
  /** 工具白名单（prompt_config.allowed_tools，空 = 不限制） */
  allowedTools: string[]
}

/** 模块级缓存：会话建立时刷新，agent_load_skill 执行器直接读 */
let cache: AgentSkill[] | null = null

/** 资源明细缓存（列表接口不携带 resources，load/read 时按需拉详情） */
const detailCache = new Map<number, SkillResource[]>()

/** 单次资源读取上限（防超长资源挤爆上下文） */
export const SKILL_RESOURCE_READ_MAX_CHARS = 20000

/** 停用技能不进清单（官方/过审技能无 disabled 标记，恒可用） */
export function isEnabled(skill: AgentSkill): boolean {
  return !skill.disabled
}

/** 当前缓存技能（未拉取过时为空；不触发请求） */
export function getCachedSkills(): AgentSkill[] {
  return cache ?? []
}

/** 按名取技能（trim + 忽略大小写，容错模型输出） */
export function getCachedSkill(name: string): AgentSkill | undefined {
  const lower = name.trim().toLowerCase()
  return (cache ?? []).find((s) => s.name.trim().toLowerCase() === lower || (s.tag && s.tag.toLowerCase() === lower))
}

/** 守卫提取 prompt_config.resources */
function resourcesOf(preset: PromptPreset): SkillResource[] {
  const list = preset.prompt_config?.resources
  if (!Array.isArray(list)) return []
  return list.filter((r): r is SkillResource => typeof r?.path === 'string' && typeof r?.content === 'string')
}

/** 拉取技能资源明细（详情接口；模块级缓存，会话期内不重复请求） */
export async function getSkillResources(skill: AgentSkill): Promise<SkillResource[]> {
  const hit = detailCache.get(skill.id)
  if (hit) return hit
  const preset = await getPreset(skill.id)
  const resources = resourcesOf(preset)
  detailCache.set(skill.id, resources)
  return resources
}

/** L3 资源清单文案（load_skill 结果附加；空资源返回 ''） */
export function skillManifestText(resources: SkillResource[]): string {
  if (resources.length === 0) return ''
  const lines = resources.map((r) => {
    const script = /\.(py|js|mjs|cjs|ts|jsx|tsx|sh|bash|zsh|sql)$/i.test(r.path)
    return `- ${r.path}（${r.content.length} 字符${script ? '，脚本仅存档不执行' : ''}）`
  })
  return [
    '',
    '## 附件资源',
    '以下文件可用 agent_read_skill_file(skill, path) 按需读取原文；脚本只存档，当前不会被执行，也不要声称已运行：',
    ...lines,
  ].join('\n')
}

// ---------- 工具围栏（allowed_tools 声明式权限） ----------

const SKILL_SCOPE_EXEMPT = new Set(['agent_load_skill', 'agent_read_skill_file'])
let activeScope: Set<string> | null = null

/** agent_load_skill 执行时设置：白名单非空的技能收窄可用工具，空/未声明 = 不限制 */
export function setActiveSkillScope(allowedTools: string[]): void {
  activeScope = allowedTools.length > 0 ? new Set([...allowedTools, ...SKILL_SCOPE_EXEMPT]) : null
}

/** 内核 beforeToolCall 读取；null = 不限制 */
export function getActiveSkillScope(): Set<string> | null {
  return activeScope
}

/**
 * agent_load_skill 共用执行体（画布/对话工具同款）：设置工具围栏 + 拼资源清单（L3）。
 * 技能不存在抛中文 Error，工具层捕获后回填 LLM。
 */
export async function loadAgentSkillFull(name: string): Promise<{ name: string; description: string; content: string }> {
  const skill = getCachedSkill(name)
  if (!skill) {
    const available = getCachedSkills().filter(isEnabled).map((s) => s.name).join('、') || '（技能库为空）'
    throw new Error(`技能「${name}」不存在。可用技能：${available}`)
  }
  setActiveSkillScope(skill.allowedTools)
  const resources = await getSkillResources(skill).catch(() => [])
  return { name: skill.name, description: skill.description, content: skill.content + skillManifestText(resources) }
}

/** agent_read_skill_file 共用执行体：按路径读资源原文，超长截断并标注 */
export async function readSkillResource(name: string, path: string): Promise<{ path: string; content: string }> {
  const skill = getCachedSkill(name)
  if (!skill) throw new Error(`技能「${name}」不在当前技能库中，请先确认名称`)
  const resources = await getSkillResources(skill)
  const target = path.trim()
  const res = resources.find((r) => r.path === target || r.path.toLowerCase() === target.toLowerCase())
  if (!res) {
    throw new Error(`资源「${path}」不存在。可用资源：${resources.map((r) => r.path).join('、') || '（无）'}`)
  }
  if (res.content.length <= SKILL_RESOURCE_READ_MAX_CHARS) return { path: res.path, content: res.content }
  return {
    path: res.path,
    content: `${res.content.slice(0, SKILL_RESOURCE_READ_MAX_CHARS)}\n\n（已截断：全文共 ${res.content.length} 字符）`,
  }
}

/**
 * 拉取技能清单（广场官方+已过审技能）。
 * 失败降级：保留旧缓存；无旧缓存则返回空列表且不缓存失败结果——技能库不可用不阻塞 Agent。
 */
export async function listAgentSkills(force = false): Promise<AgentSkill[]> {
  if (cache && !force) return cache
  try {
    const resp = await client.get('/api/presets', { params: { tab: 'plaza', type: 'skill', page_size: 100 } })
    const list = (resp as { items?: PromptPreset[] })?.items ?? []
    cache = list
      .map((p) => ({
        id: p.id,
        name: (p.name || '').trim(),
        tag: (p.prompt_config?.tag || '').trim(),
        description: (p.description || '').trim(),
        content: (p.prompt_text || '').trim(),
        disabled: p.prompt_config?.disabled === true,
        allowedTools: Array.isArray(p.prompt_config?.allowed_tools)
          ? p.prompt_config.allowed_tools.filter((s): s is string => typeof s === 'string')
          : [],
      }))
      .filter((s) => s.name && s.content)
    return cache
  } catch {
    return cache ?? []
  }
}

/** 系统提示「可用技能」段：空列表返回 ''（整段省略，Agent 正常工作） */
export function buildSkillsSection(skills: AgentSkill[]): string {
  const enabled = skills.filter(isEnabled)
  if (enabled.length === 0) return ''
  const lines = enabled.map((s) => `- ${s.name}：${s.description || '（无描述）'}`).join('\n')
  return [
    '## 可用技能',
    '下列技能是可加载的方法论知识包。当用户的问题或当前任务命中某技能的适用场景时，先调用 agent_load_skill(name) 获取完整内容，再按其指引回答或动手；不要凭技能名臆测内容。',
    '用户消息以「【使用技能：技能名】」开头时，先调用 agent_load_skill 加载该技能，再处理其后的内容。',
    lines,
  ].join('\n')
}

/**
 * 按名称/描述子串过滤技能（"/" 快速清单用；query 为空返回全部，停用技能不出现）。
 * 相关度排序对齐主流 Agent：tag 全等 > tag 前缀 > 名称前缀 > 包含——边输入边收敛到最合适的技能。
 */
export function filterSkills(skills: AgentSkill[], query: string): AgentSkill[] {
  const pool = skills.filter(isEnabled)
  const q = query.trim().toLowerCase()
  if (!q) return pool
  const score = (s: AgentSkill): number => {
    const tag = s.tag.toLowerCase()
    const name = s.name.toLowerCase()
    const desc = s.description.toLowerCase()
    if (tag === q) return 4
    if (tag.startsWith(q)) return 3
    if (name.startsWith(q)) return 2
    if (name.includes(q) || tag.includes(q) || desc.includes(q)) return 1
    return 0
  }
  return pool
    .map((s) => ({ s, k: score(s) }))
    .filter((x) => x.k > 0)
    .sort((a, b) => b.k - a.k)
    .map((x) => x.s)
}

// ---------- 技能保存（Agent 创建/转译落库，画布与对话工具共用） ----------

/** 技能正文上限：清单+正文都会进模型上下文，超长直接拒绝 */
export const SKILL_CONTENT_MAX_CHARS = 20000

export interface SaveAgentSkillInput {
  name: string
  /** "何时使用"触发行（系统提示技能清单只列 name+description），必填 */
  description: string
  content: string
  /** 短标识（/ 快速清单对齐用，可空） */
  tag?: string
  /** 转译溯源（来源格式、原始 frontmatter、丢弃清单等），记入 prompt_config.import_meta */
  importMeta?: Record<string, unknown>
}

export interface SaveAgentSkillResult {
  name: string
  tag: string
}

/** Agent 技能落库：校验 → 同名拒重 → createPreset → 刷缓存。失败抛中文 Error，工具层捕获后直接回填 LLM */
export async function saveAgentSkill(input: SaveAgentSkillInput): Promise<SaveAgentSkillResult> {
  const name = input.name.trim()
  const description = input.description.trim()
  const content = input.content.trim()
  const tag = (input.tag || '').trim()
  if (!name) throw new Error('技能名为空：必须提供 name')
  if (!description) throw new Error('description 为空：它是技能清单里的"何时使用"触发行，必须提供')
  if (!content) throw new Error('技能正文为空：必须提供 content')
  if (content.length > SKILL_CONTENT_MAX_CHARS) {
    throw new Error(`技能正文超长（${content.length} > ${SKILL_CONTENT_MAX_CHARS} 字符），请精简后再保存`)
  }
  const existing = await listAgentSkills(true)
  if (existing.some((s) => s.name.toLowerCase() === name.toLowerCase())) {
    throw new Error(`同名技能已存在：「${name}」（按名加载不允许歧义），请换名，或到预设中心编辑原技能`)
  }
  await createPreset({
    type: 'skill',
    name,
    description,
    prompt_text: content,
    category: '技能',
    prompt_config: { tag: tag || undefined, import_meta: input.importMeta },
    source: 'agent_created',
  })
  // 刷新缓存：当前会话 agent_load_skill 立即可用
  await listAgentSkills(true)
  return { name, tag }
}
