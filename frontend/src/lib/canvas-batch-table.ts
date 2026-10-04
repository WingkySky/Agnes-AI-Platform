/* =====================================================
 * 批量创作表节点（table）纯函数层与生成编排
 *
 * 节点 content 形状：
 *   refSlots     参考图列数上限（列固定命名「参考图 N」）
 *   rows         行数组：每行 = 各列参考图槽位 + 行提示词 + 启用开关 + 行状态
 *   preset       操作预设（批量换装/创意生图/自定义，切换套用模板与建议列数）
 *   globalPrompt 全局提示词（非空时与行提示词追加拼接）
 *   model / size 生图模型与尺寸（与媒体节点 content 字段同名，便于复用参数链）
 *
 * 行结果 = 独立图片节点（复用 createLoadingResultNode + executeInNodeGeneration
 * 的分镜派生模式），连线回表格节点表达血缘；行状态经 onProgress 回写。
 * ===================================================== */

import type { CanvasPanel } from '@/stores/canvas'
import { useAssetStore } from '@/stores/canvasAsset'
import { useModelsStore } from '@/stores/models'
import { createLoadingResultNode, executeInNodeGeneration, type CanvasGenerationStore } from '@/lib/canvas-generation'

/** 参考图列数上下限 */
export const MAX_REF_SLOTS = 6
export const DEFAULT_REF_SLOTS = 3

/** 行状态 */
export type BatchRowStatus = 'idle' | 'queued' | 'running' | 'done' | 'failed'

/** 参考图单元格：assetId 用于跨刷新从素材库还原 URL，url 为直存兜底 */
export interface BatchTableCell {
  assetId?: string
  url?: string
}

/** 批量创作表行 */
export interface BatchTableRow {
  id: string
  refs: Array<BatchTableCell | null>
  prompt: string
  enabled: boolean
  status: BatchRowStatus
  error?: string
  errorCategory?: string
}

/** 操作预设 */
export type BatchTablePreset = 'try_on' | 'creative' | 'custom'

/** 预设模板（面向生成模型的提示词文案，参考图 N = 该行第 N 列资产） */
export const TRY_ON_PROMPT_TEMPLATE =
  '参考图1为人物原图，参考图2为目标服装。保持人物身份、五官、姿态与背景不变，将服装替换为参考图2的款式；准确还原版型、颜色、材质与装饰细节，穿着关系自然，光影与原图保持一致。'
export const CREATIVE_PROMPT_TEMPLATE =
  '基于参考图创作一张新的商业图片，保留主体身份与关键产品细节，构图完整，光影自然。'

/** 预设 → 建议列数 + 全局提示词模板 */
export const BATCH_PRESETS: Record<Exclude<BatchTablePreset, 'custom'>, { refSlots: number; globalPrompt: string }> = {
  try_on: { refSlots: 2, globalPrompt: TRY_ON_PROMPT_TEMPLATE },
  creative: { refSlots: 3, globalPrompt: CREATIVE_PROMPT_TEMPLATE },
}

/** 行 ID（与画布资产 uid 同风格） */
function rowUid(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
}

/** 合同上限 → 列数：min(6, 合同上限)，无配置（不限制）用默认 3 列，最低保 1 */
export function maxSlotsForModel(maxRefImages: number | null | undefined): number {
  if (!maxRefImages || maxRefImages <= 0) return DEFAULT_REF_SLOTS
  return Math.max(1, Math.min(MAX_REF_SLOTS, maxRefImages))
}

/** 新建行：refs 为定长数组（null = 空槽），列序即「参考图 N」 */
export function createBatchRow(refSlots: number): BatchTableRow {
  return { id: rowUid(), refs: new Array(refSlots).fill(null), prompt: '', enabled: true, status: 'idle' }
}

/** 表格节点默认 content（建节点时用；modelLimit 传所选默认模型的合同上限） */
export function createBatchContent(modelLimit?: number | null): Record<string, unknown> {
  const refSlots = maxSlotsForModel(modelLimit)
  return {
    refSlots,
    rows: [createBatchRow(refSlots), createBatchRow(refSlots), createBatchRow(refSlots)],
    preset: 'custom',
    globalPrompt: '',
    model: '',
    size: '',
  }
}

