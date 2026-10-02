/* canvas-storage 双通道单测：
 * - 通道路由（登录走云端 API / anon 走 localforage）
 * - 云端保存队列串行单飞（在途合并终态、逐工作区 PUT）
 * - 404 懒创建（同 id 透传，不再重试 PUT）
 * - 409 冲突 → 冲突处理器收到云端详情 → 按新 revision 续推一次
 * - 云端加载（工作区映射 + 偏好小设置回填 / 云端为空返回 null）
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ---------- 模块 mock（import 被测模块前声明） ----------

const mockUser = vi.hoisted(() => ({ authed: false }))
vi.mock('@/stores/user', () => ({
  useUserStore: () => ({ isAuthenticated: mockUser.authed, userId: mockUser.authed ? 1 : null }),
}))

const api = vi.hoisted(() => ({
  listWorkspaces: vi.fn(),
  getWorkspace: vi.fn(),
  saveWorkspace: vi.fn(),
  createWorkspace: vi.fn(),
  deleteWorkspace: vi.fn(),
}))
vi.mock('@/api/canvasWorkspace', () => ({
  listWorkspaces: api.listWorkspaces,
  getWorkspace: api.getWorkspace,
  saveWorkspace: api.saveWorkspace,
  createWorkspace: api.createWorkspace,
  deleteWorkspace: api.deleteWorkspace,
}))

const prefsApi = vi.hoisted(() => ({ patchPreferences: vi.fn(), getPreferences: vi.fn() }))
vi.mock('@/api/preferences', () => ({
  patchPreferences: prefsApi.patchPreferences,
  getPreferences: prefsApi.getPreferences,
}))

// localforage 在测试环境不可用：内存实现，断言 anon 路径调用
const idb = vi.hoisted(() => ({ setItem: vi.fn(async () => undefined), getItem: vi.fn(async () => null) }))
vi.mock('localforage', () => ({
  default: { createInstance: () => ({ ready: async () => true, getItem: idb.getItem, setItem: idb.setItem }) },
}))

import {
  isCloudChannel, loadCanvasData, saveCanvas, cancelSaveCanvas,
  setCanvasConflictHandler, createWorkspaceCloud, deleteWorkspaceCloud, canvasSaveStatus,
} from '../canvas-storage'

const ws = (id: string, over: Record<string, unknown> = {}) => ({
  id, name: `画布${id}`, created_at: '2026-10-02T00:00:00Z', updated_at: '2026-10-02T00:00:00Z',
  viewport: { x: 0, y: 0, zoom: 1 }, panels: [{ id: `p-${id}` }], connections: [], groups: [],
  styleConfig: null, ...over,
})

beforeEach(() => {
  vi.useFakeTimers()
  mockUser.authed = false
  canvasSaveStatus.saving = false
  canvasSaveStatus.error = false
  canvasSaveStatus.lastSavedAt = null
  vi.clearAllMocks()
})

afterEach(() => {
  cancelSaveCanvas()
  setCanvasConflictHandler(null)
  vi.useRealTimers()
})

describe('通道路由', () => {
  it('未登录走 anon（isCloudChannel=false，saveCanvas 写 localforage 不发请求）', async () => {
    expect(isCloudChannel()).toBe(false)
    saveCanvas({ workspaces: [ws('a')], activeWorkspaceId: 'a' })
    await vi.advanceTimersByTimeAsync(500)
    expect(api.saveWorkspace).not.toHaveBeenCalled()
    expect(idb.setItem).toHaveBeenCalled()
  })

  it('登录态走云端：激活工作区 PUT + 偏好 PATCH', async () => {
    mockUser.authed = true
    api.saveWorkspace.mockResolvedValue({ revision: 2 })
    saveCanvas({ workspaces: [ws('a')], activeWorkspaceId: 'a' })
    await vi.advanceTimersByTimeAsync(500)
    expect(api.saveWorkspace).toHaveBeenCalledWith('a', expect.objectContaining({
      base_revision: 0, name: '画布a',
      data: expect.objectContaining({ panels: [{ id: 'p-a' }] }),
    }))
    expect(prefsApi.patchPreferences).toHaveBeenCalledWith({ ui: expect.objectContaining({
      canvas_active_workspace_id: 'a',
    }) })
  })
})

describe('保存队列串行单飞', () => {
  it('在途期间的多次保存合并为一次（只发终态数据）', async () => {
    mockUser.authed = true
    let resolveFirst!: (v: { revision: number }) => void
    api.saveWorkspace.mockImplementationOnce(() => new Promise((r) => { resolveFirst = r }))
    api.saveWorkspace.mockResolvedValue({ revision: 9 })

    saveCanvas({ workspaces: [ws('a', { panels: [{ id: 'v1' }] })], activeWorkspaceId: 'a' })
    await vi.advanceTimersByTimeAsync(500) // 第一批进入在途
    expect(api.saveWorkspace).toHaveBeenCalledTimes(1)

    // 在途期间再次编辑（终态 v2）+ 又编辑（终态 v3）
    saveCanvas({ workspaces: [ws('a', { panels: [{ id: 'v2' }] })], activeWorkspaceId: 'a' })
    saveCanvas({ workspaces: [ws('a', { panels: [{ id: 'v3' }] })], activeWorkspaceId: 'a' })
    await vi.advanceTimersByTimeAsync(500) // 防抖到期，但前一 PUT 未返回 → 不发新请求
    expect(api.saveWorkspace).toHaveBeenCalledTimes(1)

    resolveFirst({ revision: 2 })
    await vi.advanceTimersByTimeAsync(50)
    // 队列继续：只发一次，且带终态 v3 与最新 base_revision
    expect(api.saveWorkspace).toHaveBeenCalledTimes(2)
    expect(api.saveWorkspace).toHaveBeenLastCalledWith('a', expect.objectContaining({
      base_revision: 2,
      data: expect.objectContaining({ panels: [{ id: 'v3' }] }),
    }))
  })

  it('切换工作区时旧工作区的待存 id 不丢（pendingIds 累积）', async () => {
    mockUser.authed = true
    api.saveWorkspace.mockResolvedValue({ revision: 2 })
    saveCanvas({ workspaces: [ws('a'), ws('b')], activeWorkspaceId: 'a' })
    saveCanvas({ workspaces: [ws('a'), ws('b')], activeWorkspaceId: 'b' })
    await vi.advanceTimersByTimeAsync(500)
    const savedIds = api.saveWorkspace.mock.calls.map((c) => c[0])
    expect(savedIds).toEqual(expect.arrayContaining(['a', 'b']))
  })
})

describe('懒创建与冲突副本', () => {
  it('PUT 404 → 同 id 创建云端工作区（数据随创建写入，不重试 PUT）', async () => {
    mockUser.authed = true
    api.saveWorkspace.mockRejectedValueOnce(Object.assign(new Error('x'), { status: 404 }))
    api.createWorkspace.mockResolvedValue({
      id: 'a', name: '画布a', revision: 1, data: {}, created_at: '', updated_at: '',
    })
    saveCanvas({ workspaces: [ws('a')], activeWorkspaceId: 'a' })
    await vi.advanceTimersByTimeAsync(500)
    expect(api.createWorkspace).toHaveBeenCalledWith(expect.objectContaining({ id: 'a' }))
    expect(api.saveWorkspace).toHaveBeenCalledTimes(1)
  })

  it('PUT 409 → 冲突处理器收到云端详情 → 按云端 revision 续推一次本地内容', async () => {
    mockUser.authed = true
    api.saveWorkspace
      .mockRejectedValueOnce(Object.assign(new Error('conflict'), { status: 409 }))
      .mockResolvedValueOnce({ revision: 7 })
    api.getWorkspace.mockResolvedValue({
      id: 'a', name: '云端名', revision: 6,
      data: { panels: [{ id: 'cloud' }], connections: [], groups: [] },
      created_at: '', updated_at: '',
    })
    const seen: Array<Record<string, unknown>> = []
    setCanvasConflictHandler((cloud) => { seen.push(cloud) })

    saveCanvas({ workspaces: [ws('a')], activeWorkspaceId: 'a' })
    await vi.advanceTimersByTimeAsync(500)
    expect(seen).toHaveLength(1)
    const [first] = seen
    expect(first).toMatchObject({ name: '云端名', revision: 6 })
    // 重试 PUT 携带云端 revision
    expect(api.saveWorkspace).toHaveBeenLastCalledWith('a', expect.objectContaining({ base_revision: 6 }))
    expect(api.saveWorkspace).toHaveBeenCalledTimes(2)
  })

  it('无冲突处理器时 409 直接失败（error 置位，不无限重试）', async () => {
    mockUser.authed = true
    api.saveWorkspace.mockRejectedValue(Object.assign(new Error('conflict'), { status: 409 }))
    saveCanvas({ workspaces: [ws('a')], activeWorkspaceId: 'a' })
    await vi.advanceTimersByTimeAsync(500)
    expect(api.saveWorkspace).toHaveBeenCalledTimes(1)
    expect(canvasSaveStatus.error).toBe(true)
  })
})

describe('云端加载', () => {
  it('工作区映射 + 偏好小设置回填（active/background/showImageInfo）', async () => {
    mockUser.authed = true
    api.listWorkspaces.mockResolvedValue([
      { id: 'a', name: 'A', revision: 3, created_at: '', updated_at: '' },
      { id: 'b', name: 'B', revision: 1, created_at: '', updated_at: '' },
    ])
    api.getWorkspace.mockImplementation(async (id: string) => ({
      id, name: id.toUpperCase(), revision: id === 'a' ? 3 : 1,
      data: { panels: [{ id: `p-${id}` }], connections: [], groups: [], viewport: { x: 1, y: 2, zoom: 3 } },
      created_at: '', updated_at: '',
    }))
    prefsApi.getPreferences.mockResolvedValue({
      preferences: { ui: { canvas_active_workspace_id: 'b', canvas_background_mode: 'blueprint', canvas_show_image_info: true } },
    })

    const data = await loadCanvasData()
    expect(data).not.toBeNull()
    const workspaces = data?.workspaces ?? []
    const [firstWs] = workspaces
    expect(workspaces.map((w) => w.id)).toEqual(['a', 'b'])
    expect(firstWs?.panels).toEqual([{ id: 'p-a' }])
    expect(data?.activeWorkspaceId).toBe('b')
    expect(data!.backgroundMode).toBe('blueprint')
    expect(data!.showImageInfo).toBe(true)
    // 加载过的 revision 记账：后续保存带 base_revision
    api.saveWorkspace.mockResolvedValue({ revision: 4 })
    saveCanvas({ workspaces: [ws('a')], activeWorkspaceId: 'a' })
    await vi.advanceTimersByTimeAsync(500)
    expect(api.saveWorkspace).toHaveBeenCalledWith('a', expect.objectContaining({ base_revision: 3 }))
  })

  it('云端为空返回 null（迁移/回退由调用方决定）', async () => {
    mockUser.authed = true
    api.listWorkspaces.mockResolvedValue([])
    expect(await loadCanvasData()).toBeNull()
  })
})

describe('显式远端动作', () => {
  it('createWorkspaceCloud / deleteWorkspaceCloud 在 anon 下直接跳过', async () => {
    await createWorkspaceCloud(ws('a'))
    await deleteWorkspaceCloud('a')
    expect(api.createWorkspace).not.toHaveBeenCalled()
    expect(api.deleteWorkspace).not.toHaveBeenCalled()
  })
})
