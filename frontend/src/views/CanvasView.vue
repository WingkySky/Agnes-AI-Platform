<!-- =====================================================
     无限画布页面
     - 左侧栏：多画布管理
     - 中间：无限画布主体
     - 顶部：工具栏（含导入/导出按钮）
     - 右侧：选中面板/连线的属性编辑面板
     - 全局快捷键处理器
     - 右键上下文菜单
     - Minimap 小地图
     ===================================================== -->

<template>
  <div class="canvas-view" @contextmenu.prevent="handleContextMenu">
    <!-- 左侧栏 -->
    <CanvasSidebar />

    <!-- 主内容区 -->
    <div class="canvas-main">
      <!-- 顶部工具栏 -->
      <CanvasToolbar @export-json="handleExportJson" @import-json="triggerImport" />

      <!-- 无限画布 -->
      <InfiniteCanvas ref="infiniteCanvasRef" />

      <!-- Minimap 小地图 -->
      <CanvasMinimap />
    </div>

    <!-- 右侧属性面板 -->
    <CanvasRightPanel />

    <!-- 右键菜单 -->
    <CanvasContextMenu ref="contextMenuRef" />

    <!-- 隐藏的文件 input 用于导入 JSON -->
    <input
      ref="importInputRef"
      type="file"
      accept=".json,application/json"
      style="display: none"
      @change="handleImportFile"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useCanvasStore } from '@/stores/canvas'
import CanvasSidebar from '@/components/infinite-canvas/CanvasSidebar.vue'
import CanvasToolbar from '@/components/infinite-canvas/CanvasToolbar.vue'
import InfiniteCanvas from '@/components/infinite-canvas/InfiniteCanvas.vue'
import CanvasContextMenu from '@/components/infinite-canvas/CanvasContextMenu.vue'
import CanvasMinimap from '@/components/infinite-canvas/CanvasMinimap.vue'
import CanvasRightPanel from '@/components/infinite-canvas/CanvasRightPanel.vue'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const store = useCanvasStore()
const contextMenuRef = ref(null)
const infiniteCanvasRef = ref(null)
const importInputRef = ref(null)

/** 右键菜单处理 */
function handleContextMenu(e) {
  const target = e.target

  // 检查是否点击了面板
  const panelEl = target.closest('[data-canvas-target="panel"]')
  if (panelEl) {
    contextMenuRef.value?.show(e, {
      target: 'panel',
      data: { panelId: panelEl.getAttribute('data-panel-id') },
    })
    return
  }

  // 检查是否点击了连线（SVG path）
  if (target.classList.contains('connection-path')) {
    const connGroup = target.closest('.connection-group')
    const connId = connGroup?.dataset?.connId
    contextMenuRef.value?.show(e, {
      target: 'connection',
      data: { connectionId: connId },
    })
    return
  }

  // 背景右键
  contextMenuRef.value?.show(e, { target: 'background' })
}

/** 全局点击关闭菜单 */
function handleClick() {
  contextMenuRef.value?.hide()
}

