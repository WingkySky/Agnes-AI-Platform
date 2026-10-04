/* 批量创作表纯函数层单测：列数收敛、行校验、提示词拼接、预设套用、
 * 连线填槽、状态回写、content 宽松读取 */

import { describe, it, expect } from 'vitest'

import {
  BATCH_PRESETS,
  MAX_REF_SLOTS,
  applyPreset,
  clampRowsToSlots,
  createBatchContent,
  createBatchRow,
  fillCellFromNode,
  filledRefCount,
  maxSlotsForModel,
  readBatchContent,
  resolveRowPrompt,
  setRowStatus,
  validateBatchRows,
  type BatchTableRow,
} from '@/lib/canvas-batch-table'

function makeRow(overrides: Partial<BatchTableRow> = {}): BatchTableRow {
  return { ...createBatchRow(3), ...overrides }
}

describe('列数收敛（能力合同）', () => {
  it('合同无配置（不限制）用默认 3 列', () => {
    expect(maxSlotsForModel(null)).toBe(3)
    expect(maxSlotsForModel(undefined)).toBe(3)
  })

  it('合同上限收敛到 [1, 6] 区间', () => {
    expect(maxSlotsForModel(1)).toBe(1)
    expect(maxSlotsForModel(4)).toBe(4)
    expect(maxSlotsForModel(6)).toBe(6)
    expect(maxSlotsForModel(8)).toBe(MAX_REF_SLOTS)
    expect(maxSlotsForModel(0)).toBe(3)
  })

  it('createBatchContent 按上限建表：3 行 × 定长 refs', () => {
    const content = createBatchContent(2)
    expect(content.refSlots).toBe(2)
    expect((content.rows as ReturnType<typeof createBatchRow>[]).length).toBe(3)
    for (const row of content.rows as ReturnType<typeof createBatchRow>[]) {
      expect(row.refs.length).toBe(2)
    }
  })
})

describe('行编辑与提示词拼接', () => {
  it('clampRowsToSlots 截断并补齐 refs', () => {
    const row = makeRow({ refs: [{ url: 'a' }, { url: 'b' }, { url: 'c' }] })
    const clamped = clampRowsToSlots([row], 2)
    expect(clamped[0]!.refs.length).toBe(2)
    expect(clamped[0]!.refs[1]).toEqual({ url: 'b' })
    const padded = clampRowsToSlots([row], 5)
    expect(padded[0]!.refs.length).toBe(5)
    expect(padded[0]!.refs[4]).toBeNull()
  })

  it('resolveRowPrompt：全局非空时追加拼接', () => {
    const row = makeRow({ prompt: ' 一件红色外套 ' })
    expect(resolveRowPrompt(row, ' 商业摄影风格 ')).toBe('商业摄影风格\n一件红色外套')
    expect(resolveRowPrompt(row, '')).toBe('一件红色外套')
    expect(resolveRowPrompt(makeRow({ prompt: '' }), '只有全局')).toBe('只有全局')
    expect(resolveRowPrompt(makeRow({ prompt: '' }), '  ')).toBe('')
  })

  it('filledRefCount 只数有内容的槽位', () => {
    const row = makeRow({ refs: [{ url: 'a' }, null, { assetId: 'x' }] })
    expect(filledRefCount(row)).toBe(2)
  })
})

describe('行校验', () => {
  it('启用 + 提示词非空 + 参考图不超额 → 合格', () => {
    const rows = [makeRow({ prompt: 'p', refs: [{ url: 'a' }, null, null] })]
    const { valid, invalidIds } = validateBatchRows(rows, { globalPrompt: '', hasModel: true, refLimit: 2 })
    expect(valid.length).toBe(1)
    expect(invalidIds).toEqual([])
  })

  it('禁用行 / 提示词为空 / 参考图超额 / 无模型 → 不合格', () => {
    const rows = [
      makeRow({ prompt: 'p', enabled: false }),
      makeRow({ prompt: '' }),
      makeRow({ prompt: 'p', refs: [{ url: 'a' }, { url: 'b' }, { url: 'c' }] }),
    ]
    const { valid, invalidIds } = validateBatchRows(rows, { globalPrompt: '', hasModel: true, refLimit: 2 })
    expect(valid.length).toBe(0)
    expect(invalidIds.length).toBe(3)
  })

  it('全局提示词可兜底空行提示词；refLimit 为 null 时不限制参考图', () => {
    const rows = [makeRow({ prompt: '', refs: [{ url: 'a' }, { url: 'b' }, { url: 'c' }] })]
    const withGlobal = validateBatchRows(rows, { globalPrompt: '全局', hasModel: true, refLimit: null })
    expect(withGlobal.valid.length).toBe(1)
    const limited = validateBatchRows(rows, { globalPrompt: '全局', hasModel: true, refLimit: 2 })
    expect(limited.valid.length).toBe(0)
  })
})

describe('操作预设', () => {
  it('try_on=2 列 + 换装模板；creative=3 列 + 创意模板；custom 不变更', () => {
    expect(applyPreset('try_on')).toEqual(BATCH_PRESETS.try_on)
    expect(applyPreset('try_on')!.refSlots).toBe(2)
    expect(applyPreset('creative')!.refSlots).toBe(3)
    expect(applyPreset('custom')).toBeNull()
  })
})

describe('连线填槽', () => {
  it('按列填充自上而下首个空槽', () => {
    const rows = [makeRow({ refs: [{ url: 'a' }, null, null] }), makeRow({ refs: [null, null, null] })]
    const first = fillCellFromNode(rows, 0, { assetId: 'x1', url: 'u1' })
    expect(first!.rowIndex).toBe(1)
    expect(first!.rows[1]!.refs[0]).toEqual({ assetId: 'x1', url: 'u1' })
    expect(rows[0]!.refs[0]).toEqual({ url: 'a' })
    const second = fillCellFromNode(first!.rows, 0, { url: 'u2' })
    expect(second).toBeNull()
  })

  it('非法列索引返回 null', () => {
    expect(fillCellFromNode([makeRow()], -1, { url: 'u' })).toBeNull()
    expect(fillCellFromNode([makeRow()], 9, { url: 'u' })).toBeNull()
  })
})

describe('状态回写', () => {
  it('setRowStatus 只更新目标行；failed 保留错误、其余清空', () => {
    const rows = [makeRow(), makeRow()]
    const next = setRowStatus(rows, rows[1]!.id, 'failed', '上游 400')
    expect(next[0]!.status).toBe('idle')
    expect(next[1]!.status).toBe('failed')
    expect(next[1]!.error).toBe('上游 400')
    const recovered = setRowStatus(next, rows[1]!.id, 'done')
    expect(recovered[1]!.status).toBe('done')
    expect(recovered[1]!.error).toBeUndefined()
  })
})

describe('content 宽松读取', () => {
  it('缺字段 / 非法字段兜底默认值', () => {
    const content = readBatchContent(undefined)
    expect(content.refSlots).toBe(3)
    expect(content.rows).toEqual([])
    expect(content.preset).toBe('custom')
    expect(content.model).toBe('')
    const weird = readBatchContent({ refSlots: 99, rows: 'nope', preset: 'bogus', globalPrompt: 123 })
    expect(weird.refSlots).toBe(MAX_REF_SLOTS)
    expect(weird.rows).toEqual([])
    expect(weird.preset).toBe('custom')
    expect(weird.globalPrompt).toBe('')
  })
})
