// 模型备用路由编辑纯函数测试（多渠道路由 failover）
import { describe, expect, it } from 'vitest'
import {
  appendModelRoute,
  buildRouteSavePayload,
  moveModelRoute,
  type EditableModelRoute,
} from '../model-routes'

const base: EditableModelRoute[] = [
  { provider_id: 1, model_id: 'm-a', is_enabled: true },
  { provider_id: 2, model_id: 'm-b', is_enabled: false },
]

describe('moveModelRoute', () => {
  it('上移交换相邻条目', () => {
    const next = moveModelRoute(base, 1, -1)
    expect(next.map((r) => r.model_id)).toEqual(['m-b', 'm-a'])
  })

  it('越界返回原数组（首条上移/末条下移）', () => {
    expect(moveModelRoute(base, 0, -1)).toBe(base)
    expect(moveModelRoute(base, 1, 1)).toBe(base)
  })

  it('不改原数组', () => {
    moveModelRoute(base, 0, 1)
    expect(base.map((r) => r.model_id)).toEqual(['m-a', 'm-b'])
  })
})

describe('appendModelRoute', () => {
  it('追加新条目默认启用', () => {
    const { routes, duplicate } = appendModelRoute(base, 3, ' m-c ')
    expect(duplicate).toBe(false)
    expect(routes).toHaveLength(3)
    expect(routes[2]).toEqual({ provider_id: 3, model_id: 'm-c', is_enabled: true })
    expect(base).toHaveLength(2)
  })

  it('(provider, model) 重复时拒绝并标记 duplicate', () => {
    const { routes, duplicate } = appendModelRoute(base, 2, 'm-b')
    expect(duplicate).toBe(true)
    expect(routes).toBe(base)
  })

  it('同模型不同渠道不算重复', () => {
    const { routes, duplicate } = appendModelRoute(base, 1, 'm-b')
    expect(duplicate).toBe(false)
    expect(routes).toHaveLength(3)
  })

  it('空参数不追加', () => {
    expect(appendModelRoute(base, 0, 'm-x').routes).toBe(base)
    expect(appendModelRoute(base, 2, '  ').routes).toBe(base)
  })
})

describe('buildRouteSavePayload', () => {
  it('列表顺序即 priority，保留启用状态', () => {
    const payload = buildRouteSavePayload(base)
    expect(payload.routes).toEqual([
      { provider_id: 1, model_id: 'm-a', priority: 0, is_enabled: true },
      { provider_id: 2, model_id: 'm-b', priority: 1, is_enabled: false },
    ])
  })
})
