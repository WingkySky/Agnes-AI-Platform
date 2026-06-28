<!-- =====================================================
     模板导入/导出对话框组件 TemplateImportExportDialog
     - 导出 Tab：多选模板 + 可选关联剧本/风格预设，下载 JSON
     - 导入 Tab：上传文件 → 预览冲突 → 选择策略 → 提交导入
     - 支持外部传入 presetTemplateIds，用于"导出单个模板"场景
     ===================================================== -->

<template>
  <el-dialog
    v-model="visible"
    :title="t('workshop.importExport.title')"
    width="720px"
    destroy-on-close
    @closed="onClosed"
  >
    <el-tabs v-model="activeTab">
      <!-- ===== 导出 Tab ===== -->
      <el-tab-pane :label="t('workshop.importExport.exportTab')" name="export">
        <div v-loading="loadingTemplates" class="export-pane">
          <!-- 关联项勾选 -->
          <div class="export-options">
            <el-checkbox v-model="includeScript">
              {{ t('workshop.importExport.includeScript') }}
            </el-checkbox>
            <el-checkbox v-model="includeStyle">
              {{ t('workshop.importExport.includeStyle') }}
            </el-checkbox>
          </div>

          <!-- 模板多选列表 -->
          <div class="export-list-header">
            <el-checkbox
              v-model="exportCheckAll"
              :indeterminate="exportIndeterminate"
              @change="onExportCheckAllChange"
            >
              {{ t('workshop.importExport.selectAll') }}
            </el-checkbox>
            <span class="export-count">
              {{ t('workshop.importExport.selectedCount', { n: selectedExportIds.length }) }}
            </span>
          </div>
          <div class="export-template-list">
            <div v-if="exportableTemplates.length === 0" class="empty-tip">
              {{ t('workshop.importExport.noTemplates') }}
            </div>
            <el-checkbox-group v-else v-model="selectedExportIds">
              <div
                v-for="tpl in exportableTemplates"
                :key="tpl.id"
                class="export-template-item"
              >
                <el-checkbox :value="tpl.id">
                  <div class="tpl-info">
                    <span class="tpl-name">{{ tpl.name }}</span>
                    <el-tag size="small" type="info">{{ tpl.category }}</el-tag>
                    <span class="tpl-key">{{ tpl.key }}</span>
                  </div>
                </el-checkbox>
              </div>
            </el-checkbox-group>
          </div>
        </div>
        <template #footer>
          <el-button @click="visible = false">{{ t('workshop.importExport.cancel') }}</el-button>
          <el-button
            type="primary"
            :loading="exporting"
            :disabled="selectedExportIds.length === 0"
            @click="doExport"
          >
            {{ t('workshop.importExport.exportBtn') }}
          </el-button>
        </template>
      </el-tab-pane>

      <!-- ===== 导入 Tab ===== -->
      <el-tab-pane :label="t('workshop.importExport.importTab')" name="import">
        <div class="import-pane">
          <!-- 文件选择 -->
          <div class="import-file-area">
            <el-button @click="triggerFilePick">
              <el-icon><Upload /></el-icon>
              {{ t('workshop.importExport.chooseFile') }}
            </el-button>
            <span v-if="importFileName" class="file-name">{{ importFileName }}</span>
            <input
              ref="fileInputRef"
              type="file"
              accept=".json"
              style="display: none"
              @change="onFileSelect"
            />
          </div>

          <!-- 预览区域 -->
          <div v-if="previewData" class="import-preview">
            <div class="preview-summary">
              <el-tag type="info" size="small">
                {{ t('workshop.importExport.templatesInFile', { n: previewData.templates.length }) }}
              </el-tag>
              <el-tag v-if="previewData.script_templates.length" type="success" size="small">
                {{ t('workshop.importExport.scriptsInFile', { n: previewData.script_templates.length }) }}
              </el-tag>
              <el-tag v-if="previewData.style_presets.length" type="warning" size="small">
                {{ t('workshop.importExport.stylesInFile', { n: previewData.style_presets.length }) }}
              </el-tag>
            </div>

            <!-- 冲突策略 -->
            <div class="conflict-strategy">
              <span class="strategy-label">{{ t('workshop.importExport.conflictStrategy') }}</span>
              <el-radio-group v-model="conflictStrategy">
                <el-radio value="rename">{{ t('workshop.importExport.strategyRename') }}</el-radio>
                <el-radio value="skip">{{ t('workshop.importExport.strategySkip') }}</el-radio>
                <el-radio value="overwrite">{{ t('workshop.importExport.strategyOverwrite') }}</el-radio>
              </el-radio-group>
            </div>

            <!-- 导入可见性（仅管理员） -->
            <div v-if="userStore.isAdmin" class="import-visibility">
              <span class="strategy-label">{{ t('workshop.importExport.importVisibility') }}</span>
              <el-radio-group v-model="importVisibility">
                <el-radio value="private">{{ t('workshop.importExport.visibilityPrivate') }}</el-radio>
                <el-radio value="public">{{ t('workshop.importExport.visibilityPublic') }}</el-radio>
                <el-radio value="builtin">{{ t('workshop.importExport.visibilityBuiltin') }}</el-radio>
              </el-radio-group>
            </div>

            <!-- 模板预览表 -->
            <el-table :data="previewRows" size="small" border max-height="320">
              <el-table-column prop="name" :label="t('workshop.importExport.colName')" min-width="140" />
              <el-table-column prop="key" :label="t('workshop.importExport.colKey')" min-width="160" />
              <el-table-column prop="category" :label="t('workshop.importExport.colCategory')" width="100" />
              <el-table-column :label="t('workshop.importExport.colStatus')" width="120">
                <template #default="{ row }">
                  <el-tag v-if="row.conflict" type="warning" size="small">
                    {{ t('workshop.importExport.conflictTag') }}
                  </el-tag>
                  <el-tag v-else type="success" size="small">
                    {{ t('workshop.importExport.newTag') }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
        <template #footer>
          <el-button @click="visible = false">{{ t('workshop.importExport.cancel') }}</el-button>
          <el-button
            type="primary"
            :loading="importing"
            :disabled="!previewData || previewData.templates.length === 0"
            @click="doImport"
          >
            {{ t('workshop.importExport.importBtn') }}
          </el-button>
        </template>
      </el-tab-pane>
    </el-tabs>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import client from '@/api/client'
import { useI18n } from '@/i18n'
import { useUserStore } from '@/stores/user'
import type { PipelineTemplate } from '@/types'

const { t } = useI18n()
const userStore = useUserStore()

const props = defineProps<{
  modelValue: boolean
  /** 预设要导出的模板 ID 列表（来自卡片"导出此模板"操作） */
  presetTemplateIds?: number[]
  /** 初始激活的 Tab */
  initialTab?: 'export' | 'import'
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'imported'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const activeTab = ref<'export' | 'import'>(props.initialTab || 'export')

// ===== 导出相关状态 =====
const loadingTemplates = ref(false)
const exporting = ref(false)
const exportableTemplates = ref<PipelineTemplate[]>([])
const selectedExportIds = ref<number[]>([])
const includeScript = ref(true)
const includeStyle = ref(false)

const exportCheckAll = computed({
  get: () =>
    exportableTemplates.value.length > 0 &&
    selectedExportIds.value.length === exportableTemplates.value.length,
  set: (val: boolean) => {
    selectedExportIds.value = val ? exportableTemplates.value.map((x) => x.id) : []
  },
})
const exportIndeterminate = computed(() => {
  const n = selectedExportIds.value.length
  return n > 0 && n < exportableTemplates.value.length
})
function onExportCheckAllChange(val: any) {
  selectedExportIds.value = val
    ? exportableTemplates.value.map((x) => x.id)
    : []
}

// ===== 导入相关状态 =====
const importing = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const importFileName = ref('')
const previewData = ref<any>(null)
const previewRows = ref<any[]>([])
const conflictStrategy = ref<'rename' | 'skip' | 'overwrite'>('rename')
const importVisibility = ref<'private' | 'public' | 'builtin'>('private')

// ===== 弹窗打开时初始化 =====
watch(
  () => props.modelValue,
  async (val) => {
    if (val) {
      activeTab.value = props.initialTab || 'export'
      await loadExportableTemplates()
    }
  },
)

// 外部预选模板 ID 时自动勾选
watch(
  () => props.presetTemplateIds,
  (ids) => {
    if (ids && ids.length > 0) {
      selectedExportIds.value = [...ids]
    }
  },
)

async function loadExportableTemplates() {
  loadingTemplates.value = true
  try {
    // 调用模板列表接口，筛选当前用户的自定义模板
    // 注意：后端 page_size 上限为 100，这里取最大值
    const res = await client.get('/api/pipeline/templates', {
      params: { page: 1, page_size: 100 },
    })
    // 所有可见模板都可导出（内置 + 公开 + 自定义），导出是只读操作不做限制
    const all: PipelineTemplate[] = res.data?.items || []
    exportableTemplates.value = all
    // 应用外部预选
    if (props.presetTemplateIds && props.presetTemplateIds.length > 0) {
      selectedExportIds.value = props.presetTemplateIds.filter((id) =>
        exportableTemplates.value.some((x) => x.id === id),
      )
    } else {
      selectedExportIds.value = []
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || t('workshop.importExport.loadFailed'))
  } finally {
    loadingTemplates.value = false
  }
}

/* ---- 导出 ---- */
async function doExport() {
  if (selectedExportIds.value.length === 0) return
  exporting.value = true
  try {
    const params = {
      template_ids: selectedExportIds.value.join(','),
      include_script: includeScript.value,
      include_style: includeStyle.value,
    }
    const res = await client.get('/api/pipeline/templates/export', { params })

    const jsonStr = JSON.stringify(res.data, null, 2)
    const blob = new Blob([jsonStr], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `agnes-templates-${Date.now()}.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)

    ElMessage.success(t('workshop.importExport.exportSuccess'))
    visible.value = false
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || t('workshop.importExport.exportFailed'))
  } finally {
    exporting.value = false
  }
}

/* ---- 导入 ---- */
function triggerFilePick() {
  fileInputRef.value?.click()
}

async function onFileSelect(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  target.value = ''

  if (!file.name.endsWith('.json')) {
    ElMessage.warning(t('workshop.importExport.invalidJsonFile'))
    return
  }

  importFileName.value = file.name
  try {
    const text = await file.text()
    const parsed = JSON.parse(text)
    if (!parsed || !Array.isArray(parsed.templates)) {
      ElMessage.error(t('workshop.importExport.invalidJson'))
      return
    }
    previewData.value = parsed
    await buildPreviewRows(parsed)
  } catch {
    ElMessage.error(t('workshop.importExport.invalidJson'))
    previewData.value = null
    previewRows.value = []
  }
}

async function buildPreviewRows(data: any) {
  // 检查每个模板的 key 是否已在系统存在（用于显示冲突状态）
  const rows: any[] = []
  for (const tpl of data.templates || []) {
    rows.push({
      key: tpl.key || '',
      name: tpl.name || '',
      category: tpl.category || '',
      conflict: false, // 简化：实际是否冲突由后端策略决定，这里默认显示为"新增"
    })
  }
  // 尝试查询已有模板 key 列表来标记冲突
  try {
    const res = await client.get('/api/pipeline/templates', {
      params: { page: 1, page_size: 100 },
    })
    const existingKeys = new Set<string>(
      (res.data?.items || []).map((x: any) => x.key),
    )
    rows.forEach((r) => {
      r.conflict = existingKeys.has(r.key)
    })
  } catch {
    // 查询失败不影响导入流程
  }
  previewRows.value = rows
}

async function doImport() {
  if (!previewData.value) return
  importing.value = true
  try {
    const res = await client.post('/api/pipeline/templates/import', {
      data: previewData.value,
      conflict_strategy: conflictStrategy.value,
      import_mode: importVisibility.value,
    })
    const r = res.data || {}
    ElMessage.success(
      t('workshop.importExport.importSuccess', {
        imported: r.imported || 0,
        renamed: r.renamed || 0,
        overwritten: r.overwritten || 0,
        skipped: r.skipped || 0,
      }),
    )
    emit('imported')
    visible.value = false
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || t('workshop.importExport.importFailed'))
  } finally {
    importing.value = false
  }
}

function onClosed() {
  // 重置内部状态
  previewData.value = null
  previewRows.value = []
  importFileName.value = ''
  conflictStrategy.value = 'rename'
  importVisibility.value = 'private'
  selectedExportIds.value = []
}
</script>

<style scoped>
.export-pane,
.import-pane {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.export-options {
  display: flex;
  gap: 24px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.export-list-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.export-count {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.export-template-list {
  max-height: 360px;
  overflow-y: auto;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 4px 0;
}

.export-template-item {
  padding: 6px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.export-template-item:last-child {
  border-bottom: none;
}

.tpl-info {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.tpl-name {
  font-weight: 500;
}
.tpl-key {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  font-family: monospace;
}

.empty-tip {
  padding: 24px;
  text-align: center;
  color: var(--el-text-color-secondary);
}

.import-file-area {
  display: flex;
  align-items: center;
  gap: 12px;
}
.file-name {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.import-preview {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.preview-summary {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.conflict-strategy {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}
.strategy-label {
  font-size: 13px;
  color: var(--el-text-color-regular);
}
</style>
