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
      <!-- 画布标题栏：默认微缩态，hover 展开操作 -->
      <div
        class="canvas-title-bar"
        :class="{ expanded: titleHovered || editingTitle }"
        :style="titleBarStyle"
        @mouseenter="titleHovered = true"
        @mouseleave="titleHovered = false"
      >
        <!-- 微缩态：只显示画布名称首字图标 -->
        <div v-if="!titleHovered && !editingTitle" class="title-mini" :style="{ background: store.canvasTheme.node.activeStroke }">
          {{ (activeWorkspaceName || 'C').charAt(0) }}
        </div>

        <!-- 展开态：画布名称 + 操作按钮 -->
        <template v-else>
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
          <!-- 画布名称显示（点击打开管理弹窗） -->
          <span
            v-else
            class="canvas-selector"
            :style="{ color: store.canvasTheme.node.text }"
            :title="t('canvas.manager.title')"
            @click="managerVisible = true"
          >
            {{ activeWorkspaceName }}
          </span>
        </div>

        <!-- 画布管理按钮组 -->
        <div class="title-actions">
          <button class="title-btn" :style="titleBtnStyle" :title="t('canvas.messages.rename')" @click="startEditTitle">
            <Pencil :size="15" />
          </button>
          <button class="title-btn" :style="titleBtnStyle" :title="t('canvas.manager.newCanvas')" @click="newCanvas">
            <Plus :size="16" />
          </button>
          <button class="title-btn" :style="titleBtnStyle" :title="t('canvas.messages.exportJsonTip')" @click="handleExportJson">
            <Download :size="16" />
          </button>
          <!-- 管理按钮：打开完整管理弹窗（批量操作、模板库） -->
          <button class="title-btn" :style="titleBtnStyle" :title="t('canvas.manager.title')" @click="managerVisible = true">
            <LayoutGrid :size="16" />
          </button>
        </div>
        </template>
      </div>

      <!-- 无限画布（背景网格 + 视口变换 + 连线层 + 节点层） -->
      <InfiniteCanvas
        ref="canvasRef"
        :pan-enabled="activeTool !== 'select'"
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
        :active-tool="activeTool"
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
        @show-shortcuts="handleShowShortcuts"
      />

      <!-- ============ 左下角缩放控件 ============ -->
      <CanvasZoomControls
        ref="zoomControlsRef"
        class="zoom-controls"
        :theme="store.canvasTheme"
        :zoom="store.viewport.zoom"
        :minimap-visible="minimapVisible"
        @toggle-minimap="minimapVisible = !minimapVisible"
        @reset-view="store.resetView()"
        @zoom-change="(z) => store.setZoom(z)"
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
          @generate-image="handleHoverGenerateImage"
          @quick-generate="handleQuickGenerate"
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

      <!-- ============ 图片加工弹窗 ============ -->
      <!-- 裁剪弹窗 -->
      <CanvasImageCropDialog
        v-if="imageOpsState.crop.visible"
        :visible="imageOpsState.crop.visible"
        :image-url="imageOpsState.crop.imageUrl"
        :theme="store.canvasTheme"
        @confirm="handleCropConfirm"
        @cancel="imageOpsState.crop.visible = false"
      />
      <!-- 拆分弹窗 -->
      <CanvasImageSplitDialog
        v-if="imageOpsState.split.visible"
        :visible="imageOpsState.split.visible"
        :image-url="imageOpsState.split.imageUrl"
        :theme="store.canvasTheme"
        @confirm="handleSplitConfirm"
        @cancel="imageOpsState.split.visible = false"
      />
      <!-- 放大弹窗 -->
      <CanvasImageUpscaleDialog
        v-if="imageOpsState.upscale.visible"
        :visible="imageOpsState.upscale.visible"
        :image-url="imageOpsState.upscale.imageUrl"
        :theme="store.canvasTheme"
        @confirm="handleUpscaleConfirm"
        @cancel="imageOpsState.upscale.visible = false"
      />
      <!-- AI 多角度弹窗 -->
      <CanvasImageAngleDialog
        v-if="imageOpsState.angle.visible"
        :visible="imageOpsState.angle.visible"
        :image-url="imageOpsState.angle.imageUrl"
        :theme="store.canvasTheme"
        @confirm="handleAngleConfirm"
        @cancel="imageOpsState.angle.visible = false"
      />

      <!-- ============ 画布管理弹窗（批量操作、模板库） ============ -->
      <CanvasManagerPopover
        v-model="managerVisible"
        @new-canvas="newCanvas"
        @import-json="importJson"
        @save-as-template="openSaveTemplateDialog"
        @use-template="handleUseTemplate"
      />

      <!-- ============ 保存为模板对话框 ============ -->
      <el-dialog
        v-model="saveTemplateVisible"
        :title="t('canvas.templates.saveTitle')"
        width="440px"
        :append-to-body="true"
      >
        <el-form :model="saveTemplateForm" label-position="top">
          <el-form-item :label="t('canvas.templates.nameLabel')">
            <el-input
              v-model="saveTemplateForm.name"
              :placeholder="t('canvas.templates.namePlaceholder')"
              maxlength="40"
              show-word-limit
            />
          </el-form-item>
          <el-form-item :label="t('canvas.templates.descLabel')">
            <el-input
              v-model="saveTemplateForm.description"
              type="textarea"
              :rows="3"
              :placeholder="t('canvas.templates.descPlaceholder')"
              maxlength="120"
              show-word-limit
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="saveTemplateVisible = false">{{ t('canvas.templates.cancel') }}</el-button>
          <el-button type="primary" :loading="saveTemplateLoading" @click="handleSaveAsTemplate">
            {{ t('canvas.templates.confirmSave') }}
          </el-button>
        </template>
      </el-dialog>

      <!-- ============ 图片预览弹窗 ============ -->
      <div v-if="previewImage" class="preview-overlay" @click="previewImage = null">
        <img :src="previewImage" class="preview-img" @click.stop />
        <button class="preview-close" @click="previewImage = null">×</button>
      </div>

      <!-- ============ 快捷生成配置弹窗（从文本/图片节点快速触发生图/生视频） ============ -->
      <GenerationQuickPanel
        v-model="quickGenerateState.visible"
        :source-panel="quickGenerateState.sourcePanel"
        :mode="quickGenerateState.mode"
        @generate="handleQuickGenerateConfirm"
      />

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

<script setup lang="ts">
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
import { Download, Pencil, Plus, LayoutGrid } from 'lucide-vue-next'
import { useI18n } from '@/i18n'
import { useCanvasStore } from '@/stores/canvas'
import { useTaskQueueStore } from '@/stores/taskQueue'
import { useModelsStore } from '@/stores/models'
import { usePreferencesStore } from '@/stores/preferences'
import InfiniteCanvas from '@/components/canvas/InfiniteCanvas.vue'
import CanvasConnectionsLayer from '@/components/canvas/CanvasConnectionsLayer.vue'
import CanvasNode from '@/components/canvas/CanvasNode.vue'
import CanvasToolbar from '@/components/canvas/CanvasToolbar.vue'
import CanvasZoomControls from '@/components/canvas/CanvasZoomControls.vue'
import CanvasMinimap from '@/components/canvas/CanvasMinimap.vue'
import CanvasNodeHoverToolbar from '@/components/canvas/CanvasNodeHoverToolbar.vue'
import CanvasContextMenu from '@/components/canvas/CanvasContextMenu.vue'
import CanvasAssetLibrary from '@/components/canvas/CanvasAssetLibrary.vue'
import GenerationQuickPanel from '@/components/canvas/GenerationQuickPanel.vue'
import MaskEditDialog from '@/components/canvas/MaskEditDialog.vue'
import CanvasImageCropDialog from '@/components/canvas/CanvasImageCropDialog.vue'
import CanvasImageSplitDialog from '@/components/canvas/CanvasImageSplitDialog.vue'
import CanvasImageUpscaleDialog from '@/components/canvas/CanvasImageUpscaleDialog.vue'
import CanvasImageAngleDialog from '@/components/canvas/CanvasImageAngleDialog.vue'
// 画布模板库组件
import CanvasManagerPopover from '@/components/canvas/CanvasManagerPopover.vue'
// 画布积分预估与校验（生图/生视频/局部编辑前预检积分）
import { checkCreditsBeforeGenerate, showCostConsumedMessage } from '@/lib/canvas-credits'
// 画布模板管理（保存/加载/创建画布）
import {
  type CanvasTemplate,
  saveAsTemplate,
  createWorkspaceFromTemplate,
} from '@/lib/canvas-templates'
// 画布生成：上游节点查找（用于配置节点 prompt 为空时检查上游文本）
import { getUpstreamNodes } from '@/lib/canvas-generation'

const { t } = useI18n()

const store = useCanvasStore()
const taskQueue = useTaskQueueStore()

// ---------- 节点默认尺寸（对齐参考项目） ----------
const NODE_DEFAULT_SIZES = {
  text: { width: 340, height: 240 },
  image: { width: 340, height: 240 },
  video: { width: 420, height: 236 },
  audio: { width: 340, height: 120 },
  config: { width: 340, height: 240 },
}

