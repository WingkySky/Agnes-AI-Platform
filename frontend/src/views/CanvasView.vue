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
        @drop-asset="handleCanvasDropAsset"
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
          @generate="handleConfigGenerate"
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

      <!-- ============ 素材库浮动面板 ============ -->
      <CanvasAssetLibrary
        v-if="showAssetLibrary"
        :theme="store.canvasTheme"
        @close="showAssetLibrary = false"
        @use-asset="handleUseAsset"
        @delete-asset="handleDeleteAsset"
        @upload-asset="handleUploadAssetFiles"
      />

      <!-- ============ 蒙版编辑对话框 ============ -->
      <MaskEditDialog
        v-if="maskEditState.visible"
        :visible="maskEditState.visible"
        :image-url="maskEditState.imageUrl"
        :theme="store.canvasTheme"
        @confirm="handleMaskConfirm"
        @cancel="maskEditState.visible = false"
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
import CanvasAssetLibrary from '@/components/canvas/CanvasAssetLibrary.vue'
import MaskEditDialog from '@/components/canvas/MaskEditDialog.vue'

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

// 从文本节点生图：读取文本内容作为 prompt，在源节点旁创建 image 节点并连线
async function handleNodeGenerateImage(panel) {
  const prompt = panel.content?.content || panel.content?.prompt || ''
  if (!prompt.trim()) {
    ElMessage.warning('文本节点内容为空')
    return
  }
  await generateImageFromPrompt(panel, prompt)
}

// 重试生成：查找上游 config 节点重新生成，或用节点自身 prompt 重新生成
async function handleNodeRetry(panel) {
  await retryGeneration(panel)
}

// 通用：从 prompt 生成图片，在源节点旁创建 image 节点并连线
// - sourcePanel: 源节点（文本节点或重试时的图片节点）
// - prompt: 提示词
// - targetPanelId: 可选，若提供则更新该节点而不是创建新节点（用于重试场景）
async function generateImageFromPrompt(sourcePanel, prompt, targetPanelId = null) {
  let newPanelId = targetPanelId

  if (!targetPanelId) {
    // 在源节点右侧创建 image 节点（loading 状态）
    // 注意：store.addPanel 返回的是新节点 ID 字符串
    newPanelId = store.addPanel({
      type: 'image',
      x: sourcePanel.x + sourcePanel.width + 60,
      y: sourcePanel.y,
      width: 340,
      height: 240,
      content: { content: '', status: 'loading', prompt },
    })
    // 连线：源节点 → 新图片节点
    store.addConnection({ source_panel_id: sourcePanel.id, target_panel_id: newPanelId })
    store.pushSnapshot()
  } else {
    // 重试场景：更新已有节点为 loading 状态
    store.updatePanel(targetPanelId, { content: { content: '', status: 'loading', errorDetails: null } })
  }

  try {
    // 调用图片生成 API
    const { createImageTask, getImageTaskStatus } = await import('@/api/images')
    const resp = await createImageTask({ prompt, model: 'agnes-image-2.1-flash', size: '1024x1024' })
    const taskId = resp.task_id

    // 轮询任务状态（间隔 2 秒，最多 150 次 ≈ 5 分钟）
    const maxAttempts = 150
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 2000))
      const status = await getImageTaskStatus(taskId)
      if (status.status === 'completed' || status.status === 'succeeded' || status.status === 'success' || status.status === 'done') {
        const imageUrl = status.result_url || status.image_url || status.url || status.data?.[0]?.url
        store.updatePanel(newPanelId, { content: { content: imageUrl, status: 'success' } })
        store.pushSnapshot()
        ElMessage.success('图片生成完成')
        return
      }
      if (status.status === 'failed' || status.status === 'error') {
        const errMsg = status.message || status.error || '生成失败'
        store.updatePanel(newPanelId, { content: { status: 'error', errorDetails: errMsg } })
        ElMessage.error('图片生成失败: ' + errMsg)
        return
      }
    }
    // 超时
    store.updatePanel(newPanelId, { content: { status: 'error', errorDetails: '生成超时' } })
    ElMessage.warning('生成超时')
  } catch (err) {
    console.error('[canvas] generate image error:', err)
    store.updatePanel(newPanelId, { content: { status: 'error', errorDetails: err.message } })
    ElMessage.error('生成失败: ' + err.message)
  }
}

