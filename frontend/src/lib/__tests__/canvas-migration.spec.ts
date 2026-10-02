/* canvas-migration 单测：
 * - 触发条件（anon 跳过 / 云端非空跳过 / 云端不可达跳过）
 * - 迁移流程：blob 素材上传 → URL 替换 → 原 id 创建工作区
 * - 失败隔离：单工作区失败计入 failed，其余继续
 */

import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mockUser = vi.hoisted(() => ({ authed: true }))
const storage = vi.hoisted(() => ({ localData: null as unknown }))
vi.mock('../canvas-storage', () => ({
  isCloudChannel: () => mockUser.authed,
  loadCanvas: async () => storage.localData,
}))

const api = vi.hoisted(() => ({
  listWorkspaces: vi.fn(),
  createWorkspace: vi.fn(),
  uploadCanvasAsset: vi.fn(),
}))
vi.mock('@/api/canvasWorkspace', () => ({
  listWorkspaces: api.listWorkspaces,
  createWorkspace: api.createWorkspace,
  uploadCanvasAsset: api.uploadCanvasAsset,
}))

// 内存版 IndexedDB：blob 可存取（asset store 的动态 import 也会命中此 mock）
const idbData = vi.hoisted(() => new Map<string, unknown>())
vi.mock('localforage', () => ({
  default: {
    createInstance: () => ({
      getItem: async (k: string) => idbData.get(k) ?? null,
      setItem: async (k: string, v: unknown) => { idbData.set(k, v); return v },
    }),
  },
}))

import { migrateLocalToCloudIfNeeded } from '../canvas-migration'
import { useAssetStore } from '@/stores/canvasAsset'

beforeAll(() => {
  setActivePinia(createPinia())
})

beforeEach(() => {
  vi.clearAllMocks()
  idbData.clear()
  storage.localData = null
  mockUser.authed = true
  api.listWorkspaces.mockResolvedValue([])
  api.uploadCanvasAsset.mockImplementation(async (_blob: Blob, name: string) => ({ url: `/uploads/canvas/assets/${name}` }))
  api.createWorkspace.mockResolvedValue({ id: 'x', revision: 1, data: {}, created_at: '', updated_at: '', name: '' })
})

const localWs = (id: string, panels: unknown[]) => ({
  id, name: `画布${id}`, viewport: { x: 0, y: 0, zoom: 1 }, panels, connections: [], groups: [], styleConfig: null,
})

describe('触发条件', () => {
  it('anon 直接跳过', async () => {
    mockUser.authed = false
    const r = await migrateLocalToCloudIfNeeded()
    expect(r.total).toBe(0)
    expect(api.listWorkspaces).not.toHaveBeenCalled()
  })

  it('云端已有数据 → 永不迁移（幂等，防另一设备删除的工作区被旧数据复活）', async () => {
    api.listWorkspaces.mockResolvedValue([{ id: 'existing', name: 'x' }])
    const r = await migrateLocalToCloudIfNeeded()
    expect(r.total).toBe(0)
    expect(api.createWorkspace).not.toHaveBeenCalled()
  })

  it('云端不可达 → 跳过', async () => {
    api.listWorkspaces.mockRejectedValue(new Error('network'))
    const r = await migrateLocalToCloudIfNeeded()
    expect(r.total).toBe(0)
  })

  it('云端为空且本地无数据 → 不触发', async () => {
    const r = await migrateLocalToCloudIfNeeded()
    expect(r.total).toBe(0)
  })
})

describe('迁移流程', () => {
  it('blob 素材上传并替换 URL，工作区以原 id 创建', async () => {
    // 预置本地素材（registerAsset 走内存 IndexedDB；注册期间关登录态避免其触发上云）
    const assetStore = useAssetStore()
    mockUser.authed = false
    const asset = await assetStore.registerAsset({ type: 'image', blob: new Blob(['img'], { type: 'image/png' }), name: '截图' })
    mockUser.authed = true
    expect(asset).not.toBeNull()

    storage.localData = {
      workspaces: [localWs('ws1', [
        { id: 'p1', name: '我的图', content: { assetId: asset!.id, content: 'blob:blob-url' } },
        { id: 'p2', content: { content: 'https://remote/a.png' } }, // 远程 URL 不动
      ])],
    }
    const r = await migrateLocalToCloudIfNeeded()
    expect(r).toEqual({ total: 1, failed: 0 })
    expect(api.uploadCanvasAsset).toHaveBeenCalledTimes(1)
    expect(api.uploadCanvasAsset.mock.calls[0][1]).toContain('.png')
    // createWorkspace 携带原 id 与替换后的远程 URL
    const call = api.createWorkspace.mock.calls[0][0]
    expect(call.id).toBe('ws1')
    expect(call.data.panels[0].content.content).toBe('/uploads/canvas/assets/我的图.png')
    expect(call.data.panels[1].content.content).toBe('https://remote/a.png')
  })

  it('blob 缓存丢失（素材库无此 id）→ 保留原引用不上传', async () => {
    storage.localData = {
      workspaces: [localWs('ws1', [{ id: 'p1', content: { assetId: 'ghost', content: 'blob:gone' } }])],
    }
    const r = await migrateLocalToCloudIfNeeded()
    expect(r.failed).toBe(0)
    expect(api.uploadCanvasAsset).not.toHaveBeenCalled()
    expect(api.createWorkspace).toHaveBeenCalledTimes(1)
  })

  it('单工作区失败跳过继续，计入 failed', async () => {
    storage.localData = { workspaces: [localWs('bad', []), localWs('good', [])] }
    api.createWorkspace.mockImplementation(async (payload: { id: string }) => {
      if (payload.id === 'bad') throw new Error('boom')
      return { id: payload.id, revision: 1, data: {}, created_at: '', updated_at: '', name: '' }
    })
    const r = await migrateLocalToCloudIfNeeded()
    expect(r.total).toBe(2)
    expect(r.failed).toBe(1)
    expect(api.createWorkspace).toHaveBeenCalledTimes(2)
  })
})
