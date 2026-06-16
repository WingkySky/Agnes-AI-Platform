/* =====================================================
 * 顶部工具栏
 * - 鼠标模式切换（选择/平移/连线）
 * - 添加面板下拉菜单（7 种类型）
 * - 缩放显示/控制
 * - 撤销/重做按钮
 * - 重置视图
 * ===================================================== */

<template>
  <div class="canvas-toolbar">
    <!-- 左侧：鼠标模式切换 -->
    <div class="toolbar-left">
      <el-tooltip :content="t('canvas.modeSelect')" placement="bottom">
        <el-icon
          class="mode-btn"
          :class="{ active: store.mouseMode === 'select' }"
          @click="store.setMouseMode('select')"
        >
          <Pointer />
        </el-icon>
      </el-tooltip>
      <el-tooltip :content="t('canvas.modePan')" placement="bottom">
        <el-icon
          class="mode-btn"
          :class="{ active: store.mouseMode === 'pan' }"
          @click="store.setMouseMode('pan')"
        >
          <CaretRight />
        </el-icon>
      </el-tooltip>
      <el-tooltip :content="t('canvas.modeConnect')" placement="bottom">
        <el-icon
          class="mode-btn"
          :class="{ active: store.mouseMode === 'connect' }"
          @click="store.setMouseMode('connect')"
        >
          <Connection />
        </el-icon>
      </el-tooltip>
      <el-divider direction="vertical" />
    </div>

    <!-- 左中：添加面板菜单 -->
    <el-dropdown trigger="click" @command="handleAddPanel">
      <el-button size="small" type="primary" plain>
        <el-icon><Plus /></el-icon>
        {{ t('canvas.addPanel') }}
      </el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-for="opt in panelTypes"
            :key="opt.value"
            :command="opt.value"
          >
            {{ opt.label }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <!-- 中间：缩放控制 -->
    <div class="toolbar-center">
      <el-icon class="zoom-btn" @click="store.zoom(1 / 1.2)">
        <ZoomOut />
      </el-icon>

      <el-slider
        v-model="zoomPercent"
        :min="10"
        :max="300"
        :step="5"
        :show-tooltip="false"
        class="zoom-slider"
      />

      <span class="zoom-label">{{ zoomPercent }}%</span>

      <el-icon class="zoom-btn" @click="store.zoom(1.2)">
        <ZoomIn />
      </el-icon>
    </div>

    <!-- 右侧：操作按钮 -->
    <div class="toolbar-right">
      <el-tooltip :content="t('canvas.importJson')" placement="bottom">
        <el-icon class="tool-btn" @click="emit('import-json')">
          <Upload />
        </el-icon>
      </el-tooltip>

      <el-tooltip :content="t('canvas.exportJson')" placement="bottom">
        <el-icon class="tool-btn" @click="emit('export-json')">
          <Download />
        </el-icon>
      </el-tooltip>

      <el-divider direction="vertical" />

      <el-tooltip :content="t('canvas.undo')" placement="bottom">
        <el-icon
          class="tool-btn"
          :class="{ disabled: store.history.past.length === 0 }"
          @click="store.undo()"
        >
          <RefreshLeft />
        </el-icon>
      </el-tooltip>

      <el-tooltip :content="t('canvas.redo')" placement="bottom">
        <el-icon
          class="tool-btn"
          :class="{ disabled: store.history.future.length === 0 }"
          @click="store.redo()"
        >
          <RefreshRight />
        </el-icon>
      </el-tooltip>

      <el-divider direction="vertical" />

      <el-tooltip :content="t('canvas.resetView')" placement="bottom">
        <el-icon class="tool-btn" @click="store.resetView()">
          <FullScreen />
        </el-icon>
      </el-tooltip>

      <span class="panel-count">{{ store.panels.length }} {{ t('canvas.panels') }}</span>
    </div>

    <!-- 交互提示徽章（pan 模式 / Space 键时显示） -->
    <div v-if="store.mouseMode === 'pan'" class="mode-badge pan-badge">
      <el-icon><CaretRight /></el-icon>
      {{ t('canvas.panModeHint') }}
    </div>
    <div v-else-if="store.mouseMode === 'connect'" class="mode-badge connect-badge">
      <el-icon><Connection /></el-icon>
      {{ t('canvas.connectModeHint') }}
    </div>
    <div v-else-if="store._isSpacePressed" class="mode-badge space-badge">
      <el-icon><CaretRight /></el-icon>
      {{ t('canvas.spacePanningHint') }}
    </div>
    <div v-else class="mode-badge hint-badge">
      <el-icon><Pointer /></el-icon>
      {{ t('canvas.interactionHint') }}
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import { useI18n } from '@/i18n'
import {
  Plus, ZoomIn, ZoomOut, RefreshLeft, RefreshRight, FullScreen,
  Pointer, CaretRight, Connection, Upload, Download,
} from '@element-plus/icons-vue'

const { t } = useI18n()
const store = useCanvasStore()
const emit = defineEmits(['export-json', 'import-json'])

const zoomPercent = computed({
  get: () => Math.round(store.viewport.zoom * 100),
  set: (val) => {
    store.zoom(val / 100 / store.viewport.zoom)
  },
})

const panelTypes = [
  { value: 'image', label: '图片预览' },
  { value: 'video', label: '视频预览' },
  { value: 'text', label: '文本笔记' },
  { value: 'url', label: 'URL 链接' },
  { value: 'quick-generate', label: '快捷生成' },
  { value: 'file-upload', label: '文件上传' },
  { value: 'placeholder', label: '占位面板' },
]

function handleAddPanel(type) {
  const defaultSizes = {
    image: { width: 400, height: 300 },
    video: { width: 560, height: 315 },
    text: { width: 300, height: 200 },
    url: { width: 400, height: 300 },
    'quick-generate': { width: 350, height: 200 },
    'file-upload': { width: 350, height: 250 },
    placeholder: { width: 200, height: 150 },
  }

  const size = defaultSizes[type] || { width: 300, height: 200 }

  // 以视口可见区域中心为基准（扣除左侧栏 220px 宽度 + 顶部工具栏 48px）
  const sidebarWidth = 220
  const viewWidth = window.innerWidth - sidebarWidth
  const viewHeight = window.innerHeight - 48

  const centerX = -store.viewport.x / store.viewport.zoom + viewWidth / store.viewport.zoom / 2
  const centerY = -store.viewport.y / store.viewport.zoom + viewHeight / store.viewport.zoom / 2

  // 修复：基于已存在面板数量做阶梯式偏移，避免完全叠放
  // 每多一个面板，偏移 30px（对角线方向），形成瀑布流
  const offset = store.panels.length * 30
  const offsetX = (offset % 300) - 150  // 在 -150 ~ 150 之间循环
  const offsetY = Math.floor(offset / 300) * 30  // 每 10 个换行

  // 检查与最后一个面板位置的距离，太近则继续偏移
  let finalX = centerX - size.width / 2 + offsetX
  let finalY = centerY - size.height / 2 + offsetY

  if (store.panels.length > 0) {
    const lastPanel = store.panels[store.panels.length - 1]
    const dx = Math.abs(finalX - lastPanel.x)
    const dy = Math.abs(finalY - lastPanel.y)
    if (dx < 50 && dy < 50) {
      // 太近，强制偏移到 60px 之外
      finalX = lastPanel.x + 60
      finalY = lastPanel.y + 60
    }
  }

  store.addPanel({
    type,
    x: finalX,
    y: finalY,
    width: size.width,
    height: size.height,
    content: {},
    zIndex: (store.panels.length + 1),
  })
}
</script>

<style scoped>
.canvas-toolbar {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: rgba(15, 22, 38, 0.8);
  border-bottom: 1px solid rgba(100, 150, 220, 0.12);
  backdrop-filter: blur(12px);
  gap: 12px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 4px;
}

.mode-btn {
  font-size: 16px;
  color: #6b84aa;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.15s;
}

.mode-btn:hover {
  color: #a0d4ff;
  background: rgba(80, 140, 255, 0.1);
}

.mode-btn.active {
  color: #508cff;
  background: rgba(80, 140, 255, 0.15);
}

.toolbar-center {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  max-width: 400px;
  justify-content: center;
}

.zoom-slider {
  width: 120px;
}

:deep(.el-slider__button) {
  background: #508cff;
}

:deep(.el-slider__bar) {
  background: rgba(80, 140, 255, 0.25);
}

.zoom-label {
  font-size: 12px;
  color: #8ba3c9;
  min-width: 36px;
  text-align: center;
}

.zoom-btn {
  font-size: 16px;
  color: #8ba3c9;
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  transition: color 0.15s;
}

.zoom-btn:hover {
  color: #a0d4ff;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tool-btn {
  font-size: 16px;
  color: #8ba3c9;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: color 0.15s;
}

.tool-btn:hover:not(.disabled) {
  color: #a0d4ff;
}

.tool-btn.disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.panel-count {
  font-size: 12px;
  color: #6b84aa;
  margin-left: 6px;
}

/* 交互提示徽章 */
.mode-badge {
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  margin-top: 4px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 11px;
  border-radius: 12px;
  background: rgba(15, 22, 38, 0.85);
  border: 1px solid rgba(100, 150, 220, 0.18);
  color: #8ba3c9;
  pointer-events: none;
  white-space: nowrap;
  backdrop-filter: blur(8px);
  z-index: 10;
}

.mode-badge .el-icon {
  font-size: 12px;
}

.pan-badge {
  background: rgba(80, 140, 255, 0.15);
  border-color: rgba(80, 140, 255, 0.4);
  color: #a0d4ff;
}

.connect-badge {
  background: rgba(160, 120, 255, 0.15);
  border-color: rgba(160, 120, 255, 0.4);
  color: #d4b6ff;
  max-width: 90%;
  text-align: center;
  line-height: 1.4;
  padding: 6px 14px;
}

.space-badge {
  background: rgba(160, 120, 255, 0.15);
  border-color: rgba(160, 120, 255, 0.4);
  color: #d4b6ff;
}

.hint-badge {
  opacity: 0.7;
}
</style>
