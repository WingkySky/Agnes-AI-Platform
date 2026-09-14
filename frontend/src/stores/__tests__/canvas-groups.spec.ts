/* 画布分组（CanvasGroup）store 单测：
 * - 成员制成组/加组/移出/删除节点联动、折叠/锁定、快照撤销、工作区同步与导入导出
 * - 旧流程模式（steps/analyzeFlow）已整体移除，这里守护 store 边界与分镜链路解耦 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createPinia, setActivePinia } from 'pinia'

const mocks = vi.hoisted(() => {
  const storage = new Map<string, unknown>()
  return { storage }
})

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

import { useCanvasStore, CANVAS_GROUP_COLORS } from '../canvas'
import { suggestGroups, detectAssetCategory } from '@/lib/canvas-groups'
import { computeArrangedLayout } from '@/lib/canvas-layout'

/** 整理后坐标：结果表只含移动过的节点，未移动的取原坐标 */
function arrangedPos(store: ReturnType<typeof useCanvasStore>, positions: Record<string, { x: number; y: number }>, id: string) {
  return positions[id] ?? store.panels.find((p) => p.id === id)!
}

/** 建工作区 + n 个文本节点，返回 store */
function setupStore(panelCount = 3) {
  const store = useCanvasStore()
  store.createWorkspace('测试画布')
  const ids: string[] = []
  for (let i = 0; i < panelCount; i++) {
    ids.push(store.addPanel({ type: 'text', x: i * 400, y: 0, width: 340, height: 240, content: {} }))
  }
  return { store, ids }
}

beforeEach(() => {
  setActivePinia(createPinia())
  mocks.storage.clear()
})

describe('分组创建与成员制', () => {
  it('创建分组：默认名/色板循环/成员入选，返回空 skipped', () => {
    const { store, ids } = setupStore(2)
    const { id, skipped } = store.createGroup(ids)
    expect(id).toBeTruthy()
    expect(skipped).toEqual([])
    const group = store.groups.find((g) => g.id === id)
    expect(group?.name).toBe('分组 1')
    expect(group?.color).toBe(CANVAS_GROUP_COLORS[0])
    expect(group?.panel_ids).toEqual(ids)
    expect(group?.collapsed).toBe(false)
    expect(group?.locked).toBe(false)
    // 第二个组：名字序号与色板推进
    const extra = store.addPanel({ type: 'text', x: 0, y: 400, width: 340, height: 240, content: {} })
    const second = store.createGroup([extra])
    expect(store.groups.find((g) => g.id === second.id)?.name).toBe('分组 2')
    expect(store.groups.find((g) => g.id === second.id)?.color).toBe(CANVAS_GROUP_COLORS[1])
  })

  it('已属于其他分组的节点被跳过，不自动换组', () => {
    const { store, ids } = setupStore(3)
    store.createGroup([ids[0], ids[1]])
    const { id, skipped } = store.createGroup([ids[1], ids[2]])
    expect(skipped).toEqual([ids[1]])
    expect(store.groups.find((g) => g.id === id)?.panel_ids).toEqual([ids[2]])
  })

  it('全部节点不可入组时不创建，返回空 id', () => {
    const { store, ids } = setupStore(2)
    store.createGroup(ids)
    const { id } = store.createGroup(ids)
    expect(id).toBe('')
  })

  it('getGroupOfPanel 返回所属分组；未分组为 null', () => {
    const { store, ids } = setupStore(2)
    const { id } = store.createGroup([ids[0]])
    expect(store.getGroupOfPanel(ids[0])?.id).toBe(id)
    expect(store.getGroupOfPanel(ids[1])).toBeNull()
  })

  it('addPanelsToGroup 跳过已分组节点；不存在的节点跳过', () => {
    const { store, ids } = setupStore(3)
    const { id } = store.createGroup([ids[0]])
    const skipped = store.addPanelsToGroup(id, [ids[0], ids[1], 'ghost'])
    expect(skipped).toEqual([ids[0], 'ghost'])
    expect(store.getGroupOfPanel(ids[1])?.id).toBe(id)
  })
})

