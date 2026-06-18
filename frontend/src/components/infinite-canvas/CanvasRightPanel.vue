<!-- =====================================================
     右侧属性面板 CanvasRightPanel
     - 宽度 260px，背景使用 var(--canvas-panel-bg)，左侧边框
     - 顶部双 Tab：属性 | 备注
     - 属性 Tab：
       · 未选中：提示"未选中任何面板"
       · 选中单个面板：名称(可编辑)、类型/位置/尺寸(只读)、
         锁定/隐藏/复制/删除按钮、创建与更新时间
       · 选中连线：source → target 信息 + 删除按钮
     - 备注 Tab：
       · 选中单个面板：textarea，onChange 调 store.updateNote
       · 未选中：提示"选中单个节点以编辑备注"
     ===================================================== -->

<template>
  <aside class="canvas-right-panel">
    <el-tabs v-model="activeTab" class="right-panel-tabs">
      <!-- Tab 1：属性 -->
      <el-tab-pane label="属性" name="props">
        <!-- 选中单个面板 -->
        <template v-if="isSingleSelected && selectedPanel">
          <div class="form-section">
            <label class="form-label">名称</label>
            <el-input
              v-model="nameDraft"
              size="small"
              placeholder="请输入名称"
              @change="onNameChange"
            />
          </div>

          <div class="form-section">
            <label class="form-label">类型</label>
            <div class="readonly-text">{{ panelTypeLabel(selectedPanel.type) }}</div>
          </div>

          <div class="form-section">
            <label class="form-label">位置</label>
            <div class="info-row">
              <div class="info-cell"><span class="info-key">X</span><span class="info-val">{{ Math.round(selectedPanel.x) }}</span></div>
              <div class="info-cell"><span class="info-key">Y</span><span class="info-val">{{ Math.round(selectedPanel.y) }}</span></div>
            </div>
          </div>

          <div class="form-section">
            <label class="form-label">尺寸</label>
            <div class="info-row">
              <div class="info-cell"><span class="info-key">W</span><span class="info-val">{{ Math.round(selectedPanel.width) }}</span></div>
              <div class="info-cell"><span class="info-key">H</span><span class="info-val">{{ Math.round(selectedPanel.height) }}</span></div>
            </div>
          </div>

          <!-- 操作按钮：锁定 / 隐藏 / 复制 / 删除 -->
          <div class="form-section">
            <label class="form-label">操作</label>
            <div class="action-row">
              <el-button size="small" :type="isLocked ? 'primary' : 'default'" @click="store.toggleLock(selectedPanel.id)">
                {{ isLocked ? '解锁' : '锁定' }}
              </el-button>
              <el-button size="small" :type="isHidden ? 'warning' : 'default'" @click="toggleHidden">
                {{ isHidden ? '显示' : '隐藏' }}
              </el-button>
              <el-button size="small" @click="store.duplicatePanel(selectedPanel.id)">复制</el-button>
              <el-button size="small" type="danger" plain @click="store.deletePanel(selectedPanel.id)">删除</el-button>
            </div>
          </div>

          <div class="form-section">
            <label class="form-label">创建时间</label>
            <div class="readonly-text">{{ formatDate(selectedPanel.created_at) }}</div>
          </div>

          <div class="form-section">
            <label class="form-label">更新时间</label>
            <div class="readonly-text">{{ formatDate(selectedPanel.updated_at) }}</div>
          </div>
        </template>

        <!-- 选中连线 -->
        <div v-else-if="selectedConnection" class="placeholder">
          <p class="conn-info">
            <span class="conn-name">{{ connectionSourceName }}</span>
            <span class="conn-arrow">→</span>
            <span class="conn-name">{{ connectionTargetName }}</span>
          </p>
          <el-button size="small" type="danger" plain @click="deleteSelectedConn">删除连线</el-button>
        </div>

        <!-- 未选中任何对象 -->
        <div v-else class="placeholder">
          <p>未选中任何面板</p>
        </div>
      </el-tab-pane>

      <!-- Tab 2：备注 -->
      <el-tab-pane label="备注" name="notes">
        <div v-if="isSingleSelected && selectedPanel" class="notes-editor">
          <el-input
            v-model="noteDraft"
            type="textarea"
            :rows="10"
            placeholder="请输入节点备注…"
            @change="onNoteChange"
          />
        </div>
        <div v-else class="placeholder">
          <p>选中单个节点以编辑备注</p>
        </div>
      </el-tab-pane>
    </el-tabs>
  </aside>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useCanvasStore } from '@/stores/canvas'

const store = useCanvasStore()
const activeTab = ref('props')

// 当前选中的面板（getter）
const selectedPanel = computed(() => store.selectedPanel)

// 是否单选：selectedPanelIds 长度为 1
const isSingleSelected = computed(() => store.selectedPanelIds.length === 1)

// 当前选中的连线对象（通过 selectedConnectionId 在 connections 中查找）
const selectedConnection = computed(() => {
  if (!store.selectedConnectionId) return null
  return store.connections.find((c) => c.id === store.selectedConnectionId) ?? null
})

