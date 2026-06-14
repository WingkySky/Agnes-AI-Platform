/* =====================================================
 * 顶部工具栏
 * - 添加面板下拉菜单（7 种类型）
 * - 缩放显示/控制
 * - 撤销/重做按钮
 * - 重置视图
 * ===================================================== */

<template>
  <div class="canvas-toolbar">
    <!-- 左侧：添加面板菜单 -->
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
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import { useI18n } from '@/i18n'
import {
  Plus, ZoomIn, ZoomOut, RefreshLeft, RefreshRight, FullScreen,
} from '@element-plus/icons-vue'

const { t } = useI18n()
const store = useCanvasStore()

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
  // 默认在视口中心位置创建
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
  const centerX = -store.viewport.x / store.viewport.zoom
  const centerY = -store.viewport.y / store.viewport.zoom

  store.addPanel({
    type,
    x: centerX - size.width / 2 + (Math.random() - 0.5) * 40,
    y: centerY - size.height / 2 + (Math.random() - 0.5) * 40,
    width: size.width,
    height: size.height,
    content: {},
    zIndex: (store.panels.length + 1),
  })
}
</script>

<style scoped>
.canvas-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: rgba(15, 22, 38, 0.8);
  border-bottom: 1px solid rgba(100, 150, 220, 0.12);
  backdrop-filter: blur(12px);
  gap: 12px;
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
</style>