describe('分组删除与节点联动', () => {
  it('删除节点自动移出分组；组空自动解散，非空保留', () => {
    const { store, ids } = setupStore(3)
    const { id: ga } = store.createGroup([ids[0], ids[1]])
    const { id: gb } = store.createGroup([ids[2]])
    store.deletePanel(ids[2])
    expect(store.groups.some((g) => g.id === gb)).toBe(false)
    store.deletePanel(ids[0])
    expect(store.groups.some((g) => g.id === ga)).toBe(true)
    expect(store.groups.find((g) => g.id === ga)?.panel_ids).toEqual([ids[1]])
  })

  it('removePanelFromGroup 移出节点并解散空组', () => {
    const { store, ids } = setupStore(2)
    const { id } = store.createGroup([ids[0]])
    store.removePanelFromGroup(ids[0])
    expect(store.groups.some((g) => g.id === id)).toBe(false)
    expect(store.getGroupOfPanel(ids[0])).toBeNull()
  })

  it('dissolveGroup 只解散分组，保留节点', () => {
    const { store, ids } = setupStore(2)
    const { id } = store.createGroup(ids)
    store.dissolveGroup(id)
    expect(store.groups).toHaveLength(0)
    expect(store.panels).toHaveLength(2)
  })

  it('clearAllPanels 清空分组', () => {
    const { store, ids } = setupStore(2)
    store.createGroup(ids)
    store.clearAllPanels()
    expect(store.groups).toHaveLength(0)
  })
})

describe('折叠 / 锁定 / 更新', () => {
  it('toggleGroupCollapsed / toggleGroupLocked 翻转状态', () => {
    const { store, ids } = setupStore(1)
    const { id } = store.createGroup(ids)
    store.toggleGroupCollapsed(id)
    store.toggleGroupLocked(id)
    const group = store.groups.find((g) => g.id === id)
    expect(group?.collapsed).toBe(true)
    expect(group?.locked).toBe(true)
    store.toggleGroupLocked(id)
    expect(store.groups.find((g) => g.id === id)?.locked).toBe(false)
  })

  it('updateGroup 修改名称与颜色', () => {
    const { store, ids } = setupStore(1)
    const { id } = store.createGroup(ids)
    store.updateGroup(id, { name: '角色设定', color: '#123456' })
    expect(store.groups.find((g) => g.id === id)?.name).toBe('角色设定')
    expect(store.groups.find((g) => g.id === id)?.color).toBe('#123456')
  })

  it('框选排除折叠分组的隐藏成员', () => {
    const { store, ids } = setupStore(2)
    const { id } = store.createGroup([ids[0]])
    store.toggleGroupCollapsed(id)
    // 框住整个画布区域
    store.selectPanelsInRect({ startWorld: { x: -100, y: -100 }, endWorld: { x: 5000, y: 5000 } })
    expect(store.selectedPanelIds).toEqual([ids[1]])
  })
})

describe('撤销快照 / 工作区同步 / 导入导出', () => {
  it('组操作进快照：createGroup 后 undo 恢复为无分组', () => {
    const { store, ids } = setupStore(2)
    store.createGroup(ids)
    expect(store.groups).toHaveLength(1)
    store.undo()
    expect(store.groups).toHaveLength(0)
    store.redo()
    expect(store.groups).toHaveLength(1)
  })

  it('updateGroup 后 undo 恢复旧名', () => {
    const { store, ids } = setupStore(1)
    const { id } = store.createGroup(ids, { name: 'A' })
    store.updateGroup(id, { name: 'B' })
    store.undo()
    expect(store.groups.find((g) => g.id === id)?.name).toBe('A')
  })

  it('切换工作区再切回，分组随工作区保留', () => {
    const { store, ids } = setupStore(1)
    const wsA = store.activeWorkspaceId!
    const { id } = store.createGroup(ids)
    const wsB = store.createWorkspace('画布 2').id
    expect(store.groups).toHaveLength(0)
    store.switchWorkspace(wsA)
    expect(store.groups.map((g) => g.id)).toEqual([id])
  })

  it('exportJSON/importJSON 往返保留分组；旧 JSON 无 groups 置空', () => {
    const { store, ids } = setupStore(2)
    const { id } = store.createGroup(ids, { name: '链路' })
    const json = store.exportJSON()
    const parsed: { workspace: { groups?: Array<{ id: string }>; panels: unknown[] } } = JSON.parse(json)
    expect(parsed.workspace.groups?.map((g) => g.id)).toEqual([id])

    // 模拟旧版导出：删除 groups 字段
    delete parsed.workspace.groups
    store.importJSON(JSON.stringify(parsed))
    expect(store.groups).toEqual([])
    expect(store.panels).toHaveLength(2)
  })
})

