<!-- =====================================================
     CanvasConnectionsLayer 画布连线层
     - 渲染节点之间的贝塞尔曲线连线
     - 选中/未选中样式（activeStroke 发光 / muted 半透明）
     - 透明热区路径（strokeWidth 16）便于点击命中
     - 拖拽创建连线时显示虚线临时路径
     - 1:1 复刻参考项目 canvas-connections 的视觉与交互
     ===================================================== -->

<script setup>
import { computed } from 'vue'
import { useCanvasStore } from '@/stores/canvas'

// ---------- Props ----------
const props = defineProps({
  // 连线数组；不传则使用 store.connections
  connections: { type: Array, default: null },
  // 节点数组；不传则使用 store.panels
  panels: { type: Array, default: null },
  // 当前选中的连线 id；不传则使用 store.selectedConnectionId
  selectedConnectionId: { type: String, default: null },
  // 拖拽中的临时连线状态；不传则使用 store.connecting
  connecting: { type: Object, default: null },
  // 主题 token 对象；不传则使用 store.canvasTheme
  theme: { type: Object, default: null },
})

// ---------- Emits ----------
const emit = defineEmits([
  'select-connection',  // 选中连线，payload: connectionId
  'delete-connection',  // 删除连线（右键），payload: connectionId
  'start-connecting',   // 从锚点开始拖（接口预留，由节点组件触发）
  'update-connecting',  // 拖拽中（接口预留，由节点组件触发）
  'end-connecting',     // 在目标锚点释放（接口预留，由节点组件触发）
])

const store = useCanvasStore()

// ---------- 实际使用的数据（props 优先，回退到 store）----------
const currentConnections = computed(() => props.connections || store.connections)
const currentPanels = computed(() => props.panels || store.panels)
const currentSelectedId = computed(() =>
  props.selectedConnectionId !== null ? props.selectedConnectionId : store.selectedConnectionId,
)
const currentConnecting = computed(() => props.connecting || store.connecting)
const currentTheme = computed(() => props.theme || store.canvasTheme)

// ---------- 工具：根据 id 查找节点 ----------
function getPanelById(id) {
  return currentPanels.value.find((p) => p.id === id) || null
}

// ---------- 计算贝塞尔曲线路径 ----------
// 从源节点右侧中点到目标节点左侧中点，曲率为距离的 50%（最小 50）
function computePath(from, to) {
  const startX = from.x + from.width
  const startY = from.y + from.height / 2
  const endX = to.x
  const endY = to.y + to.height / 2
  const dx = Math.abs(endX - startX)
  const curvature = Math.max(dx * 0.5, 50)
  return `M ${startX} ${startY} C ${startX + curvature} ${startY}, ${endX - curvature} ${endY}, ${endX} ${endY}`
}

// ---------- 已建立连线路径列表 ----------
const connectionPaths = computed(() => {
  const result = []
  for (const conn of currentConnections.value) {
    const from = getPanelById(conn.source_panel_id)
    const to = getPanelById(conn.target_panel_id)
    if (!from || !to) continue
    result.push({
      id: conn.id,
      path: computePath(from, to),
      active: conn.id === currentSelectedId.value,
    })
  }
  return result
})

// ---------- 拖拽中的临时连线路径 ----------
// 根据源锚点类型决定方向：source 锚点从节点右侧出发，target 锚点从节点左侧出发
const connectingPath = computed(() => {
  const c = currentConnecting.value
  if (!c) return null

  const sourcePanel = getPanelById(c.sourcePanelId)
  if (!sourcePanel) return null

  let startX, startY, endX, endY
  if (c.sourceAnchorType === 'source') {
    // 从源节点右侧输出锚点出发，到鼠标位置
    startX = sourcePanel.x + sourcePanel.width
    startY = sourcePanel.y + sourcePanel.height / 2
    endX = c.endWorld.x
    endY = c.endWorld.y
  } else {
    // 从鼠标位置出发，到源节点左侧输入锚点
    startX = c.endWorld.x
    startY = c.endWorld.y
    endX = sourcePanel.x
    endY = sourcePanel.y + sourcePanel.height / 2
  }

  // 临时连线曲率为距离的 50%（无最小值限制）
  const distance = Math.abs(endX - startX)
  const curvature = distance * 0.5
  return `M ${startX} ${startY} C ${startX + curvature} ${startY}, ${endX - curvature} ${endY}, ${endX} ${endY}`
})

// ---------- 选中连线 ----------
function handleSelectConnection(id) {
  // 兼容旧用法：直接更新 store 选中状态
  if (!props.connections) {
    store.selectedConnectionId = id
    store.selectedPanelId = null
    store.selectedPanelIds = []
  }
  emit('select-connection', id)
}

// ---------- 删除连线（右键触发）----------
function handleDeleteConnection(id) {
  // 兼容旧用法：直接调用 store 删除
  if (!props.connections) {
    store.deleteConnection(id)
    if (store.selectedConnectionId === id) {
      store.selectedConnectionId = null
    }
  }
  emit('delete-connection', id)
}
</script>

<template>
  <svg class="canvas-connections-layer" xmlns="http://www.w3.org/2000/svg">
    <!-- 已建立连线 -->
    <g
      v-for="conn in connectionPaths"
      :key="conn.id"
      :data-connection-id="conn.id"
      class="connection-group"
    >
      <!-- 透明热区路径（strokeWidth 16，便于点击命中）-->
      <path
        :d="conn.path"
        stroke="transparent"
        :stroke-width="16"
        fill="none"
        class="connection-hit"
        @click.stop="handleSelectConnection(conn.id)"
        @contextmenu.prevent.stop="handleDeleteConnection(conn.id)"
      />
      <!-- 可见路径：选中时 activeStroke + 发光；未选中时 muted + 半透明 -->
      <path
        :d="conn.path"
        :stroke="conn.active ? currentTheme.node.activeStroke : currentTheme.node.muted"
        :stroke-width="conn.active ? 3 : 2"
        :stroke-opacity="conn.active ? 1 : 0.82"
        fill="none"
        :style="{
          filter: conn.active ? `drop-shadow(0 0 8px ${currentTheme.node.activeStroke}66)` : 'none',
          pointerEvents: 'none',
        }"
      />
    </g>

    <!-- 拖拽中的临时连线（虚线路径）-->
    <path
      v-if="connectingPath"
      :d="connectingPath"
      :stroke="currentTheme.node.activeStroke"
      :stroke-width="2"
      fill="none"
      stroke-dasharray="5,5"
      class="connection-preview"
    />
  </svg>
</template>

<style scoped>
.canvas-connections-layer {
  position: absolute;
  left: 0;
  top: 0;
  width: 1px;
  height: 1px;
  overflow: visible;
  pointer-events: none;
}

.connection-group {
  pointer-events: auto;
}

.connection-hit {
  cursor: pointer;
  pointer-events: stroke;
}

.connection-preview {
  pointer-events: none;
}
</style>
