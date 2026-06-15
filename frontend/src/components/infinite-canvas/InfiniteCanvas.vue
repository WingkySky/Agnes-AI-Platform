/* =====================================================
 * 无限画布容器
 * - Pointer Events 处理（背景平移、滚轮缩放）
 * - 交互模型：
 *    · select 模式：点击空白处取消选中（不平移）
 *    · pan 模式 / Space 键 + 拖动：平移画布
 *    · 拖动面板时画布绝对不动
 *    · 滚轮始终缩放，不再平移
 * ===================================================== */

<template>
  <div
    ref="canvasRef"
    class="infinite-canvas"
    :class="{
      'connecting-mode': store.mouseMode === 'connect',
      'pan-mode': shouldPan,
      'space-panning': store._isSpacePressed,
    }"
    @pointerdown="handlePointerDown"
    @pointermove="handlePointerMove"
    @pointerup="handlePointerUp"
    @pointercancel="handlePointerUp"
    @wheel="handleWheel"
  >
    <CanvasGrid />
    <CanvasViewport>
      <CanvasConnectionsSvg />
      <CanvasPanels />
    </CanvasViewport>
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'
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
let panStartViewport = { x: 0, y: 0 }
let panningPointerId = null

/** 是否应该平移：pan 模式 或 Space 键按下 */
const shouldPan = computed(() => store.mouseMode === 'pan' || store._isSpacePressed)

/** 节流更新视口（用于 60fps 渲染优化） */
function scheduleRender() {
  if (rafId) return
  rafId = requestAnimationFrame(() => {
    rafId = null
  })
}

/** 指针按下 */
function handlePointerDown(e) {
  // 只处理左键
  if (e.button !== 0) return

  // 1) 正在拖动面板：画布绝对不平移
  if (store._isDraggingPanel) return

  // 2) 判断事件目标
  const target = e.target
  const closestPanel = target?.closest?.('[data-canvas-target="panel"]')
  const closestAnchor = target?.closest?.('[data-canvas-target="anchor"]')
  const closestControl = target?.closest?.('[data-canvas-target="control"]')

  // 3) 命中面板/锚点/控件 → 让子组件自己处理（不启动画布平移）
  if (closestPanel || closestAnchor || closestControl) return

  // 4) connect 模式下空白处不做任何事（避免误平移）
  if (store.mouseMode === 'connect') {
    // connect 模式点空白处可以取消连线（如果有）
    if (store._connecting) store.cancelConnecting()
    return
  }

  // 5) select 模式下点空白处：取消选中（不平移画布）
  if (store.mouseMode === 'select' && !store._isSpacePressed) {
    store.selectedPanelId = null
    store.selectedConnectionId = null
    return
  }

  // 6) pan 模式 或 Space 键按下 → 平移画布
  if (shouldPan.value) {
    startPan(e)
  }
}

function startPan(e) {
  isPanning = true
  panningPointerId = e.pointerId
  panStart = { x: e.clientX, y: e.clientY }
  panStartViewport = { ...store.viewport }
  canvasRef.value?.setPointerCapture(e.pointerId)
  scheduleRender()
}

/** 指针移动 */
function handlePointerMove(e) {
  // 正在拖动面板：画布绝对不平移
  if (store._isDraggingPanel) return

  // 不在平移状态：直接返回
  if (!isPanning) return

  const dx = e.clientX - panStart.x
  const dy = e.clientY - panStart.y
  // 修复：基于起始视口增量计算，避免连续平移累积误差
  store.viewport.x = panStartViewport.x + dx
  store.viewport.y = panStartViewport.y + dy
  scheduleRender()
}

/** 指针释放 */
function handlePointerUp(e) {
  if (isPanning && panningPointerId !== null) {
    try {
      canvasRef.value?.releasePointerCapture(panningPointerId)
    } catch {
      // 已经被 release 了
    }
  }
  isPanning = false
  panningPointerId = null
}

/** 滚轮：始终缩放（不再平移，符合用户期望的"画布不动"） */
function handleWheel(e) {
  // 阻止页面滚动
  e.preventDefault()

  // 当前指针位置（用于以指针为中心缩放）
  const rect = canvasRef.value?.getBoundingClientRect()
  const center = rect
    ? { x: e.clientX - rect.left, y: e.clientY - rect.top }
    : { x: e.clientX, y: e.clientY }

  // 缩放因子：向上滚动放大，向下缩小
  // 加速度根据 deltaY 大小调整
  const intensity = Math.min(Math.abs(e.deltaY) / 100, 2)
  const factor = e.deltaY < 0 ? (1 + 0.1 * intensity) : (1 / (1 + 0.1 * intensity))

  store.zoom(factor, center)
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
  cursor: default;
  user-select: none;
  touch-action: none; /* 防止触屏滚动干扰 */
}

/* 选中态面板被 hover/操作时不变光标 */
.infinite-canvas:not(.pan-mode):not(.space-panning) {
  cursor: default;
}

/* 平移模式 / Space 键按下时显示抓手指针 */
.infinite-canvas.pan-mode,
.infinite-canvas.space-panning {
  cursor: grab;
}

.infinite-canvas.pan-mode:active,
.infinite-canvas.space-panning:active {
  cursor: grabbing;
}
</style>
