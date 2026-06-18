<!-- =====================================================
     无限画布主组件
     - 负责视口平移 / 缩放交互（滚轮缩放，Space + 拖动或空白拖动平移）
     - 负责 Ctrl/Cmd + 拖动框选（世界坐标矩形写入 store.selectionBox）
     - 组装背景网格（CanvasGrid）、变换容器（CanvasViewport）、
       面板容器（CanvasPanels）、连线 SVG（CanvasConnectionsSvg）、
       框选矩形（SelectionBox）
     - 事件命中检测：pointerdown 在面板 / 连线 / 锚点上时不触发画布平移/框选
     - 空格键按下时整个容器切换为"平移优先"光标（grab / grabbing）
     ===================================================== -->

<template>
  <!-- 画布容器：fill parent，作为滚轮/指针事件的根节点
       - tabindex 允许接收键盘聚焦，但真正快捷键由全局 keydown 处理
       - data-canvas-root 作为 CSS 选择器供事件委托使用 -->
  <div
    ref="rootRef"
    class="infinite-canvas"
    :class="{
      'is-space-pressed': store._isSpacePressed,
      'is-panning': isPanning,
    }"
    @contextmenu.prevent="handleContextMenu"
    @wheel.prevent="handleWheel"
    @pointerdown="handlePointerDown"
    @pointermove="handlePointerMove"
    @pointerup="handlePointerUp"
    @pointercancel="handlePointerUp"
  >
    <!-- 背景网格（屏幕坐标系，不跟随 transform，由自身样式响应 viewport 变化） -->
    <CanvasGrid />

    <!-- 变换容器：子节点全部位于世界坐标系，由 viewport 的 translate+scale 统一变换 -->
    <CanvasViewport>
      <!-- 连线层：必须放在面板层之前（z-index 更低），避免遮挡节点交互 -->
      <CanvasConnectionsSvg />

      <!-- 面板容器：按 zIndex 排序渲染可见面板 -->
      <CanvasPanels
        @panel-edit="(panel) => emit('panel-edit', panel)"
        @panel-action="(payload) => emit('panel-action', payload)"
      />
    </CanvasViewport>

    <!-- 框选矩形（屏幕坐标，跟随 store.selectionBox） -->
    <SelectionBox
      :box="store.selectionBox"
      :zoom="store.viewport.zoom"
      :viewport="{ x: store.viewport.x, y: store.viewport.y }"
    />
  </div>
</template>

<script setup>
import { ref, onBeforeUnmount } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import CanvasGrid from '@/components/infinite-canvas/CanvasGrid.vue'
import CanvasViewport from '@/components/infinite-canvas/CanvasViewport.vue'
import CanvasPanels from '@/components/infinite-canvas/CanvasPanels.vue'
import CanvasConnectionsSvg from '@/components/infinite-canvas/CanvasConnectionsSvg.vue'
import SelectionBox from '@/components/infinite-canvas/SelectionBox.vue'

// ===== 模块依赖 =====
const store = useCanvasStore()
const rootRef = ref(null)

// emit 声明：对外向上抛出 panel-edit（由 CanvasPanels → PanelWrapper → BaseNode 逐层抛出）
const emit = defineEmits(['panel-edit', 'panel-action'])

// ===== 交互状态 =====
// 平移状态：{ active, startX, startY, initX, initY }，只存在于本次 pointer 序列内
const panState = ref(null)
// 是否正在平移中（用于 CSS 切换 grabbing 光标）
const isPanning = ref(false)
// 框选状态：{ active, startScreenX, startScreenY }
const selectionState = ref(null)

/** 计算 pointerdown 时命中的元素类型，用于决定是否触发画布级操作 */
function hitCanvasBackground(event) {
  const target = event.target
  if (!(target instanceof Element)) return false
  // 如果命中节点/连线/锚点/工具栏/浮层，则不是"画布背景"
  if (target.closest('[data-canvas-target="panel"]')) return false
  if (target.closest('.connection-group')) return false
  if (target.closest('[data-anchor]')) return false
  if (target.closest('.connection-create-menu')) return false
  return true
}

/** 滚轮缩放：以鼠标位置为中心；按住 Ctrl/Cmd 微调缩放速度 */
function handleWheel(event) {
  // 命中节点输入内容时不缩放（虽然 preventDefault 会阻止滚动，但为了安全仍做判断）
  const target = event.target
  if (target && target.closest('[data-canvas-no-zoom]')) return

  const factor = Math.pow(1.0015, -event.deltaY)
  // 以鼠标相对画布容器的位置为缩放中心
  const rect = rootRef.value?.getBoundingClientRect()
  if (!rect) return
  const centerX = event.clientX - rect.left
  const centerY = event.clientY - rect.top
  store.zoom(factor, { x: centerX, y: centerY })
}

