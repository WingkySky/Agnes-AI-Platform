<!-- =====================================================
     项目画布视图 ProjectCanvasView
     - J4 双视图中的"画布视图"
     - 复用 InfiniteCanvas 的交互思路（平移/缩放/网格背景）
     - 数据来自后端 project.canvas_data（nodes + edges + viewport）
     - 节点类型：script / character / scene / prop / shot
     - 节点可拖动；拖动后自动保存布局到后端
     - Phase 1 仅做轻量展示与拖动；完整回写将在 Phase 3 实现
     ===================================================== -->

<template>
  <div class="project-canvas-view">
    <!-- 工具栏 -->
    <div class="canvas-toolbar">
      <el-button-group>
        <el-button :icon="Refresh" size="small" @click="reload">刷新</el-button>
        <el-button :icon="Aim" size="small" @click="resetViewport">归位</el-button>
        <el-button :icon="Plus" size="small" @click="zoomIn">放大</el-button>
        <el-button :icon="Minus" size="small" @click="zoomOut">缩小</el-button>
      </el-button-group>
      <span class="zoom-label">{{ Math.round(viewport.zoom * 100) }}%</span>
      <div class="toolbar-right">
        <el-button type="primary" size="small" :icon="Check" :loading="saving" @click="saveLayout">
          保存布局
        </el-button>
      </div>
    </div>

    <!-- 画布主体 -->
    <div
      ref="containerRef"
      class="canvas-container"
      :style="{ cursor: cursorStyle }"
      @pointerdown="onBackgroundPointerDown"
      @wheel.prevent="onWheel"
    >
      <!-- 背景网格 -->
      <div class="canvas-grid" :style="gridStyle" />

      <!-- 世界层（应用 translate + scale 变换） -->
      <div class="canvas-world" :style="{ transform: worldTransform }">
        <!-- 连线层（SVG 覆盖整个节点区域） -->
        <svg class="edges-layer" :width="svgSize.width" :height="svgSize.height">
          <defs>
            <marker
              id="project-canvas-arrow"
              viewBox="0 0 10 10"
              refX="10"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--el-border-color)" />
            </marker>
          </defs>
          <path
            v-for="edge in edges"
            :key="edge.id"
            :d="edgePath(edge)"
            class="edge-path"
            :marker-end="'url(#project-canvas-arrow)'"
          />
        </svg>

        <!-- 节点层 -->
        <div
          v-for="node in nodes"
          :key="node.id"
          class="canvas-node"
          :class="`node-${node.type}`"
          :style="nodeStyle(node)"
          @pointerdown.stop="onNodePointerDown($event, node)"
          @click.stop="onNodeClick(node)"
        >
          <div class="node-header">
            <el-icon class="node-icon"><component :is="nodeIcon(node.type)" /></el-icon>
            <span class="node-title">{{ nodeTitle(node) }}</span>
            <el-tag class="node-type-tag" size="small" effect="plain">{{ typeLabel(node.type) }}</el-tag>
          </div>
          <div class="node-body">
            <div v-if="node.data.active_image_id" class="node-thumb">
              <el-icon><Picture /></el-icon>
            </div>
            <div v-else-if="node.type === 'shot' && node.data.active_frame_image_id" class="node-thumb">
              <el-icon><Picture /></el-icon>
            </div>
            <div v-else class="node-placeholder">
              <el-icon :size="28"><Film /></el-icon>
            </div>
            <div class="node-meta">{{ nodeMeta(node) }}</div>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="nodes.length === 0 && !loading" class="canvas-empty">
        <el-icon :size="48"><DataLine /></el-icon>
        <p>暂无画布节点，请先在管理视图中添加剧本/角色/场景/道具/分镜</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import {
  Refresh, Aim, Plus, Minus, Check,
  Picture, Film, DataLine,
  Document, User, Location, Box, VideoCamera,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/stores/project'

// ================ 类型定义 ================
interface CanvasNode {
  id: string
  type: 'script' | 'character' | 'scene' | 'prop' | 'shot'
  ref_id: number
  position: { x: number; y: number }
  data: Record<string, any>
}

interface CanvasEdge {
  id: string
  source: string
  target: string
  animated?: boolean
}

interface Viewport {
  x: number
  y: number
  zoom: number
}

// ================ Store ================
const projectStore = useProjectStore()

// ================ 响应式状态 ================
const containerRef = ref<HTMLElement | null>(null)
const nodes = ref<CanvasNode[]>([])
const edges = ref<CanvasEdge[]>([])
const viewport = reactive<Viewport>({ x: 0, y: 0, zoom: 0.7 })
const loading = ref(false)
const saving = ref(false)

// 拖动状态
const dragState = reactive({
  isPanning: false,
  isDraggingNode: false,
  draggingNodeId: null as string | null,
  startClientX: 0,
  startClientY: 0,
  initialVpX: 0,
  initialVpY: 0,
  initialNodeX: 0,
  initialNodeY: 0,
  hasMoved: false,
})

// ================ 计算属性 ================
const cursorStyle = computed(() => {
  if (dragState.isPanning) return 'grabbing'
  if (dragState.isDraggingNode) return 'move'
  return 'grab'
})

const worldTransform = computed(
  () => `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})`,
)

const gridStyle = computed(() => {
  const gridSize = 48 * viewport.zoom
  const x = viewport.x % gridSize
  const y = viewport.y % gridSize
  const dotSize = viewport.zoom < 0.12 ? 0.8 : 1.15
  return {
    backgroundImage: `radial-gradient(circle, var(--el-border-color) ${dotSize}px, transparent ${dotSize + 0.2}px)`,
    backgroundSize: `${gridSize}px ${gridSize}px`,
    backgroundPosition: `${x}px ${y}px`,
  }
})

// SVG 覆盖区域：根据节点边界自动计算
const svgSize = computed(() => {
  if (nodes.value.length === 0) return { width: 0, height: 0 }
  let maxX = 0
  let maxY = 0
  for (const n of nodes.value) {
    maxX = Math.max(maxX, n.position.x + 220)
    maxY = Math.max(maxY, n.position.y + 120)
  }
  return { width: maxX + 100, height: maxY + 100 }
})

// ================ 节点辅助函数 ================
function nodeStyle(node: CanvasNode) {
  return {
    left: `${node.position.x}px`,
    top: `${node.position.y}px`,
  }
}

function nodeIcon(type: string) {
  switch (type) {
    case 'script': return Document
    case 'character': return User
    case 'scene': return Location
    case 'prop': return Box
    case 'shot': return VideoCamera
    default: return Film
  }
}

function typeLabel(type: string): string {
  const map: Record<string, string> = {
    script: '剧本',
    character: '角色',
    scene: '场景',
    prop: '道具',
    shot: '分镜',
  }
  return map[type] || type
}

function nodeTitle(node: CanvasNode): string {
  return node.data?.title || node.data?.name || `${typeLabel(node.type)} ${node.ref_id}`
}

function nodeMeta(node: CanvasNode): string {
  if (node.type === 'shot') {
    if (node.data?.active_video_id) return '已生成视频'
    if (node.data?.active_frame_image_id) return '已生成帧图'
    return '未生成'
  }
  if (node.data?.active_image_id) return '已设定形象'
  return '未设定形象'
}

// ================ 连线路径计算 ================
function edgePath(edge: CanvasEdge): string {
  const source = nodes.value.find(n => n.id === edge.source)
  const target = nodes.value.find(n => n.id === edge.target)
  if (!source || !target) return ''
  // 起点：源节点右侧中点；终点：目标节点左侧中点
  const sx = source.position.x + 220
  const sy = source.position.y + 60
  const tx = target.position.x
  const ty = target.position.y + 60
  // 贝塞尔曲线
  const dx = Math.abs(tx - sx) * 0.5
  return `M ${sx} ${sy} C ${sx + dx} ${sy}, ${tx - dx} ${ty}, ${tx} ${ty}`
}

// ================ 视口操作 ================
function resetViewport() {
  viewport.x = 0
  viewport.y = 0
  viewport.zoom = 0.7
}

function zoomIn() {
  viewport.zoom = Math.min(viewport.zoom * 1.2, 5)
}

function zoomOut() {
  viewport.zoom = Math.max(viewport.zoom / 1.2, 0.05)
}

function onWheel(e: WheelEvent) {
  const rect = containerRef.value?.getBoundingClientRect()
  if (!rect) return
  const delta = -e.deltaY
  const factor = Math.pow(1.1, delta / 100)
  const oldZoom = viewport.zoom
  const newZoom = Math.min(Math.max(oldZoom * factor, 0.05), 5)
  if (newZoom === oldZoom) return
  // 以鼠标位置为缩放中心
  const mouseX = e.clientX - rect.left
  const mouseY = e.clientY - rect.top
  const worldX = (mouseX - viewport.x) / oldZoom
  const worldY = (mouseY - viewport.y) / oldZoom
  viewport.x = mouseX - worldX * newZoom
  viewport.y = mouseY - worldY * newZoom
  viewport.zoom = newZoom
}

// ================ 拖动操作 ================
function onBackgroundPointerDown(e: PointerEvent) {
  if (e.button !== 0 && e.button !== 1) return
  dragState.isPanning = true
  dragState.startClientX = e.clientX
  dragState.startClientY = e.clientY
  dragState.initialVpX = viewport.x
  dragState.initialVpY = viewport.y
  dragState.hasMoved = false
  ;(e.currentTarget as HTMLElement)?.setPointerCapture(e.pointerId)
}

function onNodePointerDown(e: PointerEvent, node: CanvasNode) {
  if (e.button !== 0) return
  dragState.isDraggingNode = true
  dragState.draggingNodeId = node.id
  dragState.startClientX = e.clientX
  dragState.startClientY = e.clientY
  dragState.initialNodeX = node.position.x
  dragState.initialNodeY = node.position.y
  dragState.hasMoved = false
  ;(e.currentTarget as HTMLElement)?.setPointerCapture(e.pointerId)
}

function onPointerMove(e: PointerEvent) {
  if (!dragState.isPanning && !dragState.isDraggingNode) return
  const dx = e.clientX - dragState.startClientX
  const dy = e.clientY - dragState.startClientY
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
    dragState.hasMoved = true
  }
  if (dragState.isPanning) {
    viewport.x = dragState.initialVpX + dx
    viewport.y = dragState.initialVpY + dy
  } else if (dragState.isDraggingNode && dragState.draggingNodeId) {
    const node = nodes.value.find(n => n.id === dragState.draggingNodeId)
    if (node) {
      node.position.x = dragState.initialNodeX + dx / viewport.zoom
      node.position.y = dragState.initialNodeY + dy / viewport.zoom
    }
  }
}

