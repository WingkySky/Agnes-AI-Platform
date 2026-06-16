/* =====================================================
 * 顶部工具栏
 * - 鼠标模式切换（选择/平移/连线）
 * - 添加面板下拉菜单（7 种类型）
 * - 搜索框 + 类型筛选下拉（任务 3：节点搜索 / 类型筛选）
 * - 缩放显示/控制（+/- 按钮、缩放滑杆、百分比）
 * - 背景模式切换（点阵 / 网格 / 空白）
 * - 网格吸附开关（按 store.gridSize 自动对齐）
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

    <!-- 搜索 + 类型筛选（任务 3） -->
    <div class="toolbar-search-group">
      <el-tooltip
        :content="t('canvas.toolbar.searchShortcutHint')"
        placement="bottom"
      >
        <el-input
          ref="searchInputRef"
          v-model="searchInputValue"
          class="toolbar-search-input"
          size="small"
          clearable
          :prefix-icon="Search"
          :placeholder="t('canvas.toolbar.searchPlaceholder')"
          @input="onSearchInput"
          @clear="onSearchClear"
          @keyup.enter="onSearchEnter"
          @keyup.esc="onSearchEsc"
        />
      </el-tooltip>

      <el-dropdown trigger="click" @visible-change="onFilterDropdownToggle">
        <span class="filter-trigger-wrap">
          <el-tooltip
            :content="t('canvas.toolbar.filterTypes')"
            placement="bottom"
          >
            <el-button size="small" class="filter-trigger-btn">
              <el-icon><Filter /></el-icon>
              <span
                v-if="store.filterTypes.length > 0"
                class="filter-badge"
              >{{ store.filterTypes.length }}</span>
            </el-button>
          </el-tooltip>
        </span>
        <template #dropdown>
          <div class="filter-dropdown" @click.stop>
            <div class="filter-dropdown-header">
              <span class="filter-dropdown-title">{{ t('canvas.toolbar.filterTypes') }}</span>
              <span class="filter-dropdown-actions">
                <el-button
                  size="small"
                  link
                  type="primary"
                  @click="setAllFilterTypes"
                >{{ t('canvas.toolbar.filterAll') }}</el-button>
                <el-button
                  size="small"
                  link
                  @click="setNoneFilterTypes"
                >{{ t('canvas.toolbar.filterNone') }}</el-button>
              </span>
            </div>
            <el-checkbox-group
              :model-value="store.filterTypes"
              @change="onFilterTypesChange"
              class="filter-checkbox-group"
            >
              <el-checkbox
                v-for="opt in filterTypeOptions"
                :key="opt.value"
                :value="opt.value"
                :label="opt.value"
              >
                {{ opt.label }}
              </el-checkbox>
            </el-checkbox-group>
          </div>
        </template>
      </el-dropdown>
    </div>

    <!-- 中间：缩放控制 -->
    <el-tooltip :content="t('canvas.addFrameHint')" placement="bottom">
      <el-button size="small" plain @click="handleAddFrame">
        <el-icon><Files /></el-icon>
        {{ t('canvas.addFrame') }}
      </el-button>
    </el-tooltip>

    <!-- 已在 Frame 内部时显示"返回上级"按钮 -->
    <el-button v-if="store.enteredFrameId" size="small" plain @click="store.exitFrame()">
      <el-icon><Back /></el-icon>
      {{ t('canvas.backToParent') }}
    </el-button>

    <!-- 中间：缩放控制 -->
    <div class="toolbar-center">
      <el-icon class="zoom-btn" @click="store.zoom(1 / 1.2)">
        <ZoomOut />
      </el-icon>

      <input
        type="range"
        min="0.1"
        max="3"
        step="0.05"
        :value="store.viewport.zoom"
        @input="onZoomSliderInput"
        class="canvas-zoom-slider"
      />

      <span class="zoom-label">{{ zoomPercent }}%</span>

      <el-icon class="zoom-btn" @click="store.zoom(1.2)">
        <ZoomIn />
      </el-icon>
    </div>

    <!-- 背景模式切换：点阵 / 网格 / 空白 -->
    <el-dropdown
      trigger="click"
      @command="(cmd) => store.setBackgroundMode(cmd)"
    >
      <span class="bg-mode-trigger-wrap">
        <el-tooltip :content="t('canvas.backgroundMode')" placement="bottom">
          <el-icon class="tool-btn">
            <Grid />
          </el-icon>
        </el-tooltip>
      </span>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="dot">{{ t('canvas.backgroundDot') }}</el-dropdown-item>
          <el-dropdown-item command="grid">{{ t('canvas.backgroundGrid') }}</el-dropdown-item>
          <el-dropdown-item command="blank">{{ t('canvas.backgroundBlank') }}</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <!-- 网格吸附开关：开启后拖动面板会按 gridSize 自动对齐；按住 Alt 临时关闭吸附 -->
    <el-tooltip :content="t('canvas.toggleGrid')" placement="bottom">
      <el-icon
        class="tool-btn"
        :class="{ active: store.showGrid }"
        @click="store.toggleGrid()"
      >
        <Grid />
      </el-icon>
    </el-tooltip>

    <el-divider direction="vertical" />

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
import { ref, computed, nextTick } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import { useI18n } from '@/i18n'
import {
  Plus, ZoomIn, ZoomOut, RefreshLeft, RefreshRight, FullScreen,
  Pointer, CaretRight, Connection, Upload, Download, Grid, Files, Back,
  Search, Filter,
} from '@element-plus/icons-vue'

const { t } = useI18n()
const store = useCanvasStore()
const emit = defineEmits(['export-json', 'import-json'])

// 搜索输入框内容（与 store.searchQuery 双向同步：清空时保持一致）
const searchInputValue = ref(store.searchQuery)
// 搜索 input 组件 ref（父组件 CanvasView 通过 / 快捷键调 focus）
const searchInputRef = ref(null)

// 类型筛选可选列表（任务 3：8 种类型，包含 frame）
const filterTypeOptions = [
  { value: 'image', label: '图片' },
  { value: 'video', label: '视频' },
  { value: 'text', label: '文本' },
  { value: 'url', label: 'URL' },
  { value: 'quick-generate', label: '快捷生成' },
  { value: 'file-upload', label: '文件上传' },
  { value: 'placeholder', label: '占位' },
  { value: 'frame', label: '分组框' },
]

/**
 * 暴露给父组件：用于全局 / 快捷键聚焦搜索框
 */