/** 指针按下：区分"平移 / 框选 / 普通点击" */
function handlePointerDown(event) {
  // 只处理主按钮（左键）或中键
  const isMiddle = event.button === 1
  const isLeft = event.button === 0
  if (!isLeft && !isMiddle) return

  const target = event.target
  const isBackground = hitCanvasBackground(event)

  // Ctrl/Cmd + 左键 + 背景命中：框选模式
  if (isLeft && (event.ctrlKey || event.metaKey) && isBackground) {
    selectionState.value = {
      startScreenX: event.clientX,
      startScreenY: event.clientY,
    }
    // 尝试捕获指针，避免拖到浏览器外部时丢失 move/up
    try { rootRef.value?.setPointerCapture(event.pointerId) } catch { /* noop */ }
    return
  }

  // 中键 或 (空格按下且左键且背景)：进入平移
  const spacePan = isLeft && store._isSpacePressed && isBackground
  const bgPan = isLeft && isBackground
  if (isMiddle || spacePan || bgPan) {
    panState.value = {
      startX: event.clientX,
      startY: event.clientY,
      initX: store.viewport.x,
      initY: store.viewport.y,
    }
    isPanning.value = true
    try { rootRef.value?.setPointerCapture(event.pointerId) } catch { /* noop */ }
    return
  }

  // 命中背景 + 普通左键：清空当前选中（已由 CanvasPanels/BaseNode 处理节点选中，
  // 这里只负责"点到空白 → 取消选中"）
  if (isLeft && isBackground) {
    // 如果之前有选中节点/连线，则清空；否则什么都不做，允许继续传递事件
    if (store.selectedPanelIds.length > 0 || store.selectedConnectionId) {
      store.clearSelection()
    }
  }
}

/** 指针移动：根据当前状态（平移 / 框选）执行对应更新 */
function handlePointerMove(event) {
  // 平移进行中
  if (panState.value) {
    const dx = event.clientX - panState.value.startX
    const dy = event.clientY - panState.value.startY
    // viewport.x/y 直接是屏幕偏移量（像素），不需要除 zoom
    store.viewport.x = panState.value.initX + dx
    store.viewport.y = panState.value.initY + dy
    return
  }

  // 框选进行中：屏幕坐标 → 世界坐标，写入 store.selectionBox
  if (selectionState.value) {
    const rect = rootRef.value?.getBoundingClientRect()
    if (!rect) return
    const sx = selectionState.value.startScreenX - rect.left
    const sy = selectionState.value.startScreenY - rect.top
    const ex = event.clientX - rect.left
    const ey = event.clientY - rect.top
    // 屏幕坐标 → 世界坐标：(x - viewport.x) / zoom
    const z = store.viewport.zoom
    const startWorld = { x: (sx - store.viewport.x) / z, y: (sy - store.viewport.y) / z }
    const endWorld = { x: (ex - store.viewport.x) / z, y: (ey - store.viewport.y) / z }
    store.setSelectionBox({ startWorld, endWorld })
    return
  }
}

/** 指针松开：结束平移/框选，并在框选时触发 selectPanelsInRect */
function handlePointerUp(event) {
  // 结束平移
  if (panState.value) {
    panState.value = null
    isPanning.value = false
    try { rootRef.value?.releasePointerCapture(event.pointerId) } catch { /* noop */ }
    return
  }

  // 结束框选：用当前 selectionBox 触发选中（追加模式由 Shift 控制）
  if (selectionState.value) {
    const box = store.selectionBox
    selectionState.value = null
    try { rootRef.value?.releasePointerCapture(event.pointerId) } catch { /* noop */ }
    if (box) {
      // Shift：与已有选中叠加；否则替换
      const append = event.shiftKey
      store.selectPanelsInRect(box, { append })
      store.clearSelectionBox()
    }
    return
  }
}

/** 画布上右键（被 @contextmenu.prevent 拦截） → 抛给上层 CanvasView 统一处理 */
function handleContextMenu(event) {
  // 此处不直接打开菜单，由上层 CanvasView 监听全局 contextmenu 事件来处理
  // 保留钩子以便未来做"画布级"右键菜单项
  return false
}

onBeforeUnmount(() => {
  // 组件卸载时清理交互状态
  panState.value = null
  selectionState.value = null
  isPanning.value = false
})
</script>

<style scoped>
.infinite-canvas {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  /* 默认光标：指针；平移时切换为 grab */
  cursor: default;
  /* 避免文本选中影响拖动体验 */
  user-select: none;
  -webkit-user-select: none;
  /* 触摸设备：允许非被动的滚轮处理（禁止滚动页面） */
  touch-action: none;
}

/* 空格键按下：整画布显示 grab 光标，提示用户可以拖动画布 */
.infinite-canvas.is-space-pressed {
  cursor: grab;
}

/* 平移中：显示 grabbing 光标 */
.infinite-canvas.is-panning {
  cursor: grabbing;
}

/* 正在框选时：显示 crosshair（这里在 selectionState 存在时由 pointerdown 已决定，
   因此这里不用额外 class；保留以防未来需要） */
</style>
