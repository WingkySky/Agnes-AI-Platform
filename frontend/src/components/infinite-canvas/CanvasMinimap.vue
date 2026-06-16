/* =====================================================
 * Minimap 小地图
 * - 右下角固定位置
 * - 显示所有面板的缩略位置
 * - 显示当前视口区域（高亮矩形）
 * - 点击小地图跳转到对应区域
 * ===================================================== */

<template>
  <div class="minimap" @click.self="handleMinimapClick">
    <svg
      ref="svgRef"
      class="minimap-svg"
      :viewBox="`${bounds.left} ${bounds.top} ${bounds.width} ${bounds.height}`"
    >
      <!-- 连线 -->
      <path
        v-for="conn in connections"
        :key="conn.id"
        :d="getMinimapConnectionD(conn)"
        :stroke="theme.connection.muted"
        stroke-width="1"
        fill="none"
      />

      <!-- 面板缩略图 -->
      <rect
        v-for="panel in panels"
        :key="panel.id"
        :x="panel.x"
        :y="panel.y"
        :width="panel.width"
        :height="panel.height"
        :rx="4"
        :fill="getPanelColor(panel.type)"
        :opacity="panel.id === selectedPanelId ? 0.9 : 0.6"
      />

      <!-- 当前视口高亮矩形 -->
      <rect
        :x="viewportRect.x"
        :y="viewportRect.y"
        :width="viewportRect.width"
        :height="viewportRect.height"
        rx="4"
        fill="none"
        :stroke="theme.connection.active"
        stroke-width="2"
        stroke-dasharray="4 2"
      />
    </svg>

    <!-- 缩放提示 -->
    <div class="minimap-hint">
      <span>{{ Math.round(viewport.zoom * 100) }}%</span>
      <el-icon class="minimap-toggle" @click="toggleVisible">
        <Close v-if="visible" />
        <ZoomIn v-else />
      </el-icon>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import { Close, ZoomIn } from '@element-plus/icons-vue'

const store = useCanvasStore()
const svgRef = ref(null)
const visible = ref(true)
const theme = computed(() => store.canvasTheme)

const panels = computed(() => store.panels)
const connections = computed(() => store.connections)
const bounds = computed(() => store.canvasBounds)
const viewportRect = computed(() => store.viewportRect)
const selectedPanelId = computed(() => store.selectedPanelId)
const viewport = computed(() => store.viewport)

/** 根据面板类型返回颜色（从画布主题 token 读取） */
function getPanelColor(type) {
  const colors = theme.value.minimap?.panelColors ?? {}
  return colors[type] || colors.default || 'rgba(150, 150, 180, 0.4)'
}

/** 小地图中的连线路径（直线连接锚点） */
function getMinimapConnectionD(conn) {
  const source = store.panels.find((p) => p.id === conn.source_panel_id)
  const target = store.panels.find((p) => p.id === conn.target_panel_id)
  if (!source || !target) return ''

  const sx = source.x + source.width
  const sy = source.y + source.height
  const tx = target.x
  const ty = target.y

  return `M ${sx} ${sy} L ${tx} ${ty}`
}

/** 点击小地图跳转到对应区域 */
function handleMinimapClick(e) {
  if (!visible.value) return

  const svg = svgRef.value
  if (!svg) return

  const rect = svg.getBoundingClientRect()
  const vb = svg.viewBox.baseVal

  // 计算点击位置在世界坐标中的位置
  const clickWorldX = vb.x + ((e.clientX - rect.left) / rect.width) * vb.width
  const clickWorldY = vb.y + ((e.clientY - rect.top) / rect.height) * vb.height

  // 将点击位置转换为视口中心
  const viewWidth = window.innerWidth
  const viewHeight = window.innerHeight

  // 新的视口中心应该是点击位置
  // 反向计算 viewport.x/y
  const newX = -clickWorldX * viewport.value.zoom + viewWidth / 2 * viewport.value.zoom
  const newY = -clickWorldY * viewport.value.zoom + viewHeight / 2 * viewport.value.zoom

  store.viewport.x = newX
  store.viewport.y = newY
}

/** 切换显示/隐藏 */
function toggleVisible() {
  visible.value = !visible.value
}
</script>

<style scoped>
.minimap {
  position: absolute;
  bottom: 16px;
  right: 16px;
  width: 200px;
  height: 140px;
  background: var(--canvas-panel-bg);
  border: 1px solid var(--canvas-node-border);
  border-radius: 8px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(12px);
  overflow: hidden;
  z-index: 100;
  transition: opacity 0.2s;
}

.minimap-svg {
  width: 100%;
  height: 100%;
  cursor: grab;
}

.minimap-svg:active {
  cursor: grabbing;
}

.minimap-hint {
  position: absolute;
  bottom: 4px;
  left: 4px;
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: var(--canvas-node-muted-text);
  pointer-events: none;
}

.minimap-toggle {
  font-size: 12px;
  color: var(--canvas-node-muted-text);
  cursor: pointer;
  pointer-events: all;
  transition: color 0.15s;
}

.minimap-toggle:hover {
  color: var(--canvas-connection-active);
}
</style>
