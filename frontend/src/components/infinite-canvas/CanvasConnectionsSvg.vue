/* =====================================================
 * 连线 SVG 层
 * - 绘制所有贝塞尔曲线连线（水平流动：from 右中点 → to 左中点）
 * - 颜色区分类型（任务流=蓝色，手动=灰色）
 * - 支持拖拽创建连线时的临时虚线
 * - 选中连线时高亮 + 删除按钮
 * - 选中面板时，联动高亮上下游连线与节点
 * - 渲染对齐参考线（Task 6）：拖动节点时根据 store.alignmentGuides
 *   绘制世界坐标下的红色虚线参考线（SVG DOM 顺序即 z-order，
 *   放在所有连线之后以保证绘制在最上层，最为醒目）
 * - 监听 store.pendingAutoConnect（Task 6：自动连线）
 *   延迟 200ms 后调用 store.autoConnect 完成新连线创建
 * ===================================================== */

<template>
  <!-- viewBox 让 SVG 直接理解世界坐标范围（-50000 到 +50000），内部 path 可以直接使用 panel.x/panel.y 等世界坐标。
       不再使用 CSS transform translate(-50000, -50000)，避免世界坐标与 SVG 内部坐标的双重平移导致连线不可见。 -->
  <svg class="canvas-connections" viewBox="-50000 -50000 100000 100000">
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
        <polygon points="0 0, 10 3.5, 0 7" :fill="theme.connection.active" />
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
        <polygon points="0 0, 10 3.5, 0 7" :fill="theme.connection.muted" />
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
      <!-- 加宽透明 hit area，便于点击曲线本身 -->
      <path
        :d="getPathD(conn)"
        fill="none"
        stroke="transparent"
        stroke-width="16"
        pointer-events="stroke"
        class="connection-hit"
      />
      <!-- 可见曲线 -->
      <path
        :d="getPathD(conn)"
        :fill="none"
        :stroke="getStrokeColor(conn)"
        :stroke-width="getStrokeWidth(conn)"
        :marker-end="getMarker(conn)"
        :style="{ filter: getFilter(conn) }"
        pointer-events="none"
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
      :stroke="theme.connection.active"
      stroke-width="2"
      stroke-dasharray="6 4"
      pointer-events="none"
    />

    <!-- 对齐参考线（Task 6）：根据 store.alignmentGuides 渲染
         - 放在所有连线之后（DOM 顺序即 z-order），保证绘制在最上层
         - 线段端点 ±50000 对应世界坐标全画布范围（与 SVG viewBox="-50000 -50000 100000 100000" 配套）
         - pointer-events="none" 不阻挡节点拖动 -->
    <g v-if="hasAlignmentGuides" class="alignment-guides" pointer-events="none">
      <!-- 垂直线：沿 x 坐标的竖线（对齐 left/center/right） -->
      <line
        v-for="x in store.alignmentGuides.vertical"
        :key="`v-${x}`"
        :x1="x" :y1="-50000"
        :x2="x" :y2="50000"
        :stroke="guideColor"
        stroke-width="1"
        stroke-dasharray="4 4"
      />
      <!-- 水平线：沿 y 坐标的横线（对齐 top/center/bottom） -->
      <line
        v-for="y in store.alignmentGuides.horizontal"
        :key="`h-${y}`"
        :x1="-50000" :y1="y"
        :x2="50000" :y2="y"
        :stroke="guideColor"
        stroke-width="1"
        stroke-dasharray="4 4"
      />
    </g>
  </svg>
</template>

<script setup>
import { computed, watch, ref } from 'vue'
import { useCanvasStore } from '@/stores/canvas'

const store = useCanvasStore()
const theme = computed(() => store.canvasTheme)

const connections = computed(() => store.connections)
const connecting = computed(() => store._connecting)
const isConnecting = computed(() => !!connecting.value)

/** 选中面板 id 变化时重新计算联动高亮连线集合，避免每帧重复扫所有连线 */
const relatedConnections = computed(() => {
  if (!store.selectedPanelId) return new Set()
  return store.relatedHighlight(store.selectedPanelId).connections
})

/** 起点 = source 锚点（右侧中点），终点 = target 锚点（左侧中点） */
function getAnchorPoints(source, target) {
  const sx = source.x + source.width
  const sy = source.y + source.height / 2
  const tx = target.x
  const ty = target.y + target.height / 2
  // 水平流动贝塞尔曲线：控制点水平延伸，最小 50 避免短距离过陡
  const curvature = Math.max(Math.abs(tx - sx) * 0.5, 50)
  return {
    sx, sy, tx, ty,
    c1x: sx + curvature,
    c1y: sy,
    c2x: tx - curvature,
    c2y: ty,
  }
}

/** 计算贝塞尔曲线路径 */
function getPathD(conn) {
  const source = store.panels.find((p) => p.id === conn.source_panel_id)
  const target = store.panels.find((p) => p.id === conn.target_panel_id)
  if (!source || !target) return ''

  const { sx, sy, tx, ty, c1x, c1y, c2x, c2y } = getAnchorPoints(source, target)
  return `M ${sx} ${sy} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${tx} ${ty}`
}

