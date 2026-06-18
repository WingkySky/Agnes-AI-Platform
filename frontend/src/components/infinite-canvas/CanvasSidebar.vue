<!-- =====================================================
     CanvasSidebar 左侧栏：多画布管理
     - 顶部标题"画布管理" + 新建画布按钮
     - 画布列表：点击切换 / 双击重命名 / 删除确认（el-popconfirm）
     - 当前激活画布高亮
     - 底部主题切换（深色 / 浅色）
     - 直接操作 useCanvasStore，不对外 emit
     ===================================================== -->

<template>
  <aside class="canvas-sidebar">
    <!-- 顶部标题 + 新建按钮 -->
    <div class="sidebar-header">
      <span class="sidebar-title">{{ t('canvas.sidebarTitle') }}</span>
      <button class="icon-btn" :title="t('canvas.newCanvas')" @click="handleNewCanvas">
        <el-icon><Plus /></el-icon>
      </button>
    </div>

    <!-- 画布列表（可滚动） -->
    <div class="workspace-list">
      <div v-if="store.workspaces.length === 0" class="empty-hint">
        {{ t('canvas.noCanvas') }}
      </div>

      <div
        v-for="ws in store.workspaces"
        :key="ws.id"
        class="workspace-item"
        :class="{ active: ws.id === store.activeWorkspaceId }"
        @click="handleSwitch(ws.id)"
        @dblclick="startRename(ws)"
      >
        <!-- 名称行：重命名时显示 el-input，否则显示文本 -->
        <div class="ws-name-row">
          <el-input
            v-if="renameState.id === ws.id"
            ref="renameInputRef"
            v-model="renameState.value"
            size="small"
            :placeholder="t('canvas.renamePlaceholder')"
            @keyup.enter="confirmRename"
            @keyup.escape="cancelRename"
            @blur="confirmRename"
            @click.stop
          />
          <span v-else class="ws-name" :title="ws.name">{{ ws.name }}</span>

          <!-- 删除按钮（el-popconfirm 确认） -->
          <el-popconfirm
            :title="t('canvas.confirmDelete')"
            confirm-button-text="确定"
            cancel-button-text="取消"
            @confirm="store.deleteWorkspace(ws.id)"
          >
            <template #reference>
              <button class="delete-btn" :title="t('canvas.toolbar.delete')" @click.stop>
                <el-icon><Delete /></el-icon>
              </button>
            </template>
          </el-popconfirm>
        </div>

        <!-- 元信息：创建时间 + 面板数量 -->
        <div v-if="renameState.id !== ws.id" class="ws-meta">
          <span class="ws-date">{{ formatDate(ws.created_at) }}</span>
          <span class="ws-count">{{ getPanelCount(ws) }} {{ t('canvas.panels') }}</span>
        </div>
      </div>
    </div>

    <!-- 底部主题切换 -->
    <div class="sidebar-footer">
      <div class="theme-toggle">
        <button
          class="theme-btn"
          :class="{ active: store.themeMode === 'dark' }"
          @click="store.setThemeMode('dark')"
        >
          深色
        </button>
        <button
          class="theme-btn"
          :class="{ active: store.themeMode === 'light' }"
          @click="store.setThemeMode('light')"
        >
          浅色
        </button>
      </div>
    </div>
  </aside>
</template>

<script setup>
// ------ 模块依赖 ------
import { reactive, ref, nextTick } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import { useI18n } from '@/i18n'

const store = useCanvasStore()
const { t } = useI18n()

// ------ 重命名状态 ------
// renameState.id 为正在重命名的 workspace id，null 表示不在重命名
const renameState = reactive({ id: null, value: '' })
const renameInputRef = ref(null)

// ------ 新建画布 ------
function handleNewCanvas() {
  const name = `画布 ${store.workspaces.length + 1}`
  store.createWorkspace(name)
}

// ------ 切换画布 ------
function handleSwitch(id) {
  if (id !== store.activeWorkspaceId) {
    store.switchWorkspace(id)
  }
}

// ------ 开始重命名 ------
async function startRename(ws) {
  renameState.id = ws.id
  renameState.value = ws.name
  await nextTick()
  // ref 在 v-for 内可能是数组，取第一个
  const el = Array.isArray(renameInputRef.value)
    ? renameInputRef.value[0]
    : renameInputRef.value
  el?.focus?.()
  el?.select?.()
}

// ------ 确认重命名 ------
function confirmRename() {
  if (renameState.id) {
    store.renameWorkspace(renameState.id, renameState.value)
    renameState.id = null
  }
}

// ------ 取消重命名 ------
function cancelRename() {
  renameState.id = null
}

// ------ 面板数量：激活画布用 store.panels，其余用 workspace.panels ------
function getPanelCount(ws) {
  if (ws.id === store.activeWorkspaceId) return store.panels.length
  return ws.panels?.length ?? 0
}

// ------ 日期格式化：MM-DD HH:mm ------
function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${mm}-${dd} ${hh}:${mi}`
}
</script>

<style scoped>
/* 左侧栏容器：220px 宽，全高，右侧分隔线 */
.canvas-sidebar {
  width: 220px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--canvas-panel-bg);
  border-right: 1px solid var(--canvas-node-border);
  backdrop-filter: blur(12px);
  user-select: none;
}

/* 顶部标题栏 */
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--canvas-node-border);
}

.sidebar-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--canvas-node-title-text);
  letter-spacing: 0.5px;
}

/* 极简扁平图标按钮 */
.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--canvas-node-muted-text);
  cursor: pointer;
  transition: all 0.15s ease;
}

.icon-btn:hover {
  background: var(--canvas-node-border);
  color: var(--canvas-node-title-text);
}

/* 画布列表（可滚动区域） */
.workspace-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.workspace-list::-webkit-scrollbar {
  width: 4px;
}

.workspace-list::-webkit-scrollbar-thumb {
  background: var(--canvas-node-border);
  border-radius: 2px;
}

/* 空状态提示 */
.empty-hint {
  padding: 24px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--canvas-node-muted-text);
  line-height: 1.6;
}

/* 单个画布卡片 */
.workspace-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
  border: 1px solid transparent;
  transition: all 0.15s ease;
}

.workspace-item:hover {
  background: var(--canvas-node-border);
}

.workspace-item.active {
  background: var(--canvas-node-border);
  border-color: var(--canvas-node-active-border);
}

/* 名称行：名称 + 删除按钮 */
.ws-name-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.ws-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: var(--canvas-node-title-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 删除按钮：默认隐藏，hover 时显示 */
.delete-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--canvas-node-muted-text);
  cursor: pointer;
  opacity: 0;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.workspace-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  background: rgba(248, 113, 113, 0.15);
  color: #f87171;
}

/* 元信息行 */
.ws-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 11px;
  color: var(--canvas-node-muted-text);
}

.ws-date {
  font-variant-numeric: tabular-nums;
}

.ws-count {
  margin-left: auto;
}

/* 底部主题切换 */
.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--canvas-node-border);
}

.theme-toggle {
  display: flex;
  gap: 4px;
  background: var(--canvas-node-border);
  border-radius: 8px;
  padding: 3px;
}

.theme-btn {
  flex: 1;
  padding: 6px 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--canvas-node-muted-text);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.theme-btn.active {
  background: var(--canvas-panel-bg);
  color: var(--canvas-node-title-text);
  font-weight: 500;
}

.theme-btn:not(.active):hover {
  color: var(--canvas-node-title-text);
}
</style>
