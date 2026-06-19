<!-- =====================================================
     InfiniteCanvas 无限画布主体
     - 视口变换（CSS transform：translate + scale）
     - 背景渲染（点阵 / 网格 / 空白，根据 store.backgroundMode）
     - 节点渲染（委托给 CanvasNode.vue）
     - 连线渲染（委托给 CanvasConnectionsSvg.vue）
     - 画布级鼠标事件：平移（Space/中键）、框选、滚轮缩放
     - 节点级事件转发：拖拽移动、四角缩放、锚点连线
     - emit panel-edit / panel-action 给父组件
     ===================================================== -->

<template>
  <div
    ref="containerRef"
    class="infinite-canvas-container"
    @mousedown="onCanvasMouseDown"
    @mousemove="onCanvasMouseMove"
    @mouseup="onCanvasMouseUp"
    @wheel.prevent="onWheel"
    @contextmenu.prevent
  >
    <!-- 画布世界层（应用视口 transform） -->
    <div class="canvas-world" :style="worldStyle">
      <!-- 背景层（点阵 / 网格 / 空白） -->
      <div class="canvas-bg" :class="`bg-${store.backgroundMode}`"></div>

      <!-- 连线 SVG 层（由 CanvasConnectionsLayer 统一渲染） -->
      <CanvasConnectionsLayer />

      <!-- 节点层（由 CanvasNodesLayer 统一渲染：内部根据 panel.type 动态选择内容组件） -->
      <CanvasNodesLayer
        @connect-start="onConnectStart"
        @connect-end="onConnectEnd"
      />
    </div>

    <!-- 框选矩形（屏幕坐标层，不参与 world transform） -->
    <div
      v-if="store.selectionBox"
      class="selection-box"
      :style="selectionBoxStyle"
    ></div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import CanvasNodesLayer from '@/components/canvas/CanvasNodesLayer.vue'
import CanvasConnectionsLayer from '@/components/canvas/CanvasConnectionsLayer.vue'

const store = useCanvasStore()
const containerRef = ref(null)

// 拖拽状态（不持久化）
const dragState = ref(null) // { type: 'pan'|'select'|'node'|'resize', ... }

// 视口 transform 样式
const worldStyle = computed(() => ({
  transform: `translate(${store.viewport.x}px, ${store.viewport.y}px) scale(${store.viewport.zoom})`,
  transformOrigin: '0 0',
}))

// 渲染的面板列表（应用搜索/筛选/隐藏过滤）
const renderPanels = computed(() => {
  let list = store.visiblePanels
  // 隐藏过滤
  if (store.hiddenIds.length > 0) {
    const hiddenSet = new Set(store.hiddenIds)
    list = list.filter((p) => !hiddenSet.has(p.id))
  }
  // 类型筛选
  if (store.filterTypes.length > 0) {
    const typeSet = new Set(store.filterTypes)
    list = list.filter((p) => typeSet.has(p.type))
  }
  return list
})

// 框选矩形样式（屏幕坐标）
const selectionBoxStyle = computed(() => {
  if (!store.selectionBox) return {}
  const { startScreen, endScreen } = store.selectionBox
  const left = Math.min(startScreen.x, endScreen.x)
  const top = Math.min(startScreen.y, endScreen.y)
  const width = Math.abs(endScreen.x - startScreen.x)
  const height = Math.abs(endScreen.y - startScreen.y)
  return {
    left: `${left}px`,
    top: `${top}px`,
    width: `${width}px`,
    height: `${height}px`,
  }
})

// ---------- 坐标转换 ----------

/** 屏幕坐标 → 世界坐标（基于容器） */
function screenToWorld(clientX, clientY) {
  const rect = containerRef.value?.getBoundingClientRect()
  if (!rect) return { x: 0, y: 0 }
  return store.screenToWorld(clientX - rect.left, clientY - rect.top)
}

// ---------- 画布级鼠标事件 ----------

