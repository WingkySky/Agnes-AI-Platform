<!-- =====================================================
     右侧属性面板（任务 4：图层面板成熟化 + 提示词/素材库 Drawer；
                   任务 2：助手面板 CanvasAssistantPanel）
     - 六个 Tab：属性 / 图层 / 备注 / 助手 / 提示词库 / 素材库
     - 前四个 Tab 显示对应面板内容
     - 提示词库 / 素材库 Tab 只作为 Drawer 的开关入口，Tab 头本身无内容
     - 选中面板时显示可编辑属性
     - 未选中或选中连线时显示对应提示
     - 支持编辑：名称、备注、颜色标签、关联任务 ID
     - 实时更新（store.updatePanel 不入历史栈单独走 _updatePanelDirect）
     ===================================================== -->

<template>
  <aside class="canvas-right-panel" :class="{ collapsed }">
    <div class="right-panel-header">
      <h3>{{ t('canvas.propertiesTitle') }}</h3>
      <el-icon class="collapse-btn" @click="collapsed = !collapsed">
        <ArrowRight v-if="!collapsed" />
        <ArrowLeft v-else />
      </el-icon>
    </div>

    <div v-show="!collapsed" class="right-panel-body">
      <el-tabs v-model="activeTab" class="canvas-right-tabs">
        <!-- Tab 1：属性（原选中对象详情） -->
        <el-tab-pane :label="t('canvas.properties')" name="props">
          <!-- 选中面板 -->
          <template v-if="selectedPanel">
            <div class="form-section">
              <label class="form-label">{{ t('canvas.propertiesName') }}</label>
              <el-input
                v-model="formState.name"
                size="small"
                :placeholder="t('canvas.propertiesNamePlaceholder')"
                @blur="commitField('name')"
                @keydown.enter="commitField('name')"
              />
            </div>

            <div class="form-section">
              <label class="form-label">{{ t('canvas.propertiesNote') }}</label>
              <el-input
                v-model="formState.note"
                type="textarea"
                :rows="3"
                :placeholder="t('canvas.propertiesNotePlaceholder')"
                @blur="commitField('note')"
              />
            </div>

            <div class="form-section">
              <label class="form-label">{{ t('canvas.propertiesColor') }}</label>
              <div class="color-picker">
                <div
                  v-for="opt in colorOptions"
                  :key="opt.value"
                  class="color-dot"
                  :class="{ active: formState.color === opt.value }"
                  :style="{ background: opt.color }"
                  :title="opt.label"
                  @click="setColor(opt.value)"
                />
              </div>
            </div>

            <div class="form-section">
              <label class="form-label">{{ t('canvas.propertiesPosition') }}</label>
              <div class="info-row">
                <el-input-number
                  v-model="formState.x"
                  :step="1"
                  size="small"
                  controls-position="right"
                  @change="commitField('x')"
                />
                <el-input-number
                  v-model="formState.y"
                  :step="1"
                  size="small"
                  controls-position="right"
                  @change="commitField('y')"
                />
              </div>
            </div>

            <div class="form-section">
              <label class="form-label">{{ t('canvas.propertiesSize') }}</label>
              <div class="info-row">
                <el-input-number
                  v-model="formState.width"
                  :min="150"
                  :step="10"
                  size="small"
                  controls-position="right"
                  @change="commitField('width')"
                />
                <el-input-number
                  v-model="formState.height"
                  :min="100"
                  :step="10"
                  size="small"
                  controls-position="right"
                  @change="commitField('height')"
                />
              </div>
            </div>

            <div class="form-section">
              <label class="form-label">{{ t('canvas.propertiesTaskId') }}</label>
              <el-input
                v-model="formState.taskId"
                size="small"
                :placeholder="t('canvas.propertiesTaskIdPlaceholder')"
                @blur="commitField('taskId')"
                @keydown.enter="commitField('taskId')"
              />
            </div>

            <div class="form-section">
              <label class="form-label">{{ t('canvas.propertiesCreated') }}</label>
              <div class="readonly-text">{{ formatDate(selectedPanel.created_at) }}</div>
            </div>

            <div class="form-section">
              <label class="form-label">{{ t('canvas.propertiesUpdated') }}</label>
              <div class="readonly-text">{{ formatDate(selectedPanel.updated_at) }}</div>
            </div>
          </template>

          <!-- 选中连线 -->
          <div v-else-if="selectedConnection" class="placeholder">
            <el-icon :size="36"><Connection /></el-icon>
            <p>已选中连线</p>
            <el-button size="small" type="danger" plain @click="deleteSelectedConn">
              {{ t('canvas.deleteConnection') }}
            </el-button>
          </div>

          <!-- 未选中 -->
          <div v-else class="placeholder">
            <el-icon :size="36"><InfoFilled /></el-icon>
            <p>{{ t('canvas.propertiesNoSelection') }}</p>
          </div>
        </el-tab-pane>

        <!-- Tab 2：图层（任务 4：CanvasLayersPanel） -->
        <el-tab-pane :label="t('canvas.layers.title')" name="layers">
          <CanvasLayersPanel :store="store" :selected-panel-id="store.selectedPanelId" />
        </el-tab-pane>

        <!-- Tab 3：备注（Task 9 实现） -->
        <el-tab-pane :label="t('canvas.notes.tab')" name="notes">
          <div v-if="!singleSelected" class="empty">
            {{ t('canvas.notes.empty') }}
          </div>
          <div v-else class="notes-editor">
            <div class="notes-header">
              <span class="notes-panel-name">{{ singleSelected.content?.name || panelTypeLabel(singleSelected.type) }}</span>
            </div>
            <el-input
              v-model="noteDraft"
              type="textarea"
              :rows="8"
              :placeholder="t('canvas.notes.placeholder')"
              @blur="commitNote"
            />
            <div class="notes-tip">{{ t('canvas.notes.tip') }}</div>
          </div>
        </el-tab-pane>

        <!-- Tab 4：助手（Task 2：CanvasAssistantPanel） -->
        <el-tab-pane :label="t('canvas.assistant.tab')" name="assistant">
          <CanvasAssistantPanel />
        </el-tab-pane>

        <!-- Tab 5：提示词库（任务 4） -->
        <el-tab-pane :label="t('canvas.drawer.prompts')" name="prompts" />
        <!-- Tab 6：素材库（任务 4） -->
        <el-tab-pane :label="t('canvas.drawer.assets')" name="assets" />
      </el-tabs>
    </div>

    <!-- 任务 4：提示词库 / 素材库 Drawer（仅在右侧面板未折叠时挂载） -->
    <PromptLibraryDrawer
      v-if="!collapsed"
      v-model="promptDrawerOpen"
      @select="onPromptSelect"
    />
    <AssetPickerDrawer
      v-if="!collapsed"
      v-model="assetDrawerOpen"
      @select="onAssetSelect"
    />
  </aside>
