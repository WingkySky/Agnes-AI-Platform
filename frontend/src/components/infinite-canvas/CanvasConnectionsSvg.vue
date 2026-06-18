<!-- =====================================================
     CanvasConnectionsSvg 连线渲染层
     - 渲染所有连线为贝塞尔曲线
     - 渲染正在拖拽的临时连线（store._connecting）
     - 渲染节点锚点圆点（hover 高亮）
     - 处理连线点击选中、锚点拖拽开始
     - emit connect-start / connect-end / select-connection
     ===================================================== -->

<template>
  <svg class="connections-svg" :style="svgStyle">
    <!-- 已有连线 -->
    <g
      v-for="conn in connectionPaths"
      :key="conn.id"
      class="connection-group"
      :data-conn-id="conn.id"
      :class="{ active: conn.id === store.selectedConnectionId }"
    >
      <!-- 连线点击区域（透明加粗，便于选中） -->
      <path
        :d="conn.path"
        class="connection-hit"
        @click.stop="onConnectionClick(conn.id)"
        @contextmenu.prevent.stop
      />
      <!-- 连线可见路径 -->
      <path :d="conn.path" class="connection-path" />
    </g>

    <!-- 正在拖拽的临时连线 -->
    <path
      v-if="tempPath"
      :d="tempPath"
      class="connection-temp"
    />

    <!-- 节点锚点（输入/输出圆点） -->
    <g v-for="panel in anchorPanels" :key="`anchor-${panel.id}`">
      <!-- 输入锚点（左侧） -->
      <circle
        :cx="panel.x"
        :cy="panel.y + panel.height / 2"
        r="6"
        class="anchor-dot anchor-input"
        @mousedown.stop="onAnchorMouseDown($event, panel, 'target')"
        @mouseup.stop="onAnchorMouseUp($event, panel, 'target')"
      />
      <!-- 输出锚点（右侧，Config 节点无输出锚点） -->
      <circle
        v-if="panel.type !== 'config'"
        :cx="panel.x + panel.width"
        :cy="panel.y + panel.height / 2"
        r="6"
        class="anchor-dot anchor-output"
        @mousedown.stop="onAnchorMouseDown($event, panel, 'source')"
        @mouseup.stop="onAnchorMouseUp($event, panel, 'source')"
      />
    </g>
  </svg>
</template>

<script setup>
import { computed } from 'vue'
import { useCanvasStore } from '@/stores/canvas'

const store = useCanvasStore()
const emit = defineEmits(['connect-start', 'connect-end', 'select-connection'])

// SVG 容器样式：覆盖整个画布世界
const svgStyle = computed(() => ({
  position: 'absolute',
  top: '-100000px',
  left: '-100000px',
  width: '200000px',
  height: '200000px',
  overflow: 'visible',
  pointerEvents: 'none',
}))

// 需要渲染锚点的面板（所有可见面板）
const anchorPanels = computed(() => store.visiblePanels)

// ---------- 连线路径计算 ----------

/** 计算锚点位置（世界坐标） */
function getAnchorPos(panel, side) {
  if (side === 'left') {
    return { x: panel.x, y: panel.y + panel.height / 2 }
  }
  return { x: panel.x + panel.width, y: panel.y + panel.height / 2 }
}

/** 生成贝塞尔曲线路径 */
function bezierPath(start, end) {
  const dx = end.x - start.x
  const curvature = Math.max(Math.abs(dx) * 0.5, 50)
  return `M ${start.x} ${start.y} C ${start.x + curvature} ${start.y}, ${end.x - curvature} ${end.y}, ${end.x} ${end.y}`
}

// 所有连线的路径
const connectionPaths = computed(() => {
  const panelMap = new Map(store.panels.map((p) => [p.id, p]))
  return store.connections
    .map((conn) => {
      const source = panelMap.get(conn.source_panel_id)
      const target = panelMap.get(conn.target_panel_id)
      if (!source || !target) return null
      const start = getAnchorPos(source, 'right')
      const end = getAnchorPos(target, 'left')
      return {
        id: conn.id,
        path: bezierPath(start, end),
      }
    })
    .filter(Boolean)
})

// 正在拖拽的临时连线路径
const tempPath = computed(() => {
  if (!store._connecting) return ''
  const source = store.panels.find((p) => p.id === store._connecting.sourcePanelId)
  if (!source) return ''
  // 根据锚点类型决定起点
  const start = store._connecting.anchorType === 'source'
    ? getAnchorPos(source, 'right')
    : getAnchorPos(source, 'left')
  const end = { x: store._connecting.worldX, y: store._connecting.worldY }
  return bezierPath(start, end)
})

// ---------- 事件处理 ----------

/** 连线点击：选中连线 */
function onConnectionClick(connId) {
  emit('select-connection', connId)
}

/** 锚点 mousedown：开始连线拖拽 */
function onAnchorMouseDown(e, panel, anchorType) {
  emit('connect-start', { panelId: panel.id, anchorType })
}

/** 锚点 mouseup：结束连线（命中目标锚点） */
function onAnchorMouseUp(e, panel, anchorType) {
  if (store._connecting) {
    emit('connect-end', { panelId: panel.id, anchorType })
  }
}
</script>

<style scoped>
.connections-svg {
  z-index: 1;
}

.connection-group {
  pointer-events: auto;
}

/* 连线点击区域（透明加粗） */
.connection-hit {
  fill: none;
  stroke: transparent;
  stroke-width: 16;
  cursor: pointer;
}

/* 连线可见路径 */
.connection-path {
  fill: none;
  stroke: var(--canvas-connection-muted);
  stroke-width: 2;
  transition: stroke 0.15s;
}

.connection-group.active .connection-path {
  stroke: var(--canvas-connection-active);
  stroke-width: 3;
  filter: drop-shadow(0 0 6px var(--canvas-connection-active));
}

.connection-group:hover .connection-path {
  stroke: var(--canvas-connection-active);
}

/* 临时拖拽连线 */
.connection-temp {
  fill: none;
  stroke: var(--canvas-connection-active);
  stroke-width: 2;
  stroke-dasharray: 6 4;
  pointer-events: none;
  opacity: 0.8;
}

/* 锚点圆点 */
.anchor-dot {
  pointer-events: auto;
  cursor: crosshair;
  fill: var(--canvas-anchor-fill);
  stroke: var(--canvas-bg);
  stroke-width: 2;
  transition: r 0.15s, fill 0.15s;
}

.anchor-dot:hover {
  r: 8;
}

.anchor-input {
  fill: var(--canvas-anchor-input);
}

.anchor-output {
  fill: var(--canvas-anchor-output);
}
</style>
