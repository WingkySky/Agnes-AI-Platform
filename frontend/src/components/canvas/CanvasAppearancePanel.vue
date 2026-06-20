<!--
  CanvasAppearancePanel.vue
  画布外观设置面板组件
  1:1 复刻参考项目 infinite-canvas 的画布外观面板设计
  提供主题模式（浅色/深色）、网格样式（点/线/空白）、图片信息开关
  固定在底部工具栏上方，通过 emits 让父组件处理具体逻辑
-->
<template>
  <div class="canvas-appearance-panel" :style="panelStyle">
    <!-- 面板标题 -->
    <div class="panel-title">画布外观</div>

    <!-- 主题模式：浅色/深色 -->
    <div class="section-label">主题模式</div>
    <div class="mode-group theme-mode-group" :style="{ background: theme.toolbar.itemHover }">
      <button
        type="button"
        class="mode-btn"
        :class="{ active: themeMode === 'light' }"
        :style="themeMode === 'light' ? lightActiveStyle : { color: theme.toolbar.item }"
        aria-label="切换到浅色主题"
        title="切换到浅色主题"
        @click="$emit('set-theme', 'light')"
      >
        <Sun :size="16" />
        <span>浅色</span>
      </button>
      <button
        type="button"
        class="mode-btn"
        :class="{ active: themeMode === 'dark' }"
        :style="themeMode === 'dark' ? darkActiveStyle : { color: theme.toolbar.item }"
        aria-label="切换到深色主题"
        title="切换到深色主题"
        @click="$emit('set-theme', 'dark')"
      >
        <Moon :size="16" />
        <span>深色</span>
      </button>
    </div>

    <!-- 网格样式：点/线/空白 -->
    <div class="section-label mt-3">网格样式</div>
    <div class="mode-group bg-mode-group" :style="{ background: theme.toolbar.itemHover }">
      <button
        type="button"
        class="mode-btn"
        :class="{ active: backgroundMode === 'dots' }"
        :style="backgroundMode === 'dots' ? activeStyle : { color: theme.toolbar.item }"
        @click="$emit('set-background', 'dots')"
      >
        <CircleDot :size="16" />
        <span>点</span>
      </button>
      <button
        type="button"
        class="mode-btn"
        :class="{ active: backgroundMode === 'lines' }"
        :style="backgroundMode === 'lines' ? activeStyle : { color: theme.toolbar.item }"
        @click="$emit('set-background', 'lines')"
      >
        <Grid2x2 :size="16" />
        <span>线</span>
      </button>
      <button
        type="button"
        class="mode-btn"
        :class="{ active: backgroundMode === 'blank' }"
        :style="backgroundMode === 'blank' ? activeStyle : { color: theme.toolbar.item }"
        @click="$emit('set-background', 'blank')"
      >
        <Square :size="16" />
        <span>空白</span>
      </button>
    </div>

    <!-- 图片信息开关 -->
    <div class="image-info-row">
      <span class="image-info-label">
        <Info :size="14" />
        图片信息
      </span>
      <el-switch
        :model-value="showImageInfo"
        size="small"
        @update:model-value="(val) => $emit('toggle-image-info', val)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Sun, Moon, CircleDot, Grid2x2, Square, Info } from 'lucide-vue-next'
import { ElSwitch } from 'element-plus'

const props = defineProps({
  theme: { type: Object, required: true },
  themeMode: { type: String, default: 'dark' },
  backgroundMode: { type: String, default: 'dots' },
  showImageInfo: { type: Boolean, default: false },
})

defineEmits(['set-theme', 'set-background', 'toggle-image-info'])

// 面板容器样式：背景/边框/文字色由主题 token 控制
const panelStyle = computed(() => ({
  background: props.theme.toolbar.panel,
  borderColor: props.theme.toolbar.border,
  color: props.theme.toolbar.item,
}))

// 浅色主题激活样式（参考项目：light 时用黑底白字）
const lightActiveStyle = computed(() => ({
  background: '#111111',
  color: '#ffffff',
}))

// 深色主题激活样式
const darkActiveStyle = computed(() => ({
  background: props.theme.toolbar.activeBg,
  color: props.theme.toolbar.activeText,
}))

// 网格样式激活样式
const activeStyle = computed(() => ({
  background: props.theme.toolbar.activeBg,
  color: props.theme.toolbar.activeText,
}))
</script>

<style scoped>
/* 面板容器：固定在工具栏上方，居中对齐 */
.canvas-appearance-panel {
  position: absolute;
  bottom: 100%;
  margin-bottom: 8px;
  left: 50%;
  transform: translateX(-50%);
  width: 248px;
  padding: 10px;
  border: 1px solid;
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.18);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  z-index: 30;
  pointer-events: auto;
}

/* 面板标题 */
.panel-title {
  padding: 0 4px 8px;
  font-size: 14px;
  font-weight: 500;
  opacity: 0.65;
}

/* 分组小标题 */
.section-label {
  padding: 0 4px 6px;
  font-size: 11px;
  font-weight: 500;
  opacity: 0.5;
}

.section-label.mt-3 {
  margin-top: 12px;
}

/* 模式按钮组容器 */
.mode-group {
  display: grid;
  gap: 4px;
  padding: 4px;
  border-radius: 8px;
}

.theme-mode-group {
  grid-template-columns: repeat(2, 1fr);
}

.bg-mode-group {
  grid-template-columns: repeat(3, 1fr);
}

/* 模式按钮 */
.mode-btn {
  display: inline-flex;
  min-width: 0;
  height: 32px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 8px;
  border: none;
  border-radius: 6px;
  background: transparent;
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.mode-btn:hover:not(.active) {
  opacity: 0.8;
}

/* 图片信息开关行 */
.image-info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
  padding: 4px 6px;
  border-radius: 8px;
}

.image-info-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 500;
  opacity: 0.65;
}
</style>