/** 宽松读取表格 content（旧数据/缺字段兜底） */
export function readBatchContent(content: Record<string, unknown> | undefined | null): {
  refSlots: number
  rows: BatchTableRow[]
  preset: BatchTablePreset
  globalPrompt: string
  model: string
  size: string
} {
  const raw = (content ?? {}) as Record<string, unknown>
  const refSlots = typeof raw.refSlots === 'number' && raw.refSlots >= 1 ? Math.min(MAX_REF_SLOTS, Math.floor(raw.refSlots)) : DEFAULT_REF_SLOTS
  const rows = Array.isArray(raw.rows) ? (raw.rows as BatchTableRow[]) : []
  const preset = raw.preset === 'try_on' || raw.preset === 'creative' || raw.preset === 'custom' ? raw.preset : 'custom'
  return {
    refSlots,
    rows,
    preset,
    globalPrompt: typeof raw.globalPrompt === 'string' ? raw.globalPrompt : '',
    model: typeof raw.model === 'string' ? raw.model : '',
    size: typeof raw.size === 'string' ? raw.size : '',
  }
}

/** 切换预设：返回建议列数与全局提示词模板；custom 不变更（返回 null） */
export function applyPreset(preset: BatchTablePreset): { refSlots: number; globalPrompt: string } | null {
  if (preset === 'custom') return null
  return { ...BATCH_PRESETS[preset] }
}

/** 模型/列数变化后收敛各行：refs 截断到 refSlots，不足补空槽 */
export function clampRowsToSlots(rows: BatchTableRow[], refSlots: number): BatchTableRow[] {
  return rows.map((row) => {
    const refs = row.refs.slice(0, refSlots)
    while (refs.length < refSlots) refs.push(null)
    return { ...row, refs }
  })
}

/** 最终提示词：全局非空时「全局 + 行提示词」追加拼接 */
export function resolveRowPrompt(row: BatchTableRow, globalPrompt: string): string {
  const rowPrompt = row.prompt.trim()
  const global = globalPrompt.trim()
  if (global && rowPrompt) return `${global}\n${rowPrompt}`
  return global || rowPrompt
}

/** 行内已填参考图数 */
export function filledRefCount(row: BatchTableRow): number {
  return row.refs.filter((c) => !!(c && (c.assetId || c.url))).length
}

/**
 * 行校验：启用行要求（行提示词或全局提示词非空）且参考图数 ≤ 上限（合同 None=不限制）。
 * 返回合格行与不合格行 ID（供 UI 标红拦截）。
 */
export function validateBatchRows(
  rows: BatchTableRow[],
  opts: { globalPrompt: string; hasModel: boolean; refLimit?: number | null },
): { valid: BatchTableRow[]; invalidIds: string[] } {
  const valid: BatchTableRow[] = []
  const invalidIds: string[] = []
  for (const row of rows) {
    const promptOk = resolveRowPrompt(row, opts.globalPrompt).trim().length > 0
    const refsOk = opts.refLimit == null || filledRefCount(row) <= opts.refLimit
    if (row.enabled && opts.hasModel && promptOk && refsOk) valid.push(row)
    else invalidIds.push(row.id)
  }
  return { valid, invalidIds }
}

/** 连线填槽：按列填充自上而下首个空槽，返回新行数组；无空槽返回 null */
export function fillCellFromNode(
  rows: BatchTableRow[],
  columnIndex: number,
  cell: BatchTableCell,
): { rows: BatchTableRow[]; rowIndex: number } | null {
  if (columnIndex < 0 || columnIndex >= MAX_REF_SLOTS) return null
  for (let r = 0; r < rows.length; r++) {
    const row = rows[r]!
    if (row.refs.length <= columnIndex || row.refs[columnIndex]) continue
    const refs = row.refs.slice()
    refs[columnIndex] = cell
    const next = rows.slice()
    next[r] = { ...row, refs }
    return { rows: next, rowIndex: r }
  }
  return null
}

