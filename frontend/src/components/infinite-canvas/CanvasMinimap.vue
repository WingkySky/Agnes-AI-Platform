<!-- =====================================================
     CanvasMinimap 右下角小地图
     - 固定定位 200x150px，右下角 20px 边距
     - SVG 渲染：所有面板按 type 颜色画小矩形
     - 当前视口框高亮显示
     - 点击 / 拖动小地图可平移画布（把点击位置居中到视口）
     - 面板颜色来自 canvasThemes.minimap.panelColors
       image 蓝 / video 紫 / text 绿 / config 橙 / frame 灰
     ===================================================== -->

<template>
  <div class="canvas-minimap">
    <svg
      ref="minimapRef"
      class="minimap-svg"
      width="200"
      height="150"
      :class="{ dragging: isDragging }"
      @mousedown="handleMouseDown"
    >
      <!-- 面板矩形：按 type 颜色区分 -->
      <rect
        v-for="panel in store.panels"
        :key="panel.id"
        :x="worldToMiniX(panel.x)"
        :y="worldToMiniY(panel.y)"
        :width="Math.max(2, panel.width * transform.scale)"
        :height="Math.max(2, panel.height * transform.scale)"
        :rx="1"
        :fill="panelColor(panel.type)"
        pointer-events="none"
      />

      <!-- 当前视口框（高亮边框） -->
      <rect
        :x="worldToMiniX(store.viewportRect.x)"
        :y="worldToMiniY(store.viewportRect.y)"
        :width="Math.max(2, store.viewportRect.width * transform.scale)"
        :height="Math.max(2, store.viewportRect.height * transform.scale)"
        class="viewport-rect"
        pointer-events="none"
      />
    </svg>
  </div>
</template>

<script setup>
// ------ 模块依赖 ------
import { ref, computed, onUnmounted } from 'vue'
import { useCanvasStore } from '@/stores/canvas'

const store = useCanvasStore()

// ------ 小地图尺寸常量 ------
const MINI_W = 200
const MINI_H = 150
const PADDING = 6 // 内边距，避免内容贴边

// ------ SVG 元素 ref ------
const minimapRef = ref(null)

// ------ 拖拽状态 ------
const isDragging = ref(false)

// ------ 缩放变换计算：根据 canvasBounds 计算 scale 和 offset ------
const transform = computed(() => {
  const bounds = store.canvasBounds
  // 取宽高方向较小的缩放比，保证内容完整显示在小地图内
  const scaleX = (MINI_W - PADDING * 2) / bounds.width
  const scaleY = (MINI_H - PADDING * 2) / bounds.height
  const scale = Math.min(scaleX, scaleY)

  // 居中偏移
  const contentW = bounds.width * scale
  const contentH = bounds.height * scale
  const offsetX = (MINI_W - contentW) / 2
  const offsetY = (MINI_H - contentH) / 2

  return { scale, offsetX, offsetY, bounds }
})

// ------ 世界坐标 → 小地图坐标 ------
function worldToMiniX(worldX) {
  const { scale, offsetX, bounds } = transform.value
  return offsetX + (worldX - bounds.left) * scale
}

function worldToMiniY(worldY) {
  const { scale, offsetY, bounds } = transform.value
  return offsetY + (worldY - bounds.top) * scale
}

// ------ 小地图坐标 → 世界坐标 ------
function miniToWorldX(miniX) {
  const { scale, offsetX, bounds } = transform.value
  return (miniX - offsetX) / scale + bounds.left
}

function miniToWorldY(miniY) {
  const { scale, offsetY, bounds } = transform.value
  return (miniY - offsetY) / scale + bounds.top
}

// ------ 面板颜色映射：来自 canvasThemes.minimap.panelColors ------
// 任务要求：config 用橙色（映射自 url 色），frame 用灰色
function panelColor(type) {
  const colors = store.canvasTheme.minimap?.panelColors || {}
  if (type === 'config') return colors.url || 'rgba(255, 180, 80, 0.5)'
  if (type === 'frame') return 'rgba(150, 150, 180, 0.4)'
  return colors[type] || colors.default || 'rgba(150, 150, 180, 0.4)'
}

// ------ 把指定世界坐标居中到视口 ------
// 直接修改 viewport.x/y，不压历史快照（与 centerOnPanel 同算法）
function centerOnWorld(worldX, worldY) {
  const { zoom } = store.viewport
  store.viewport.x = window.innerWidth / 2 - worldX * zoom
  store.viewport.y = window.innerHeight / 2 - worldY * zoom
}

// ------ 鼠标按下：开始拖拽并立即居中到点击位置 ------
function handleMouseDown(e) {
  isDragging.value = true
  centerOnMouse(e)
  window.addEventListener('mousemove', handleMouseMove)
  window.addEventListener('mouseup', handleMouseUp)
}

// ------ 鼠标移动：拖拽中持续平移 ------
function handleMouseMove(e) {
  if (!isDragging.value) return
  centerOnMouse(e)
}

// ------ 鼠标释放：结束拖拽 ------
function handleMouseUp() {
  isDragging.value = false
  window.removeEventListener('mousemove', handleMouseMove)
  window.removeEventListener('mouseup', handleMouseUp)
}

// ------ 把鼠标位置转换为世界坐标并居中 ------
function centerOnMouse(e) {
  const svg = minimapRef.value
  if (!svg) return
  const rect = svg.getBoundingClientRect()
  const miniX = e.clientX - rect.left
  const miniY = e.clientY - rect.top
  const worldX = miniToWorldX(miniX)
  const worldY = miniToWorldY(miniY)
  centerOnWorld(worldX, worldY)
}

// ------ 组件卸载时清理事件监听 ------
onUnmounted(() => {
  window.removeEventListener('mousemove', handleMouseMove)
  window.removeEventListener('mouseup', handleMouseUp)
})
</script>

<style scoped>
/* 小地图容器：固定定位右下角 */
.canvas-minimap {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: 200px;
  height: 150px;
  background: var(--canvas-panel-bg);
  border: 1px solid var(--canvas-node-border);
  border-radius: 8px;
  overflow: hidden;
  backdrop-filter: blur(12px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
  z-index: 100;
  user-select: none;
}

/* SVG 填满容器 */
.minimap-svg {
  display: block;
  width: 100%;
  height: 100%;
  cursor: crosshair;
}

.minimap-svg.dragging {
  cursor: grabbing;
}

/* 视口高亮框 */
.viewport-rect {
  fill: rgba(100, 150, 255, 0.08);
  stroke: var(--canvas-node-active-border);
  stroke-width: 1.5;
}
</style>
