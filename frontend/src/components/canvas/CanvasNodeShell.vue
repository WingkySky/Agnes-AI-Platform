<!-- =====================================================
     CanvasNodeShell 节点通用外壳
     - 所有节点类型（text/image/video/chat/config/frame）共用的外层组件
     - 负责：标题栏（图标/类型名/状态徽标）、输入/输出锚点、拖拽移动、
             右下角尺寸调整、选中高亮、悬停工具栏
     - 内部内容由 `<slot />` 渲染（由各节点类型子组件填充）
     ===================================================== -->

<template>
  <div
    class="canvas-node-shell"
    :class="[
      `node-type-${panel.type}`,
      {
        'is-selected': isSelected,
        'is-locked': panel.content?.locked,
        'is-hover': isHover
      }
    ]"
    :style="shellStyle"
    data-canvas-target="panel"
    :data-panel-id="panel.id"
    @mousedown.stop="handleMouseDown"
    @mouseenter="isHover = true"
    @mouseleave="isHover = false"
  >
    <!-- 节点标题栏：图标 + 类型名 + 状态徽标 + 锁定按钮 -->
    <div class="node-header" @mousedown.stop="handleHeaderMouseDown">
      <el-icon class="node-icon" :size="16">
        <Picture v-if="panel.type === 'image'" />
        <VideoPlay v-else-if="panel.type === 'video'" />
        <Document v-else-if="panel.type === 'text'" />
        <ChatDotRound v-else-if="panel.type === 'chat'" />
        <Setting v-else-if="panel.type === 'config'" />
        <Collection v-else-if="panel.type === 'frame'" />
        <Box v-else />
      </el-icon>

      <span class="node-title">{{ titleLabel }}</span>

      <span v-if="nodeStatus" class="node-status-badge" :class="nodeStatus">
        {{ statusText }}
      </span>

      <!-- 应用上游数据按钮（当节点有上游连接时显示） -->
      <button
        v-if="hasUpstream"
        class="apply-upstream-btn"
        @click.stop="handleApplyUpstream"
        title="应用上游节点数据到此节点"
      >
        <el-icon :size="11"><Link /></el-icon>
        <span>应用上游</span>
      </button>

      <!-- 悬停时的操作工具栏（锁定/删除） -->
      <div v-if="isHover && !panel.content?.locked" class="node-hover-actions" @mousedown.stop>
        <el-icon
          class="hover-action lock"
          :size="14"
          title="锁定节点"
          @click.stop="handleToggleLock"
        >
          <Lock />
        </el-icon>
        <el-icon
          class="hover-action remove"
          :size="14"
          title="删除节点"
          @click.stop="handleRemove"
        >
          <Close />
        </el-icon>
      </div>
      <el-icon v-else-if="isHover && panel.content?.locked" class="hover-action" :size="14" title="已锁定">
        <Unlock />
      </el-icon>
    </div>

    <!-- 内容区（由子组件填充） -->
    <div class="node-body">
      <slot />
    </div>

    <!-- 输入锚点（左侧，作为连线的目标端 target） -->
    <div
      v-if="!isFrame"
      class="node-anchor node-anchor-input"
      title="输入：上游节点连线到此"
      @mousedown.stop="handleAnchorMouseDown('target')"
      @mouseup.stop="handleAnchorMouseUp('target')"
    >
      <el-icon :size="10"><ArrowRight /></el-icon>
    </div>

    <!-- 输出锚点（右侧，作为连线的源端 source） -->
    <div
      v-if="!isFrame"
      class="node-anchor node-anchor-output"
      title="输出：从此拖线连接到下游节点"
      @mousedown.stop="handleAnchorMouseDown('source')"
      @mouseup.stop="handleAnchorMouseUp('source')"
    >
      <el-icon :size="10"><ArrowRight /></el-icon>
    </div>

    <!-- 右下角尺寸调整把手（Frame 节点不支持调整，由子节点自行处理） -->
    <div
      v-if="!isFrame"
      class="node-resize-handle"
      title="拖拽调整尺寸"
      @mousedown.stop="handleResizeMouseDown"
    />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import {
  Picture,
  VideoPlay,
  Document,
  ChatDotRound,
  Setting,
  Collection,
  Lock,
  Unlock,
  Close,
  ArrowRight,
  Box,
  Link,
} from '@element-plus/icons-vue'
import { useCanvasStore } from '@/stores/canvas'
import { useI18n } from '@/i18n'

