<!-- =====================================================
     无限画布主视图（融合项目全局导航风格）
     - 画布标题栏：浮动在画布左上角（标题编辑 + 画布管理按钮）
     - 画布主体：InfiniteCanvas（连线层 + 节点层）+ 框选覆盖层
     - 底部浮动工具栏：节点创建 / 撤销重做 / 外观面板 / 删除清空
     - 左下角缩放控件 + 小地图
     - 节点悬停工具栏（浮动定位）
     - 右键菜单（仅节点）
     - 图片预览弹窗 + 快捷键帮助弹窗
     - 全局快捷键：Escape / Delete / Ctrl+Z / Ctrl+Shift+Z / Ctrl+D / Ctrl+A / Ctrl+S / Ctrl+L
     ===================================================== -->

<template>
  <div class="canvas-view" :data-theme="store.themeMode">
    <!-- ============ 画布主体 ============ -->
    <main class="canvas-main">
      <!-- 画布标题栏：浮动在画布左上角 -->
      <div class="canvas-title-bar" :style="titleBarStyle">
        <!-- 画布选择器（下拉切换） + 改名输入 -->
        <div class="title-wrap">
          <!-- 改名输入模式 -->
          <input
            v-if="editingTitle"
            ref="titleInputRef"
            v-model="titleInput"
            class="title-input"
            :style="titleInputStyle"
            @keydown.enter="saveTitle"
            @keydown.escape="cancelTitle"
            @blur="saveTitle"
          />
          <!-- 画布下拉选择器 -->
          <el-dropdown v-else trigger="click" @command="onSwitchCanvas">
            <span class="canvas-selector" :style="{ color: store.canvasTheme.node.text }">
              {{ activeWorkspaceName }}
              <ChevronDown :size="14" style="margin-left: 4px; opacity: 0.6;" />
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="ws in store.workspaces"
                  :key="ws.id"
                  :command="ws.id"
                  :class="{ 'is-active': ws.id === store.activeWorkspaceId }"
                >
                  {{ ws.name }}
                </el-dropdown-item>
                <el-dropdown-item v-if="store.workspaces.length === 0" disabled>暂无画布</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <!-- 画布管理按钮组 -->
        <div class="title-actions">
          <button class="title-btn" :style="titleBtnStyle" title="重命名" @click="startEditTitle">
            <Pencil :size="15" />
          </button>
          <button class="title-btn" :style="titleBtnStyle" title="新建画布" @click="newCanvas">
            <Plus :size="16" />
          </button>
          <button class="title-btn" :style="titleBtnStyle" title="删除当前画布" @click="deleteCanvas">
            <Trash2 :size="16" />
          </button>
          <button class="title-btn" :style="titleBtnStyle" title="导入 JSON" @click="importJson">
            <Upload :size="16" />
          </button>
          <button class="title-btn" :style="titleBtnStyle" title="导出 JSON" @click="handleExportJson">
            <Download :size="16" />
          </button>
        </div>
      </div>

      <!-- 无限画布（背景网格 + 视口变换 + 连线层 + 节点层） -->
      <InfiniteCanvas
        ref="canvasRef"
        @background-click="handleBackgroundClick"
        @pointerdown="handleCanvasPointerDown"
      >
        <!-- 连线层（不传 props 时自动使用 store 数据） -->
        <CanvasConnectionsLayer />

        <!-- 节点层：遍历所有面板渲染节点 -->
        <CanvasNode
          v-for="panel in store.panels"
          :key="panel.id"
          :panel="panel"
          :selected="store.selectedPanelIds.includes(panel.id)"
          :is-connecting="!!store.connecting"
          :show-image-info="store.showImageInfo"
          :theme="store.canvasTheme"
          :viewport="store.viewport"
          @select="handleNodeSelect"
          @drag-start="handleNodeDragStart"
          @drag="handleNodeDrag"
          @drag-end="handleNodeDragEnd"
          @resize-start="handleNodeResizeStart"
          @resize="handleNodeResize"
          @resize-end="handleNodeResizeEnd"
          @start-connecting="(anchorType) => handleNodeStartConnecting(panel.id, anchorType)"
          @context-menu="handleNodeContextMenu"
          @hover-enter="handleNodeHoverEnter"
          @hover-leave="handleNodeHoverLeave"
          @view-image="handleViewImage"
          @edit-text="(text) => handleNodeEditText(panel.id, text)"
          @generate-image="handleNodeGenerateImage"
          @retry="handleNodeRetry"
          @upload="(p) => handleNodeUpload(p)"
        />
      </InfiniteCanvas>

      <!-- 框选矩形（屏幕坐标覆盖层，不受画布变换影响） -->
      <div
        v-if="selectionBox.active"
        class="selection-box"
        :style="selectionBoxStyle"
      />

      <!-- ============ 底部浮动工具栏 ============ -->
      <CanvasToolbar
        class="bottom-toolbar"
        :theme="store.canvasTheme"
        :has-selection="store.selectedPanelIds.length > 0"
        :can-undo="store.history.past.length > 0"
        :can-redo="store.history.future.length > 0"
        :show-appearance-panel="showAppearancePanel"
        :theme-mode="store.themeMode"
        :background-mode="store.backgroundMode"
        :show-image-info="store.showImageInfo"
        @select-tool="handleSelectTool"
        @undo="store.undo()"
        @redo="store.redo()"
        @add-node="handleAddNode"
        @upload-asset="handleUploadAsset"
        @open-asset-library="handleOpenAssetLibrary"
        @toggle-appearance-panel="showAppearancePanel = !showAppearancePanel"
        @delete-selected="handleDeleteSelected"
        @clear-canvas="handleClearCanvas"
        @set-theme="(mode) => store.setThemeMode(mode)"
        @set-background="(mode) => store.setBackgroundMode(mode)"
        @toggle-image-info="(val) => handleToggleImageInfo(val)"
      />

      <!-- ============ 左下角缩放控件 ============ -->
      <CanvasZoomControls
        class="zoom-controls"
        :theme="store.canvasTheme"
        :zoom="store.viewport.zoom"
        :minimap-visible="minimapVisible"
        @toggle-minimap="minimapVisible = !minimapVisible"
        @reset-view="store.resetView()"
        @zoom-change="(z) => store.setZoom(z)"
        @show-help="showHelp = true"
      />

      <!-- ============ 小地图（条件渲染） ============ -->
      <CanvasMinimap
        v-if="minimapVisible"
        class="minimap"
        :theme="store.canvasTheme"
        :panels="store.panels"
        :viewport="store.viewport"
        :canvas-size="canvasSize"
        @locate="handleMinimapLocate"
      />

      <!-- ============ 节点悬停工具栏（浮动定位在节点上方） ============ -->
      <div
        v-if="hoveredPanel && showHoverToolbar"
        class="hover-toolbar-wrap"
        :style="hoverToolbarStyle"
        @mouseenter="cancelHoverHide"
        @mouseleave="scheduleHoverHide"
      >
        <CanvasNodeHoverToolbar
          :panel="hoveredPanel"
          :theme="store.canvasTheme"
          @info="handleHoverInfo"
          @delete="handleHoverDelete"
          @retry="handleHoverRetry"
          @save-asset="handleHoverSaveAsset"
          @download="handleHoverDownload"
          @edit="handleHoverEdit"
          @edit-text="handleHoverEditText"
          @generate-image="handleHoverGenerateImage"
          @font-size-down="handleHoverFontSizeDown"
          @font-size-up="handleHoverFontSizeUp"
          @upload-image="handleHoverUploadImage"
          @upload-video="handleHoverUploadVideo"
          @upload-audio="handleHoverUploadAudio"
          @copy-prompt="handleHoverCopyPrompt"
          @describe="handleHoverDescribe"
          @replace-image="handleHoverReplaceImage"
          @toggle-ratio="handleHoverToggleRatio"
          @mask-edit="handleHoverMaskEdit"
          @crop="handleHoverCrop"
          @split="handleHoverSplit"
          @upscale="handleHoverUpscale"
          @super-resolution="handleHoverSuperResolution"
          @angle="handleHoverAngle"
          @view-large="handleHoverViewLarge"
        />
      </div>

      <!-- ============ 右键菜单（仅节点） ============ -->
      <CanvasContextMenu
        v-if="contextMenu.open"
        :x="contextMenu.x"
        :y="contextMenu.y"
        :target-type="contextMenu.targetType"
        :theme="store.canvasTheme"
        @duplicate="handleContextDuplicate"
        @delete="handleContextDelete"
        @close="contextMenu.open = false"
      />

      <!-- ============ 图片预览弹窗 ============ -->
      <div v-if="previewImage" class="preview-overlay" @click="previewImage = null">
        <img :src="previewImage" class="preview-img" @click.stop />
        <button class="preview-close" @click="previewImage = null">×</button>
      </div>

      <!-- ============ 快捷键帮助弹窗 ============ -->
      <div v-if="showHelp" class="help-overlay" @click="showHelp = false">
        <div class="help-modal" :style="helpModalStyle" @click.stop>
          <h3 class="help-title">快捷键</h3>
          <ul class="help-list">
            <li><kbd>Space</kbd> + 拖动 / 中键拖动：平移画布</li>
            <li><kbd>Ctrl</kbd> + 滚轮：缩放画布</li>
            <li><kbd>Ctrl</kbd> + 拖动背景：框选节点</li>
            <li><kbd>Ctrl</kbd> + 点击节点：多选</li>
            <li><kbd>Ctrl</kbd> + <kbd>Z</kbd>：撤销</li>
            <li><kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>Z</kbd>：重做</li>
            <li><kbd>Ctrl</kbd> + <kbd>D</kbd>：复制选中节点</li>
            <li><kbd>Ctrl</kbd> + <kbd>A</kbd>：全选节点</li>
            <li><kbd>Ctrl</kbd> + <kbd>S</kbd>：保存画布</li>
            <li><kbd>Ctrl</kbd> + <kbd>L</kbd>：编辑画布标题</li>
            <li><kbd>Delete</kbd> / <kbd>Backspace</kbd>：删除选中</li>
            <li><kbd>Escape</kbd>：取消选中 / 取消连线 / 关闭菜单</li>
          </ul>
          <button class="help-close-btn" @click="showHelp = false">关闭</button>
        </div>
      </div>

      <!-- ============ 隐藏的文件输入（用于上传素材 / 导入 JSON） ============ -->
      <input
        ref="fileInputRef"
        type="file"
        class="hidden-file-input"
        :accept="fileAccept"
        @change="handleFileSelect"
      />
    </main>
  </div>
