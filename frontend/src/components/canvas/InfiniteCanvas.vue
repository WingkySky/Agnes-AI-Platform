<!-- =====================================================
     InfiniteCanvas 无限画布主体
     - 背景网格（dots / lines / blank 三种模式）
     - 视口变换（CSS transform: translate + scale）
     - 平移交互（Space 按住 / 中键拖 / 左键拖背景）
     - 缩放交互（滚轮缩放，以鼠标位置为中心，范围 0.05-5）
     - 提供 default slot 渲染节点层和连线层
     - 1:1 复刻参考项目 infinite-canvas 的交互与视觉设计
     ===================================================== -->

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import CanvasConnectionsLayer from './CanvasConnectionsLayer.vue'

// ---------- Props ----------
const props = defineProps({
  // 视口对象 { x, y, zoom }；不传则使用 store.viewport
  viewport: { type: Object, default: null },
  // 背景模式 'dots' | 'lines' | 'blank'；不传则映射 store.backgroundMode
  backgroundMode: { type: String, default: '' },
  // 主题 token 对象；不传则使用 store.canvasTheme
  theme: { type: Object, default: null },
  // 是否允许左键拖动平移画布；选择工具模式下应设为 false，由外部处理框选
  panEnabled: { type: Boolean, default: true },
})

// ---------- Emits ----------
const emit = defineEmits([
  'pan',              // 平移时触发，payload: { x, y, zoom }
  'zoom',             // 缩放时触发，payload: { x, y, zoom }
  'background-click', // 点击背景时触发（用于取消选中）
  'drop-asset',       // 从素材库拖拽素材到画布时触发，payload: { asset, worldX, worldY }
  // 以下为兼容 CanvasView 旧接口声明，本组件不主动触发
  'panel-edit',
  'panel-action',
])

const store = useCanvasStore()

// ---------- 容器引用 ----------
const containerRef = ref<HTMLElement | null>(null)

// ---------- 实际使用的视口（props 优先，回退到 store）----------
const currentViewport = computed(() => props.viewport || store.viewport)

// ---------- 实际使用的背景模式（props 优先，回退到 store.backgroundMode）----------
// store.backgroundMode 已是 'dots' | 'lines' | 'blank'，直接使用即可
const currentBackgroundMode = computed(() => {
  if (props.backgroundMode) return props.backgroundMode
  return store.backgroundMode || 'dots'
})

// ---------- 实际使用的主题（props 优先，回退到 store.canvasTheme）----------
const currentTheme = computed(() => props.theme || store.canvasTheme)

// ---------- 平移状态 ----------
const panState = reactive({
  isPanning: false,
  startX: 0,
  startY: 0,
  initialX: 0,
  initialY: 0,
  hasMoved: false,
})

// ---------- Space 按键状态 ----------
const isSpacePressed = ref(false)

// ---------- 应用视口变更（兼容 props 和 store 两种模式）----------
function applyViewport(newVp: { x: number; y: number; zoom: number }) {
  // 没传 props.viewport 时，直接更新 store（保持向后兼容）
  if (!props.viewport) {
    store.viewport.x = newVp.x
    store.viewport.y = newVp.y
    store.viewport.zoom = newVp.zoom
  }
}

// ---------- 滚轮缩放（以鼠标位置为中心，范围 0.05-5）----------
function handleWheel(event: WheelEvent) {
  // 始终阻止默认滚动行为
  event.preventDefault()

  // 跳过特定元素（弹窗、下拉等标记了 data-canvas-no-zoom 的元素）
  const target = event.target instanceof Element ? event.target : null
  if (target?.closest?.('[data-canvas-no-zoom]')) return

  const delta = -event.deltaY
  const factor = Math.pow(1.1, delta / 100)
  const oldZoom = currentViewport.value.zoom
  const newZoom = Math.min(Math.max(oldZoom * factor, 0.05), 5)
  if (newZoom === oldZoom) return

  const rect = containerRef.value?.getBoundingClientRect()
  if (!rect) return

  // 以鼠标位置为缩放中心：保持鼠标下的世界坐标不变
  const mouseX = event.clientX - rect.left
  const mouseY = event.clientY - rect.top
  const worldX = (mouseX - currentViewport.value.x) / oldZoom
  const worldY = (mouseY - currentViewport.value.y) / oldZoom

  const newVp = {
    x: mouseX - worldX * newZoom,
    y: mouseY - worldY * newZoom,
    zoom: newZoom,
  }
  applyViewport(newVp)
  emit('zoom', newVp)
}

