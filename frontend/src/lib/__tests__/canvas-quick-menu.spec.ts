/* 快速创建菜单注册表单测：分组完整性、连线候选过滤（对齐连线类型校验）、
 * 推荐动作规则与 content 预填、搜索过滤与去重 */

import { describe, it, expect, beforeAll, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const storage = new Map<string, unknown>()
  return { storage }
})

// canvas-quick-menu 复用 stores/canvas 的连线类型校验，需隔离 store 模块的持久化依赖
vi.mock('localforage', () => ({
  default: {
    createInstance: () => ({
      ready: () => Promise.resolve(),
      getItem: (key: string) => Promise.resolve(mocks.storage.get(key) ?? null),
      setItem: (key: string, value: unknown) => { mocks.storage.set(key, value); return Promise.resolve(value) },
      removeItem: (key: string) => { mocks.storage.delete(key); return Promise.resolve() },
    }),
  },
}))

vi.mock('@/stores/user', () => ({
  useUserStore: () => null,
}))

vi.mock('@/stores/theme', () => ({
  useThemeStore: () => ({ setMode: () => {} }),
}))

vi.mock('@/lib/canvas-generation', () => ({
  getUpstreamNodesWithIndex: () => [],
}))

vi.mock('@/lib/canvas-migration', () => ({
  migrateLocalToCloudIfNeeded: vi.fn(async () => ({ total: 0, failed: 0 })),
}))

import { setLocale, t } from '@/i18n'
import { validateConnectionTypes } from '@/stores/canvas'
import {
  resolveCreateGroups, resolveConnectMenu, filterQuickMenuGroups,
  type QuickMenuGroup,
} from '../canvas-quick-menu'

// 文案断言固定在中文（测试环境 navigator.language 可能是 en）
beforeAll(() => setLocale('zh-CN'))

const ALL_TYPES = ['config', 'image', 'video', 'audio', 'text', 'script', 'tts', 'subtitle', 'compose'].sort()

const flatTypes = (groups: QuickMenuGroup[]) =>
  groups.flatMap((g) => g.items).filter((i) => i.kind === 'node').map((i) => i.type)

describe('注册表卫生（create 模式）', () => {
  it('收录全部 9 种节点类型且 id 唯一', () => {
    const groups = resolveCreateGroups()
    const items = groups.flatMap((g) => g.items)
    expect(flatTypes(groups).sort()).toEqual(ALL_TYPES)
    expect(new Set(items.map((i) => i.id)).size).toBe(items.length)
  })

  it('分组顺序 AI 生成 → 媒体 → 辅助 → 快捷操作，末组只有上传动作', () => {
    const groups = resolveCreateGroups()
    expect(groups.map((g) => g.key)).toEqual(['ai', 'media', 'assist', 'action'])
    expect(groups.map((g) => t(g.labelKey))).toEqual(['AI 生成', '媒体节点', '辅助节点', '快捷操作'])
    expect(groups[3].items).toHaveLength(1)
    expect(groups[3].items[0].kind).toBe('upload')
  })

  it('config 归 AI 生成组，image/video/audio 归媒体组', () => {
    const groups = resolveCreateGroups()
    expect(groups[0].items.map((i) => i.type)).toEqual(['config'])
    expect(groups[1].items.map((i) => i.type)).toEqual(['image', 'video', 'audio'])
  })

  it('节点项 labelKey 均可翻译（nodeNames 无缺键）', () => {
    for (const item of resolveCreateGroups().flatMap((g) => g.items)) {
      expect(t(item.labelKey)).not.toBe(item.labelKey)
    }
  })
})

describe('connect 模式：右锚出（新节点为接收方）', () => {
  it('text 源：推荐生成图/视频（config 去重），候选全部通过连线校验', () => {
    const m = resolveConnectMenu('text', 'source')
    expect(m.recommendations.map((i) => i.type)).toEqual(['config', 'config'])
    const types = flatTypes(m.groups)
    expect(types).not.toContain('config')
    for (const ty of types) expect(validateConnectionTypes('text', ty!)).toBeNull()
  })

  it('推荐动作预填图/视频生成模式', () => {
    const m = resolveConnectMenu('image', 'source')
    expect(m.recommendations[0].content).toEqual({ mode: 'text2image' })
    expect(m.recommendations[1].content).toEqual({ mode: 'text2video' })
  })

  it('script 源：出边只允许 config，推荐创建生成配置后候选为空', () => {
    const m = resolveConnectMenu('script', 'source')
    expect(m.recommendations.map((i) => i.type)).toEqual(['config'])
    expect(m.groups).toEqual([])
  })
})

describe('connect 模式：左锚入（新节点为上游）', () => {
  it('compose 目标：推荐视频节点，候选只剩配音/字幕', () => {
    const m = resolveConnectMenu('compose', 'target')
    expect(m.recommendations.map((i) => i.type)).toEqual(['video'])
    expect(flatTypes(m.groups).sort()).toEqual(['subtitle', 'tts'])
  })

  it('tts 目标：推荐文本节点，候选为空（text 已被推荐覆盖）', () => {
    const m = resolveConnectMenu('tts', 'target')
    expect(m.recommendations.map((i) => i.type)).toEqual(['text'])
    expect(m.groups).toEqual([])
  })

  it('config 目标：除文本节点外全部类型均可作上游', () => {
    const m = resolveConnectMenu('config', 'target')
    expect(m.recommendations.map((i) => i.type)).toEqual(['text'])
    const types = flatTypes(m.groups)
    expect(types).not.toContain('text')
    expect(types).toHaveLength(8)
    for (const ty of types) expect(validateConnectionTypes(ty!, 'config')).toBeNull()
  })
})

describe('搜索过滤', () => {
  const groups = resolveCreateGroups()

  it('按译文匹配（中文）', () => {
    const hit = filterQuickMenuGroups(groups, '配音')
    expect(flatTypes(hit)).toEqual(['tts'])
  })

  it('按节点类型 id 匹配（不区分大小写）', () => {
    expect(flatTypes(filterQuickMenuGroups(groups, 'IMAGE'))).toEqual(['image'])
  })

  it('空查询原样返回，无命中返回空数组', () => {
    expect(filterQuickMenuGroups(groups, '   ')).toBe(groups)
    expect(filterQuickMenuGroups(groups, '不存在的节点')).toEqual([])
  })
})
