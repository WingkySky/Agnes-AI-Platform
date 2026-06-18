<!-- =====================================================
     CanvasToolbar 顶部工具栏（高度 44px）
     - 左侧：撤销 / 重做 / 重置视图
     - 中间：搜索框（Enter 触发 searchAndLocate）+ 类型筛选（多选）
     - 右侧：背景模式切换 / 缩放显示与按钮 / 导出 / 导入
     - defineExpose: focusSearch() 供父组件 / 快捷键聚焦搜索框
     - 对外 emit: export-json / import-json
     ===================================================== -->

<template>
  <div class="canvas-toolbar">
    <!-- 左侧：撤销 / 重做 / 重置视图 -->
    <div class="toolbar-left">
      <button
        class="tool-btn"
        :disabled="store.history.past.length === 0"
        :title="t('canvas.undo')"
        @click="store.undo()"
      >
        <el-icon><RefreshLeft /></el-icon>
      </button>
      <button
        class="tool-btn"
        :disabled="store.history.future.length === 0"
        :title="t('canvas.redo')"
        @click="store.redo()"
      >
        <el-icon><RefreshRight /></el-icon>
      </button>
      <button
        class="tool-btn"
        :title="t('canvas.resetView')"
        @click="store.resetView()"
      >
        <el-icon><Aim /></el-icon>
      </button>
    </div>

    <!-- 中间：搜索框 + 类型筛选 -->
    <div class="toolbar-center">
      <!-- 搜索框：Enter 触发 searchAndLocate -->
      <el-input
        ref="searchInputRef"
        v-model="searchQueryModel"
        size="small"
        class="search-input"
        :placeholder="t('canvas.toolbar.searchPlaceholder')"
        @keyup.enter="handleSearchEnter"
      >
        <template #prefix>
          <el-icon class="search-icon"><Search /></el-icon>
        </template>
        <template #suffix>
          <span class="shortcut-hint">{{ t('canvas.toolbar.searchShortcutHint') }}</span>
        </template>
      </el-input>

      <!-- 类型筛选（多选） -->
      <el-select
        v-model="filterTypesModel"
        multiple
        collapse-tags
        collapse-tags-tooltip
        size="small"
        class="filter-select"
        :placeholder="t('canvas.toolbar.filterTypes')"
      >
        <el-option
          v-for="opt in filterOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
    </div>

    <!-- 右侧：背景模式 / 导出 / 导入 -->
    <div class="toolbar-right">
      <!-- 背景模式切换 -->
      <div class="bg-mode-group">
        <button
          v-for="mode in bgModes"
          :key="mode.value"
          class="bg-mode-btn"
          :class="{ active: store.backgroundMode === mode.value }"
          :title="mode.title"
          @click="store.setBackgroundMode(mode.value)"
        >
          <span class="bg-mode-icon" v-html="mode.icon"></span>
        </button>
      </div>

      <!-- 分隔线 -->
      <span class="toolbar-divider"></span>

      <!-- 导出 / 导入 -->
      <button class="tool-btn" :title="t('canvas.exportJson')" @click="emit('export-json')">
        <el-icon><Download /></el-icon>
      </button>
      <button class="tool-btn" :title="t('canvas.importJson')" @click="emit('import-json')">
        <el-icon><Upload /></el-icon>
      </button>
    </div>
  </div>
</template>

<script setup>
// ------ 模块依赖 ------
import { ref, computed } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import { useI18n } from '@/i18n'

const store = useCanvasStore()
const { t } = useI18n()

// ------ emit 声明 ------
const emit = defineEmits(['export-json', 'import-json'])

// ------ 搜索框 ref（供 defineExpose 聚焦） ------
const searchInputRef = ref(null)

// ------ 搜索关键字双向绑定：读 store.searchQuery，写 store.setSearchQuery ------
const searchQueryModel = computed({
  get: () => store.searchQuery,
  set: (val) => store.setSearchQuery(val),
})

// ------ 类型筛选双向绑定 ------
const filterTypesModel = computed({
  get: () => store.filterTypes,
  set: (val) => store.setFilterTypes(val),
})

// ------ 类型筛选选项 ------
const filterOptions = [
  { value: 'image', label: '图片' },
  { value: 'video', label: '视频' },
  { value: 'text', label: '文本' },
  { value: 'config', label: '配置' },
  { value: 'frame', label: '分组' },
]

