/* fitContent（缩放适配）单测：包围盒缩放居中、zoom 上限 100%、空画布 no-op、折叠分组成员排除 */

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

// node 测试环境无 window：stub 画布视口尺寸（fitContent 以全窗口为画布）
vi.stubGlobal('window', { innerWidth: 1000, innerHeight: 800 })

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('fitContent（缩放适配）', () => {
  it('空画布 no-op', () => {
    const store = useCanvasStore()
    store.viewport = { x: 40, y: 50, zoom: 0.5 }
    store.fitContent()
    expect(store.viewport).toEqual({ x: 40, y: 50, zoom: 0.5 })
  })

  it('包围盒加 60px 内边距后居中，zoom 上限 100%', () => {
    const store = useCanvasStore()
    store.addPanel({ type: 'image', x: 0, y: 0, width: 100, height: 100 })
    store.addPanel({ type: 'image', x: 300, y: 100, width: 100, height: 100 })
    store.fitContent()
    // bbox 0..400 × 0..200，加边距后 520×320：zoom = min(1, 1000/520, 800/320) = 1
    expect(store.viewport.zoom).toBe(1)
    expect(store.viewport.x).toBeCloseTo(1000 / 2 - 200)
    expect(store.viewport.y).toBeCloseTo(800 / 2 - 100)
  })

  it('内容超出画布时缩小适配', () => {
    const store = useCanvasStore()
    store.addPanel({ type: 'image', x: 0, y: 0, width: 2000, height: 100 })
    store.fitContent()
    // bbox 宽 2120（2000 + 2×60）：zoom = 1000/2120
    expect(store.viewport.zoom).toBeCloseTo(1000 / 2120, 5)
  })

  it('折叠分组的隐藏成员不参与适配', () => {
    const store = useCanvasStore()
    store.addPanel({ type: 'image', x: 0, y: 0, width: 100, height: 100 })
    const b = store.addPanel({ type: 'image', x: 5000, y: 5000, width: 100, height: 100 })
    store.createGroup([b], { collapsed: true })
    store.fitContent()
    // 只剩第一个节点参与：zoom = min(1, 1000/220, 800/220) = 1，中心为该节点
    expect(store.viewport.zoom).toBe(1)
    expect(store.viewport.x).toBeCloseTo(1000 / 2 - 50)
    expect(store.viewport.y).toBeCloseTo(800 / 2 - 50)
  })
})
