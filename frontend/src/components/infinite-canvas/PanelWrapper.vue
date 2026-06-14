/* =====================================================
 * 通用面板包装器
 * - 接收 panel prop（x, y, width, height, type, content）
 * - CSS transform 定位
 * - 拖拽移动 + 8 点缩放
 * - 选中样式（蓝色渐变边框 + 发光阴影）
 * - 最小尺寸限制（宽 150px，高 100px）
 * - 动态渲染子组件
 * ===================================================== */

<template>
  <div
    ref="panelRef"
    :data-canvas-target="panel.type === 'placeholder' ? 'panel' : 'panel'"
    :class="['canvas-panel', { selected: isSelected, dragging: isDragging }]"
    :style="panelStyle"
    @pointerdown="handlePointerDown"
    @click.stop="store.selectPanel(panel.id)"
  >
    <!-- 面板头部（拖拽手柄） -->
    <div class="panel-header" @pointerdown.stop="startDrag">
      <span class="panel-title">{{ panelTitle }}</span>
      <div class="panel-actions">
        <el-icon v-if="isSelected" class="action-icon" @click.stop="handleDuplicate">
          <CopyDocument />
        </el-icon>
        <el-icon v-if="isSelected" class="action-icon delete" @click.stop="handleDelete">
          <Delete />
        </el-icon>
      </div>
    </div>

    <!-- 面板内容 -->
    <div class="panel-body">
      <component
        :is="componentMap[panel.type]"
        :panel="panel"
        @update="handleUpdate"
      />
    </div>

    <!-- 8 点缩放手柄 -->
    <template v-if="isSelected">
      <div
        v-for="handle in resizeHandles"
        :key="handle.dir"
        class="resize-handle"
        :class="`handle-${handle.dir}`"
        @pointerdown.stop="startResize(handle.dir)"
      />
    </template>

    <!-- 输出锚点（右下角） -->
    <div
      v-if="panel.type !== 'placeholder'"
      class="anchor-point anchor-output"
      @pointerdown.stop="startConnectionDrag"
    />

    <!-- 输入锚点（左上角） -->
    <div
      v-if="panel.type !== 'placeholder'"
      class="anchor-point anchor-input"
      @pointerdown.stop="startConnectionDrag"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { CopyDocument, Delete } from '@element-plus/icons-vue'
import { useCanvasStore } from '@/stores/canvas'
import ImagePanel from './item-types/ImagePanel.vue'
import VideoPanel from './item-types/VideoPanel.vue'
import TextPanel from './item-types/TextPanel.vue'
import UrlPanel from './item-types/UrlPanel.vue'
import QuickGeneratePanel from './item-types/QuickGeneratePanel.vue'
import FileUploadPanel from './item-types/FileUploadPanel.vue'
import PlaceholderPanel from './item-types/PlaceholderPanel.vue'

const props = defineProps({
  panel: { type: Object, required: true },
})

const store = useCanvasStore()
const panelRef = ref(null)
const isDragging = ref(false)

const isSelected = computed(() => store.selectedPanelId === props.panel.id)

const componentMap = {
  image: ImagePanel,
  video: VideoPanel,
  text: TextPanel,
  url: UrlPanel,
  'quick-generate': QuickGeneratePanel,
  'file-upload': FileUploadPanel,
  placeholder: PlaceholderPanel,
}

const panelTypeLabels = {
  image: '图片预览',
  video: '视频预览',
  text: '文本笔记',
  url: 'URL 链接',
  'quick-generate': '快捷生成',
  'file-upload': '文件上传',
  placeholder: '占位面板',
}

const panelTitle = computed(() => {
  const base = panelTypeLabels[props.panel.type]
  if (props.panel.type === 'text' && props.panel.content?.text) {
    const text = props.panel.content.text
    return text.length > 15 ? text.slice(0, 15) + '...' : text
  }
  return base
})

const panelStyle = computed(() => ({
  transform: `translate(${props.panel.x}px, ${props.panel.y}px)`,
  width: `${props.panel.width}px`,
  height: `${props.panel.height}px`,
  zIndex: props.panel.zIndex || 1,
}))

const resizeHandles = [
  { dir: 'nw' }, { dir: 'n' }, { dir: 'ne' },
  { dir: 'w' },                                         { dir: 'e' },
  { dir: 'sw' }, { dir: 's' }, { dir: 'se' },
]

let isPanning = false
let isResizing = false
let dragStart = { x: 0, y: 0 }
let panelStart = { x: 0, y: 0 }
let resizeDir = ''
let resizeStart = {}

/** 面板拖拽 */
function handlePointerDown(e) {
  if (e.button !== 0) return
  if (e.target.classList.contains('resize-handle') ||
      e.target.classList.contains('action-icon') ||
      e.target.closest('.panel-header')?.dragHandled) {
    return
  }
  store.selectPanel(props.panel.id)
}