function onPointerUp() {
  // 节点拖动结束：标记需保存
  if (dragState.isDraggingNode && dragState.hasMoved) {
    dirty.value = true
  }
  dragState.isPanning = false
  dragState.isDraggingNode = false
  dragState.draggingNodeId = null
}

function onNodeClick(node: CanvasNode) {
  // Phase 1 仅展示信息；后续可扩展为打开编辑面板
  ElMessage.info(`节点：${nodeTitle(node)}（${typeLabel(node.type)} #${node.ref_id}）`)
}

// ================ 数据加载 / 保存 ================
const dirty = ref(false)

async function reload() {
  if (!projectStore.currentProjectId) return
  loading.value = true
  try {
    const data = await projectStore.fetchCanvasLayout()
    if (data && Array.isArray(data.nodes)) {
      nodes.value = data.nodes
      edges.value = data.edges || []
      if (data.viewport) {
        viewport.x = data.viewport.x || 0
        viewport.y = data.viewport.y || 0
        viewport.zoom = data.viewport.zoom || 0.7
      }
      dirty.value = false
    }
  } catch (e: any) {
    ElMessage.error('加载画布失败：' + (e?.message || e))
  } finally {
    loading.value = false
  }
}

async function saveLayout() {
  if (!projectStore.currentProjectId) return
  if (!dirty.value) {
    ElMessage.info('布局无变更')
    return
  }
  saving.value = true
  try {
    const canvasData = {
      nodes: nodes.value,
      edges: edges.value,
      viewport: { x: viewport.x, y: viewport.y, zoom: viewport.zoom },
    }
    await projectStore.saveCanvasLayout(canvasData)
    dirty.value = false
    ElMessage.success('画布布局已保存')
  } catch (e: any) {
    ElMessage.error('保存画布失败：' + (e?.message || e))
  } finally {
    saving.value = false
  }
}

