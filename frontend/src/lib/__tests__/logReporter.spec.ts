/* =====================================================
 * logReporter 单测：截断 / 批量 flush / 定时 flush / 会话上限
 * 运行于 node 环境：installLogReporter 依赖 DOM 不在此覆盖（由手动冒烟验证）
 * ===================================================== */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reportEvent, __resetForTest } from '../logReporter'

interface FakeInit {
  body?: string
}

const fetchMock = vi.fn(async (_input: unknown, _init?: FakeInit) =>
  new Response('{"status":"success","data":{"received":0}}', { status: 200 }))

beforeEach(() => {
  __resetForTest()
  fetchMock.mockClear()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  __resetForTest()
})

function sentBodies(): Array<Array<Record<string, unknown>>> {
  return fetchMock.mock.calls.map((call) => {
    const init = call[1] as FakeInit
    return JSON.parse(init.body || '{}').events
  })
}

describe('logReporter 错误收集与上报', () => {
  it('满 10 条立即批量上报', async () => {
    for (let i = 0; i < 10; i++) {
      reportEvent({ message: `e${i}` })
    }
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const events = sentBodies()[0]
    expect(events).toHaveLength(10)
    expect(events[0].message).toBe('e0')
  })

  it('不足 10 条时 10 秒定时上报', async () => {
    vi.useFakeTimers()
    reportEvent({ message: 'single' })
    expect(fetchMock).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(sentBodies()[0]).toHaveLength(1)
  })

  it('message / stack 截断到上限', async () => {
    vi.useFakeTimers()
    reportEvent({ message: 'm'.repeat(3000), stack: 's'.repeat(9000) })
    await vi.advanceTimersByTimeAsync(10_000)
    const event = sentBodies()[0][0]
    expect(event.message).toHaveLength(2048)
    expect(event.stack).toHaveLength(8192)
  })

  it('单会话超过 200 条后静默丢弃', async () => {
    for (let i = 0; i < 205; i++) {
      reportEvent({ message: `e${i}` })
    }
    await vi.waitFor(() => {
      const total = sentBodies().reduce((n, events) => n + events.length, 0)
      expect(total).toBe(200)
    })
  })

  it('level 缺省 error，url / timestamp 自动补齐', async () => {
    vi.useFakeTimers()
    reportEvent({ message: 'x' })
    await vi.advanceTimersByTimeAsync(10_000)
    const event = sentBodies()[0][0]
    expect(event.level).toBe('error')
    expect(event.url).toBe('') // node 环境无 window.location
    expect(event.timestamp).toBeTruthy()
  })
})
