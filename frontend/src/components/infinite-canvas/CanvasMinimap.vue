<!-- =====================================================
     CanvasMinimap 右下角小地图
     - 显示所有节点的缩略色块（按类型不同颜色）
     - 显示当前视口矩形
     - 点击/拖动跳转视口
     样式：右下角固定 200x150，半透明背景
     ===================================================== -->

<template>
  <div class="canvas-minimap">
    <svg
      ref="svgRef"
      class="minimap-svg"
      :width="width"
      :height="height"
      @mousedown="handleMouseDown"
    >
      <!-- 节点缩略色块 -->
      <rect
        v-for="p in scaledPanels"
        :key="p.id"
        :x="p.x"
        :y="p.y"
        :width="p.w"
        :height="p.h"
        :fill="panelColor(p.type)"
        :rx="1"
      />
      <!-- 当前视口矩形 -->
      <rect
        v-if="scaledViewport"
        :x="scaledViewport.x"
        :y="scaledViewport.y"
        :width="scaledViewport.w"
        :height="scaledViewport.h"
        fill="none"
        :stroke="viewportStroke"
        :stroke-width="1.5"
        pointer-events="none"
      />
    </svg>
  </div>
</template>

<script setup>
// ------ 引入 Vue / Store ------
import { ref, computed } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import { canvasThemes } from '@/lib/canvas-theme'

const store = useCanvasStore()

// ------ 小地图尺寸 ------
const width = 200
const height = 150

const svgRef = ref(null)

// ------ 主题色映射（按节点类型） ------
function panelColor(type) {
  const theme = store.canvasTheme
  const colors = theme?.minimap?.panelColors || canvasThemes.dark.minimap.panelColors
  return colors[type] || colors.default
}

// 视口矩形描边色：使用主题的 active 连线色，确保在浅/深主题下都可见
const viewportStroke = computed(() => store.canvasTheme?.connection?.active || 'rgba(80, 140, 255, 0.8)')

// ------ 计算缩放比例：把世界坐标映射到 minimap 坐标 ------
const scale = computed(() => {
  const b = store.canvasBounds
  if (!b || b.width === 0 || b.height === 0) return 1
  return Math.min(width / b.width, height / b.height)
})

/** 世界坐标 → minimap 坐标 */
function worldToMini(wx, wy) {
  const b = store.canvasBounds
  const s = scale.value
  return {
    x: (wx - b.left) * s,
    y: (wy - b.top) * s,
  }
}

// ------ 缩放后的节点列表 ------
const scaledPanels = computed(() => {
  const s = scale.value
  return store.panels.map((p) => {
    const mini = worldToMini(p.x, p.y)
    return {
      id: p.id,
      type: p.type,
      x: mini.x,
      y: mini.y,
      w: Math.max(2, p.width * s),
      h: Math.max(2, p.height * s),
    }
  })
})

// ------ 缩放后的视口矩形 ------
const scaledViewport = computed(() => {
  const vp = store.viewportRect
  if (!vp) return null
  const s = scale.value
  const mini = worldToMini(vp.x, vp.y)
  return {
    x: mini.x,
    y: mini.y,
    w: vp.width * s,
    h: vp.height * s,
  }
})

// ------ 点击/拖动跳转视口 ------
let dragging = false

function handleMouseDown(e) {
  dragging = true
  jumpTo(e)
  window.addEventListener('mousemove', handleMouseMove)
  window.addEventListener('mouseup', handleMouseUp)
}

function handleMouseMove(e) {
  if (!dragging) return
  jumpTo(e)
}

function handleMouseUp() {
  dragging = false
  window.removeEventListener('mousemove', handleMouseMove)
  window.removeEventListener('mouseup', handleMouseUp)
}

/** 把鼠标在 minimap 上的位置转换为世界坐标，并居中视口 */
function jumpTo(e) {
  const svg = svgRef.value
  if (!svg) return
  const rect = svg.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  // minimap 坐标 → 世界坐标
  const b = store.canvasBounds
  const s = scale.value
  const worldX = mx / s + b.left
  const worldY = my / s + b.top
  // 把该世界坐标点居中到视口
  const { zoom } = store.viewport
  store.viewport.x = window.innerWidth / 2 - worldX * zoom
  store.viewport.y = window.innerHeight / 2 - worldY * zoom
}
</script>

<style scoped>
/* 右下角固定 200x150，半透明背景 */
.canvas-minimap {
  position: absolute;
  right: 16px;
  bottom: 16px;
  width: 200px;
  height: 150px;
  background: var(--canvas-panel-bg);
  border: 1px solid var(--canvas-node-border);
  border-radius: 8px;
  overflow: hidden;
  backdrop-filter: blur(8px);
  z-index: 10;
}

.minimap-svg {
  display: block;
  cursor: pointer;
  user-select: none;
}
</style>
