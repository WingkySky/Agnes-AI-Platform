<!-- =====================================================
  TableNodeContent 批量创作表节点内容（无限画布）
  - N 行 × M 参考图列矩阵生成：每行 = 参考图槽位 + 行提示词 + 开关 + 状态
  - 参考图入槽三个通道：点击选文件 / 拖入图片文件 / 画布节点连线到列（列头圆点句柄）
  - 操作预设（批量换装/创意生图）套用模板与建议列数；全局提示词与行提示词追加拼接
  - 数据全部存画布节点 content（rows 整体替换更新），生成走 lib/canvas-batch-table 编排
  - 样式沿用节点约定：原生控件 + @mousedown.stop + 主题 token（不引入 el-table）
===================================================== -->

<template>
  <div v-if="panel" class="batch-table" :style="{ color: theme.node.text }">
    <!-- 无可用图片模型：空态引导（管理员一键跳模型配置） -->
    <div v-if="modelsStore.loaded && modelsStore.imageModels.length === 0" class="bt-empty" :style="panelStyle">
      <span>{{ t('canvas.batchTable.noModels') }}</span>
      <button
        v-if="userStore.isAdmin" type="button" class="bt-link"
        :style="linkStyle" @mousedown.stop @click.stop="router.push('/admin/models')"
      >
        {{ t('canvas.batchTable.goConfigure') }}
      </button>
    </div>

    <!-- 顶部：模型 / 操作预设 / 生成 -->
    <div class="bt-toolbar">
      <select
        class="bt-select" :value="currentModelId" :style="selectStyle"
        :title="t('canvas.batchTable.modelTitle')" @mousedown.stop @change="onModelChange"
      >
        <option v-for="m in modelsStore.imageModels" :key="m.id" :value="m.id">{{ m.name }}</option>
      </select>
      <select
        class="bt-select" :value="content.preset" :style="selectStyle"
        :title="t('canvas.batchTable.presetTitle')" @mousedown.stop @change="onPresetChange"
      >
        <option value="custom">{{ t('canvas.batchTable.presetCustom') }}</option>
        <option value="try_on">{{ t('canvas.batchTable.presetTryOn') }}</option>
        <option value="creative">{{ t('canvas.batchTable.presetCreative') }}</option>
      </select>
      <button
        type="button" class="bt-generate" :style="generateStyle"
        :disabled="generating || !hasModels" @mousedown.stop @click.stop="onGenerate"
      >
        {{ generating ? t('canvas.batchTable.generating') : t('canvas.batchTable.generate', { count: validCount }) }}
      </button>
    </div>

    <!-- 全局提示词（非空时与行提示词追加拼接） -->
    <textarea
      class="bt-global" rows="2" :value="content.globalPrompt"
      :placeholder="t('canvas.batchTable.globalPromptPlaceholder')" :style="inputStyle"
      @input="onGlobalPrompt" @mousedown.stop @wheel.stop
    />

    <!-- 表头：参考图列（含连线句柄）+ 行提示词 + 操作 -->
    <div class="bt-head" :style="headStyle">
      <div v-for="i in content.refSlots" :key="`h${i}`" class="bt-col-head">
        <span>{{ t('canvas.batchTable.refColumn', { n: i }) }}</span>
        <span
          class="bt-col-handle" :style="handleStyle" :title="t('canvas.batchTable.connectHint')"
          @mousedown.stop.prevent="emit('connect-col', i - 1)"
        />
      </div>
      <div class="bt-col-prompt">{{ t('params.prompt') }}</div>
      <div class="bt-col-ops">{{ t('canvas.batchTable.opsColumn') }}</div>
    </div>

    <!-- 行区 -->
    <div class="bt-rows">
      <div
        v-for="row in rows" :key="row.id"
        class="bt-row" :class="{ 'is-invalid': invalidIds.includes(row.id) }" :style="rowStyle(row)"
      >
        <div
          v-for="i in content.refSlots" :key="`${row.id}c${i}`"
          class="bt-cell" :style="cellStyle(cellAt(row, i - 1))"
          :title="t('canvas.batchTable.cellHint')"
          @click.stop="pickFile(row.id, i - 1)"
          @dragover.stop.prevent @drop.stop.prevent="onDrop($event, row.id, i - 1)"
        >
          <img v-if="cellAt(row, i - 1)" :src="cellUrl(cellAt(row, i - 1))" class="bt-thumb" draggable="false" @dragstart.prevent>
          <span v-else class="bt-cell-plus">+</span>
          <button
            v-if="cellAt(row, i - 1)" type="button" class="bt-cell-clear"
            :title="t('canvas.batchTable.clearCell')" @mousedown.stop @click.stop="setCell(row.id, i - 1, null)"
          >×</button>
        </div>
        <div class="bt-prompt-wrap">
          <input
            class="bt-prompt" :value="row.prompt" :placeholder="t('canvas.batchTable.promptPlaceholder')"
            :style="inputStyle" @input="onRowPrompt(row.id, $event)" @mousedown.stop @wheel.stop
          >
          <button
            type="button" class="bt-prompt-opt" :style="selectStyle"
            :title="t('promptOptimizer.openButton')" @mousedown.stop @click.stop="openOptimize(row)"
          >✦</button>
        </div>
        <div class="bt-ops">
          <input
            type="checkbox" class="bt-switch" :checked="row.enabled" :title="t('canvas.batchTable.enableRow')"
            @mousedown.stop @change="onToggle(row.id, ($event.target as HTMLInputElement).checked)"
          >
          <span class="bt-status" :class="`is-${row.status}`" :title="row.error || ''">{{ statusLabel(row.status) }}</span>
          <button type="button" class="bt-row-del" :title="t('canvas.batchTable.removeRow')" @mousedown.stop @click.stop="removeRow(row.id)">×</button>
        </div>
      </div>
    </div>

    <button type="button" class="bt-add-row" :style="linkStyle" @mousedown.stop @click.stop="addRow">
      + {{ t('canvas.batchTable.addRow') }}
    </button>

    <input ref="fileRef" type="file" accept="image/*" class="bt-file" @change="onFileChosen">

    <!-- 优化提示词弹窗（行提示词回填） -->
    <PromptOptimizeDialog
      v-model:visible="optimizeVisible"
      :initial-prompt="optimizeRowPrompt"
      target="image"
      :model-id="currentModelId"
      @apply="onOptimizeApply"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useI18n } from '@/i18n'
