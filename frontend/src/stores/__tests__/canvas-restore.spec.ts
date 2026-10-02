/* 画布工作区数据覆盖（applyWorkspaceData，版本历史还原的落点）单测：
 * - 快照 data 覆盖 panels/connections/groups/viewport/styleConfig
 * - 清空选中与撤销历史（旧历史对新内容无效）
 * - 走 _save 正常保存链路 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
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

vi.mock('@/lib/canvas-migration', () => ({
  migrateLocalToCloudIfNeeded: vi.fn(async () => ({ total: 0, failed: 0 })),
}))

import { useCanvasStore } from '../canvas'

describe('applyWorkspaceData（版本还原）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mocks.storage.clear()
  })

  it('覆盖当前工作区内容并清空选中与历史，viewport 增量合并', () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    const id = store.addPanel({ type: 'text', x: 0, y: 0, width: 340, height: 240, content: {} })
    store.selectedPanelIds = [id]
    store.selectedPanelId = id
    store.history = { past: [{ panels: [], connections: [], groups: [], viewport: store.viewport }], future: [] }

    store.applyWorkspaceData({
      panels: [{ id: 'restored-1', type: 'text', x: 10, y: 20, width: 340, height: 240, content: {} }],
      connections: [],
      groups: [],
      viewport: { zoom: 2 },
      styleConfig: null,
    })

    expect(store.panels.map((p) => p.id)).toEqual(['restored-1'])
    expect(store.selectedPanelIds).toEqual([])
    expect(store.selectedPanelId).toBeNull()
    expect(store.history.past).toEqual([])
    expect(store.history.future).toEqual([])
    expect(store.viewport.zoom).toBe(2)
    // 当前工作区对象同步了快照内容（切走再切回不丢）
    const ws = store.workspaces.find((w) => w.id === store.activeWorkspaceId)
    expect(ws?.panels.map((p) => p.id)).toEqual(['restored-1'])
  })
})
