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
    data-canvas-target="panel"
    :data-panel-id="panel.id"
    :class="['canvas-panel', { selected: isSelected, dragging: isDragging }]"
    :style="panelStyle"
    @pointerdown="handlePointerDown"
    @click.stop="store.selectPanel(panel.id)"
    @contextmenu.stop="handleContextMenu"
  >
    <!-- 颜色标签条（左侧 4px 宽） -->
    <div
      v-if="colorBarVisible"
      class="color-bar"
      :style="{ background: colorBarColor }"
    />

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
        :data-canvas-target="'control'"
        @pointerdown.stop="(e) => startResize(handle.dir, e)"
      />
    </template>

    <!-- 输出锚点（右下角） -->
    <div
      v-if="panel.type !== 'placeholder'"
      class="anchor-point anchor-output"
      data-canvas-target="anchor"
      @pointerdown.stop="startConnectionDrag"
    />

    <!-- 输入锚点（左上角） -->
    <div
      v-if="panel.type !== 'placeholder'"
      class="anchor-point anchor-input"
      data-canvas-target="anchor"
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

const COLOR_MAP = {
  blue: 'rgba(80, 140, 255, 0.85)',
  green: 'rgba(80, 200, 160, 0.85)',
  orange: 'rgba(255, 180, 80, 0.85)',
  red: 'rgba(255, 120, 120, 0.85)',
  purple: 'rgba(160, 120, 255, 0.85)',
}

const colorBarColor = computed(() => COLOR_MAP[props.panel.content?.color] || 'transparent')
const colorBarVisible = computed(() => !!props.panel.content?.color)

