/* 技能导出单测：frontmatter 装配 + 与 skillImport 解析互逆 */

import { describe, it, expect } from 'vitest'
import { skillToSkillMd } from '../skillExport'
import { parseSkillPackage } from '../skillImport'

describe('skillToSkillMd', () => {
  it('装配 frontmatter（name/description/tag）+ 正文', () => {
    const md = skillToSkillMd({
      name: '分镜师',
      description: '当用户规划分镜时使用',
      prompt_text: '正文内容',
      prompt_config: { tag: '分镜' },
    })
    expect(md.startsWith('---\n')).toBe(true)
    expect(md).toContain('name: 分镜师')
    expect(md).toContain('tag: 分镜')
    expect(md.trimEnd().endsWith('正文内容')).toBe(true)
  })

  it('与 skillImport 解析互逆（roundtrip，特殊字符安全）', () => {
    const md = skillToSkillMd({
      name: '转译技能: 测试',
      description: 'desc: with colon',
      prompt_text: '正文\n第二行',
      prompt_config: { tag: 't' },
    })
    const r = parseSkillPackage([{ path: 'SKILL.md', text: md }])
    expect(r.name).toBe('转译技能: 测试')
    expect(r.description).toBe('desc: with colon')
    expect(r.tag).toBe('t')
    expect(r.content).toBe('正文\n第二行')
  })
})
