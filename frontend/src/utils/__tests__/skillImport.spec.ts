/* 技能整包导入解析单测：frontmatter 映射/资源收集/二进制跳过/allowed-tools 映射/上限/致命错误 */

import { describe, it, expect } from 'vitest'
import { zipSync, strToU8, unzipSync } from 'fflate'
import { parseSkillPackage, mapAllowedTools, type SkillImportInput } from '../skillImport'
import { filterSkills } from '@/lib/agent/skills'
import type { AgentSkill } from '@/lib/agent/skills'

const SKILL_MD = `---
name: 分镜节奏
description: 规划分镜时使用
version: 2
---
方法论正文第一段。`

function pkg(entries: Record<string, string>): SkillImportInput[] {
  return Object.entries(entries).map(([path, text]) => ({ path, text }))
}

describe('parseSkillPackage', () => {
  it('标准 SKILL.md：name/description 映射、正文提取、未知键进 import_meta', () => {
    const r = parseSkillPackage(pkg({ 'SKILL.md': SKILL_MD }))
    expect(r.name).toBe('分镜节奏')
    expect(r.description).toBe('规划分镜时使用')
    expect(r.content).toBe('方法论正文第一段。')
    expect(r.importMeta.frontmatter).toMatchObject({ name: '分镜节奏', version: 2 })
  })

  it('包外裹一层目录：定位最浅层 SKILL.md，资源路径相对技能根', () => {
    const r = parseSkillPackage(
      pkg({ 'my-skill/SKILL.md': SKILL_MD, 'my-skill/references/api.md': '参考内容', 'other/readme.md': '无关' })
    )
    expect(r.name).toBe('分镜节奏')
    expect(r.resources.map((x) => x.path)).toEqual(['references/api.md', 'other/readme.md'])
    expect(r.resources[0].content).toBe('参考内容')
  })

  it('缺 name 用 SKILL.md 文件名兜底并告警；缺 description 告警', () => {
    const r = parseSkillPackage(pkg({ 'SKILL.md': '---\n\n---\n正文' }))
    expect(r.name).toBe('SKILL')
    expect(r.warnings.some((w) => w.includes('name'))).toBe(true)
    expect(r.warnings.some((w) => w.includes('description'))).toBe(true)
  })

  it('无 SKILL.md 报错', () => {
    expect(() => parseSkillPackage(pkg({ 'a.md': '普通文本' }))).toThrow('SKILL.md')
  })

  it('SKILL.md 缺 frontmatter 报错', () => {
    expect(() => parseSkillPackage(pkg({ 'SKILL.md': '普通文本' }))).toThrow('frontmatter')
  })

  it('非法 frontmatter YAML 报错', () => {
    expect(() => parseSkillPackage(pkg({ 'SKILL.md': '---\nname: [unclosed\n---\n正文' }))).toThrow('YAML')
  })

  it('frontmatter tag/alias 进短标识', () => {
    const r = parseSkillPackage(pkg({ 'SKILL.md': '---\nname: A\nalias: a-短\n---\n正文' }))
    expect(r.tag).toBe('a-短')
    expect(parseSkillPackage(pkg({ 'SKILL.md': SKILL_MD })).tag).toBe('')
  })

  it('文本文件进资源（含脚本存档）；二进制跳过并报告', () => {
    const r = parseSkillPackage(
      pkg({ 'SKILL.md': SKILL_MD, 'references/api.md': '参考细节', 'scripts/run.py': 'print(1)', 'logo.png': '\u0000\uFFFD二进制' })
    )
    expect(r.content).not.toContain('附件')
    expect(r.resources.map((x) => x.path)).toEqual(['references/api.md', 'scripts/run.py'])
    expect(r.resources[1].content).toBe('print(1)')
    expect(r.skipped).toEqual(['logo.png'])
    expect(r.warnings.some((w) => w.includes('logo.png'))).toBe(true)
  })

  it('资源超限：单文件超限跳过并告警', () => {
    const big = 'x'.repeat(100_001)
    const r = parseSkillPackage(pkg({ 'SKILL.md': SKILL_MD, 'big.md': big, 'ok.md': 'ok' }))
    expect(r.skipped).toContain('big.md')
    expect(r.resources.map((x) => x.path)).toEqual(['ok.md'])
  })

  it('allowed-tools 解析：字符串逗号分隔、数组、"Name(pattern)" 取 Name', () => {
    const r = parseSkillPackage(pkg({ 'SKILL.md': '---\nname: A\ndescription: d\nallowed-tools: agent_apply_ops, Bash(git *)\n---\n正文' }))
    expect(r.allowedTools).toEqual(['agent_apply_ops'])
    expect(r.importMeta.allowed_tools_raw).toEqual(['agent_apply_ops', 'Bash'])
    const r2 = parseSkillPackage(pkg({ 'SKILL.md': '---\nname: A\nallowed-tools:\n  - generate_image\n---\n正文' }))
    expect(r2.allowedTools).toEqual(['generate_image'])
  })

  it('allowed-tools 全部映射不上：allowedTools 为空 + 告警，raw 留存', () => {
    const r = parseSkillPackage(pkg({ 'SKILL.md': '---\nname: A\nallowed-tools: Bash, Read\n---\n正文' }))
    expect(r.allowedTools).toEqual([])
    expect(r.importMeta.allowed_tools_raw).toEqual(['Bash', 'Read'])
    expect(r.warnings.some((w) => w.includes('allowed-tools'))).toBe(true)
  })

  it('zip 整包（fflate 压缩 → 解析）：路径与内容一致', () => {
    const zipped = zipSync({ 'SKILL.md': strToU8(SKILL_MD), 'references/x.md': strToU8('zip 参考') })
    const entries = unzipSync(zipped)
    const inputs: SkillImportInput[] = Object.entries(entries)
      .filter(([p]) => !p.endsWith('/'))
      .map(([path, data]) => ({ path, text: new TextDecoder().decode(data) }))
    const r = parseSkillPackage(inputs)
    expect(r.name).toBe('分镜节奏')
    expect(r.resources).toEqual([{ path: 'references/x.md', content: 'zip 参考' }])
  })
})