// 通用：重试生成
// - 查找上游 config 节点，重新执行合并生成
// - 没有上游 config 节点时，用节点自身 prompt 重新生成（直接更新当前节点）
async function retryGeneration(panel) {
  // 查找上游 config 节点
  const upstreamConnections = store.connections.filter((c) => c.target_panel_id === panel.id)
  const configConn = upstreamConnections.find((c) => {
    const source = store.panels.find((p) => p.id === c.source_panel_id)
    return source?.type === 'config'
  })

  if (configConn) {
    // 有上游 config 节点，重新执行合并生成
    const configNode = store.panels.find((p) => p.id === configConn.source_panel_id)
    try {
      const { executeMergeGeneration, executeMergeVideoGeneration } = await import('@/lib/canvas-generation')
      const isVideo = panel.type === 'video'
      const fn = isVideo ? executeMergeVideoGeneration : executeMergeGeneration
      ElMessage.info('正在重新生成...')
      await fn(configNode.id, store, {
        onProgress: (stage) => {
          if (stage === 'done') {
            ElMessage.success('重新生成完成')
          }
        },
      })
    } catch (err) {
      ElMessage.error('重试失败: ' + err.message)
    }
  } else {
    // 没有上游 config 节点，用节点自身的 prompt 重新生成（直接更新当前节点）
    const prompt = panel.content?.prompt || panel.content?.content || ''
    if (!prompt.trim()) {
      ElMessage.warning('无法重试：未找到提示词')
      return
    }
    await generateImageFromPrompt(panel, prompt, panel.id)
  }
}

// 节点上传文件
function handleNodeUpload(panel) {
  if (panel) {
    triggerFileUpload(panel.id)
  }
}

// 配置节点：点击生成按钮，根据模式调用图片或视频合并生成流程
async function handleConfigGenerate(panel) {
  const mode = panel.content?.mode || 'text2image'
  const isVideo = mode.includes('video')

  // 校验提示词
  const prompt = panel.content?.prompt || panel.content?.composerContent || ''
  if (!prompt.trim()) {
    ElMessage.warning('请先输入提示词')
    return
  }

  // 设置生成中状态
  store.updatePanel(panel.id, { content: { generating: true, progress: 0, progressText: '准备中...' } })

  try {
    const { executeMergeGeneration, executeMergeVideoGeneration } = await import('@/lib/canvas-generation')
    const fn = isVideo ? executeMergeVideoGeneration : executeMergeGeneration

    await fn(panel.id, store, {
      onProgress: (stage) => {
        // 按阶段更新进度条与文字
        const stageMap = {
          building: { progress: 10, text: '构建上下文...' },
          creating: { progress: 25, text: '创建任务...' },
          polling: { progress: 40, text: '等待生成...' },
          generating: { progress: 60, text: '生成中...' },
          done: { progress: 100, text: '完成' },
        }
        const info = stageMap[stage]
        if (info) {
          store.updatePanel(panel.id, { content: { progress: info.progress, progressText: info.text } })
        }
        if (stage === 'done') {
          ElMessage.success(isVideo ? '视频生成完成' : '图片生成完成')
        }
      },
    })
  } catch (err) {
    console.error('[canvas] config generate error:', err)
    ElMessage.error('生成失败: ' + err.message)
  } finally {
    // 无论成功或失败，重置生成状态
    store.updatePanel(panel.id, { content: { generating: false, progress: 0, progressText: '' } })
  }
}

// ==================== 悬停工具栏 ====================

const hoveredPanelId = ref(null)
const showHoverToolbar = ref(false)
let hoverHideTimer = null

// 蒙版编辑对话框状态
const maskEditState = reactive({
  visible: false,
  panelId: null,
  imageUrl: '',
})

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