const props = defineProps({
  /** 当前节点面板对象 */
  panel: {
    type: Object,
    required: true,
  },
})

/** 事件：供外层处理节点级通用动作与锚点连线事件 */
const emit = defineEmits(['action', 'connect-start', 'connect-end'])

const { t } = useI18n()
const store = useCanvasStore()
const isHover = ref(false)

// ===== 计算属性 =====

/** 当前节点是否选中 */
const isSelected = computed(() => {
  return store.selectedPanelIds.includes(props.panel.id)
})

/** frame 节点隐藏锚点与尺寸调整 */
const isFrame = computed(() => props.panel.type === 'frame')

/** 节点外壳的世界坐标样式（x/y/width/height/zIndex） */
const shellStyle = computed(() => ({
  left: `${props.panel.x}px`,
  top: `${props.panel.y}px`,
  width: `${props.panel.width}px`,
  height: `${props.panel.height}px`,
  zIndex: props.panel.zIndex || 1,
}))

/** 节点标题（优先 content.name，其次读取 store.getNodeTypeMeta 的 label） */
const titleLabel = computed(() => {
  if (props.panel.content?.name) return props.panel.content.name
  const meta = store.getNodeTypeMeta?.(props.panel.type)
  if (meta?.label) return meta.label
  const fallback = {
    image: '图片',
    video: '视频',
    text: '文本',
    chat: '对话',
    config: '配置',
    frame: '分组',
  }
  return fallback[props.panel.type] || props.panel.type
})

/** 根据 content.status / resultUrl 推断状态徽标类型：generating/error/done */
const nodeStatus = computed(() => {
  const c = props.panel.content || {}
  if (c.status === 'generating' || c.status === 'processing') return 'generating'
  if (c.status === 'error' || c.status === 'failed') return 'error'
  if (c.resultUrl || c.imageUrl || c.videoUrl) return 'done'
  return null
})

/** 状态文本（与状态一一对应） */
const statusText = computed(() => {
  if (nodeStatus.value === 'generating') return '生成中'
  if (nodeStatus.value === 'error') return '失败'
  if (nodeStatus.value === 'done') return '已完成'
  return ''
})

/** 节点是否有上游连接（连线到此节点） */
const hasUpstream = computed(() =>
  store.connections.some((c) => c.target_panel_id === props.panel.id),
)

/** 节点是否有下游连接（连线从该节点出去） */
const hasDownstream = computed(() =>
  store.connections.some((c) => c.source_panel_id === props.panel.id),
)

// ===== 交互处理 =====

/** 点击节点外壳：单选或多选追加（Ctrl/Cmd + 点击） */
function handleMouseDown(e) {
  const mod = e.metaKey || e.ctrlKey
  if (mod) {
    store.selectPanel(props.panel.id, { append: true })
  } else if (!isSelected.value) {
    store.selectPanel(props.panel.id, { append: false })
  }
}