/** 全局快捷键处理 */
function handleKeydown(e) {
  // 忽略在表单元素中的按键
  const tag = (e.target?.tagName || '').toLowerCase()
  if (['input', 'textarea', 'select'].includes(tag) || e.target?.isContentEditable) {
    return
  }

  const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0
  const mod = isMac ? e.metaKey : e.ctrlKey

  // Space 键：临时进入平移模式（按下时显示抓手指针，可拖动画布）
  if (e.code === 'Space' && !e.repeat) {
    e.preventDefault()
    store._isSpacePressed = true
    return
  }

  // Escape：关闭右键菜单 + 取消选中
  if (e.key === 'Escape') {
    contextMenuRef.value?.hide()
    store.selectedPanelId = null
    store.selectedConnectionId = null
    return
  }

  // Delete / Backspace：删除选中的面板或连线
  if (e.key === 'Delete' || e.key === 'Backspace') {
    if (store.selectedPanelId) {
      e.preventDefault()
      store.deletePanel(store.selectedPanelId)
    } else if (store.selectedConnectionId) {
      e.preventDefault()
      store.deleteConnection(store.selectedConnectionId)
    }
    return
  }

  // Ctrl+Z / Cmd+Z：撤销
  if (e.key === 'z' && mod && !e.shiftKey) {
    e.preventDefault()
    store.undo()
    return
  }

  // Ctrl+Shift+Z / Cmd+Shift+Z：重做
  if (e.key === 'z' && mod && e.shiftKey) {
    e.preventDefault()
    store.redo()
    return
  }

  // Ctrl+D / Cmd+D：复制选中面板
  if (e.key === 'd' && mod) {
    e.preventDefault()
    if (store.selectedPanelId) {
      store.duplicatePanel(store.selectedPanelId)
    }
    return
  }

  // Ctrl+A / Cmd+A：全选面板（选中第一个）
  if (e.key === 'a' && mod && !store._connecting) {
    e.preventDefault()
    if (store.panels.length > 0) {
      store.selectPanel(store.panels[0].id)
    }
    return
  }

  // Ctrl+S / Cmd+S：导出当前画布为 JSON（防止浏览器默认保存网页）
  if (e.key === 's' && mod) {
    e.preventDefault()
    handleExportJson()
    return
  }

  // 方向键：微调面板位置
  const nudgeAmount = e.shiftKey ? 10 : 1
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key) && store.selectedPanelId) {
    e.preventDefault()
    const panel = store.panels.find((p) => p.id === store.selectedPanelId)
    if (!panel) return

    let dx = 0, dy = 0
    if (e.key === 'ArrowUp') dy = -nudgeAmount
    else if (e.key === 'ArrowDown') dy = nudgeAmount
    else if (e.key === 'ArrowLeft') dx = -nudgeAmount
    else if (e.key === 'ArrowRight') dx = nudgeAmount

    store.updatePanel(panel.id, { x: panel.x + dx, y: panel.y + dy })
  }
}

/** 全局按键释放处理（用于 Space 键松开） */
function handleKeyup(e) {
  if (e.code === 'Space') {
    store._isSpacePressed = false
  }
}

/** 导出当前画布为 JSON 文件下载 */
function handleExportJson() {
  if (store.panels.length === 0 && store.connections.length === 0) {
    ElMessage.warning('画布为空，无需导出')
    return
  }
  const json = store.exportJSON()
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  const wsName = store.activeWorkspace?.name || 'canvas'
  a.href = url
  a.download = `${wsName}-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  ElMessage.success(t('canvas.exportSuccess'))
}

/** 触发文件选择对话框 */
function triggerImport() {
  importInputRef.value?.click()
}

/** 处理选择的 JSON 文件 */
function handleImportFile(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (ev) => {
    try {
      const result = store.importJSON(ev.target.result)
      ElMessage.success(
        t('canvas.importSuccess', { n: result.panels, m: result.connections }),
      )
    } catch (err) {
      ElMessage.error(t('canvas.importFailed', { msg: err.message }))
    }
  }
  reader.onerror = () => {
    ElMessage.error(t('canvas.importFailed', { msg: '文件读取失败' }))
  }
  reader.readAsText(file)
  // 清空 input.value 允许同名文件重复选择
  e.target.value = ''
}

onMounted(() => {
  document.title = `${t('router.canvas')} · Agnes AI Platform`
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('keyup', handleKeyup)
  // 点击其他地方关闭右键菜单
  window.addEventListener('click', handleClick)
})

onUnmounted(() => {
  document.title = 'Agnes AI Platform'
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('keyup', handleKeyup)
  window.removeEventListener('click', handleClick)
  // 离开时清掉 Space 状态
  store._isSpacePressed = false
})
</script>

<style scoped>
.canvas-view {
  display: flex;
  height: calc(100vh - 76px); /* 减去顶部栏高度 */
  background: linear-gradient(135deg, #0b0f1a 0%, #101827 50%, #0b0f1a 100%);
  overflow: hidden;
}

.canvas-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
</style>
