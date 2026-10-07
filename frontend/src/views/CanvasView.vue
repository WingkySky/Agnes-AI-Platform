<!-- =====================================================
     无限画布主视图（融合项目全局导航风格）
     - 画布标题栏：浮动在画布左上角（标题编辑 + 画布管理按钮）
     - 画布主体：InfiniteCanvas（分组层 + 连线层 + 节点层）+ 框选覆盖层
     - 底部浮动工具栏：节点创建 / 撤销重做 / 外观面板 / 删除清空
     - 左下角缩放控件 + 小地图
     - 节点悬停工具栏（浮动定位）
     - 右键菜单（节点 / 分组 / 连线）
     - 图片预览弹窗 + 快捷键帮助弹窗
     - 全局快捷键：Escape / Delete / Ctrl+Z / Ctrl+Shift+Z / Ctrl+D / Ctrl+A / Ctrl+S / Ctrl+L / Ctrl+G
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
          <!-- 层级面包屑：作品 › 画布（作品为家，点作品名回详情） -->
          <template v-if="activeWorkTitle && activeWorkId">
            <span class="crumb-work" :title="t('works.workDetail')" @click="router.push(`/works/${activeWorkId}`)">{{ activeWorkTitle }}</span>
            <span class="crumb-sep">›</span>
          </template>
          <!-- 云端同步状态指示器（登录态落库后显示；anon 纯本地不显示） -->
          <span
            v-if="cloudSyncEnabled && saveStatusText"
            class="save-status"
            :class="{ 'save-status-error': canvasSaveStatus.error }"
          >{{ saveStatusText }}</span>
          <!-- 远端有更新（对话 Agent/CLI 等外部写入）：点击手动同步 -->
          <span
            v-if="store.remoteUpdateAvailable"
            class="save-status remote-update"
            :title="t('canvas.saveStatus.remoteUpdate')"
            @click="handleRemoteSync"
          >{{ t('canvas.saveStatus.remoteUpdate') }}</span>
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
          <!-- 挂到作品（自由画布 → 选择归属） -->
          <button v-if="!activeWorkId" class="title-btn" :style="titleBtnStyle" :title="t('canvas.work.bindWork')" @click="openBindDialog">
            <Link2 :size="15" />
          </button>
          <!-- 管理按钮：打开完整管理弹窗（批量操作、模板库） -->
          <button class="title-btn" :style="titleBtnStyle" :title="t('canvas.manager.title')" @click="managerVisible = true">
            <LayoutGrid :size="16" />
          </button>
        </div>

        <!-- 挂到作品对话框 -->
        <el-dialog v-model="bindVisible" :title="t('canvas.work.bindWork')" width="380">
          <el-select v-model="bindWorkId" style="width: 100%">
            <el-option :label="t('canvas.work.unbindOption')" :value="null" />
            <el-option v-for="w in worksItems" :key="w.id" :label="w.title" :value="w.id" />
          </el-select>
          <template #footer>
            <el-button @click="bindVisible = false">{{ t('common.cancel') }}</el-button>
            <el-button type="primary" @click="submitBind">{{ t('common.confirm') }}</el-button>
          </template>
        </el-dialog>
        </template>
      </div>

      <!-- 无限画布（背景网格 + 视口变换 + 连线层 + 节点层） -->
      <InfiniteCanvas
        ref="canvasRef"
        :pan-enabled="activeTool !== 'select'"
        @background-click="handleBackgroundClick"
        @pointerdown="handleCanvasPointerDown"
        @pane-dblclick="handlePaneDblClick"
        @pane-contextmenu="handlePaneContextMenu"
        @drop-asset="handleCanvasDropAsset"
        @drop-files="(p) => createMediaNodesFromFiles(p.files, p.worldX, p.worldY)"
      >
        <!-- 分组层（组框在连线/节点层之下；折叠组成员由 v-show 隐藏） -->
        <CanvasGroupLayer
          v-for="group in store.groups"
          :key="group.id"
          :group="group"
          :panels="store.panels"
          :selected="selectedGroupId === group.id"
          @toggle-collapse="store.toggleGroupCollapsed(group.id)"
          @toggle-lock="store.toggleGroupLocked(group.id)"
          @cycle-color="handleGroupCycleColor(group.id)"
          @rename="(name) => store.updateGroup(group.id, { name })"
          @reference="(type) => handleGroupReference(group.id, type)"
          @rerun="handleGroupRerun(group.id)"
          @delete-group="handleGroupDeleteWithNodes(group.id)"
          @drag-start="(e) => handleGroupDragStart(group.id, e)"
          @context-menu="(e) => handleGroupContextMenu(group.id, e)"
        />

        <!-- 连线层（不传 props 时自动使用 store 数据） -->
        <CanvasConnectionsLayer />

        <!-- 节点层：遍历所有面板渲染节点（折叠分组成员隐藏但保留 DOM 状态） -->
        <CanvasNode
          v-for="panel in store.panels"
          :key="panel.id"
          v-show="!hiddenPanelIds.has(panel.id)"
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
          @view-image="handleViewImage"
          @edit-text="(text) => handleNodeEditText(panel.id, text)"
          @generate-image="handleNodeGenerateImage"
          @retry="handleNodeRetry"
          @run-node="handleNodeRun"
          @upload="(p) => handleNodeUpload(p)"
        />
      </InfiniteCanvas>

      <!-- 框选矩形（屏幕坐标覆盖层，不受画布变换影响） -->
      <div
        v-if="selectionBox.active"
        class="selection-box"
        :style="selectionBoxStyle"
      />

      <!-- 节点悬浮 AI 对话框：单选 script/text/image/video 节点时显示在节点正下方 -->
      <CanvasNodeComposer
        v-if="composerPanelId"
        :key="composerPanelId"
        :panel-id="composerPanelId"
        :style="composerStyle"
        @regenerate="generateComposerRegenerate"
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
        :auto-place-media="store.autoPlaceMedia"
        :active-tool="activeTool"
        :show-agent-panel="agentPanelOpen"
        @select-tool="handleSelectTool"
        @undo="store.undo()"
        @redo="store.redo()"
        @add-node="handleAddNode"
        @upload-asset="handleUploadAsset"
        @open-asset-library="handleOpenAssetLibrary"
        @show-history="historyVisible = true"
        @toggle-appearance-panel="showAppearancePanel = !showAppearancePanel"
        @toggle-agent-panel="agentPanelOpen = !agentPanelOpen"
        @delete-selected="handleDeleteSelected"
        @clear-canvas="handleClearCanvas"
        @set-theme="(mode) => store.setThemeMode(mode)"
        @set-background="(mode) => store.setBackgroundMode(mode)"
        @toggle-image-info="(val) => handleToggleImageInfo(val)"
        @toggle-auto-place="(val) => handleToggleAutoPlace(val)"
        @show-shortcuts="handleShowShortcuts"
        @smart-group="handleSmartGroup"
        @arrange-layout="handleArrangeLayout"
      />

      <!-- ============ 左下角缩放控件 ============ -->
      <CanvasZoomControls
        ref="zoomControlsRef"
        class="zoom-controls"
        :theme="store.canvasTheme"
        :zoom="store.viewport.zoom"
        :minimap-visible="minimapVisible"
        :connections-visible="store.showConnections"
        @toggle-minimap="minimapVisible = !minimapVisible"
        @toggle-connections="store.toggleShowConnections()"
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

      <!-- ============ 画布 Agent 面板（右侧抽屉） ============ -->
      <CanvasAgentPanel v-if="agentPanelOpen" :theme="store.canvasTheme" @close="agentPanelOpen = false" />

      <!-- ============ 节点工具栏（选中节点后常驻显示在节点上方） ============ -->
      <div
        v-if="toolbarPanel"
        class="node-toolbar-wrap"
        :style="nodeToolbarStyle"
      >
        <CanvasNodeToolbar
          :panel="toolbarPanel"
          :theme="store.canvasTheme"
          @action="handleToolAction"
        />
      </div>

      <!-- ============ 右键菜单（节点 / 分组 / 连线 / 空白画布） ============ -->
      <CanvasContextMenu
        v-if="contextMenu.open"
        :x="contextMenu.x"
        :y="contextMenu.y"
        :target-type="contextMenu.targetType"
        :selection-count="store.selectedPanelIds.length"
        :can-remove-from-group="canRemoveFromGroup"
        :theme="store.canvasTheme"
        @duplicate="handleContextDuplicate"
        @delete="handleContextDelete"
        @group-create="handleContextGroupCreate"
        @group-remove-panel="handleContextRemoveFromGroup"
        @group-dissolve="handleGroupDissolve(contextMenu.targetId)"
        @group-delete-with-nodes="handleGroupDeleteWithNodes(contextMenu.targetId)"
        @canvas-create="handleContextCanvasCreate"
        @canvas-select-all="selectAllVisible"
        @canvas-fit="store.fitContent()"
        @close="contextMenu.open = false"
      />

      <!-- ============ 快速创建菜单（双击空白 / 拖线松手落点） ============ -->
      <CanvasQuickMenu
        v-if="quickMenu.open"
        :x="quickMenu.x"
        :y="quickMenu.y"
        :mode="quickMenu.mode"
        :source-type="quickMenu.sourceType"
        :anchor-type="quickMenu.anchorType"
        :theme="store.canvasTheme"
        @select="handleQuickMenuSelect"
        @close="closeQuickMenu"
      />

      <!-- ============ 素材库浮动面板 ============ -->
      <CanvasAssetLibrary
        :work-id="store.activeWorkspace?.work_id ?? undefined"
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
      <!-- 实体选择器：从作品实体库落挂链实体卡（快捷菜单动作） -->
      <EntityPickerDialog v-model="entityPickerVisible" @select="onPickEntity" />
      <!-- AI 打光弹窗 -->
      <CanvasLightingDialog
        v-if="imageOpsState.lighting.visible"
        :visible="imageOpsState.lighting.visible"
        :image-url="imageOpsState.lighting.imageUrl"
        :theme="store.canvasTheme"
        @confirm="handleLightingConfirm"
        @cancel="imageOpsState.lighting.visible = false"
      />
      <!-- 表情控制弹窗 -->
      <CanvasEmotionDialog
        v-if="imageOpsState.emotion.visible"
        :visible="imageOpsState.emotion.visible"
        :image-url="imageOpsState.emotion.imageUrl"
        :theme="store.canvasTheme"
        :fix-jobs="imageOpsState.emotion.fixJobs"
        @confirm="handleEmotionConfirm"
        @cancel="imageOpsState.emotion.visible = false"
      />
      <!-- ============ 分类分组模式选择弹窗 ============ -->
      <el-dialog
        v-model="smartGroupDialog.visible"
        :title="t('canvas.groupMode.title')"
        width="460px"
        :append-to-body="true"
      >
        <div class="group-mode-options">
          <el-checkbox v-model="smartGroupDialog.byChain">{{ t('canvas.groupMode.byChain') }}</el-checkbox>
          <el-checkbox v-model="smartGroupDialog.byCategory">{{ t('canvas.groupMode.byCategory') }}</el-checkbox>
        </div>
        <p class="group-mode-preview" :style="{ color: store.canvasTheme.node.muted }">
          {{ t('canvas.smartGroupConfirm', { n: smartGroupPreview.count, m: smartGroupPreview.nodes }) }}
        </p>
        <template #footer>
          <el-button @click="smartGroupDialog.visible = false">{{ t('canvas.templates.cancel') }}</el-button>
          <el-button type="primary" @click="handleSmartGroupConfirm">{{ t('canvas.groupMode.confirm') }}</el-button>
        </template>
      </el-dialog>

      <!-- ============ 画布管理弹窗（批量操作、模板库） ============ -->
      <CanvasManagerPopover
        v-model="managerVisible"
        @new-canvas="newCanvas"
        @import-json="importJson"
        @save-as-template="openSaveTemplateDialog"
        @use-template="handleUseTemplate"
      />

      <!-- ============ 版本历史弹窗（自动快照 / 手动版本 / 还原） ============ -->
      <CanvasHistoryDialog v-model="historyVisible" />

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

      <!-- ============ 节点信息对话框（查看提示词等元数据） ============ -->
      <el-dialog
        v-model="nodeInfoVisible"
        :title="t('canvas.nodeInfo.title')"
        width="520px"
        :append-to-body="true"
      >
        <div class="node-info">
          <div v-if="nodeInfoPanel?.name" class="node-info-row">
            <span class="node-info-label">{{ t('canvas.nodeInfo.name') }}</span>
            <span class="node-info-value">{{ nodeInfoPanel.name }}</span>
          </div>
          <div class="node-info-row">
            <span class="node-info-label">{{ t('canvas.nodeInfo.type') }}</span>
            <span class="node-info-value">{{ getNodeName(nodeInfoPanel?.type || '') }}</span>
          </div>
          <div class="node-info-row">
            <span class="node-info-label">{{ t('canvas.nodeInfo.status') }}</span>
            <span class="node-info-value">{{ nodeInfoStatusText }}</span>
          </div>
          <div v-if="nodeInfoModel" class="node-info-row">
            <span class="node-info-label">{{ t('canvas.nodeInfo.model') }}</span>
            <span class="node-info-value">{{ nodeInfoModel }}</span>
          </div>
          <div v-if="nodeInfoSize" class="node-info-row">
            <span class="node-info-label">{{ t('canvas.nodeInfo.size') }}</span>
            <span class="node-info-value">{{ nodeInfoSize }}</span>
          </div>
          <div v-if="nodeInfoRefCount" class="node-info-row">
            <span class="node-info-label">{{ t('canvas.nodeInfo.referenceImages') }}</span>
            <span class="node-info-value">{{ t('canvas.nodeInfo.refCount', { n: nodeInfoRefCount }) }}</span>
          </div>
          <div v-if="nodeInfoShotFrom" class="node-info-row">
            <span class="node-info-label">{{ t('canvas.nodeInfo.shotFromLabel') }}</span>
            <span class="node-info-value">{{ nodeInfoShotFrom }}</span>
          </div>
          <div v-if="nodeInfoPrompt" class="node-info-prompt">
            <div class="node-info-prompt-head">
              <span class="node-info-label">{{ t('canvas.nodeInfo.prompt') }}</span>
              <el-button link size="small" type="primary" @click="handleInfoCopyPrompt">
                {{ t('canvas.hoverToolbar.copyPrompt') }}
              </el-button>
            </div>
            <div class="node-info-prompt-text">{{ nodeInfoPrompt }}</div>
          </div>
          <div class="node-info-row">
            <span class="node-info-label">ID</span>
            <span class="node-info-value node-info-id">{{ nodeInfoPanel?.id }}</span>
          </div>
        </div>
      </el-dialog>

      <!-- ============ 图片预览弹窗 ============ -->
      <div v-if="previewImage" class="preview-overlay" @click="previewImage = null">
        <!-- 关闭按钮 -->
        <button class="preview-close" @click="previewImage = null">×</button>
        <!-- 下载按钮（走后端带水印下载） -->
        <button class="preview-download" @click.stop="downloadPreviewImage" :title="t('history.download')">
          <el-icon><Download /></el-icon>
        </button>
        <!-- 使用带水印的图片组件，自带防右键另存保护；
             max 约束必须同时落在内层 img 上（外层 inline-block 包装不会把高度传下去，高图会被 overflow 裁掉） -->
        <ImageWithWatermark
          :src="previewImage"
          fit="contain"
          class="preview-img"
          :img-style="{ maxWidth: '90vw', maxHeight: '90vh' }"
          @click.stop
        />
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
 *   CanvasNodeToolbar / CanvasContextMenu / CanvasAppearancePanel（内嵌于 Toolbar）
 * - 接入 useCanvasStore：panels / connections / viewport / history
 * - 处理节点创建/拖拽/缩放/删除、连线创建/删除、框选、撤销/重做、快捷键
 * ===================================================== */