describe('资产类别判定（detectAssetCategory）', () => {
  function makePanel(partial: { type?: string; name?: string; content?: Record<string, unknown>; meta?: Record<string, unknown> }) {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    const id = store.addPanel({
      type: partial.type || 'image',
      name: partial.name,
      x: 0, y: 0, width: 340, height: 240,
      content: partial.content || {},
      meta: partial.meta,
    })
    return store.panels.find((p) => p.id === id)!
  }

  it('类型兜底：脚本/文本→script，视频→video，带派生血缘的图片→storyboard', () => {
    expect(detectAssetCategory(makePanel({ type: 'script' }))).toBe('script')
    expect(detectAssetCategory(makePanel({ type: 'text' }))).toBe('script')
    expect(detectAssetCategory(makePanel({ type: 'video' }))).toBe('video')
    const scriptId = 'script-1'
    expect(detectAssetCategory(makePanel({ type: 'image', content: { lineage: { scriptPanelId: scriptId, kind: 'image' } } }))).toBe('storyboard')
  })

  it('镜头血缘（带 shotId/shotNo）优先于提示词关键词：带人物词的分镜图仍是 storyboard', () => {
    expect(detectAssetCategory(makePanel({ type: 'image', content: { prompt: '男主角特写', lineage: { scriptPanelId: 's1', shotId: 'shot-1', shotNo: 1 } } }))).toBe('storyboard')
    expect(detectAssetCategory(makePanel({ type: 'image', content: { prompt: '男主角特写', lineage: { scriptPanelId: 's1', shotNo: 2 } } }))).toBe('storyboard')
  })

  it('脚本派生的资产设定图按提示词关键词归类：角色设定图→人物、场景设定图→场景、物品设定图→物品', () => {
    expect(detectAssetCategory(makePanel({ type: 'image', content: { prompt: '角色设定图：关羽\n同一角色三视图设定图：正面、侧面、背面全身立绘并排排列', lineage: { scriptPanelId: 's1', kind: 'image' } } }))).toBe('character')
    expect(detectAssetCategory(makePanel({ type: 'image', content: { prompt: '场景设定图：城门\n空场景环境全景，画面中无人物出现', lineage: { scriptPanelId: 's1', kind: 'image' } } }))).toBe('scene')
    expect(detectAssetCategory(makePanel({ type: 'image', content: { prompt: '物品设定图：青龙偃月刀\n物品单体设定图：该物品的清晰特写', lineage: { scriptPanelId: 's1', kind: 'image' } } }))).toBe('prop')
    // 无关键词命中的脚本派生图仍按分镜归档（归档容器依赖此行为）
    expect(detectAssetCategory(makePanel({ type: 'image', content: { prompt: '一朵云', lineage: { scriptPanelId: 's1', kind: 'image' } } }))).toBe('storyboard')
  })

  it('提示词关键词推断：角色→人物、场景→场景、道具→物品，未命中→图片兜底', () => {
    expect(detectAssetCategory(makePanel({ type: 'image', content: { prompt: '女主角特写，长发' } }))).toBe('character')
    expect(detectAssetCategory(makePanel({ type: 'image', content: { prompt: '城市街道背景环境' } }))).toBe('scene')
    expect(detectAssetCategory(makePanel({ type: 'image', content: { prompt: '一把武器道具' } }))).toBe('prop')
    expect(detectAssetCategory(makePanel({ type: 'image', content: { prompt: '一朵云' } }))).toBe('image')
  })

  it('无血缘的镜头图兜底识别：单帧约束提示词或 #镜号 命名 → storyboard（优先于人物关键词）', () => {
    expect(detectAssetCategory(makePanel({ type: 'image', content: { prompt: '关羽单枪匹马冲阵\n单帧画面：只表现该镜头的一个瞬间，电影剧照式单画面构图' } }))).toBe('storyboard')
    expect(detectAssetCategory(makePanel({ type: 'image', name: '#3 三国演义', content: { prompt: '关羽冲阵，人物特写' } }))).toBe('storyboard')
  })

  it('meta.category 手动标记优先于推断', () => {
    expect(detectAssetCategory(makePanel({ type: 'image', content: { prompt: '女主角' }, meta: { category: 'scene' } }))).toBe('scene')
  })
})