import { useCanvasStore } from '@/stores/canvas'
import { useAssetStore } from '@/stores/canvasAsset'
import { useModelsStore } from '@/stores/models'
import { useUserStore } from '@/stores/user'
import PromptOptimizeDialog from '@/components/PromptOptimizeDialog.vue'
import {
  applyPreset,
  clampRowsToSlots,
  createBatchRow,
  generateBatchTableRows,
  maxSlotsForModel,
  readBatchContent,
  resolveCellUrl,
  validateBatchRows,
  type BatchTableCell,
  type BatchRowStatus,
  type BatchTableRow,
} from '@/lib/canvas-batch-table'

const props = defineProps<{ panelId: string }>()

const emit = defineEmits<{
  (e: 'connect-col', columnIndex: number): void
}>()

const { t } = useI18n()
const router = useRouter()
const store = useCanvasStore()
const assetStore = useAssetStore()
const modelsStore = useModelsStore()
const userStore = useUserStore()

/** 当前节点（节点被删除时为 null，模板 v-if 兜底） */
const panel = computed(() => store.panels.find((p) => p.id === props.panelId) || null)
const theme = computed(() => store.canvasTheme)

/** 表格 content（宽松读取，缺字段兜底） */
const content = computed(() => readBatchContent(panel.value?.content))
const rows = computed(() => content.value.rows)
const hasModels = computed(() => modelsStore.imageModels.length > 0)
const currentModelId = computed(() => content.value.model || modelsStore.defaultImageModel)
const refLimit = computed(() => modelsStore.getModelGenParams(currentModelId.value)?.max_ref_images ?? null)

/** 行校验：不合格行标红拦截（提示词为空 / 参考图超额 / 未选模型） */
const invalidIds = computed(() => validateBatchRows(rows.value, {
  globalPrompt: content.value.globalPrompt,
  hasModel: hasModels.value,
  refLimit: refLimit.value,
}).invalidIds)
const validCount = computed(() => rows.value.length - invalidIds.value.length)
const generating = computed(() => rows.value.some((r) => r.status === 'queued' || r.status === 'running'))

/* ---------- 行/单元格编辑（rows 整体替换写回） ---------- */

function writeRows(next: BatchTableRow[]) {
  if (!panel.value) return
  store.updatePanel(panel.value.id, { content: { rows: next } })
}

function updateRow(rowId: string, patch: Partial<BatchTableRow>) {
  writeRows(rows.value.map((r) => (r.id === rowId ? { ...r, ...patch } : r)))
}

function cellAt(row: BatchTableRow, colIndex: number): BatchTableCell | null {
  return row.refs[colIndex] ?? null
}