// 悬停工具栏：重试
async function handleHoverRetry() {
  const panel = hoveredPanel.value
  if (!panel) return
  await retryGeneration(panel)
}

// 悬停工具栏：存素材到素材库
async function handleHoverSaveAsset() {
  const panel = hoveredPanel.value
  if (!panel) return

  const content = panel.content || {}
  const url = content.content || content.url
  if (!url) {
    ElMessage.warning('节点没有可保存的内容')
    return
  }

  try {
    const { useAssetStore } = await import('@/stores/asset')
    const assetStore = useAssetStore()
    assetStore.registerAsset({
      type: panel.type, // 'image' | 'video' | 'audio'
      url: url,
      prompt: content.prompt || '',
      name: panel.name || `${panel.type}-${panel.id.slice(0, 8)}`,
      sourceNodeId: panel.id,
    })
    ElMessage.success('已保存到素材库')
  } catch (err) {
    ElMessage.error('保存失败: ' + (err.message || err))
  }
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

// 悬停工具栏：通用编辑（按节点类型分发）
function handleHoverEdit() {
  const panel = hoveredPanel.value
  if (!panel) return

  switch (panel.type) {
    case 'text':
      handleHoverEditText()
      break
    case 'image':
      // 触发替换图片
      triggerFileUpload(panel.id, 'image/*')
      break
    case 'video':
      triggerFileUpload(panel.id, 'video/*')
      break
    case 'audio':
      triggerFileUpload(panel.id, 'audio/*')
      break
    case 'config':
      // 聚焦到配置节点，提示用户在节点内编辑
      store.selectPanel(panel.id, { append: false })
      ElMessage.info('请在配置节点中编辑生成参数')
      break
    default:
      ElMessage.info('不支持编辑此类型节点')
  }
}

// 悬停工具栏：编辑文字（通过 store.editingPanelId 触发 CanvasNode 进入编辑模式）
function handleHoverEditText() {
  const panel = hoveredPanel.value
  if (!panel || panel.type !== 'text') return

  store.selectPanel(panel.id, { append: false })
  // 使用 nextTick 确保 CanvasNode 已渲染并响应
  nextTick(() => {
    store.editingPanelId = panel.id
  })
}

// 悬停工具栏：生图
async function handleHoverGenerateImage() {
  const panel = hoveredPanel.value
  if (!panel) return
  const prompt = panel.content?.content || panel.content?.prompt || ''
  if (!prompt.trim()) {
    ElMessage.warning('文本内容为空')
    return
  }
  await generateImageFromPrompt(panel, prompt)
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

// 悬停工具栏：反推提示词（图生文）—— 将当前 hover 图片发给 AI，生成适合 AI 绘画的英文 prompt，写入节点 prompt 字段
async function handleHoverDescribe() {
  const panel = hoveredPanel.value
  if (!panel) return

  // 取图片地址：优先 content.content，兼容 content.url
  const imageUrl = panel.content?.content || panel.content?.url
  if (!imageUrl) {
    ElMessage.warning('节点没有图片内容')
    return
  }

  // 设置节点为 loading 状态（updatePanel 对 content 深合并，不会覆盖图片地址）
  store.updatePanel(panel.id, { content: { describing: true } })

  try {
    const { createChatSession, sendMessageStream, deleteChatSession } = await import('@/api/chat')

    // 创建临时会话
    const session = await createChatSession({ title: '图片反推' })
    const sessionId = session.id || session.session_id

    // 反推指令：让 AI 描述图片并输出适合 AI 绘画的英文提示词
    const prompt = '请详细描述这张图片的内容、风格、构图、色彩等，生成一段适合 AI 绘画的英文提示词（prompt），只输出提示词本身，不要其他解释。'
    // attachments 格式：{ source: 'url', url } —— sendMessageStream 内部会转成后端 image_url 格式
    const attachments = [{ source: 'url', url: imageUrl }]

    let resultText = ''

    // SSE 流式接收：text 事件携带 event.content 增量文本
    await sendMessageStream(
      sessionId,
      prompt,
      attachments,
      (event) => {
        if (event.type === 'text' && event.content) {
          resultText += event.content
          // 实时更新节点 prompt（saveCanvas 已防抖，频繁更新安全）
          store.updatePanel(panel.id, { content: { prompt: resultText } })
        }
        // done / 其他事件类型无需额外处理
      }
    )

    // 最终写入 prompt 并清除 loading 状态
    store.updatePanel(panel.id, {
      content: {
        prompt: resultText.trim(),
        describing: false,
      },
    })
    store.pushSnapshot()
    ElMessage.success('提示词已生成')

    // 删除临时会话（失败可忽略）
    try {
      await deleteChatSession(sessionId)
    } catch (e) {
      // 忽略删除失败
    }
  } catch (err) {
    console.error('[canvas] describe error:', err)
    store.updatePanel(panel.id, { content: { describing: false } })
    ElMessage.error('反推失败: ' + (err.message || err))
  }
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
  const panel = hoveredPanel.value
  if (!panel) return
  const imageUrl = panel.content?.content || panel.content?.url
  if (!imageUrl) {
    ElMessage.warning('节点没有图片内容')
    return
  }
  maskEditState.visible = true
  maskEditState.panelId = panel.id
  maskEditState.imageUrl = imageUrl
}

// 蒙版编辑确认：调用 image2image 局部编辑
async function handleMaskConfirm({ mask, prompt }) {
  const panelId = maskEditState.panelId
  const panel = store.panels.find(p => p.id === panelId)
  if (!panel) return

  const imageUrl = panel.content?.content || panel.content?.url
  maskEditState.visible = false

  // 设置节点为 loading 状态
  store.updatePanel(panelId, { content: { status: 'loading' } })

  try {
    const { createImageTask, getImageTaskStatus } = await import('@/api/images')

    // 将图片转为 base64（如果还不是 base64）
    let base64Image = imageUrl
    if (!imageUrl.startsWith('data:')) {
      // URL 模式，需要先获取图片 base64
      const response = await fetch(imageUrl)
      const blob = await response.blob()
      base64Image = await new Promise((resolve) => {
        const reader = new FileReader()
        reader.onloadend = () => resolve(reader.result)
        reader.readAsDataURL(blob)
      })
    }

    // 创建 image2image 任务（带 mask 局部编辑）
    const resp = await createImageTask({
      prompt,
      model: 'agnes-image-2.1-flash',
      size: '1024x1024',
      base64_image: base64Image,
      mask: mask,
    })

    const taskId = resp.task_id

    // 轮询任务状态
    for (let i = 0; i < 150; i++) {
      await new Promise(r => setTimeout(r, 2000))
      const status = await getImageTaskStatus(taskId)
      if (status.status === 'completed' || status.status === 'succeeded' || status.status === 'success' || status.status === 'done') {
        const resultUrl = status.result_url || status.image_url || status.url || status.data?.[0]?.url
        store.updatePanel(panelId, { content: { content: resultUrl, status: 'success' } })
        store.pushSnapshot()
        ElMessage.success('局部编辑完成')
        return
      }
      if (status.status === 'failed' || status.status === 'error') {
        const errMsg = status.message || status.error || '编辑失败'
        store.updatePanel(panelId, { content: { status: 'error', errorDetails: errMsg } })
        ElMessage.error('编辑失败: ' + errMsg)
        return
      }
    }
    ElMessage.warning('编辑超时')
    store.updatePanel(panelId, { content: { status: 'error', errorDetails: '超时' } })
  } catch (err) {
    console.error('[canvas] mask edit error:', err)
    store.updatePanel(panelId, { content: { status: 'error', errorDetails: err.message } })
    ElMessage.error('编辑失败: ' + err.message)
  }
}

// 图片裁剪：弹出比例选择，按比例居中裁剪
async function handleHoverCrop() {
  const panel = hoveredPanel.value
  if (!panel?.content?.content) return
  const imageUrl = panel.content.content

  try {
    // 弹出比例选择
    const { value } = await ElMessageBox.prompt('选择裁剪比例（输入如 1:1, 4:3, 16:9, 3:4）', '裁剪图片', {
      inputValue: '1:1',
      inputPattern: /^\d+:\d+$/,
      inputErrorMessage: '请输入正确的比例格式，如 1:1',
    })
    const [rw, rh] = value.split(':').map(Number)

    ElMessage.info('正在裁剪...')
    const { cropImage, getImageSize } = await import('@/lib/canvas-image-ops')
    const { width, height } = await getImageSize(imageUrl)
    // 计算居中裁剪区域
    const targetRatio = rw / rh
    const currentRatio = width / height
    let cropX, cropY, cropW, cropH
    if (currentRatio > targetRatio) {
      cropH = height
      cropW = height * targetRatio
      cropX = (width - cropW) / 2
      cropY = 0
    } else {
      cropW = width
      cropH = width / targetRatio
      cropX = 0
      cropY = (height - cropH) / 2
    }
    const result = await cropImage(imageUrl, { x: cropX, y: cropY, width: cropW, height: cropH })
    store.updatePanel(panel.id, { content: { content: result } })
    store.pushSnapshot()
    ElMessage.success('裁剪完成')
  } catch (err) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.error('裁剪失败: ' + (err.message || err))
    }
  }
}