</template>

<script setup>
import { ref, reactive, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Connection, InfoFilled } from '@element-plus/icons-vue'
import { useCanvasStore } from '@/stores/canvas'
import { useI18n } from '@/i18n'
import CanvasAssistantPanel from '@/components/infinite-canvas/CanvasAssistantPanel.vue'
import CanvasLayersPanel from '@/components/infinite-canvas/CanvasLayersPanel.vue'
import PromptLibraryDrawer from '@/components/infinite-canvas/PromptLibraryDrawer.vue'
import AssetPickerDrawer from '@/components/infinite-canvas/AssetPickerDrawer.vue'

const { t } = useI18n()
const store = useCanvasStore()
const collapsed = ref(false)
const activeTab = ref('properties')

// 任务 4：两个 Drawer 的开关状态
const promptDrawerOpen = ref(false)
const assetDrawerOpen = ref(false)

/**
 * 监听 activeTab：点击"提示词库" / "素材库" Tab 时打开对应 Drawer
 * - 切到其他 Tab 时关闭两个 Drawer
 * - 这样 Tab 头只承担"开关"入口，Drawer 实际承载内容
 */
watch(activeTab, (tab) => {
  if (tab === 'prompts') {
    promptDrawerOpen.value = true
  } else if (tab === 'assets') {
    assetDrawerOpen.value = true
  } else {
    promptDrawerOpen.value = false
    assetDrawerOpen.value = false
  }
})

/** Drawer 关闭时把 activeTab 拉回"属性"，避免 Tab 头状态与 Drawer 状态不一致 */
watch(promptDrawerOpen, (open) => {
  if (!open && activeTab.value === 'prompts') activeTab.value = 'props'
})
watch(assetDrawerOpen, (open) => {
  if (!open && activeTab.value === 'assets') activeTab.value = 'props'
})

/** 任务 4：点击 Drawer 卡片（不拖动）时直接在画布视口中心插入一个节点 */
function onPromptSelect(p) {
  // 视口中心 → 世界坐标
  const center = {
    x: (window.innerWidth / 2 - store.viewport.x) / store.viewport.zoom,
    y: (window.innerHeight / 2 - store.viewport.y) / store.viewport.zoom,
  }
  store.addPanel({
    type: 'text',
    x: center.x - 150,
    y: center.y - 100,
    width: 300,
    height: 200,
    content: { text: p.content, name: p.name },
  })
  ElMessage.success(`已插入提示词 · ${p.name}`)
  promptDrawerOpen.value = false
}