// ---------- 节点类型名称（国际化） ----------
function getNodeName(type: string): string {
  return t(`canvas.nodeNames.${type}`)
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
  store.createWorkspace(`${t('canvas.canvas')} ${store.workspaces.length + 1}`)
  ElMessage.success(t('canvas.messages.canvasCreated'))
}

function importJson() {
  triggerFileUpload(null, '.json')
}

// ==================== 标题编辑 ====================

const editingTitle = ref(false)
const titleInput = ref('')
const titleInputRef = ref<HTMLInputElement | null>(null)
const activeWorkspaceName = computed(() => store.activeWorkspace?.name ?? t('canvas.topBar.titlePlaceholder'))

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

// ==================== 工具模式（hand=移动，select=选择框选） ====================

// 当前激活的工具：hand（默认，拖动平移画布）/ select（拖动框选节点）
const activeTool = ref<'hand' | 'select'>('hand')

// ==================== 框选（选择模式拖动 / Ctrl/Cmd + 拖动背景） ====================

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

// 画布指针按下：
// - 选择模式（activeTool === 'select'）：直接拖动框选节点
// - 移动模式（hand）：Ctrl/Cmd + 拖动背景才框选，否则交给 InfiniteCanvas 平移
function handleCanvasPointerDown(event: PointerEvent) {
  if (event.button !== 0) return
  // 选择模式直接框选；移动模式需要 Ctrl/Cmd 才框选
  const isSelectMode = activeTool.value === 'select'
  if (!isSelectMode && !(event.ctrlKey || event.metaKey)) return
  // 检查是否点击在背景上（非节点、非连线）
  const target = event.target instanceof Element ? event.target : null
  if (target?.closest?.('[data-node-id],[data-connection-id]')) return

  selectionBox.active = true
  selectionBox.startScreenX = event.clientX
  selectionBox.startScreenY = event.clientY
  selectionBox.endScreenX = event.clientX
  selectionBox.endScreenY = event.clientY

  // 选择模式下阻止事件冒泡，避免 InfiniteCanvas 同时平移画布
  if (isSelectMode) {
    event.stopPropagation()
    event.preventDefault()
  }

  window.addEventListener('pointermove', handleSelectionMove)
  window.addEventListener('pointerup', handleSelectionUp)
}

// 框选拖动：实时更新框选矩形并选中范围内节点
function handleSelectionMove(event: PointerEvent) {
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

function handleNodeSelect(panelId: string) {
  store.selectPanel(panelId, { append: ctrlPressed.value })
}

// ==================== 节点交互：拖拽移动 ====================

const dragState = reactive({
  active: false,
  draggedId: null as string | null,
  initialPositions: {} as Record<string, { x: number; y: number }>,
  hasMoved: false,
})

// 节点拖拽开始：记录所有选中节点的初始位置
function handleNodeDragStart({ id, event: _event }: { id: string; event: PointerEvent }) {
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
function handleNodeDrag({ id, x, y }: { id: string; x: number; y: number }) {
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
function handleNodeDragEnd({ id }: { id: string }) {
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
  panelId: null as string | null,
  hasMoved: false,
})

// 节点缩放开始：压入快照
function handleNodeResizeStart({ id }: { id: string }) {
  resizeState.active = true
  resizeState.panelId = id
  resizeState.hasMoved = false
  store.pushSnapshot()
}

// 节点缩放中：直接更新节点尺寸
function handleNodeResize({ id, width, height, x, y }: { id: string; width: number; height: number; x: number; y: number }) {
  store._updatePanelDirect(id, { width, height, x, y })
  resizeState.hasMoved = true
}

// 节点缩放结束：触发一次保存
function handleNodeResizeEnd({ id }: { id: string }) {
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
function handleNodeStartConnecting(panelId: string, anchorType: string) {
  store.startConnecting(panelId, anchorType)
  window.addEventListener('pointermove', handleConnectingMove)
  window.addEventListener('pointerup', handleConnectingUp)
}

// 连线拖拽中：更新临时连线终点
function handleConnectingMove(event: PointerEvent) {
  if (!store.connecting) return
  const world = store.screenToWorld(event.clientX, event.clientY)
  store.updateConnecting(world.x, world.y)
}

// 连线结束：检测是否释放在节点上
function handleConnectingUp(event: PointerEvent) {
  window.removeEventListener('pointermove', handleConnectingMove)
  window.removeEventListener('pointerup', handleConnectingUp)
  if (!store.connecting) return
  const el = document.elementFromPoint(event.clientX, event.clientY)
  const nodeEl = el?.closest?.('[data-node-id]')
  if (nodeEl) {
    const targetId = nodeEl.getAttribute('data-node-id')!
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
  targetType: 'node' as 'node' | 'connection',
  targetId: null as string | null,
})

// 节点右键：打开菜单
function handleNodeContextMenu(event: PointerEvent) {
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
function handleViewImage(imageUrl: string) {
  if (imageUrl) previewImage.value = imageUrl
}

// 编辑文本节点内容
function handleNodeEditText(panelId: string, text: string) {
  store.pushSnapshot()
  store.updatePanel(panelId, { content: { content: text } })
}

// 从文本节点生图：读取文本内容作为 prompt，在源节点旁创建 image 节点并连线
async function handleNodeGenerateImage(panel: typeof store.panels[number]) {
  const prompt = (panel.content?.content || panel.content?.prompt || '') as string
  if (!prompt.trim()) {
    ElMessage.warning(t('canvas.messages.textNodeEmpty'))
    return
  }
  await generateImageFromPrompt(panel, prompt)
}

// ==================== 快捷生成弹窗（从文本/图片节点快速触发生图/生视频） ====================

// 弹窗状态：visible + 源节点 + 模式（text2image/text2video/image2image/image2video）
const quickGenerateState = reactive({
  visible: false,
  sourcePanel: null as any,
  mode: 'text2image' as 'text2image' | 'text2video' | 'image2image' | 'image2video',
})

// 打开快捷生成弹窗（由文本/图片节点的生图/生视频按钮触发）
function handleQuickGenerate({ panel, mode }: { panel: any; mode: string }) {
  // 校验源内容非空
  if (panel.type === 'text') {
    const text = (panel.content?.content || '').trim()
    if (!text) {
      ElMessage.warning(t('canvas.messages.textNodeEmpty'))
      return
    }
  } else if (panel.type === 'image') {
    const img = panel.content?.content || ''
    if (!img) {
      ElMessage.warning(t('canvas.messages.imageNodeEmpty'))
      return
    }
  }
  quickGenerateState.sourcePanel = panel
  quickGenerateState.mode = mode as any
  quickGenerateState.visible = true
}

// 弹窗确认生成：根据模式拼装 prompt 和参考图，调用图片/视频生成 API
async function handleQuickGenerateConfirm(payload: any) {
  const { mode, prompt: auxPrompt, model, size, aspect_ratio, seconds } = payload
  const sourcePanel = quickGenerateState.sourcePanel
  if (!sourcePanel) return

  // 拼装最终 prompt 和参考图
  let finalPrompt = ''
  let referenceImages: string[] = []

  if (mode.startsWith('text')) {
    // 文本源：主提示词 = 文本内容 + 辅助提示词（可选）
    const textContent = (sourcePanel.content?.content || '').trim()
    finalPrompt = auxPrompt.trim() ? `${textContent}\n\n${auxPrompt.trim()}` : textContent
  } else {
    // 图片源：参考图 = 图片内容，prompt = 辅助提示词
    referenceImages = [sourcePanel.content?.content || '']
    finalPrompt = auxPrompt.trim()
  }

  // 根据模式调用对应的生成函数
  if (mode.includes('video')) {
    await generateVideoFromSource(sourcePanel, finalPrompt, model, aspect_ratio, seconds, referenceImages)
  } else {
    await generateImageFromSource(sourcePanel, finalPrompt, model, size, referenceImages)
  }
}

// 重试生成：查找上游 config 节点重新生成，或用节点自身 prompt 重新生成
async function handleNodeRetry(panel: typeof store.panels[number]) {
  await retryGeneration(panel)
}

// 通用：从 prompt 生成图片，在源节点旁创建 image 节点并连线
// - sourcePanel: 源节点（文本节点或重试时的图片节点）
// - prompt: 提示词
// - targetPanelId: 可选，若提供则更新该节点而不是创建新节点（用于重试场景）
// - 同步注册到任务队列，让画布任务在队列面板中可见
// - 生成前预检积分，余额不足时中止并提示
async function generateImageFromPrompt(sourcePanel: typeof store.panels[number], prompt: string, targetPanelId: string | null = null) {
  // 积分预检：余额不足直接中止，不创建 loading 节点
  // 根据偏好设置的比例匹配图片尺寸
  const prefsStore = usePreferencesStore()
  const ratio = prefsStore.generation.default_aspect_ratio || '1:1'
  const { getModelParams } = await import('@/config/model-params')
  const imgParams = getModelParams()
  const [rw, rh] = ratio.split(':').map(Number)
  const matchedSize = (rw && rh) ? imgParams.imageSizes.find(o => o.w === rw && o.h === rh) : null
  const size = matchedSize?.value || '1024x1024'
  const canGenerate = await checkCreditsBeforeGenerate({ type: 'image', mode: 'text2image', size })
  if (!canGenerate) return

  let newPanelId: string | null = targetPanelId

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
    const resp = await createImageTask({ prompt, model: useModelsStore().defaultImageModel, size, response_format: 'url' })
    const taskId = resp.task_id

    // 注册到任务队列（让画布任务在队列面板中可见）
    taskQueue.registerCanvasTask({
      taskId,
      type: 'image',
      prompt,
      backendTaskId: taskId,
      panelId: newPanelId || undefined,
    })

    // 轮询任务状态（间隔 2 秒，最多 150 次 ≈ 5 分钟）
    const maxAttempts = 150
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 2000))
      const status = await getImageTaskStatus(taskId)
      const isSuccess = ['completed', 'succeeded', 'success', 'done'].includes(status.status)
      const isFailed = ['failed', 'error'].includes(status.status)

      if (isSuccess) {
        const imageUrl = status.result_url || (status as any).image_url || status.url || (status as any).data?.[0]?.url
        store.updatePanel(newPanelId!, { content: { content: imageUrl, status: 'success' } })
        store.pushSnapshot()
        taskQueue.updateCanvasTask(taskId, { status: 'success', resultUrl: imageUrl, progress: 100 })
        // 成功提示附带消耗积分数量
        showCostConsumedMessage({ type: 'image', mode: 'text2image', size }, t('canvas.messages.imageGenerationDone'))
        // 【用户偏好】自动下载 + 完成通知
        const prefsStore = usePreferencesStore()
        prefsStore.autoDownload(imageUrl, 'image', { modelId: useModelsStore().defaultImageModel })
        prefsStore.notifyComplete('image', { prompt, modelId: useModelsStore().defaultImageModel })
        return
      }
      if (isFailed) {
        const errMsg = status.message || (status as any).error || t('canvas.messages.generateFailed')
        store.updatePanel(newPanelId!, { content: { status: 'error', errorDetails: errMsg } })
        taskQueue.updateCanvasTask(taskId, { status: 'failed' })
        ElMessage.error(`${t('canvas.messages.imageGenerationFailed')}: ${errMsg}`)
        return
      }
      // 更新队列进度
      const progress = typeof status.progress === 'number' ? status.progress : undefined
      taskQueue.updateCanvasTask(taskId, { status: 'processing', progress })
    }
    // 超时
    store.updatePanel(newPanelId!, { content: { status: 'error', errorDetails: t('canvas.messages.generateTimeout') } })
    taskQueue.updateCanvasTask(taskId, { status: 'failed' })
    ElMessage.warning(t('canvas.messages.generateTimeout'))
  } catch (err) {
    console.error('[canvas] generate image error:', err)
    store.updatePanel(newPanelId!, { content: { status: 'error', errorDetails: (err as Error).message } })
    ElMessage.error(`${t('canvas.messages.generateFailed')}: ${(err as Error).message}`)
  }
}