// ================ 生命周期 ================
onMounted(() => {
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  reload()
})

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
})
</script>

<style scoped>
.project-canvas-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  overflow: hidden;
}

/* ================ 工具栏 ================ */
.canvas-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--el-bg-color-page);
  border-bottom: 1px solid var(--el-border-color-light);
}
.zoom-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  min-width: 48px;
}
.toolbar-right {
  margin-left: auto;
}

/* ================ 画布主体 ================ */
.canvas-container {
  position: relative;
  flex: 1;
  overflow: hidden;
  user-select: none;
  -webkit-user-select: none;
}
.canvas-grid {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.5;
}
.canvas-world {
  position: absolute;
  left: 0;
  top: 0;
  transform-origin: 0 0;
}

/* ================ 连线层 ================ */
.edges-layer {
  position: absolute;
  left: 0;
  top: 0;
  pointer-events: none;
  overflow: visible;
}
.edge-path {
  fill: none;
  stroke: var(--el-border-color);
  stroke-width: 1.5;
  opacity: 0.6;
}

/* ================ 节点 ================ */
.canvas-node {
  position: absolute;
  width: 220px;
  height: 120px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
  cursor: move;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.canvas-node:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}
.node-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 13px;
  font-weight: 600;
}
.node-icon {
  color: var(--el-color-primary);
  flex-shrink: 0;
}
.node-title {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.node-type-tag {
  flex-shrink: 0;
}
.node-body {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  overflow: hidden;
}
.node-thumb,
.node-placeholder {
  width: 48px;
  height: 48px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.node-thumb {
  color: var(--el-color-success);
}
.node-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}

/* 节点类型颜色 */
.node-script .node-icon { color: var(--el-color-primary); }
.node-character .node-icon { color: var(--el-color-success); }
.node-scene .node-icon { color: var(--el-color-warning); }
.node-prop .node-icon { color: var(--el-color-info); }
.node-shot .node-icon { color: var(--el-color-danger); }

/* ================ 空状态 ================ */
.canvas-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-secondary);
  pointer-events: none;
}
.canvas-empty p {
  margin-top: 12px;
  font-size: 13px;
}
</style>
