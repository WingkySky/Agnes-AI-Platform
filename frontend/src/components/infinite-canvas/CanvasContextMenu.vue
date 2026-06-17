/* =====================================================
 * 右键上下文菜单
 * - 监听画布区域右键事件
 * - 根据点击目标（面板/连线/背景）渲染不同菜单
 * - 面板菜单按 panel.type 显示节点级操作（编辑/裁剪/分割/旋转/反推/改写/字号/生成/提取首帧/锁定等）
 * - 背景菜单支持粘贴（基于 store clipboard）
 * - 通过 emit('panel-action', { type, panel }) 把节点级操作抛给 CanvasView 集中处理
 * ===================================================== */

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="context-menu"
      :style="{ left: `${x}px`, top: `${y}px` }"
      @pointerdown.stop
    >
      <!-- 面板右键菜单 -->
      <template v-if="target === 'panel'">
        <!-- 通用：编辑 / 复制 / 删除 / 选中 -->
        <div class="context-menu-item" @click="handleAction('edit')">
          <el-icon><Edit /></el-icon>
          {{ t('canvas.toolbar.edit') }}
        </div>
        <div class="context-menu-item" @click="handleAction('copy')">
          <el-icon><CopyDocument /></el-icon>
          {{ t('canvas.copyPanel') }}
        </div>
        <div class="context-menu-item" @click="handleAction('duplicate')">
          <el-icon><CopyDocument /></el-icon>
          {{ t('canvas.toolbar.duplicate') }}
        </div>
        <div class="context-menu-item context-menu-item--danger" @click="handleAction('delete')">
          <el-icon><Delete /></el-icon>
          {{ t('canvas.deletePanel') }}
        </div>
        <div class="context-menu-item" @click="handleAction('select')">
          <el-icon><Select /></el-icon>
          {{ t('canvas.selectPanel') }}
        </div>

        <!-- 锁定/解锁：根据当前锁定状态切换文案 -->
        <div class="context-menu-divider" />
        <div class="context-menu-item context-menu-item--lock" @click="handleAction('toggleLock')">
          <el-icon><component :is="isPanelLocked ? 'Unlock' : 'Lock'" /></el-icon>
          {{ isPanelLocked ? t('canvas.toolbar.unlock') : t('canvas.toolbar.lock') }}
        </div>

        <!-- 节点级操作：仅未锁定时显示 -->
        <template v-if="!isPanelLocked">
          <!-- 图片节点：裁剪 / 分割 / 旋转 / 反推提示词 / 加入素材库 -->
          <template v-if="panelType === 'image'">
            <div class="context-menu-divider" />
            <div class="context-menu-item" @click="handleAction('crop')">
              <el-icon><Crop /></el-icon>
              {{ t('canvas.toolbar.crop') }}
            </div>
            <div class="context-menu-item" @click="handleAction('split')">
              <el-icon><CopyDocument /></el-icon>
              {{ t('canvas.toolbar.split') }}
            </div>
            <div class="context-menu-item" @click="handleAction('rotate')">
              <el-icon><RefreshRight /></el-icon>
              {{ t('canvas.toolbar.rotate') }}
            </div>
            <div class="context-menu-item" @click="handleAction('inferPrompt')">
              <el-icon><MagicStick /></el-icon>
              {{ t('canvas.toolbar.inferPrompt') }}
            </div>
            <div class="context-menu-item" @click="handleAction('addToAssets')">
              <el-icon><FolderAdd /></el-icon>
              {{ t('canvas.toolbar.addToAssets') }}
            </div>
          </template>

          <!-- 文本节点：改写 / 字号+ / 字号- -->
          <template v-else-if="panelType === 'text'">
            <div class="context-menu-divider" />
            <div class="context-menu-item" @click="handleAction('rewrite')">
              <el-icon><Refresh /></el-icon>
              {{ t('canvas.toolbar.rewrite') }}
            </div>
            <div class="context-menu-item" @click="handleAction('fontUp')">
              <el-icon><Plus /></el-icon>
              {{ t('canvas.toolbar.fontUp') }}
            </div>
            <div class="context-menu-item" @click="handleAction('fontDown')">
              <el-icon><Minus /></el-icon>
              {{ t('canvas.toolbar.fontDown') }}
            </div>
          </template>

          <!-- 视频节点：提取首帧 / 反推提示词 / 查看信息 -->
          <template v-else-if="panelType === 'video'">
            <div class="context-menu-divider" />
            <div class="context-menu-item" @click="handleAction('extractFirstFrame')">
              <el-icon><PictureFilled /></el-icon>
              {{ t('canvas.toolbar.extractFirstFrame') }}
            </div>
            <div class="context-menu-item" @click="handleAction('inferPrompt')">
              <el-icon><MagicStick /></el-icon>
              {{ t('canvas.toolbar.inferPrompt') }}
            </div>
            <div class="context-menu-item" @click="handleAction('info')">
              <el-icon><InfoFilled /></el-icon>
              {{ t('canvas.toolbar.info') }}
            </div>
          </template>

          <!-- 快捷生成节点：生图 / 生视频 -->
          <template v-else-if="panelType === 'quick-generate'">
            <div class="context-menu-divider" />
            <div class="context-menu-item" @click="handleAction('generate')">
              <el-icon><Picture /></el-icon>
              {{ t('canvas.toolbar.generate') }}
            </div>
            <div class="context-menu-item" @click="handleAction('generateVideo')">
              <el-icon><VideoCamera /></el-icon>
              {{ t('canvas.toolbar.generateVideo') }}
            </div>
          </template>

          <!-- 文件上传节点：重新上传 -->
          <template v-else-if="panelType === 'file-upload'">
            <div class="context-menu-divider" />
            <div class="context-menu-item" @click="handleAction('upload')">
              <el-icon><Upload /></el-icon>
              {{ t('canvas.toolbar.upload') }}
            </div>
          </template>
        </template>
      </template>

      <!-- 连线右键菜单 -->
      <template v-if="target === 'connection'">
        <div class="context-menu-item" @click="handleAction('delete')">
          <el-icon><Delete /></el-icon>
          {{ t('canvas.deleteConnection') }}
        </div>
        <div class="context-menu-item" @click="handleAction('disconnect')">
          <el-icon><CloseBold /></el-icon>
          {{ t('canvas.disconnect') }}
        </div>
      </template>

      <!-- 背景右键菜单 -->
      <template v-if="target === 'background'">
        <div class="context-menu-item" @click="handleAction('selectAll')">
          <el-icon><Select /></el-icon>
          {{ t('canvas.selectAll') }}
        </div>
        <!-- 粘贴：基于 store clipboard，无内容时禁用 -->
        <div
          class="context-menu-item"
          :class="{ 'context-menu-item--disabled': !hasClipboard }"
          @click="hasClipboard && handleAction('paste')"
        >
          <el-icon><DocumentCopy /></el-icon>
          {{ t('canvas.paste') }}
        </div>
        <div class="context-menu-divider" />
        <div class="context-menu-item" @click="handleAction('centerView')">
          <el-icon><FullScreen /></el-icon>
          {{ t('canvas.centerView') }}
        </div>
        <div class="context-menu-item context-menu-item--danger" @click="handleAction('clearCanvas')">
          <el-icon><Delete /></el-icon>
          {{ t('canvas.clearCanvas') }}
        </div>
      </template>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import { useI18n } from '@/i18n'