</template>

<script setup>
/* =====================================================
 * CanvasView 无限画布主视图
 * - 整合 9 个子组件：InfiniteCanvas / CanvasConnectionsLayer /
 *   CanvasNode / CanvasToolbar / CanvasZoomControls / CanvasMinimap /
 *   CanvasNodeHoverToolbar / CanvasContextMenu / CanvasAppearancePanel（内嵌于 Toolbar）
 * - 接入 useCanvasStore：panels / connections / viewport / history
 * - 处理节点创建/拖拽/缩放/删除、连线创建/删除、框选、撤销/重做、快捷键
 * ===================================================== */

import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Trash2, Upload, Download, Pencil, ChevronDown } from 'lucide-vue-next'
import { useCanvasStore } from '@/stores/canvas'
import InfiniteCanvas from '@/components/canvas/InfiniteCanvas.vue'
import CanvasConnectionsLayer from '@/components/canvas/CanvasConnectionsLayer.vue'
import CanvasNode from '@/components/canvas/CanvasNode.vue'
import CanvasToolbar from '@/components/canvas/CanvasToolbar.vue'
import CanvasZoomControls from '@/components/canvas/CanvasZoomControls.vue'
import CanvasMinimap from '@/components/canvas/CanvasMinimap.vue'
import CanvasNodeHoverToolbar from '@/components/canvas/CanvasNodeHoverToolbar.vue'
import CanvasContextMenu from '@/components/canvas/CanvasContextMenu.vue'