import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useConfirm } from '@/composables/useConfirm'
import { useCopyText } from '@/composables/useCopyText'
import { Download, Pencil, Plus, LayoutGrid, Link2 } from 'lucide-vue-next'
import { useI18n } from '@/i18n'
import { createEditorProject } from '@/api/editor'
import { useDownload } from '@/composables/useDownload'
import { useCanvasStore } from '@/stores/canvas'
import { useUserStore } from '@/stores/user'
import { useChatStore } from '@/stores/chat'
import { canvasSaveStatus, flushSaveCanvas } from '@/lib/canvas-storage'
import { listWorks } from '@/api/works'
import type { WorkItem } from '@/api/works'
import { setWorkspaceWork } from '@/api/canvasWorkspace'
import { useTaskQueueStore } from '@/stores/taskQueue'
import { useModelsStore } from '@/stores/models'
import { usePreferencesStore } from '@/stores/preferences'
import InfiniteCanvas from '@/components/canvas/InfiniteCanvas.vue'
import CanvasNodeComposer from '@/components/canvas/CanvasNodeComposer.vue'
import CanvasConnectionsLayer from '@/components/canvas/CanvasConnectionsLayer.vue'
import CanvasNode from '@/components/canvas/CanvasNode.vue'
import CanvasToolbar from '@/components/canvas/CanvasToolbar.vue'
import CanvasZoomControls from '@/components/canvas/CanvasZoomControls.vue'
import CanvasMinimap from '@/components/canvas/CanvasMinimap.vue'
import CanvasNodeToolbar from '@/components/canvas/CanvasNodeToolbar.vue'
import CanvasContextMenu from '@/components/canvas/CanvasContextMenu.vue'
import CanvasQuickMenu from '@/components/canvas/CanvasQuickMenu.vue'
import type { QuickMenuItem } from '@/lib/canvas-quick-menu'
import CanvasAssetLibrary from '@/components/canvas/CanvasAssetLibrary.vue'
import CanvasAgentPanel from '@/components/canvas/CanvasAgentPanel.vue'
import GenerationQuickPanel from '@/components/canvas/GenerationQuickPanel.vue'
import MaskEditDialog from '@/components/canvas/MaskEditDialog.vue'
import CanvasImageCropDialog from '@/components/canvas/CanvasImageCropDialog.vue'
import CanvasImageSplitDialog from '@/components/canvas/CanvasImageSplitDialog.vue'
import CanvasImageUpscaleDialog from '@/components/canvas/CanvasImageUpscaleDialog.vue'
import CanvasImageAngleDialog from '@/components/canvas/CanvasImageAngleDialog.vue'
import EntityPickerDialog from '@/components/canvas/EntityPickerDialog.vue'
import type { WorkEntityItem } from '@/api/workEntities'
import CanvasLightingDialog from '@/components/canvas/CanvasLightingDialog.vue'
import CanvasEmotionDialog from '@/components/canvas/CanvasEmotionDialog.vue'
// 画布分组层组件（成员制分组，替代旧流程模式步骤）
import CanvasGroupLayer from '@/components/canvas/CanvasGroupLayer.vue'
// 带水印的图片组件（预览大图时显示水印）
import ImageWithWatermark from '@/components/ImageWithWatermark.vue'
// 画布模板库组件
import CanvasManagerPopover from '@/components/canvas/CanvasManagerPopover.vue'
// 版本历史弹窗（自动快照 / 手动版本 / 还原）
import CanvasHistoryDialog from '@/components/canvas/CanvasHistoryDialog.vue'
// 画布积分预估与校验（生图/生视频/局部编辑前预检积分）
import { CANVAS_GROUP_COLORS, type CanvasPanel, type CanvasConnection } from '@/stores/canvas'
import { checkCreditsBeforeGenerate, showCostConsumedMessage } from '@/lib/canvas-credits'
import {
  type CanvasTemplate,
  saveAsTemplate,
  createWorkspaceFromTemplate,
} from '@/lib/canvas-templates'
// 画布生成：上游节点查找（用于配置节点 prompt 为空时检查上游文本）+ 生成归档上下文
import { getUpstreamNodes, buildCanvasContext, resumeLoadingCanvasNodes, resolvePromptMentions, executeSourceImageGeneration, executeSourceVideoGeneration, entityCardLinkId, type CanvasGenerationStore, type GenerationContext } from '@/lib/canvas-generation'
import { createBatchContent, fillCellFromNode, readBatchContent } from '@/lib/canvas-batch-table'
// 分镜派生：单镜头图生视频 + 整组重跑的批量积分确认
import { confirmGroupedCost, deriveVideoForShot, deriveTailFrameFromImageNode, derivePrevFrameFromImageNode, deriveChainVideosFromImageNode, getShotLineageInfo, readShots } from '@/lib/canvas-storyboard'
// 分组包络计算与智能建议分组（按连线连通分量）
import { calculateGroupBounds, suggestGroups } from '@/lib/canvas-groups'
// 一键整理布局（面板摆放位置优化，按类别分块平铺）
import { computeArrangedLayout } from '@/lib/canvas-layout'
// 画布三节点执行（spec M3：配音/字幕/成片合成）
import { generateCanvasTts, generateCanvasSubtitles, composeCanvasVideos, type CanvasSubtitleSegment } from '@/api/canvas'
import { parseSrt } from '@/lib/canvas-media'
import { planDropLayout } from '@/lib/canvas-drop'
import { emotionGenerationSize, compositeEmotionFaces, emotionResultToFile, type EmotionFaceBox, type EmotionGeneratePayload, type EmotionJobRecord } from '@/lib/canvas-emotion'
import { detectFaces } from '@/lib/canvas-face-detection'
import { getErrorMessage } from '@/lib/type-helpers'
import type { ImageGenerationRequest } from '@/types'

// ---------- 任务状态轮询响应（扩展字段） ----------
/** 图片任务状态轮询响应（覆盖层可能在 status 外返回 image_url/error/data） */
interface ImageTaskPollStatus {
  status: string
  task_id?: string
  progress?: number
  result_url?: string | null
  url?: string | null
  message?: string | null
  image_url?: string | null
  data?: { url?: string }[]
  error?: string
}

/** 视频任务状态轮询响应（扩展字段） */
interface VideoTaskPollStatus {
  status: string
  progress?: number
  message?: string | null
  video_url?: string | null
  error?: string | null
}

/** 从画布节点 content（Record<string, unknown>）中安全读取字符串字段 */
function contentString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

const { t } = useI18n()
const { confirm } = useConfirm()
const { copyText } = useCopyText()
const { downloadViaProxy, downloadWatermarkedImage } = useDownload()

const store = useCanvasStore()
const agentPanelOpen = ref(false)
const chatStore = useChatStore()
const taskQueue = useTaskQueueStore()
const route = useRoute()
const router = useRouter()

// ---------- 所属作品（轻容器）：画布页与作品详情互跳 ----------
const worksMap = ref<Record<number, string>>({})
const worksItems = ref<WorkItem[]>([])
const activeWorkId = computed(() => store.activeWorkspace?.work_id ?? null)
const activeWorkTitle = computed(() => (activeWorkId.value ? worksMap.value[activeWorkId.value] ?? null : null))

function loadWorksMap(): void {
  void listWorks()
    .then((r) => {
      worksItems.value = r.items
      const m: Record<number, string> = {}
      for (const w of r.items) m[w.id] = w.title
      worksMap.value = m
    })
    .catch(() => {})
}

const bindVisible = ref(false)
const bindWorkId = ref<number | null>(null)

function openBindDialog(): void {
  bindWorkId.value = activeWorkId.value
  bindVisible.value = true
}

async function submitBind(): Promise<void> {
  if (!store.activeWorkspaceId) return
  const res = await setWorkspaceWork(store.activeWorkspaceId, bindWorkId.value)
  const ws = store.workspaces.find((w) => w.id === res.id)
  if (ws) ws.work_id = res.work_id
  bindVisible.value = false
  loadWorksMap()
  ElMessage.success(t('canvas.work.bindDone'))
}

// ---------- 全局对话列表跳转进入：?workspace=…&session=<backendId> ----------
/** 定位工作区并打开对应画布会话；工作区本地不存在（跨设备）时仅打开 Agent 会话 */
async function handleSessionJumpQuery(): Promise<void> {
  const ws = route.query.workspace
  const session = route.query.session
  if (!ws && !session) return
  if (typeof ws === 'string' && ws && store.workspaces.some((w) => w.id === ws)) {
    store.switchWorkspace(ws)
  }
  if (typeof session === 'string' && session) {
    const backendId = Number(session)
    if (Number.isFinite(backendId) && backendId > 0) {
      agentPanelOpen.value = true
      await chatStore.init()
      if (chatStore.sessions.some((x) => x.id === backendId)) {
        await chatStore.switchSession(backendId)
      }
    }
  }
}

// ---------- 节点默认尺寸 ----------
const NODE_DEFAULT_SIZES = {
  text: { width: 340, height: 240 },
  image: { width: 340, height: 240 },
  video: { width: 420, height: 236 },
  audio: { width: 340, height: 120 },
  // 新增 3 种节点类型（spec 5.4.1）
  tts: { width: 340, height: 180 },
  subtitle: { width: 340, height: 180 },
  compose: { width: 360, height: 240 },
  // 脚本节点：紧凑卡片 + 全屏分镜向导入口
  script: { width: 340, height: 300 },
  // 批量创作表：N 行 × M 参考图列矩阵生成
  table: { width: 780, height: 420 },
}