describe('mapAllowedTools', () => {
  it('产品工具名精确匹配（大小写不敏感），未知条目丢弃', () => {
    expect(mapAllowedTools(['AGENT_APPLY_OPS', 'Bash', 'generate_image'])).toEqual(['agent_apply_ops', 'generate_image'])
    expect(mapAllowedTools([])).toEqual([])
  })
})

describe('filterSkills', () => {
  const mk = (name: string, tag: string, description: string, extra: Partial<AgentSkill> = {}): AgentSkill => ({
    id: 1, name, tag, description, content: 'x', disabled: false, allowedTools: [], ...extra,
  })
  const skills: AgentSkill[] = [
    mk('分镜节奏与情绪曲线', '节奏', '规划分镜'),
    mk('台词打磨', '台词', '修改剧本对白'),
    mk('台词写作进阶', '', '对白技巧'),
    mk('已停用技能', '停用', '不出现', { disabled: true }),
  ]
  it('空 query 返回全部未停用技能', () => {
    expect(filterSkills(skills, '')).toHaveLength(3)
  })
  it('tag 前缀优先于名称包含（相关度排序）', () => {
    const out = filterSkills(skills, '台词')
    expect(out[0].name).toBe('台词打磨')
  })
  it('描述命中也可过滤；无命中返回空', () => {
    expect(filterSkills(skills, '对白').map((s) => s.name)).toEqual(['台词打磨', '台词写作进阶'])
    expect(filterSkills(skills, '不存在')).toEqual([])
  })
  it('tag 完全相等排最前', () => {
    const out = filterSkills(skills, '节奏')
    expect(out[0].tag).toBe('节奏')
  })
  it('停用技能不出现（按名检索也不出现）', () => {
    expect(filterSkills(skills, '停用')).toEqual([])
  })
})
