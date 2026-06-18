<!-- =====================================================
     CanvasToolbar 顶部工具栏
     - 节点创建按钮组（Text/Image/Config/Video/Audio）
     - 搜索框（/ 快捷键聚焦），输入时调用 store.searchAndLocate
     - 类型筛选多选（image/text/config/video/audio）
     - 背景模式切换（dot/grid/blank）
     - 主题切换（dark/light）
     - 导入/导出 JSON 按钮（emit export-json / import-json）
     - 暴露 focusSearch() 方法供外部快捷键调用
     样式：顶部水平工具栏，无边框融入背景，hover 轻微反馈
     ===================================================== -->

<template>
  <div class="canvas-toolbar">
    <!-- 节点创建按钮组 -->
    <div class="toolbar-group">
      <el-button
        v-for="item in nodeTypes"
        :key="item.type"
        class="toolbar-btn"
        :title="item.label"
        @click="handleAddNode(item)"
      >
        <span class="btn-icon">{{ item.icon }}</span>
        <span class="btn-label">{{ item.label }}</span>
      </el-button>
    </div>

    <div class="toolbar-divider"></div>

    <!-- 搜索框 -->
    <div class="toolbar-search">
      <el-input
        ref="searchInputRef"
        v-model="searchText"
        class="search-input"
        :placeholder="t('common.search')"
        size="small"
        clearable
        @input="handleSearch"
        @keyup.enter="handleSearch"
      >
        <template #prefix>
          <span class="search-icon">🔍</span>
        </template>
      </el-input>
    </div>

    <!-- 类型筛选多选 -->
    <el-select
      v-model="selectedTypes"
      multiple
      collapse-tags
      collapse-tags-tooltip
      class="filter-select"
      :placeholder="t('common.all')"
      size="small"
      @change="handleFilterChange"
    >
      <el-option
        v-for="item in nodeTypes"
        :key="item.type"
        :label="item.label"
        :value="item.type"
      />
    </el-select>

    <div class="toolbar-divider"></div>

    <!-- 背景模式切换 -->
    <div class="toolbar-group">
      <el-button
        v-for="mode in backgroundModes"
        :key="mode.value"
        class="toolbar-btn"
        :class="{ active: store.backgroundMode === mode.value }"
        :title="mode.label"
        @click="store.setBackgroundMode(mode.value)"
      >
        <span class="btn-icon">{{ mode.icon }}</span>
      </el-button>
    </div>

    <!-- 主题切换 -->
    <el-button
      class="toolbar-btn"
      :title="store.themeMode === 'dark' ? '切换到浅色' : '切换到深色'"
      @click="toggleTheme"
    >
      <span class="btn-icon">{{ store.themeMode === 'dark' ? '☀️' : '🌙' }}</span>
    </el-button>

    <div class="toolbar-divider"></div>

    <!-- 导入 / 导出 JSON -->
    <div class="toolbar-group">
      <el-button class="toolbar-btn" :title="t('canvas.importJson')" @click="emit('import-json')">
        <span class="btn-icon">📥</span>
        <span class="btn-label">{{ t('canvas.importJson') }}</span>
      </el-button>
      <el-button class="toolbar-btn" :title="t('canvas.exportJson')" @click="emit('export-json')">
        <span class="btn-icon">📤</span>
        <span class="btn-label">{{ t('canvas.exportJson') }}</span>
      </el-button>
    </div>
  </div>
</template>

<script setup>
// ------ 引入 Vue / Element Plus / Store / i18n ------
import { ref } from 'vue'
import { ElInput, ElButton, ElSelect, ElOption } from 'element-plus'
import { useCanvasStore } from '@/stores/canvas'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const store = useCanvasStore()

// ------ 事件向外抛 ------
const emit = defineEmits(['export-json', 'import-json'])

