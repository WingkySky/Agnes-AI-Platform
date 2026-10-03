/* 首启初始化 store 单测：mock /api/setup 端点，聚焦 bootstrap/shouldIntercept 判定与本地状态同步 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mocks = vi.hoisted(() => ({
  getBootstrapStatus: vi.fn(),
  bootstrapAdmin: vi.fn(),
  getSetupStatus: vi.fn(),
  completeSetup: vi.fn(),
}))

vi.mock('@/api/setup', () => ({
  getBootstrapStatus: mocks.getBootstrapStatus,
  bootstrapAdmin: mocks.bootstrapAdmin,
  getSetupStatus: mocks.getSetupStatus,
  completeSetup: mocks.completeSetup,
}))

import { useSetupStore } from '../setup'

const base = { provider_pending: false, setup_completed: false }

describe('setup store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  // ---------- isBootstrapPending（免登录引导判定） ----------

  it('实例无管理员 → bootstrap 拦截', async () => {
    mocks.getBootstrapStatus.mockResolvedValue({ admin_exists: false })
    const store = useSetupStore()
    await expect(store.isBootstrapPending()).resolves.toBe(true)
  })

  it('已有管理员 → 不拦截', async () => {
    mocks.getBootstrapStatus.mockResolvedValue({ admin_exists: true })
    const store = useSetupStore()
    await expect(store.isBootstrapPending()).resolves.toBe(false)
  })

  it('bootstrap 状态接口失败 → 不拦截（避免锁死用户）', async () => {
    mocks.getBootstrapStatus.mockRejectedValue(new Error('network down'))
    const store = useSetupStore()
    await expect(store.isBootstrapPending()).resolves.toBe(false)
  })

  it('bootstrap 结果缓存：每会话只拉取一次', async () => {
    mocks.getBootstrapStatus.mockResolvedValue({ admin_exists: false })
    const store = useSetupStore()
    await store.isBootstrapPending()
    await store.isBootstrapPending()
    expect(mocks.getBootstrapStatus).toHaveBeenCalledTimes(1)
  })

  // ---------- shouldIntercept（登录态向导判定） ----------

  it('管理员待配 Provider 且未完成向导 → 拦截', async () => {
    mocks.getSetupStatus.mockResolvedValue({ ...base, provider_pending: true })
    const store = useSetupStore()
    await expect(store.shouldIntercept()).resolves.toBe(true)
  })

  it('待配 Provider 但已完成过向导（此前跳过）→ 不拦截', async () => {
    mocks.getSetupStatus.mockResolvedValue({ provider_pending: true, setup_completed: true })
    const store = useSetupStore()
    await expect(store.shouldIntercept()).resolves.toBe(false)
  })

  it('无任何待办 → 不拦截', async () => {
    mocks.getSetupStatus.mockResolvedValue({ ...base })
    const store = useSetupStore()
    await expect(store.shouldIntercept()).resolves.toBe(false)
  })

  it('状态接口失败 → 不拦截（避免锁死用户）', async () => {
    mocks.getSetupStatus.mockRejectedValue(new Error('network down'))
    const store = useSetupStore()
    await expect(store.shouldIntercept()).resolves.toBe(false)
  })

  it('fetchStatus 缓存：已加载不重复请求', async () => {
    mocks.getSetupStatus.mockResolvedValue({ ...base })
    const store = useSetupStore()
    await store.fetchStatus()
    await store.fetchStatus()
    expect(mocks.getSetupStatus).toHaveBeenCalledTimes(1)
    await store.fetchStatus(true)
    expect(mocks.getSetupStatus).toHaveBeenCalledTimes(2)
  })

  it('markProviderConfigured 同步本地状态', async () => {
    mocks.getSetupStatus.mockResolvedValue({ provider_pending: true, setup_completed: false })
    const store = useSetupStore()
    await store.fetchStatus()
    store.markProviderConfigured()
    expect(store.status?.provider_pending).toBe(false)
  })

  it('complete 调用端点并置位 setup_completed', async () => {
    mocks.getSetupStatus.mockResolvedValue({ ...base, provider_pending: true })
    mocks.completeSetup.mockResolvedValue({ setup_completed: true })
    const store = useSetupStore()
    await store.fetchStatus()
    await store.complete()
    expect(mocks.completeSetup).toHaveBeenCalledTimes(1)
    expect(store.status?.setup_completed).toBe(true)
    await expect(store.shouldIntercept()).resolves.toBe(false)
  })

  it('reset 清空状态与 bootstrap 缓存（登出场景）', async () => {
    mocks.getBootstrapStatus.mockResolvedValue({ admin_exists: false })
    mocks.getSetupStatus.mockResolvedValue({ ...base })
    const store = useSetupStore()
    await store.isBootstrapPending()
    await store.fetchStatus()
    store.reset()
    expect(store.status).toBeNull()
    expect(store.adminExists).toBeNull()
    // 重置后重新拉取
    await store.isBootstrapPending()
    expect(mocks.getBootstrapStatus).toHaveBeenCalledTimes(2)
  })
})
