<!-- =====================================================
     CanvasManagerPopover — 画布管理弹窗
     - 由左上角标题栏的"管理"按钮触发，以弹窗形式打开
     - 顶部 Tab 切换：画布 / 模板
     - 画布 Tab：列表 + 搜索 + 排序 + 批量删除/导出 + 单项重命名/复制/导出/删除
     - 模板 Tab：预设模板 + 用户自定义模板，点击创建新画布
     ===================================================== -->

<template>
  <el-dialog
    v-model="visible"
    :title="t('canvas.manager.title')"
    width="640px"
    :append-to-body="true"
    :close-on-click-modal="true"
    class="manager-dialog"
  >
    <!-- ============ Tab 切换 ============ -->
    <el-tabs v-model="activeTab" class="manager-tabs">
      <el-tab-pane :label="t('canvas.manager.canvasTab')" name="canvas" />
      <el-tab-pane :label="t('canvas.manager.templateTab')" name="template" />
    </el-tabs>

    <!-- ============ 画布 Tab ============ -->
    <div v-show="activeTab === 'canvas'" class="tab-content">
      <!-- 顶部操作 -->
      <div class="toolbar">
        <el-input
          v-model="searchQuery"
          size="small"
          clearable
          class="search-input"
          :placeholder="t('canvas.manager.searchPlaceholder')"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select
          v-model="sortMode"
          size="small"
          class="sort-select"
          :title="t('canvas.manager.sortLabel')"
        >
          <el-option :label="t('canvas.manager.sortUpdated')" value="updated" />
          <el-option :label="t('canvas.manager.sortCreated')" value="created" />
          <el-option :label="t('canvas.manager.sortName')" value="name" />
        </el-select>
        <el-button size="small" :type="batchMode ? 'primary' : 'default'" @click="toggleBatchMode">
          {{ batchMode ? t('canvas.manager.cancelBatch') : t('canvas.manager.batchMode') }}
        </el-button>
      </div>

      <!-- 批量操作栏 -->
      <div v-if="batchMode" class="batch-bar">
        <el-button size="small" text @click="selectAll">{{ t('canvas.manager.selectAll') }}</el-button>
        <span class="batch-count">{{ t('canvas.manager.selected').replace('{n}', String(selectedIds.size)) }}</span>
        <div class="batch-actions">
          <el-button
            size="small"
            type="danger"
            :disabled="selectedIds.size === 0"
            @click="handleBatchDelete"
          >
            {{ t('canvas.manager.batchDelete') }}
          </el-button>
          <el-button
            size="small"
            :disabled="selectedIds.size === 0"
            @click="handleBatchExport"
          >
            {{ t('canvas.manager.batchExport') }}
          </el-button>
        </div>
      </div>

      <!-- 画布列表 -->
      <div class="list-scroll">
        <div v-if="filteredWorkspaces.length === 0" class="empty-state">
          <p>{{ t('canvas.manager.empty') }}</p>
        </div>
        <div
          v-for="ws in filteredWorkspaces"
          :key="ws.id"
          class="list-item"
          :class="{ active: ws.id === activeWorkspaceId, selected: selectedIds.has(ws.id) }"
          @click="handleItemClick(ws.id)"
        >
          <!-- 批量选择 checkbox -->
          <el-checkbox
            v-if="batchMode"
            v-model="batchCheckboxState[ws.id]"
            size="small"
            class="item-checkbox"
            @change="(val: boolean) => toggleSelect(ws.id, val)"
            @click.stop
          />

          <!-- 画布信息 -->
          <div class="item-info">
            <div class="item-name" :title="ws.name">{{ ws.name }}</div>
            <div class="item-meta">
              <span>{{ t('canvas.manager.nodeCount').replace('{n}', String(ws.panels.length)) }}</span>
              <span>·</span>
              <span>{{ formatTime(ws.updated_at) }}</span>
            </div>
          </div>

          <!-- 单项操作（非批量模式时显示） -->
          <div v-if="!batchMode" class="item-actions" @click.stop>
            <el-tooltip :content="t('canvas.manager.rename')" placement="top">
              <button class="icon-btn-sm" @click="handleRename(ws)">
                <Pencil :size="14" />
              </button>
            </el-tooltip>
            <el-tooltip :content="t('canvas.manager.duplicate')" placement="top">
              <button class="icon-btn-sm" @click="handleDuplicate(ws)">
                <Copy :size="14" />
              </button>
            </el-tooltip>
            <el-tooltip :content="t('canvas.manager.export')" placement="top">
              <button class="icon-btn-sm" @click="handleExport(ws)">
                <Download :size="14" />
              </button>
            </el-tooltip>
            <el-tooltip :content="t('canvas.manager.delete')" placement="top">
              <button class="icon-btn-sm danger" @click="handleDelete(ws)">
                <Trash2 :size="14" />
              </button>
            </el-tooltip>
          </div>
        </div>
      </div>

      <!-- 底部新建按钮 -->
      <div class="footer-actions">
        <el-button type="primary" @click="emit('new-canvas'); visible = false">
          {{ t('canvas.manager.newCanvas') }}
        </el-button>
        <el-button @click="emit('import-json'); visible = false">
          {{ t('canvas.manager.importJson') }}
        </el-button>
      </div>
    </div>

    <!-- ============ 模板 Tab ============ -->
    <div v-show="activeTab === 'template'" class="tab-content">
      <!-- 模板顶部操作 -->
      <div class="toolbar">
        <el-input
          v-model="templateSearch"
          size="small"
          clearable
          class="search-input"
          :placeholder="t('canvas.templates.searchPlaceholder')"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>

      <!-- 分类标签 -->
      <el-tabs v-model="templateCategory" class="template-tabs">
        <el-tab-pane :label="t('canvas.templates.all')" name="all" />
        <el-tab-pane :label="t('canvas.templates.preset')" name="preset" />
        <el-tab-pane :label="t('canvas.templates.user')" name="user" />
      </el-tabs>

      <!-- 模板列表 -->
      <div v-loading="templateLoading" class="list-scroll">
        <div v-if="filteredTemplates.length === 0 && !templateLoading" class="empty-state">
          <p>{{ t('canvas.templates.empty') }}</p>
        </div>
        <div
          v-for="tpl in filteredTemplates"
          :key="tpl.id"
          class="template-item"
          @click="handleUseTemplate(tpl)"
        >
          <div class="template-icon">
            <el-icon :size="22">
              <component :is="getIconComponent(tpl.icon)" />
            </el-icon>
          </div>
          <div class="template-info">
            <div class="template-name-row">
              <span class="template-name">{{ tpl.name }}</span>
              <el-tag v-if="tpl.category === 'preset'" size="small" type="info" effect="plain">
                {{ t('canvas.templates.presetTag') }}
              </el-tag>
              <el-tag v-else size="small" type="success" effect="plain">
                {{ t('canvas.templates.userTag') }}
              </el-tag>
            </div>
            <p class="template-desc">{{ tpl.description || t('canvas.templates.noDesc') }}</p>
            <div class="template-meta">
              <span>{{ tpl.workspace_data.panels.length }} {{ t('canvas.templates.nodes') }}</span>
              <span v-if="tpl.category === 'user' && tpl.updated_at" class="template-time">
                {{ formatTime(tpl.updated_at) }}
              </span>
            </div>
          </div>
          <!-- 用户模板操作 -->
          <div v-if="tpl.category === 'user'" class="item-actions" @click.stop>
            <el-tooltip :content="t('canvas.templates.rename')" placement="top">
              <button class="icon-btn-sm" @click="handleRenameTemplate(tpl)">
                <Pencil :size="14" />
              </button>
            </el-tooltip>
            <el-tooltip :content="t('canvas.templates.delete')" placement="top">
              <button class="icon-btn-sm danger" @click="handleDeleteTemplate(tpl)">
                <Trash2 :size="14" />
              </button>
            </el-tooltip>
          </div>
        </div>
      </div>

      <!-- 底部保存为模板按钮 -->
      <div class="footer-actions">
        <el-button type="primary" @click="emit('save-as-template'); visible = false">
          {{ t('canvas.manager.saveAsTemplate') }}
        </el-button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