const panelTitle = computed(() => {
  const base = panelTypeLabels[props.panel.type]
  // 优先显示用户自定义的 name
  if (props.panel.content?.name) return props.panel.content.name
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

/** 面板拖拽（选中面板体区域） */
function handlePointerDown(e) {
  if (e.button !== 0) return
  // 忽略手柄和按钮区域
  if (e.target.classList.contains('resize-handle') ||
      e.target.classList.contains('action-icon')) {
    return
  }
  store.selectPanel(props.panel.id)
}

/** 开始拖拽移动（通过头部拖拽手柄） */
function startDrag(e) {
  e.preventDefault()
  isDragging.value = true

  const el = panelRef.value
  const dragStart = { x: e.clientX, y: e.clientY }
  const panelStart = { x: props.panel.x, y: props.panel.y }

  // 护栏：拖动面板期间，画布绝对不能平移
  store._isDraggingPanel = true
  // 仅在拖拽开始时压入一次快照，避免每帧都污染历史栈
  store.pushSnapshot()

  // 使用 setPointerCapture + 元素级别监听，不会泄漏
  el.setPointerCapture(e.pointerId)

  const onMove = (ev) => {
    // 用 _updatePanelDirect 绕过 pushSnapshot，提升拖拽性能
    const dx = (ev.clientX - dragStart.x) / store.viewport.zoom
    const dy = (ev.clientY - dragStart.y) / store.viewport.zoom
    store._updatePanelDirect(props.panel.id, {
      x: panelStart.x + dx,
      y: panelStart.y + dy,
    })
  }

  const onUp = () => {
    isDragging.value = false
    store._isDraggingPanel = false
    el.releasePointerCapture(e.pointerId)
    el.removeEventListener('pointermove', onMove)
    el.removeEventListener('pointerup', onUp)
  }

  // 在 captured element 上监听，而非 window
  el.addEventListener('pointermove', onMove)
  el.addEventListener('pointerup', onUp)
}

/** 开始缩放 */
function startResize(dir, e) {
  e.preventDefault()
  e.stopPropagation()

  const el = panelRef.value
  const resizeDir = dir
  const resizeStart = {
    dir,
    x: props.panel.x,
    y: props.panel.y,
    w: props.panel.width,
    h: props.panel.height,
    sx: e.clientX,  // 修复：用真实事件坐标初始化
    sy: e.clientY,  // 修复：用真实事件坐标初始化
  }

  // 护栏：缩放期间画布不能平移
  store._isDraggingPanel = true
  // 仅在缩放开始时压入一次快照
  store.pushSnapshot()

  el.setPointerCapture(e.pointerId)

  const onMove = (ev) => {
    const dx = (ev.clientX - resizeStart.sx) / store.viewport.zoom
    const dy = (ev.clientY - resizeStart.sy) / store.viewport.zoom

    let { x, y, w, h } = { ...resizeStart }

    if (resizeDir.includes('e')) w = Math.max(150, resizeStart.w + dx)
    if (resizeDir.includes('w')) {
      w = Math.max(150, resizeStart.w - dx)
      if (w > 150) x = resizeStart.x + dx
    }
    if (resizeDir.includes('s')) h = Math.max(100, resizeStart.h + dy)
    if (resizeDir.includes('n')) {
      h = Math.max(100, resizeStart.h - dy)
      if (h > 100) y = resizeStart.y + dy
    }

    // 拖拽过程中直接更新，绕过 pushSnapshot
    store._updatePanelDirect(props.panel.id, { x, y, w, h })
  }

  const onUp = () => {
    store._isDraggingPanel = false
    el.releasePointerCapture(e.pointerId)
    el.removeEventListener('pointermove', onMove)
    el.removeEventListener('pointerup', onUp)
  }

  el.addEventListener('pointermove', onMove)
  el.addEventListener('pointerup', onUp)
}

/** 连线拖拽 */
function startConnectionDrag(e) {
  e.preventDefault()
  e.stopPropagation()

  // 判断是输入锚点（左上角，class 包含 anchor-input）还是输出锚点（右下角）
  const isInput = e.target.classList.contains('anchor-input')
  const anchorType = isInput ? 'input' : 'output'

  store.startConnecting(props.panel.id, anchorType)

  const onMove = (ev) => {
    store.updateConnecting(ev.clientX, ev.clientY)
  }

  const onUp = (ev) => {
    // 查找鼠标释放位置是否命中目标锚点
    const target = document.elementFromPoint(ev.clientX, ev.clientY)
    const targetAnchor = target?.closest?.('[data-canvas-target="anchor"]')
    let targetPanelId = null
    let targetAnchorType = null

    if (targetAnchor) {
      const panelEl = targetAnchor.closest('[data-canvas-target="panel"]')
      targetPanelId = store.panels.find(
        (p) => p.id === panelEl?.getAttribute('data-panel-id'),
      )?.id
      targetAnchorType = targetAnchor.classList.contains('anchor-input') ? 'input' : 'output'
    } else {
      // 未命中锚点，尝试看是否命中面板
      const panelEl = target?.closest?.('[data-canvas-target="panel"]')
      targetPanelId = store.panels.find(
        (p) => p.id === panelEl?.getAttribute('data-panel-id'),
      )?.id
      if (targetPanelId) {
        targetAnchorType = anchorType === 'output' ? 'input' : 'output'
      }
    }

    if (targetPanelId && targetAnchorType) {
      store.endConnecting(targetPanelId, targetAnchorType)
    } else {
      store.cancelConnecting()
    }

    // 修复：连线结束后必须清理 window 级监听器，避免多次操作后状态错乱
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }

  // 连线拖拽使用 window 级监听，因为临时虚线需要跟随鼠标到整个画布区域
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

/** 右键菜单 */
function handleContextMenu(e) {
  e.preventDefault()
  store.selectPanel(props.panel.id)
  // 发出事件让父级处理菜单显示
  emit('contextmenu', {
    event: e,
    panelId: props.panel.id,
    targetType: 'panel',
  })
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

const emit = defineEmits(['contextmenu'])
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
  contain: layout style paint;  /* 性能优化：隔离渲染 */
}

/* 颜色标签条 */
.color-bar {
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  z-index: 1;
  pointer-events: none;
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
  width: 14px;
  height: 14px;
  background: #508cff;
  border: 2px solid #fff;
  border-radius: 50%;
  cursor: crosshair;
  z-index: 5;
  opacity: 0;
  transition: opacity 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
  box-shadow: 0 0 0 0 rgba(80, 140, 255, 0);
}

.canvas-panel:hover .anchor-point,
.canvas-panel.selected .anchor-point {
  opacity: 1;
}

/* 连线模式下锚点始终可见，并带脉冲呼吸效果 */
.connecting-mode .anchor-point {
  opacity: 0.9;
  box-shadow: 0 0 0 4px rgba(80, 140, 255, 0.15);
  animation: anchor-pulse 1.6s ease-in-out infinite;
}

@keyframes anchor-pulse {
  0%, 100% { box-shadow: 0 0 0 4px rgba(80, 140, 255, 0.15); }
  50% { box-shadow: 0 0 0 8px rgba(80, 140, 255, 0.05); }
}

.connecting-mode .anchor-point:hover {
  opacity: 1;
  transform: scale(1.4);
  box-shadow: 0 0 0 6px rgba(80, 140, 255, 0.3);
}

.anchor-point:hover {
  transform: scale(1.4);
  box-shadow: 0 0 8px rgba(80, 140, 255, 0.6);
}

.anchor-point:active {
  transform: scale(1.2);
}

/* 区分输入/输出锚点颜色 */
.anchor-output {
  bottom: -7px;
  right: -7px;
}

.anchor-input {
  top: -7px;
  left: -7px;
  background: #a078ff;  /* 紫色区分输入侧 */
}

.connecting-mode .anchor-input {
  background: #a078ff;
}
</style>