// 快捷生成图片：支持自定义模型/尺寸/参考图（从快捷生成弹窗触发）
// - sourcePanel: 源节点（文本/图片）
// - prompt: 最终提示词（已合并辅助提示词）
// - model/size: 自定义参数
// - referenceImages: 参考图 URL 列表（图生图模式）
async function generateImageFromSource(
  sourcePanel: typeof store.panels[number],
  prompt: string,
  model: string,
  size: string,
  referenceImages: string[] = [],
) {
  const mode = referenceImages.length > 0 ? 'image2image' : 'text2image'
  // 积分预检
  const canGenerate = await checkCreditsBeforeGenerate({ type: 'image', mode, size })
  if (!canGenerate) return

  // 在源节点右侧创建 image 节点（loading 状态）
  const newPanelId = store.addPanel({
    type: 'image',
    x: sourcePanel.x + sourcePanel.width + 60,
    y: sourcePanel.y,
    width: 340,
    height: 240,
    content: { content: '', status: 'loading', prompt },
  })
  store.addConnection({ source_panel_id: sourcePanel.id, target_panel_id: newPanelId })
  store.pushSnapshot()

  try {
    // 处理参考图：blob URL 转 base64，data URI 直接用，公网 URL 直接用
    let base64Images: string[] = []
    let imageUrls: string[] = []
    if (referenceImages.length > 0) {
      const { toBase64IfNeeded } = await import('@/lib/canvas-image-ops')
      for (const img of referenceImages) {
        const processed = await toBase64IfNeeded(img)
        if (processed.startsWith('data:')) {
          base64Images.push(processed)
        } else if (processed.startsWith('http')) {
          imageUrls.push(processed)
        } else {
          base64Images.push(processed)
        }
      }
    }

    // 调用图片生成 API
    const { createImageTask, getImageTaskStatus } = await import('@/api/images')
    const resp = await createImageTask({
      prompt,
      model: model || useModelsStore().defaultImageModel,
      size,
      response_format: 'url',
      mode: mode as 'text2image' | 'image2image',
      base64_images: base64Images.length > 0 ? base64Images : null,
      image_urls: imageUrls.length > 0 ? imageUrls : null,
    })
    const taskId = resp.task_id

    // 注册到任务队列
    taskQueue.registerCanvasTask({
      taskId,
      type: 'image',
      prompt,
      backendTaskId: taskId,
      panelId: newPanelId,
    })

    // 轮询任务状态（间隔 2 秒，最多 150 次 ≈ 5 分钟）
    const maxAttempts = 150
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 2000))
      const status = await getImageTaskStatus(taskId)
      const isSuccess = ['completed', 'succeeded', 'success', 'done'].includes(status.status)
      const isFailed = ['failed', 'error'].includes(status.status)

      if (isSuccess) {
        const imageUrl = status.result_url || (status as any).image_url || status.url || (status as any).data?.[0]?.url
        store.updatePanel(newPanelId, { content: { content: imageUrl, status: 'success' } })
        store.pushSnapshot()
        taskQueue.updateCanvasTask(taskId, { status: 'success', resultUrl: imageUrl, progress: 100 })
        showCostConsumedMessage({ type: 'image', mode, size }, t('canvas.messages.imageGenerationDone'))
        // 【用户偏好】自动下载 + 完成通知
        const prefsStore = usePreferencesStore()
        prefsStore.autoDownload(imageUrl, 'image', { modelId: model || useModelsStore().defaultImageModel })
        prefsStore.notifyComplete('image', { prompt, modelId: model || useModelsStore().defaultImageModel })
        return
      }
      if (isFailed) {
        const errMsg = status.message || (status as any).error || t('canvas.messages.generateFailed')
        store.updatePanel(newPanelId, { content: { status: 'error', errorDetails: errMsg } })
        taskQueue.updateCanvasTask(taskId, { status: 'failed' })
        ElMessage.error(`${t('canvas.messages.imageGenerationFailed')}: ${errMsg}`)
        return
      }
      const progress = typeof status.progress === 'number' ? status.progress : undefined
      taskQueue.updateCanvasTask(taskId, { status: 'processing', progress })
    }
    // 超时
    store.updatePanel(newPanelId, { content: { status: 'error', errorDetails: t('canvas.messages.generateTimeout') } })
    taskQueue.updateCanvasTask(taskId, { status: 'failed' })
    ElMessage.warning(t('canvas.messages.generateTimeout'))
  } catch (err) {
    console.error('[canvas] quick generate image error:', err)
    store.updatePanel(newPanelId, { content: { status: 'error', errorDetails: (err as Error).message } })
    ElMessage.error(`${t('canvas.messages.generateFailed')}: ${(err as Error).message}`)
  }
}

