/* =====================================================
 * 连线 SVG 层
 * - 绘制所有贝塞尔曲线连线
 * - 颜色区分类型（任务流=蓝色，手动=灰色）
 * - 支持拖拽创建连线时的临时虚线
 * - 选中连线时高亮 + 删除按钮
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

    <!-- 正式连线 -->
    <g
      v-for="conn in connections"
      :key="conn.id"
      class="connection-group"
      :data-conn-id="conn.id"
      :class="{ selected: conn.id === store.selectedConnectionId }"
      @click.stop="store.selectConnection(conn.id)"
    >
      <path
        :d="getPathD(conn)"
        :fill="none"
        :stroke="getStrokeColor(conn)"
        :stroke-width="getStrokeWidth(conn)"
        :marker-end="getMarker(conn)"
        pointer-events="stroke"
        class="connection-path"
      />
      <!-- 删除按钮（选中时显示） -->
      <circle
        v-if="conn.id === store.selectedConnectionId"
        :cx="getMidpoint(conn).x"
        :cy="getMidpoint(conn).y"
        r="8"
        fill="#ff4d4f"
        stroke="#fff"
        stroke-width="1.5"
        cursor="pointer"
        pointer-events="all"
        @click.stop="store.deleteConnection(conn.id)"
      />
      <text
        v-if="conn.id === store.selectedConnectionId"
        :x="getMidpoint(conn).x"
        :y="getMidpoint(conn).y + 1"
        text-anchor="middle"
        dominant-baseline="central"
        fill="#fff"
        font-size="10"
        font-weight="bold"
        pointer-events="none"
        @click.stop="store.deleteConnection(conn.id)"
      >
        ×
      </text>
    </g>

    <!-- 拖拽时的临时连线 -->
    <path
      v-if="isConnecting"
      :d="getTempConnectionPath"
      fill="none"
      stroke="rgba(80, 140, 255, 0.6)"
      stroke-width="2"
      stroke-dasharray="6 4"
      pointer-events="none"
    />
  </svg>
</template>

<script setup>
import { computed } from 'vue'
import { useCanvasStore } from '@/stores/canvas'

const store = useCanvasStore()

const connections = computed(() => store.connections)
const connecting = computed(() => store._connecting)
const isConnecting = computed(() => !!connecting.value)

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

/** 计算临时连线路径（拖拽中） */
const getTempConnectionPath = computed(() => {
  const c = connecting.value
  if (!c) return ''

  const source = store.panels.find((p) => p.id === c.sourcePanelId)
  if (!source) return ''

  let sx, sy
  if (c.anchorType === 'output') {
    // 输出锚点在右下角
    sx = source.x + source.width
    sy = source.y + source.height
  } else {
    // 输入锚点在左上角
    sx = source.x
    sy = source.y
  }

  const tx = c.worldX
  const ty = c.worldY

  const dx = 30 * store.viewport.zoom
  const c1x = sx + dx
  const c1y = sy
  const c2x = tx - dx
  const c2y = ty

  return `M ${sx} ${sy} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${tx} ${ty}`
})

/** 计算连线中点（用于放置删除按钮） */
function getMidpoint(conn) {
  const source = store.panels.find((p) => p.id === conn.source_panel_id)
  const target = store.panels.find((p) => p.id === conn.target_panel_id)
  if (!source || !target) return { x: 0, y: 0 }

  const sx = source.x + source.width
  const sy = source.y + source.height
  const tx = target.x
  const ty = target.y

  // 贝塞尔曲线中点近似（控制点水平偏移 30% 面板宽度）
  const dx = 30 * store.viewport.zoom
  const c1x = sx + dx
  const c1y = sy
  const c2x = tx - dx
  const c2y = ty

  // 三次贝塞尔曲线中点：t=0.5 的插值
  const t = 0.5
  const mt = 1 - t
  return {
    x: mt*mt*mt*sx + 3*mt*mt*t*c1x + 3*mt*t*t*c2x + t*t*t*tx,
    y: mt*mt*mt*sy + 3*mt*mt*t*c1y + 3*mt*t*t*c2y + t*t*t*ty,
  }
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
}

.connection-group {
  cursor: pointer;
}

.connection-group.selected .connection-path {
  stroke-width: 3 !important;
  filter: brightness(1.5);
}

.connection-path {
  transition: stroke-width 0.15s ease;
}

.connection-group:not(.selected) .connection-path:hover {
  stroke-width: 3 !important;
  filter: brightness(1.3);
}
</style>