// ------ 背景模式选项（内联 SVG 图标） ------
const bgModes = [
  {
    value: 'dot',
    title: t('canvas.backgroundDot'),
    icon: '<svg width="14" height="14" viewBox="0 0 14 14"><circle cx="3" cy="3" r="1" fill="currentColor"/><circle cx="7" cy="3" r="1" fill="currentColor"/><circle cx="11" cy="3" r="1" fill="currentColor"/><circle cx="3" cy="7" r="1" fill="currentColor"/><circle cx="7" cy="7" r="1" fill="currentColor"/><circle cx="11" cy="7" r="1" fill="currentColor"/><circle cx="3" cy="11" r="1" fill="currentColor"/><circle cx="7" cy="11" r="1" fill="currentColor"/><circle cx="11" cy="11" r="1" fill="currentColor"/></svg>',
  },
  {
    value: 'grid',
    title: t('canvas.backgroundGrid'),
    icon: '<svg width="14" height="14" viewBox="0 0 14 14"><path d="M5 1v12M9 1v12M1 5h12M1 9h12" stroke="currentColor" stroke-width="1" fill="none"/></svg>',
  },
  {
    value: 'blank',
    title: t('canvas.backgroundBlank'),
    icon: '<svg width="14" height="14" viewBox="0 0 14 14"><rect x="1" y="1" width="12" height="12" rx="2" stroke="currentColor" stroke-width="1" fill="none"/></svg>',
  },
]

// ------ 搜索 Enter 处理 ------
function handleSearchEnter() {
  if (searchQueryModel.value.trim()) {
    store.searchAndLocate(searchQueryModel.value)
  }
}

// ------ 暴露 focusSearch 方法供父组件调用 ------
function focusSearch() {
  searchInputRef.value?.focus()
}

defineExpose({ focusSearch })
</script>

<style scoped>
/* 工具栏容器：44px 高，三段式 flex 布局 */
.canvas-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 44px;
  padding: 0 12px;
  gap: 12px;
  background: var(--canvas-panel-bg);
  border-bottom: 1px solid var(--canvas-node-border);
  backdrop-filter: blur(12px);
  user-select: none;
  flex-shrink: 0;
}

/* 左 / 右侧区域 */
.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 2px;
}

/* 中间区域：搜索 + 筛选 */
.toolbar-center {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  justify-content: center;
  max-width: 520px;
}

/* 极简扁平工具按钮 */
.tool-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--canvas-node-muted-text);
  cursor: pointer;
  font-size: 16px;
  transition: all 0.15s ease;
}

.tool-btn:hover:not(:disabled) {
  background: var(--canvas-node-border);
  color: var(--canvas-node-title-text);
}

.tool-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* 搜索框 */
.search-input {
  width: 220px;
}

.search-input :deep(.el-input__wrapper) {
  background: var(--canvas-bg);
  box-shadow: 0 0 0 1px var(--canvas-node-border) inset;
}

.search-input :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--canvas-node-active-border) inset;
}

.search-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--canvas-node-active-border) inset;
}

.search-input :deep(.el-input__inner) {
  color: var(--canvas-node-title-text);
}

.search-input :deep(.el-input__inner::placeholder) {
  color: var(--canvas-node-muted-text);
}

.search-icon {
  color: var(--canvas-node-muted-text);
}

/* 快捷键提示 */
.shortcut-hint {
  font-size: 11px;
  color: var(--canvas-node-muted-text);
  padding: 1px 5px;
  border: 1px solid var(--canvas-node-border);
  border-radius: 3px;
  line-height: 1;
}

/* 类型筛选下拉框 */
.filter-select {
  width: 140px;
}

.filter-select :deep(.el-select__wrapper) {
  background: var(--canvas-bg);
  box-shadow: 0 0 0 1px var(--canvas-node-border) inset;
}

.filter-select :deep(.el-select__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--canvas-node-active-border) inset;
}

.filter-select :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1px var(--canvas-node-active-border) inset;
}

.filter-select :deep(.el-select__placeholder),
.filter-select :deep(.el-select__selected-item) {
  color: var(--canvas-node-title-text);
}

/* 背景模式按钮组 */
.bg-mode-group {
  display: flex;
  gap: 2px;
  padding: 3px;
  border-radius: 6px;
  background: var(--canvas-node-border);
}

.bg-mode-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 24px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--canvas-node-muted-text);
  cursor: pointer;
  transition: all 0.15s ease;
}

.bg-mode-btn:hover {
  color: var(--canvas-node-title-text);
}

.bg-mode-btn.active {
  background: var(--canvas-panel-bg);
  color: var(--canvas-node-active-border);
}

/* 分隔线 */
.toolbar-divider {
  width: 1px;
  height: 20px;
  background: var(--canvas-node-border);
  margin: 0 4px;
}

/* 缩放控制组 */
.zoom-group {
  display: flex;
  align-items: center;
  gap: 2px;
}

.zoom-display {
  min-width: 48px;
  text-align: center;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--canvas-node-muted-text);
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
  transition: all 0.15s ease;
}

.zoom-display:hover {
  background: var(--canvas-node-border);
  color: var(--canvas-node-title-text);
}
</style>