/** 标题栏拖拽：移动节点（含多选节点同步平移） */
function handleHeaderMouseDown(e) {
  if (props.panel.content?.locked) return
  e.preventDefault()
  e.stopPropagation()

  const startX = e.clientX
  const startY = e.clientY
  const origX = props.panel.x
  const origY = props.panel.y
  const zoom = store.viewport?.zoom || 1

  // 收集其他已选中节点（用于同步平移）
  const otherOffsets = (store.selectedPanelIds || [])
    .filter((id) => id !== props.panel.id)
    .map((id) => {
      const p = store.panels.find((x) => x.id === id)
      return p ? { id: p.id, x: p.x, y: p.y, locked: !!p.content?.locked } : null
    })
    .filter(Boolean)

  store.pushSnapshot()

  function onMove(ev) {
    const screenDx = ev.clientX - startX
    const screenDy = ev.clientY - startY
    // 屏幕坐标差值 → 世界坐标差值（除以 zoom）
    const worldDx = screenDx / zoom
    const worldDy = screenDy / zoom
    store._updatePanelDirect(props.panel.id, { x: origX + worldDx, y: origY + worldDy })
    for (const item of otherOffsets) {
      if (item.locked) continue
      store._updatePanelDirect(item.id, { x: item.x + worldDx, y: item.y + worldDy })
    }
  }

  function onUp() {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }

  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

/** 右下角拖拽：调整尺寸（最小 160 × 120） */
function handleResizeMouseDown(e) {
  if (props.panel.content?.locked) return
  e.preventDefault()
  e.stopPropagation()
  const startX = e.clientX
  const startY = e.clientY
  const origW = props.panel.width
  const origH = props.panel.height
  const MIN_W = 160
  const MIN_H = 120
  const zoom = store.viewport?.zoom || 1

  store.pushSnapshot()

  function onMove(ev) {
    const screenDx = ev.clientX - startX
    const screenDy = ev.clientY - startY
    // 屏幕坐标差值 → 世界坐标差值
    const worldDx = screenDx / zoom
    const worldDy = screenDy / zoom
    store._updatePanelDirect(props.panel.id, {
      width: Math.max(MIN_W, origW + worldDx),
      height: Math.max(MIN_H, origH + worldDy),
    })
  }

  function onUp() {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }

  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

/** 锁定切换：优先调用 store.toggleLock(panelId)，否则手动更新 panel.content.locked */
function handleToggleLock() {
  if (typeof store.toggleLock === 'function') {
    store.toggleLock(props.panel.id)
  } else {
    const panel = store.panels.find((p) => p.id === props.panel.id)
    if (panel) {
      const newLocked = !panel.content?.locked
      store.updatePanel(props.panel.id, {
        content: { ...(panel.content ?? {}), locked: newLocked }
      })
    }
  }
  emit('action', { type: 'toggle-lock', panel: props.panel })
}

/** 删除节点 */
function handleRemove() {
  store.deletePanel(props.panel.id)
  emit('action', { type: 'remove', panel: props.panel })
}

/** 应用上游数据：把上游节点的输出合并到当前节点 */
function handleApplyUpstream() {
  const merged = store.resolveInputs(props.panel.id)
  if (!merged) return
  store.updatePanel(props.panel.id, { content: merged })
  emit('action', { type: 'apply-upstream', panel: props.panel })
}

/** 锚点按下：开始连线 */
function handleAnchorMouseDown(anchorType) {
  if (props.panel.content?.locked) return
  store.startConnecting(props.panel.id, anchorType)
  emit('connect-start', { panelId: props.panel.id, anchorType })
}

/** 锚点松开：结束连线（命中另一锚点时建立连接） */
function handleAnchorMouseUp(anchorType) {
  if (!store._connecting) return
  store.endConnecting(props.panel.id, anchorType)
  emit('connect-end', { panelId: props.panel.id, anchorType })
}
</script>

<style scoped>
.canvas-node-shell {
  position: absolute;
  display: flex;
  flex-direction: column;
  background: var(--canvas-panel-bg, rgba(22, 32, 54, 0.7));
  border: 1px solid var(--canvas-node-border, rgba(120, 170, 230, 0.2));
  border-radius: 12px;
  backdrop-filter: blur(8px);
  overflow: hidden;
  user-select: none;
  transition: box-shadow 0.15s ease, border-color 0.15s ease;
  box-shadow: 0 4px 18px rgba(0, 0, 0, 0.25);
  font-size: 12px;
}

.canvas-node-shell:hover {
  border-color: var(--canvas-node-active-border, #85b2ff);
  box-shadow: 0 6px 24px var(--canvas-node-glow, rgba(100, 150, 255, 0.25));
}

.canvas-node-shell.is-selected {
  border-color: var(--canvas-node-active-border, #85b2ff);
  box-shadow: 0 0 0 1px var(--canvas-node-active-border, #85b2ff),
    0 6px 24px var(--canvas-node-glow, rgba(100, 150, 255, 0.35));
}

.canvas-node-shell.is-locked {
  opacity: 0.85;
}

/* 标题栏（图标 / 类型名 / 状态徽标 / 悬停操作） */
.node-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-bottom: 1px solid rgba(120, 170, 230, 0.15);
  cursor: grab;
  color: var(--canvas-node-title-text, #ffffff);
  font-weight: 600;
  background: rgba(0, 0, 0, 0.15);
}
.node-header:active { cursor: grabbing; }
.node-icon {
  color: var(--agnes-primary, #6b9cff);
  flex-shrink: 0;
}
.node-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.node-status-badge {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 500;
}
.node-status-badge.generating {
  background: rgba(96, 165, 250, 0.2);
  color: #93c5fd;
  animation: status-pulse 1.5s ease-in-out infinite;
}
.node-status-badge.done { background: rgba(74, 222, 128, 0.2); color: #86efac; }
.node-status-badge.error { background: rgba(248, 113, 113, 0.2); color: #fca5a5; }

@keyframes status-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* 应用上游数据按钮 */
.apply-upstream-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  margin-left: 6px;
  font-size: 11px;
  background: rgba(107, 156, 255, 0.15);
  color: #93c5fd;
  border: 1px solid rgba(107, 156, 255, 0.35);
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  white-space: nowrap;
}

.apply-upstream-btn:hover {
  background: rgba(107, 156, 255, 0.3);
  border-color: rgba(107, 156, 255, 0.6);
}

/* 悬停操作图标 */
.node-hover-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  padding-left: 4px;
}
.hover-action {
  cursor: pointer;
  padding: 3px;
  border-radius: 4px;
  color: var(--canvas-node-muted-text, #8ba3c9);
  transition: all 0.15s ease;
}
.hover-action:hover {
  color: var(--canvas-node-title-text, #ffffff);
  background: rgba(120, 170, 230, 0.2);
}
.hover-action.remove:hover {
  color: #fca5a5;
  background: rgba(248, 113, 113, 0.2);
}

/* ===== 内容区 ===== */
.node-body {
  flex: 1;
  min-height: 0;
  padding: 8px 10px;
  overflow: auto;
  color: var(--canvas-node-title-text, #ffffff);
}

/* 输入/输出锚点 */
.node-anchor {
  position: absolute;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  cursor: crosshair;
  background: var(--canvas-panel-bg, rgba(22, 32, 54, 0.8));
  border: 1.5px solid var(--canvas-anchor-fill, #6b9cff);
  color: var(--canvas-anchor-fill, #6b9cff);
  transition: transform 0.15s ease, background 0.15s ease;
  z-index: 2;
}

.node-anchor:hover { transform: scale(1.3); background: var(--canvas-anchor-fill, #6b9cff); color: #fff; }

.node-anchor-input {
  left: -9px; top: 50%;
  transform: translateY(-50%);
  border-color: var(--canvas-anchor-input, #6b9cff);
  color: var(--canvas-anchor-input, #6b9cff);
}
.node-anchor-input:hover {
  background: var(--canvas-anchor-input, #6b9cff);
  transform: translateY(-50%) scale(1.3);
}

.node-anchor-output {
  right: -9px; top: 50%;
  transform: translateY(-50%);
  border-color: var(--canvas-anchor-output, #a78bff);
  color: var(--canvas-anchor-output, #a78bff);
}
.node-anchor-output:hover {
  background: var(--canvas-anchor-output, #a78bff);
  transform: translateY(-50%) scale(1.3);
}

/* 尺寸调整把手 */
.node-resize-handle {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 14px;
  height: 14px;
  cursor: nwse-resize;
  background:
    linear-gradient(135deg, transparent 50%, rgba(120, 170, 230, 0.4) 50%);
  border-bottom-right-radius: 10px;
  transition: background 0.15s ease;
}

.node-resize-handle:hover {
  background:
    linear-gradient(135deg, transparent 50%, var(--canvas-node-active-border, #85b2ff) 50%);
}

/* 按类型微调节点图标颜色 */
.canvas-node-shell.node-type-image .node-icon { color: #6b9cff; }
.canvas-node-shell.node-type-video .node-icon { color: #a78bff; }
.canvas-node-shell.node-type-text .node-icon { color: #4ade80; }
.canvas-node-shell.node-type-chat .node-icon { color: #fbbf24; }
.canvas-node-shell.node-type-config .node-icon { color: #f472b6; }
.canvas-node-shell.node-type-frame .node-icon { color: #94a3b8; }
</style>