// 图片拆分：2x2 拆分为 4 份，创建新节点并连线
async function handleHoverSplit() {
  const panel = hoveredPanel.value
  if (!panel?.content?.content) return
  const imageUrl = panel.content.content

  try {
    ElMessage.info('正在拆分图片...')
    const { splitImage } = await import('@/lib/canvas-image-ops')
    const pieces = await splitImage(imageUrl, 4) // 2x2 拆分为 4 份
    // store.splitImagePanel 不接受 pieces 数组，手动创建 4 个新节点并连线
    pieces.forEach((piece, i) => {
      const newId = store.addPanel({
        type: panel.type,
        name: (panel.name || '图片') + ' (拆分 ' + (i + 1) + ')',
        x: panel.x + panel.width + 40 + i * 20,
        y: panel.y + i * 20,
        width: panel.width,
        height: panel.height,
        content: { ...panel.content, content: piece },
        meta: {},
        is_locked: false,
        is_hidden: false,
      })
      store.addConnection({
        source_panel_id: panel.id,
        target_panel_id: newId,
        type: 'flow',
      })
    })
    store.pushSnapshot()
    ElMessage.success('已拆分为 4 张图片')
  } catch (err) {
    ElMessage.error('拆分失败: ' + (err.message || err))
  }
}

// 图片放大：等比放大 2 倍
async function handleHoverUpscale() {
  const panel = hoveredPanel.value
  if (!panel?.content?.content) return
  const imageUrl = panel.content.content

  try {
    ElMessage.info('正在放大 2x...')
    const { upscaleImage } = await import('@/lib/canvas-image-ops')
    const result = await upscaleImage(imageUrl, 2)
    store.updatePanel(panel.id, { content: { content: result } })
    store.pushSnapshot()
    ElMessage.success('放大完成')
  } catch (err) {
    ElMessage.error('放大失败: ' + (err.message || err))
  }
}