/* =====================================================
 * 画布管理弹窗组件
 * - 整合画布列表管理和模板库
 * - 支持批量删除、批量导出、复制、重命名、排序
 * ===================================================== */
import { ref, computed, watch, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import {
  Pencil, Copy, Trash2, Download,
} from 'lucide-vue-next'
// 模板图标映射用的 element-plus 图标
import {
  EditPen as EditPenIcon, Picture, VideoCamera, Connection, ChatDotRound, Document,
} from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useCanvasStore } from '@/stores/canvas'
import {
  type CanvasTemplate,
  getAllTemplates,
  deleteUserTemplate,
  renameUserTemplate,
} from '@/lib/canvas-templates'

const { t } = useI18n()
const store = useCanvasStore()

// ---------- Props & Emits ----------
const props = defineProps<{
  modelValue: boolean
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'new-canvas'): void
  (e: 'import-json'): void
  (e: 'save-as-template'): void
  (e: 'use-template', tpl: CanvasTemplate): void
}>()

// ---------- 双向绑定 visible ----------
const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// ---------- Tab 切换 ----------
const activeTab = ref<'canvas' | 'template'>('canvas')

// ---------- 画布列表 ----------
const searchQuery = ref('')
const sortMode = ref<'updated' | 'created' | 'name'>('updated')
const activeWorkspaceId = computed(() => store.activeWorkspaceId)

