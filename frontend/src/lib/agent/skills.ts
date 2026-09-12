/* =====================================================
 * Agent 技能（lib/agent，UI 无关）
 *
 * - 技能 = prompt_presets type='skill' 行：name=技能名、description=何时使用、prompt_text=正文
 * - 渐进披露：系统提示只列名称+用途（buildSkillsSection），正文经 agent_load_skill 按需加载
 * - 数据形态：name/description/content；加载源为能力库而非文件系统
 * ===================================================== */

import client from '@/api/client'
import type { PromptPreset } from '@/types/preset'

export interface AgentSkill {
  name: string
  /** 短标识（/ 快速对齐用；prompt_config.tag） */
  tag: string
  description: string
  content: string
}

/** 模块级缓存：会话建立时刷新，agent_load_skill 执行器直接读 */
let cache: AgentSkill[] | null = null

/** 当前缓存技能（未拉取过时为空；不触发请求） */
export function getCachedSkills(): AgentSkill[] {
  return cache ?? []
}

/** 按名取技能（trim + 忽略大小写，容错模型输出） */
export function getCachedSkill(name: string): AgentSkill | undefined {
  const lower = name.trim().toLowerCase()
  return (cache ?? []).find((s) => s.name.trim().toLowerCase() === lower || (s.tag && s.tag.toLowerCase() === lower))
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
        name: (p.name || '').trim(),
        tag: typeof p.prompt_config === 'object' && p.prompt_config !== null && typeof (p.prompt_config as { tag?: unknown }).tag === 'string'
          ? ((p.prompt_config as { tag: string }).tag || '').trim()
          : '',
        description: (p.description || '').trim(),
        content: (p.prompt_text || '').trim(),
      }))
      .filter((s) => s.name && s.content)
    return cache
  } catch {
    return cache ?? []
  }
}

/** 系统提示「可用技能」段：空列表返回 ''（整段省略，Agent 正常工作） */
export function buildSkillsSection(skills: AgentSkill[]): string {
  if (skills.length === 0) return ''
  const lines = skills.map((s) => `- ${s.name}：${s.description || '（无描述）'}`).join('\n')
  return [
    '## 可用技能',
    '下列技能是可加载的方法论知识包。当用户的问题或当前任务命中某技能的适用场景时，先调用 agent_load_skill(name) 获取完整内容，再按其指引回答或动手；不要凭技能名臆测内容。',
    '用户消息以「【使用技能：技能名】」开头时，先调用 agent_load_skill 加载该技能，再处理其后的内容。',
    lines,
  ].join('\n')
}

/**
 * 按名称/描述子串过滤技能（"/" 快速清单用；query 为空返回全部）。
 * 相关度排序对齐主流 Agent：tag 全等 > tag 前缀 > 名称前缀 > 包含——边输入边收敛到最合适的技能。
 */
export function filterSkills(skills: AgentSkill[], query: string): AgentSkill[] {
  const q = query.trim().toLowerCase()
  if (!q) return skills
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
  return skills
    .map((s) => ({ s, k: score(s) }))
    .filter((x) => x.k > 0)
    .sort((a, b) => b.k - a.k)
    .map((x) => x.s)
}