// 图片超分：等比放大 4 倍
async function handleHoverSuperResolution() {
  const panel = hoveredPanel.value
  if (!panel?.content?.content) return
  const imageUrl = panel.content.content

  try {
    ElMessage.info('正在超分辨率放大 4x...')
    const { upscaleImage } = await import('@/lib/canvas-image-ops')
    const result = await upscaleImage(imageUrl, 4)
    store.updatePanel(panel.id, { content: { content: result } })
    store.pushSnapshot()
    ElMessage.success('超分完成')
  } catch (err) {
    ElMessage.error('超分失败: ' + (err.message || err))
  }
}

// 角度调整：弹出输入框，支持 90/180/270 度旋转
async function handleHoverAngle() {
  const panel = hoveredPanel.value
  if (!panel?.content?.content) return
  const imageUrl = panel.content.content

  try {
    const { value } = await ElMessageBox.prompt('请输入旋转角度（90/180/270）', '角度调整', {
      inputValue: '90',
      inputPattern: /^(90|180|270)$/,
      inputErrorMessage: '请输入 90、180 或 270',
    })
    const degrees = Number(value)

    ElMessage.info(`正在旋转 ${degrees}°...`)
    const { rotateImage } = await import('@/lib/canvas-image-ops')
    const result = await rotateImage(imageUrl, degrees)
    store.updatePanel(panel.id, { content: { content: result } })
    store.pushSnapshot()
    ElMessage.success('旋转完成')
  } catch (err) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.error('旋转失败: ' + (err.message || err))
    }
  }
}

