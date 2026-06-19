<!-- =====================================================
     CanvasConnectionsLayer 连线渲染层
     - 基于 canvas store 的 connections 数组渲染所有连线
     - 每条连线使用贝塞尔曲线（SVG path）从 source 节点连到 target 节点
     - 正在拖动的临时连线也在此渲染
     - 支持 hover/选中高亮，点击选中连线可删除
     ===================================================== -->

<template>
  <svg
    class="canvas-connections-layer"
    :style="{
      position: 'absolute',
      left: 0,
      top: 0,
      width: '100%',
      height: '100%',
      pointerEvents: 'none',
      overflow: 'visible',
    }"
  >
    <!-- 定义箭头 -->
    <defs>
      <marker
        id="canvas-arrow"
        viewBox="0 0 10 10"
        refX="8"
        refY="5"
        markerUnits="strokeWidth"
        markerWidth="8"
        markerHeight="8"
        orient="auto-start-reverse"
      >
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#6b9cff" />
      </marker>
      <marker
        id="canvas-arrow-active"
        viewBox="0 0 10 10"
        refX="8"
        refY="5"
        markerUnits="strokeWidth"
        markerWidth="8"
        markerHeight="8"
        orient="auto-start-reverse"
      >
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#a78bff" />
      </marker>
      <marker
        id="canvas-arrow-temp"
        viewBox="0 0 10 10"
        refX="8"
        refY="5"
        markerUnits="strokeWidth"
        markerWidth="8"
        markerHeight="8"
        orient="auto-start-reverse"
      >
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#ffb86b" />
      </marker>
    </defs>

    <!-- 已有连线 -->
    <g v-for="c in visibleConnections" :key="c.id">
      <!-- 加粗透明"命中区"：便于用户点击 -->
      <path
        :d="makePath(c)"
        stroke="transparent"
        stroke-width="14"
        fill="none"
        :style="{ cursor: 'pointer', pointerEvents: 'auto' }"
        @click="handleConnectionClick(c)"
        @dblclick="handleConnectionDelete(c)"
      />
      <!-- 实际可见线 -->
      <path
        :d="makePath(c)"
        :stroke="connectionColor(c)"
        stroke-width="2"
        fill="none"
        :marker-end="isActiveConnection(c) ? 'url(#canvas-arrow-active)' : 'url(#canvas-arrow)'"
        :style="{ transition: 'stroke 0.15s ease, stroke-width 0.15s ease' }"
      />
    </g>

    <!-- 临时连线（拖动中） -->
    <g v-if="tempConnection">
      <path
        :d="tempPath"
        stroke="#ffb86b"
        stroke-width="2"
        stroke-dasharray="6,4"
        fill="none"
        marker-end="url(#canvas-arrow-temp)"
      />
    </g>
  </svg>
</template>

<script setup>
import { computed } from 'vue'
import { useCanvasStore } from '@/stores/canvas'

/* =====================================================
 * 核心逻辑：
 * 1. 获取所有可见面板（panels），构建 id -> panel 映射
 * 2. 对于每条 connection，计算源锚点和目标锚点的世界坐标
 *    → 转换为屏幕坐标
 *    → 生成贝塞尔曲线路径
 * 3. 对于临时连线，源为 _connecting.sourcePanelId，目标为鼠标位置
 * ===================================================== */

const store = useCanvasStore()

/* 面板 id 映射，便于 O(1) 查找 */
const panelMap = computed(() => {
  const map = new Map()
  for (const p of store.panels) {
    map.set(p.id, p)
  }
  return map
})

/* 只渲染两端面板都存在的连线 */
const visibleConnections = computed(() => {
  return store.connections.filter(
    (c) => panelMap.value.has(c.source_panel_id) && panelMap.value.has(c.target_panel_id),
  )
})

/* 正在拖动的临时连线信息 */
const tempConnection = computed(() => store._connecting)