/** 不可变更新行状态（读-改-写由调用方负责取最新 rows） */
export function setRowStatus(rows: BatchTableRow[], rowId: string, status: BatchRowStatus, error?: string, errorCategory?: string): BatchTableRow[] {
  return rows.map((row) => (row.id === rowId
    ? { ...row, status, error: status === 'failed' ? (error || row.error || '') : undefined, errorCategory: status === 'failed' ? (errorCategory || row.errorCategory) : undefined }
    : row))
}

/** 单元格 → 可用 URL（素材库优先还原，直存 URL 兜底） */
export function resolveCellUrl(cell: BatchTableCell | null): string {
  if (!cell) return ''
  if (cell.assetId) {
    const asset = useAssetStore().getAssetById(cell.assetId)
    if (asset?.url) return asset.url
  }
  return cell.url || ''
}

/**
 * 批量生成：合格启用行逐行派生图片节点（右侧纵向排布）并连线回表格，行状态经 onProgress 回写。
 * 单行失败不影响其他行；返回 { started, skipped }。
 * - 默认只提交 idle/failed 的启用行（生成中/已完成行不重复提交）；
 * - opts.rowIds 指定时只提交这些行（行级重试，仍需通过校验与重试闸门）。
 */
export async function generateBatchTableRows(
  tablePanel: CanvasPanel,
  store: CanvasGenerationStore,
  opts: { rowIds?: string[] } = {},
): Promise<{ started: number; skipped: number }> {
  const content = readBatchContent(tablePanel.content)
  const modelsStore = useModelsStore()
  const modelId = content.model || modelsStore.defaultImageModel
  const refLimit = modelsStore.getModelGenParams(modelId)?.max_ref_images ?? null
  const { valid } = validateBatchRows(content.rows, {
    globalPrompt: content.globalPrompt,
    hasModel: !!modelId,
    refLimit,
  })
  const rowIdSet = opts.rowIds ? new Set(opts.rowIds) : null
  const eligible = valid.filter((row) => {
    if (rowIdSet) return rowIdSet.has(row.id)
    return row.status === 'idle' || row.status === 'failed'
  })
  const skipped = content.rows.length - eligible.length
  if (eligible.length === 0) {
    return { started: 0, skipped }
  }

  /** 读-改-写当前行状态（避免覆盖生成期间用户的行编辑） */
  const writeStatus = (rowId: string, status: BatchRowStatus, error?: string, errorCategory?: string) => {
    const panel = store.panels.find((p) => p.id === tablePanel.id)
    if (!panel) return
    const current = readBatchContent(panel.content).rows
    store.updatePanel(tablePanel.id, { content: { rows: setRowStatus(current, rowId, status, error, errorCategory) } })
  }

  let started = 0
  for (const row of eligible) {
    const prompt = resolveRowPrompt(row, content.globalPrompt)
    const referenceImages = row.refs.map(resolveCellUrl).filter(Boolean)
    // index 传 4 的倍数让结果节点在第 0 列纵向堆叠（calcResultNodePosition 为 4 列网格）
    const newNodeId = createLoadingResultNode(store, tablePanel, false, started * 4, {
      prompt,
      model: modelId,
      size: content.size,
      referenceImages,
      status: 'loading',
    })
    const rowPanel = store.panels.find((p) => p.id === newNodeId)
    if (!rowPanel) continue
    started++
    writeStatus(row.id, 'queued')
    void executeInNodeGeneration(rowPanel, store, {
      onProgress: (phase, data) => {
        if (phase === 'creating') writeStatus(row.id, 'queued')
        else if (phase === 'polling' || phase === 'generating') writeStatus(row.id, 'running')
        else if (phase === 'done') writeStatus(row.id, 'done')
        else if (phase === 'error') writeStatus(row.id, 'failed', String(data?.error || ''), String(data?.category || ''))
      },
    }).catch(() => writeStatus(row.id, 'failed'))
  }
  return { started, skipped }
}