/** 排序 + 搜索后的画布列表 */
const filteredWorkspaces = computed(() => {
  let list = [...store.workspaces]
  // 搜索
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter(w => w.name.toLowerCase().includes(q))
  }
  // 排序
  if (sortMode.value === 'updated') {
    list.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
  } else if (sortMode.value === 'created') {
    list.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  } else if (sortMode.value === 'name') {
    list.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'))
  }
  return list
})

// ---------- 批量操作 ----------
const batchMode = ref(false)
const selectedIds = ref<Set<string>>(new Set())
const batchCheckboxState = reactive<Record<string, boolean>>({})

function toggleBatchMode() {
  if (batchMode.value) {
    exitBatchMode()
  } else {
    batchMode.value = true
    selectedIds.value.clear()
    Object.keys(batchCheckboxState).forEach(k => delete batchCheckboxState[k])
  }
}

function exitBatchMode() {
  batchMode.value = false
  selectedIds.value.clear()
  Object.keys(batchCheckboxState).forEach(k => delete batchCheckboxState[k])
}

function toggleSelect(id: string, checked: boolean) {
  if (checked) {
    selectedIds.value.add(id)
  } else {
    selectedIds.value.delete(id)
  }
}

function selectAll() {
  filteredWorkspaces.value.forEach(w => {
    selectedIds.value.add(w.id)
    batchCheckboxState[w.id] = true
  })
}

/** 点击列表项：批量模式下切换选中，否则切换画布并关闭弹窗 */
function handleItemClick(id: string) {
  if (batchMode.value) {
    const next = !selectedIds.value.has(id)
    batchCheckboxState[id] = next
    toggleSelect(id, next)
  } else {
    if (id !== store.activeWorkspaceId) {
      store.switchWorkspace(id)
    }
    visible.value = false
  }
}

// ---------- 单项操作 ----------
async function handleRename(ws: any) {
  try {
    const { value } = await ElMessageBox.prompt(
      t('canvas.manager.renamePrompt'),
      t('canvas.manager.renameTitle'),
      {
        inputValue: ws.name,
        inputPattern: /.+/,
        inputErrorMessage: t('canvas.manager.nameRequired'),
      },
    ) as { value: string }
    store.renameWorkspace(ws.id, value)
    ElMessage.success(t('canvas.messages.canvasRenamed'))
  } catch (_) { /* 取消 */ }
}

function handleDuplicate(ws: any) {
  const newName = `${ws.name} ${t('canvas.messages.copySuffix')}`
  store.duplicateWorkspace(ws.id, newName)
  ElMessage.success(t('canvas.messages.canvasDuplicated'))
}