// ------ 节点类型配置（含默认尺寸） ------
const nodeTypes = [
  { type: 'text', label: '文本', icon: '📝', width: 300, height: 200 },
  { type: 'image', label: '图片', icon: '🖼️', width: 320, height: 240 },
  { type: 'config', label: '配置', icon: '⚙️', width: 360, height: 280 },
  { type: 'video', label: '视频', icon: '🎬', width: 400, height: 300 },
  { type: 'audio', label: '音频', icon: '🎵', width: 280, height: 100 },
]

// ------ 背景模式选项 ------
const backgroundModes = [
  { value: 'dot', label: t('canvas.backgroundDot'), icon: '·' },
  { value: 'grid', label: t('canvas.backgroundGrid'), icon: '▦' },
  { value: 'blank', label: t('canvas.backgroundBlank'), icon: '⬜' },
]

// ------ 搜索框 ------
const searchInputRef = ref(null)
const searchText = ref('')

/** 输入时实时调用 searchAndLocate */
function handleSearch(val) {
  store.searchAndLocate(val || '')
}

/** 暴露给父组件：聚焦搜索框（/ 快捷键调用） */
function focusSearch() {
  searchInputRef.value?.focus?.()
}
defineExpose({ focusSearch })

// ------ 类型筛选 ------
const selectedTypes = ref([])

/** 筛选变更时同步到 store */
function handleFilterChange(types) {
  store.setFilterTypes(types)
}

// ------ 主题切换 ------
function toggleTheme() {
  store.setThemeMode(store.themeMode === 'dark' ? 'light' : 'dark')
}

// ------ 添加节点 ------
function handleAddNode(item) {
  store.addPanel({
    type: item.type,
    x: 100,
    y: 100,
    width: item.width,
    height: item.height,
    content: {},
  })
}
</script>

<style scoped>
/* 顶部工具栏：无边框融入背景，hover 轻微反馈 */
.canvas-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: transparent;
  border: none;
  color: var(--canvas-node-title-text);
  flex-wrap: wrap;
}

.toolbar-group {
  display: flex;
  align-items: center;
  gap: 4px;
}

.toolbar-divider {
  width: 1px;
  height: 20px;
  background: var(--canvas-node-border);
  margin: 0 4px;
}

/* 工具栏按钮：极简扁平，无边框无阴影 */
.toolbar-btn {
  background: transparent !important;
  border: none !important;
  color: var(--canvas-node-muted-text) !important;
  padding: 6px 10px !important;
  border-radius: 6px !important;
  font-size: 13px;
  transition: all 0.15s ease;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 32px;
}

.toolbar-btn:hover {
  background: var(--canvas-selection-fill) !important;
  color: var(--canvas-node-title-text) !important;
}

.toolbar-btn.active {
  background: var(--canvas-selection-fill) !important;
  color: var(--canvas-node-active-border) !important;
}

.btn-icon {
  font-size: 14px;
  line-height: 1;
}

.btn-label {
  font-size: 12px;
}

/* 搜索框 */
.toolbar-search {
  width: 200px;
}

.search-input :deep(.el-input__wrapper) {
  background: var(--canvas-panel-bg);
  border: 1px solid var(--canvas-node-border);
  box-shadow: none;
}

.search-input :deep(.el-input__wrapper:hover) {
  border-color: var(--canvas-node-active-border);
}

.search-input :deep(.el-input__inner) {
  color: var(--canvas-node-title-text);
}

.search-input :deep(.el-input__inner::placeholder) {
  color: var(--canvas-node-muted-text);
}

.search-icon {
  font-size: 12px;
  opacity: 0.7;
}

/* 类型筛选下拉 */
.filter-select {
  width: 140px;
}

.filter-select :deep(.el-input__wrapper) {
  background: var(--canvas-panel-bg);
  border: 1px solid var(--canvas-node-border);
  box-shadow: none;
}

.filter-select :deep(.el-input__inner) {
  color: var(--canvas-node-title-text);
}
</style>
