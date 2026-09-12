/* Agent 技能模块单测：清单拉取/降级/映射、技能段渲染、缓存查询 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { listAgentSkills, getCachedSkills, getCachedSkill, buildSkillsSection } from '../skills'

vi.mock('@/api/client', () => ({
  default: { get: vi.fn() },
}))

import client from '@/api/client'

beforeEach(() => {
  vi.mocked(client.get).mockReset()
  // 清模块缓存：直接置空一次失败响应再校验，或用 __ internals？——通过成功请求覆盖
})

describe('listAgentSkills', () => {
  it('拉取广场技能并映射 name/description/prompt_text，过滤无名/无正文库点', async () => {
    vi.mocked(client.get).mockResolvedValueOnce({
      items: [
        { id: 1, name: ' 分镜节奏 ', description: '规划分镜时', prompt_text: '方法论正文', prompt_config: { tag: '节奏' } },
        { id: 2, name: '', prompt_text: '无名跳过' },
        { id: 3, name: '空正文', prompt_text: '  ' },
      ],
    })
    const skills = await listAgentSkills(true)
    expect(skills).toHaveLength(1)
    expect(skills[0]).toEqual({ name: '分镜节奏', tag: '节奏', description: '规划分镜时', content: '方法论正文' })
    expect(vi.mocked(client.get)).toHaveBeenCalledWith('/api/presets', { params: { tab: 'plaza', type: 'skill', page_size: 100 } })
  })

  it('请求失败降级：保留旧缓存不抛错（无旧缓存则空表）', async () => {
    // 前序用例已建立缓存（分镜节奏）；失败刷新不应清空它
    vi.mocked(client.get).mockRejectedValueOnce(new Error('网络错误'))
    const skills = await listAgentSkills(true)
    expect(skills).toHaveLength(1)
    expect(skills[0].name).toBe('分镜节奏')
  })

  it('非 force 时命中缓存不再发请求', async () => {
    const before = vi.mocked(client.get).mock.calls.length
    await listAgentSkills()
    expect(vi.mocked(client.get).mock.calls.length).toBe(before)
  })

  it('getCachedSkill 忽略大小写与首尾空白', () => {
    expect(getCachedSkill(' 分镜节奏 ')?.name).toBe('分镜节奏')
    expect(getCachedSkill('不存在')).toBeUndefined()
    expect(getCachedSkills().length).toBeGreaterThan(0)
  })
})

describe('buildSkillsSection', () => {
  it('空列表返回空串（整段省略）', () => {
    expect(buildSkillsSection([])).toBe('')
  })

  it('渲染名称+用途清单与加载指引', () => {
    const s = buildSkillsSection([{ name: 'A 技能', tag: '', description: '场景 X', content: '正文' }])
    expect(s).toContain('## 可用技能')
    expect(s).toContain('- A 技能：场景 X')
    expect(s).toContain('agent_load_skill')
    expect(s).not.toContain('正文')
  })
})