/** 开始拖拽移动 */
function startDrag(e) {
  e.preventDefault()
  isDragging.value = true
  const rect = panelRef.value.getBoundingClientRect()
  const worldPos = store.screenToWorld(rect.left, rect.top)
  dragStart = { x: e.clientX, y: e.clientY }
  panelStart = { x: props.panel.x, y: props.panel.y }

  panelRef.value.setPointerCapture(e.pointerId)

  const onMove = (ev) => {
    const dx = (ev.clientX - dragStart.x) / store.viewport.zoom
    const dy = (ev.clientY - dragStart.y) / store.viewport.zoom
    store.updatePanel(props.panel.id, {
      x: panelStart.x + dx,
      y: panelStart.y + dy,
    })
  }

  const onUp = () => {
    isDragging.value = false
    panelRef.value?.releasePointerCapture(e.pointerId)
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }

  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

/** 开始缩放 */
function startResize(dir) {
  resizeDir = dir
  resizeStart = {
    x: props.panel.x,
    y: props.panel.y,
    w: props.panel.width,
    h: props.panel.height,
    sx: 0,
    sy: 0,
  }
  // 需要获取面板的屏幕坐标
  const rect = panelRef.value.getBoundingClientRect()
  // 这里用事件位置初始化
  const onMove = (ev) => {
    const dx = (ev.clientX - resizeStart.sx) / store.viewport.zoom
    const dy = (ev.clientY - resizeStart.sy) / store.viewport.zoom

    let { x, y, w, h } = { ...resizeStart }

    if (dir.includes('e')) w = Math.max(150, resizeStart.w + dx)
    if (dir.includes('w')) {
      w = Math.max(150, resizeStart.w - dx)
      if (w > 150) x = resizeStart.x + dx
    }
    if (dir.includes('s')) h = Math.max(100, resizeStart.h + dy)
    if (dir.includes('n')) {
      h = Math.max(100, resizeStart.h - dy)
      if (h > 100) y = resizeStart.y + dy
    }

    store.updatePanel(props.panel.id, { x, y, w, h })
  }

  const onUp = () => {
    resizeDir = ''
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }

  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

/** 连线拖拽 */
function startConnectionDrag(e) {
  // TODO: 实现连线拖拽交互（Phase 4）
}

function handleUpdate(changes) {
  store.updatePanel(props.panel.id, changes)
}

function handleDuplicate() {
  store.duplicatePanel(props.panel.id)
}

function handleDelete() {
  store.deletePanel(props.panel.id)
}
</script>

<style scoped>
.canvas-panel {
  position: absolute;
  background: rgba(20, 30, 50, 0.85);
  border: 1px solid rgba(100, 150, 220, 0.2);
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(12px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: box-shadow 0.15s ease, border-color 0.15s ease;
  min-width: 150px;
  min-height: 100px;
}

.canvas-panel:hover {
  border-color: rgba(100, 150, 220, 0.35);
  box-shadow: 0 4px 32px rgba(0, 0, 0, 0.4);
}

.canvas-panel.selected {
  border: 2px solid transparent;
  background-image: linear-gradient(rgba(20, 30, 50, 0.85), rgba(20, 30, 50, 0.85)),
    linear-gradient(135deg, #508cff, #a078ff);
  background-clip: padding-box, border-box;
  box-shadow: 0 0 24px rgba(100, 150, 255, 0.2), 0 4px 24px rgba(0, 0, 0, 0.3);
}

.canvas-panel.dragging {
  opacity: 0.85;
  z-index: 9999 !important;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 32px;
  padding: 0 10px;
  background: rgba(15, 22, 38, 0.5);
  border-bottom: 1px solid rgba(100, 150, 220, 0.12);
  cursor: grab;
  font-size: 12px;
  color: #8ba3c9;
  user-select: none;
}

.panel-header:active {
  cursor: grabbing;
}

.panel-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.panel-actions {
  display: flex;
  gap: 4px;
}

.action-icon {
  cursor: pointer;
  font-size: 14px;
  color: #6b84aa;
  transition: color 0.15s;
}

.action-icon:hover {
  color: #a0d4ff;
}

.action-icon.delete:hover {
  color: #ff6b6b;
}

.panel-body {
  flex: 1;
  padding: 8px;
  overflow: hidden;
  position: relative;
}

/* 8 点缩放手柄 */
.resize-handle {
  position: absolute;
  width: 10px;
  height: 10px;
  background: #508cff;
  border: 1px solid #fff;
  border-radius: 50%;
  z-index: 10;
}

.handle-nw { top: -5px; left: -5px; cursor: nw-resize; }
.handle-n  { top: -5px; left: 50%; margin-left: -5px; cursor: n-resize; }
.handle-ne { top: -5px; right: -5px; cursor: ne-resize; }
.handle-w  { top: 50%; left: -5px; margin-top: -5px; cursor: w-resize; }
.handle-e  { top: 50%; right: -5px; margin-top: -5px; cursor: e-resize; }
.handle-sw { bottom: -5px; left: -5px; cursor: sw-resize; }
.handle-s  { bottom: -5px; left: 50%; margin-left: -5px; cursor: s-resize; }
.handle-se { bottom: -5px; right: -5px; cursor: se-resize; }

/* 连线锚点 */
.anchor-point {
  position: absolute;
  width: 12px;
  height: 12px;
  background: #508cff;
  border: 2px solid #fff;
  border-radius: 50%;
  cursor: crosshair;
  z-index: 5;
  opacity: 0;
  transition: opacity 0.15s, transform 0.15s;
}

.canvas-panel:hover .anchor-point,
.canvas-panel.selected .anchor-point {
  opacity: 1;
}

.anchor-point:hover {
  transform: scale(1.3);
}

.anchor-output {
  bottom: -6px;
  right: -6px;
}

.anchor-input {
  top: -6px;
  left: -6px;
}
</style>