/** 画布 mousedown：判断是平移、框选还是节点拖拽 */
function onCanvasMouseDown(e) {
  // 中键或 Space 按下 → 平移模式
  if (e.button === 1 || store._isSpacePressed) {
    e.preventDefault()
    dragState.value = {
      type: 'pan',
      startX: e.clientX,
      startY: e.clientY,
      originVx: store.viewport.x,
      originVy: store.viewport.y,
    }
    return
  }

  // 左键点击空白 → 框选
  if (e.button === 0 && e.target === e.currentTarget) {
    const rect = containerRef.value.getBoundingClientRect()
    const startScreen = { x: e.clientX - rect.left, y: e.clientY - rect.top }
    const startWorld = store.screenToWorld(startScreen.x, startScreen.y)
    dragState.value = {
      type: 'select',
      startScreen,
      startWorld,
    }
    store.selectionBox = {
      startScreen,
      endScreen: { ...startScreen },
      startWorld,
      endWorld: { ...startWorld },
    }
    // 清除选中
    store.selectedPanelIds = []
    store.selectedPanelId = null
    store.selectedConnectionId = null
  }
}

/** 画布 mousemove：更新平移/框选/节点拖拽 */
function onCanvasMouseMove(e) {
  if (!dragState.value) {
    // 更新连线拖拽位置（把浏览器 client 坐标换算为相对于容器的坐标，再传给 store
    // store.screenToWorld 期望相对于画布容器的坐标，不包含容器在页面中的偏移）
    if (store._connecting) {
      const rect = containerRef.value?.getBoundingClientRect()
      const relX = rect ? e.clientX - rect.left : e.clientX
      const relY = rect ? e.clientY - rect.top : e.clientY
      store.updateConnecting(relX, relY)
    }
    return
  }

  const ds = dragState.value

  if (ds.type === 'pan') {
    const dx = e.clientX - ds.startX
    const dy = e.clientY - ds.startY
    store.viewport.x = ds.originVx + dx
    store.viewport.y = ds.originVy + dy
    return
  }

  if (ds.type === 'select') {
    const rect = containerRef.value.getBoundingClientRect()
    const endScreen = { x: e.clientX - rect.left, y: e.clientY - rect.top }
    const endWorld = store.screenToWorld(endScreen.x, endScreen.y)
    store.selectionBox = {
      ...store.selectionBox,
      endScreen,
      endWorld,
    }
    return
  }

  if (ds.type === 'node') {
    const world = screenToWorld(e.clientX, e.clientY)
    const dx = world.x - ds.startWorld.x
    const dy = world.y - ds.startWorld.y
    // 高频更新，不压栈
    for (const item of ds.panels) {
      store._updatePanelDirect(item.id, {
        x: item.origX + dx,
        y: item.origY + dy,
      })
    }
    return
  }

  if (ds.type === 'resize') {
    const world = screenToWorld(e.clientX, e.clientY)
    const panel = store.panels.find((p) => p.id === ds.panelId)
    if (!panel) return
    let newW = ds.origW
    let newH = ds.origH
    let newX = ds.origX
    let newY = ds.origY
    const dx = world.x - ds.startWorld.x
    const dy = world.y - ds.startWorld.y
    // 根据 handle 方向计算新尺寸
    if (ds.handle.includes('e')) newW = Math.max(60, ds.origW + dx)
    if (ds.handle.includes('s')) newH = Math.max(40, ds.origH + dy)
    if (ds.handle.includes('w')) {
      newW = Math.max(60, ds.origW - dx)
      newX = ds.origX + (ds.origW - newW)
    }
    if (ds.handle.includes('n')) {
      newH = Math.max(40, ds.origH - dy)
      newY = ds.origY + (ds.origH - newH)
    }
    // 图片节点保持比例（按 shift 强制自由变形）
    if (ds.keepRatio && !ds.freeResize) {
      // 简化：按宽度等比缩放高度
      const ratio = ds.origH / ds.origW
      newH = newW * ratio
    }
    store._updatePanelDirect(ds.panelId, {
      x: newX, y: newY, width: newW, height: newH,
    })
    return
  }
}

/** 画布 mouseup：结束所有拖拽 */
function onCanvasMouseUp(e) {
  if (!dragState.value) {
    // 结束连线拖拽
    if (store._connecting) {
      // 未命中目标锚点 → 检查是否拖到空白
      const world = screenToWorld(e.clientX, e.clientY)
      store.setPendingConnectionCreate({
        sourcePanelId: store._connecting.sourcePanelId,
        anchorType: store._connecting.anchorType,
        worldX: world.x,
        worldY: world.y,
      })
      store.cancelConnecting()
    }
    return
  }

  const ds = dragState.value

  if (ds.type === 'select') {
    // 计算框选范围内的面板
    if (store.selectionBox) {
      const { startWorld, endWorld } = store.selectionBox
      store.selectPanelsInRect({ startWorld, endWorld })
    }
    store.selectionBox = null
  }

  if (ds.type === 'node' || ds.type === 'resize') {
    // 拖拽结束保存一次
    store.saveCanvas?.(store)
  }

  dragState.value = null
}