// ---------- 节点类型名称（国际化） ----------
function getNodeName(type: string): string {
  // 新增 3 种节点类型兜底中文名（i18n 未覆盖时使用）
  const fallbackNames: Record<string, string> = {
    tts: '配音',
    subtitle: '字幕',
    compose: '成片合成',
    script: '脚本',
    table: '批量创作表',
  }
  const i18nKey = `canvas.nodeNames.${type}`
  const translated = t(i18nKey)
  // i18n 未命中时返回 key 本身，用兜底名替代
  return translated === i18nKey ? (fallbackNames[type] || type) : translated
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
  // 新画布继承当前画布的作品归属（作品为家：作品内新建即归该作品）
  store.createWorkspace(`${t('canvas.canvas')} ${store.workspaces.length + 1}`, activeWorkId.value)
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

// ==================== 分组状态 ====================

// 当前选中的分组 id（点击组框选中；Delete 仅解散组不删节点）
const selectedGroupId = ref<string | null>(null)

// 折叠分组成员集合（节点 v-show 隐藏 + 框选/全选排除）
const hiddenPanelIds = computed(() => {
  const ids = new Set<string>()
  for (const group of store.groups) {
    if (!group.collapsed) continue
    for (const pid of group.panel_ids) ids.add(pid)
  }
  return ids
})

// 换组颜色（按色板循环）
function handleGroupCycleColor(groupId: string) {
  const group = store.groups.find((g) => g.id === groupId)
  if (!group) return
  const idx = CANVAS_GROUP_COLORS.indexOf(group.color)
  const next = CANVAS_GROUP_COLORS[(idx + 1) % CANVAS_GROUP_COLORS.length]
  store.updateGroup(groupId, { color: next })
}

// 解散分组（保留节点）
async function handleGroupDissolve(groupId: string | null) {
  if (!groupId) return
  store.dissolveGroup(groupId)
  if (selectedGroupId.value === groupId) selectedGroupId.value = null
  ElMessage.success(t('canvas.group.groupDissolved'))
}

// 删除分组与组内节点
async function handleGroupDeleteWithNodes(groupId: string | null) {
  if (!groupId) return
  const group = store.groups.find((g) => g.id === groupId)
  if (!group) return
  await confirm(t('canvas.group.confirmDeleteWithNodes', { name: group.name }), t('common.confirm'), { confirmButtonText: t('common.delete') })
  store.pushSnapshot()
  for (const pid of [...group.panel_ids]) {
    store.deletePanel(pid)
  }
  if (selectedGroupId.value === groupId) selectedGroupId.value = null
  ElMessage.success(t('canvas.group.groupDeleted'))
}

// 引用整组：在组框右侧建下游节点，并把资源成员全部连过去（生成侧沿用现有上游收集协议）
function handleGroupReference(groupId: string, type: 'image' | 'video') {
  const group = store.groups.find((g) => g.id === groupId)
  if (!group) return
  const members = store.panels.filter((p) => group.panel_ids.includes(p.id))
  if (members.length === 0) return
  const bounds = calculateGroupBounds(group, store.panels)
  const size = NODE_DEFAULT_SIZES[type]
  store.pushSnapshot()
  const panelId = store.addPanel({
    type,
    name: `${group.name} · ${type === 'image' ? t('canvas.nodeNames.image') : t('canvas.nodeNames.video')}`,
    x: bounds ? bounds.left + bounds.width + 80 : 0,
    y: bounds ? bounds.top + bounds.height / 2 - size.height / 2 : 0,
    width: size.width,
    height: size.height,
    content: {},
  })
  // 资源成员（文本并入提示词、图片/视频/音频作参考输入）连到新节点；script 等不参与
  for (const m of members) {
    if (!['text', 'image', 'video', 'audio'].includes(m.type || 'text')) continue
    const exists = store.connections.some((c) => c.source_panel_id === m.id && c.target_panel_id === panelId)
    if (!exists) store.addConnection({ source_panel_id: m.id, target_panel_id: panelId, type: 'auto' })
  }
  store.selectPanel(panelId, { append: false })
  store.centerOnPanel(panelId)
}

// 整组重跑：组内 image/video 节点按成员间连线拓扑序逐个重生成（下游等上游落定）
async function handleGroupRerun(groupId: string) {
  const group = store.groups.find((g) => g.id === groupId)
  if (!group) return
  const runnable = store.panels.filter(
    (p) => group.panel_ids.includes(p.id)
      && (p.type === 'image' || p.type === 'video')
      && contentString(p.content?.status) !== 'loading',
  )
  if (runnable.length === 0) {
    ElMessage.warning(t('canvas.group.rerunEmpty'))
    return
  }
  // 批量积分预估确认（一次）
  const imageCount = runnable.filter((p) => p.type === 'image').length
  const videoCount = runnable.length - imageCount
  const ok = await confirmGroupedCost([
    ...(imageCount > 0 ? [{ type: 'image' as const, count: imageCount }] : []),
    ...(videoCount > 0 ? [{ type: 'video' as const, count: videoCount }] : []),
  ])
  if (!ok) return
  ElMessage.info(t('canvas.messages.regenerate'))
  for (const panel of topoSortByConnections(runnable)) {
    // 重跑过程中节点可能被删（如重跑失败自动清理），跳过已不存在的
    if (!store.panels.some((p) => p.id === panel.id)) continue
    await retryGeneration(panel)
  }
  const failed = runnable
    .filter((p) => contentString(store.panels.find((x) => x.id === p.id)?.content?.status) === 'error')
    .map((p) => p.name || p.id)
  if (failed.length > 0) {
    ElMessage.error(t('canvas.group.rerunFailed', { names: failed.join('、') }))
  } else {
    ElMessage.success(t('canvas.group.rerunDone'))
  }
}

/** 成员间按连线拓扑排序（Kahn；仅考虑成员之间的边，有环时剩余节点按原顺序兜底） */
function topoSortByConnections(members: CanvasPanel[]): CanvasPanel[] {
  const idSet = new Set(members.map((p) => p.id))
  const inDegree = new Map(members.map((p) => [p.id, 0]))
  for (const conn of store.connections) {
    if (idSet.has(conn.source_panel_id) && idSet.has(conn.target_panel_id)) {
      inDegree.set(conn.target_panel_id, (inDegree.get(conn.target_panel_id) || 0) + 1)
    }
  }
  const queue = members.filter((p) => (inDegree.get(p.id) || 0) === 0)
  const ordered: CanvasPanel[] = []
  while (queue.length > 0) {
    const panel = queue.shift()!
    ordered.push(panel)
    for (const conn of store.connections) {
      if (conn.source_panel_id !== panel.id || !idSet.has(conn.target_panel_id)) continue
      const degree = (inDegree.get(conn.target_panel_id) || 0) - 1
      inDegree.set(conn.target_panel_id, degree)
      if (degree === 0) {
        const next = members.find((p) => p.id === conn.target_panel_id)
        if (next) queue.push(next)
      }
    }
  }
  for (const p of members) {
    if (!ordered.includes(p)) ordered.push(p)
  }
  return ordered
}

// ==================== 分组拖动（整体移动成员） ====================

const groupDragState = reactive({
  groupId: null as string | null,
  startX: 0,
  startY: 0,
  initialPositions: {} as Record<string, { x: number; y: number }>,
  hasMoved: false,
})

function handleGroupDragStart(groupId: string, { event }: { event: PointerEvent }) {
  selectedGroupId.value = groupId
  groupDragState.groupId = groupId
  groupDragState.startX = event.clientX
  groupDragState.startY = event.clientY
  groupDragState.hasMoved = false
  groupDragState.initialPositions = {}
  window.addEventListener('pointermove', handleGroupDragMove)
  window.addEventListener('pointerup', handleGroupDragUp)
}

function handleGroupDragMove(event: PointerEvent) {
  if (!groupDragState.groupId) return
  if (!groupDragState.hasMoved) {
    // 首次实际移动才选中成员并压快照（单纯点击组框只选中组）
    const group = store.groups.find((g) => g.id === groupDragState.groupId)
    if (!group) return
    store.selectPanel(null)
    store.selectedPanelIds = [...group.panel_ids]
    for (const pid of group.panel_ids) {
      const p = store.panels.find((pp) => pp.id === pid)
      if (p) groupDragState.initialPositions[pid] = { x: p.x, y: p.y }
    }
    store.pushSnapshot()
    groupDragState.hasMoved = true
  }
  const zoom = store.viewport.zoom
  const dx = (event.clientX - groupDragState.startX) / zoom
  const dy = (event.clientY - groupDragState.startY) / zoom
  for (const [pid, init] of Object.entries(groupDragState.initialPositions)) {
    store._updatePanelDirect(pid, { x: init.x + dx, y: init.y + dy })
  }
}

function handleGroupDragUp() {
  if (groupDragState.groupId && groupDragState.hasMoved) {
    for (const pid of Object.keys(groupDragState.initialPositions)) {
      const p = store.panels.find((pp) => pp.id === pid)
      if (p) store.updatePanel(pid, { x: p.x, y: p.y })
    }
  }
  groupDragState.groupId = null
  groupDragState.hasMoved = false
  groupDragState.initialPositions = {}
  window.removeEventListener('pointermove', handleGroupDragMove)
  window.removeEventListener('pointerup', handleGroupDragUp)
}

// 分组右键菜单
function handleGroupContextMenu(groupId: string, event: PointerEvent) {
  event.preventDefault()
  event.stopPropagation()
  selectedGroupId.value = groupId
  contextMenu.open = true
  contextMenu.x = event.clientX - store.canvasRect.left
  contextMenu.y = event.clientY - store.canvasRect.top
  contextMenu.targetType = 'group'
  contextMenu.targetId = groupId
}

// ==================== 背景点击处理 ====================

function handleBackgroundClick() {
  // InfiniteCanvas 在无 props 时已自动清空选中
  showAppearancePanel.value = false
  selectedGroupId.value = null
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
  selectedGroupId.value = null
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
  // 锁定分组成员不可单独拖动（组整体仍可拖动）
  const memberGroup = store.getGroupOfPanel(id)
  if (memberGroup?.locked) {
    ElMessage.warning(t('canvas.group.lockedDragBlocked'))
    return
  }
  // 如果拖拽的节点不在选中列表中，只选中它
  if (!store.selectedPanelIds.includes(id)) {
    store.selectPanel(id, { append: false })
  }
  dragState.active = true
  dragState.draggedId = id
  dragState.hasMoved = false
  dragState.initialPositions = {}
  for (const pid of store.selectedPanelIds) {
    // 锁定分组成员不随多选拖动移动
    if (store.getGroupOfPanel(pid)?.locked) continue
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
  for (const [pid, init] of Object.entries(dragState.initialPositions)) {
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
  // 框选多选拖线：预览线从每个待批量接入的选中节点拉出（config 作为发送方不参与批量）
  let extraSourceIds: string[] = []
  if (store.selectedPanelIds.length > 1) {
    extraSourceIds = store.selectedPanelIds.filter((id) => {
      if (id === panelId) return false
      const p = store.panels.find((x) => x.id === id)
      return !!p
    })
  }
  store.startConnecting(panelId, anchorType, extraSourceIds)
  window.addEventListener('pointermove', handleConnectingMove)
  window.addEventListener('pointerup', handleConnectingUp)
}

// 连线拖拽中：更新临时连线终点
function handleConnectingMove(event: PointerEvent) {
  if (!store.connecting) return
  const world = store.screenToWorld(event.clientX, event.clientY)
  store.updateConnecting(world.x, world.y)
}

// 连线结束：检测是否释放在节点上（支持批量连接：选中多个节点时一次性全部连接到目标接收节点）
function handleConnectingUp(event: PointerEvent) {
  window.removeEventListener('pointermove', handleConnectingMove)
  window.removeEventListener('pointerup', handleConnectingUp)
  if (!store.connecting) return
  const connectingState = store.connecting
  // 批量创作表列句柄拖线（ref-col:N）：落点是图片节点时填充该列空槽
  const colMatch = connectingState.sourceAnchorType.match(/^ref-col:(\d+)$/)
  const el = document.elementFromPoint(event.clientX, event.clientY)
  const nodeEl = el?.closest?.('[data-node-id]')
  if (nodeEl) {
    const targetId = nodeEl.getAttribute('data-node-id')!
    if (colMatch) {
      handleBatchRefDrop(connectingState.sourcePanelId, targetId, Number(colMatch[1]))
      return
    }
    const sourceId = connectingState.sourcePanelId
    const sourceAnchor = connectingState.sourceAnchorType

    // 确定单个连接的 source 和 target（数据流方向：资源节点 → 配置/接收节点）
    let realTarget: string // 实际的接收节点（target）
    if (sourceAnchor === 'source') {
      // 从源节点右侧锚点拖出：目标就是释放在的节点
      realTarget = targetId
    } else {
      // 从目标节点左侧锚点拖出：源节点就是释放在的节点（反向连线）
      realTarget = sourceId
    }

    // 判断目标节点是否为"接收多输入"类型（媒体节点多参考输入、compose 成片合成）
    const targetPanel = store.panels.find(p => p.id === realTarget)
    const isReceiverNode = ['image', 'video', 'compose'].includes(targetPanel?.type || '')
    const hasMultipleSelection = store.selectedPanelIds.length > 1
    const isBatchConnect = isReceiverNode && hasMultipleSelection

    if (isBatchConnect) {
      store.pushSnapshot()
      const connectedIds = new Set<string>()
      let batchAdded = 0

      // 确定本次连线的起始节点（拖拽发起的那个节点）
      const dragSourceId = sourceAnchor === 'source' ? sourceId : targetId

      // 批量连接：所有选中的非接收节点 → 目标接收节点
      for (const selectedId of store.selectedPanelIds) {
        const selectedPanel = store.panels.find(p => p.id === selectedId)
        // 跳过接收节点本身，跳过非资源节点
        if (!selectedPanel) continue
        if (selectedId === realTarget) continue
        // 防止重复连接
        const exists = store.connections.some(
          c => c.source_panel_id === selectedId && c.target_panel_id === realTarget
        )
        if (exists) continue
        const conn = store.addConnection({
          source_panel_id: selectedId,
          target_panel_id: realTarget,
          type: 'flow',
        })
        // addConnection 内部做类型校验，不合法的（如 text → compose）返回 null 跳过
        if (conn) {
          connectedIds.add(selectedId)
          batchAdded++
        }
      }

      // 如果拖拽起始节点本身不在选中列表中，也单独连接
      if (!connectedIds.has(dragSourceId) && dragSourceId !== realTarget) {
        {
          const exists = store.connections.some(
            c => c.source_panel_id === dragSourceId && c.target_panel_id === realTarget
          )
          if (!exists) {
            store.addConnection({
              source_panel_id: dragSourceId,
              target_panel_id: realTarget,
              type: 'flow',
            })
          }
        }
      }
      if (batchAdded > 0) ElMessage.success(t('canvas.messages.batchConnectDone'))
      else ElMessage.warning(t('canvas.messages.batchConnectEmpty'))
      store.cancelConnecting()
    } else {
      // 普通单连接
      store.endConnecting(targetId, 'target')
      // 连线类型校验失败提示（spec 5.4.2）
      if (store.lastConnectionError) {
        ElMessage.warning(store.lastConnectionError)
        store.lastConnectionError = null
      }
    }
  } else {
    // 拖线松手在空白：落点弹快速创建菜单（临时虚线保留，选择后建节点并自动连线，取消才清线）
    if (colMatch) {
      // 列句柄拖线落空白：不做快速创建（填槽语义只对已有图片节点成立）
      store.cancelConnecting()
      return
    }
    const sourcePanel = store.panels.find((p) => p.id === connectingState.sourcePanelId)
    openQuickMenu('connect', store.screenToWorld(event.clientX, event.clientY), {
      sourceId: connectingState.sourcePanelId,
      sourceType: sourcePanel?.type || 'text',
      anchorType: connectingState.sourceAnchorType,
      extraSourceIds: [...(connectingState.extraSourceIds ?? [])],
    })
  }
}

/**
 * 批量创作表列句柄落点：图片节点 → 填充表格该列首个空槽 + 建血缘连线
 */
function handleBatchRefDrop(tableId: string, targetId: string, colIndex: number) {
  store.cancelConnecting()
  const target = store.panels.find((p) => p.id === targetId)
  const url = String(target?.content?.content || '')
  if (target?.type !== 'image' || !url) {
    ElMessage.warning(t('canvas.batchTable.connectNeedsImage'))
    return
  }
  const table = store.panels.find((p) => p.id === tableId)
  if (!table) return
  const rows = readBatchContent(table.content).rows
  const filled = fillCellFromNode(rows, colIndex, {
    assetId: typeof target.content?.assetId === 'string' ? target.content.assetId : '',
    url,
  })
  if (!filled) {
    ElMessage.warning(t('canvas.batchTable.columnFull'))
    return
  }
  store.addConnection({ source_panel_id: targetId, target_panel_id: tableId, type: 'ref' })
  store.updatePanel(tableId, { content: { rows: filled.rows } })
  ElMessage.success(t('canvas.batchTable.cellFilled', { n: colIndex + 1 }))
}

// ==================== 节点交互：右键菜单 ====================

const contextMenu = reactive({
  open: false,
  x: 0,
  y: 0,
  targetType: 'node' as 'node' | 'connection' | 'group' | 'canvas',
  targetId: null as string | null,
})

// 空白右键的位置（世界坐标，「新建节点…」在此打开快速创建菜单）
const paneContextMenuWorld = ref({ x: 0, y: 0 })

// ==================== 快速创建菜单（双击空白 / 拖线落点） ====================

const quickMenu = reactive({
  open: false,
  x: 0,
  y: 0,
  worldX: 0,
  worldY: 0,
  mode: 'create' as 'create' | 'connect',
  // connect 模式：拖线源节点 id / 类型 / 锚点方向（'source' 右锚出 | 'target' 左锚出）
  sourceId: '',
  sourceType: '',
  anchorType: '',
  extraSourceIds: [] as string[],
})

/** 打开快速创建菜单：锚定世界坐标点（屏幕坐标按现有菜单惯例换算） */
function openQuickMenu(
  mode: 'create' | 'connect',
  world: { x: number; y: number },
  connect?: { sourceId: string; sourceType: string; anchorType: string; extraSourceIds: string[] },
) {
  const screen = store.worldToScreen(world.x, world.y)
  quickMenu.open = true
  quickMenu.x = screen.x - store.canvasRect.left
  quickMenu.y = screen.y - store.canvasRect.top
  quickMenu.worldX = world.x
  quickMenu.worldY = world.y
  quickMenu.mode = mode
  quickMenu.sourceId = connect?.sourceId ?? ''
  quickMenu.sourceType = connect?.sourceType ?? ''
  quickMenu.anchorType = connect?.anchorType ?? ''
  quickMenu.extraSourceIds = connect?.extraSourceIds ?? []
}

/** 关闭菜单；connect 模式同时取消临时连线 */
function closeQuickMenu() {
  quickMenu.open = false
  store.cancelConnecting()
}

// 空白双击：打开快速创建菜单
function handlePaneDblClick(payload: { worldX: number; worldY: number }) {
  openQuickMenu('create', { x: payload.worldX, y: payload.worldY })
}

// 空白右键：画布级右键菜单（新建节点 / 全选 / 缩放适配）
function handlePaneContextMenu(payload: { clientX: number; clientY: number; worldX: number; worldY: number }) {
  contextMenu.open = true
  contextMenu.x = payload.clientX - store.canvasRect.left
  contextMenu.y = payload.clientY - store.canvasRect.top
  contextMenu.targetType = 'canvas'
  contextMenu.targetId = null
  paneContextMenuWorld.value = { x: payload.worldX, y: payload.worldY }
}

// 右键菜单「新建节点…」：在右键点打开快速创建菜单
function handleContextCanvasCreate() {
  contextMenu.open = false
  openQuickMenu('create', { x: paneContextMenuWorld.value.x, y: paneContextMenuWorld.value.y })
}

// 全选可见节点（排除折叠分组隐藏成员；Ctrl+A 与右键菜单共用）
function selectAllVisible() {
  store.selectedPanelIds = store.panels
    .filter((p) => !hiddenPanelIds.value.has(p.id))
    .map((p) => p.id)
  store.selectedPanelId = store.selectedPanelIds[0] ?? null
}

// 快速创建菜单选择：create 原地建节点；connect 建节点并自动连线
function handleQuickMenuSelect(item: QuickMenuItem) {
  const world = { x: quickMenu.worldX, y: quickMenu.worldY }
  if (item.kind === 'upload') {
    closeQuickMenu()
    triggerFileUpload(null, 'image/*', world)
    return
  }
  if (item.kind === 'action') {
    closeQuickMenu()
    // 实体库：打开实体选择器（落挂链实体卡，跨集复用入口）
    if (item.id === 'action:entity-pick') {
      if (!store.activeWorkspace?.work_id) {
        ElMessage.warning(t('entityLib.noWork'))
        return
      }
      entityPickerVisible.value = true
      return
    }
    // 快捷生成：在拖线源节点上打开快捷生成弹窗（结果节点自动连回源节点）
    const sourcePanel = store.panels.find((p) => p.id === quickMenu.sourceId)
    if (sourcePanel) handleQuickGenerate({ panel: sourcePanel, mode: String(item.content?.mode || 'image2image') })
    return
  }
  const newId = createNodeAt(item.type || 'text', world.x, world.y, item.content)
  if (quickMenu.mode === 'connect') connectCreatedNode(newId)
  closeQuickMenu()
}

// 拖线落点新建节点的自动连线：右锚出=新节点为接收方（多选拖出批量接入），左锚入=新节点为上游
function connectCreatedNode(newId: string) {
  const anchor = quickMenu.anchorType
  const sourceId = quickMenu.sourceId
  if (anchor === 'source') {
    store.addConnection({ source_panel_id: sourceId, target_panel_id: newId, type: 'flow' })
    for (const extraId of quickMenu.extraSourceIds) {
      const exists = store.connections.some(
        (c) => c.source_panel_id === extraId && c.target_panel_id === newId,
      )
      if (!exists) store.addConnection({ source_panel_id: extraId, target_panel_id: newId, type: 'flow' })
    }
  } else {
    store.addConnection({ source_panel_id: newId, target_panel_id: sourceId, type: 'flow' })
  }
  if (store.lastConnectionError) {
    ElMessage.warning(store.lastConnectionError)
    store.lastConnectionError = null
  }
}

// 目标节点是否已在分组中（控制"移出分组"菜单项）
const canRemoveFromGroup = computed(() =>
  !!contextMenu.targetId && contextMenu.targetType === 'node' && !!store.getGroupOfPanel(contextMenu.targetId),
)

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

// 右键菜单：成组（框选/多选时）
function handleContextGroupCreate() {
  if (store.selectedPanelIds.length < 2) return
  const { id, skipped } = store.createGroup([...store.selectedPanelIds], {
    name: t('canvas.group.defaultName', { n: store.groups.length + 1 }),
  })
  if (id) {
    selectedGroupId.value = id
    ElMessage.success(t('canvas.group.groupCreated'))
  }
  if (skipped.length > 0) {
    ElMessage.warning(t('canvas.group.groupCreatedSkipped', { n: skipped.length }))
  }
}

// 右键菜单：把目标节点移出所属分组
function handleContextRemoveFromGroup() {
  if (!contextMenu.targetId) return
  store.removePanelFromGroup(contextMenu.targetId)
  ElMessage.success(t('canvas.group.removedFromGroup'))
}

// ==================== 智能建议分组 ====================

// 分类分组弹窗：成组模式可多选（生成链条 / 资产类别）
const smartGroupDialog = reactive({
  visible: false,
  byChain: true,
  byCategory: true,
})

// 点击工具栏按钮：打开模式选择弹窗
function handleSmartGroup() {
  smartGroupDialog.visible = true
}

// 弹窗内实时预览将创建的分组数与覆盖节点数
const smartGroupPreview = computed(() => {
  const suggestions = suggestGroups(store.panels, store.groups, {
    byChain: smartGroupDialog.byChain,
    byCategory: smartGroupDialog.byCategory,
  })
  return {
    count: suggestions.length,
    nodes: suggestions.reduce((sum, s) => sum + s.panelIds.length, 0),
  }
})

// 确认创建：链条组用“脚本名 · 生成链”命名，类别组用资产类别名命名
async function handleSmartGroupConfirm() {
  smartGroupDialog.visible = false
  const suggestions = suggestGroups(store.panels, store.groups, {
    byChain: smartGroupDialog.byChain,
    byCategory: smartGroupDialog.byCategory,
  })
  if (suggestions.length === 0) {
    ElMessage.info(t('canvas.smartGroupNone'))
    return
  }
  store.pushSnapshot()
  let created = 0
  for (const suggestion of suggestions) {
    const name = suggestion.chainScriptName
      ? `${suggestion.chainScriptName} · ${t('canvas.chainGroupSuffix')}`
      : t(`canvas.assetCategory.${suggestion.category}`)
    const { id } = store.createGroup(suggestion.panelIds, { name }, { snapshot: false })
    if (id) created++
  }
  selectedGroupId.value = null
  ElMessage.success(t('canvas.smartGroupDone', { n: created }))
}

// ==================== 一键整理布局 ====================

// 按产出管线分带行架堆叠（脚本→人物→物品→场景→分镜→…→合成）：行内排满换行、
// 行序按上游连线质心校正让产出相邻；分镜图与直连视频配对（图左视频右）；锁定节点不动
function handleArrangeLayout() {
  const positions = computeArrangedLayout(store.panels, store.groups, store.connections)
  const moved = store.applyPanelPositions(positions)
  if (moved === 0) {
    ElMessage.info(t('canvas.arrangeNone'))
    return
  }
  ElMessage.success(t('canvas.arrangeDone', { n: moved }))
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

// ==================== 节点悬浮 AI 对话框 ====================

/** 对话框目标节点：单选且类型支持（script/text/image/video）时显示 */
const composerPanelId = computed(() => {
  if (store.selectedPanelIds.length !== 1) return null
  const p = store.panels.find((x) => x.id === store.selectedPanelIds[0])
  if (!p || !['script', 'text', 'image', 'video'].includes(p.type || '')) return null
  return p.id
})

/** 对话框定位：节点正下方，跟随视口变换（screen = world * zoom + viewport.x/y） */
const composerStyle = computed(() => {
  const p = store.panels.find((x) => x.id === composerPanelId.value)
  if (!p) return { display: 'none' }
  const { x: vx, y: vy, zoom } = store.viewport
  // 宽输入条：窄节点也保持宽敞下限，超宽节点随节点宽度放大到上限
  const width = Math.max(560, Math.min(800, p.width * zoom, window.innerWidth - 32))
  // 画布容器 overflow hidden，贴右缘时收拢左边界避免裁剪
  const left = Math.max(12, Math.min(p.x * zoom + vx, window.innerWidth - width - 16))
  return {
    left: `${left}px`,
    top: `${(p.y + p.height) * zoom + vy + 12}px`,
    width: `${width}px`,
  }
})

/** 对话框重生成（image/video 节点）：输入框即节点提示词（已写回 content），走就地重生成链路 */
function generateComposerRegenerate() {
  const p = store.panels.find((x) => x.id === composerPanelId.value)
  if (p) void retryGeneration(p)
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
  sourcePanel: null as typeof store.panels[number] | null,
  mode: 'text2image' as 'text2image' | 'text2video' | 'image2image' | 'image2video',
})

// 打开快捷生成弹窗（由文本/图片节点的生图/生视频按钮触发）
function handleQuickGenerate({ panel, mode }: { panel: typeof store.panels[number]; mode: string }) {
  // 实体卡门槛：未挂链实体卡先入库才能生成（自由画布无实体库不拦）
  if (!ensureEntityLinked(panel)) return
  // 校验源内容非空
  if (panel.type === 'text') {
    const text = contentString(panel.content?.content).trim()
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
  quickGenerateState.mode = mode as 'text2image' | 'text2video' | 'image2image' | 'image2video';
  quickGenerateState.visible = true
}

// 弹窗确认生成：拼装提示词与参考图（@ 引用解析 + 首尾帧），走源节点批量生成链路
async function handleQuickGenerateConfirm(payload: any) {
  const { mode, prompt: auxPrompt, model, size, aspect_ratio, seconds, count, use_keyframes, tail_frame_id } = payload
  const sourcePanel = quickGenerateState.sourcePanel
  if (!sourcePanel) return

  // @ 引用解析：辅助提示词引用源节点上游资源（文本替换为【文本N】块、图片并入参考图）
  const mentionHit = resolvePromptMentions(auxPrompt, store.getInputNodesWithIndex(sourcePanel.id))
  const resolvedAux = mentionHit ? mentionHit.prompt : auxPrompt

  // 拼装最终 prompt 和参考图
  let finalPrompt = ''
  const referenceImages: string[] = []
  if (mode.startsWith('text')) {
    // 文本源：主提示词 = 文本内容 + 辅助提示词（可选）
    const textContent = contentString(sourcePanel.content?.content).trim()
    finalPrompt = resolvedAux.trim() ? `${textContent}\n\n${resolvedAux.trim()}` : textContent
  } else {
    // 图片源：参考图 = 图片内容，prompt = 辅助提示词
    referenceImages.push(contentString(sourcePanel.content?.content))
    finalPrompt = resolvedAux.trim()
  }
  // @ 引用到的图片并入参考图（按 URL 去重）
  for (const u of mentionHit?.referenceImages || []) {
    if (u && !referenceImages.includes(u)) referenceImages.push(u)
  }
  // 首尾帧模式：尾帧图排参考图末位（首帧在前）
  if (mode.includes('video') && use_keyframes && tail_frame_id) {
    const tail = store.panels.find(p => p.id === tail_frame_id)
    const tailUrl = tail ? contentString(tail.content?.content) : ''
    if (tailUrl && !referenceImages.includes(tailUrl)) referenceImages.push(tailUrl)
  }

  const ctx: GenerationContext = {
    prompt: finalPrompt,
    referenceImages,
    referenceVideos: [],
    referenceTexts: [],
    inputSummary: { textCount: 0, imageCount: referenceImages.length, videoCount: 0, total: referenceImages.length },
  }

  // 积分预检：多张走批量确认（一次确认总消耗），单张静默预检
  const isVideo = mode.includes('video')
  const n = isVideo ? 1 : Math.max(1, Number(count) || 1)
  const estimateParams = isVideo
    ? { type: 'video' as const, mode: use_keyframes ? 'keyframes' : referenceImages.length > 0 ? 'image2video' : 'text2video', seconds: seconds || 5 }
    : { type: 'image' as const, mode: referenceImages.length > 0 ? 'image2image' : 'text2image', size: size || '1024x1024' }
  const canGenerate = n > 1
    ? await confirmGroupedCost([{ ...estimateParams, count: n }])
    : await checkCreditsBeforeGenerate(estimateParams)
  if (!canGenerate) return

  const onProgress = (stage: string, data: any) => {
    if (stage === 'done') {
      showCostConsumedMessage(estimateParams, isVideo ? t('canvas.messages.videoGenerationDone') : t('canvas.messages.imageGenerationDone'))
      // 选中新节点并定位视口
      const ids: string[] = data?.resultNodeIds || []
      if (ids.length > 0) {
        store.selectPanel(ids[0], { append: false })
        store.centerOnPanel(ids[0])
      }
    } else if (stage === 'error') {
      ElMessage.error(`${isVideo ? t('canvas.messages.videoGenerationFailed') : t('canvas.messages.imageGenerationFailed')}: ${data?.error || ''}`)
    }
  }

  if (isVideo) {
    await executeSourceVideoGeneration(sourcePanel, ctx, store, {
      model,
      aspectRatio: aspect_ratio,
      seconds,
      useKeyframes: !!use_keyframes,
      onProgress,
    })
  } else {
    await executeSourceImageGeneration(sourcePanel, ctx, store, { model, size, count: n, onProgress })
  }
}

// 重试生成：媒体节点就地重生成，其余用节点自身 prompt 重新生成
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
    const resp = await createImageTask({ prompt, model: useModelsStore().defaultImageModel, size, response_format: 'url', context: buildCanvasContext(sourcePanel, store) })
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
      const status: ImageTaskPollStatus = await getImageTaskStatus(taskId)
      const isSuccess = ['completed', 'succeeded', 'success', 'done'].includes(status.status)
      const isFailed = ['failed', 'error'].includes(status.status)

      if (isSuccess) {
        const imageUrl = status.result_url || status.image_url || status.url || status.data?.[0]?.url
        store.updatePanel(newPanelId!, { content: { content: imageUrl, status: 'success' } })
        store.pushSnapshot()
        taskQueue.updateCanvasTask(taskId, { status: 'success', resultUrl: imageUrl, progress: 100 })
        // 成功提示附带消耗积分数量
        showCostConsumedMessage({ type: 'image', mode: 'text2image', size }, t('canvas.messages.imageGenerationDone'))
        // 【用户偏好】自动下载 + 完成通知
        const prefsStore = usePreferencesStore()
        if (imageUrl) {
          prefsStore.autoDownload(imageUrl, 'image', { modelId: useModelsStore().defaultImageModel })
        }
        prefsStore.notifyComplete('image', { prompt, modelId: useModelsStore().defaultImageModel })
        return
      }
      if (isFailed) {
        const errMsg = status.message || status.error || t('canvas.messages.generateFailed')
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
    store.updatePanel(newPanelId!, { content: { status: 'error', errorDetails: getErrorMessage(err) } })
    ElMessage.error(`${t('canvas.messages.generateFailed')}: ${getErrorMessage(err)}`)
  }
}

// ==================== 画布三节点执行（spec M3：tts / subtitle / compose） ====================

/** 收集节点的上游节点：按"行带 → 行内 x"排序（从上到下、行内从左到右），网格摆放也符合阅读顺序 */
function getUpstreamRunNodes(panelId: string, types: string[]) {
  const nodes = store.connections
    .filter((c) => c.target_panel_id === panelId)
    .map((c) => store.panels.find((p) => p.id === c.source_panel_id))
    .filter((p): p is CanvasPanel => !!p && types.includes(p.type || ''))
  // 按 y 聚成行带（容差 = 节点高度一半，避免网格/轻微错位被拆成多行），带内按 x 排序
  const sorted = [...nodes].sort((a, b) => a.y - b.y || a.x - b.x)
  const bands: CanvasPanel[][] = []
  for (const p of sorted) {
    const band = bands.find((arr) => Math.abs(p.y - arr[0].y) <= Math.max(p.height, arr[0].height) / 2)
    if (band) band.push(p)
    else bands.push([p])
  }
  return bands.flatMap((band) => band.sort((a, b) => a.x - b.x))
}

/** 收集配音/字幕来源文本：显式文本节点 > 上游分镜台词（结构化台词源，按 no 拼接）> 节点自身 text */
function collectRunText(panel: CanvasPanel): string {
  for (const p of getUpstreamRunNodes(panel.id, ['text'])) {
    const text = contentString(p.content?.content).trim()
    if (text) return text
  }
  const dialogue = collectScriptDialogue(panel)
  if (dialogue) return dialogue
  return contentString(panel.content?.text).trim()
}

/** 上游 script 节点的分镜台词（结构化台词源：whisper 字幕与 TTS 共用） */
function collectScriptDialogue(panel: CanvasPanel): string {
  for (const p of getUpstreamRunNodes(panel.id, ['script'])) {
    const lines = readShots(p)
      .sort((a, b) => a.no - b.no)
      .map((s) => s.dialogue.trim())
      .filter(Boolean)
    if (lines.length) return lines.join('\n')
  }
  return ''
}

/** 字幕节点 whisper 模式音频源：上游 tts 节点的结果音频（有则真实时间戳转写，无则 LLM 拆分） */
function collectSubtitleAudioUrl(panel: CanvasPanel): string | undefined {
  for (const tts of getUpstreamRunNodes(panel.id, ['tts'])) {
    const resultId = contentString(tts.content?.result_panel_id)
    const result = resultId ? store.panels.find((p) => p.id === resultId) : null
    const url = result?.content?.content
    if (result?.type === 'audio' && url) return String(url)
  }
  return undefined
}

/** 确保执行结果节点存在：已有则复用并置 loading（重试），否则新建并连线 */
function ensureRunResultNode(sourcePanel: CanvasPanel, type: 'audio' | 'text' | 'video', width: number, height: number): string {
  const existing = contentString(sourcePanel.content?.result_panel_id)
  if (existing && store.panels.some((p) => p.id === existing)) {
    store.updatePanel(existing, { content: { content: '', status: 'loading', errorDetails: null } })
    return existing
  }
  const id = store.addPanel({
    type,
    x: sourcePanel.x + sourcePanel.width + 60,
    y: sourcePanel.y,
    width,
    height,
    content: { content: '', status: 'loading' },
  })
  store.addConnection({ source_panel_id: sourcePanel.id, target_panel_id: id })
  store.updatePanel(sourcePanel.id, { content: { result_panel_id: id } })
  store.pushSnapshot()
  return id
}

/** tts 节点执行：上游文本 → 配音音频节点 */
async function runTtsNode(panel: CanvasPanel) {
  const text = collectRunText(panel)
  if (!text) {
    ElMessage.warning(t('canvas.messages.textNodeEmpty'))
    return
  }
  const resultId = ensureRunResultNode(panel, 'audio', 340, 120)
  try {
    const res = await generateCanvasTts({
      text,
      voice: contentString(panel.content?.voice) || 'default',
      speed: Number(panel.content?.speed) || 1.0,
    })
    store.updatePanel(resultId, { content: { content: res.audio_url, status: 'success', duration_ms: res.duration_ms ?? null } })
    store.pushSnapshot()
    ElMessage.success(t('canvas.messages.ttsDone'))
  } catch (err) {
    store.updatePanel(resultId, { content: { status: 'error', errorDetails: getErrorMessage(err) } })
    ElMessage.error(`${t('canvas.messages.generateFailed')}: ${getErrorMessage(err)}`)
  }
}

/** subtitle 节点执行：上游文案 → SRT 文本节点 */
async function runSubtitleNode(panel: CanvasPanel) {
  const text = collectRunText(panel)
  if (!text) {
    ElMessage.warning(t('canvas.messages.textNodeEmpty'))
    return
  }
  const resultId = ensureRunResultNode(panel, 'text', 340, 240)
  try {
    const res = await generateCanvasSubtitles({
      text,
      max_chars: Number(panel.content?.max_chars) || 20,
      prompt: contentString(panel.content?.prompt) || undefined,
      // 上游有 TTS 产物时走 whisper 转写（真实时间戳），服务端失败自动回退 LLM 拆分
      audio_url: collectSubtitleAudioUrl(panel),
    })
    store.updatePanel(resultId, { content: { content: res.srt, status: 'success' } })
    store.pushSnapshot()
    ElMessage.success(t('canvas.messages.subtitleDone'))
  } catch (err) {
    store.updatePanel(resultId, { content: { status: 'error', errorDetails: getErrorMessage(err) } })
    ElMessage.error(`${t('canvas.messages.generateFailed')}: ${getErrorMessage(err)}`)
  }
}

/** compose 节点收集上游配音 URL 列表：tts 节点 → 其结果音频节点（按上游顺序，多段） */
function collectComposeAudioUrls(panel: CanvasPanel): string[] {
  const urls: string[] = []
  for (const tts of getUpstreamRunNodes(panel.id, ['tts'])) {
    const resultId = contentString(tts.content?.result_panel_id)
    const result = resultId ? store.panels.find((p) => p.id === resultId) : null
    const url = result?.content?.content
    if (result?.type === 'audio' && url) urls.push(String(url))
  }
  return urls
}

/** compose 节点收集上游字幕：subtitle 节点 → 其 SRT 文本节点 */
function collectComposeSubtitles(panel: CanvasPanel): CanvasSubtitleSegment[] | null {
  for (const sub of getUpstreamRunNodes(panel.id, ['subtitle'])) {
    const resultId = contentString(sub.content?.result_panel_id)
    const result = resultId ? store.panels.find((p) => p.id === resultId) : null
    if (result?.type === 'text' && result.content?.content) {
      const segments = parseSrt(String(result.content.content))
      if (segments.length) return segments
    }
  }
  return null
}

/** compose 节点执行：多段视频（按摆放顺序）+ 可选配音/字幕 → 成片视频节点 */
async function runComposeNode(panel: CanvasPanel) {
  // 成片 URL 生成回写在 content、引入素材落库在 url（与 agent 工具层 videoUrlOf 同口径）
  const videos = getUpstreamRunNodes(panel.id, ['video']).filter((p) => p.content?.content || p.content?.url)
  if (!videos.length) {
    ElMessage.warning(t('canvas.messages.composeNoVideo'))
    return
  }
  const withSubtitle = panel.content?.with_subtitle !== false
  store.updatePanel(panel.id, { content: { status: 'loading', errorDetails: null } })
  try {
    const res = await composeCanvasVideos({
      video_urls: videos.map((p) => String(p.content?.content || p.content?.url)),
      audios: collectComposeAudioUrls(panel),
      subtitles: withSubtitle ? collectComposeSubtitles(panel) : null,
      with_subtitle: withSubtitle,
      bgm_id: contentString(panel.content?.bgm_id) || undefined,
      aspect_ratio: contentString(panel.content?.aspect_ratio) || undefined,
      transition: contentString(panel.content?.transition) || undefined,
    })
    const resultId = ensureRunResultNode(panel, 'video', 420, 236)
    store.updatePanel(resultId, { content: { content: res.video_url, status: 'success' } })
    store.updatePanel(panel.id, { content: { status: 'idle' } })
    store.pushSnapshot()
    ElMessage.success(t('canvas.messages.composeDone'))
  } catch (err) {
    store.updatePanel(panel.id, { content: { status: 'error', errorDetails: getErrorMessage(err) } })
    ElMessage.error(`${t('canvas.messages.composeFailed')}: ${getErrorMessage(err)}`)
  }
}

/** 三节点统一执行入口（悬停工具栏「生成」按钮） */
async function handleNodeRun(panel: CanvasPanel) {
  if (panel.type === 'tts') await runTtsNode(panel)
  else if (panel.type === 'subtitle') await runSubtitleNode(panel)
  else if (panel.type === 'compose') await runComposeNode(panel)
}

// 悬停工具栏：三节点「生成」
async function handleHoverRunNode() {
  const panel = toolbarPanel.value
  if (!panel) return
  // 实体卡门槛：未挂链实体卡先入库才能生成
  if (!ensureEntityLinked(panel)) return
  await handleNodeRun(panel)
}

// ===== 实体库（画布实体卡挂链） =====
const entityPickerVisible = ref(false)

/** 实体卡生成门槛：未挂链实体卡拦截并提示入库；非实体卡/已挂链/自由画布放行 */
function ensureEntityLinked(panel: typeof store.panels[number]): boolean {
  const linked = entityCardLinkId(panel)
  if (linked === undefined) return true
  if (linked !== null || !store.activeWorkspace?.work_id) return true
  ElMessage.warning(t('entityLib.unlinkWarn'))
  return false
}

/** 实体选择器选中：在快捷菜单位落挂链实体卡（跨集复用入口） */
function onPickEntity(entity: WorkEntityItem) {
  entityPickerVisible.value = false
  const activeVersion = entity.versions.find((v) => v.is_active)
  const designImage = activeVersion?.images.find((i) => i.role === 'design') || activeVersion?.images[0]
  const id = createNodeAt('image', quickMenu.worldX, quickMenu.worldY, {
    kind: entity.kind,
    entityId: entity.id,
    entityName: entity.name,
    entityDesc: entity.description || '',
    content: entity.active_image_url || '',
    status: entity.active_image_url ? 'success' : '',
    ...(designImage ? { assetId: String(designImage.asset_id) } : {}),
  })
  store.updatePanel(id, { name: entity.name })
}

// 通用：重试生成
// - 图片/视频节点就地重生成（自身内容 + 上游连线资源合并，保留模型/参数/参考图）
// - 其余类型用节点自身 prompt 重新生成
async function retryGeneration(panel: typeof store.panels[number]) {
  // 重试闸门：不可重试类目（如提交结果不确定/审核拒绝）禁止原地重试，防重复扣费
  const retryCategory = typeof panel.content?.errorCategory === 'string' ? panel.content.errorCategory : ''
  if (retryCategory && !useModelsStore().canRetryCategory(retryCategory)) {
    ElMessage.warning(t('canvas.messages.categoryNoRetry', { category: t(`errors.category_${retryCategory}`) }))
    return
  }
  // 画布三节点（spec M3）：执行节点本身重跑；其产物节点回溯到执行节点重跑
  if (panel.type === 'tts' || panel.type === 'subtitle' || panel.type === 'compose') {
    await handleNodeRun(panel)
    return
  }
  const runConn = store.connections.find((c) => c.target_panel_id === panel.id)
  const runNode = runConn ? store.panels.find((p) => p.id === runConn.source_panel_id) : null
  if (runNode && ['tts', 'subtitle', 'compose'].includes(runNode.type || '')) {
    await handleNodeRun(runNode)
    return
  }

  if (panel.type === 'image') {
    ElMessage.info(t('canvas.messages.regenerate'))
    try {
      const { executeInNodeGeneration } = await import('@/lib/canvas-generation')
      await executeInNodeGeneration(panel, store)
    } catch (err) {
      ElMessage.error(`${t('canvas.messages.retryFailed')}: ${getErrorMessage(err)}`)
    }
    return
  }
  if (panel.type === 'video') {
    const canGenerate = await checkCreditsBeforeGenerate({ type: 'video', mode: 'image2video', seconds: (panel.content?.seconds as number) || 5 })
    if (!canGenerate) return
    ElMessage.info(t('canvas.messages.regenerate'))
    try {
      const { executeInNodeVideoGeneration } = await import('@/lib/canvas-generation')
      await executeInNodeVideoGeneration(panel, store)
    } catch (err) {
      ElMessage.error(`${t('canvas.messages.retryFailed')}: ${getErrorMessage(err)}`)
    }
    return
  }
  const prompt = (panel.content?.prompt || panel.content?.content || '') as string
  if (!prompt.trim()) {
    ElMessage.warning(t('canvas.messages.retryNoPrompt'))
    return
  }
  await generateImageFromPrompt(panel, prompt, panel.id)
}

// 节点上传文件
function handleNodeUpload(panel: typeof store.panels[number]) {
  if (panel) {
    triggerFileUpload(panel.id)
  }
}

// 蒙版编辑对话框状态
const maskEditState = reactive({
  visible: false,
  panelId: null as string | null,
  imageUrl: '' as string,
})

// 图片加工弹窗状态（裁剪/拆分/放大/AI多角度/打光）
const imageOpsState = reactive({
  crop: { visible: false, panelId: null as string | null, imageUrl: '' },
  split: { visible: false, panelId: null as string | null, imageUrl: '' },
  upscale: { visible: false, panelId: null as string | null, imageUrl: '' },
  angle: { visible: false, panelId: null as string | null, imageUrl: '' },
  lighting: { visible: false, panelId: null as string | null, imageUrl: '' },
  emotion: { visible: false, panelId: null as string | null, imageUrl: '', fixJobs: null as EmotionJobRecord | null },
})

// ============ 画布模板功能 ============
// 画布管理弹窗显示状态（批量操作、模板库）
const managerVisible = ref(false)
// 版本历史弹窗显示状态
const historyVisible = ref(false)
// 云端同步状态指示器（登录态落库后显示）
const cloudSyncEnabled = computed(() => {
  try {
    return !!useUserStore().isAuthenticated
  } catch {
    return false
  }
})
const saveStatusText = computed(() => {
  if (canvasSaveStatus.saving) return t('canvas.saveStatus.saving')
  if (canvasSaveStatus.error) return t('canvas.saveStatus.error')
  if (canvasSaveStatus.lastSavedAt) return t('canvas.saveStatus.saved', { time: canvasSaveStatus.lastSavedAt })
  return ''
})
/** 手动同步远端更新（内部自带保存队列空闲约束，忙碌时只提示） */
async function handleRemoteSync() {
  await store.pullRemoteWorkspace()
}
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
    ElMessage.error(`${t('canvas.templates.saveFailed')}: ${getErrorMessage(err)}`)
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
    ElMessage.error(`${t('canvas.messages.templateApplyFailed')}: ${getErrorMessage(err)}`)
  }
}

// ==================== 节点工具栏（选中驱动） ====================

// 单选节点即工具栏目标；多选/无选中不显示（成组等操作走右键菜单）
const toolbarPanel = computed(() => {
  return store.selectedPanels.length === 1 ? store.selectedPanels[0] : null
})

// 节点工具栏定位：节点上方居中
const nodeToolbarStyle = computed(() => {
  const panel = toolbarPanel.value
  if (!panel) return { display: 'none' }
  // worldToScreen 返回屏幕坐标，减去画布偏移转为相对于 canvas-main 的坐标
  const screen = store.worldToScreen(panel.x + panel.width / 2, panel.y)
  return {
    left: (screen.x - store.canvasRect.left) + 'px',
    top: (screen.y - store.canvasRect.top - 8) + 'px',
    transform: 'translate(-50%, -100%)',
  }
})

// ---- 悬停工具栏事件处理（复杂功能简化为 ElMessage 提示） ----

// 节点信息弹窗（查看节点信息：名称/类型/状态/模型/提示词等元数据）
const nodeInfoPanel = ref<typeof store.panels[number] | null>(null)
const nodeInfoVisible = computed({
  get: () => nodeInfoPanel.value !== null,
  set: (v: boolean) => { if (!v) nodeInfoPanel.value = null },
})

function handleHoverInfo() {
  nodeInfoPanel.value = toolbarPanel.value
}

/* ---------- 节点信息弹窗 ---------- */

/** 信息弹窗：节点内容元数据（统一从 panel.content 读取） */
const nodeInfoContent = computed(() => nodeInfoPanel.value?.content || {})

const nodeInfoPrompt = computed(() => {
  const v = nodeInfoContent.value.prompt
  return typeof v === 'string' ? v : ''
})

const nodeInfoModel = computed(() => {
  const v = nodeInfoContent.value.model
  return typeof v === 'string' ? v : ''
})

const nodeInfoSize = computed(() => {
  const v = nodeInfoContent.value.size
  return typeof v === 'string' ? v : ''
})

const nodeInfoRefCount = computed(() => {
  const v = nodeInfoContent.value.referenceImages
  return Array.isArray(v) ? v.length : 0
})

/** 信息弹窗：分镜来源（分镜派生节点显示来源剧本与镜号） */
const nodeInfoShotFrom = computed(() => {
  const p = nodeInfoPanel.value
  if (!p) return ''
  const info = getShotLineageInfo(p)
  if (!info) return ''
  const script = store.panels.find((pp) => pp.id === info.lineage.scriptPanelId)
  return t('canvas.nodeInfo.shotFrom', { name: script?.name || '', no: info.lineage.shotNo })
})

/** 信息弹窗：状态文案 */
const nodeInfoStatusText = computed(() => {
  switch (nodeInfoContent.value.status) {
    case 'loading': return t('canvas.node.generating')
    case 'success': return t('canvas.nodeInfo.statusSuccess')
    case 'error': return t('canvas.node.generateFailed')
    default: return t('canvas.nodeInfo.statusIdle')
  }
})

async function handleInfoCopyPrompt() {
  if (!nodeInfoPrompt.value) return
  const ok = await copyText(nodeInfoPrompt.value, t('canvas.messages.promptCopied'))
  if (!ok) ElMessage.warning(t('canvas.messages.copyFailed'))
}

function handleHoverDelete() {
  const panel = toolbarPanel.value
  if (!panel) return
  store.pushSnapshot()
  store.deletePanel(panel.id)
}

// 悬停工具栏：重试
async function handleHoverRetry() {
  const panel = toolbarPanel.value
  if (!panel) return
  await retryGeneration(panel)
}

// 悬停工具栏：存素材到素材库
async function handleHoverSaveAsset() {  const panel = toolbarPanel.value
  if (!panel) return

  const content: Record<string, unknown> = panel.content || {}
  const url = (content.content || content.url) as string
  if (!url) {
    ElMessage.warning(t('canvas.messages.noSaveContent'))
    return
  }

  try {
    const { useAssetStore } = await import('@/stores/canvasAsset')
    const assetStore = useAssetStore()
    assetStore.registerAsset({
      type: panel.type as 'image' | 'video',
      url: url,
      prompt: (content.prompt || '') as string,
      name: panel.name || `${panel.type}-${panel.id.slice(0, 8)}`,
      sourceNodeId: panel.id,
      work_id: store.activeWorkspace?.work_id ?? undefined,
    })
    ElMessage.success(t('canvas.messages.savedToAssets'))
  } catch (err) {
    ElMessage.error(`${t('canvas.messages.saveFailed')}: ${getErrorMessage(err) || err}`)
  }
}

// 悬停工具栏：送进剪辑器（素材懒入库 → 建剪辑工程草稿 → 跳 /editor/:uid）
async function handleHoverSendToEditor() {
  const panel = toolbarPanel.value
  if (!panel) return
  const content: Record<string, unknown> = panel.content || {}
  const url = (content.content || content.url) as string
  if (!url) {
    ElMessage.warning(t('canvas.messages.noSaveContent'))
    return
  }

  // 已持数字 assetId 直接引用；否则经 registerAsset 懒入库（未登录/失败降级 uid → 阻断并提示）
  let assetId: number | null = null
  const existing = content.assetId
  if (existing != null && /^\d+$/.test(String(existing))) {
    assetId = Number(existing)
  }
  if (assetId == null) {
    const { useAssetStore } = await import('@/stores/canvasAsset')
    const assetStore = useAssetStore()
    const item = await assetStore.registerAsset({
      type: panel.type as 'image' | 'video',
      url,
      prompt: (content.prompt || '') as string,
      name: panel.name || `${panel.type}-${panel.id.slice(0, 8)}`,
      sourceNodeId: panel.id,
      work_id: store.activeWorkspace?.work_id ?? undefined,
    })
    if (item && /^\d+$/.test(item.id)) assetId = Number(item.id)
  }
  if (assetId == null) {
    ElMessage.warning(t('canvas.messages.sendToEditorNeedLogin'))
    return
  }

  try {
    const detail = await createEditorProject({
      title: panel.name || t('editorProjects.defaultTitle'),
      work_id: store.activeWorkspace?.work_id ?? undefined,
      source_workspace_id: store.activeWorkspaceId ?? undefined,
      asset_ids: [assetId],
    })
    ElMessage.success(t('editor.sendToEditorDone'))
    void router.push(`/editor/${detail.uid}`)
  } catch (err) {
    ElMessage.error(`${t('editor.sendToEditorFailed')}: ${getErrorMessage(err) || err}`)
  }
}

/**
 * 悬停工具栏：下载节点内容
 * - 图片：走后端水印代理接口，下载带水印版本
 * - 视频：直接代理下载（视频水印暂未实现）
 */
async function handleHoverDownload() {
  const p = toolbarPanel.value
  if (!p?.content?.content) {
    ElMessage.warning(t('canvas.messages.noDownloadContent'))
    return
  }

  const contentUrl = p.content.content as string
  const isVideo = p.type === 'video'
  const ext = isVideo ? 'mp4' : 'png'
  const defaultName = `agnes-${p.type}-${p.id.slice(0, 8)}.${ext}`

  try {
    if (isVideo) {
      // 视频：暂时通过通用代理下载（视频水印后续再实现）
      // 注意：当前没有通用视频代理接口，先提示用户
      // 直接打开新页签作为临时方案，后续添加视频水印接口后替换
      window.open(contentUrl, '_blank', 'noopener,noreferrer')
      ElMessage.info(t('canvas.messages.videoDownloadTip'))
    } else {
      // 图片：通过后端水印接口下载带水印版本
      await downloadWatermarkedImage(contentUrl, defaultName)
      ElMessage.success(t('canvas.messages.downloadStarted'))
    }
  } catch (err: any) {
    console.warn('[Canvas] 下载失败：', err)
    ElMessage.error(err?.message || t('canvas.messages.downloadFailed'))
  }
}

// 悬停工具栏：通用编辑（按节点类型分发）
function handleHoverEdit() {
  const panel = toolbarPanel.value
  if (!panel) return

  switch (panel.type) {
    case 'text':
      handleHoverEditText()
      break
    case 'audio':
      triggerFileUpload(panel.id, 'audio/*')
      break
    case 'image':
    case 'video':
      // 聚焦编辑：选中即打开悬浮 AI 对话框（提示词支持 @ 引用上游）
      store.selectPanel(panel.id, { append: false })
      break
    default:
      ElMessage.info(`${getNodeName(panel.type ?? '')} - ${t('canvas.messages.saveFailed')}`)
  }
}

// 悬停工具栏：编辑文字（通过 store.editingPanelId 触发 CanvasNode 进入编辑模式）
function handleHoverEditText() {
  const panel = toolbarPanel.value
  if (!panel || panel.type !== 'text') return

  store.selectPanel(panel.id, { append: false })
  // 使用 nextTick 确保 CanvasNode 已渲染并响应
  nextTick(() => {
    store.editingPanelId = panel.id
  })
}

function handleHoverFontSizeDown() {
  const panel = toolbarPanel.value
  if (!panel) return
  const cur = (panel.content?.fontSize ?? 16) as number
  store.updatePanel(panel.id, { content: { fontSize: Math.max(10, cur - 2) } })
}

function handleHoverFontSizeUp() {
  const panel = toolbarPanel.value
  if (!panel) return
  const cur = (panel.content?.fontSize ?? 16) as number
  store.updatePanel(panel.id, { content: { fontSize: Math.min(48, cur + 2) } })
}

function handleHoverUploadImage() {
  triggerFileUpload(toolbarPanel.value?.id ?? null, 'image/*')
}

function handleHoverUploadVideo() {
  triggerFileUpload(toolbarPanel.value?.id ?? null, 'video/*')
}

function handleHoverUploadAudio() {
  triggerFileUpload(toolbarPanel.value?.id ?? null, 'audio/*')
}

function handleHoverCopyPrompt() {
  const prompt = (toolbarPanel.value?.content?.prompt ?? '') as string

  void copyText(prompt, t('canvas.messages.promptCopied')).then((ok) => {
    if (!ok) ElMessage.warning(t('canvas.messages.copyFailed'))
  })
}

// 悬停工具栏：反推提示词（图生文）—— 将当前 hover 图片发给 AI，生成适合 AI 绘画的英文 prompt
// 反推结果会同时：
//   1. 写入图片节点的 content.prompt 字段（供 Copy Prompt 使用）
//   2. 在图片右侧自动创建一个文字节点，把 prompt 作为可见文本展示，并用连线关联
async function handleHoverDescribe() {
  const panel = toolbarPanel.value
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
    const sessionId = session.id

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
        content: `${t('canvas.messages.describeFailed')}: ${getErrorMessage(err) || err}`,
        status: 'error',
      },
    })
    ElMessage.error(`${t('canvas.messages.describeFailed')}: ${getErrorMessage(err) || err}`)
  }
}