const store = useCanvasStore()

// ---------- 节点默认尺寸（对齐参考项目） ----------
const NODE_DEFAULT_SIZES = {
  text: { width: 340, height: 240 },
  image: { width: 340, height: 240 },
  video: { width: 420, height: 236 },
  audio: { width: 340, height: 120 },
  config: { width: 340, height: 240 },
}

// ---------- 节点类型中文名 ----------
const NODE_NAMES = {
  text: '文本节点',
  image: '图片节点',
  video: '视频节点',
  audio: '音频节点',
  config: '配置节点',
}

// ==================== 画布标题栏 ====================

// 画布标题栏容器样式
const titleBarStyle = computed(() => ({
  background: store.canvasTheme.toolbar.panel,
  borderColor: store.canvasTheme.toolbar.border,
}))

// 标题栏按钮样式
const titleBtnStyle = computed(() => ({
  color: store.canvasTheme.toolbar.item,
}))

// 画布管理操作
function newCanvas() {
  store.createWorkspace('画布 ' + (store.workspaces.length + 1))
  ElMessage.success('已创建新画布')
}

function onSwitchCanvas(id) {
  if (id !== store.activeWorkspaceId) {
    store.switchWorkspace(id)
  }
}

function deleteCanvas() {
  if (!store.activeWorkspaceId) {
    ElMessage.warning('当前没有画布')
    return
  }
  ElMessageBox.confirm('确定删除当前画布吗？此操作不可撤销。', '提示', { type: 'warning' })
    .then(() => {
      store.deleteWorkspace(store.activeWorkspaceId)
      ElMessage.success('画布已删除')
    })
    .catch(() => {})
}

function importJson() {
  triggerFileUpload(null, '.json')
}

// ==================== 标题编辑 ====================

const editingTitle = ref(false)
const titleInput = ref('')
const titleInputRef = ref(null)
const activeWorkspaceName = computed(() => store.activeWorkspace?.name ?? '未命名画布')

const titleInputStyle = computed(() => ({
  background: store.canvasTheme.node.panel,
  borderColor: store.canvasTheme.node.stroke,
  color: store.canvasTheme.node.text,
}))

function startEditTitle() {
  titleInput.value = activeWorkspaceName.value
  editingTitle.value = true
  nextTick(() => titleInputRef.value?.focus())
}

function saveTitle() {
  if (!editingTitle.value) return
  const name = titleInput.value.trim()
  if (name && store.activeWorkspaceId) {
    store.renameWorkspace(store.activeWorkspaceId, name)
  }
  editingTitle.value = false
}

function cancelTitle() {
  editingTitle.value = false
}

// ==================== 画布主体引用 ====================

const canvasRef = ref(null)

// ==================== 背景点击处理 ====================

function handleBackgroundClick() {
  // InfiniteCanvas 在无 props 时已自动清空选中
  showAppearancePanel.value = false
}

// ==================== 框选（Ctrl/Cmd + 拖动背景） ====================

const selectionBox = reactive({
  active: false,
  startScreenX: 0,
  startScreenY: 0,
  endScreenX: 0,
  endScreenY: 0,
})