defineExpose({
  focusSearch: () => {
    searchInputRef.value?.focus?.()
  },
  /** 清空搜索内容与 store 状态 */
  clearSearch: () => {
    searchInputValue.value = ''
    store.clearSearch()
  },
})

/** 仅用于显示的缩放百分比 */
const zoomPercent = computed(() => Math.round(store.viewport.zoom * 100))

/**
 * 缩放滑杆 input 事件
 * - 拖动期间连续更新 viewport.zoom，但不压入历史栈（避免污染 undo/redo）
 * - 以画布视口中心为缩放中心
 */
function onZoomSliderInput(e) {
  const targetZoom = Number(e.target.value)
  const center = { x: window.innerWidth / 2, y: window.innerHeight / 2 }
  store.setZoom(targetZoom, center)
}

// ========== 任务 3：搜索 & 筛选事件处理 ==========

/**
 * 搜索框实时输入
 * - 仅写入 store.searchQuery，不主动计算匹配（避免高频输入时全量扫描）
 * - searchAndLocate 由回车键触发
 */
function onSearchInput(value) {
  store.setSearchQuery(value)
}

/** 清空按钮 / 清除时同步本地 input 和 store */
function onSearchClear() {
  searchInputValue.value = ''
  store.clearSearch()
}

/**
 * 回车：执行搜索 + 定位第一个匹配
 * - 调 store.searchAndLocate：内部会计算 matchedPanels / centerOnPanel / 高亮到期时间
 * - 找不到时给个轻提示（避免静默失败）
 */