function handleHoverReplaceImage() {
  triggerFileUpload(toolbarPanel.value?.id ?? null, 'image/*')
}

function handleHoverToggleRatio() {
  const p = toolbarPanel.value
  if (!p) return
  const cur = (p.content?.freeResize ?? false) as boolean
  // 从自由比例 → 锁比例：根据当前宽高强制调整高度，保持中心不动
  if (cur) {
    const ratio = p.width / p.height
    const newH = p.width / ratio
    const dy = (newH - p.height) / 2
    store.updatePanel(p.id, {
      content: { freeResize: false },
      height: newH,
      y: p.y - dy,
    })
  } else {
    store.updatePanel(p.id, { content: { freeResize: true } })
  }
  ElMessage.success(cur ? t('canvas.hoverToolbar.lockRatio') : t('canvas.hoverToolbar.unlockRatio'))
}

function handleHoverMaskEdit() {
  const panel = toolbarPanel.value
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
      mask,
      context: buildCanvasContext(panel, store),
    })

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
      const status: ImageTaskPollStatus = await getImageTaskStatus(taskId)
      const isSuccess = ['completed', 'succeeded', 'success', 'done'].includes(status.status)
      const isFailed = ['failed', 'error'].includes(status.status)

      if (isSuccess) {
        const resultUrl = status.result_url || status.image_url || status.url || status.data?.[0]?.url
        store.updatePanel(panelId!, { content: { content: resultUrl, status: 'success' } })
        store.pushSnapshot()
        taskQueue.updateCanvasTask(taskId, { status: 'success', resultUrl, progress: 100 })
        // 成功提示附带消耗积分数量
        showCostConsumedMessage({ type: 'image', mode: 'image2image', size: '1024x1024' }, t('canvas.messages.maskEditDone'))
        // 【用户偏好】自动下载 + 完成通知
        const prefsStore = usePreferencesStore()
        if (resultUrl) {
          prefsStore.autoDownload(resultUrl, 'image', { modelId: useModelsStore().defaultImageModel })
        }
        prefsStore.notifyComplete('image', { prompt, modelId: useModelsStore().defaultImageModel })
        return
      }
      if (isFailed) {
        const errMsg = status.message || status.error || t('canvas.messages.maskEditFailed')
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
    store.updatePanel(panelId!, { content: { status: 'error', errorDetails: getErrorMessage(err) } })
    ElMessage.error(`${t('canvas.messages.maskEditFailed')}: ${getErrorMessage(err)}`)
  }
}

