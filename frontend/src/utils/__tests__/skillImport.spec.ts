/* SKILL.md 导入解析单测：frontmatter 映射/兜底/附件并入/跳过报告/致命错误 */

import { describe, it, expect } from 'vitest'
import { parseSkillImport } from '../skillImport'
import { filterSkills } from '@/lib/agent/skills'
import type { AgentSkill } from '@/lib/agent/skills'

const SKILL_MD = `---
name: 分镜节奏
description: 规划分镜时使用
version: 2
---
方法论正文第一段。`

describe('parseSkillImport', () => {
  it('标准 SKILL.md：name/description 映射、正文提取、未知键进 import_meta', () => {
    const r = parseSkillImport([{ name: 'SKILL.md', text: SKILL_MD }])
    expect(r.name).toBe('分镜节奏')
    expect(r.description).toBe('规划分镜时使用')
    expect(r.content).toBe('方法论正文第一段。')
    expect(r.importMeta.frontmatter).toMatchObject({ name: '分镜节奏', version: 2 })
  })

  it('缺 name 用文件名兜底并告警；缺 description 告警', () => {
    const r = parseSkillImport([{ name: 'my-skill.md', text: '---\n\n---\n正文' }])
    expect(r.name).toBe('my-skill')
    expect(r.warnings.some((w) => w.includes('name'))).toBe(true)
    expect(r.warnings.some((w) => w.includes('description'))).toBe(true)
  })

  it('无 frontmatter 报错', () => {
    expect(() => parseSkillImport([{ name: 'a.md', text: '普通文本' }])).toThrow('未找到技能主文件')
  })

  it('非法 frontmatter YAML 报错', () => {
    expect(() => parseSkillImport([{ name: 'SKILL.md', text: '---\nname: [unclosed\n---\n正文' }])).toThrow('YAML')
  })

  it('frontmatter tag/alias 进短标识', () => {
    const r = parseSkillImport([{ name: 'SKILL.md', text: '---\nname: A\nalias: a-短\n---\n正文' }])
    expect(r.tag).toBe('a-短')
    const r2 = parseSkillImport([{ name: 'SKILL.md', text: SKILL_MD }])
    expect(r2.tag).toBe('')
  })

  it('md 附件并入正文；脚本文件跳过并报告', () => {
    const r = parseSkillImport([
      { name: 'SKILL.md', text: SKILL_MD },
      { name: 'references.md', text: '参考细节' },
      { name: 'run.py', text: 'print(1)' },
    ])
    expect(r.content).toContain('## 附件：references.md')
    expect(r.content).toContain('参考细节')
    expect(r.skipped).toEqual(['run.py'])
    expect(r.warnings.some((w) => w.includes('run.py'))).toBe(true)
  })
})

describe('filterSkills', () => {
  const skills: AgentSkill[] = [
    { name: '分镜节奏与情绪曲线', tag: '节奏', description: '规划分镜', content: 'x' },
    { name: '台词打磨', tag: '台词', description: '修改剧本对白', content: 'y' },
    { name: '台词写作进阶', tag: '', description: '对白技巧', content: 'z' },
  ]
  it('空 query 返回全部', () => {
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
})
