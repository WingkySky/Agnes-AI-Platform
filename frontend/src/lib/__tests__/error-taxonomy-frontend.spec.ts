/* 错误类目重试闸门单测：models store canRetryCategory + 批量表行状态带类目 */

import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

import { useModelsStore } from '@/stores/models'
import { setRowStatus, createBatchRow } from '@/lib/canvas-batch-table'
import type { ConfigResponse } from '@/types'

function configWith(categories: Array<{ code: string; can_retry: boolean }>): ConfigResponse {
  return { error_categories: categories } as unknown as ConfigResponse
}

describe('canRetryCategory（重试闸门）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  function loadInto(store: ReturnType<typeof useModelsStore>, resp: ConfigResponse) {
    // 直接走 fetchConfig 的解析路径不现实（会发请求），手动同步语义表
    // （setup store 的 ref 在实例上已解包，直接赋值 Map 即为写入 .value）
    const map = new Map<string, boolean>()
    for (const meta of resp.error_categories || []) map.set(meta.code, meta.can_retry)
    ;(store as unknown as { errorCategories: Map<string, boolean> }).errorCategories = map
  }

  it('无类目（旧数据）默认可重试', () => {
    const store = useModelsStore()
    expect(store.canRetryCategory(undefined)).toBe(true)
    expect(store.canRetryCategory('')).toBe(true)
  })

  it('不可重试类目（submission_uncertain / moderation_rejected）被拦下', () => {
    const store = useModelsStore()
    loadInto(store, configWith([
      { code: 'submission_uncertain', can_retry: false },
      { code: 'moderation_rejected', can_retry: false },
      { code: 'rate_limited', can_retry: true },
    ]))
    expect(store.canRetryCategory('submission_uncertain')).toBe(false)
    expect(store.canRetryCategory('moderation_rejected')).toBe(false)
    expect(store.canRetryCategory('rate_limited')).toBe(true)
  })

  it('未知编码兜底可重试（后端升级前端未跟时的行为不变）', () => {
    const store = useModelsStore()
    loadInto(store, configWith([{ code: 'rate_limited', can_retry: true }]))
    expect(store.canRetryCategory('brand-new-category')).toBe(true)
  })
})

describe('批量表行状态携带错误类目', () => {
  it('failed 保留类目文案与编码，恢复后清空', () => {
    const row = createBatchRow(2)
    const failed = setRowStatus([row], row.id, 'failed', '太快了', 'rate_limited')
    expect(failed[0]!.status).toBe('failed')
    expect(failed[0]!.error).toBe('太快了')
    expect(failed[0]!.errorCategory).toBe('rate_limited')
    const recovered = setRowStatus(failed, row.id, 'queued')
    expect(recovered[0]!.errorCategory).toBeUndefined()
    expect(recovered[0]!.error).toBeUndefined()
  })
})
