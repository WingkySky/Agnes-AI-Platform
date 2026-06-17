/* =====================================================
 * 无限画布容器
 * - Pointer Events 处理（背景平移、滚轮缩放）
 * - 交互模型（统一交互，无模式切换）：
 *    · 单击空白处取消选中；按住拖动空白处平移画布
 *    · Space 键 + 拖动：平移画布
 *    · 拖动面板时画布绝对不动
 *    · 滚轮始终缩放，不再平移
 *    · Ctrl/Cmd + 拖动空白处：进入框选模式（多选）
 *    · 锚点在 hover/选中时显示，从锚点拖出即可连线
 * - 任务 4：HTML5 拖放支持
 *    · 监听根节点 dragover / drop
 *    · 解析 PromptLibraryDrawer / AssetPickerDrawer 拖入的数据
 *    · 在 drop 落点的世界坐标创建文本/图片节点
 * ===================================================== */

<template>
  <div
    ref="canvasRef"
    class="infinite-canvas"
    :class="{
      'space-panning': store._isSpacePressed,
      'marquee-active': marqueeStart !== null,
    }"
    @pointerdown="handlePointerDown"
    @pointermove="handlePointerMove"
    @pointerup="handlePointerUp"
    @pointercancel="handlePointerUp"
    @wheel="handleWheel"
    @dragover.prevent="handleDragOver"
    @drop="handleDrop"
  >
    <CanvasGrid />
    <CanvasViewport>
      <CanvasConnectionsSvg />
      <CanvasPanels @panel-edit="(p) => emit('panel-edit', p)" />
    </CanvasViewport>
    <!-- 框选矩形：Ctrl/Cmd + 拖动时显示在画布最上层 -->
    <SelectionBox
      :box="store.selectionBox"
      :zoom="store.viewport.zoom"
      :viewport="store.viewport"
    />
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import CanvasGrid from '@/components/infinite-canvas/CanvasGrid.vue'
import CanvasViewport from '@/components/infinite-canvas/CanvasViewport.vue'
import CanvasConnectionsSvg from '@/components/infinite-canvas/CanvasConnectionsSvg.vue'
import CanvasPanels from '@/components/infinite-canvas/CanvasPanels.vue'
import SelectionBox from '@/components/infinite-canvas/SelectionBox.vue'

const store = useCanvasStore()
const canvasRef = ref(null)
let rafId = null
let isPanning = false
let panStart = { x: 0, y: 0 }
let panStartViewport = { x: 0, y: 0 }
let panningPointerId = null
// 框选起点（世界坐标）；非 null 表示处于框选状态
let marqueeStart = null

// select 模式下记录"按下空白处"的起点
// 仅在未按住 Space、且命中空白时记录
// 用于区分"单击空白（取消选中）"与"按住拖动空白（平移）"
let selectDownAt = null  // { x, y } 屏幕坐标

/** 是否应该平移：Space 键按下时 */
const shouldPan = computed(() => store._isSpacePressed)

/** 节流更新视口（用于 60fps 渲染优化） */
function scheduleRender() {
  if (rafId) return
  rafId = requestAnimationFrame(() => {
    rafId = null
  })
}

/** 启动平移（Space 键 / select 拖动到位） */
function startPan(e) {
  isPanning = true
  panningPointerId = e.pointerId
  panStart = { x: e.clientX, y: e.clientY }
  panStartViewport = { ...store.viewport }
  canvasRef.value?.setPointerCapture(e.pointerId)
  scheduleRender()
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

  // 3) Ctrl/Cmd + 空白处按下 → 进入框选模式（不响应平移、不取消选中）
  const isMarquee = (e.ctrlKey || e.metaKey) && !closestPanel && !closestAnchor && !closestControl
  if (isMarquee) {
    marqueeStart = store.screenToWorld(e.clientX, e.clientY)
    // 把指针捕获到画布上，确保后续 move/up 不被其他元素抢走
    try {
      canvasRef.value?.setPointerCapture(e.pointerId)
    } catch {
      // ignore
    }
    return
  }

  // 4) 命中面板/锚点/控件 → 让子组件自己处理（不启动画布平移）
  if (closestPanel || closestAnchor || closestControl) return

  // 5) 未按 Space 时点空白处：先记录起点，等 pointermove 决定是单击还是拖动
  if (!store._isSpacePressed) {
    selectDownAt = { x: e.clientX, y: e.clientY }
    // 不立即 return，让后续 pointermove 监听位移动作
    return
  }

  // 6) Space 键按下 → 直接平移画布
  if (shouldPan.value) {
    startPan(e)
  }
}

