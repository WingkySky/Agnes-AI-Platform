<!--
  CanvasMinimap.vue
  画布小地图：用 SVG 渲染所有节点的缩略色块和当前视口框，支持点击/拖拽定位视口
  1:1 复刻参考项目 infinite-canvas 的 canvas-mini-map 设计
-->
<template>
  <div class="canvas-minimap" :style="containerStyle">
    <svg
      ref="svgRef"
      class="minimap-svg"
      :width="width"
      :height="height"
      :viewBox="`0 0 ${width} ${height}`"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointerleave="onPointerUp"
    >
      <!-- 节点色块（按类型着色） -->
      <rect
        v-for="p in panels"
        :key="p.id"
        :x="nodeRect(p).x"
        :y="nodeRect(p).y"
        :width="nodeRect(p).w"
        :height="nodeRect(p).h"
        :fill="nodeColor(p.type)"
        :opacity="0.8"
        rx="1"
      />
      <!-- 视口框：主题选择框颜色 -->
      <rect
        :x="viewportRect.x"
        :y="viewportRect.y"
        :width="viewportRect.w"
        :height="viewportRect.h"
        :fill="theme.canvas.selectionFill"
        :stroke="theme.canvas.selectionStroke"
        stroke-width="1"
        pointer-events="none"
      />
    </svg>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  theme: { type: Object, required: true },
  panels: { type: Array, default: () => [] }, // 所有节点
  viewport: { type: Object, required: true }, // { x, y, zoom }
  canvasSize: {
    type: Object,
    default: () => ({ width: window.innerWidth, height: window.innerHeight }),
  },
})

const emit = defineEmits(['locate']) // (worldX, worldY)

// 小地图尺寸
const width = 240
const height = 160
// 节点边界外扩 padding（世界坐标）
const PADDING = 500

const svgRef = ref(null)
const isDragging = ref(false)

// 计算所有节点的世界边界 + 缩放比 + 偏移
const minimapBounds = computed(() => {
  if (!props.panels.length) {
    return {
      worldBounds: { x: -500, y: -500, w: 1000, h: 1000 },
      scale: 0.16,
      offset: { x: 40, y: 0 },
    }
  }
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const node of props.panels) {
    const nx = node.x ?? 0
    const ny = node.y ?? 0
    const nw = node.width ?? 0
    const nh = node.height ?? 0
    minX = Math.min(minX, nx)
    minY = Math.min(minY, ny)
    maxX = Math.max(maxX, nx + nw)
    maxY = Math.max(maxY, ny + nh)
  }
  minX -= PADDING
  minY -= PADDING
  maxX += PADDING
  maxY += PADDING
  const boundsWidth = maxX - minX
  const boundsHeight = maxY - minY
  const scale = Math.min(width / boundsWidth, height / boundsHeight)
  const mapContentW = boundsWidth * scale
  const mapContentH = boundsHeight * scale
  return {
    worldBounds: { x: minX, y: minY, w: boundsWidth, h: boundsHeight },
    scale,
    offset: { x: (width - mapContentW) / 2, y: (height - mapContentH) / 2 },
  }
})

// 世界坐标 -> 小地图坐标
function toMinimap(worldX, worldY) {
  const { worldBounds, scale, offset } = minimapBounds.value
  return {
    x: (worldX - worldBounds.x) * scale + offset.x,
    y: (worldY - worldBounds.y) * scale + offset.y,
  }
}

// 小地图坐标 -> 世界坐标
function toWorld(minimapX, minimapY) {
  const { worldBounds, scale, offset } = minimapBounds.value
  return {
    x: (minimapX - offset.x) / scale + worldBounds.x,
    y: (minimapY - offset.y) / scale + worldBounds.y,
  }
}

// 节点在小地图上的矩形
function nodeRect(node) {
  const pos = toMinimap(node.x ?? 0, node.y ?? 0)
  const s = minimapBounds.value.scale
  return {
    x: pos.x,
    y: pos.y,
    w: Math.max((node.width ?? 0) * s, 2),
    h: Math.max((node.height ?? 0) * s, 2),
  }
}

// 节点类型颜色
function nodeColor(type) {
  switch (type) {
    case 'image':
      return '#10b981'
    case 'video':
      return '#f97316'
    case 'audio':
      return '#a855f7'
    case 'config':
      return '#60a5fa'
    case 'text':
    default:
      return props.theme.node.muted
  }
}

// 视口框在小地图上的矩形
const viewportRect = computed(() => {
  const zoom = props.viewport.zoom || 1
  const vx = -props.viewport.x / zoom
  const vy = -props.viewport.y / zoom
  const vw = props.canvasSize.width / zoom
  const vh = props.canvasSize.height / zoom
  const p1 = toMinimap(vx, vy)
  const p2 = toMinimap(vx + vw, vy + vh)
  return {
    x: p1.x,
    y: p1.y,
    w: Math.max(p2.x - p1.x, 4),
    h: Math.max(p2.y - p1.y, 4),
  }
})

// 容器样式
const containerStyle = computed(() => ({
  width: `${width}px`,
  height: `${height}px`,
  background: props.theme.toolbar.panel,
  borderColor: props.theme.toolbar.border,
}))

// 拖拽/点击定位视口：将小地图坐标转为世界坐标后 emit
function locateFromEvent(event) {
  const rect = svgRef.value?.getBoundingClientRect()
  if (!rect) return
  const mx = event.clientX - rect.left
  const my = event.clientY - rect.top
  const world = toWorld(mx, my)
  emit('locate', world.x, world.y)
}

function onPointerDown(event) {
  event.preventDefault()
  svgRef.value?.setPointerCapture?.(event.pointerId)
  isDragging.value = true
  locateFromEvent(event)
}

function onPointerMove(event) {
  if (!isDragging.value) return
  locateFromEvent(event)
}

function onPointerUp() {
  isDragging.value = false
}
</script>

<style scoped>
/* 容器：固定在缩放控件上方 */
.canvas-minimap {
  position: fixed;
  bottom: 96px; /* bottom-24 */
  left: 24px; /* left-6 */
  z-index: 50;
  overflow: hidden;
  border: 1px solid;
  border-radius: 8px; /* rounded-lg */
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.25);
  backdrop-filter: blur(4px); /* backdrop-blur-sm */
  -webkit-backdrop-filter: blur(4px);
}

.minimap-svg {
  display: block;
  cursor: crosshair;
}
</style>