const selectionBoxStyle = computed(() => {
  if (!selectionBox.active) return {}
  // 减去画布容器偏移，转为相对于 canvas-main 的坐标
  const offsetX = store.canvasRect.left
  const offsetY = store.canvasRect.top
  const left = Math.min(selectionBox.startScreenX, selectionBox.endScreenX) - offsetX
  const top = Math.min(selectionBox.startScreenY, selectionBox.endScreenY) - offsetY
  const width = Math.abs(selectionBox.endScreenX - selectionBox.startScreenX)
  const height = Math.abs(selectionBox.endScreenY - selectionBox.startScreenY)
  return {
    left: left + 'px',
    top: top + 'px',
    width: width + 'px',
    height: height + 'px',
    borderColor: store.canvasTheme.canvas.selectionStroke,
    backgroundColor: store.canvasTheme.canvas.selectionFill,
  }
})

// 画布指针按下：检测 Ctrl/Cmd + 背景点击，启动框选
function handleCanvasPointerDown(event) {
  if (event.button !== 0) return
  if (!(event.ctrlKey || event.metaKey)) return
  // 检查是否点击在背景上（非节点、非连线）
  const target = event.target instanceof Element ? event.target : null
  if (target?.closest?.('[data-node-id],[data-connection-id]')) return

  selectionBox.active = true
  selectionBox.startScreenX = event.clientX
  selectionBox.startScreenY = event.clientY
  selectionBox.endScreenX = event.clientX
  selectionBox.endScreenY = event.clientY

  window.addEventListener('pointermove', handleSelectionMove)
  window.addEventListener('pointerup', handleSelectionUp)
}

// 框选拖动：实时更新框选矩形并选中范围内节点
function handleSelectionMove(event) {
  if (!selectionBox.active) return
  selectionBox.endScreenX = event.clientX
  selectionBox.endScreenY = event.clientY
  const startWorld = store.screenToWorld(selectionBox.startScreenX, selectionBox.startScreenY)
  const endWorld = store.screenToWorld(event.clientX, event.clientY)
  store.selectPanelsInRect({ startWorld, endWorld }, { append: event.shiftKey })
}

// 框选结束
function handleSelectionUp() {
  selectionBox.active = false
  window.removeEventListener('pointermove', handleSelectionMove)
  window.removeEventListener('pointerup', handleSelectionUp)
}

// ==================== 节点交互：选中 ====================

// 跟踪 Ctrl/Cmd 按键状态（用于多选判断）
const ctrlPressed = ref(false)

function handleNodeSelect(panelId) {
  store.selectPanel(panelId, { append: ctrlPressed.value })
}

// ==================== 节点交互：拖拽移动 ====================

const dragState = reactive({
  active: false,
  draggedId: null,
  initialPositions: {}, // { panelId: { x, y } }
  hasMoved: false,
})

// 节点拖拽开始：记录所有选中节点的初始位置
function handleNodeDragStart({ id, event }) {
  // 如果拖拽的节点不在选中列表中，只选中它
  if (!store.selectedPanelIds.includes(id)) {
    store.selectPanel(id, { append: false })
  }
  dragState.active = true
  dragState.draggedId = id
  dragState.hasMoved = false
  dragState.initialPositions = {}
  for (const pid of store.selectedPanelIds) {
    const p = store.panels.find((pp) => pp.id === pid)
    if (p) dragState.initialPositions[pid] = { x: p.x, y: p.y }
  }
}

// 节点拖拽中：第一次移动时压入快照，之后同步移动所有选中节点
function handleNodeDrag({ id, x, y }) {
  if (!dragState.active) return
  if (!dragState.hasMoved) {
    store.pushSnapshot()
    dragState.hasMoved = true
  }
  const initial = dragState.initialPositions[id]
  if (!initial) return
  const dx = x - initial.x
  const dy = y - initial.y
  // 应用增量到所有选中节点
  for (const pid of store.selectedPanelIds) {
    const init = dragState.initialPositions[pid]
    if (!init) continue
    store._updatePanelDirect(pid, { x: init.x + dx, y: init.y + dy })
  }
}

// 节点拖拽结束：触发一次保存
function handleNodeDragEnd({ id }) {
  if (!dragState.active) return
  if (dragState.hasMoved) {
    const panel = store.panels.find((p) => p.id === id)
    if (panel) store.updatePanel(id, { x: panel.x, y: panel.y })
  }
  dragState.active = false
  dragState.draggedId = null
  dragState.initialPositions = {}
}

// ==================== 节点交互：缩放 ====================

const resizeState = reactive({
  active: false,
  panelId: null,
  hasMoved: false,
})

// 节点缩放开始：压入快照
function handleNodeResizeStart({ id }) {
  resizeState.active = true
  resizeState.panelId = id
  resizeState.hasMoved = false
  store.pushSnapshot()
}

// 节点缩放中：直接更新节点尺寸
function handleNodeResize({ id, width, height, x, y }) {
  store._updatePanelDirect(id, { width, height, x, y })
  resizeState.hasMoved = true
}

// 节点缩放结束：触发一次保存
function handleNodeResizeEnd({ id }) {
  if (resizeState.hasMoved) {
    const panel = store.panels.find((p) => p.id === id)
    if (panel) {
      store.updatePanel(id, {
        width: panel.width,
        height: panel.height,
        x: panel.x,
        y: panel.y,
      })
    }
  }
  resizeState.active = false
  resizeState.panelId = null
}