/** 指针移动 */
function handlePointerMove(e) {
  // 正在拖动面板：画布绝对不平移
  if (store._isDraggingPanel) return

  // 0) 框选状态：更新框选矩形（世界坐标）
  if (marqueeStart) {
    const endWorld = store.screenToWorld(e.clientX, e.clientY)
    store.setSelectionBox({ startWorld: marqueeStart, endWorld })
    scheduleRender()
    return
  }

  // 1) select 模式拖动空白处：位移超过 4px 阈值就升级为平移
  if (selectDownAt && !isPanning) {
    const dx = e.clientX - selectDownAt.x
    const dy = e.clientY - selectDownAt.y
    if (dx * dx + dy * dy >= 16) {  // 4px 平方阈值
      isPanning = true
      panningPointerId = e.pointerId
      panStart = { x: e.clientX, y: e.clientY }
      panStartViewport = { ...store.viewport }
      canvasRef.value?.setPointerCapture(e.pointerId)
      scheduleRender()
    }
    return
  }

  // 2) 不在平移状态：直接返回
  if (!isPanning) return

  // 3) 处于平移状态：更新视口
  const dx = e.clientX - panStart.x
  const dy = e.clientY - panStart.y
  // 修复：基于起始视口增量计算，避免连续平移累积误差
  store.viewport.x = panStartViewport.x + dx
  store.viewport.y = panStartViewport.y + dy
  scheduleRender()
}

/** 指针释放 */
function handlePointerUp(e) {
  // 框选结束：把矩形内的面板加入选中
  if (marqueeStart) {
    const box = store.selectionBox
    if (box) {
      const dx = Math.abs(box.endWorld.x - box.startWorld.x)
      const dy = Math.abs(box.endWorld.y - box.startWorld.y)
      if (dx > 4 || dy > 4) {
        // 拖动距离够大 → 真正框选；Shift 追加
        const append = e.shiftKey
        store.selectPanelsInRect(box, { append })
      } else if (!e.shiftKey) {
        // 距离过短按单击处理：清空选中（Shift 单独按不视为取消）
        store.clearSelection()
      }
    }
    store.clearSelectionBox()
    try {
      canvasRef.value?.releasePointerCapture(e.pointerId)
    } catch {
      // 已经被 release 了
    }
    marqueeStart = null
    return
  }

  // select 模式下松开：若没进入平移则视为"单击空白 → 取消选中"
  if (selectDownAt) {
    if (!isPanning) {
      store.clearSelection()
    }
    selectDownAt = null
  }

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

/**
 * 拖动经过：声明允许 copy 效果，让浏览器显示可放置光标
 * （必须 preventDefault，否则 drop 不会触发）
 */
function handleDragOver(e) {
  if (e.dataTransfer) {
    e.dataTransfer.dropEffect = 'copy'
  }
}

/**
 * 处理 Drawer 拖入：在落点（世界坐标）创建对应类型的节点
 * - application/x-agnes-prompt → 文本面板（text）
 * - application/x-agnes-asset  → 图片面板（image）
 * - 未知类型：交给浏览器默认行为（不破坏现有拖文件逻辑）
 */
function handleDrop(e) {
  if (!e.dataTransfer) return

  const promptRaw = e.dataTransfer.getData('application/x-agnes-prompt')
  const assetRaw = e.dataTransfer.getData('application/x-agnes-asset')

  // 只处理我们识别的数据；其他拖放（如桌面文件）不拦截
  if (!promptRaw && !assetRaw) return

  // 命中自定义数据：阻止默认行为，避免浏览器把内容当 URL 打开
  e.preventDefault()

  // 落点转世界坐标（用 clientX/Y 而不是 clientX/Y 减去 rect 偏移，
  // 因为 screenToWorld 内部按屏幕坐标换算）
  const world = store.screenToWorld(e.clientX, e.clientY)

  try {
    if (promptRaw) {
      const p = JSON.parse(promptRaw)
      store.addPanel({
        type: 'text',
        x: world.x - 150,
        y: world.y - 100,
        width: 300,
        height: 200,
        content: { text: p.content, name: p.name },
      })
    } else if (assetRaw) {
      const a = JSON.parse(assetRaw)
      store.addPanel({
        type: 'image',
        x: world.x - 200,
        y: world.y - 150,
        width: 400,
        height: 300,
        content: { imageUrl: a.url, name: a.name },
      })
    }
  } catch (err) {
    // 解析失败时静默忽略，不影响其他画布交互
    // eslint-disable-next-line no-console
    console.warn('[InfiniteCanvas] handleDrop 解析失败：', err)
  }
}

onBeforeUnmount(() => {
  if (rafId) cancelAnimationFrame(rafId)
})

// 把 CanvasPanels 的 panel-edit 事件继续向上抛，给 CanvasView 处理
const emit = defineEmits(['panel-edit'])
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
.infinite-canvas:not(.space-panning):not(.marquee-active) {
  cursor: default;
}

/* Space 键按下时显示抓手指针 */
.infinite-canvas.space-panning {
  cursor: grab;
}

.infinite-canvas.space-panning:active {
  cursor: grabbing;
}

/* 框选进行中：十字光标提示正在框选 */
.infinite-canvas.marquee-active {
  cursor: crosshair;
}
</style>