function handleHoverViewLarge() {
  const p = hoveredPanel.value
  if (p?.content?.content) previewImage.value = p.content.content
}

// ==================== 底部工具栏事件 ====================

const showAppearancePanel = ref(false)
// 素材库面板显示开关
const showAssetLibrary = ref(false)

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

// 打开素材库（切换显示）
function handleOpenAssetLibrary() {
  showAssetLibrary.value = !showAssetLibrary.value
}

// 使用素材：在画布中央创建对应类型的节点
async function handleUseAsset(asset) {
  if (!asset?.type || !asset?.url) return
  const id = createNodeAtCenter(asset.type)
  // 历史记录的视频用后端流式接口，避免直接加载完整文件
  const nodeUrl = asset.source === 'history' && asset.type === 'video'
    ? `/api/history/video/${asset.id}/stream`
    : asset.url
  store.updatePanel(id, {
    content: {
      content: nodeUrl,
      status: 'success',
      prompt: asset.prompt || '',
    },
  })
  if (asset.name) {
    store.updatePanel(id, { name: asset.name })
  }
  ElMessage.success('已创建节点')
}

// 拖拽素材到画布：在 drop 的世界坐标位置创建节点
function handleCanvasDropAsset({ asset, worldX, worldY }) {
  if (!asset?.type || !asset?.url) return
  const size = NODE_DEFAULT_SIZES[asset.type] ?? NODE_DEFAULT_SIZES.text
  store.pushSnapshot()
  const id = store.addPanel({
    type: asset.type,
    name: asset.name || NODE_NAMES[asset.type] || '节点',
    x: worldX - size.width / 2,
    y: worldY - size.height / 2,
    width: size.width,
    height: size.height,
    content: {},
  })
  // 历史记录的视频用后端流式接口，避免直接加载完整文件
  const nodeUrl = asset.source === 'history' && asset.type === 'video'
    ? `/api/history/video/${asset.id}/stream`
    : asset.url
  store.updatePanel(id, {
    content: {
      content: nodeUrl,
      status: 'success',
      prompt: asset.prompt || '',
    },
  })
  ElMessage.success('已创建节点')
}

// 删除素材：从素材库移除
async function handleDeleteAsset(id) {
  if (!id) return
  try {
    const { useAssetStore } = await import('@/stores/asset')
    const assetStore = useAssetStore()
    await assetStore.removeAsset(id)
    ElMessage.success('已删除素材')
  } catch (err) {
    ElMessage.error('删除失败: ' + (err.message || err))
  }
}

// 素材库上传：将用户选择的文件注册为本地素材
async function handleUploadAssetFiles(files) {
  if (!files || files.length === 0) return
  try {
    const { useAssetStore } = await import('@/stores/asset')
    const assetStore = useAssetStore()
    let count = 0
    for (const file of files) {
      const type = file.type.startsWith('image/') ? 'image'
        : file.type.startsWith('video/') ? 'video'
        : file.type.startsWith('audio/') ? 'audio'
        : 'image'
      // 传入 blob（File 对象继承自 Blob），由 assetStore 持久化到 IndexedDB
      // 刷新页面后从 IndexedDB 读取 Blob 重新创建 object URL，不会失效
      await assetStore.registerAsset({
        type,
        blob: file,
        name: file.name,
        prompt: '',
      })
      count++
    }
    ElMessage.success(`已上传 ${count} 个素材`)
  } catch (err) {
    ElMessage.error('上传失败: ' + (err.message || err))
  }
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
