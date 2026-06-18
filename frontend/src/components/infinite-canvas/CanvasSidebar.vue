<!-- =====================================================
     CanvasSidebar 左侧多画布管理
     - 顶部标题"画布管理" + "新建画布"按钮
     - 画布列表：名称、面板数量、切换/重命名/删除按钮
     - 当前画布高亮
     - 双击画布名称进入 inline 重命名
     - 删除前用 ElMessageBox.confirm 确认
     样式：左侧固定宽度 220px，垂直布局
     ===================================================== -->

<template>
  <div class="canvas-sidebar">
    <!-- 顶部标题 + 新建按钮 -->
    <div class="sidebar-header">
      <span class="sidebar-title">{{ t('canvas.sidebarTitle') }}</span>
      <el-button class="header-btn" size="small" :title="t('canvas.newCanvas')" @click="handleCreate">
        <span class="btn-icon">＋</span>
      </el-button>
    </div>

    <!-- 画布列表 -->
    <div class="sidebar-list">
      <div v-if="store.workspaces.length === 0" class="empty-hint">
        {{ t('canvas.noCanvas') }}
      </div>

      <div
        v-for="ws in store.workspaces"
        :key="ws.id"
        class="canvas-item"
        :class="{ active: ws.id === store.activeWorkspaceId }"
        @click="handleSwitch(ws.id)"
      >
        <!-- 名称 / 重命名输入框 -->
        <div class="item-main">
          <el-input
            v-if="renamingId === ws.id"
            ref="renameInputRef"
            v-model="renamingName"
            size="small"
            autofocus
            @keyup.enter="commitRename(ws.id)"
            @blur="commitRename(ws.id)"
          />
          <div
            v-else
            class="item-name"
            :title="ws.name"
            @dblclick.stop="startRename(ws)"
          >
            {{ ws.name }}
          </div>
          <div class="item-meta">{{ getPanelCount(ws) }} {{ t('canvas.panels') }}</div>
        </div>

        <!-- 操作按钮 -->
        <div class="item-actions" @click.stop>
          <button class="icon-btn" title="重命名" @click="startRename(ws)">✎</button>
          <button class="icon-btn danger" title="删除" @click="handleDelete(ws)">🗑</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
// ------ 引入 Vue / Element Plus / Store / i18n ------
import { ref, nextTick } from 'vue'
import { ElButton, ElInput, ElMessageBox, ElMessage } from 'element-plus'
import { useCanvasStore } from '@/stores/canvas'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const store = useCanvasStore()

// ------ 重命名状态 ------
const renamingId = ref(null)
const renamingName = ref('')
const renameInputRef = ref(null)

/** 获取画布的面板数量（兼容运行时 panels 与持久化 panels） */
function getPanelCount(ws) {
  // 当前激活画布的 panels 在 store.panels 顶层；非激活的在 ws.panels
  if (ws.id === store.activeWorkspaceId) {
    return store.panels.length
  }
  return Array.isArray(ws.panels) ? ws.panels.length : 0
}

/** 新建画布 */
function handleCreate() {
  const idx = store.workspaces.length + 1
  store.createWorkspace(`画布 ${idx}`)
}

/** 切换画布 */
function handleSwitch(id) {
  if (id === store.activeWorkspaceId) return
  store.switchWorkspace(id)
}

/** 进入重命名模式 */
async function startRename(ws) {
  renamingId.value = ws.id
  renamingName.value = ws.name
  await nextTick()
  renameInputRef.value?.focus?.()
}

/** 提交重命名 */
function commitRename(id) {
  if (renamingId.value !== id) return
  const name = renamingName.value.trim()
  if (name) {
    store.renameWorkspace(id, name)
  }
  renamingId.value = null
  renamingName.value = ''
}

/** 删除画布（带确认） */
async function handleDelete(ws) {
  try {
    await ElMessageBox.confirm(
      t('canvas.confirmDelete'),
      t('common.delete'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning',
      },
    )
    store.deleteWorkspace(ws.id)
    ElMessage.success('已删除')
  } catch {
    // 用户取消
  }
}
</script>

<style scoped>
/* 左侧栏：固定宽度 220px，垂直布局 */
.canvas-sidebar {
  width: 220px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--canvas-panel-bg);
  border-right: 1px solid var(--canvas-node-border);
  color: var(--canvas-node-title-text);
  overflow: hidden;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--canvas-node-border);
}

.sidebar-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--canvas-node-title-text);
}

.header-btn {
  background: transparent !important;
  border: none !important;
  color: var(--canvas-node-muted-text) !important;
  padding: 4px 8px !important;
  border-radius: 6px !important;
  transition: all 0.15s ease;
}

.header-btn:hover {
  background: var(--canvas-selection-fill) !important;
  color: var(--canvas-node-active-border) !important;
}

.btn-icon {
  font-size: 16px;
  line-height: 1;
}

.sidebar-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
}

.empty-hint {
  padding: 20px 12px;
  font-size: 12px;
  color: var(--canvas-node-muted-text);
  text-align: center;
}

/* 画布列表项 */
.canvas-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s ease;
  margin-bottom: 2px;
}

.canvas-item:hover {
  background: var(--canvas-selection-fill);
}

.canvas-item.active {
  background: var(--canvas-selection-fill);
  border-left: 2px solid var(--canvas-node-active-border);
}

.item-main {
  flex: 1;
  min-width: 0;
}

.item-name {
  font-size: 13px;
  color: var(--canvas-node-title-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-meta {
  font-size: 11px;
  color: var(--canvas-node-muted-text);
  margin-top: 2px;
}

.item-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.canvas-item:hover .item-actions {
  opacity: 1;
}

.icon-btn {
  background: transparent;
  border: none;
  color: var(--canvas-node-muted-text);
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  font-size: 12px;
  transition: all 0.15s ease;
}

.icon-btn:hover {
  background: var(--canvas-node-border);
  color: var(--canvas-node-title-text);
}

.icon-btn.danger:hover {
  color: #f87171;
}

/* 重命名输入框 */
.item-main :deep(.el-input__wrapper) {
  background: var(--canvas-bg);
  border: 1px solid var(--canvas-node-active-border);
  box-shadow: none;
  height: 24px;
}

.item-main :deep(.el-input__inner) {
  color: var(--canvas-node-title-text);
  font-size: 13px;
}
</style>