function onSearchEnter() {
  const q = (searchInputValue.value || '').trim()
  if (!q) {
    store.clearSearch()
    return
  }
  store.searchAndLocate(q)
  if (store.matchedPanels.length === 0) {
    // 仅清掉高亮，保留 query 让用户继续编辑
    store.searchHighlightUntil = 0
  }
}

/** Esc：清空搜索 + 失焦 */
function onSearchEsc(e) {
  searchInputValue.value = ''
  store.clearSearch()
  // 让 input 失焦，回退到画布快捷键作用域
  e?.target?.blur?.()
  searchInputRef.value?.blur?.()
}

/** 类型筛选 checkbox 组变更 */
function onFilterTypesChange(values) {
  // el-checkbox-group 在 v-model 写法下也会传数组；为空时清空 store
  store.setFilterTypes(Array.isArray(values) ? values : [])
}

/** 全选：把 8 种类型全勾上 */
function setAllFilterTypes() {
  store.setFilterTypes(filterTypeOptions.map((o) => o.value))
}

/** 全不选：清空筛选（store 内部 [] 表示显示全部） */
function setNoneFilterTypes() {
  store.setFilterTypes([])
}

/** 筛选下拉打开/关闭：保留 hook 以便未来扩展（如打开时刷新） */
function onFilterDropdownToggle(visible) {
  if (visible) {
    nextTick(() => {
      // 预留：可在此处聚焦第一个 checkbox
    })
  }
}

