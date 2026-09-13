/* Agent 技能模块单测：清单拉取/降级/映射、技能段渲染（停用过滤）、缓存查询、L3 资源、工具围栏、Agent 落库保存 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  listAgentSkills, getCachedSkills, getCachedSkill, buildSkillsSection,
  saveAgentSkill, SKILL_CONTENT_MAX_CHARS,
  loadAgentSkillFull, readSkillResource, getActiveSkillScope,
} from '../skills'

vi.mock('@/api/client', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

import client from '@/api/client'

beforeEach(() => {
  vi.mocked(client.get).mockReset()
  vi.mocked(client.post).mockReset()
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
    expect(skills[0]).toEqual({
      id: 1, name: '分镜节奏', tag: '节奏', description: '规划分镜时', content: '方法论正文', disabled: false, allowedTools: [],
    })
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

  it('渲染名称+用途清单与加载指引；停用技能不出现', () => {
    const s = buildSkillsSection([{ id: 1, name: 'A 技能', tag: '', description: '场景 X', content: '正文', disabled: false, allowedTools: [] }])
    expect(s).toContain('## 可用技能')
    expect(s).toContain('- A 技能：场景 X')
    expect(s).toContain('agent_load_skill')
    expect(s).not.toContain('正文')
    const off = buildSkillsSection([{ id: 2, name: '停用', tag: '', description: 'x', content: 'y', disabled: true, allowedTools: [] }])
    expect(off).toBe('')
  })
})

describe('loadAgentSkillFull / readSkillResource（L3 资源与工具围栏）', () => {
  it('加载拼资源清单并设置围栏；资源详情拉取一次后走缓存', async () => {
    vi.mocked(client.get).mockImplementation(async (url: string) => {
      if (url === '/api/presets') {
        return { items: [{ id: 5, name: '整包技能', description: 'd', prompt_text: '正文', prompt_config: { allowed_tools: ['agent_apply_ops'] } }] }
      }
      if (url === '/api/presets/5') {
        return { prompt_config: { resources: [{ path: 'scripts/run.py', content: 'print(1)' }] } }
      }
      throw new Error('unexpected ' + url)
    })
    await listAgentSkills(true)
    const r = await loadAgentSkillFull('整包技能')
    expect(r.content).toContain('## 附件资源')
    expect(r.content).toContain('scripts/run.py')
    expect(r.content).toContain('不执行')
    const scope = getActiveSkillScope()
    expect(scope?.has('agent_apply_ops')).toBe(true)
    expect(scope?.has('agent_load_skill')).toBe(true)
    expect(scope?.has('generate_image')).toBe(false)
    const calls = vi.mocked(client.get).mock.calls.length
    const res = await readSkillResource('整包技能', 'scripts/run.py')
    expect(res.content).toBe('print(1)')
    expect(vi.mocked(client.get).mock.calls.length).toBe(calls)
  })

  it('无 allowed_tools 的技能加载后围栏为 null（不限制）；资源拉取失败降级空清单', async () => {
    vi.mocked(client.get).mockResolvedValueOnce({ items: [{ id: 6, name: '普通技能', description: 'd', prompt_text: 'x' }] })
    await listAgentSkills(true)
    const r = await loadAgentSkillFull('普通技能')
    expect(r.content).not.toContain('附件资源')
    expect(getActiveSkillScope()).toBeNull()
  })

  it('readSkillResource：路径不存在报错列出可用资源；超长截断', async () => {
    vi.mocked(client.get).mockImplementation(async (url: string) => {
      if (url === '/api/presets') return { items: [{ id: 7, name: '长资源技能', description: 'd', prompt_text: 'x' }] }
      if (url === '/api/presets/7') return { prompt_config: { resources: [{ path: 'big.md', content: 'y'.repeat(25000) }] } }
      throw new Error('unexpected ' + url)
    })
    await listAgentSkills(true)
    await expect(readSkillResource('长资源技能', 'nope.md')).rejects.toThrow('不存在')
    const r = await readSkillResource('长资源技能', 'big.md')
    expect(r.content.length).toBeLessThan(25000)
    expect(r.content).toContain('已截断')
  })
})

describe('saveAgentSkill', () => {
  it('name/description/正文缺失抛错且不发请求', async () => {
    await expect(saveAgentSkill({ name: 'A', description: '', content: 'x' })).rejects.toThrow('description 为空')
    await expect(saveAgentSkill({ name: '  ', description: 'd', content: 'x' })).rejects.toThrow('技能名为空')
    await expect(saveAgentSkill({ name: 'A', description: 'd', content: '   ' })).rejects.toThrow('技能正文为空')
    expect(vi.mocked(client.post)).not.toHaveBeenCalled()
  })

  it('正文超长抛错', async () => {
    await expect(saveAgentSkill({ name: 'A', description: 'd', content: 'x'.repeat(SKILL_CONTENT_MAX_CHARS + 1) })).rejects.toThrow('超长')
    expect(vi.mocked(client.post)).not.toHaveBeenCalled()
  })

  it('同名拒重（trim + 大小写不敏感），不创建', async () => {
    vi.mocked(client.get).mockResolvedValueOnce({ items: [{ id: 1, name: '分镜节奏', prompt_text: 'x' }] })
    await expect(saveAgentSkill({ name: ' 分镜节奏 ', description: 'd', content: 'c' })).rejects.toThrow('同名技能已存在')
    expect(vi.mocked(client.post)).not.toHaveBeenCalled()
  })

  it('成功：trim 入参、createPreset 落库（type=skill/source=agent_created）并刷缓存', async () => {
    vi.mocked(client.get).mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce({ items: [] })
    vi.mocked(client.post).mockResolvedValueOnce({ id: 9 })
    const r = await saveAgentSkill({ name: ' 新技能 ', description: ' 当用户 X 时使用 ', content: ' 正文 ', tag: ' 新 ', importMeta: { source_format: 'skill_md' } })
    expect(r).toEqual({ name: '新技能', tag: '新' })
    expect(vi.mocked(client.post)).toHaveBeenCalledWith('/api/presets', expect.objectContaining({
      type: 'skill',
      name: '新技能',
      description: '当用户 X 时使用',
      prompt_text: '正文',
      category: '技能',
      source: 'agent_created',
      prompt_config: { tag: '新', import_meta: { source_format: 'skill_md' } },
    }))
    expect(vi.mocked(client.get)).toHaveBeenCalledTimes(2) // 同名查重 + 保存后刷缓存
  })
})