function cellUrl(cell: BatchTableCell | null): string {
  return resolveCellUrl(cell)
}

function setCell(rowId: string, colIndex: number, cell: BatchTableCell | null) {
  updateRow(rowId, {
    refs: rows.value.find((r) => r.id === rowId)!.refs.map((c, i) => (i === colIndex ? cell : c)),
    status: 'idle',
    error: undefined,
  })
}

function onRowPrompt(rowId: string, e: Event) {
  updateRow(rowId, { prompt: (e.target as HTMLInputElement).value })
}

function onToggle(rowId: string, checked: boolean) {
  updateRow(rowId, { enabled: checked })
}

function addRow() {
  writeRows([...rows.value, createBatchRow(content.value.refSlots)])
}

function removeRow(rowId: string) {
  writeRows(rows.value.filter((r) => r.id !== rowId))
}

function onGlobalPrompt(e: Event) {
  if (!panel.value) return
  store.updatePanel(panel.value.id, { content: { globalPrompt: (e.target as HTMLTextAreaElement).value } })
}

/* ---------- 模型与预设 ---------- */

function onModelChange(e: Event) {
  if (!panel.value) return
  const modelId = (e.target as HTMLSelectElement).value
  const refSlots = maxSlotsForModel(modelsStore.getModelGenParams(modelId)?.max_ref_images ?? null)
  store.updatePanel(panel.value.id, {
    content: { model: modelId, refSlots, rows: clampRowsToSlots(rows.value, refSlots) },
  })
}

function onPresetChange(e: Event) {
  if (!panel.value) return
  const preset = (e.target as HTMLSelectElement).value as 'custom' | 'try_on' | 'creative'
  const applied = applyPreset(preset)
  if (!applied) {
    store.updatePanel(panel.value.id, { content: { preset } })
    return
  }
  const refSlots = Math.min(applied.refSlots, maxSlotsForModel(refLimit.value))
  store.updatePanel(panel.value.id, {
    content: { preset, refSlots, globalPrompt: applied.globalPrompt, rows: clampRowsToSlots(rows.value, refSlots) },
  })
}

/* ---------- 参考图入槽：文件选择 / 拖入 ---------- */

const fileRef = ref<HTMLInputElement | null>(null)
const pendingCell = ref<{ rowId: string; colIndex: number } | null>(null)

function pickFile(rowId: string, colIndex: number) {
  pendingCell.value = { rowId, colIndex }
  fileRef.value?.click()
}

async function fillFromFile(file: File | undefined | null, target?: { rowId: string; colIndex: number }) {
  const slot = target ?? pendingCell.value
  if (!file || !slot) return
  const asset = await assetStore.registerAsset({ type: 'image', blob: file, name: file.name, prompt: '' })
  if (!asset) {
    ElMessage.error(t('canvas.batchTable.cellFillFailed'))
    return
  }
  setCell(slot.rowId, slot.colIndex, { assetId: asset.id, url: asset.url })
}

function onFileChosen(e: Event) {
  const input = e.target as HTMLInputElement
  void fillFromFile(input.files?.[0])
  input.value = ''
}

function onDrop(e: DragEvent, rowId: string, colIndex: number) {
  void fillFromFile(e.dataTransfer?.files?.[0], { rowId, colIndex })
}

/* ---------- 生成 ---------- */

async function onGenerate() {
  if (!panel.value) return
  const outcome = await generateBatchTableRows(panel.value, store)
  if (outcome.started === 0) {
    ElMessage.warning(t('canvas.batchTable.noValidRows'))
  } else if (outcome.skipped > 0) {
    ElMessage.warning(t('canvas.batchTable.partialSkipped', { started: outcome.started, skipped: outcome.skipped }))
  } else {
    ElMessage.success(t('canvas.batchTable.started', { count: outcome.started }))
  }
}

function statusLabel(status: BatchRowStatus): string {
  return t(`canvas.batchTable.status_${status}`)
}

/* ---------- 行提示词优化 ---------- */

const optimizeVisible = ref(false)
/** 优化目标行 ID：应用时按 ID 回填（行可能被增删，用 ID 而非索引定位） */
let optimizeRowId = ''
const optimizeRowPrompt = computed(() => rows.value.find((r) => r.id === optimizeRowId)?.prompt ?? '')

function openOptimize(row: BatchTableRow) {
  optimizeRowId = row.id
  optimizeVisible.value = true
}

function onOptimizeApply({ positive }: { positive: string; negative: string }) {
  if (optimizeRowId) updateRow(optimizeRowId, { prompt: positive, status: 'idle', error: undefined })
}