// 快捷生成视频：支持文生视频/图生视频（从快捷生成弹窗触发）
// - sourcePanel: 源节点（文本/图片）
// - prompt: 最终提示词
// - model/aspect_ratio/seconds: 视频参数
// - referenceImages: 参考图（图生视频模式，取第一张）
async function generateVideoFromSource(
  sourcePanel: typeof store.panels[number],
  prompt: string,
  model: string,
  aspectRatio: string,
  seconds: number,
  referenceImages: string[] = [],
) {
  const mode = referenceImages.length > 0 ? 'image2video' : 'text2video'
  // 积分预检
  const canGenerate = await checkCreditsBeforeGenerate({ type: 'video', mode, seconds })
  if (!canGenerate) return

  // 在源节点右侧创建 video 节点（loading 状态）
  const newPanelId = store.addPanel({
    type: 'video',
    x: sourcePanel.x + sourcePanel.width + 60,
    y: sourcePanel.y,
    width: 360,
    height: 240,
    content: { content: '', status: 'loading', prompt },
  })
  store.addConnection({ source_panel_id: sourcePanel.id, target_panel_id: newPanelId })
  store.pushSnapshot()

  try {
    // 处理参考图（图生视频）：blob URL 转 base64
    let imageBase64: string | null = null
    if (referenceImages.length > 0) {
      const { toBase64IfNeeded } = await import('@/lib/canvas-image-ops')
      imageBase64 = await toBase64IfNeeded(referenceImages[0])
    }

    // 调用视频生成 API
    const { createVideoTask, getVideoStatus } = await import('@/api/videos')
    const resp = await createVideoTask({
      prompt,
      model: model || useModelsStore().defaultVideoModel,
      aspect_ratio: aspectRatio,
      seconds,
      mode: mode as 'text2video' | 'image2video',
      image: imageBase64,
    })
    const taskId = resp.task_id
    if (!taskId) {
      throw new Error('视频生成 API 未返回任务 ID')
    }

    // 注册到任务队列
    taskQueue.registerCanvasTask({
      taskId,
      type: 'video',
      prompt,
      backendTaskId: taskId,
      panelId: newPanelId,
    })

    // 轮询任务状态（间隔 3 秒，最多 100 次 ≈ 5 分钟）
    const maxAttempts = 100
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 3000))
      const status = await getVideoStatus(taskId)
      const isSuccess = ['completed', 'succeeded', 'success', 'done'].includes(status.status)
      const isFailed = ['failed', 'error'].includes(status.status)

      if (isSuccess) {
        const videoUrl = status.video_url || ''
        if (!videoUrl) {
          throw new Error('视频生成成功但未返回视频 URL')
        }
        store.updatePanel(newPanelId, { content: { content: videoUrl, status: 'success' } })
        store.pushSnapshot()
        taskQueue.updateCanvasTask(taskId, { status: 'success', resultUrl: videoUrl, progress: 100 })
        showCostConsumedMessage({ type: 'video', mode, seconds }, t('canvas.messages.videoGenerationDone'))
        const prefsStore = usePreferencesStore()
        prefsStore.autoDownload(videoUrl, 'video', { modelId: model || useModelsStore().defaultVideoModel })
        prefsStore.notifyComplete('video', { prompt, modelId: model || useModelsStore().defaultVideoModel })
        return
      }
      if (isFailed) {
        const errMsg = status.message || (status as any).error || t('canvas.messages.generateFailed')
        store.updatePanel(newPanelId, { content: { status: 'error', errorDetails: errMsg } })
        taskQueue.updateCanvasTask(taskId, { status: 'failed' })
        ElMessage.error(`${t('canvas.messages.videoGenerationFailed')}: ${errMsg}`)
        return
      }
      const progress = typeof status.progress === 'number' ? status.progress : undefined
      taskQueue.updateCanvasTask(taskId, { status: 'processing', progress })
    }
    // 超时
    store.updatePanel(newPanelId, { content: { status: 'error', errorDetails: t('canvas.messages.generateTimeout') } })
    taskQueue.updateCanvasTask(taskId, { status: 'failed' })
    ElMessage.warning(t('canvas.messages.generateTimeout'))
  } catch (err) {
    console.error('[canvas] quick generate video error:', err)
    store.updatePanel(newPanelId, { content: { status: 'error', errorDetails: (err as Error).message } })
    ElMessage.error(`${t('canvas.messages.generateFailed')}: ${(err as Error).message}`)
  }
}

// 通用：重试生成
// - 查找上游 config 节点，重新执行合并生成（创建新的 loading 结果节点）
// - 没有上游 config 节点时，用节点自身 prompt 重新生成（直接更新当前节点）
async function retryGeneration(panel: typeof store.panels[number]) {
  // 查找上游 config 节点
  const upstreamConnections = store.connections.filter((c) => c.target_panel_id === panel.id)
  const configConn = upstreamConnections.find((c) => {
    const source = store.panels.find((p) => p.id === c.source_panel_id)
    return source?.type === 'config'
  })

  if (configConn) {
    // 有上游 config 节点，重新执行合并生成（会创建新的 loading 结果节点）
    const configNode = store.panels.find((p) => p.id === configConn.source_panel_id)
    if (!configNode) return
    try {
      const { executeMergeGeneration, executeMergeVideoGeneration } = await import('@/lib/canvas-generation')
      const isVideo = panel.type === 'video'
      const fn = isVideo ? executeMergeVideoGeneration : executeMergeGeneration

      // 积分预检：根据 config 节点模式构造预估参数
      const mode = (configNode.content?.mode || 'text2image') as string
      const estimateParams = isVideo
        ? { type: 'video' as const, mode, seconds: (configNode.content?.seconds as number) || 5 }
        : { type: 'image' as const, mode, size: (configNode.content?.size as string) || '1024x1024' }
      const canGenerate = await checkCreditsBeforeGenerate(estimateParams)
      if (!canGenerate) return

      // 先把当前失败的节点设为 loading
      store.updatePanel(panel.id, { content: { status: 'loading', errorDetails: null } })
      ElMessage.info(t('canvas.messages.regenerate'))
      // 异步执行，不阻塞
      fn(configNode.id, store as any, {
        onProgress: (stage, data) => {
          if (stage === 'done') {
            // 成功提示附带消耗积分数量
            showCostConsumedMessage(estimateParams, t('canvas.messages.regenerateDone'))
            const ids: string[] = data?.resultNodeIds || []
            if (ids.length > 0) {
              store.selectPanel(ids[0], { append: false })
              store.centerOnPanel(ids[0])
            }
          } else if (stage === 'error') {
            ElMessage.error(`${t('canvas.messages.regenerateFailed')}: ${data?.error || ''}`)
          }
        },
      })
    } catch (err) {
      ElMessage.error(`${t('canvas.messages.retryFailed')}: ${(err as Error).message}`)
    }
  } else {
    // 没有上游 config 节点，用节点自身的 prompt 重新生成（直接更新当前节点）
    const prompt = (panel.content?.prompt || panel.content?.content || '') as string
    if (!prompt.trim()) {
      ElMessage.warning(t('canvas.messages.retryNoPrompt'))
      return
    }
    await generateImageFromPrompt(panel, prompt, panel.id)
  }
}

// 节点上传文件
function handleNodeUpload(panel: typeof store.panels[number]) {
  if (panel) {
    triggerFileUpload(panel.id)
  }
}

// 配置节点：点击生成按钮，根据模式调用图片或视频合并生成流程
// - 点击后立刻创建 loading 状态的结果节点，异步执行生成
// - 不阻塞配置面板，可连续点击生成多次
// - 生成前预检积分，余额不足时中止并提示
async function handleConfigGenerate(panel: typeof store.panels[number]) {
  const mode = (panel.content?.mode || 'text2image') as string
  const isVideo = mode.includes('video')

  // 校验提示词：prompt 为空时检查上游文本节点（配置节点 prompt 为可选补充）
  const prompt = (panel.content?.prompt || panel.content?.composerContent || '') as string
  if (!prompt.trim()) {
    // prompt 为空时，检查上游是否有文本节点（buildSimpleContext 会自动拼接上游文本）
    const upstreamNodes = getUpstreamNodes(panel.id, store.panels as any, store.connections)
    const hasUpstreamText = upstreamNodes.some(
      (p) => p.type === 'text' && ((p.content?.content as string) || '').trim(),
    )
    if (!hasUpstreamText) {
      ElMessage.warning(t('canvas.messages.promptOrUpstreamEmpty'))
      return
    }
  }

  // 积分预检：根据模式构造预估参数
  const estimateParams = isVideo
    ? {
        type: 'video' as const,
        mode,
        seconds: (panel.content?.seconds as number) || 5,
      }
    : {
        type: 'image' as const,
        mode,
        size: (panel.content?.size as string) || '1024x1024',
      }
  const canGenerate = await checkCreditsBeforeGenerate(estimateParams)
  if (!canGenerate) return

  try {
    const { executeMergeGeneration, executeMergeVideoGeneration } = await import('@/lib/canvas-generation')
    const fn = isVideo ? executeMergeVideoGeneration : executeMergeGeneration

    // 异步执行：立刻创建 loading 结果节点，后台轮询
    const newNodeId = await fn(panel.id, store as any, {
      onProgress: (stage, data) => {
        if (stage === 'done') {
          // 成功提示附带消耗积分数量
          showCostConsumedMessage(estimateParams, isVideo ? t('canvas.messages.videoGenerationDone') : t('canvas.messages.imageGenerationDone'))
          // 选中新节点并定位视口
          const ids: string[] = data?.resultNodeIds || []
          if (ids.length > 0) {
            store.selectPanel(ids[0], { append: false })
            store.centerOnPanel(ids[0])
          }
        } else if (stage === 'error') {
          ElMessage.error(isVideo ? `${t('canvas.messages.videoGenerationFailed')}: ${data?.error || ''}` : `${t('canvas.messages.imageGenerationFailed')}: ${data?.error || ''}`)
        }
      },
    })

    // 立刻选中新创建的 loading 节点并定位视口
    if (newNodeId) {
      store.selectPanel(newNodeId, { append: false })
      store.centerOnPanel(newNodeId)
    }
  } catch (err) {
    console.error('[canvas] config generate error:', err)
    ElMessage.error(`${t('canvas.messages.generateFailed')}: ${(err as Error).message}`)
  }
}

// ==================== 悬停工具栏 ====================

const hoveredPanelId = ref<string | null>(null)
const showHoverToolbar = ref(false)
let hoverHideTimer: ReturnType<typeof setTimeout> | null = null

// 蒙版编辑对话框状态
const maskEditState = reactive({
  visible: false,
  panelId: null as string | null,
  imageUrl: '' as string,
})

// 图片加工弹窗状态（裁剪/拆分/放大/AI多角度）
const imageOpsState = reactive({
  crop: { visible: false, panelId: null as string | null, imageUrl: '' },
  split: { visible: false, panelId: null as string | null, imageUrl: '' },
  upscale: { visible: false, panelId: null as string | null, imageUrl: '' },
  angle: { visible: false, panelId: null as string | null, imageUrl: '' },
})