const panelTypes = [
  { value: 'image', label: '图片预览' },
  { value: 'video', label: '视频预览' },
  { value: 'text', label: '文本笔记' },
  { value: 'url', label: 'URL 链接' },
  { value: 'quick-generate', label: '快捷生成' },
  { value: 'file-upload', label: '文件上传' },
  { value: 'placeholder', label: '占位面板' },
  // 任务 8：配置节点（驱动批量生图）
  { value: 'config', label: '配置节点' },
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
    // 任务 8：config 节点的默认尺寸与 store.addConfigNode 保持一致
    config: { width: 240, height: 180 },
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

  // 任务 8：config 节点走 store.addConfigNode 自带的默认 content（model/size/count/batchMode）
  if (type === 'config') {
    store.addConfigNode({ x: finalX, y: finalY })
    return
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

/**
 * 添加 Frame 分组框（任务 5）
 * - 以当前视口可见区域中心为锚点，扣除左侧栏 (220px) 和顶部工具栏 (48px)
 * - 默认 600x400 尺寸；createFrame 会自动收编中心点在框内的非 frame 节点
 */
function handleAddFrame() {
  const sidebarWidth = 220
  const viewWidth = window.innerWidth - sidebarWidth
  const viewHeight = window.innerHeight - 48
  const centerX = -store.viewport.x / store.viewport.zoom + viewWidth / store.viewport.zoom / 2
  const centerY = -store.viewport.y / store.viewport.zoom + viewHeight / store.viewport.zoom / 2
  const width = 600
  const height = 400
  store.createFrame({
    x: centerX - width / 2,
    y: centerY - height / 2,
    width,
    height,
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

.canvas-zoom-slider {
  /* 扁平无边框、融入工具栏背景，仅保留轻微 hover 反馈 */
  -webkit-appearance: none;
  appearance: none;
  width: 140px;
  height: 4px;
  background: rgba(139, 163, 201, 0.2);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
  margin: 0 4px;
  transition: background 0.15s;
}

.canvas-zoom-slider:hover {
  background: rgba(139, 163, 201, 0.32);
}

/* WebKit 滑块（Chrome / Edge / Safari） */
.canvas-zoom-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #508cff;
  border: none;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
}

.canvas-zoom-slider:hover::-webkit-slider-thumb {
  transform: scale(1.15);
  box-shadow: 0 0 0 4px rgba(80, 140, 255, 0.18);
}

/* Firefox 滑块 */
.canvas-zoom-slider::-moz-range-thumb {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #508cff;
  border: none;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
}

.canvas-zoom-slider:hover::-moz-range-thumb {
  transform: scale(1.15);
  box-shadow: 0 0 0 4px rgba(80, 140, 255, 0.18);
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
  transition: color 0.15s, background 0.15s;
}

.tool-btn:hover:not(.disabled) {
  color: #a0d4ff;
}

.tool-btn.active {
  /* 网格吸附等可切换按钮的高亮态：与 .mode-btn.active 保持一致 */
  color: #508cff;
  background: rgba(80, 140, 255, 0.15);
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

/* ========== 任务 3：搜索 + 类型筛选样式 ========== */

.toolbar-search-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* 搜索 input：扁平深色背景，融入工具栏，无强圆角 */
.toolbar-search-input {
  width: 220px;
}

.toolbar-search-input :deep(.el-input__wrapper) {
  background: var(--canvas-panel-bg, rgba(22, 32, 54, 0.7));
  box-shadow: 0 0 0 1px rgba(100, 150, 220, 0.12) inset;
  border-radius: 4px;
}

.toolbar-search-input :deep(.el-input__wrapper):hover {
  box-shadow: 0 0 0 1px rgba(100, 150, 220, 0.24) inset;
}

.toolbar-search-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px rgba(80, 140, 255, 0.55) inset;
}

.toolbar-search-input :deep(.el-input__inner) {
  color: #e6efff;
  font-size: 12px;
}

.toolbar-search-input :deep(.el-input__inner::placeholder) {
  color: #6b84aa;
}

.toolbar-search-input :deep(.el-input__prefix .el-icon),
.toolbar-search-input :deep(.el-input__suffix .el-icon) {
  color: #6b84aa;
}

/* el-dropdown 默认 slot 只能接受一个 element 节点，把 el-tooltip 用 span 包一层以满足约束 */
.filter-trigger-wrap,
.bg-mode-trigger-wrap {
  display: inline-flex;
  align-items: center;
}

/* 筛选触发按钮：扁平无边框，融入工具栏 */
.filter-trigger-btn {
  position: relative;
  background: transparent !important;
  border: 1px solid rgba(100, 150, 220, 0.12) !important;
  color: #8ba3c9 !important;
  padding: 4px 8px !important;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.filter-trigger-btn:hover {
  color: #a0d4ff !important;
  border-color: rgba(80, 140, 255, 0.35) !important;
  background: rgba(80, 140, 255, 0.08) !important;
}

/* 筛选角标：已选类型数量 */
.filter-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  font-size: 10px;
  line-height: 1;
  border-radius: 8px;
  background: #508cff;
  color: #fff;
  margin-left: 2px;
}

/* 类型筛选下拉内容：暗色面板风格 */
.filter-dropdown {
  width: 220px;
  padding: 8px 10px 10px;
  background: rgba(15, 22, 38, 0.95);
  border: 1px solid rgba(100, 150, 220, 0.18);
  border-radius: 6px;
  color: #cfd8e8;
}

.filter-dropdown-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(100, 150, 220, 0.1);
}

.filter-dropdown-title {
  font-size: 12px;
  color: #8ba3c9;
}

.filter-dropdown-actions {
  display: inline-flex;
  gap: 4px;
}

.filter-dropdown-actions :deep(.el-button) {
  font-size: 11px;
  padding: 0 4px;
}

.filter-checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.filter-checkbox-group :deep(.el-checkbox) {
  height: auto;
  margin-right: 0;
  white-space: nowrap;
  color: #cfd8e8;
  font-size: 12px;
}

.filter-checkbox-group :deep(.el-checkbox__label) {
  color: #cfd8e8;
  font-size: 12px;
}
</style>