/* =====================================================
 * 锚点位置计算：
 * - source_anchor / target_anchor 的取值：'right-middle' | 'left-middle' | 'top-left' | 'bottom-right'
 * - 返回世界坐标（SVG 在 .canvas-world 内部，受 CSS transform 影响，
 *   所以直接使用世界坐标即可；不要再做 worldToScreen，否则会被双重缩放）
 * ===================================================== */
function getAnchorWorldPos(panel, anchorName) {
  if (!panel) return { x: 0, y: 0 }
  let wx, wy
  const px = panel.x ?? 0
  const py = panel.y ?? 0
  const pw = panel.width ?? 100
  const ph = panel.height ?? 80

  switch (anchorName) {
    case 'right-middle':
      wx = px + pw
      wy = py + ph / 2
      break
    case 'left-middle':
      wx = px
      wy = py + ph / 2
      break
    case 'top-left':
      wx = px
      wy = py
      break
    case 'bottom-right':
      wx = px + pw
      wy = py + ph
      break
    default:
      // 默认右侧中点作为 source
      wx = px + pw
      wy = py + ph / 2
  }
  return { x: wx, y: wy }
}

/* 贝塞尔曲线控制点：水平延伸两点的 0.4 倍水平距离，
 * 使连线呈现平滑的 S 形或水平拖尾。 */
function makeBezierPath(sx, sy, tx, ty) {
  const dx = Math.max(Math.abs(tx - sx), 40)
  const controlOffset = dx * 0.5
  return `M ${sx.toFixed(1)} ${sy.toFixed(1)}
          C ${(sx + controlOffset).toFixed(1)} ${sy.toFixed(1)},
            ${(tx - controlOffset).toFixed(1)} ${ty.toFixed(1)},
            ${tx.toFixed(1)} ${ty.toFixed(1)}`
}

/* 计算一条 connection 的 SVG 路径（全部使用世界坐标，SVG 在 .canvas-world transform 内会自动转到屏幕位置） */
function makePath(conn) {
  const src = panelMap.value.get(conn.source_panel_id)
  const tgt = panelMap.value.get(conn.target_panel_id)
  if (!src || !tgt) return ''

  const { x: sx, y: sy } = getAnchorWorldPos(src, conn.source_anchor || 'right-middle')
  const { x: tx, y: ty } = getAnchorWorldPos(tgt, conn.target_anchor || 'left-middle')
  return makeBezierPath(sx, sy, tx, ty)
}

/* 临时连线：source 节点锚点 → 鼠标位置（store._connecting.worldX/Y 已经是世界坐标）
 * 两者都是世界坐标，直接传入 makeBezierPath 即可 */
const tempPath = computed(() => {
  const tc = tempConnection.value
  if (!tc) return ''
  const src = panelMap.value.get(tc.sourcePanelId)
  if (!src) return ''

  const { x: sx, y: sy } = getAnchorWorldPos(src, 'right-middle')
  // tc.worldX / tc.worldY 已经是世界坐标
  return makeBezierPath(sx, sy, tc.worldX, tc.worldY)
})

/* 连线颜色：普通 / 选中高亮 / 激活关联高亮 */
function isActiveConnection(c) {
  return store.selectedConnectionId === c.id
}

function connectionColor(c) {
  // 根据面板类型返回不同颜色，便于区分
  const src = panelMap.value.get(c.source_panel_id)
  const tgt = panelMap.value.get(c.target_panel_id)
  if (isActiveConnection(c)) return '#a78bff'
  // type 决定颜色
  if (tgt?.type === 'image') return '#6b9cff'
  if (tgt?.type === 'video') return '#ff8ab3'
  if (tgt?.type === 'chat') return '#86e3a6'
  if (tgt?.type === 'config') return '#ffb86b'
  if (src?.type === 'text') return '#9c88ff'
  return '#6b9cff'
}

/* 点击连线 → 选中 */
function handleConnectionClick(c) {
  store.selectConnection(c.id)
}

/* 双击连线 → 删除（常见交互：双击断开） */
function handleConnectionDelete(c) {
  store.deleteConnection(c.id)
}
</script>

<style scoped>
.canvas-connections-layer {
  /* SVG 样式由行内 style 控制 */
}
</style>
