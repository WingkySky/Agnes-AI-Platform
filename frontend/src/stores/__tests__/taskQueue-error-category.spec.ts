/* 任务队列错误类目透出单测：
 * - 轮询失败捕获 error_category → task.errorCategory
 * - 提交失败捕获错误对象上的 category
 * - 不可重试类目（合同 canRetry=false）阻断自动重试
 * - 可重试类目照常调度重试，重试执行时清空类目
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mocks = vi.hoisted(() => {
  const storage = new Map<string, unknown>()
  const prefs = { autoRetry: true }
  const nonRetryable = new Set<string>()
  return { storage, prefs, nonRetryable }
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
  useUserStore: () => ({ isAuthenticated: false }),
}))

vi.mock('@/stores/preferences', () => ({
  usePreferencesStore: () => ({
    autoRetry: mocks.prefs.autoRetry,
    autoDownload: vi.fn(),
    notifyComplete: vi.fn(),
  }),
}))

vi.mock('@/stores/models', () => ({
  useModelsStore: () => ({
    canRetryCategory: (category: string) => !mocks.nonRetryable.has(category),
  }),
}))

const createImageTask = vi.fn()
const getImageTaskStatus = vi.fn()
vi.mock('@/api/images', () => ({
  createImageTask: (...args: unknown[]) => createImageTask(...args),
  getImageTaskStatus: (...args: unknown[]) => getImageTaskStatus(...args),
  cancelImageTask: vi.fn(),
}))
vi.mock('@/api/videos', () => ({
  createVideoTask: vi.fn(),
  getVideoStatus: vi.fn(),
  cancelVideoTask: vi.fn(),
}))

import { useTaskQueueStore } from '../taskQueue'

beforeEach(() => {
  setActivePinia(createPinia())
  mocks.storage.clear()
  mocks.prefs.autoRetry = true
  mocks.nonRetryable.clear()
  createImageTask.mockReset()
  getImageTaskStatus.mockReset()
  vi.useFakeTimers()
})

describe('任务队列错误类目（error_category）透出', () => {
  it('轮询失败捕获后端 error_category', async () => {
    createImageTask.mockResolvedValue({ task_id: 'bt1', status: 'processing' })
    getImageTaskStatus.mockResolvedValue({
      status: 'failed',
      message: '内容未通过渠道审核',
      error_category: 'moderation_rejected',
    })
    const store = useTaskQueueStore()
    const taskId = store.submitImageTask({ prompt: 'x' })
    await vi.advanceTimersByTimeAsync(0)

    const task = store.tasks[taskId]
    expect(task.status).toBe('failed')
    expect(task.errorCategory).toBe('moderation_rejected')
    expect(task.errorMessage).toBe('内容未通过渠道审核')
  })

  it('提交失败捕获错误对象上的 category', async () => {
    const err = Object.assign(new Error('渠道余额或额度不足'), { category: 'upstream_quota' })
    createImageTask.mockRejectedValue(err)
    const store = useTaskQueueStore()
    const taskId = store.submitImageTask({ prompt: 'x' })
    await vi.advanceTimersByTimeAsync(0)

    const task = store.tasks[taskId]
    expect(task.status).toBe('failed')
    expect(task.errorCategory).toBe('upstream_quota')
  })

  it('不可重试类目阻断自动重试（不再白烧重试次数）', async () => {
    mocks.nonRetryable.add('upstream_quota')
    createImageTask.mockRejectedValue(
      Object.assign(new Error('ECONNRESET'), { code: 'ECONNRESET', category: 'upstream_quota' }),
    )
    const store = useTaskQueueStore()
    const taskId = store.submitImageTask({ prompt: 'x' })
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(30000)

    const task = store.tasks[taskId]
    expect(task.errorCategory).toBe('upstream_quota')
    expect(task.retryScheduledAt ?? null).toBeNull()
    expect(createImageTask).toHaveBeenCalledTimes(1)
  })

  it('可重试类目照常调度重试，重试执行时清空类目', async () => {
    createImageTask
      .mockRejectedValueOnce(
        Object.assign(new Error('ECONNRESET'), { code: 'ECONNRESET', category: 'rate_limited' }),
      )
      .mockResolvedValue({ task_id: 'bt2', status: 'processing' })
    getImageTaskStatus.mockResolvedValue({ status: 'processing', progress: 10 })
    const store = useTaskQueueStore()
    const taskId = store.submitImageTask({ prompt: 'x' })
    await vi.advanceTimersByTimeAsync(0)

    const task = store.tasks[taskId]
    expect(task.errorCategory).toBe('rate_limited')
    expect(task.retryScheduledAt).not.toBeNull()

    await vi.advanceTimersByTimeAsync(3000)
    expect(createImageTask).toHaveBeenCalledTimes(2)
    expect(task.errorCategory ?? null).toBeNull()
    expect(task.status === 'pending' || task.status === 'processing').toBe(true)
  })
})