function handleExport(ws: any) {
  const json = store.exportWorkspaceById(ws.id)
  if (!json) return
  downloadJson(json, `canvas-${ws.name}-${Date.now()}.json`)
  ElMessage.success(t('canvas.messages.jsonExported'))
}

async function handleDelete(ws: any) {
  try {
    await ElMessageBox.confirm(
      t('canvas.manager.confirmDelete').replace('{name}', ws.name),
      t('canvas.manager.deleteTitle'),
      { type: 'warning' },
    )
    store.deleteWorkspace(ws.id)
    ElMessage.success(t('canvas.messages.canvasDeleted'))
  } catch (_) { /* 取消 */ }
}

// ---------- 批量删除/导出 ----------
async function handleBatchDelete() {
  if (selectedIds.value.size === 0) {
    ElMessage.warning(t('canvas.messages.noSelection'))
    return
  }
  const ids = Array.from(selectedIds.value)
  try {
    await ElMessageBox.confirm(
      t('canvas.messages.batchDeleteConfirm').replace('{n}', String(ids.length)),
      { type: 'warning' },
    )
    store.deleteWorkspaces(ids)
    ElMessage.success(t('canvas.messages.batchDeleteDone').replace('{n}', String(ids.length)))
    exitBatchMode()
  } catch (_) { /* 取消 */ }
}

function handleBatchExport() {
  if (selectedIds.value.size === 0) {
    ElMessage.warning(t('canvas.messages.noSelection'))
    return
  }
  const ids = Array.from(selectedIds.value)
  try {
    if (ids.length === 1) {
      const json = store.exportWorkspaceById(ids[0])
      if (json) {
        const ws = store.workspaces.find(w => w.id === ids[0])
        downloadJson(json, `canvas-${ws?.name || 'untitled'}-${Date.now()}.json`)
      }
    } else {
      // 多个：合并成一个 JSON 数组文件
      const allData = ids.map(id => {
        const json = store.exportWorkspaceById(id)
        return json ? JSON.parse(json) : null
      }).filter(Boolean)
      const bundle = JSON.stringify({ version: 1, exportedAt: new Date().toISOString(), canvases: allData }, null, 2)
      downloadJson(bundle, `canvases-batch-${Date.now()}.json`)
    }
    ElMessage.success(t('canvas.messages.batchExportDone').replace('{n}', String(ids.length)))
  } catch (err) {
    console.error('[manager] batch export failed:', err)
    ElMessage.error(t('canvas.messages.batchExportFailed'))
  }
}