// 图片裁剪：打开可视化裁剪弹窗
function handleHoverCrop() {
  const panel = toolbarPanel.value
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
    ElMessage.error(`${t('canvas.messages.cropFailed')}: ${getErrorMessage(err) || err}`)
  }
}

// 图片拆分：打开行列选择弹窗
function handleHoverSplit() {
  const panel = toolbarPanel.value
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
    ElMessage.error(`${t('canvas.messages.splitFailed')}: ${getErrorMessage(err) || err}`)
  }
}

// 图片放大：打开目标尺寸选择弹窗
function handleHoverUpscale() {
  const panel = toolbarPanel.value
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
    ElMessage.error(`${t('canvas.messages.upscaleFailed')}: ${getErrorMessage(err) || err}`)
  }
}

// 图片超分：复用放大弹窗，默认 4K + 高清算法
function handleHoverSuperResolution() {
  const panel = toolbarPanel.value
  if (!panel?.content?.content) return
  const imageUrl = panel.content.content as string
  imageOpsState.upscale.visible = true
  imageOpsState.upscale.panelId = panel.id
  imageOpsState.upscale.imageUrl = imageUrl
}

// AI 多角度：打开角度配置弹窗
function handleHoverAngle() {
  const panel = toolbarPanel.value
  if (!panel?.content?.content) return
  const imageUrl = panel.content.content as string
  imageOpsState.angle.visible = true
  imageOpsState.angle.panelId = panel.id
  imageOpsState.angle.imageUrl = imageUrl
}