function onAssetSelect(a) {
  const center = {
    x: (window.innerWidth / 2 - store.viewport.x) / store.viewport.zoom,
    y: (window.innerHeight / 2 - store.viewport.y) / store.viewport.zoom,
  }
  store.addPanel({
    type: 'image',
    x: center.x - 200,
    y: center.y - 150,
    width: 400,
    height: 300,
    content: { imageUrl: a.url, name: a.name },
  })
  ElMessage.success(t('canvas.addedToAssets') + ` · ${a.name}`)
  assetDrawerOpen.value = false
}

const selectedPanel = computed(() => store.selectedPanel)
const selectedConnection = computed(() => store.selectedConnection)
// 单选时的 panel 对象（多选或未选时为 null），用于"备注" Tab 隔离多选场景
const singleSelected = computed(() => {
  if (store.selectedPanelIds.length !== 1) return null
  return store.panels.find((p) => p.id === store.selectedPanelIds[0]) ?? null
})

const colorOptions = [
  { value: null, color: 'transparent', label: t('canvas.propertiesColorNone') },
  { value: 'blue', color: 'rgba(80, 140, 255, 0.5)', label: t('canvas.propertiesColorBlue') },
  { value: 'green', color: 'rgba(80, 200, 160, 0.5)', label: t('canvas.propertiesColorGreen') },
  { value: 'orange', color: 'rgba(255, 180, 80, 0.5)', label: t('canvas.propertiesColorOrange') },
  { value: 'red', color: 'rgba(255, 120, 120, 0.5)', label: t('canvas.propertiesColorRed') },
  { value: 'purple', color: 'rgba(160, 120, 255, 0.5)', label: t('canvas.propertiesColorPurple') },
]

/** 表单本地状态 - 避免每次输入都污染历史栈（属性 Tab 内的"备注"输入框仍由 commitField('note') 管理） */
const formState = reactive({
  name: '',
  note: '',
  color: null,
  x: 0,
  y: 0,
  width: 300,
  height: 200,
  taskId: '',
})

/** 备注 Tab 的本地草稿：跟随 singleSelected 切换同步，blur 时写回 store */
const noteDraft = ref('')
watch(
  () => singleSelected.value?.id,
  () => {
    noteDraft.value = singleSelected.value?.content?.note ?? ''
  },
  { immediate: true },
)

/** 节点类型 → 中文标签，用于"备注" Tab 头部显示 */
const TYPE_LABELS = {
  image: '图片预览', video: '视频预览', text: '文本笔记', url: 'URL 链接',
  'quick-generate': '快捷生成', 'file-upload': '文件上传',
  placeholder: '占位面板', frame: '分组框',
}
function panelTypeLabel(type) {
  return TYPE_LABELS[type] ?? '节点'
}

/** 当选中面板变化时，把面板内容同步到表单 */
watch(
  selectedPanel,
  (panel) => {
    if (!panel) return
    formState.name = panel.content?.name ?? ''
    formState.note = panel.content?.note ?? ''
    formState.color = panel.content?.color ?? null
    formState.x = Math.round(panel.x)
    formState.y = Math.round(panel.y)
    formState.width = Math.round(panel.width)
    formState.height = Math.round(panel.height)
    formState.taskId = panel.task_id ?? panel.taskId ?? ''
  },
  { immediate: true },
)

/** 提交单个字段的修改
 * - 名称/备注/颜色/任务ID：写入 panel.content，不影响几何
 * - 任务 ID：写入 panel.task_id
 * - x/y/width/height：写入 panel 顶层几何
 * - 备注（"备注" Tab）：由 commitNote 单独处理，避免污染属性 Tab 内的快速备注字段
 */
function commitField(field) {
  const panel = selectedPanel.value
  if (!panel) return

  if (field === 'name' || field === 'note' || field === 'color' || field === 'taskId') {
    const newContent = { ...(panel.content ?? {}) }
    if (field === 'name') newContent.name = formState.name
    if (field === 'note') newContent.note = formState.note
    if (field === 'color') newContent.color = formState.color
    if (field === 'taskId') {
      // 同步到 panel.task_id（设计文档里规定的字段）
      store._updatePanelDirect(panel.id, { task_id: formState.taskId || null })
      ElMessage.success(formState.taskId ? `已关联任务 ${formState.taskId}` : '已清除任务关联')
      return
    }
    // 手动指定要更新的字段并走历史栈
    store.pushSnapshot()
    store._updatePanelDirect(panel.id, { content: newContent })
  } else {
    // 几何字段：x/y/width/height
    const changes = {}
    if (field === 'x') changes.x = Number(formState.x)
    if (field === 'y') changes.y = Number(formState.y)
    if (field === 'width') changes.width = Math.max(150, Number(formState.width))
    if (field === 'height') changes.height = Math.max(100, Number(formState.height))
    store.pushSnapshot()
    store._updatePanelDirect(panel.id, changes)
  }
}