// ==================== 连线交互 ====================

// 节点开始连线：启动全局 pointermove/pointerup 监听
function handleNodeStartConnecting(panelId, anchorType) {
  store.startConnecting(panelId, anchorType)
  window.addEventListener('pointermove', handleConnectingMove)
  window.addEventListener('pointerup', handleConnectingUp)
}

// 连线拖拽中：更新临时连线终点
function handleConnectingMove(event) {
  if (!store.connecting) return
  const world = store.screenToWorld(event.clientX, event.clientY)
  store.updateConnecting(world.x, world.y)
}

// 连线结束：检测是否释放在节点上
function handleConnectingUp(event) {
  window.removeEventListener('pointermove', handleConnectingMove)
  window.removeEventListener('pointerup', handleConnectingUp)
  if (!store.connecting) return
  const el = document.elementFromPoint(event.clientX, event.clientY)
  const nodeEl = el?.closest?.('[data-node-id]')
  if (nodeEl) {
    const targetId = nodeEl.getAttribute('data-node-id')
    store.endConnecting(targetId, 'target')
  } else {
    store.cancelConnecting()
  }
}

// ==================== 节点交互：右键菜单 ====================

const contextMenu = reactive({
  open: false,
  x: 0,
  y: 0,
  targetType: 'node',
  targetId: null,
})

// 节点右键：打开菜单
function handleNodeContextMenu(event) {
  event.preventDefault()
  event.stopPropagation()
  const nodeEl = event.target instanceof Element ? event.target.closest('[data-node-id]') : null
  const targetId = nodeEl?.getAttribute('data-node-id') ?? null
  contextMenu.open = true
  // 减去画布容器偏移，转为相对于 canvas-main 的坐标
  contextMenu.x = event.clientX - store.canvasRect.left
  contextMenu.y = event.clientY - store.canvasRect.top
  contextMenu.targetType = 'node'
  contextMenu.targetId = targetId
}

// 右键菜单：复制
function handleContextDuplicate() {
  if (contextMenu.targetId) {
    store.pushSnapshot()
    store.duplicatePanel(contextMenu.targetId)
  }
  contextMenu.open = false
}

// 右键菜单：删除
function handleContextDelete() {
  if (contextMenu.targetId) {
    store.pushSnapshot()
    store.deletePanel(contextMenu.targetId)
  }
  contextMenu.open = false
}

// ==================== 节点交互：其他事件 ====================

// 查看图片大图
function handleViewImage(imageUrl) {
  if (imageUrl) previewImage.value = imageUrl
}

// 编辑文本节点内容
function handleNodeEditText(panelId, text) {
  store.pushSnapshot()
  store.updatePanel(panelId, { content: { content: text } })
}

// 从文本节点生图（简化为提示）
function handleNodeGenerateImage(panel) {
  ElMessage.info('生图功能开发中')
  console.log('[canvas] generate-image from panel:', panel.id)
}

// 重试生成
function handleNodeRetry(panel) {
  ElMessage.info('重试功能开发中')
  console.log('[canvas] retry panel:', panel.id)
}

// 节点上传文件
function handleNodeUpload(panel) {
  if (panel) {
    triggerFileUpload(panel.id)
  }
}

// ==================== 悬停工具栏 ====================

const hoveredPanelId = ref(null)
const showHoverToolbar = ref(false)
let hoverHideTimer = null

const hoveredPanel = computed(() => {
  if (!hoveredPanelId.value) return null
  return store.panels.find((p) => p.id === hoveredPanelId.value) ?? null
})

// 悬停工具栏定位：节点上方居中
const hoverToolbarStyle = computed(() => {
  const panel = hoveredPanel.value
  if (!panel) return { display: 'none' }
  // worldToScreen 返回屏幕坐标，减去画布偏移转为相对于 canvas-main 的坐标
  const screen = store.worldToScreen(panel.x + panel.width / 2, panel.y)
  return {
    left: (screen.x - store.canvasRect.left) + 'px',
    top: (screen.y - store.canvasRect.top - 8) + 'px',
    transform: 'translate(-50%, -100%)',
  }
})

// 节点 hover 进入
function handleNodeHoverEnter(panelId) {
  cancelHoverHide()
  hoveredPanelId.value = panelId
  showHoverToolbar.value = true
}

// 节点 hover 离开：延迟隐藏（允许鼠标移到工具栏上）
function handleNodeHoverLeave() {
  scheduleHoverHide()
}

function scheduleHoverHide() {
  cancelHoverHide()
  hoverHideTimer = setTimeout(() => {
    showHoverToolbar.value = false
    hoveredPanelId.value = null
  }, 200)
}

function cancelHoverHide() {
  if (hoverHideTimer) {
    clearTimeout(hoverHideTimer)
    hoverHideTimer = null
  }
}

// ---- 悬停工具栏事件处理（复杂功能简化为 ElMessage 提示） ----

function handleHoverInfo() {
  const p = hoveredPanel.value
  if (p) ElMessage.info(`节点类型: ${NODE_NAMES[p.type] || p.type} | ID: ${p.id}`)
}