/** 计算临时连线路径（拖拽中） */
const getTempConnectionPath = computed(() => {
  const c = connecting.value
  if (!c) return ''

  const source = store.panels.find((p) => p.id === c.sourcePanelId)
  if (!source) return ''

  // source 锚点（右侧中点）or target 锚点（左侧中点）
  const sx = c.anchorType === 'source' ? source.x + source.width : source.x
  const sy = source.y + source.height / 2

  const tx = c.worldX
  const ty = c.worldY

  const curvature = Math.max(Math.abs(tx - sx) * 0.5, 50)
  const c1x = sx + curvature
  const c1y = sy
  const c2x = tx - curvature
  const c2y = ty

  return `M ${sx} ${sy} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${tx} ${ty}`
})

/** 计算连线中点（用于放置删除按钮） */
function getMidpoint(conn) {
  const source = store.panels.find((p) => p.id === conn.source_panel_id)
  const target = store.panels.find((p) => p.id === conn.target_panel_id)
  if (!source || !target) return { x: 0, y: 0 }

  const { sx, sy, tx, ty, c1x, c1y, c2x, c2y } = getAnchorPoints(source, target)

  // 三次贝塞尔曲线中点：t=0.5 的插值
  const t = 0.5
  const mt = 1 - t
  return {
    x: mt*mt*mt*sx + 3*mt*mt*t*c1x + 3*mt*t*t*c2x + t*t*t*tx,
    y: mt*mt*mt*sy + 3*mt*mt*t*c1y + 3*mt*t*t*c2y + t*t*t*ty,
  }
}

/** 是否处于"高亮"状态（被选中 或 属于选中面板的上下游） */
function isHighlightedConn(conn) {
  return conn.id === store.selectedConnectionId || relatedConnections.value.has(conn.id)
}

function getStrokeColor(conn) {
  return isHighlightedConn(conn)
    ? 'var(--canvas-connection-active)'
    : 'var(--canvas-connection-muted)'
}

function getStrokeWidth(conn) {
  return isHighlightedConn(conn) ? 3 : 2
}

function getFilter(conn) {
  return isHighlightedConn(conn)
    ? 'drop-shadow(0 0 8px var(--canvas-connection-active))'
    : 'none'
}

function getMarker(conn) {
  return conn.type === 'auto' ? 'url(#arrow-blue)' : 'url(#arrow-gray)'
}

// ===== Task 6: 对齐参考线渲染 =====
/** 是否需要渲染对齐参考线（任一方向有值即可） */
const hasAlignmentGuides = computed(() => {
  const g = store.alignmentGuides
  return !!g && ((g.vertical?.length ?? 0) > 0 || (g.horizontal?.length ?? 0) > 0)
})
/** 参考线颜色：警告红，醒目提示对齐位置 */
const guideColor = computed(() => '#ff4d4f')

// ===== Task 6: 自动连线 pending 监听 =====
// 监听 store.pendingAutoConnect 的变化，延迟 200ms 后调用 autoConnect 创建连线
// - 同一时刻只允许一个 pending，新的会替换旧的（旧的 timer 被清掉）
// - 防循环：用组件本地变量记录 watcher 自己刚刚设置的 timer，
//   当 pending.timer 已是本组件设置的值时跳过，避免无限递归
const lastAutoConnectTimer = ref(null)
watch(() => store.pendingAutoConnect, (pending) => {
  if (!pending) {
    lastAutoConnectTimer.value = null
    return
  }
  const { sourcePanelId, targetPanelId, timer, delay } = pending
  // 如果是本 watcher 刚刚设置的 timer，跳过避免循环
  if (timer && timer === lastAutoConnectTimer.value) return
  // 取消上一个 timer（store action 或前一次 watcher 设置的）
  if (timer) clearTimeout(timer)
  const newTimer = setTimeout(() => {
    if (sourcePanelId && targetPanelId) {
      // autoConnect 内部已处理"已存在则不重复创建"逻辑
      store.autoConnect(sourcePanelId, targetPanelId)
    }
    store.cancelPendingAutoConnect()
  }, delay ?? 200)
  lastAutoConnectTimer.value = newTimer
  // 同步新 timer 回 store（Pinia 允许直接 mutate state，保持响应性）
  store.pendingAutoConnect = { sourcePanelId, targetPanelId, timer: newTimer, delay: delay ?? 200 }
})
</script>

<style scoped>
.canvas-connections {
  position: absolute;
  /* SVG 左上角放在 (-50000, -50000)，配合 viewBox="-50000 -50000 100000 100000"，
     使 SVG 内容坐标系与世界坐标完全对齐：世界坐标 (wx, wy) 的 path 绘制到父元素 (wx, wy) 位置。
     不再使用 CSS transform translate(-50000px, -50000px)，因为 path 已是世界坐标，再平移会导致双重偏移而不可见。 */
  left: -50000px;
  top: -50000px;
  width: 100000px;
  height: 100000px;
  /* SVG 根元素禁用指针事件，避免 10万×10万 的巨大 SVG 拦截锚点/面板的 pointerdown。
     需要交互的子元素（连线 hit area、删除按钮）显式设置 pointer-events: auto/all。 */
  pointer-events: none;
}

.connection-group {
  cursor: pointer;
}

.connection-path {
  transition: stroke-width 0.15s ease, filter 0.15s ease;
}

/* Task 6: 对齐参考线
   - pointer-events: none 保证不阻挡节点拖动（虽然 g 上也写了，双重保险）
   - 红色虚线在视觉上最醒目，便于用户立即捕捉对齐位置 */
.alignment-guides {
  pointer-events: none;
}
</style>
