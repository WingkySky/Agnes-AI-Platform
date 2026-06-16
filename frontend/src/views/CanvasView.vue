<!-- =====================================================
     无限画布页面
     - 左侧栏：多画布管理
     - 中间：无限画布主体
     - 顶部：工具栏（含导入/导出按钮、搜索/筛选）
     - 右侧：选中面板/连线的属性编辑面板
     - 全局快捷键处理器（含 / 聚焦搜索框）
     - 右键上下文菜单
     - Minimap 小地图
     ===================================================== -->

<template>
  <div class="canvas-view" :data-theme="store.themeMode" @contextmenu.prevent="handleContextMenu">
    <!-- 左侧栏 -->
    <CanvasSidebar />

    <!-- 主内容区 -->
    <div class="canvas-main">
      <!-- 顶部工具栏（暴露 ref 以便全局 / 快捷键聚焦搜索框） -->
      <CanvasToolbar
        ref="canvasToolbarRef"
        @export-json="handleExportJson"
        @import-json="triggerImport"
      />

      <!-- 无限画布 -->
      <InfiniteCanvas ref="infiniteCanvasRef" @panel-edit="handlePanelEdit" />

      <!-- Minimap 小地图 -->
      <CanvasMinimap />
    </div>

    <!-- 右侧属性面板 -->
    <CanvasRightPanel />

    <!-- 右键菜单 -->
    <CanvasContextMenu ref="contextMenuRef" />

    <!-- 拖线到空白弹出的"创建新节点"菜单 -->
    <ConnectionCreateMenu />

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
import ConnectionCreateMenu from '@/components/infinite-canvas/ConnectionCreateMenu.vue'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const store = useCanvasStore()
const contextMenuRef = ref(null)
const infiniteCanvasRef = ref(null)
const importInputRef = ref(null)
const canvasToolbarRef = ref(null)

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

  // / 键：聚焦工具栏搜索框（任务 3 节点搜索）
  // - 不与现有 Ctrl/Cmd + 字母组合冲突
  // - 表单元素中的 / 已被前置 guard 拦截
  if (e.key === '/') {
    e.preventDefault()
    canvasToolbarRef.value?.focusSearch?.()
    return
  }

  // Escape：关闭右键菜单 + 取消选中；优先退出 Frame 内部模式
  if (e.key === 'Escape') {
    contextMenuRef.value?.hide()
    // 优先退出 Frame 内部模式（双击进入后用 Esc 返回上级）
    if (store.enteredFrameId) {
      store.exitFrame()
      return
    }
    // 关闭拖线空白处弹出的"创建新节点"菜单
    if (store.pendingConnectionCreate) {
      store.clearPendingConnectionCreate()
      return
    }
    store.clearSelection()
    return
  }

  // Delete / Backspace：删除选中的面板（多选支持）或连线；锁定节点会被过滤
  if (e.key === 'Delete' || e.key === 'Backspace') {
    if (store.selectedPanelIds.length > 0) {
      e.preventDefault()
      // 过滤掉 locked 节点，避免误删
      const deletableIds = store.selectedPanelIds.filter(
        (id) => !store.panels.find((p) => p.id === id)?.content?.locked
      )
      if (deletableIds.length === 0) {
        ElMessage.warning(t('canvas.lockedHint'))
        return
      }
      // 重新设置选中集合为可删除的，再触发删除
      store.selectedPanelIds = deletableIds
      store.selectedPanelId = deletableIds[0] ?? null
      store.deleteSelectedPanels()
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

  // Ctrl+D / Cmd+D：复制选中面板（多选支持）
  if (e.key === 'd' && mod) {
    if (store.selectedPanelIds.length > 0) {
      e.preventDefault()
      store.duplicateSelectedPanels()
    } else if (store.selectedPanelId) {
      // 兼容旧单选
      e.preventDefault()
      store.duplicatePanel(store.selectedPanelId)
    }
    return
  }

  // Ctrl+A / Cmd+A：全选所有面板（多选）
  if (e.key === 'a' && mod && !store._connecting) {
    e.preventDefault()
    if (store.panels.length > 0) {
      // 用无限矩形一次性框选全部面板
      store.selectPanelsInRect({
        startWorld: { x: -Infinity, y: -Infinity },
        endWorld: { x: Infinity, y: Infinity },
      })
    }
    return
  }

  // Ctrl+L / Cmd+L：切换当前选中节点的锁定状态（仅支持单选）
  if (e.key === 'l' && mod && !e.shiftKey && !e.altKey) {
    e.preventDefault()
    if (store.selectedPanelIds.length === 1) {
      store.toggleLock(store.selectedPanelIds[0])
    } else if (store.selectedPanelIds.length > 1) {
      ElMessage.info(t('canvas.lockMultiSelectHint'))
    }
    return
  }

  // Ctrl+S / Cmd+S：导出当前画布为 JSON（防止浏览器默认保存网页）
  if (e.key === 's' && mod) {
    e.preventDefault()
    handleExportJson()
    return
  }

  // 方向键：微调选中面板位置（多选支持，只压一次快照）
  const nudgeAmount = e.shiftKey ? 10 : 1
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key) && store.selectedPanelIds.length > 0) {
    e.preventDefault()

    let dx = 0, dy = 0
    if (e.key === 'ArrowUp') dy = -nudgeAmount
    else if (e.key === 'ArrowDown') dy = nudgeAmount
    else if (e.key === 'ArrowLeft') dx = -nudgeAmount
    else if (e.key === 'ArrowRight') dx = nudgeAmount

    // 一次 pushSnapshot：多选微调视为一次操作
    store.pushSnapshot()
    const ids = [...store.selectedPanelIds]
    for (const id of ids) {
      const panel = store.panels.find((p) => p.id === id)
      if (!panel) continue
      store._updatePanelDirect(id, {
        x: panel.x + dx,
        y: panel.y + dy,
      })
    }
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

/** 处理面板编辑事件（来自 NodeHoverToolbar 的 edit 动作）
 *  - 暂用 ElMessage.info 提示"该功能待接入"（占位）
 *  - 后续会接入具体编辑弹窗（图片/视频/文本/URL 等） */
function handlePanelEdit(panel) {
  ElMessage.info(t('canvas.pendingFeature'))
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
  // Task 5: 异步从 localforage 恢复完整画布状态（panels / connections / viewport）
  // - 仅触发一次，store 内部有 _storageReady 幂等保护
  // - fire-and-forget：hydrate 是异步后台任务，不阻塞 onMounted
  store._hydrateFromStorage()
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
  background: var(--canvas-bg);
  overflow: hidden;

  /* 深色主题 token 映射（默认值） */
  &[data-theme="dark"] {
    --canvas-bg: linear-gradient(135deg, #0b0f1a 0%, #101827 50%, #0b0f1a 100%);
    --canvas-panel-bg: rgba(22, 32, 54, 0.7);
    --canvas-grid-dot: rgba(245, 245, 244, 0.24);
    --canvas-grid-line: rgba(245, 245, 244, 0.10);
    --canvas-node-border: rgba(120, 170, 230, 0.2);
    --canvas-node-active-border: #85b2ff;
    --canvas-node-glow: rgba(100, 150, 255, 0.35);
    --canvas-node-title-text: #ffffff;
    --canvas-node-muted-text: #8ba3c9;
    --canvas-connection-active: rgba(80, 140, 255, 0.6);
    --canvas-connection-muted: rgba(150, 150, 180, 0.3);
    --canvas-anchor-fill: #6b9cff;
    --canvas-anchor-input: #6b9cff;
    --canvas-anchor-output: #a78bff;
    --canvas-selection-fill: rgba(100, 150, 255, 0.15);
    --canvas-selection-stroke: #6b9cff;
  }

  /* 浅色主题 token 映射 */
  &[data-theme="light"] {
    --canvas-bg: #f5f7fa;
    --canvas-panel-bg: rgba(255, 255, 255, 0.95);
    --canvas-grid-dot: rgba(68, 64, 60, 0.28);
    --canvas-grid-line: rgba(68, 64, 60, 0.12);
    --canvas-node-border: rgba(0, 0, 0, 0.1);
    --canvas-node-active-border: #1d4ed8;
    --canvas-node-glow: rgba(37, 99, 235, 0.25);
    --canvas-node-title-text: #1f2937;
    --canvas-node-muted-text: #6b7280;
    --canvas-connection-active: #2563eb;
    --canvas-connection-muted: rgba(120, 113, 108, 0.5);
    --canvas-anchor-fill: #1d4ed8;
    --canvas-anchor-input: #1d4ed8;
    --canvas-anchor-output: #7c3aed;
    --canvas-selection-fill: rgba(37, 99, 235, 0.1);
    --canvas-selection-stroke: #2563eb;
  }
}

.canvas-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
</style>