function handleHoverDelete() {
  if (hoveredPanelId.value) {
    store.pushSnapshot()
    store.deletePanel(hoveredPanelId.value)
  }
  showHoverToolbar.value = false
  hoveredPanelId.value = null
}

function handleHoverRetry() {
  ElMessage.info('重试功能开发中')
}

function handleHoverSaveAsset() {
  ElMessage.info('存素材功能开发中')
}

function handleHoverDownload() {
  const p = hoveredPanel.value
  if (p?.content?.content) {
    const a = document.createElement('a')
    a.href = p.content.content
    a.download = `download-${Date.now()}`
    a.click()
  }
}

function handleHoverEdit() {
  ElMessage.info('编辑功能开发中')
}

function handleHoverEditText() {
  ElMessage.info('编辑文字功能开发中')
}

function handleHoverGenerateImage() {
  ElMessage.info('生图功能开发中')
}

function handleHoverFontSizeDown() {
  if (!hoveredPanelId.value) return
  const p = store.panels.find((pp) => pp.id === hoveredPanelId.value)
  const cur = p?.content?.fontSize ?? 16
  store.updatePanel(hoveredPanelId.value, { content: { fontSize: Math.max(10, cur - 2) } })
}

function handleHoverFontSizeUp() {
  if (!hoveredPanelId.value) return
  const p = store.panels.find((pp) => pp.id === hoveredPanelId.value)
  const cur = p?.content?.fontSize ?? 16
  store.updatePanel(hoveredPanelId.value, { content: { fontSize: Math.min(48, cur + 2) } })
}

function handleHoverUploadImage() {
  triggerFileUpload(hoveredPanelId.value, 'image/*')
}

function handleHoverUploadVideo() {
  triggerFileUpload(hoveredPanelId.value, 'video/*')
}

function handleHoverUploadAudio() {
  triggerFileUpload(hoveredPanelId.value, 'audio/*')
}

function handleHoverCopyPrompt() {
  if (!hoveredPanelId.value) return
  const p = store.panels.find((pp) => pp.id === hoveredPanelId.value)
  const prompt = p?.content?.prompt ?? ''
  navigator.clipboard?.writeText(prompt).then(() => {
    ElMessage.success('已复制提示词')
  }).catch(() => {
    ElMessage.warning('复制失败')
  })
}

function handleHoverDescribe() {
  ElMessage.info('反推提示词功能开发中')
}

function handleHoverReplaceImage() {
  triggerFileUpload(hoveredPanelId.value, 'image/*')
}

function handleHoverToggleRatio() {
  if (!hoveredPanelId.value) return
  const p = store.panels.find((pp) => pp.id === hoveredPanelId.value)
  const cur = p?.content?.freeResize ?? false
  store.updatePanel(hoveredPanelId.value, { content: { freeResize: !cur } })
  ElMessage.success(cur ? '已切换为锁定比例' : '已切换为自由比例')
}

function handleHoverMaskEdit() {
  ElMessage.info('蒙版编辑功能开发中')
}

function handleHoverCrop() {
  ElMessage.info('裁剪功能开发中')
}

function handleHoverSplit() {
  ElMessage.info('拆分功能开发中')
}

function handleHoverUpscale() {
  ElMessage.info('放大功能开发中')
}

function handleHoverSuperResolution() {
  ElMessage.info('超分功能开发中')
}

function handleHoverAngle() {
  ElMessage.info('角度调整功能开发中')
}

function handleHoverViewLarge() {
  const p = hoveredPanel.value
  if (p?.content?.content) previewImage.value = p.content.content
}

// ==================== 底部工具栏事件 ====================

const showAppearancePanel = ref(false)

// 选择/移动工具
function handleSelectTool() {
  // 无需特殊处理，默认即为选择模式
}

// 工具栏添加节点
function handleAddNode(type) {
  createNodeAtCenter(type)
}

// 工具栏上传素材
function handleUploadAsset() {
  triggerFileUpload(null, 'image/*,video/*,audio/*')
}

// 打开素材库
function handleOpenAssetLibrary() {
  ElMessage.info('素材库功能开发中')
}

// 删除选中节点
function handleDeleteSelected() {
  if (store.selectedPanelIds.length === 0) return
  store.pushSnapshot()
  const ids = [...store.selectedPanelIds]
  for (const id of ids) {
    store.deletePanel(id)
  }
}

// 清空画布
function handleClearCanvas() {
  if (store.panels.length === 0) return
  ElMessageBox.confirm('确定清空当前画布的所有节点吗？', '提示', { type: 'warning' })
    .then(() => {
      store.pushSnapshot()
      store.clearAllPanels()
      ElMessage.success('画布已清空')
    })
    .catch(() => {})
}

// 切换图片信息显示
function handleToggleImageInfo(val) {
  if (val !== store.showImageInfo) store.toggleImageInfo()
}

// ==================== 缩放控件 + 小地图 ====================

const minimapVisible = ref(false)
const showHelp = ref(false)
const canvasSize = computed(() => ({
  width: window.innerWidth,
  height: window.innerHeight,
}))

const helpModalStyle = computed(() => ({
  background: store.canvasTheme.toolbar.panel,
  borderColor: store.canvasTheme.toolbar.border,
  color: store.canvasTheme.node.text,
}))