describe('分类分组（suggestGroups 模式多选）', () => {
  it('byChain：同一脚本派生的节点 + 脚本本体为一组，返回脚本名', () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    const script = store.addPanel({ type: 'script', x: 0, y: 0, width: 340, height: 300, name: '第一集剧本', content: {} })
    const img1 = store.addPanel({ type: 'image', x: 400, y: 0, width: 340, height: 240, content: { lineage: { scriptPanelId: script, kind: 'image' } } })
    const img2 = store.addPanel({ type: 'image', x: 800, y: 0, width: 340, height: 240, content: { lineage: { scriptPanelId: script, kind: 'image' } } })
    const suggestions = suggestGroups(store.panels, store.groups, { byChain: true, byCategory: false })
    expect(suggestions).toHaveLength(1)
    expect(suggestions[0]!.chainScriptName).toBe('第一集剧本')
    expect([...suggestions[0]!.panelIds].sort()).toEqual([script, img1, img2].sort())
  })

  it('byCategory：按资产类别聚类，每类 ≥2 成组', () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    for (let i = 0; i < 2; i++) store.addPanel({ type: 'image', x: i * 400, y: 0, width: 340, height: 240, content: { prompt: '男主角形象' } })
    for (let i = 0; i < 2; i++) store.addPanel({ type: 'video', x: i * 400, y: 500, width: 420, height: 236, content: {} })
    store.addPanel({ type: 'audio', x: 0, y: 1000, width: 340, height: 120, content: {} })
    const suggestions = suggestGroups(store.panels, store.groups, { byChain: false, byCategory: true })
    const byCategory = new Map(suggestions.map((s) => [s.category, s.panelIds.length]))
    expect(byCategory.get('character')).toBe(2)
    expect(byCategory.get('video')).toBe(2)
    // 单节点类别不成组
    expect(byCategory.has('audio')).toBe(false)
  })

  it('双模式叠加：链条优先占用节点，剩余按资产类别', () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    const script = store.addPanel({ type: 'script', x: 0, y: 0, width: 340, height: 300, name: '剧本A', content: {} })
    const shot = store.addPanel({ type: 'image', x: 400, y: 0, width: 340, height: 240, content: { lineage: { scriptPanelId: script, kind: 'image', shotId: 'shot-1', shotNo: 1 } } })
    // 分镜图带人物提示词，但已属生成链条，不再进人物组
    store.updatePanel(shot, { content: { prompt: '男主角' } })
    for (let i = 0; i < 2; i++) store.addPanel({ type: 'image', x: i * 400, y: 500, width: 340, height: 240, content: { prompt: '男主角形象' } })
    const suggestions = suggestGroups(store.panels, store.groups, { byChain: true, byCategory: true })
    expect(suggestions).toHaveLength(2)
    const chain = suggestions.find((s) => s.chainScriptName)!
    expect(chain.panelIds).toContain(script)
    expect(chain.panelIds).toContain(shot)
    const character = suggestions.find((s) => s.category === 'character')!
    expect(character.panelIds).toHaveLength(2)
    expect(character.panelIds).not.toContain(shot)
  })

  it('已分组节点不参与两种模式', () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    const script = store.addPanel({ type: 'script', x: 0, y: 0, width: 340, height: 300, name: '已分组剧本', content: {} })
    const img = store.addPanel({ type: 'image', x: 400, y: 0, width: 340, height: 240, content: { lineage: { scriptPanelId: script, kind: 'image' } } })
    store.createGroup([script, img])
    expect(suggestGroups(store.panels, store.groups, { byChain: true, byCategory: true })).toEqual([])
  })
})