function downloadJson(content: string, filename: string) {
  const blob = new Blob([content], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ---------- 模板列表 ----------
const templates = ref<CanvasTemplate[]>([])
const templateLoading = ref(false)
const templateSearch = ref('')
const templateCategory = ref<'all' | 'preset' | 'user'>('all')

async function loadTemplates() {
  templateLoading.value = true
  try {
    templates.value = await getAllTemplates()
  } catch (e) {
    console.error('[manager] load templates failed:', e)
    ElMessage.error(t('canvas.templates.loadFailed'))
  } finally {
    templateLoading.value = false
  }
}

const filteredTemplates = computed(() => {
  let list = templates.value
  if (templateCategory.value !== 'all') {
    list = list.filter(tpl => tpl.category === templateCategory.value)
  }
  const q = templateSearch.value.trim().toLowerCase()
  if (q) {
    list = list.filter(tpl =>
      tpl.name.toLowerCase().includes(q) ||
      (tpl.description || '').toLowerCase().includes(q),
    )
  }
  return list
})

// 弹窗打开时加载模板
watch(visible, (v) => {
  if (v) loadTemplates()
})

/** 使用模板创建画布后关闭弹窗 */
function handleUseTemplate(tpl: CanvasTemplate) {
  emit('use-template', tpl)
  visible.value = false
}

// ---------- 模板操作 ----------
async function handleRenameTemplate(tpl: CanvasTemplate) {
  try {
    const { value } = await ElMessageBox.prompt(
      t('canvas.templates.renamePrompt'),
      t('canvas.templates.renameTitle'),
      {
        inputValue: tpl.name,
        inputPattern: /.+/,
        inputErrorMessage: t('canvas.templates.nameRequired'),
      },
    ) as { value: string }
    const ok = await renameUserTemplate(tpl.id, value)
    if (ok) {
      ElMessage.success(t('canvas.templates.renamed'))
      await loadTemplates()
    }
  } catch (_) { /* 取消 */ }
}

async function handleDeleteTemplate(tpl: CanvasTemplate) {
  try {
    await ElMessageBox.confirm(
      t('canvas.templates.confirmDelete').replace('{name}', tpl.name),
      t('canvas.templates.deleteTitle'),
      { type: 'warning' },
    )
    const ok = await deleteUserTemplate(tpl.id)
    if (ok) {
      ElMessage.success(t('canvas.templates.deleted'))
      await loadTemplates()
    }
  } catch (_) { /* 取消 */ }
}

// ---------- 图标映射 ----------
function getIconComponent(iconName?: string) {
  const map: Record<string, any> = {
    EditPen: EditPenIcon,
    Picture,
    VideoCamera,
    Connection,
    ChatDotRound,
    Document,
  }
  return map[iconName || ''] || Document
}

// ---------- 时间格式化 ----------
function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    const now = new Date()
    const diff = now.getTime() - d.getTime()
    if (diff < 60000) return t('canvas.manager.justNow')
    if (diff < 3600000) return Math.floor(diff / 60000) + t('canvas.manager.minutesAgo')
    if (diff < 86400000) return Math.floor(diff / 3600000) + t('canvas.manager.hoursAgo')
    if (diff < 86400000 * 7) return Math.floor(diff / 86400000) + t('canvas.manager.daysAgo')
    return d.toLocaleDateString()
  } catch {
    return ''
  }
}
</script>

<style scoped>
/* Tab 切换 */
.manager-tabs {
  margin-bottom: 12px;
}
.manager-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

/* Tab 内容区 */
.tab-content {
  display: flex;
  flex-direction: column;
  min-height: 400px;
}

/* 工具栏（搜索 + 排序 + 批量） */
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.search-input {
  flex: 1;
}
.sort-select {
  width: 130px;
  flex-shrink: 0;
}

/* 批量操作栏 */
.batch-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}
.batch-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: auto;
  margin-right: 8px;
}
.batch-actions {
  display: flex;
  gap: 8px;
}

/* 列表滚动区 */
.list-scroll {
  flex: 1;
  overflow-y: auto;
  max-height: 360px;
  min-height: 200px;
  padding: 4px 0;
}

/* 空状态 */
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  text-align: center;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

/* 画布列表项 */
.list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.list-item:hover {
  border-color: var(--el-color-primary);
  background: var(--el-fill-color-light);
}
.list-item.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.list-item.selected {
  border-color: var(--el-color-primary);
}

/* checkbox */
.item-checkbox {
  flex-shrink: 0;
}

/* 画布信息 */
.item-info {
  flex: 1;
  min-width: 0;
}
.item-name {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 2px;
}
.item-meta {
  display: flex;
  gap: 4px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

/* 单项操作按钮组 */
.item-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}
.icon-btn-sm {
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  color: var(--el-text-color-regular);
  transition: background 0.15s;
}
.icon-btn-sm:hover {
  background: var(--el-fill-color);
}
.icon-btn-sm.danger {
  color: var(--el-color-danger);
}

/* 底部操作按钮 */
.footer-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
  margin-top: 12px;
}

/* 模板列表项 */
.template-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.template-item:hover {
  border-color: var(--el-color-primary);
  background: var(--el-fill-color-light);
}
.template-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 6px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  flex-shrink: 0;
}
.template-info {
  flex: 1;
  min-width: 0;
}
.template-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}
.template-name {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.template-desc {
  margin: 0 0 4px 0;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.template-meta {
  display: flex;
  gap: 8px;
  font-size: 10px;
  color: var(--el-text-color-placeholder);
}

/* 模板分类 tabs */
.template-tabs {
  margin-bottom: 8px;
}
.template-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}
</style>
