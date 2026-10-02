/* 画布页远端变更感知（轻轮询）单测：
 * - revision 未变 → 无动作
 * - 有变化且保存队列空闲 → 自动拉取合入（applyWorkspaceData 链路），指示器熄灭
 * - 有变化但队列忙碌 → 只点亮「云端有更新」指示器，不拉取
 * - 手动 pullRemoteWorkspace 在忙碌时同样只点亮并提示 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mocks = vi.hoisted(() => ({
  checkRemoteRevision: vi.fn(),
  isCloudQueueIdle: vi.fn(),
  pullRemoteWorkspaceCloud: vi.fn(),
}))

vi.mock('@/lib/canvas-storage', () => ({
  loadCanvasData: vi.fn(async () => null),
  saveCanvas: vi.fn(),
  switchCanvasUser: vi.fn(() => 'anon'),
  cancelSaveCanvas: vi.fn(),
  isCloudChannel: vi.fn(() => true),
  setCanvasConflictHandler: vi.fn(),
  createWorkspaceCloud: vi.fn(),
  deleteWorkspaceCloud: vi.fn(),
  renameWorkspaceCloud: vi.fn(),
  checkRemoteRevision: mocks.checkRemoteRevision,
  isCloudQueueIdle: mocks.isCloudQueueIdle,
  pullRemoteWorkspaceCloud: mocks.pullRemoteWorkspaceCloud,
}))

vi.mock('localforage', () => ({
  default: {
    createInstance: () => ({
      ready: () => Promise.resolve(),
      getItem: () => Promise.resolve(null),
      setItem: (_key: string, value: unknown) => Promise.resolve(value),
      removeItem: () => Promise.resolve(),
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

// node 测试环境无 DOM：ElMessage 打桩（成功/提示只验证不弹）
vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}))

import { useCanvasStore } from '../canvas'

beforeEach(() => {
  setActivePinia(createPinia())
  mocks.checkRemoteRevision.mockReset().mockResolvedValue({ changed: false, revision: 1 })
  mocks.isCloudQueueIdle.mockReset().mockReturnValue(true)
  mocks.pullRemoteWorkspaceCloud.mockReset().mockResolvedValue(null)
})

describe('画布远端变更轻轮询', () => {
  it('revision 未变：不拉取、不点亮指示器', async () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    await store._checkRemoteUpdate()
    expect(mocks.pullRemoteWorkspaceCloud).not.toHaveBeenCalled()
    expect(store.remoteUpdateAvailable).toBe(false)
  })

  it('有变化且队列空闲：自动拉取合入（panels 被远端内容替换），指示器熄灭', async () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    store.addPanel({ type: 'text', x: 0, y: 0, width: 340, height: 240, content: {} })
    mocks.checkRemoteRevision.mockResolvedValueOnce({ changed: true, revision: 5 })
    mocks.pullRemoteWorkspaceCloud.mockResolvedValueOnce({
      panels: [{ id: 'remote-1', type: 'image', x: 1, y: 2, width: 240, height: 180, content: {} }],
      connections: [],
      groups: [],
      viewport: { x: 0, y: 0, zoom: 1 },
      styleConfig: null,
    })
    await store._checkRemoteUpdate()
    expect(mocks.pullRemoteWorkspaceCloud).toHaveBeenCalledWith(store.activeWorkspaceId)
    expect(store.panels.map((p) => p.id)).toEqual(['remote-1'])
    expect(store.remoteUpdateAvailable).toBe(false)
  })

  it('有变化但队列忙碌：只点亮指示器，不拉取', async () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    mocks.checkRemoteRevision.mockResolvedValueOnce({ changed: true, revision: 5 })
    mocks.isCloudQueueIdle.mockReturnValue(false)
    await store._checkRemoteUpdate()
    expect(mocks.pullRemoteWorkspaceCloud).not.toHaveBeenCalled()
    expect(store.remoteUpdateAvailable).toBe(true)
  })

  it('手动 pullRemoteWorkspace 在队列忙碌时只提示并点亮，不拉取', async () => {
    const store = useCanvasStore()
    store.createWorkspace('测试画布')
    mocks.isCloudQueueIdle.mockReturnValue(false)
    await store.pullRemoteWorkspace()
    expect(mocks.pullRemoteWorkspaceCloud).not.toHaveBeenCalled()
    expect(store.remoteUpdateAvailable).toBe(true)
  })

  it('startRemotePoll/stopRemotePoll：定时器幂等启停', () => {
    const store = useCanvasStore()
    vi.useFakeTimers()
    try {
      store.startRemotePoll()
      const first = store.remotePollTimer
      store.startRemotePoll()
      expect(store.remotePollTimer).toBe(first)
      store.stopRemotePoll()
      expect(store.remotePollTimer).toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })
})