// AI 打光：打开打光配置弹窗
function handleHoverLighting() {
  const panel = toolbarPanel.value
  if (!panel?.content?.content) return
  const imageUrl = panel.content.content as string
  imageOpsState.lighting.visible = true
  imageOpsState.lighting.panelId = panel.id
  imageOpsState.lighting.imageUrl = imageUrl
}

// 表情控制：打开情绪调节弹窗（节点携带逐脸任务记录时进入微调模式）
function handleHoverEmotion() {
  const panel = toolbarPanel.value
  if (!panel?.content?.content) return
  const imageUrl = panel.content.content as string
  imageOpsState.emotion.visible = true
  imageOpsState.emotion.panelId = panel.id
  imageOpsState.emotion.imageUrl = imageUrl
  imageOpsState.emotion.fixJobs = (panel.meta?.emotionJobs as EmotionJobRecord | undefined) ?? null
}

// 轮询图片任务直至完成并返回结果图 URL（进度同步任务队列）；失败/无图/超时抛错
async function waitForImageTask(taskId: string): Promise<string> {
  const { getImageTaskStatus } = await import('@/api/images')
  for (let i = 0; i < 150; i++) {
    await new Promise(r => setTimeout(r, 2000))
    const status: ImageTaskPollStatus = await getImageTaskStatus(taskId)
    if (['completed', 'succeeded', 'success', 'done'].includes(status.status)) {
      const resultUrl = status.result_url || status.image_url || status.url || status.data?.[0]?.url
      if (!resultUrl) throw new Error(t('canvas.messages.generateFailed'))
      return resultUrl
    }
    if (['failed', 'error'].includes(status.status)) {
      throw new Error(status.message || status.error || t('canvas.messages.generateFailed'))
    }
    taskQueue.updateCanvasTask(taskId, { status: 'processing', progress: typeof status.progress === 'number' ? status.progress : undefined })
  }
  throw new Error(t('canvas.messages.generateTimeout'))
}

// 派生图生成共享链路（多角度/打光等）：积分预检 → 建 loading 子节点并连线 → 图生图任务 → 轮询更新
async function generateDerivedImage(opts: {
  panelId: string | null
  imageUrl: string
  prompt: string
  nameSuffix: string
  doneMessage: string
  failedMessage: string
  size?: string
  base64Images?: string[]
}): Promise<void> {
  const panel = store.panels.find(p => p.id === opts.panelId)
  if (!panel) return

  const size = opts.size || '1024x1024'

  // 积分预检：派生图走 image2image 模式
  const canGenerate = await checkCreditsBeforeGenerate({ type: 'image', mode: 'image2image', size })
  if (!canGenerate) return

  // 先创建 loading 状态的子节点
  const newId = store.addPanel({
    type: 'image',
    name: (panel.name || '') + ' · ' + opts.nameSuffix,
    x: panel.x + panel.width + 60,
    y: panel.y,
    width: panel.width,
    height: panel.height,
    content: { content: '', status: 'loading', prompt: opts.prompt },
    meta: {},
    is_locked: false,
    is_hidden: false,
  })
  store.addConnection({
    source_panel_id: panel.id,
    target_panel_id: newId,
    type: 'flow',
  })

  let taskId = ''
  try {
    const { createImageTask } = await import('@/api/images')
    const { toBase64IfNeeded } = await import('@/lib/canvas-image-ops')
    // 参考图转 base64（远程 URL 会自动走后端代理下载后再转）
    const base64Images = opts.base64Images ?? [await toBase64IfNeeded(opts.imageUrl)]

    // 派生图 context：源是挂链实体卡时按 angle 角色追加进当前采用版本（兄弟节点照常落画布）
    const context = buildCanvasContext(panel, store)
    const srcEntityId = entityCardLinkId(panel)
    if (srcEntityId) {
      context.entity_id = srcEntityId
      context.version_role = 'angle'
    }

    const resp = await createImageTask({
      prompt: opts.prompt,
      model: useModelsStore().defaultImageModel,
      size,
      response_format: 'url',
      mode: 'image2image',
      // 用数组形式传参，与当前后端 schema 对齐；旧字段也保留一份兜底
      base64_images: base64Images,
      base64_image: base64Images[0],
      context,
    })
    taskId = resp.task_id
    taskQueue.registerCanvasTask({
      taskId,
      type: 'image',
      prompt: opts.prompt,
      backendTaskId: taskId,
      panelId: newId,
    })

    const resultUrl = await waitForImageTask(taskId)
    store.updatePanel(newId, { content: { content: resultUrl, status: 'success' } })
    store.pushSnapshot()
    taskQueue.updateCanvasTask(taskId, { status: 'success', resultUrl, progress: 100 })
    showCostConsumedMessage({ type: 'image', mode: 'image2image', size }, opts.doneMessage)
    // 【用户偏好】自动下载 + 完成通知
    const prefsStore = usePreferencesStore()
    if (resultUrl) {
      prefsStore.autoDownload(resultUrl, 'image', { modelId: useModelsStore().defaultImageModel })
    }
    prefsStore.notifyComplete('image', { prompt: opts.prompt, modelId: useModelsStore().defaultImageModel })
  } catch (err) {
    console.error('[canvas] derived image error:', err)
    if (taskId) taskQueue.updateCanvasTask(taskId, { status: 'failed' })
    store.updatePanel(newId, { content: { status: 'error', errorDetails: getErrorMessage(err) } })
    ElMessage.error(`${opts.failedMessage}: ${getErrorMessage(err)}`)
  }
}

// AI 多角度确认
async function handleAngleConfirm({ prompt }: { prompt: string }) {
  imageOpsState.angle.visible = false
  await generateDerivedImage({
    panelId: imageOpsState.angle.panelId,
    imageUrl: imageOpsState.angle.imageUrl,
    prompt,
    nameSuffix: t('canvas.imageOps.angleSuffix'),
    doneMessage: t('canvas.messages.angleDone'),
    failedMessage: t('canvas.messages.angleFailed'),
  })
}

// AI 打光确认
async function handleLightingConfirm({ prompt, label }: { prompt: string, label: string }) {
  imageOpsState.lighting.visible = false
  await generateDerivedImage({
    panelId: imageOpsState.lighting.panelId,
    imageUrl: imageOpsState.lighting.imageUrl,
    prompt,
    nameSuffix: label,
    doneMessage: t('canvas.messages.lightingDone'),
    failedMessage: t('canvas.messages.lightingFailed'),
  })
}