import {
  Edit, CopyDocument, Delete, Select, Lock, Unlock, CloseBold, DocumentCopy, FullScreen,
  Crop, RefreshRight, MagicStick, FolderAdd, Refresh, Plus, Minus, PictureFilled,
  InfoFilled, Picture, VideoCamera, Upload,
} from '@element-plus/icons-vue'

const { t } = useI18n()
const store = useCanvasStore()

const visible = ref(false)
const x = ref(0)
const y = ref(0)
const target = ref('background') // 'panel' | 'connection' | 'background'
const contextData = ref({})

/** 显示菜单 */
function show(event, data) {
  visible.value = true
  x.value = event.clientX
  y.value = event.clientY
  target.value = data.target
  contextData.value = data.data || {}

  // 确保菜单位置不超出视口
  requestAnimationFrame(() => {
    const menu = document.querySelector('.context-menu')
    if (!menu) return
    const rect = menu.getBoundingClientRect()
    if (rect.right > window.innerWidth) {
      x.value = window.innerWidth - rect.width - 4
    }
    if (rect.bottom > window.innerHeight) {
      y.value = window.innerHeight - rect.height - 4
    }
  })
}

/** 隐藏菜单 */
function hide() {
  visible.value = false
}

/** 当前面板对象（来自 contextData.panel） */
const currentPanel = computed(() => contextData.value.panel || null)
/** 当前面板类型 */
const panelType = computed(() => currentPanel.value?.type || '')
/** 当前面板是否已锁定 */
const isPanelLocked = computed(() => !!currentPanel.value?.content?.locked)
/** store 剪贴板是否有内容（用于背景菜单的粘贴项） */
const hasClipboard = computed(() => Array.isArray(store.clipboard) && store.clipboard.length > 0)

