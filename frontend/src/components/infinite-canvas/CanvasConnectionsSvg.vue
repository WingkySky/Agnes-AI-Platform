/* =====================================================
 * 连线 SVG 层
 * - 绘制所有贝塞尔曲线连线
 * - 颜色区分类型（任务流=蓝色，手动=灰色）
 * ===================================================== */

<template>
  <svg class="canvas-connections">
    <defs>
      <!-- 蓝色箭头（任务流） -->
      <marker
        id="arrow-blue"
        markerWidth="10"
        markerHeight="7"
        refX="9"
        refY="3.5"
        orient="auto"
      >
        <polygon points="0 0, 10 3.5, 0 7" fill="rgba(100, 150, 255, 0.6)" />
      </marker>
      <!-- 灰色箭头（手动） -->
      <marker
        id="arrow-gray"
        markerWidth="10"
        markerHeight="7"
        refX="9"
        refY="3.5"
        orient="auto"
      >
        <polygon points="0 0, 10 3.5, 0 7" fill="rgba(150, 150, 180, 0.3)" />
      </marker>
    </defs>

    <path
      v-for="conn in connections"
      :key="conn.id"
      :d="getPathD(conn)"
      :fill="none"
      :stroke="getStrokeColor(conn)"
      :stroke-width="getStrokeWidth(conn)"
      :marker-end="getMarker(conn)"
      :class="['connection-path', { selected: conn.id === store.selectedConnectionId }]"
      @click.stop="store.selectConnection(conn.id)"
    />
  </svg>
</template>

<script setup>
import { computed } from 'vue'
import { useCanvasStore } from '@/stores/canvas'

const store = useCanvasStore()

const connections = computed(() => store.connections)

/** 计算贝塞尔曲线路径 */
function getPathD(conn) {
  const source = store.panels.find((p) => p.id === conn.source_panel_id)
  const target = store.panels.find((p) => p.id === conn.target_panel_id)
  if (!source || !target) return ''

  // 源锚点（右下角）和目标锚点（左上角）
  const sx = source.x + source.width
  const sy = source.y + source.height
  const tx = target.x
  const ty = target.y

  // 控制点水平延伸面板宽度的 30%
  const dx = 30 * store.viewport.zoom
  const c1x = sx + dx
  const c1y = sy
  const c2x = tx - dx
  const c2y = ty

  return `M ${sx} ${sy} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${tx} ${ty}`
}

function getStrokeColor(conn) {
  return conn.type === 'auto'
    ? 'rgba(100, 150, 255, 0.4)'
    : 'rgba(150, 150, 180, 0.3)'
}

function getStrokeWidth(conn) {
  return conn.id === store.selectedConnectionId ? 3 : 2
}

function getMarker(conn) {
  return conn.type === 'auto' ? 'url(#arrow-blue)' : 'url(#arrow-gray)'
}
</script>

<style scoped>
.canvas-connections {
  position: absolute;
  top: 0;
  left: 0;
  width: 100000px;
  height: 100000px;
  transform: translate(-50000px, -50000px);
  pointer-events: none;
}

.connection-path {
  pointer-events: stroke;
  cursor: pointer;
  transition: stroke-width 0.15s ease;
}

.connection-path:hover {
  stroke-width: 3 !important;
  filter: brightness(1.3);
}

.connection-path.selected {
  stroke-width: 3 !important;
  filter: brightness(1.5);
}
</style>