/* ---------- 主题样式 ---------- */

const panelStyle = computed(() => ({ background: theme.value.node.panel, borderColor: theme.value.node.stroke }))
const linkStyle = computed(() => ({ color: theme.value.node.activeStroke }))
const headStyle = computed(() => ({ background: theme.value.node.faint, color: theme.value.node.muted }))
const inputStyle = computed(() => ({ borderColor: theme.value.node.stroke, color: theme.value.node.text }))
const selectStyle = computed(() => ({ borderColor: theme.value.node.stroke, color: theme.value.node.text, background: 'transparent' }))
const handleStyle = computed(() => ({ background: theme.value.node.activeStroke }))

const generateStyle = computed(() => {
  if (generating.value) return { background: theme.value.node.faint, color: theme.value.node.muted, borderColor: theme.value.node.stroke }
  return { background: theme.value.node.activeStroke, color: '#fff', borderColor: theme.value.node.activeStroke }
})

function rowStyle(row: BatchTableRow) {
  if (invalidIds.value.includes(row.id)) return { borderColor: '#f56c6c' }
  return { borderColor: 'transparent' }
}

function cellStyle(cell: BatchTableCell | null) {
  if (cell) return { borderColor: theme.value.node.activeStroke }
  return { borderColor: theme.value.node.stroke }
}
</script>

<style scoped>
.batch-table {
  display: flex;
  flex-direction: column;
  gap: 6px;
  height: 100%;
  padding: 8px;
  font-size: 12px;
  box-sizing: border-box;
}

.bt-empty {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border: 1px dashed;
  border-radius: 6px;
}

.bt-link {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  padding: 0;
}

.bt-toolbar {
  display: flex;
  gap: 6px;
  align-items: center;
}

.bt-select {
  flex: 1;
  min-width: 0;
  height: 26px;
  border: 1px solid;
  border-radius: 5px;
  padding: 0 4px;
  font-size: 12px;
  outline: none;
}

.bt-generate {
  height: 26px;
  padding: 0 12px;
  border: 1px solid;
  border-radius: 5px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}

.bt-generate:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.bt-global {
  width: 100%;
  border: 1px solid;
  border-radius: 5px;
  padding: 4px 6px;
  font-size: 12px;
  line-height: 1.4;
  resize: none;
  outline: none;
  box-sizing: border-box;
  background: transparent;
}

.bt-head,
.bt-row {
  display: flex;
  align-items: stretch;
  gap: 4px;
}

.bt-head {
  font-size: 11px;
  padding: 3px 0;
  border-radius: 4px;
}

.bt-col-head {
  width: 56px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
}

.bt-col-handle {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  cursor: crosshair;
  flex: none;
}

.bt-col-prompt {
  flex: 1;
  min-width: 0;
}

.bt-col-ops {
  width: 92px;
  flex: none;
  text-align: center;
}

.bt-rows {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.bt-row {
  border: 1px solid;
  border-radius: 5px;
  padding: 4px;
}

.bt-cell {
  width: 56px;
  flex: none;
  aspect-ratio: 1;
  border: 1px dashed;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  position: relative;
  overflow: hidden;
}

.bt-cell-plus {
  font-size: 16px;
  opacity: 0.5;
}

.bt-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.bt-cell-clear {
  position: absolute;
  top: 0;
  right: 0;
  width: 14px;
  height: 14px;
  line-height: 12px;
  text-align: center;
  font-size: 11px;
  border: none;
  border-radius: 0 0 0 4px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  cursor: pointer;
  padding: 0;
}

.bt-prompt-wrap {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 4px;
}

.bt-prompt {
  flex: 1;
  min-width: 0;
  border: 1px solid;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 12px;
  outline: none;
  background: transparent;
}

.bt-prompt-opt {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  border: 1px solid;
  font-size: 10px;
  line-height: 1;
  background: transparent;
  cursor: pointer;
  flex: none;
}

.bt-ops {
  width: 92px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.bt-switch {
  accent-color: #409eff;
  cursor: pointer;
}

.bt-status {
  font-size: 10px;
  opacity: 0.75;
  max-width: 52px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bt-row-del {
  border: none;
  background: transparent;
  color: inherit;
  opacity: 0.5;
  cursor: pointer;
  font-size: 13px;
  padding: 0 2px;
}

.bt-row-del:hover {
  opacity: 1;
}

.bt-add-row {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  padding: 2px 0;
  text-align: left;
}

.bt-file {
  display: none;
}
</style>