// 连线 source / target 面板名称
const connectionSourceName = computed(() => {
  const c = selectedConnection.value
  if (!c) return '—'
  const p = store.panels.find((p) => p.id === c.source_panel_id)
  return p?.content?.name || p?.id || '—'
})
const connectionTargetName = computed(() => {
  const c = selectedConnection.value
  if (!c) return '—'
  const p = store.panels.find((p) => p.id === c.target_panel_id)
  return p?.content?.name || p?.id || '—'
})

// 锁定 / 隐藏状态
const isLocked = computed(() => !!selectedPanel.value?.content?.locked)
const isHidden = computed(() => {
  const id = selectedPanel.value?.id
  return id ? store.isPanelHidden(id) : false
})

// 名称与备注的本地草稿，跟随选中面板切换同步
const nameDraft = ref('')
const noteDraft = ref('')
watch(
  () => selectedPanel.value?.id,
  () => {
    const p = selectedPanel.value
    nameDraft.value = p?.content?.name ?? ''
    noteDraft.value = p?.content?.note ?? ''
  },
  { immediate: true },
)

/** 节点类型 → 中文标签 */
function panelTypeLabel(type) {
  const map = {
    image: '图片',
    video: '视频',
    text: '文本',
    config: '配置',
    frame: '分组框',
    'quick-generate': '快捷生成',
  }
  return map[type] || type
}

/** 名称变更：写入 panel.content.name */
function onNameChange() {
  const p = selectedPanel.value
  if (!p) return
  store.updatePanel(p.id, {
    content: { ...(p.content ?? {}), name: nameDraft.value },
  })
}

/** 备注变更：调 store.updateNote */
function onNoteChange() {
  const p = selectedPanel.value
  if (!p) return
  store.updateNote(p.id, noteDraft.value)
}

/** 切换隐藏状态 */
function toggleHidden() {
  const p = selectedPanel.value
  if (!p) return
  store.setPanelHidden(p.id, !isHidden.value)
}

/** 删除当前选中的连线 */
function deleteSelectedConn() {
  const c = selectedConnection.value
  if (!c) return
  store.deleteConnection(c.id)
  ElMessage.success('已删除连线')
}

/** 格式化时间戳 */
function formatDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}
</script>

<style scoped>
.canvas-right-panel {
  width: 260px;
  min-width: 260px;
  background: var(--canvas-panel-bg, rgba(22, 32, 54, 0.7));
  border-left: 1px solid var(--canvas-node-border, rgba(120, 170, 230, 0.2));
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(12px);
  user-select: none;
  overflow: hidden;
}

.right-panel-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 8px 8px 0;
}

/* Tab 头部样式 */
.right-panel-tabs :deep(.el-tabs__header) {
  margin: 0 0 8px;
}

.right-panel-tabs :deep(.el-tabs__item) {
  font-size: 12px;
  height: 34px;
  line-height: 34px;
  color: var(--canvas-node-muted-text, #8ba3c9);
}

.right-panel-tabs :deep(.el-tabs__item.is-active) {
  color: var(--canvas-node-title-text, #fff);
}

.right-panel-tabs :deep(.el-tabs__active-bar) {
  background-color: var(--canvas-node-active-border, #85b2ff);
}

.right-panel-tabs :deep(.el-tabs__content) {
  overflow-y: auto;
  padding-bottom: 12px;
}

/* 表单分区 */
.form-section {
  margin-bottom: 14px;
}

.form-label {
  display: block;
  font-size: 11px;
  color: var(--canvas-node-muted-text, #8ba3c9);
  margin-bottom: 6px;
  letter-spacing: 0.3px;
}

.readonly-text {
  font-size: 12px;
  color: var(--canvas-node-title-text, #e8eef7);
  padding: 2px 0;
  word-break: break-all;
}

.info-row {
  display: flex;
  gap: 8px;
}

.info-cell {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.15);
}

.info-key {
  color: var(--canvas-node-muted-text, #8ba3c9);
}

.info-val {
  color: var(--canvas-node-title-text, #e8eef7);
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.action-row .el-button {
  flex: 1;
  min-width: 60px;
}

/* 占位提示 */
.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 16px;
  text-align: center;
  color: var(--canvas-node-muted-text, #6b84aa);
  font-size: 12px;
}

.placeholder p {
  margin: 0;
}

/* 连线信息 */
.conn-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--canvas-node-title-text, #e8eef7);
}

.conn-name {
  max-width: 90px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conn-arrow {
  color: var(--canvas-node-muted-text, #8ba3c9);
}

/* 备注 Tab */
.notes-editor {
  padding: 4px 0;
}

/* Element Plus 深色主题覆盖 */
:deep(.el-input__inner),
:deep(.el-textarea__inner) {
  background: rgba(0, 0, 0, 0.2);
  border-color: var(--canvas-node-border, rgba(120, 170, 230, 0.2));
  color: var(--canvas-node-title-text, #e8eef7);
}

:deep(.el-input__inner:focus),
:deep(.el-textarea__inner:focus) {
  border-color: var(--canvas-node-active-border, #85b2ff);
}
</style>