// 表情控制确认：逐脸「紧裁切 → 图生图 → 椭圆羽化合成」。上游是重合成模型，
// 只有紧裁切任务才能保证表情局部生效；各脸任务并发、合成串行，宫格等
// 椭圆外像素始终以源图为底零改动，失败的脸保留原表情。
// 微调模式（fixContext）：基准回原始源图重建——未重抽的脸从上一轮结果按椭圆取回，
// 重抽的脸对原始图重新生成，上一轮的白圈/接缝等伪影在椭圆外不会被带入
async function handleEmotionConfirm(payload: EmotionGeneratePayload) {
  imageOpsState.emotion.visible = false
  const panel = store.panels.find(p => p.id === imageOpsState.emotion.panelId)
  if (!panel) return
  const fixContext = payload.fixContext
  const sourcePanel = fixContext ? store.panels.find(p => p.id === fixContext.sourcePanelId) : null
  const fixSourceUrl = fixContext ? ((sourcePanel?.content?.content as string) || '') : ''
  if (fixContext && !fixSourceUrl) {
    ElMessage.error(t('canvas.imageOps.emotionFixSourceMissing'))
    return
  }

  // 积分预检（每张脸一个图生图任务，费用随角色数增加）
  const canGenerate = await checkCreditsBeforeGenerate({ type: 'image', mode: 'image2image', size: '1024x1024' })
  if (!canGenerate) return

  const summary = payload.characters.map(c => `${c.name}·${c.label}`).join('，')
  const labels = [...new Set(payload.characters.map(c => c.label))].join('+')
  // 逐脸任务记录持久化到结果节点（微调模式的下一轮沿用；sourcePanelId 恒指原始源图节点）
  const allFaces = fixContext
    ? fixContext.allFaces.map(f => payload.characters.find(c => c.faceBox.id === f.faceBox.id) ?? f)
    : payload.characters
  const emotionJobs = {
    sourcePanelId: fixContext ? fixContext.sourcePanelId : String(imageOpsState.emotion.panelId),
    allFaces,
  }
  const newId = store.addPanel({
    type: 'image',
    name: (panel.name || '') + ' · ' + (fixContext ? `${t('canvas.imageOps.emotionFixTitle')}·${labels}` : labels),
    x: panel.x + panel.width + 60,
    y: panel.y,
    width: panel.width,
    height: panel.height,
    content: { content: '', status: 'loading', prompt: `${t('canvas.imageOps.emotionTitle')}：${summary}` },
    meta: { emotionJobs },
    is_locked: false,
    is_hidden: false,
  })
  store.addConnection({ source_panel_id: panel.id, target_panel_id: newId, type: 'flow' })

  try {
    const { createImageTask } = await import('@/api/images')
    const { toBase64IfNeeded } = await import('@/lib/canvas-image-ops')
    const { buildEmotionArtifacts, buildEmotionPrompt, compositeEmotionFaces, emotionGenerationSize, emotionDriftScore, findEmotionPreset, resolveEmotionEditRegion } = await import('@/lib/canvas-emotion')

    // 重建基准：微调模式用原始源图（干净底），否则用当前图
    const sourceBase64 = await toBase64IfNeeded(fixContext ? fixSourceUrl : imageOpsState.emotion.imageUrl)
    let accumulated = sourceBase64

    // 微调模式：未重抽的脸从上一轮结果按椭圆取回（保持已生成的表情，椭圆外旧伪影不带入）
    if (fixContext) {
      const rerollIds = new Set(payload.characters.map(c => c.faceBox.id))
      const rebuildBase64 = await toBase64IfNeeded(imageOpsState.emotion.imageUrl)
      for (const face of allFaces) {
        if (rerollIds.has(face.faceBox.id)) continue
        accumulated = await compositeEmotionFaces(
          accumulated,
          rebuildBase64,
          resolveEmotionEditRegion(face.faceBox, payload.imageWidth, payload.imageHeight),
          [{ faceBox: face.faceBox, sameCoords: true }],
        )
      }
    }

    // 每张脸独立紧裁切与提示词，各自一个图生图任务并发执行
    const jobs = await Promise.all(payload.characters.map(async (character) => {
      const artifacts = await buildEmotionArtifacts(sourceBase64, [character.faceBox], payload.imageWidth, payload.imageHeight)
      const preset = findEmotionPreset(character.intimacy, character.arousal)
      const prompt = buildEmotionPrompt([{ name: character.name, preset, faceBox: character.faceBox }], artifacts.editRegion)
      return { character, prompt, editRegion: artifacts.editRegion, sourceDataUrl: artifacts.sourceDataUrl, characterDataUrl: artifacts.characterDataUrls[0], maskDataUrl: artifacts.maskDataUrl }
    }))

    const taskIds = jobs.map(() => [] as string[])
    const createFaceTask = async (jobIndex: number, useMask: boolean): Promise<string> => {
      const job = jobs[jobIndex]
      const resp = await createImageTask({
        prompt: job.prompt,
        model: useModelsStore().defaultImageModel,
        size: emotionGenerationSize(job.editRegion),
        response_format: 'url',
        mode: 'image2image',
        base64_images: [job.sourceDataUrl, job.characterDataUrl],
        base64_image: job.sourceDataUrl,
        // 蒙版（白色=可编辑）把上游重绘范围锁死在人脸椭圆内，取景想漂都没空间
        mask: useMask ? job.maskDataUrl : undefined,
        context: buildCanvasContext(panel, store),
      })
      taskIds[jobIndex].push(resp.task_id)
      taskQueue.registerCanvasTask({ taskId: resp.task_id, type: 'image', prompt: job.prompt, backendTaskId: resp.task_id, panelId: newId })
      return resp.task_id
    }

    // 单脸生成 + 人脸检测 + 几何漂移评分（生成质量有随机性，评分为择优依据）
    const attemptFace = async (jobIndex: number, useMask: boolean) => {
      const job = jobs[jobIndex]
      const url = await waitForImageTask(await createFaceTask(jobIndex, useMask))
      const generatedBase64 = await toBase64IfNeeded(url)
      let generatedFaceBox: EmotionFaceBox | undefined
      let generatedWidth = 0
      let generatedHeight = 0
      try {
        const detection = await detectFaces(generatedBase64)
        generatedWidth = detection.imageWidth
        generatedHeight = detection.imageHeight
        generatedFaceBox = [...detection.faces].sort((a, b) => b.width * b.height - a.width * a.height)[0]
      } catch (reason) {
        console.warn('[canvas] emotion align detect failed:', reason)
      }
      const score = emotionDriftScore({ faceBox: job.character.faceBox, generatedFaceBox }, job.editRegion, generatedWidth, generatedHeight)
      return { url, generatedBase64, generatedFaceBox, score }
    }

    // 单脸完整流程：首选带 mask；渠道不认 mask 时自动去 mask；
    // 首次结果几何漂移超标（该次重绘跑偏）自动再roll一次，取分低者
    const generateFaceBest = async (jobIndex: number) => {
      const job = jobs[jobIndex]
      let useMask = true
      let best: Awaited<ReturnType<typeof attemptFace>> | null = null
      try {
        best = await attemptFace(jobIndex, useMask)
      } catch (error) {
        console.warn('[canvas] emotion masked task failed, retry without mask:', job.character.name, error)
        useMask = false
        best = await attemptFace(jobIndex, useMask)
      }
      if (best.score > 0.08) {
        try {
          const second = await attemptFace(jobIndex, useMask)
          if (second.score < best.score) best = second
        } catch (error) {
          console.warn('[canvas] emotion face reroll failed:', job.character.name, error)
        }
      }
      return best
    }

    // 各脸并发生成择优；合成必须串行，避免并发读改同一底图
    const results = await Promise.allSettled(jobs.map((_, jobIndex) => generateFaceBest(jobIndex)))
    const failedRoles: string[] = []
    for (let i = 0; i < jobs.length; i++) {
      const result = results[i]
      const ids = taskIds[i]
      if (result.status === 'fulfilled') {
        // 合成按"生成图人脸 → 源图人脸"做带死区的软校正（偏差在检测噪声底内不修，超过死区线性增强到全量）
        accumulated = await compositeEmotionFaces(accumulated, result.value.generatedBase64, jobs[i].editRegion, [{ faceBox: jobs[i].character.faceBox, generatedFaceBox: result.value.generatedFaceBox }])
        // 重试链上只有最后一个任务成功，其余标 failed
        ids.forEach(id => taskQueue.updateCanvasTask(id, { status: 'failed' }))
        taskQueue.updateCanvasTask(ids[ids.length - 1], { status: 'success', resultUrl: result.value.url, progress: 100 })
      } else {
        failedRoles.push(`${jobs[i].character.name}·${jobs[i].character.label}`)
        ids.forEach(id => taskQueue.updateCanvasTask(id, { status: 'failed' }))
        console.error('[canvas] emotion face failed:', jobs[i].character.name, result.reason)
      }
    }
    if (failedRoles.length === jobs.length) throw new Error(t('canvas.messages.generateFailed'))

    const { uploadImage } = await import('@/api/uploads')
    const file = await emotionResultToFile(accumulated, 'emotion-composite.png')
    const finalUrl = (await uploadImage(file)).url
    store.updatePanel(newId, { content: { content: finalUrl, status: 'success' } })
    store.pushSnapshot()
    showCostConsumedMessage({ type: 'image', mode: 'image2image', size: '1024x1024' }, t('canvas.messages.emotionDone'))
    const prefsStore = usePreferencesStore()
    prefsStore.autoDownload(finalUrl, 'image', { modelId: useModelsStore().defaultImageModel })
    prefsStore.notifyComplete('image', { prompt: summary, modelId: useModelsStore().defaultImageModel })
    if (failedRoles.length) ElMessage.warning(t('canvas.messages.emotionPartialFailed', { roles: failedRoles.join('、') }))
  } catch (err) {
    console.error('[canvas] emotion error:', err)
    store.updatePanel(newId, { content: { status: 'error', errorDetails: getErrorMessage(err) } })
    ElMessage.error(`${t('canvas.messages.emotionFailed')}: ${getErrorMessage(err)}`)
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

// 视频节点截帧（首帧/当前帧/尾帧）：新建图片子节点并连线（衔接连续镜头）
// 工具栏统一分发：注册表工具 id → 既有处理器（处理器内部读 toolbarPanel）
function handleToolAction(toolId: string, payload?: Record<string, unknown>) {
  const panel = toolbarPanel.value
  if (!panel) return
  const actions: Record<string, () => void> = {
    info: handleHoverInfo,
    delete: handleHoverDelete,
    retry: handleHoverRetry,
    'run-node': handleHoverRunNode,
    'save-asset': handleHoverSaveAsset,
    'send-to-editor': handleHoverSendToEditor,
    download: handleHoverDownload,
    edit: handleHoverEdit,
    'quick-generate-image': () => handleQuickGenerate({ panel, mode: String(payload?.mode ?? 'image2image') }),
    'quick-generate-video': () => handleQuickGenerate({ panel, mode: String(payload?.mode ?? 'image2video') }),
    'font-size-down': handleHoverFontSizeDown,
    'font-size-up': handleHoverFontSizeUp,
    'upload-image': handleHoverUploadImage,
    'upload-video': handleHoverUploadVideo,
    'upload-audio': handleHoverUploadAudio,
    'copy-prompt': handleHoverCopyPrompt,
    describe: handleHoverDescribe,
    'replace-image': handleHoverReplaceImage,
    'toggle-ratio': handleHoverToggleRatio,
    'mask-edit': handleHoverMaskEdit,
    crop: handleHoverCrop,
    split: handleHoverSplit,
    upscale: handleHoverUpscale,
    'super-resolution': handleHoverSuperResolution,
    angle: handleHoverAngle,
    lighting: handleHoverLighting,
    emotion: handleHoverEmotion,
    'view-large': handleHoverViewLarge,
    'derive-video': handleHoverDeriveVideo,
    'derive-tail': handleHoverDeriveTail,
    'derive-prev': handleHoverDerivePrev,
    'derive-chain': handleHoverDeriveChain,
    reshoot: handleHoverReshoot,
    'capture-frame-first': () => handleHoverCaptureFrame({ panel, position: 'first' }),
    'capture-frame': () => handleHoverCaptureFrame({ panel, position: 'current' }),
    'capture-frame-last': () => handleHoverCaptureFrame({ panel, position: 'last' }),
  }
  actions[toolId]?.()
}

async function handleHoverCaptureFrame(payload: { panel: typeof store.panels[number]; position: 'first' | 'current' | 'last' }) {
  const panel = payload.panel
  if (!panel?.content?.content) return
  const videoUrl = panel.content.content as string
  const suffixKey = payload.position === 'first'
    ? 'canvas.imageOps.frameSuffixFirst'
    : payload.position === 'last'
      ? 'canvas.imageOps.frameSuffixLast'
      : 'canvas.imageOps.frameSuffix'
  try {
    ElMessage.info(t('canvas.messages.captureFrameProcessing'))
    const { captureVideoFrame, getVideoTime } = await import('@/lib/canvas-image-ops')
    const time = payload.position === 'current' ? getVideoTime(panel.id) : payload.position
    const frame = await captureVideoFrame(videoUrl, time)
    createImageChildNode(panel, frame, (panel.name || '') + ' · ' + t(suffixKey))
    store.pushSnapshot()
    ElMessage.success(t('canvas.messages.captureFrameDone'))
  } catch (err) {
    ElMessage.error(`${t('canvas.messages.captureFrameFailed')}: ${getErrorMessage(err) || err}`)
  }
}

function handleHoverViewLarge() {
  const p = toolbarPanel.value
  if (p?.content?.content) previewImage.value = p.content.content as string
}

// 分镜图节点一键派生视频节点（单镜头图生视频）
async function handleHoverDeriveVideo() {
  const panel = toolbarPanel.value
  if (!panel) return
  try {
    await deriveVideoForShot(panel)
  } catch (err) {
    ElMessage.error(`${t('canvas.messages.generateFailed')}: ${getErrorMessage(err) || err}`)
  }
}

// 分镜图节点一键生成尾帧（keyframes 结束帧 + 跨镜头衔接底图）
async function handleHoverDeriveTail() {
  const panel = toolbarPanel.value
  if (!panel) return
  try {
    await deriveTailFrameFromImageNode(panel)
  } catch (err) {
    ElMessage.error(`${t('canvas.messages.generateFailed')}: ${getErrorMessage(err) || err}`)
  }
}

// 分镜图节点一键推演前段画面（画面时间推演，向前延展）
async function handleHoverDerivePrev() {
  const panel = toolbarPanel.value
  if (!panel) return
  try {
    await derivePrevFrameFromImageNode(panel)
  } catch (err) {
    ElMessage.error(`${t('canvas.messages.generateFailed')}: ${getErrorMessage(err) || err}`)
  }
}

// 分镜图节点一键生成分段视频（画面链长视频：补帧 + 分段 + compose）
async function handleHoverDeriveChain() {
  const panel = toolbarPanel.value
  if (!panel) return
  try {
    await deriveChainVideosFromImageNode(panel)
  } catch (err) {
    ElMessage.error(`${t('canvas.messages.generateFailed')}: ${getErrorMessage(err) || err}`)
  }
}

// 重拍此镜头：就地重拍（保留模型/参数/参考图/源图），与重试同链路
async function handleHoverReshoot() {
  const panel = toolbarPanel.value
  if (!panel) return
  await retryGeneration(panel)
}

/**
 * 预览大图弹窗：下载按钮（走后端带水印下载）
 */
async function downloadPreviewImage() {
  if (!previewImage.value) return
  try {
    const defaultName = `agnes-preview-${Date.now()}.png`
    await downloadWatermarkedImage(previewImage.value, defaultName)
    ElMessage.success(t('canvas.messages.downloadStarted'))
  } catch (err: any) {
    console.warn('[Canvas Preview] 下载失败：', err)
    ElMessage.error(err?.message || t('canvas.messages.downloadFailed'))
  }
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
  const updates: Record<string, any> = {
    content: {
      content: nodeUrl,
      status: 'success',
      prompt: asset.prompt || '',
      assetId: asset.id || '',
    },
  }
  if (asset.name) {
    updates.name = asset.name
  }
  store.updatePanel(id, updates)
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
      assetId: asset.id || '',
    },
  })
  ElMessage.success(t('canvas.messages.nodeCreated'))
}

// ==================== 系统文件拖入 / 粘贴 ====================

// 文件注册进素材库（Blob 持久化到 IndexedDB，刷新后不失效）并在落点批量创建媒体节点
async function createMediaNodesFromFiles(files: File[], worldX: number, worldY: number) {
  const media: { file: File; type: 'image' | 'video' }[] = []
  for (const file of files) {
    if (file.type.startsWith('image/')) media.push({ file, type: 'image' })
    else if (file.type.startsWith('video/')) media.push({ file, type: 'video' })
  }
  const skipped = files.length - media.length
  if (media.length === 0) {
    ElMessage.warning(t('canvas.messages.filesSkipped', { n: skipped }))
    return
  }
  store.pushSnapshot()
  const { useAssetStore } = await import('@/stores/canvasAsset')
  const assetStore = useAssetStore()
  // 素材面板是 v-if 懒挂载，注册前必须先加载既有索引，否则 _persist 会用空索引覆盖旧素材
  await assetStore.hydrate()
  const positions = planDropLayout(media.map((item) => NODE_DEFAULT_SIZES[item.type]), worldX, worldY)
  let created = 0
  for (const [i, item] of media.entries()) {
    try {
      const asset = await assetStore.registerAsset({ type: item.type, blob: item.file, name: item.file.name, prompt: '', work_id: store.activeWorkspace?.work_id ?? undefined })
      if (!asset) continue
      const size = NODE_DEFAULT_SIZES[item.type]
      const id = store.addPanel({
        type: item.type,
        name: item.file.name || getNodeName(item.type),
        x: positions[i].x,
        y: positions[i].y,
        width: size.width,
        height: size.height,
        content: {},
      })
      store.updatePanel(id, { content: { content: asset.url, status: 'success', bytes: item.file.size, assetId: asset.id } })
      store.selectPanel(id, { append: true })
      created++
    } catch (err) {
      console.warn('[canvas] 文件建节点失败:', err)
    }
  }
  if (created > 0) ElMessage.success(t('canvas.messages.nodesAdded', { n: created }))
  if (skipped > 0) ElMessage.warning(t('canvas.messages.filesSkipped', { n: skipped }))
}