// ============ 画布模板功能 ============
// 画布管理弹窗显示状态（批量操作、模板库）
const managerVisible = ref(false)
// 标题栏 hover 状态（控制微缩态/展开态切换）
const titleHovered = ref(false)
// 保存为模板对话框状态
const saveTemplateVisible = ref(false)
const saveTemplateLoading = ref(false)
const saveTemplateForm = reactive({
  name: '',
  description: '',
})

/** 打开"保存为模板"对话框，预填当前画布名称 */
function openSaveTemplateDialog() {
  if (!store.activeWorkspaceId || store.panels.length === 0) {
    ElMessage.warning(t('canvas.templates.emptyCanvas'))
    return
  }
  saveTemplateForm.name = store.activeWorkspace?.name || ''
  saveTemplateForm.description = ''
  saveTemplateVisible.value = true
}

/** 把当前画布保存为用户自定义模板 */
async function handleSaveAsTemplate() {
  if (!saveTemplateForm.name.trim()) {
    ElMessage.warning(t('canvas.templates.nameRequired'))
    return
  }
  saveTemplateLoading.value = true
  try {
    // 深拷贝当前画布数据（剥离 Proxy）
    const workspaceData = {
      panels: JSON.parse(JSON.stringify(store.panels)),
      connections: JSON.parse(JSON.stringify(store.connections)),
      viewport: { ...store.viewport },
    }
    await saveAsTemplate(saveTemplateForm.name, saveTemplateForm.description, workspaceData)
    ElMessage.success(t('canvas.templates.saved'))
    saveTemplateVisible.value = false
  } catch (err) {
    console.error('[canvas] save as template failed:', err)
    ElMessage.error(`${t('canvas.templates.saveFailed')}: ${(err as Error).message}`)
  } finally {
    saveTemplateLoading.value = false
  }
}

/** 从模板创建新画布 */
function handleUseTemplate(template: CanvasTemplate) {
  try {
    // 从模板数据构建新画布的 panels/connections/viewport（重新生成 id）
    const { panels, connections, viewport } = createWorkspaceFromTemplate(template)
    // 创建新画布
    const wsName = `${template.name} ${store.workspaces.length + 1}`
    store.createWorkspace(wsName)
    // 把模板数据填入新画布
    store.panels.splice(0, store.panels.length, ...panels)
    store.connections.splice(0, store.connections.length, ...connections)
    store.viewport.x = viewport.x
    store.viewport.y = viewport.y
    store.viewport.zoom = viewport.zoom
    store.pushSnapshot()
    ElMessage.success(t('canvas.messages.templateApplied'))
  } catch (err) {
    console.error('[canvas] apply template failed:', err)
    ElMessage.error(`${t('canvas.messages.templateApplyFailed')}: ${(err as Error).message}`)
  }
}

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
function handleNodeHoverEnter(panelId: string) {
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
  if (p) ElMessage.info(`${getNodeName(p.type ?? '')} | ID: ${p.id}`)
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

  const content = panel.content || {} as Record<string, unknown>
  const url = (content.content || content.url) as string
  if (!url) {
    ElMessage.warning(t('canvas.messages.noSaveContent'))
    return
  }

  try {
    const { useAssetStore } = await import('@/stores/asset')
    const assetStore = useAssetStore()
    assetStore.registerAsset({
      type: panel.type as 'image' | 'video',
      url: url,
      prompt: (content.prompt || '') as string,
      name: panel.name || `${panel.type}-${panel.id.slice(0, 8)}`,
      sourceNodeId: panel.id,
    })
    ElMessage.success(t('canvas.messages.savedToAssets'))
  } catch (err) {
    ElMessage.error(`${t('canvas.messages.saveFailed')}: ${(err as Error).message || err}`)
  }
}