// 小地图定位：将视口中心移动到指定世界坐标
function handleMinimapLocate(worldX, worldY) {
  const { zoom } = store.viewport
  store.viewport.x = window.innerWidth / 2 - worldX * zoom
  store.viewport.y = window.innerHeight / 2 - worldY * zoom
}

// ==================== 节点创建 ====================

// 在视口中心创建节点
function createNodeAtCenter(type) {
  const size = NODE_DEFAULT_SIZES[type] ?? NODE_DEFAULT_SIZES.text
  const cx = (window.innerWidth / 2 - store.viewport.x) / store.viewport.zoom
  const cy = (window.innerHeight / 2 - store.viewport.y) / store.viewport.zoom
  store.pushSnapshot()
  const id = store.addPanel({
    type,
    name: NODE_NAMES[type] ?? '节点',
    x: cx - size.width / 2,
    y: cy - size.height / 2,
    width: size.width,
    height: size.height,
    content: {},
  })
  store.selectPanel(id, { append: false })
  return id
}

// ==================== 文件上传 / 导入 ====================

const fileInputRef = ref(null)
const uploadTargetPanelId = ref(null)
const fileAccept = ref('*')

// 触发文件选择对话框
function triggerFileUpload(panelId, accept = '*') {
  uploadTargetPanelId.value = panelId
  fileAccept.value = accept
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
    fileInputRef.value.click()
  }
}

// 文件选择回调
function handleFileSelect(event) {
  const file = event.target.files?.[0]
  if (!file) return

  // JSON 导入
  if (file.name.endsWith('.json')) {
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        store.importJSON(e.target.result)
        ElMessage.success('导入成功')
      } catch (err) {
        ElMessage.error('导入失败：' + err.message)
      }
    }
    reader.readAsText(file)
    return
  }

  // 文件上传到节点
  const url = URL.createObjectURL(file)
  const targetId = uploadTargetPanelId.value

  if (targetId) {
    // 更新现有节点内容
    store.pushSnapshot()
    store.updatePanel(targetId, {
      content: {
        content: url,
        status: 'success',
      },
    })
    ElMessage.success('文件已加载到节点')
  } else {
    // 创建新节点
    const type = file.type.startsWith('image/') ? 'image'
      : file.type.startsWith('video/') ? 'video'
      : file.type.startsWith('audio/') ? 'audio'
      : 'text'
    const id = createNodeAtCenter(type)
    store.updatePanel(id, {
      content: { content: url, status: 'success' },
    })
    ElMessage.success('节点已创建')
  }

  uploadTargetPanelId.value = null
}

// ==================== 图片预览弹窗 ====================

const previewImage = ref(null)

// ==================== 导出 JSON ====================