// 刷新后 blob object URL 失效：按 content.assetId 从素材库重建节点媒体地址（hydrate 幂等）
async function remapAssetUrls() {
  const { useAssetStore } = await import('@/stores/canvasAsset')
  const assetStore = useAssetStore()
  await assetStore.hydrate()
  for (const panel of store.panels) {
    const assetId = panel.content?.assetId
    const url = panel.content?.content
    if (typeof assetId !== 'string' || typeof url !== 'string' || !url.startsWith('blob:')) continue
    const asset = assetStore.getAssetById(assetId)
    if (asset?.url && asset.url !== url) {
      store.updatePanel(panel.id, { content: { content: asset.url } })
    }
  }
}

// 懒迁移：旧 uid 型 assetId 入库为统一资产行并替换为数字 id（幂等，失败下次重试）
async function migrateLegacyAssetIds() {
  const { useAssetStore } = await import('@/stores/canvasAsset')
  const assetStore = useAssetStore()
  for (const panel of store.panels) {
    const assetId = panel.content?.assetId
    if (typeof assetId !== 'string' || !assetId || /^\d+$/.test(assetId)) continue
    const numeric = await assetStore.migrateUidAsset(assetId)
    if (numeric) store.updatePanel(panel.id, { content: { assetId: numeric } })
  }
}

// Ctrl/Cmd+V 粘贴截图或复制的图片，落到当前视口中心（输入框聚焦时不拦截）
function handleCanvasPaste(e: ClipboardEvent) {
  const active = document.activeElement
  if (active instanceof HTMLElement && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.isContentEditable)) return
  const imageFiles: File[] = []
  for (const item of Array.from(e.clipboardData?.items ?? [])) {
    if (item.kind !== 'file' || !item.type.startsWith('image/')) continue
    const file = item.getAsFile()
    if (file) imageFiles.push(file)
  }
  if (imageFiles.length === 0) return
  e.preventDefault()
  const world = store.screenToWorld(window.innerWidth / 2, window.innerHeight / 2)
  createMediaNodesFromFiles(imageFiles, world.x, world.y)
}

// 删除素材：从素材库移除
async function handleDeleteAsset(id: string) {
  if (!id) return
  try {
    const { useAssetStore } = await import('@/stores/canvasAsset')
    const assetStore = useAssetStore()
    await assetStore.removeAsset(id)
    ElMessage.success(t('canvas.messages.assetDeleted'))
  } catch (err) {
    ElMessage.error(`${t('canvas.messages.assetDeleteFailed')}: ${getErrorMessage(err) || err}`)
  }
}

// 素材库上传：将用户选择的文件注册为本地素材
async function handleUploadAssetFiles(files: FileList | File[]) {
  if (!files || files.length === 0) return
  try {
    const { useAssetStore } = await import('@/stores/canvasAsset')
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
        work_id: store.activeWorkspace?.work_id ?? undefined,
      })
      count++
    }
    ElMessage.success(`${t('canvas.messages.nodeCreated')}: ${count}`)
  } catch (err) {
    ElMessage.error(`${t('canvas.messages.uploadFailed')}: ${getErrorMessage(err) || err}`)
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
async function handleClearCanvas() {
  if (store.panels.length === 0) return
  await confirm(t('canvas.messages.canvasCleared'))
  store.pushSnapshot()
  store.clearAllPanels()
  ElMessage.success(t('canvas.messages.canvasCleared'))
}

// 切换图片信息显示
function handleToggleImageInfo(val: boolean) {
  if (val !== store.showImageInfo) store.toggleImageInfo()
}

// 切换「生成后自动放入画布」（Agent 落画布默认行为，随偏好持久化）
function handleToggleAutoPlace(val: boolean) {
  if (val !== store.autoPlaceMedia) store.toggleAutoPlaceMedia()
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

// 在指定世界坐标（节点中心）创建节点；extraContent 由菜单项预填
function createNodeAt(type: string, cx: number, cy: number, extraContent?: Record<string, unknown>) {
  const size = NODE_DEFAULT_SIZES[type as keyof typeof NODE_DEFAULT_SIZES] ?? NODE_DEFAULT_SIZES.text
  store.pushSnapshot()
  // 新增 3 种节点类型使用预设默认 content（spec 5.4.4）
  // 其他类型保持空 content，由用户后续填充
  let initialContent: Record<string, unknown> = {}
  if (type === 'tts') {
    initialContent = {
      voice: 'default',
      speed: 1.0,
      provider: 'agnes-tts',
      from_node: null,
    }
  } else if (type === 'subtitle') {
    initialContent = {
      model: 'agnes-2.0-flash',
      temperature: 0.5,
      from_node: null,
      prompt: '根据上游剧本内容生成 SRT 格式字幕，每条字幕不超过 20 字',
    }
  } else if (type === 'compose') {
    initialContent = {
      from_node: null,
      with_subtitle: true,
      audio_from_node: null,
      subtitle_from_node: null,
    }
  } else if (type === 'script') {
    // 脚本节点：剧情/镜头/资产/生成全部在向导内编辑
    initialContent = {
      story: '',
      shots: [],
      assets: { characters: [], scenes: [] },
    }
  } else if (type === 'table') {
    // 批量创作表：默认 3 行 × 按默认图片模型合同收敛的列数
    initialContent = createBatchContent(useModelsStore().getModelGenParams(useModelsStore().defaultImageModel)?.max_ref_images)
  }
  if (extraContent) initialContent = { ...initialContent, ...extraContent }
  const id = store.addPanel({
    type,
    name: getNodeName(type),
    x: cx - size.width / 2,
    y: cy - size.height / 2,
    width: size.width,
    height: size.height,
    content: initialContent,
  })
  store.selectPanel(id, { append: false })
  return id
}

// 在视口中心创建节点
function createNodeAtCenter(type: string) {
  const cx = (window.innerWidth / 2 - store.viewport.x) / store.viewport.zoom
  const cy = (window.innerHeight / 2 - store.viewport.y) / store.viewport.zoom
  return createNodeAt(type, cx, cy)
}

// ==================== 文件上传 / 导入 ====================

const fileInputRef = ref<HTMLInputElement | null>(null)
const uploadTargetPanelId = ref<string | null>(null)
// 快速创建菜单「上传本地图片」指定的落点（世界坐标，节点中心）；普通上传为 null → 视口中心
const uploadTargetPoint = ref<{ x: number; y: number } | null>(null)
const fileAccept = ref('*')

// 触发文件选择对话框
function triggerFileUpload(panelId: string | null, accept = '*', point?: { x: number; y: number }) {
  uploadTargetPanelId.value = panelId
  uploadTargetPoint.value = point ? { ...point } : null
  fileAccept.value = accept
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
    fileInputRef.value.click()
  }
}

// 文件选择回调
async function handleFileSelect(event: Event) {
  const file = (event.target as HTMLInputElement)?.files?.[0]
  if (!file) return

  // JSON 导入
  if (file.name.endsWith('.json')) {
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        store.importJSON((e.target as FileReader)?.result as string)
        remapAssetUrls()
        ElMessage.success(t('canvas.messages.jsonLoadedToNode'))
      } catch (err) {
        ElMessage.error(`${t('canvas.messages.jsonExported')}: ${getErrorMessage(err)}`)
      }
    }
    reader.readAsText(file)
    return
  }

  const targetId = uploadTargetPanelId.value
  uploadTargetPanelId.value = null
  const uploadPoint = uploadTargetPoint.value
  uploadTargetPoint.value = null

  // 图片/视频先注册进素材库（Blob 持久化到 IndexedDB），节点记录 assetId，刷新后按 id 重建地址
  if (file.type.startsWith('image/') || file.type.startsWith('video/')) {
    const type = file.type.startsWith('image/') ? 'image' : 'video'
    const { useAssetStore } = await import('@/stores/canvasAsset')
    const assetStore = useAssetStore()
    await assetStore.hydrate()
    const asset = await assetStore.registerAsset({ type, blob: file, name: file.name, prompt: '', work_id: store.activeWorkspace?.work_id ?? undefined })
    if (asset) {
      const content = { content: asset.url, status: 'success', bytes: file.size, assetId: asset.id }
      if (targetId) {
        store.pushSnapshot()
        store.updatePanel(targetId, { content })
      } else {
        const id = uploadPoint ? createNodeAt(type, uploadPoint.x, uploadPoint.y) : createNodeAtCenter(type)
        store.updatePanel(id, { content })
      }
      return
    }
  }

  // 音频/其他类型或素材注册失败：退回运行时 object URL（刷新后失效，维持旧行为）
  const url = URL.createObjectURL(file)
  if (targetId) {
    store.pushSnapshot()
    store.updatePanel(targetId, { content: { content: url, status: 'success', bytes: file.size } })
  } else {
    const type = file.type.startsWith('image/') ? 'image'
      : file.type.startsWith('video/') ? 'video'
      : file.type.startsWith('audio/') ? 'audio'
      : 'text'
    const id = uploadPoint ? createNodeAt(type, uploadPoint.x, uploadPoint.y) : createNodeAtCenter(type)
    store.updatePanel(id, { content: { content: url, status: 'success', bytes: file.size } })
  }
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
    else if (selectedGroupId.value) selectedGroupId.value = null
    else store.clearSelection()
    return
  }

  // Delete / Backspace：删除选中分组（仅解散）/ 删除选中节点
  if (event.key === 'Delete' || event.key === 'Backspace') {
    if (selectedGroupId.value) {
      event.preventDefault()
      handleGroupDissolve(selectedGroupId.value)
    } else if (store.selectedPanelIds.length > 0) {
      event.preventDefault()
      handleDeleteSelected()
    }
    return
  }

  // Cmd/Ctrl+G：成组；Cmd/Ctrl+Shift+G：解散组 / 移出分组
  if (ctrl && (event.key === 'g' || event.key === 'G')) {
    event.preventDefault()
    if (event.shiftKey) {
      if (selectedGroupId.value) {
        handleGroupDissolve(selectedGroupId.value)
      } else if (store.selectedPanelIds.length === 1) {
        store.removePanelFromGroup(store.selectedPanelIds[0])
        ElMessage.success(t('canvas.group.removedFromGroup'))
      }
    } else {
      handleContextGroupCreate()
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

  // Ctrl+A：全选（排除折叠分组的隐藏成员）
  if (ctrl && event.key === 'a') {
    event.preventDefault()
    selectAllVisible()
    return
  }

  // Ctrl+S：立即强制保存（云端直推保存队列 / anon 立即落盘）
  if (ctrl && event.key === 's') {
    event.preventDefault()
    flushSaveCanvas()
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

// 切换工作区时恢复该工作区中断的生成任务（含生成中切走又切回的场景）
watch(() => store.activeWorkspaceId, () => {
  resumeLoadingCanvasNodes(store)
  remapAssetUrls()
})

onMounted(async () => {
  // 从 localforage 加载持久化数据
  await store._hydrateFromStorage()
  // 作品名映射（所属作品徽标展示用）
  loadWorksMap()
  // 启动远端 revision 轻轮询（外部宿主增量写入感知：对话 Agent/CLI 落画布等）
  store.startRemotePoll()
  // 画布页激活：统一 Agent 注册 canvas scope（深度工具随注册注入，离开画布页注销）
  chatStore.registerAgentScope({ host: 'canvas' })
  // 刷新后节点里的 blob object URL 已失效，按 assetId 从素材库重建
  await remapAssetUrls()
  // 统一资产层：旧 uid 型 assetId 懒迁移为数字 id（幂等）
  await migrateLegacyAssetIds()
  // 如果没有工作区，创建默认画布
  if (!store.activeWorkspaceId && store.workspaces.length === 0) {
    store.createWorkspace(`${t('canvas.canvas')} 1`)
  }
  // 作品详情「进入画布」跳转：定位指定工作区
  const targetWs = route.query.workspace
  if (typeof targetWs === 'string' && targetWs && store.workspaces.some((w) => w.id === targetWs)) {
    store.switchWorkspace(targetWs)
  }
  // 全局对话列表跳转进入：定位工作区并打开画布 Agent 会话
  await handleSessionJumpQuery()
  // 恢复中断的生成任务：刷新后轮询循环已丢失，按队列任务对账回填 loading 节点
  resumeLoadingCanvasNodes(store)
  // 注册全局事件监听
  window.addEventListener('keydown', handleKeyDown)
  window.addEventListener('keyup', handleKeyUp)
  window.addEventListener('click', handleGlobalClick)
  window.addEventListener('paste', handleCanvasPaste)
  // 监听用户登录/退出，切换画布数据空间
  window.addEventListener('agnes:user-login', handleUserSwitch)
  window.addEventListener('agnes:user-logout', handleUserLogout)
})

onBeforeUnmount(() => {
  // 停止远端 revision 轻轮询；注销画布深度工具 scope
  store.stopRemotePoll()
  chatStore.unregisterAgentScope('canvas')
  // 移除全局事件监听
  window.removeEventListener('keydown', handleKeyDown)
  window.removeEventListener('keyup', handleKeyUp)
  window.removeEventListener('click', handleGlobalClick)
  window.removeEventListener('paste', handleCanvasPaste)
  window.removeEventListener('pointermove', handleSelectionMove)
  window.removeEventListener('pointerup', handleSelectionUp)
  window.removeEventListener('pointermove', handleConnectingMove)
  window.removeEventListener('pointerup', handleConnectingUp)
  window.removeEventListener('pointermove', handleGroupDragMove)
  window.removeEventListener('pointerup', handleGroupDragUp)
  window.removeEventListener('agnes:user-login', handleUserSwitch)
  window.removeEventListener('agnes:user-logout', handleUserLogout)
})

/** 登录/切换用户后，切换到对应的数据空间 */
async function handleUserSwitch(e: Event) {
  const detail = e instanceof CustomEvent ? e.detail : undefined
  const userId: number | null = typeof detail?.id === 'number' ? detail.id : null
  await store._switchUserStorage(userId)
  await remapAssetUrls()
  if (!store.activeWorkspaceId && store.workspaces.length === 0) {
    store.createWorkspace(`${t('canvas.canvas')} 1`)
  }
}

/** 退出登录：切换到匿名数据空间 */
async function handleUserLogout() {
  await store._switchUserStorage(null)
  await remapAssetUrls()
  if (!store.activeWorkspaceId && store.workspaces.length === 0) {
    store.createWorkspace(`${t('canvas.canvas')} 1`)
  }
}
</script>

<style scoped>
/* ==================== 分类分组弹窗 ==================== */
.group-mode-options {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}

.group-mode-preview {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
}
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

/* 层级面包屑：作品 › 画布（作品名可点回详情） */
.crumb-work {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  white-space: nowrap;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.crumb-work:hover {
  color: var(--el-color-primary);
}
.crumb-sep {
  margin: 0 6px;
  color: var(--el-text-color-placeholder);
}

/* 云端同步状态指示器（标题旁，登录态落库后显示） */
.save-status {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}
.save-status-error {
  color: var(--el-color-danger);
}
/* 远端有更新提示：可点击同步 */
.save-status.remote-update {
  color: var(--el-color-warning);
  cursor: pointer;
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

/* ==================== 节点工具栏 ==================== */
.node-toolbar-wrap {
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
  z-index: 10;
}

.preview-close:hover {
  background: rgba(255, 255, 255, 0.25);
}

.preview-download {
  position: absolute;
  top: 16px;
  right: 66px;
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}

.preview-download:hover {
  background: rgba(255, 255, 255, 0.25);
}

/* ==================== 节点信息对话框 ==================== */
.node-info {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 60vh;
  overflow-y: auto;
}

.node-info-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  font-size: 13px;
  line-height: 1.5;
}

.node-info-label {
  flex: none;
  width: 72px;
  color: var(--agnes-text-muted);
  font-size: 12px;
}

.node-info-value {
  flex: 1;
  min-width: 0;
  word-break: break-all;
}

.node-info-id {
  font-family: monospace;
  font-size: 11px;
  color: var(--agnes-text-muted);
}

.node-info-prompt-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.node-info-prompt-text {
  margin-top: 6px;
  padding: 8px 10px;
  background: var(--agnes-bg-inset);
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 180px;
  overflow-y: auto;
}

/* ==================== 隐藏文件输入 ==================== */
.hidden-file-input {
  display: none;
}
</style>