// ---------- 开始平移 ----------
function startPan(event: MouseEvent) {
  panState.isPanning = true
  panState.startX = event.clientX
  panState.startY = event.clientY
  panState.initialX = currentViewport.value.x
  panState.initialY = currentViewport.value.y
  panState.hasMoved = false
  document.body.style.cursor = 'grabbing'
}

// ---------- 指针按下 ----------
function handlePointerDown(event: PointerEvent) {
  const target = event.target instanceof Element ? event.target : null
  // 跳过标记了 data-canvas-no-zoom 的元素
  if (target?.closest?.('[data-canvas-no-zoom]')) return
  // 跳过连线创建菜单
  if (target?.closest?.('[data-connection-create-menu]')) return

  // 判断是否点击在背景上（非节点、非连线）
  const isBackgroundClick = !target?.closest?.('[data-node-id],[data-connection-id]')

  // Ctrl/Cmd + 左键点击背景：交给外部处理（如框选），不启动平移
  if (event.button === 0 && (event.ctrlKey || event.metaKey) && isBackgroundClick) {
    event.preventDefault()
    return
  }

  // 中键：开始平移
  if (event.button === 1) {
    event.preventDefault()
    ;(event.currentTarget as HTMLElement)?.setPointerCapture(event.pointerId)
    startPan(event)
    return
  }

  // 左键点击背景：开始平移（panEnabled 为 false 时跳过，交给外部处理框选）
  if (event.button === 0 && isBackgroundClick && props.panEnabled) {
    event.preventDefault()
    ;(event.currentTarget as HTMLElement)?.setPointerCapture(event.pointerId)
    startPan(event)
    return
  }

  // Space + 左键（即使点在节点上）：优先平移
  if (event.button === 0 && isSpacePressed.value) {
    event.preventDefault()
    ;(event.currentTarget as HTMLElement)?.setPointerCapture(event.pointerId)
    startPan(event)
    return
  }
}

// ---------- 指针移动（全局监听，平移时更新视口）----------
function handlePointerMove(event: PointerEvent) {
  if (!panState.isPanning) return

  const dx = event.clientX - panState.startX
  const dy = event.clientY - panState.startY
  // 移动超过 3 像素才视为真正的平移（区分点击与拖动）
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
    panState.hasMoved = true
  }

  const newVp = {
    x: panState.initialX + dx,
    y: panState.initialY + dy,
    zoom: currentViewport.value.zoom,
  }
  applyViewport(newVp)
  emit('pan', newVp)
}

// ---------- 指针释放（全局监听）----------
function handlePointerUp() {
  if (!panState.isPanning) return

  // 没有移动 → 视为背景点击（用于取消选中）
  if (!panState.hasMoved) {
    emit('background-click')
    // 兼容旧用法：清空 store 选中
    if (!props.viewport) {
      store.clearSelection()
    }
  }
  panState.isPanning = false
  document.body.style.cursor = isSpacePressed.value ? 'grab' : ''
}

// ---------- Space 按键监听 ----------
function handleKeyDown(event: KeyboardEvent) {
  if (event.code !== 'Space') return
  // 输入框内不响应
  if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
  isSpacePressed.value = true
  // 同步到 store（兼容旧逻辑，如节点拖拽时禁用 Space）
  store._isSpacePressed = true
}

function handleKeyUp(event: KeyboardEvent) {
  if (event.code === 'Space') {
    isSpacePressed.value = false
    store._isSpacePressed = false
  }
}

// ---------- 光标样式 ----------
// 光标样式：平移中=grabbing，按住 Space=grab，禁用平移（选择模式）=crosshair，默认=grab
const cursorStyle = computed(() => {
  if (panState.isPanning) return 'grabbing'
  if (isSpacePressed.value) return 'grab'
  if (!props.panEnabled) return 'crosshair'
  return 'grab'
})