function handleExportJson() {
  const json = store.exportJSON()
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `canvas-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出 JSON')
}

// ==================== 全局快捷键 ====================

function handleKeyDown(event) {
  // 跟踪 Ctrl/Cmd 状态
  if (event.ctrlKey || event.metaKey) {
    ctrlPressed.value = true
  }

  // 输入框内不响应快捷键（Escape 除外）
  const isInput = event.target instanceof HTMLInputElement
    || event.target instanceof HTMLTextAreaElement
    || event.target?.isContentEditable

  if (isInput) {
    if (event.key === 'Escape') {
      event.target.blur()
    }
    return
  }

  const ctrl = event.ctrlKey || event.metaKey

  // Escape：取消连线 / 关闭菜单 / 清空选中
  if (event.key === 'Escape') {
    if (store.connecting) store.cancelConnecting()
    else if (contextMenu.open) contextMenu.open = false
    else if (showAppearancePanel.value) showAppearancePanel.value = false
    else if (showHelp.value) showHelp.value = false
    else store.clearSelection()
    return
  }

  // Delete / Backspace：删除选中节点
  if (event.key === 'Delete' || event.key === 'Backspace') {
    if (store.selectedPanelIds.length > 0) {
      event.preventDefault()
      handleDeleteSelected()
    }
    return
  }

  // Ctrl+Z：撤销
  if (ctrl && event.key === 'z' && !event.shiftKey) {
    event.preventDefault()
    store.undo()
    return
  }

  // Ctrl+Shift+Z / Ctrl+Y：重做
  if ((ctrl && event.key === 'z' && event.shiftKey) || (ctrl && event.key === 'y')) {
    event.preventDefault()
    store.redo()
    return
  }

  // Ctrl+D：复制选中节点
  if (ctrl && event.key === 'd') {
    event.preventDefault()
    if (store.selectedPanelIds.length > 0) {
      store.pushSnapshot()
      store.duplicateSelectedPanels()
    }
    return
  }

  // Ctrl+A：全选
  if (ctrl && event.key === 'a') {
    event.preventDefault()
    store.selectedPanelIds = store.panels.map((p) => p.id)
    store.selectedPanelId = store.selectedPanelIds[0] ?? null
    return
  }

  // Ctrl+S：保存（阻止浏览器默认保存，提示已自动保存）
  if (ctrl && event.key === 's') {
    event.preventDefault()
    ElMessage.success('画布已自动保存')
    return
  }

  // Ctrl+L：编辑画布标题
  if (ctrl && event.key === 'l') {
    event.preventDefault()
    startEditTitle()
    return
  }
}

// 按键释放：重置 Ctrl/Cmd 状态
function handleKeyUp(event) {
  if (!event.ctrlKey && !event.metaKey) {
    ctrlPressed.value = false
  }
}

// ==================== 全局点击：关闭弹出层 ====================

function handleGlobalClick(event) {
  const target = event.target instanceof Element ? event.target : null
  // 关闭右键菜单
  if (contextMenu.open && !target?.closest?.('.context-menu')) {
    contextMenu.open = false
  }
}

// ==================== 生命周期 ====================

onMounted(async () => {
  // 从 localforage 加载持久化数据
  await store._hydrateFromStorage()
  // 如果没有工作区，创建默认画布
  if (!store.activeWorkspaceId && store.workspaces.length === 0) {
    store.createWorkspace('画布 1')
  }
  // 注册全局事件监听
  window.addEventListener('keydown', handleKeyDown)
  window.addEventListener('keyup', handleKeyUp)
  window.addEventListener('click', handleGlobalClick)
})

onBeforeUnmount(() => {
  // 移除全局事件监听
  window.removeEventListener('keydown', handleKeyDown)
  window.removeEventListener('keyup', handleKeyUp)
  window.removeEventListener('click', handleGlobalClick)
  window.removeEventListener('pointermove', handleSelectionMove)
  window.removeEventListener('pointerup', handleSelectionUp)
  window.removeEventListener('pointermove', handleConnectingMove)
  window.removeEventListener('pointerup', handleConnectingUp)
  // 清理 hover 定时器
  cancelHoverHide()
})
</script>

<style scoped>
/* ==================== 画布主容器 ==================== */
/* 在 app-main 内占满可用空间（App.vue canvas-mode 已设 position:relative） */
.canvas-view {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
}

/* ==================== 画布标题栏（浮动在画布左上角） ==================== */
.canvas-title-bar {
  position: absolute;
  top: 16px;
  left: 16px;
  z-index: 50;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px 6px 14px;
  border: 1px solid;
  border-radius: 10px;
  backdrop-filter: blur(12px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

/* ---- 画布标题 ---- */
.title-wrap {
  display: flex;
  align-items: center;
  min-width: 0;
}

/* 画布下拉选择器 */
.canvas-selector {
  display: flex;
  align-items: center;
  font-size: 14px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
  outline: none;
}

.canvas-selector:hover {
  background: rgba(128, 128, 128, 0.1);
}

.title-input {
  font-size: 14px;
  font-weight: 500;
  padding: 4px 8px;
  border: 1px solid;
  border-radius: 6px;
  outline: none;
  max-width: 200px;
}

/* ---- 标题栏按钮组 ---- */
.title-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.title-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  transition: background 0.15s;
}

.title-btn:hover {
  background: rgba(128, 128, 128, 0.15);
}

/* ==================== 画布主体 ==================== */
.canvas-main {
  position: relative;
  width: 100%;
  height: 100%;
}

/* ==================== 框选矩形 ==================== */
.selection-box {
  position: absolute;
  z-index: 30;
  border: 1px solid;
  border-radius: 2px;
  pointer-events: none;
}

/* ==================== 底部浮动工具栏 ==================== */
.bottom-toolbar {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 40;
}

/* ==================== 左下角缩放控件 ==================== */
.zoom-controls {
  position: absolute;
  bottom: 20px;
  left: 20px;
  z-index: 40;
}

/* ==================== 小地图 ==================== */
.minimap {
  position: absolute;
  bottom: 96px;
  left: 24px;
  z-index: 40;
}

/* ==================== 节点悬停工具栏 ==================== */
.hover-toolbar-wrap {
  position: absolute;
  z-index: 45;
}

/* ==================== 图片预览弹窗 ==================== */
.preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: zoom-out;
}

.preview-img {
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  border-radius: 8px;
  cursor: default;
}

.preview-close {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  font-size: 24px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-close:hover {
  background: rgba(255, 255, 255, 0.25);
}

/* ==================== 快捷键帮助弹窗 ==================== */
.help-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
}

.help-modal {
  border: 1px solid;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  padding: 24px;
  max-width: 480px;
  width: 90%;
}

.help-title {
  margin: 0 0 16px 0;
  font-size: 18px;
  font-weight: 600;
}

.help-list {
  margin: 0 0 16px 0;
  padding-left: 20px;
  font-size: 14px;
  line-height: 2;
}

.help-list kbd {
  display: inline-block;
  padding: 2px 6px;
  border: 1px solid rgba(128, 128, 128, 0.4);
  border-radius: 4px;
  background: rgba(128, 128, 128, 0.1);
  font-size: 12px;
  font-family: monospace;
}

.help-close-btn {
  padding: 6px 16px;
  border: 1px solid rgba(128, 128, 128, 0.4);
  border-radius: 8px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 14px;
}

.help-close-btn:hover {
  background: rgba(128, 128, 128, 0.15);
}

/* ==================== 隐藏文件输入 ==================== */
.hidden-file-input {
  display: none;
}
</style>