/** 处理菜单动作 */
function handleAction(action) {
  hide()

  const panelId = contextData.value.panelId
  const connectionId = contextData.value.connectionId
  const panel = currentPanel.value

  switch (action) {
    case 'edit':
      // 节点编辑：抛给 CanvasView 接入编辑弹窗
      emit('panel-action', { type: 'edit', panel })
      break
    case 'copy':
      // 复制到剪贴板（不立即创建新面板，paste 时才创建）
      if (panelId) store.copyToClipboard(panelId)
      break
    case 'duplicate':
      // 直接复制一份（原地偏移 20px）
      if (panelId) store.duplicatePanel(panelId)
      break
    case 'delete':
      if (panelId) store.deletePanel(panelId)
      else if (connectionId) store.deleteConnection(connectionId)
      break
    case 'select':
      if (panelId) store.selectPanel(panelId)
      break
    case 'toggleLock':
      // 接入 store.toggleLock（已实现）
      if (panelId) store.toggleLock(panelId)
      break
    case 'disconnect':
      if (connectionId) store.deleteConnection(connectionId)
      break
    case 'selectAll':
      if (store.panels.length > 0) store.selectPanel(store.panels[0].id)
      break
    case 'paste':
      // 粘贴：在右键位置（屏幕坐标）创建副本
      store.pastePanel(x.value, y.value)
      break
    case 'centerView':
      store.resetView()
      break
    case 'clearCanvas':
      if (store.panels.length > 0) {
        // 用 store action 一次性清空（只压一次快照，避免历史栈被污染）
        store.clearAllPanels()
      }
      break
    // 节点级操作：裁剪/分割/旋转/反推/改写/字号/生成/提取首帧/加入素材/上传
    // 统一抛给 CanvasView 处理（涉及弹窗或 API 调用）
    case 'crop':
    case 'split':
    case 'rotate':
    case 'inferPrompt':
    case 'addToAssets':
    case 'rewrite':
    case 'fontUp':
    case 'fontDown':
    case 'extractFirstFrame':
    case 'info':
    case 'generate':
    case 'generateVideo':
    case 'upload':
      emit('panel-action', { type: action, panel })
      break
  }
}

const emit = defineEmits(['panel-action'])

defineExpose({ show, hide })
</script>

<style scoped>
.context-menu {
  position: fixed;
  z-index: 10000;
  min-width: 180px;
  background: rgba(20, 30, 50, 0.95);
  border: 1px solid rgba(100, 150, 220, 0.2);
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(12px);
  padding: 4px 0;
  user-select: none;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 13px;
  color: #8ba3c9;
  cursor: pointer;
  transition: all 0.1s;
}

.context-menu-item:hover:not(.context-menu-item--disabled) {
  background: rgba(80, 140, 255, 0.15);
  color: #a0d4ff;
}

.context-menu-item.context-menu-item--danger:hover {
  background: rgba(255, 77, 79, 0.15);
  color: #ff6b6b;
}

.context-menu-item.context-menu-item--lock:hover {
  background: rgba(255, 193, 7, 0.15);
  color: #ffc107;
}

.context-menu-item--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.context-menu-divider {
  height: 1px;
  margin: 4px 0;
  background: rgba(100, 150, 220, 0.1);
}
</style>