// ---------- 背景网格样式（dots / lines / blank）----------
const gridStyle = computed(() => {
  const mode = currentBackgroundMode.value
  if (mode === 'blank') return { display: 'none' }

  const vp = currentViewport.value
  const gridSize = 48 * vp.zoom
  const x = vp.x % gridSize
  const y = vp.y % gridSize
  // 缩放过小时减小点尺寸，避免糊成一团
  const dotSize = vp.zoom < 0.12 ? 0.8 : 1.15
  const theme = currentTheme.value

  const backgroundImage =
    mode === 'dots'
      ? `radial-gradient(circle, ${theme.canvas.dot} ${dotSize}px, transparent ${dotSize + 0.2}px)`
      : `linear-gradient(${theme.canvas.line} 1px, transparent 1px), linear-gradient(90deg, ${theme.canvas.line} 1px, transparent 1px)`

  return {
    backgroundImage,
    backgroundSize: `${gridSize}px ${gridSize}px`,
    backgroundPosition: `${x}px ${y}px`,
  }
})

// ---------- 世界层 transform 样式 ----------
const worldTransform = computed(
  () => `translate(${currentViewport.value.x}px, ${currentViewport.value.y}px) scale(${currentViewport.value.zoom})`,
)

// ---------- 生命周期 ----------
let wheelTarget: HTMLElement | null = null

// 更新画布容器在屏幕中的位置偏移（用于 screenToWorld 坐标转换）
function updateCanvasRect() {
  const rect = containerRef.value?.getBoundingClientRect()
  if (rect) store.setCanvasRect(rect)
}

onMounted(() => {
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', handlePointerUp)
  window.addEventListener('keydown', handleKeyDown)
  window.addEventListener('keyup', handleKeyUp)
  // 容器位置变化时更新偏移（header 高度、窗口 resize 等）
  window.addEventListener('resize', updateCanvasRect)
  updateCanvasRect()

  // 在容器上注册 wheel 监听器（passive: false 以便阻止默认滚动）
  wheelTarget = containerRef.value
  wheelTarget?.addEventListener('wheel', handleWheel, { passive: false })
})

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', handlePointerMove)
  window.removeEventListener('pointerup', handlePointerUp)
  window.removeEventListener('keydown', handleKeyDown)
  window.removeEventListener('keyup', handleKeyUp)
  window.removeEventListener('resize', updateCanvasRect)
  wheelTarget?.removeEventListener('wheel', handleWheel)
  document.body.style.cursor = ''
  // 重置 store 的 Space 状态，避免遗留
  store._isSpacePressed = false
})

// ---------- 拖拽素材到画布 ----------
// 接收从素材库拖出的素材，转换为世界坐标后 emit 给父组件创建节点
function handleDragOver(e: DragEvent) {
  // 仅接收素材拖拽（application/x-asset），不干扰文件拖拽上传
  if (e.dataTransfer && e.dataTransfer.types.includes('application/x-asset')) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }
}

function handleDrop(e: DragEvent) {
  const assetData = e.dataTransfer?.getData('application/x-asset')
  if (!assetData) return
  e.preventDefault()
  try {
    const asset = JSON.parse(assetData)
    // 屏幕坐标转世界坐标
    const world = store.screenToWorld(e.clientX, e.clientY)
    emit('drop-asset', { asset, worldX: world.x, worldY: world.y })
  } catch (err) {
    console.warn('[infinite-canvas] 素材 drop 解析失败:', err)
  }
}
</script>

<template>
  <div
    ref="containerRef"
    class="infinite-canvas"
    :style="{ background: currentTheme.canvas.background, cursor: cursorStyle }"
    @pointerdown="handlePointerDown"
    @dragover="handleDragOver"
    @drop="handleDrop"
  >
    <!-- 背景网格层（dots / lines / blank），pointer-events none，透明度 0.4 -->
    <div class="infinite-canvas-grid" :style="gridStyle" />

    <!-- 世界坐标系层（通过 transform 应用视口变换）-->
    <div class="infinite-canvas-world" :style="{ transform: worldTransform }">
      <!-- 提供 slot 渲染节点层和连线层；默认渲染连线层 -->
      <slot>
        <CanvasConnectionsLayer />
      </slot>
    </div>
  </div>
</template>

<style scoped>
.infinite-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  user-select: none;
  -webkit-user-select: none;
}

.infinite-canvas-grid {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.4;
}

.infinite-canvas-world {
  position: absolute;
  left: 0;
  top: 0;
  transform-origin: 0 0;
}
</style>
