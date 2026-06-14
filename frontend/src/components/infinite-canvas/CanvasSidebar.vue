/* =====================================================
 * 左侧栏：多画布管理
 * - 画布列表展示
 * - 新建/删除画布按钮
 * - 选中高亮
 * ===================================================== */

<template>
  <div class="canvas-sidebar">
    <div class="sidebar-header">
      <h3>{{ t('canvas.sidebarTitle') }}</h3>
      <el-tooltip :content="t('canvas.newCanvas')" placement="right">
        <el-icon class="add-icon" @click="handleCreate">
          <Plus />
        </el-icon>
      </el-tooltip>
    </div>

    <div class="sidebar-list">
      <div
        v-for="ws in workspaces"
        :key="ws.id"
        :class="['sidebar-item', { active: ws.id === store.activeWorkspaceId }]"
        @click="store.switchWorkspace(ws.id)"
      >
        <el-icon><Monitor /></el-icon>
        <span class="sidebar-item-name">{{ ws.name }}</span>
        <el-icon
          v-if="workspaces.length > 1"
          class="sidebar-item-delete"
          @click.stop="handleDelete(ws.id)"
        >
          <Delete />
        </el-icon>
      </div>

      <!-- 空状态 -->
      <div v-if="workspaces.length === 0" class="sidebar-empty">
        <p>{{ t('canvas.noCanvas') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Plus, Delete, Monitor } from '@element-plus/icons-vue'
import { useCanvasStore } from '@/stores/canvas'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const store = useCanvasStore()
const workspaces = computed(() => store.workspaces)

function handleCreate() {
  const name = `${t('canvas.canvas')} ${workspaces.value.length + 1}`
  store.createWorkspace(name)
}

async function handleDelete(id) {
  await ElMessageBox.confirm(
    t('canvas.confirmDelete'),
    t('common.confirm'),
    { type: 'warning' },
  )
  store.deleteWorkspace(id)
}
</script>

<style scoped>
.canvas-sidebar {
  width: 220px;
  min-width: 220px;
  background: rgba(15, 22, 38, 0.75);
  border-right: 1px solid rgba(100, 150, 220, 0.12);
  display: flex;
  flex-direction: column;
  user-select: none;
  backdrop-filter: blur(12px);
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 14px 10px;
  border-bottom: 1px solid rgba(100, 150, 220, 0.08);
}

.sidebar-header h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #a0b4d6;
}

.add-icon {
  font-size: 18px;
  color: #508cff;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  transition: background 0.15s;
}

.add-icon:hover {
  background: rgba(80, 140, 255, 0.12);
}

.sidebar-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.sidebar-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: #8ba3c9;
  transition: all 0.15s;
}

.sidebar-item:hover {
  background: rgba(120, 170, 255, 0.06);
  color: #c0d4f6;
}

.sidebar-item.active {
  background: linear-gradient(135deg, rgba(80, 140, 255, 0.2) 0%, rgba(160, 120, 255, 0.2) 100%);
  color: #fff;
}

.sidebar-item-icon {
  font-size: 15px;
}

.sidebar-item-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-item-delete {
  font-size: 14px;
  color: #6b84aa;
  opacity: 0;
  transition: all 0.15s;
}

.sidebar-item:hover .sidebar-item-delete {
  opacity: 1;
}

.sidebar-item-delete:hover {
  color: #ff6b6b;
}

.sidebar-empty {
  padding: 20px;
  text-align: center;
  color: #6b84aa;
  font-size: 13px;
}
</style>
