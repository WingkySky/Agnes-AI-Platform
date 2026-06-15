/* =====================================================
 * 右键上下文菜单
 * - 监听画布区域右键事件
 * - 根据点击目标（面板/连线/背景）渲染不同菜单
 * - 预留扩展位置
 * ===================================================== */

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="context-menu"
      :style="{ left: `${x}px`, top: `${y}px` }"
      @pointerdown.stop
    >
      <!-- 面板右键菜单 -->
      <template v-if="target === 'panel'">
        <div class="context-menu-item" @click="handleAction('copy')">
          <el-icon><CopyDocument /></el-icon>
          {{ t('canvas.copyPanel') }}
        </div>
        <div class="context-menu-item" @click="handleAction('delete')">
          <el-icon><Delete /></el-icon>
          {{ t('canvas.deletePanel') }}
        </div>
        <div class="context-menu-item" @click="handleAction('select')">
          <el-icon><Select /></el-icon>
          {{ t('canvas.selectPanel') }}
        </div>
        <div class="context-menu-divider" />
        <div class="context-menu-item context-menu-item--lock" @click="handleAction('lock')">
          <el-icon><Lock /></el-icon>
          {{ t('canvas.lockPanel') }}
        </div>
      </template>

      <!-- 连线右键菜单 -->
      <template v-if="target === 'connection'">
        <div class="context-menu-item" @click="handleAction('delete')">
          <el-icon><Delete /></el-icon>
          {{ t('canvas.deleteConnection') }}
        </div>
        <div class="context-menu-item" @click="handleAction('disconnect')">
          <el-icon><CloseBold /></el-icon>
          {{ t('canvas.disconnect') }}
        </div>
      </template>

      <!-- 背景右键菜单 -->
      <template v-if="target === 'background'">
        <div class="context-menu-item" @click="handleAction('selectAll')">
          <el-icon><Select /></el-icon>
          {{ t('canvas.selectAll') }}
        </div>
        <div class="context-menu-item context-menu-item--disabled">
          <el-icon><DocumentCopy /></el-icon>
          {{ t('canvas.paste') }}
        </div>
        <div class="context-menu-divider" />
        <div class="context-menu-item" @click="handleAction('centerView')">
          <el-icon><FullScreen /></el-icon>
          {{ t('canvas.centerView') }}
        </div>
        <div class="context-menu-item context-menu-item--danger" @click="handleAction('clearCanvas')">
          <el-icon><Delete /></el-icon>
          {{ t('canvas.clearCanvas') }}
        </div>
      </template>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import { useI18n } from '@/i18n'
import {
  CopyDocument, Delete, Select, Lock, CloseBold, DocumentCopy, FullScreen,
} from '@element-plus/icons-vue'

const { t } = useI18n()
const store = useCanvasStore()

const visible = ref(false)
const x = ref(0)
const y = ref(0)
const target = ref('background') // 'panel' | 'connection' | 'background'
const contextData = ref({})

/** 显示菜单 */
function show(event, data) {
  visible.value = true
  x.value = event.clientX
  y.value = event.clientY
  target.value = data.target
  contextData.value = data.data || {}

  // 确保菜单位置不超出视口
  requestAnimationFrame(() => {
    const menu = document.querySelector('.context-menu')
    if (!menu) return
    const rect = menu.getBoundingClientRect()
    if (rect.right > window.innerWidth) {
      x.value = window.innerWidth - rect.width - 4
    }
    if (rect.bottom > window.innerHeight) {
      y.value = window.innerHeight - rect.height - 4
    }
  })
}

/** 隐藏菜单 */
function hide() {
  visible.value = false
}

/** 处理菜单动作 */
function handleAction(action) {
  hide()

  const panelId = contextData.value.panelId
  const connectionId = contextData.value.connectionId

  switch (action) {
    case 'copy':
      if (panelId) store.duplicatePanel(panelId)
      break
    case 'delete':
      if (panelId) store.deletePanel(panelId)
      else if (connectionId) store.deleteConnection(connectionId)
      break
    case 'select':
      if (panelId) store.selectPanel(panelId)
      break
    case 'lock':
      // 预留：锁定面板
      break
    case 'disconnect':
      if (connectionId) store.deleteConnection(connectionId)
      break
    case 'selectAll':
      if (store.panels.length > 0) store.selectPanel(store.panels[0].id)
      break
    case 'centerView':
      store.resetView()
      break
    case 'clearCanvas':
      if (store.panels.length > 0) {
        // 用 store action 一次性清空（只压一次快照，避免历史栈被污染）
        store.clearAllPanels()
      }
      break
  }
}

defineExpose({ show, hide })
</script>

<style scoped>
.context-menu {
  position: fixed;
  z-index: 10000;
  min-width: 180px;
  background: rgba(20, 30, 50, 0.95);
  border: 1px solid rgba(100, 150, 220, 0.2);
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(12px);
  padding: 4px 0;
  user-select: none;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 13px;
  color: #8ba3c9;
  cursor: pointer;
  transition: all 0.1s;
}

.context-menu-item:hover:not(.context-menu-item--disabled) {
  background: rgba(80, 140, 255, 0.15);
  color: #a0d4ff;
}

.context-menu-item.context-menu-item--danger:hover {
  background: rgba(255, 77, 79, 0.15);
  color: #ff6b6b;
}

.context-menu-item.context-menu-item--lock:hover {
  background: rgba(255, 193, 7, 0.15);
  color: #ffc107;
}

.context-menu-item--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.context-menu-divider {
  height: 1px;
  margin: 4px 0;
  background: rgba(100, 150, 220, 0.1);
}
</style>