describe('一键整理布局（产出管线分堆）', () => {
  it('堆按管线序横向排列：脚本→人物→物品→场景→分镜→视频，同类同堆横排', () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    const script = store.addPanel({ type: 'text', x: 8000, y: 0, width: 340, height: 240, content: {} })
    const char1 = store.addPanel({ type: 'image', x: 0, y: 3000, width: 340, height: 240, content: { prompt: '女主角形象' } })
    const char2 = store.addPanel({ type: 'image', x: 400, y: 3300, width: 340, height: 240, content: { prompt: '男主角形象' } })
    const prop = store.addPanel({ type: 'image', x: 0, y: 4000, width: 340, height: 240, content: { prompt: '武器道具' } })
    const scene = store.addPanel({ type: 'image', x: 0, y: 5000, width: 340, height: 240, content: { prompt: '场景背景' } })
    const shot = store.addPanel({ type: 'image', x: 0, y: 6000, width: 340, height: 240, content: { lineage: { scriptPanelId: script, kind: 'image' } } })
    const video = store.addPanel({ type: 'video', x: 0, y: 7000, width: 420, height: 236, content: {} })
    const positions = computeArrangedLayout(store.panels, store.groups, store.connections)
    expect(Object.keys(positions)).toHaveLength(7)
    expect(arrangedPos(store, positions, script).x).toBeLessThan(arrangedPos(store, positions, char1).x)
    expect(arrangedPos(store, positions, char1).x).toBeLessThan(arrangedPos(store, positions, prop).x)
    expect(arrangedPos(store, positions, prop).x).toBeLessThan(arrangedPos(store, positions, scene).x)
    expect(arrangedPos(store, positions, scene).x).toBeLessThan(arrangedPos(store, positions, shot).x)
    expect(arrangedPos(store, positions, shot).x).toBeLessThan(arrangedPos(store, positions, video).x)
    // 同带同行横排
    expect(arrangedPos(store, positions, char2).y).toBe(arrangedPos(store, positions, char1).y)
    expect(arrangedPos(store, positions, char2).x).toBeGreaterThan(arrangedPos(store, positions, char1).x)
  })

  it('分镜行序按上游连线质心排序：来源角色靠前的镜头排上面', () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    const c1 = store.addPanel({ type: 'image', x: 0, y: 0, width: 340, height: 240, content: { prompt: '角色A形象' } })
    const c2 = store.addPanel({ type: 'image', x: 0, y: 400, width: 340, height: 240, content: { prompt: '角色B形象' } })
    const s1 = store.addPanel({ type: 'image', x: 2000, y: 1000, width: 340, height: 240, content: { lineage: { scriptPanelId: 's', kind: 'image' } } })
    const s2 = store.addPanel({ type: 'image', x: 2400, y: 1600, width: 340, height: 240, content: { lineage: { scriptPanelId: 's', kind: 'image' } } })
    // s1 来自下方角色 c2、s2 来自上方角色 c1：行主序下 s2 应排在 s1 之前（同行更靠左，或在更高行）
    store.addConnection({ source_panel_id: c2, target_panel_id: s1, type: 'auto' })
    store.addConnection({ source_panel_id: c1, target_panel_id: s2, type: 'auto' })
    const positions = computeArrangedLayout(store.panels, store.groups, store.connections)
    const p1 = arrangedPos(store, positions, s1)
    const p2 = arrangedPos(store, positions, s2)
    expect(p2.y < p1.y || (p2.y === p1.y && p2.x < p1.x)).toBe(true)
  })

  it('分组作为块搬入所属带，组内相对位移保持', () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    const a1 = store.addPanel({ type: 'text', x: 0, y: 0, width: 340, height: 240, content: {} })
    const a2 = store.addPanel({ type: 'text', x: 400, y: 300, width: 340, height: 240, content: {} })
    const b1 = store.addPanel({ type: 'text', x: 9000, y: 9000, width: 340, height: 240, content: {} })
    const b2 = store.addPanel({ type: 'text', x: 9400, y: 9300, width: 340, height: 240, content: {} })
    store.createGroup([a1, a2])
    store.createGroup([b1, b2])
    const positions = computeArrangedLayout(store.panels, store.groups, store.connections)
    // 首带首块对齐原内容左上角落回原位，无需移动
    expect(positions[a1]).toBeUndefined()
    expect(positions[a2]).toBeUndefined()
    // 第二组搬入同堆（两块并排放进 5 列堆），成员相对位移 (400, 300) 保持
    expect(positions[b1]).toBeTruthy()
    expect(positions[b2]!.x - positions[b1]!.x).toBeCloseTo(400)
    expect(positions[b2]!.y - positions[b1]!.y).toBeCloseTo(300)
    expect(positions[b1]!.x).toBeGreaterThan(0)
  })

  it('分镜账本竖排：读满一列换下一列，列首行对齐', () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    const ids: string[] = []
    for (let i = 0; i < 12; i++) {
      ids.push(store.addPanel({ type: 'image', x: i * 400, y: 5000 + i * 300, width: 340, height: 240, content: { lineage: { scriptPanelId: 's', kind: 'image' } } }))
    }
    const positions = computeArrangedLayout(store.panels, store.groups, store.connections)
    // 前 10 个竖排一列，第 11 个换列且行首对齐
    expect(arrangedPos(store, positions, ids[9]!).y).toBeGreaterThan(arrangedPos(store, positions, ids[0]!).y)
    expect(arrangedPos(store, positions, ids[10]!).x).toBeGreaterThan(arrangedPos(store, positions, ids[0]!).x)
    expect(arrangedPos(store, positions, ids[10]!).y).toBe(arrangedPos(store, positions, ids[0]!).y)
  })

  it('视频统一放分镜右侧视频区，不穿插在分镜账本里', () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    const s1 = store.addPanel({ type: 'image', x: 0, y: 0, width: 340, height: 240, content: { lineage: { scriptPanelId: 's', kind: 'image' } } })
    const v1 = store.addPanel({ type: 'video', x: 5000, y: 5000, width: 420, height: 236, content: {} })
    const s2 = store.addPanel({ type: 'image', x: 400, y: 300, width: 340, height: 240, content: { lineage: { scriptPanelId: 's', kind: 'image' } } })
    const v2 = store.addPanel({ type: 'video', x: 6000, y: 6000, width: 420, height: 236, content: {} })
    store.addConnection({ source_panel_id: s1, target_panel_id: v1, type: 'auto' })
    const positions = computeArrangedLayout(store.panels, store.groups, store.connections)
    // 分镜竖排账本：s2 在 s1 正下方同列
    expect(arrangedPos(store, positions, s2).y).toBeGreaterThan(arrangedPos(store, positions, s1).y)
    expect(arrangedPos(store, positions, s2).x).toBe(arrangedPos(store, positions, s1).x)
    // 两个视频都在账本右侧的视频区同一行并排
    expect(arrangedPos(store, positions, v1).x).toBeGreaterThan(arrangedPos(store, positions, s1).x)
    expect(arrangedPos(store, positions, v2).x).toBeGreaterThan(arrangedPos(store, positions, v1).x)
    expect(arrangedPos(store, positions, v2).y).toBe(arrangedPos(store, positions, v1).y)
  })

  it('重复整理幂等：第二次整理不再移动任何节点', () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    const script = store.addPanel({ type: 'script', x: 0, y: 0, width: 340, height: 300, content: {} })
    store.addPanel({ type: 'image', x: 3000, y: 0, width: 340, height: 240, content: { prompt: '男主角形象' } })
    const scene = store.addPanel({ type: 'image', x: 0, y: 3000, width: 340, height: 240, content: { prompt: '场景背景' } })
    const shot = store.addPanel({ type: 'image', x: 6000, y: 6000, width: 340, height: 240, content: { lineage: { scriptPanelId: script, kind: 'image' } } })
    const video = store.addPanel({ type: 'video', x: 7000, y: 0, width: 420, height: 236, content: {} })
    store.addConnection({ source_panel_id: script, target_panel_id: shot, type: 'auto' })
    store.addConnection({ source_panel_id: scene, target_panel_id: shot, type: 'auto' })
    store.addConnection({ source_panel_id: shot, target_panel_id: video, type: 'auto' })
    const first = computeArrangedLayout(store.panels, store.groups, store.connections)
    store.applyPanelPositions(first)
    expect(computeArrangedLayout(store.panels, store.groups, store.connections)).toEqual({})
  })

  it('异常尺寸节点不污染布局（宽高缺失回退兜底值）', () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    store.addPanel({ type: 'image', x: 0, y: 0, width: 340, height: 240, content: {} })
    const bad = store.addPanel({ type: 'image', x: 100, y: 100, width: undefined as unknown as number, height: NaN, content: {} })
    const positions = computeArrangedLayout(store.panels, store.groups, store.connections)
    expect(Number.isFinite(positions[bad]!.x)).toBe(true)
    expect(Number.isFinite(positions[bad]!.y)).toBe(true)
  })

  it('锁定组与锁定节点不参与整理', () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    const free = store.addPanel({ type: 'image', x: 4000, y: 2000, width: 340, height: 240, content: {} })
    const free2 = store.addPanel({ type: 'image', x: 4500, y: 2600, width: 340, height: 240, content: {} })
    const lockedPanel = store.addPanel({ type: 'image', x: 6000, y: 0, width: 340, height: 240, content: {}, is_locked: true })
    const lockA = store.addPanel({ type: 'text', x: 8000, y: 8000, width: 340, height: 240, content: {} })
    const lockB = store.addPanel({ type: 'text', x: 8400, y: 8300, width: 340, height: 240, content: {} })
    const lockedGroup = store.createGroup([lockA, lockB])
    store.toggleGroupLocked(lockedGroup.id)
    const positions = computeArrangedLayout(store.panels, store.groups, store.connections)
    expect(positions[free2]).toBeTruthy()
    expect(positions[free]).toBeUndefined()
    expect(positions[lockedPanel]).toBeUndefined()
    expect(positions[lockA]).toBeUndefined()
    expect(positions[lockB]).toBeUndefined()
  })
})

describe('旧流程模式移除边界', () => {
  it('store 不再暴露 steps/流程模式状态与动作', () => {
    const { store } = setupStore(1)
    expect('steps' in store.$state).toBe(false)
    expect('isFlowMode' in store.$state).toBe(false)
    expect('addStep' in store).toBe(false)
    expect('toggleFlowMode' in store).toBe(false)
  })

  it('分镜派生链路不再引用 steps/stepId（解耦守护）', () => {
    const source = readFileSync(fileURLToPath(new URL('../../lib/canvas-storyboard.ts', import.meta.url)), 'utf-8')
    expect(source).not.toMatch(/\bstepId\b/)
    expect(source).not.toMatch(/\bstore\.steps\b/)
    expect(source).not.toMatch(/addPanelToStep|ensureShotStep/)
  })
})
