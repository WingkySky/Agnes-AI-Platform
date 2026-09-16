/* 首启初始化 store 单测：mock /api/setup 端点，聚焦 shouldIntercept 判定与本地状态同步 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mocks = vi.hoisted(() => ({
  getSetupStatus: vi.fn(),
  completeSetup: vi.fn(),
}))

vi.mock('@/api/setup', () => ({
  getSetupStatus: mocks.getSetupStatus,
  completeSetup: mocks.completeSetup,
}))

import { useSetupStore } from '../setup'

const base = { password_pending: false, provider_pending: false, setup_completed: false }

describe('setup store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('仅待改密 → 拦截', async () => {
    mocks.getSetupStatus.mockResolvedValue({ ...base, password_pending: true })
    const store = useSetupStore()
    await expect(store.shouldIntercept()).resolves.toBe(true)
  })

  it('管理员待配 Provider 且未完成向导 → 拦截', async () => {
    mocks.getSetupStatus.mockResolvedValue({ ...base, provider_pending: true })
    const store = useSetupStore()
    await expect(store.shouldIntercept()).resolves.toBe(true)
  })

  it('待配 Provider 但已完成过向导（此前跳过）→ 不拦截', async () => {
    mocks.getSetupStatus.mockResolvedValue({ provider_pending: true, password_pending: false, setup_completed: true })
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

  it('markPasswordChanged / markProviderConfigured 同步本地状态', async () => {
    mocks.getSetupStatus.mockResolvedValue({ password_pending: true, provider_pending: true, setup_completed: false })
    const store = useSetupStore()
    await store.fetchStatus()
    store.markPasswordChanged()
    expect(store.status?.password_pending).toBe(false)
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

  it('reset 清空状态（登出场景）', async () => {
    mocks.getSetupStatus.mockResolvedValue({ ...base })
    const store = useSetupStore()
    await store.fetchStatus()
    store.reset()
    expect(store.status).toBeNull()
  })
})
