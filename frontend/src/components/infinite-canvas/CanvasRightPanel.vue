<!-- =====================================================
     右侧属性面板
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
    </div>
  </aside>
</template>

<script setup>
import { ref, reactive, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Connection, InfoFilled } from '@element-plus/icons-vue'
import { useCanvasStore } from '@/stores/canvas'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const store = useCanvasStore()
const collapsed = ref(false)

const selectedPanel = computed(() => store.selectedPanel)
const selectedConnection = computed(() => store.selectedConnection)

const colorOptions = [
  { value: null, color: 'transparent', label: t('canvas.propertiesColorNone') },
  { value: 'blue', color: 'rgba(80, 140, 255, 0.5)', label: t('canvas.propertiesColorBlue') },
  { value: 'green', color: 'rgba(80, 200, 160, 0.5)', label: t('canvas.propertiesColorGreen') },
  { value: 'orange', color: 'rgba(255, 180, 80, 0.5)', label: t('canvas.propertiesColorOrange') },
  { value: 'red', color: 'rgba(255, 120, 120, 0.5)', label: t('canvas.propertiesColorRed') },
  { value: 'purple', color: 'rgba(160, 120, 255, 0.5)', label: t('canvas.propertiesColorPurple') },
]

/** 表单本地状态 - 避免每次输入都污染历史栈 */
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
 * - x/y/width/height：写入 panel 顶层几何
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
  padding: 14px;
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