// ---------- 滚轮缩放 ----------

function onWheel(e) {
  const rect = containerRef.value.getBoundingClientRect()
  const center = { x: e.clientX - rect.left, y: e.clientY - rect.top }
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  const newZoom = Math.min(3, Math.max(0.1, store.viewport.zoom * delta))
  store.setZoom(newZoom, center)
}

// ---------- 节点事件转发 ----------

/** 节点开始拖拽 */
function onNodeDragStart({ panelId, e }) {
  // 选中该节点
  if (!store.selectedPanelIds.includes(panelId)) {
    if (e.shiftKey) {
      store.selectedPanelIds = [...store.selectedPanelIds, panelId]
    } else {
      store.selectedPanelIds = [panelId]
    }
    store.selectedPanelId = panelId
  }
  // 收集所有选中节点
  const panels = store.selectedPanelIds
    .map((id) => store.panels.find((p) => p.id === id))
    .filter(Boolean)
  store.pushSnapshot()
  dragState.value = {
    type: 'node',
    startWorld: screenToWorld(e.clientX, e.clientY),
    panels: panels.map((p) => ({
      id: p.id,
      origX: p.x,
      origY: p.y,
    })),
  }
}

/** 节点开始缩放 */
function onNodeResizeStart({ panelId, handle, e }) {
  const panel = store.panels.find((p) => p.id === panelId)
  if (!panel) return
  store.pushSnapshot()
  const keepRatio = panel.type === 'image' && !panel.content?.freeResize
  dragState.value = {
    type: 'resize',
    panelId,
    handle,
    startWorld: screenToWorld(e.clientX, e.clientY),
    origX: panel.x,
    origY: panel.y,
    origW: panel.width,
    origH: panel.height,
    keepRatio,
    freeResize: panel.content?.freeResize,
  }
}

/** 连线开始 */
function onConnectStart({ panelId, anchorType }) {
  store.startConnecting(panelId, anchorType)
}

/** 连线结束（命中目标锚点） */
function onConnectEnd({ panelId, anchorType }) {
  store.endConnecting(panelId, anchorType)
}

/** 选中连线 */
function onSelectConnection(connId) {
  store.selectedConnectionId = connId
  store.selectedPanelIds = []
  store.selectedPanelId = null
}

/** 节点编辑事件 */
function onPanelEdit(panel) {
  emit('panel-edit', panel)
}

/** 节点动作事件 */
function onPanelAction(payload) {
  emit('panel-action', payload)
}

// ---------- 生命周期 ----------

const emit = defineEmits(['panel-edit', 'panel-action'])

onMounted(() => {
  // 全局 mouseup 监听（防止鼠标移出容器后拖拽不结束）
  window.addEventListener('mouseup', onCanvasMouseUp)
})

onUnmounted(() => {
  window.removeEventListener('mouseup', onCanvasMouseUp)
})
</script>

<style scoped>
.infinite-canvas-container {
  position: relative;
  flex: 1;
  overflow: hidden;
  cursor: default;
  background: var(--canvas-bg);
}

.infinite-canvas-container:active {
  cursor: inherit;
}

.canvas-world {
  position: absolute;
  top: 0;
  left: 0;
  width: 0;
  height: 0;
}

/* 背景层：覆盖一个超大区域，随 world transform 缩放 */
.canvas-bg {
  position: absolute;
  top: -100000px;
  left: -100000px;
  width: 200000px;
  height: 200000px;
  pointer-events: none;
}

/* 点阵背景 */
.canvas-bg.bg-dot {
  background-image: radial-gradient(
    var(--canvas-grid-dot) 1px,
    transparent 1px
  );
  background-size: 24px 24px;
}

/* 网格背景 */
.canvas-bg.bg-grid {
  background-image: linear-gradient(var(--canvas-grid-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--canvas-grid-line) 1px, transparent 1px);
  background-size: 24px 24px;
}

/* 空白背景 */
.canvas-bg.bg-blank {
  background: transparent;
}

/* 框选矩形 */
.selection-box {
  position: absolute;
  background: var(--canvas-selection-fill);
  border: 1px solid var(--canvas-selection-stroke);
  pointer-events: none;
  z-index: 9999;
}
</style>