function handleHoverDownload() {
  const p = hoveredPanel.value
  if (p?.content?.content) {
    const a = document.createElement('a')
    a.href = p.content.content as string
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
      ElMessage.info(`${getNodeName('config')} - ${t('canvas.messages.promptEmpty')}`)
      break
    default:
      ElMessage.info(`${getNodeName(panel.type ?? '')} - ${t('canvas.messages.saveFailed')}`)
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
// - 生成前预检积分，余额不足时中止并提示
async function handleHoverGenerateImage() {
  const panel = hoveredPanel.value
  if (!panel) return
  const prompt = (panel.content?.content || panel.content?.prompt || '') as string
  if (!prompt.trim()) {
    ElMessage.warning(t('canvas.messages.textContentEmpty'))
    return
  }
  // 积分预检
  const canGenerate = await checkCreditsBeforeGenerate({ type: 'image', mode: 'text2image', size: '1024x1024' })
  if (!canGenerate) return
  await generateImageFromPrompt(panel, prompt)
}

function handleHoverFontSizeDown() {
  if (!hoveredPanelId.value) return
  const p = store.panels.find((pp) => pp.id === hoveredPanelId.value)
  const cur = (p?.content?.fontSize ?? 16) as number
  store.updatePanel(hoveredPanelId.value, { content: { fontSize: Math.max(10, cur - 2) } })
}

function handleHoverFontSizeUp() {
  if (!hoveredPanelId.value) return
  const p = store.panels.find((pp) => pp.id === hoveredPanelId.value)
  const cur = (p?.content?.fontSize ?? 16) as number
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
  const prompt = (p?.content?.prompt ?? '') as string
  // 复制到剪贴板：优先用 Clipboard API，失败时回退到 textarea + execCommand
  // （HTTP 非安全上下文或浏览器禁用 Clipboard API 时需要兜底）
  const fallbackCopy = (text: string) => {
    try {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(textarea)
      return ok
    } catch (_) {
      return false
    }
  }

  if (navigator.clipboard?.writeText) {
    navigator.clipboard?.writeText(prompt).then(() => {
      ElMessage.success(t('canvas.messages.promptCopied'))
    }).catch(() => {
      // Clipboard API 失败（如非安全上下文），用兜底方案
      if (fallbackCopy(prompt)) {
        ElMessage.success(t('canvas.messages.promptCopied'))
      } else {
        ElMessage.warning(t('canvas.messages.copyFailed'))
      }
    })
  } else {
    // 无 Clipboard API，直接用兜底方案
    if (fallbackCopy(prompt)) {
      ElMessage.success(t('canvas.messages.promptCopied'))
    } else {
      ElMessage.warning(t('canvas.messages.copyFailed'))
    }
  }
}

// 悬停工具栏：反推提示词（图生文）—— 将当前 hover 图片发给 AI，生成适合 AI 绘画的英文 prompt
// 反推结果会同时：
//   1. 写入图片节点的 content.prompt 字段（供 Copy Prompt 使用）
//   2. 在图片右侧自动创建一个文字节点，把 prompt 作为可见文本展示，并用连线关联
async function handleHoverDescribe() {
  const panel = hoveredPanel.value
  if (!panel) return

  // 取图片地址：优先 content.content，兼容 content.url
  const imageUrl = (panel.content?.content || panel.content?.url) as string
  if (!imageUrl) {
    ElMessage.warning(t('canvas.messages.noImageContent'))
    return
  }

  // 设置节点为 loading 状态（updatePanel 对 content 深合并，不会覆盖图片地址）
  store.updatePanel(panel.id, { content: { describing: true } })

  // 预先在图片右侧创建一个文字节点用于承载反推结果
  // 流式更新时实时把增量文本写入这个文字节点，让用户看到生成过程
  const textSize = NODE_DEFAULT_SIZES.text
  store.pushSnapshot()
  const textNodeId = store.addPanel({
    type: 'text',
    name: t('canvas.nodeNames.text') + ' · ' + (panel.name || ''),
    x: panel.x + panel.width + 60,
    y: panel.y,
    width: textSize.width,
    height: textSize.height,
    content: { content: '', status: 'loading' },
  })
  // 用连线把图片和文字节点关联起来（type=flow 表示派生关系）
  store.addConnection({
    source_panel_id: panel.id,
    target_panel_id: textNodeId,
    type: 'flow',
  })

  try {
    const { createChatSession, sendMessageStream, deleteChatSession } = await import('@/api/chat')

    // 创建临时会话
    const session = await createChatSession({ title: '图片反推' })
    const sessionId = (session as any).id || (session as any).session_id

    // 反推指令：让 AI 描述图片并输出适合 AI 绘画的英文提示词
    // 措辞要点：明确这是"看图描述"任务，不是"生成图片"任务，避免 AI 误触发生图工具
    const prompt = [
      '【任务】图片反推（Image Captioning / Reverse Prompting）',
      '附件中已提供一张图片，请你仔细观察这张图片，然后用英文写一段详细的提示词（prompt），',
      '让另一个 AI 绘画模型能根据这段提示词重新生成类似的图片。',
      '',
      '要求：',
      '1. 这是图片理解任务，不要生成任何新图片，不要调用 generate_image 等工具',
      '2. 只输出一段英文提示词，不要输出中文，不要解释，不要客套话',
      '3. 提示词应包含：主体内容、风格、构图、光线、色彩、细节等关键信息',
      '4. 以英文逗号分隔的关键词或短语为主，类似 "a cat sitting on a wooden table, warm lighting, ..."',
    ].join('\n')
    // 附件格式根据图片来源选择：
    //   - data: URL（base64）→ base64_image 字段，传完整 data URI（后端要求以 "data:image/" 开头）
    //   - http(s) URL → image_url 字段（后端拉取后传给 AI）
    let attachments: any[]
    if (imageUrl.startsWith('data:')) {
      // 直接传完整 data URL，后端会作为多模态 image_url 注入给 AI
      attachments = [{
        name: 'image.png',
        base64_image: imageUrl,
        size: imageUrl.length,
        mime_type: 'image/png',
        source: 'base64' as const,
      }]
    } else {
      // 远程 http(s) URL —— 直接传给后端，后端再传给 AI 服务
      // （代理只用于浏览器 canvas 像素操作，AI 服务能直接访问远程 URL）
      attachments = [{ source: 'url' as const, url: imageUrl, name: 'image', size: 0, mime_type: 'image/url' }]
    }

    let resultText = ''

    // SSE 流式接收：text 事件携带 event.content 增量文本
    await sendMessageStream(
      sessionId,
      prompt,
      attachments,
      (event) => {
        if (event.type === 'text' && event.content) {
          resultText += event.content
          // 实时更新文字节点内容，让用户看到生成过程
          store.updatePanel(textNodeId, { content: { content: resultText } })
          // 同步写入图片节点的 prompt 字段（供 Copy Prompt 使用）
          store.updatePanel(panel.id, { content: { prompt: resultText } })
        }
        // done / 其他事件类型无需额外处理
      }
    )

    // 最终写入 prompt 并清除 loading 状态
    const finalText = resultText.trim()
    store.updatePanel(panel.id, {
      content: {
        prompt: finalText,
        describing: false,
      },
    })
    // 文字节点也标记为成功
    store.updatePanel(textNodeId, { content: { content: finalText, status: 'success' } })
    store.pushSnapshot()
    ElMessage.success(t('canvas.messages.promptGenerated'))

    // 删除临时会话（失败可忽略）
    try {
      await deleteChatSession(sessionId)
    } catch (e) {
      // 忽略删除失败
    }
  } catch (err) {
    console.error('[canvas] describe error:', err)
    store.updatePanel(panel.id, { content: { describing: false } })
    // 反推失败时把文字节点标记为错误状态并写入错误信息
    store.updatePanel(textNodeId, {
      content: {
        content: `${t('canvas.messages.describeFailed')}: ${(err as Error).message || err}`,
        status: 'error',
      },
    })
    ElMessage.error(`${t('canvas.messages.describeFailed')}: ${(err as Error).message || err}`)
  }
}

function handleHoverReplaceImage() {
  triggerFileUpload(hoveredPanelId.value, 'image/*')
}

function handleHoverToggleRatio() {
  if (!hoveredPanelId.value) return
  const p = store.panels.find((pp) => pp.id === hoveredPanelId.value)
  if (!p) return
  const cur = (p.content?.freeResize ?? false) as boolean
  // 从自由比例 → 锁比例：根据当前宽高强制调整高度，保持中心不动
  if (cur) {
    const ratio = p.width / p.height
    const newH = p.width / ratio
    const dy = (newH - p.height) / 2
    store.updatePanel(hoveredPanelId.value, {
      content: { freeResize: false },
      height: newH,
      y: p.y - dy,
    })
  } else {
    store.updatePanel(hoveredPanelId.value, { content: { freeResize: true } })
  }
  ElMessage.success(cur ? t('canvas.hoverToolbar.lockRatio') : t('canvas.hoverToolbar.unlockRatio'))
}

function handleHoverMaskEdit() {
  const panel = hoveredPanel.value
  if (!panel) return
  const imageUrl = (panel.content?.content || panel.content?.url) as string
  if (!imageUrl) {
    ElMessage.warning(t('canvas.messages.noImageContent'))
    return
  }
  maskEditState.visible = true
  maskEditState.panelId = panel.id
  maskEditState.imageUrl = imageUrl
}

// 蒙版编辑确认：调用 image2image 局部编辑
// - 同步注册到任务队列，让画布任务在队列面板中可见
// - 生成前预检积分，余额不足时中止并提示
async function handleMaskConfirm(
  { mask, prompt, base64_image }: { mask: string; prompt: string; base64_image?: string }
) {
  const panelId = maskEditState.panelId
  const panel = store.panels.find(p => p.id === panelId)
  if (!panel) return

  // 积分预检：局部编辑走 image2image 模式
  const canGenerate = await checkCreditsBeforeGenerate({ type: 'image', mode: 'image2image', size: '1024x1024' })
  if (!canGenerate) return

  const imageUrl = (panel.content?.content || panel.content?.url) as string | undefined
  maskEditState.visible = false

  // 设置节点为 loading 状态
  store.updatePanel(panelId!, { content: { status: 'loading' } })

  try {
    const { createImageTask, getImageTaskStatus } = await import('@/api/images')

    // 优先使用弹窗组件预转换好的 base64（它已经走代理下载好）；否则统一走 toBase64IfNeeded 转换
    const { toBase64IfNeeded } = await import('@/lib/canvas-image-ops')
    const base64Image = (base64_image && base64_image.startsWith('data:'))
      ? base64_image
      : await toBase64IfNeeded(imageUrl || '')

    // 创建 image2image 任务（带 mask 局部编辑），用数组形式传参与后端一致
    const resp = await createImageTask({
      prompt,
      model: useModelsStore().defaultImageModel,
      size: '1024x1024',
      response_format: 'url',
      base64_images: [base64Image],
      mask: mask,
    } as any)

    const taskId = resp.task_id

    // 注册到任务队列（让画布任务在队列面板中可见）
    taskQueue.registerCanvasTask({
      taskId,
      type: 'image',
      prompt,
      backendTaskId: taskId,
      panelId: panelId || undefined,
    })

    // 轮询任务状态
    for (let i = 0; i < 150; i++) {
      await new Promise(r => setTimeout(r, 2000))
      const status = await getImageTaskStatus(taskId)
      const isSuccess = ['completed', 'succeeded', 'success', 'done'].includes(status.status)
      const isFailed = ['failed', 'error'].includes(status.status)

      if (isSuccess) {
        const resultUrl = status.result_url || (status as any).image_url || status.url || (status as any).data?.[0]?.url
        store.updatePanel(panelId!, { content: { content: resultUrl, status: 'success' } })
        store.pushSnapshot()
        taskQueue.updateCanvasTask(taskId, { status: 'success', resultUrl, progress: 100 })
        // 成功提示附带消耗积分数量
        showCostConsumedMessage({ type: 'image', mode: 'image2image', size: '1024x1024' }, t('canvas.messages.maskEditDone'))
        // 【用户偏好】自动下载 + 完成通知
        const prefsStore = usePreferencesStore()
        prefsStore.autoDownload(resultUrl, 'image', { modelId: useModelsStore().defaultImageModel })
        prefsStore.notifyComplete('image', { prompt, modelId: useModelsStore().defaultImageModel })
        return
      }
      if (isFailed) {
        const errMsg = status.message || (status as any).error || t('canvas.messages.maskEditFailed')
        store.updatePanel(panelId!, { content: { status: 'error', errorDetails: errMsg } })
        taskQueue.updateCanvasTask(taskId, { status: 'failed' })
        ElMessage.error(`${t('canvas.messages.maskEditFailed')}: ${errMsg}`)
        return
      }
      // 更新队列进度
      const progress = typeof status.progress === 'number' ? status.progress : undefined
      taskQueue.updateCanvasTask(taskId, { status: 'processing', progress })
    }
    ElMessage.warning(t('canvas.messages.maskEditTimeout'))
    store.updatePanel(panelId!, { content: { status: 'error', errorDetails: t('canvas.messages.generateTimeout') } })
    taskQueue.updateCanvasTask(taskId, { status: 'failed' })
  } catch (err) {
    console.error('[canvas] mask edit error:', err)
    store.updatePanel(panelId!, { content: { status: 'error', errorDetails: (err as Error).message } })
    ElMessage.error(`${t('canvas.messages.maskEditFailed')}: ${(err as Error).message}`)
  }
}

// 图片裁剪：打开可视化裁剪弹窗
function handleHoverCrop() {
  const panel = hoveredPanel.value
  if (!panel?.content?.content) return
  const imageUrl = panel.content.content as string
  imageOpsState.crop.visible = true
  imageOpsState.crop.panelId = panel.id
  imageOpsState.crop.imageUrl = imageUrl
}

// 裁剪确认：按相对坐标裁剪，新建子节点并连线
async function handleCropConfirm(rect: { x: number; y: number; w: number; h: number }) {
  const panelId = imageOpsState.crop.panelId
  const panel = store.panels.find(p => p.id === panelId)
  if (!panel) return
  const imageUrl = imageOpsState.crop.imageUrl
  imageOpsState.crop.visible = false

  try {
    ElMessage.info(t('canvas.messages.cropProcessing'))
    const { cropImage, getImageSize } = await import('@/lib/canvas-image-ops')
    const { width, height } = await getImageSize(imageUrl)
    // 相对坐标转像素坐标
    const result = await cropImage(imageUrl, {
      x: rect.x * width,
      y: rect.y * height,
      width: rect.w * width,
      height: rect.h * height,
    })
    // 新建子节点并连线
    createImageChildNode(panel, result, (panel.name || '') + ' · ' + t('canvas.imageOps.croppedSuffix'))
    store.pushSnapshot()
    ElMessage.success(t('canvas.messages.cropDone'))
  } catch (err) {
    ElMessage.error(`${t('canvas.messages.cropFailed')}: ${(err as Error).message || err}`)
  }
}

// 图片拆分：打开行列选择弹窗
function handleHoverSplit() {
  const panel = hoveredPanel.value
  if (!panel?.content?.content) return
  const imageUrl = panel.content.content as string
  imageOpsState.split.visible = true
  imageOpsState.split.panelId = panel.id
  imageOpsState.split.imageUrl = imageUrl
}

// 拆分确认：按行列网格拆分，新建多个子节点并连线
async function handleSplitConfirm({ rows, cols }: { rows: number; cols: number }) {
  const panelId = imageOpsState.split.panelId
  const panel = store.panels.find(p => p.id === panelId)
  if (!panel) return
  const imageUrl = imageOpsState.split.imageUrl
  imageOpsState.split.visible = false

  try {
    ElMessage.info(t('canvas.messages.splitProcessing'))
    const { splitImageByGrid } = await import('@/lib/canvas-image-ops')
    const pieces = await splitImageByGrid(imageUrl, rows, cols)
    // 按网格排列子节点
    const cellW = panel.width / cols
    const cellH = panel.height / rows
    pieces.forEach((piece, i) => {
      const r = Math.floor(i / cols)
      const c = i % cols
      const newId = store.addPanel({
        type: 'image',
        name: `${panel.name || ''} ${r + 1}-${c + 1}`,
        x: panel.x + panel.width + 60 + c * (cellW + 16),
        y: panel.y + r * (cellH + 16),
        width: cellW,
        height: cellH,
        content: { ...panel.content, content: piece, status: 'success' },
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
    ElMessage.success(t('canvas.messages.splitDone'))
  } catch (err) {
    ElMessage.error(`${t('canvas.messages.splitFailed')}: ${(err as Error).message || err}`)
  }
}

// 图片放大：打开目标尺寸选择弹窗
function handleHoverUpscale() {
  const panel = hoveredPanel.value
  if (!panel?.content?.content) return
  const imageUrl = panel.content.content as string
  imageOpsState.upscale.visible = true
  imageOpsState.upscale.panelId = panel.id
  imageOpsState.upscale.imageUrl = imageUrl
}

// 放大确认：按目标长边放大，新建子节点并连线
async function handleUpscaleConfirm({ targetLongEdge, algorithm }: { targetLongEdge: number; algorithm: 'high' | 'bilinear' | 'nearest' }) {
  const panelId = imageOpsState.upscale.panelId
  const panel = store.panels.find(p => p.id === panelId)
  if (!panel) return
  const imageUrl = imageOpsState.upscale.imageUrl
  imageOpsState.upscale.visible = false

  try {
    ElMessage.info(t('canvas.messages.upscaleProcessing'))
    const { upscaleToLongEdge } = await import('@/lib/canvas-image-ops')
    const result = await upscaleToLongEdge(imageUrl, targetLongEdge, algorithm)
    createImageChildNode(panel, result, (panel.name || '') + ' · ' + t('canvas.imageOps.upscaledSuffix'))
    store.pushSnapshot()
    ElMessage.success(t('canvas.messages.upscaleDone'))
  } catch (err) {
    ElMessage.error(`${t('canvas.messages.upscaleFailed')}: ${(err as Error).message || err}`)
  }
}

// 图片超分：复用放大弹窗，默认 4K + 高清算法
function handleHoverSuperResolution() {
  const panel = hoveredPanel.value
  if (!panel?.content?.content) return
  const imageUrl = panel.content.content as string
  imageOpsState.upscale.visible = true
  imageOpsState.upscale.panelId = panel.id
  imageOpsState.upscale.imageUrl = imageUrl
}

// AI 多角度：打开角度配置弹窗
function handleHoverAngle() {
  const panel = hoveredPanel.value
  if (!panel?.content?.content) return
  const imageUrl = panel.content.content as string
  imageOpsState.angle.visible = true
  imageOpsState.angle.panelId = panel.id
  imageOpsState.angle.imageUrl = imageUrl
}

// AI 多角度确认：调用图生图 API，新建子节点并连线
async function handleAngleConfirm({ prompt }: { prompt: string }) {
  const panelId = imageOpsState.angle.panelId
  const panel = store.panels.find(p => p.id === panelId)
  if (!panel) return
  const imageUrl = imageOpsState.angle.imageUrl
  imageOpsState.angle.visible = false

  // 积分预检：AI 多角度走 image2image 模式
  const canGenerate = await checkCreditsBeforeGenerate({ type: 'image', mode: 'image2image', size: '1024x1024' })
  if (!canGenerate) return

  // 先创建 loading 状态的子节点
  const newId = store.addPanel({
    type: 'image',
    name: (panel.name || '') + ' · ' + t('canvas.imageOps.angleSuffix'),
    x: panel.x + panel.width + 60,
    y: panel.y,
    width: panel.width,
    height: panel.height,
    content: { content: '', status: 'loading', prompt },
    meta: {},
    is_locked: false,
    is_hidden: false,
  })
  store.addConnection({
    source_panel_id: panel.id,
    target_panel_id: newId,
    type: 'flow',
  })

  try {
    const { createImageTask, getImageTaskStatus } = await import('@/api/images')
    const { toBase64IfNeeded } = await import('@/lib/canvas-image-ops')
    // 参考图转 base64（远程 URL 会自动走后端代理下载后再转）
    const base64Image = await toBase64IfNeeded(imageUrl)

    const resp = await createImageTask({
      prompt,
      model: useModelsStore().defaultImageModel,
      size: '1024x1024',
      response_format: 'url',
      mode: 'image2image',
      // 用数组形式传参，与当前后端 schema 对齐；旧字段也保留一份兜底
      base64_images: [base64Image],
      base64_image: base64Image,
    } as any)

    const taskId = resp.task_id
    taskQueue.registerCanvasTask({
      taskId,
      type: 'image',
      prompt,
      backendTaskId: taskId,
      panelId: newId,
    })

    // 轮询任务状态
    for (let i = 0; i < 150; i++) {
      await new Promise(r => setTimeout(r, 2000))
      const status = await getImageTaskStatus(taskId)
      const isSuccess = ['completed', 'succeeded', 'success', 'done'].includes(status.status)
      const isFailed = ['failed', 'error'].includes(status.status)

      if (isSuccess) {
        const resultUrl = status.result_url || (status as any).image_url || status.url || (status as any).data?.[0]?.url
        store.updatePanel(newId, { content: { content: resultUrl, status: 'success' } })
        store.pushSnapshot()
        taskQueue.updateCanvasTask(taskId, { status: 'success', resultUrl, progress: 100 })
        showCostConsumedMessage({ type: 'image', mode: 'image2image', size: '1024x1024' }, t('canvas.messages.angleDone'))
        // 【用户偏好】自动下载 + 完成通知
        const prefsStore = usePreferencesStore()
        prefsStore.autoDownload(resultUrl, 'image', { modelId: useModelsStore().defaultImageModel })
        prefsStore.notifyComplete('image', { prompt, modelId: useModelsStore().defaultImageModel })
        return
      }
      if (isFailed) {
        const errMsg = status.message || (status as any).error || t('canvas.messages.angleFailed')
        store.updatePanel(newId, { content: { status: 'error', errorDetails: errMsg } })
        taskQueue.updateCanvasTask(taskId, { status: 'failed' })
        ElMessage.error(`${t('canvas.messages.angleFailed')}: ${errMsg}`)
        return
      }
      const progress = typeof status.progress === 'number' ? status.progress : undefined
      taskQueue.updateCanvasTask(taskId, { status: 'processing', progress })
    }
    ElMessage.warning(t('canvas.messages.generateTimeout'))
    store.updatePanel(newId, { content: { status: 'error', errorDetails: t('canvas.messages.generateTimeout') } })
    taskQueue.updateCanvasTask(taskId, { status: 'failed' })
  } catch (err) {
    console.error('[canvas] angle error:', err)
    store.updatePanel(newId, { content: { status: 'error', errorDetails: (err as Error).message } })
    ElMessage.error(`${t('canvas.messages.angleFailed')}: ${(err as Error).message}`)
  }
}

// 辅助：为图片节点创建子节点（加工结果），并连线
function createImageChildNode(parentPanel: any, imageContent: string, name: string) {
  const newId = store.addPanel({
    type: 'image',
    name,
    x: parentPanel.x + parentPanel.width + 60,
    y: parentPanel.y,
    width: parentPanel.width,
    height: parentPanel.height,
    content: { ...parentPanel.content, content: imageContent, status: 'success' },
    meta: {},
    is_locked: false,
    is_hidden: false,
  })
  store.addConnection({
    source_panel_id: parentPanel.id,
    target_panel_id: newId,
    type: 'flow',
  })
}

function handleHoverViewLarge() {
  const p = hoveredPanel.value
  if (p?.content?.content) previewImage.value = p.content.content as string
}

// ==================== 底部工具栏事件 ====================

const showAppearancePanel = ref(false)
// 素材库面板显示开关
const showAssetLibrary = ref(false)

// 选择/移动工具
// 工具栏切换工具：hand（移动）/ select（选择框选）
function handleSelectTool(tool: 'hand' | 'select') {
  activeTool.value = tool
}

// 工具栏添加节点
function handleAddNode(type: string) {
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
async function handleUseAsset(asset: Record<string, any>) {
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
  ElMessage.success(t('canvas.messages.nodeCreated'))
}

// 拖拽素材到画布：在 drop 的世界坐标位置创建节点
function handleCanvasDropAsset({ asset, worldX, worldY }: { asset: Record<string, any>; worldX: number; worldY: number }) {
  if (!asset?.type || !asset?.url) return
  const size = NODE_DEFAULT_SIZES[asset.type as keyof typeof NODE_DEFAULT_SIZES] ?? NODE_DEFAULT_SIZES.text
  store.pushSnapshot()
  const id = store.addPanel({
    type: asset.type,
    name: asset.name || getNodeName(asset.type),
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
  ElMessage.success(t('canvas.messages.nodeCreated'))
}

// 删除素材：从素材库移除
async function handleDeleteAsset(id: string) {
  if (!id) return
  try {
    const { useAssetStore } = await import('@/stores/asset')
    const assetStore = useAssetStore()
    await assetStore.removeAsset(id)
    ElMessage.success(t('canvas.messages.assetDeleted'))
  } catch (err) {
    ElMessage.error(`${t('canvas.messages.assetDeleteFailed')}: ${(err as Error).message || err}`)
  }
}

// 素材库上传：将用户选择的文件注册为本地素材
async function handleUploadAssetFiles(files: FileList | File[]) {
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
        type: type as 'image' | 'video',
        blob: file,
        name: file.name,
        prompt: '',
      })
      count++
    }
    ElMessage.success(`${t('canvas.messages.nodeCreated')}: ${count}`)
  } catch (err) {
    ElMessage.error(`${t('canvas.messages.uploadFailed')}: ${(err as Error).message || err}`)
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
  ElMessageBox.confirm(t('canvas.messages.canvasCleared'), { type: 'warning' })
    .then(() => {
      store.pushSnapshot()
      store.clearAllPanels()
      ElMessage.success(t('canvas.messages.canvasCleared'))
    })
    .catch(() => {})
}

// 切换图片信息显示
function handleToggleImageInfo(val: boolean) {
  if (val !== store.showImageInfo) store.toggleImageInfo()
}

// ==================== 缩放控件 + 小地图 ====================

const minimapVisible = ref(false)
// 左下角缩放控件引用（用于外部按钮触发快捷键弹窗）
const zoomControlsRef = ref<InstanceType<typeof CanvasZoomControls> | null>(null)
const canvasSize = computed(() => ({
  width: window.innerWidth,
  height: window.innerHeight,
}))

// 打开快捷键帮助弹窗（由底部工具栏的快捷键按钮触发）
function handleShowShortcuts() {
  zoomControlsRef.value?.openShortcuts()
}

// 小地图定位：将视口中心移动到指定世界坐标
function handleMinimapLocate(worldX: number, worldY: number) {
  const { zoom } = store.viewport
  store.viewport.x = window.innerWidth / 2 - worldX * zoom
  store.viewport.y = window.innerHeight / 2 - worldY * zoom
}

// ==================== 节点创建 ====================

// 在视口中心创建节点
function createNodeAtCenter(type: string) {
  const size = NODE_DEFAULT_SIZES[type as keyof typeof NODE_DEFAULT_SIZES] ?? NODE_DEFAULT_SIZES.text
  const cx = (window.innerWidth / 2 - store.viewport.x) / store.viewport.zoom
  const cy = (window.innerHeight / 2 - store.viewport.y) / store.viewport.zoom
  store.pushSnapshot()
  const id = store.addPanel({
    type,
    name: getNodeName(type),
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

const fileInputRef = ref<HTMLInputElement | null>(null)
const uploadTargetPanelId = ref<string | null>(null)
const fileAccept = ref('*')

// 触发文件选择对话框
function triggerFileUpload(panelId: string | null, accept = '*') {
  uploadTargetPanelId.value = panelId
  fileAccept.value = accept
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
    fileInputRef.value.click()
  }
}

// 文件选择回调
function handleFileSelect(event: Event) {
  const file = (event.target as HTMLInputElement)?.files?.[0]
  if (!file) return

  // JSON 导入
  if (file.name.endsWith('.json')) {
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        store.importJSON((e.target as FileReader)?.result as string)
        ElMessage.success(t('canvas.messages.jsonLoadedToNode'))
      } catch (err) {
        ElMessage.error(`${t('canvas.messages.jsonExported')}: ${(err as Error).message}`)
      }
    }
    reader.readAsText(file)
    return
  }

  // 文件上传到节点（图片/视频元数据由 CanvasNode 的 @load 自动读取并回填）
  const url = URL.createObjectURL(file)
  const targetId = uploadTargetPanelId.value

  if (targetId) {
    store.pushSnapshot()
    store.updatePanel(targetId, { content: { content: url, status: 'success', bytes: file.size } })
  } else {
    const type = file.type.startsWith('image/') ? 'image'
      : file.type.startsWith('video/') ? 'video'
      : file.type.startsWith('audio/') ? 'audio'
      : 'text'
    const id = createNodeAtCenter(type)
    store.updatePanel(id, { content: { content: url, status: 'success', bytes: file.size } })
  }

  uploadTargetPanelId.value = null
}

// ==================== 图片预览弹窗 ====================

const previewImage = ref<string | null>(null)

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
  ElMessage.success(t('canvas.messages.jsonExported'))
}

// ==================== 全局快捷键 ====================

function handleKeyDown(event: KeyboardEvent) {
  // 跟踪 Ctrl/Cmd 状态
  if (event.ctrlKey || event.metaKey) {
    ctrlPressed.value = true
  }

  // 输入框内不响应快捷键（Escape 除外）
  const isInput = event.target instanceof HTMLInputElement
    || event.target instanceof HTMLTextAreaElement
    || (event.target as HTMLElement)?.isContentEditable

  if (isInput) {
    if (event.key === 'Escape') {
      (event.target as HTMLElement).blur()
    }
    return
  }

  const ctrl = event.ctrlKey || event.metaKey

  // Escape：取消连线 / 关闭菜单 / 清空选中
  if (event.key === 'Escape') {
    if (store.connecting) store.cancelConnecting()
    else if (contextMenu.open) contextMenu.open = false
    else if (showAppearancePanel.value) showAppearancePanel.value = false
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
    ElMessage.success(t('canvas.messages.autoSaved'))
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
function handleKeyUp(event: KeyboardEvent) {
  if (!event.ctrlKey && !event.metaKey) {
    ctrlPressed.value = false
  }
}

// ==================== 全局点击：关闭弹出层 ====================

function handleGlobalClick(event: MouseEvent) {
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
    store.createWorkspace(`${t('canvas.canvas')} 1`)
  }
  // 注册全局事件监听
  window.addEventListener('keydown', handleKeyDown)
  window.addEventListener('keyup', handleKeyUp)
  window.addEventListener('click', handleGlobalClick)
  // 监听用户登录/退出，切换画布数据空间
  window.addEventListener('agnes:user-login', handleUserSwitch as unknown as EventListener)
  window.addEventListener('agnes:user-logout', handleUserLogout as unknown as EventListener)
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
  window.removeEventListener('agnes:user-login', handleUserSwitch as unknown as EventListener)
  window.removeEventListener('agnes:user-logout', handleUserLogout as unknown as EventListener)
  // 清理 hover 定时器
  cancelHoverHide()
})

/** 登录/切换用户后，切换到对应的数据空间 */
async function handleUserSwitch(e: CustomEvent) {
  const userId: number | null = (e?.detail?.id as number) ?? null
  await store._switchUserStorage(userId)
  if (!store.activeWorkspaceId && store.workspaces.length === 0) {
    store.createWorkspace(`${t('canvas.canvas')} 1`)
  }
}

/** 退出登录：切换到匿名数据空间 */
async function handleUserLogout() {
  await store._switchUserStorage(null)
  if (!store.activeWorkspaceId && store.workspaces.length === 0) {
    store.createWorkspace(`${t('canvas.canvas')} 1`)
  }
}
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
/* 默认微缩态：只显示首字图标；hover 展开显示名称和按钮 */
.canvas-title-bar {
  position: absolute;
  top: 16px;
  left: 16px;
  z-index: 50;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px;
  border: 1px solid;
  border-radius: 999px;
  backdrop-filter: blur(12px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
  transition: padding 0.2s ease, border-radius 0.2s ease;
  max-width: 60px;
  overflow: hidden;
}
.canvas-title-bar.expanded {
  padding: 6px 8px 6px 14px;
  border-radius: 10px;
  max-width: 480px;
}

/* 微缩态首字图标 */
.title-mini {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
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
  background: var(--agnes-bg-hover);
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
  background: var(--agnes-bg-hover);
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
  background: var(--agnes-overlay-strong);
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

/* ==================== 隐藏文件输入 ==================== */
.hidden-file-input {
  display: none;
}
</style>
