/* =====================================================
 * 无限画布容器
 * - Pointer Events 处理（背景平移）
 * - Wheel 事件处理（缩放）
 * - 坐标转换、requestAnimationFrame 节流
 * ===================================================== */

<template>
  <div
    ref="canvasRef"
    class="infinite-canvas"
    @pointerdown="handlePointerDown"
    @pointermove="handlePointerMove"
    @pointerup="handlePointerUp"
    @wheel="handleWheel"
    @pointermove.self="onGlobalPointerMove"
  >
    <CanvasGrid />
    <CanvasViewport>
      <CanvasConnectionsSvg />
      <CanvasPanels />
    </CanvasViewport>
  </div>
</template>

<script setup>
import { ref, onBeforeUnmount } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import CanvasGrid from '@/components/infinite-canvas/CanvasGrid.vue'
import CanvasViewport from '@/components/infinite-canvas/CanvasViewport.vue'
import CanvasConnectionsSvg from '@/components/infinite-canvas/CanvasConnectionsSvg.vue'
import CanvasPanels from '@/components/infinite-canvas/CanvasPanels.vue'

const store = useCanvasStore()
const canvasRef = ref(null)
let rafId = null
let isPanning = false
let panStart = { x: 0, y: 0 }
let viewportStart = { x: 0, y: 0 }

/** 节流更新视口 */
function throttleViewportUpdate() {
  if (rafId) return
  rafId = requestAnimationFrame(() => {
    rafId = null
  })
}

/** 指针按下：判断是平移背景还是其他操作 */
function handlePointerDown(e) {
  // 只处理左键
  if (e.button !== 0) return

  const target = e.target

  // 如果点击的是面板/锚点/控件，不处理背景平移
  if (
    target.dataset.canvasTarget === 'panel' ||
    target.dataset.canvasTarget === 'anchor' ||
    target.dataset.canvasTarget === 'control'
  ) {
    return
  }

  // 开始平移
  isPanning = true
  panStart = { x: e.clientX, y: e.clientY }
  viewportStart = { ...store.viewport }

  // 捕获指针
  canvasRef.value?.setPointerCapture(e.pointerId)
}

/** 指针移动 */
function handlePointerMove(e) {
  if (!isPanning) return

  const dx = e.clientX - panStart.x
  const dy = e.clientY - panStart.y
  store.pan(dx, dy)
  throttleViewportUpdate()
}

/** 指针释放 */
function handlePointerUp() {
  isPanning = false
}

/** 缩放处理：以鼠标位置为中心 */
function handleWheel(e) {
  if (e.ctrlKey || e.metaKey) {
    // Ctrl/Cmd + 滚轮：缩放
    e.preventDefault()
    const factor = e.deltaY < 0 ? 1.1 : 0.9
    store.zoom(factor, { x: e.clientX, y: e.clientY })
    return
  }

  // 仅滚轮：平移（纵向）
  const dy = e.deltaY / store.viewport.zoom
  store.pan(0, -dy)
}

onBeforeUnmount(() => {
  if (rafId) cancelAnimationFrame(rafId)
})
</script>

<style scoped>
.infinite-canvas {
  flex: 1;
  position: relative;
  overflow: hidden;
  cursor: grab;
  user-select: none;
}

.infinite-canvas:active {
  cursor: grabbing;
}
</style>