/** 提交备注：blur 时把草稿写回 store（仅在内容真正变化时写） */
function commitNote() {
  if (!singleSelected.value) return
  if (noteDraft.value !== (singleSelected.value.content?.note ?? '')) {
    store.updateNote(singleSelected.value.id, noteDraft.value)
  }
}

function setColor(value) {
  formState.color = value
  commitField('color')
}

function deleteSelectedConn() {
  if (selectedConnection.value) {
    store.deleteConnection(selectedConnection.value.id)
    ElMessage.success(t('canvas.deleteConnection') + ' ✓')
  }
}

function formatDate(iso) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleString()
  } catch {
    return iso
  }
}
</script>

<style scoped>
.canvas-right-panel {
  width: 280px;
  min-width: 280px;
  background: rgba(15, 22, 38, 0.75);
  border-left: 1px solid rgba(100, 150, 220, 0.12);
  display: flex;
  flex-direction: column;
  transition: width 0.2s ease, min-width 0.2s ease;
  backdrop-filter: blur(12px);
  user-select: none;
}

.canvas-right-panel.collapsed {
  width: 40px;
  min-width: 40px;
}

.right-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 14px 10px;
  border-bottom: 1px solid rgba(100, 150, 220, 0.08);
}

.right-panel-header h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #a0b4d6;
}

.collapsed .right-panel-header h3 {
  display: none;
}

.collapse-btn {
  cursor: pointer;
  color: #6b84aa;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.15s;
}

.collapse-btn:hover {
  color: #a0d4ff;
  background: rgba(80, 140, 255, 0.1);
}

.right-panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 4px;
}

/* Tabs：让 tab 头与右侧面板深色背景协调 */
.canvas-right-tabs {
  --el-color-primary: #85b2ff;
}

.canvas-right-tabs :deep(.el-tabs__header) {
  margin: 0 6px;
  border-bottom: 1px solid rgba(100, 150, 220, 0.08);
}

.canvas-right-tabs :deep(.el-tabs__item) {
  color: #8ba3c9;
  font-size: 12px;
  padding: 0 8px;
  height: 36px;
  line-height: 36px;
}

.canvas-right-tabs :deep(.el-tabs__item.is-active) {
  color: #e8eef7;
}

.canvas-right-tabs :deep(.el-tabs__active-bar) {
  background-color: #85b2ff;
}

.canvas-right-tabs :deep(.el-tabs__content) {
  padding: 0 8px 12px;
}

.form-section {
  margin-bottom: 14px;
}

.form-label {
  display: block;
  font-size: 11px;
  color: #8ba3c9;
  margin-bottom: 6px;
  letter-spacing: 0.3px;
}

.info-row {
  display: flex;
  gap: 8px;
}

.info-row > * {
  flex: 1;
}

.readonly-text {
  font-size: 12px;
  color: #6b84aa;
  padding: 4px 0;
  word-break: break-all;
}

.color-picker {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.color-dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.15);
  cursor: pointer;
  transition: transform 0.15s, border-color 0.15s;
  position: relative;
}

.color-dot:hover {
  transform: scale(1.15);
}

.color-dot.active {
  border-color: #fff;
  box-shadow: 0 0 0 2px rgba(80, 140, 255, 0.5);
}

.color-dot[style*="transparent"] {
  background: transparent !important;
  border: 2px dashed rgba(255, 255, 255, 0.2);
}

.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 16px;
  text-align: center;
  color: #6b84aa;
  font-size: 12px;
}

.placeholder p {
  margin: 0;
}

.placeholder .el-icon {
  color: #4a5b7a;
}

/* 备注 Tab 编辑器（Task 9） */
.notes-editor { padding: 8px 0; }
.notes-header { margin-bottom: 8px; }
.notes-panel-name {
  font-size: 12px;
  color: #8ba3c9;
}
.notes-tip {
  margin-top: 6px;
  font-size: 11px;
  color: #6b84aa;
}
.empty {
  padding: 24px 0;
  text-align: center;
  color: #6b84aa;
  font-size: 12px;
}

/* Element Plus 覆盖：深色主题 */
:deep(.el-input__inner),
:deep(.el-textarea__inner) {
  background: rgba(20, 30, 50, 0.6) !important;
  border-color: rgba(100, 150, 220, 0.2) !important;
  color: #e8eef7 !important;
}

:deep(.el-input__inner:focus),
:deep(.el-textarea__inner:focus) {
  border-color: rgba(80, 140, 255, 0.6) !important;
}
</style>
