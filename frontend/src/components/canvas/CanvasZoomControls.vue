<!--
  CanvasZoomControls.vue
  画布左下角缩放控件：包含小地图开关、重置视图、缩放滑块、缩放百分比显示
  快捷键帮助弹窗也由本组件提供（通过 defineExpose openShortcuts 暴露给父组件）
  1:1 复刻参考项目 infinite-canvas 的 canvas-zoom-controls 设计
-->
<template>
  <div
    class="canvas-zoom-controls"
    @mousedown.stop
    @pointerdown.stop
  >
    <div class="dock" :style="dockStyle">
      <!-- 小地图开关（开启时高亮） -->
      <button
        class="dock-btn"
        :style="minimapVisible ? activeStyle : { color: theme.toolbar.item }"
        :title="minimapVisible ? t('canvas.zoom.minimapClose') : t('canvas.zoom.minimapOpen')"
        :aria-label="minimapVisible ? t('canvas.zoom.minimapClose') : t('canvas.zoom.minimapOpen')"
        @click="$emit('toggle-minimap')"
      >
        <Compass class="icon" />
      </button>

      <!-- 重置视图 -->
      <button
        class="dock-btn"
        :style="{ color: theme.toolbar.item }"
        :title="t('canvas.zoom.reset')"
        :aria-label="t('canvas.zoom.reset')"
        @click="$emit('reset-view')"
      >
        <Focus class="icon" />
      </button>

      <!-- 缩放滑块：min 5% max 500% -->
      <input
        type="range"
        min="5"
        max="500"
        step="1"
        :value="zoomPercent"
        class="zoom-slider"
        :style="{ accentColor: theme.node.activeStroke }"
        :title="t('canvas.zoom.zoomInOut')"
        :aria-label="t('canvas.zoom.zoomInOut')"
        @input="onSliderInput"
      />

      <!-- 缩放百分比显示（右对齐） -->
      <span class="zoom-value" :style="{ color: theme.node.muted }">
        {{ zoomPercent }}%
      </span>
    </div>

    <!-- 快捷键帮助 Modal（由底部工具栏的快捷键按钮通过 ref 触发） -->
    <el-dialog
      v-model="shortcutsOpen"
      :title="t('canvas.help.title')"
      width="420px"
      align-center
      append-to-body
    >
      <div class="shortcut-list" :style="{ borderColor: theme.node.stroke }">
        <div v-for="s in shortcuts" :key="s.label" class="shortcut-row">
          <span class="shortcut-label">{{ s.label }}</span>
          <span class="shortcut-value">{{ s.value }}</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Compass, Focus } from 'lucide-vue-next'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const props = defineProps({
  theme: { type: Object, required: true },
  zoom: { type: Number, default: 1 }, // 当前缩放倍数 0.05-5
  minimapVisible: { type: Boolean, default: false },
})

const emit = defineEmits(['toggle-minimap', 'reset-view', 'zoom-change'])

// 快捷键帮助弹窗开关
const shortcutsOpen = ref(false)

// 缩放百分比（5-500）
const zoomPercent = computed(() => Math.round(props.zoom * 100))

// 主题深浅判断（用于阴影色）
const isDark = computed(() => {
  const bg = props.theme?.canvas?.background || ''
  if (bg.startsWith('#')) {
    const hex = bg.slice(1)
    const r = parseInt(hex.slice(0, 2), 16)
    const g = parseInt(hex.slice(2, 4), 16)
    const b = parseInt(hex.slice(4, 6), 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5
  }
  return false
})

// 工具栏容器样式
const dockStyle = computed(() => ({
  background: props.theme.toolbar.panel,
  borderColor: props.theme.toolbar.border,
  color: props.theme.toolbar.item,
  boxShadow: isDark.value
    ? '0 18px 45px rgba(0,0,0,.32)'
    : '0 16px 40px rgba(28,25,23,.12)',
}))

// 激活态样式（小地图开启 / 快捷键弹窗打开时）
const activeStyle = computed(() => ({
  background: props.theme.toolbar.activeBg,
  color: props.theme.toolbar.activeText,
}))

// 滑块输入：将百分比转回倍数后 emit
function onSliderInput(event: Event) {
  emit('zoom-change', Number((event.target as HTMLInputElement)?.value) / 100)
}

// 打开快捷键弹窗（同时供父组件通过 ref 调用）
function openShortcuts() {
  shortcutsOpen.value = true
}

// 画布快捷键列表（label 为按键名硬编，value 为功能说明走 i18n）
const shortcuts = computed(() => [
  { label: 'Space + 拖动 / 中键', value: t('canvas.help.spacePan') },
  { label: '滚轮', value: t('canvas.help.ctrlWheel') },
  { label: 'Ctrl + 拖动背景', value: t('canvas.help.ctrlDrag') },
  { label: 'Ctrl + 点击节点', value: t('canvas.help.ctrlClick') },
  { label: t('canvas.toolbar.toolSelect'), value: t('canvas.help.selectTool') },
  { label: 'Ctrl + Z', value: t('canvas.help.ctrlZ') },
  { label: 'Ctrl + Shift + Z', value: t('canvas.help.ctrlShiftZ') },
  { label: 'Ctrl + D', value: t('canvas.help.ctrlD') },
  { label: 'Ctrl + A', value: t('canvas.help.ctrlA') },
  { label: 'Ctrl + S', value: t('canvas.help.ctrlS') },
  { label: 'Ctrl + L', value: t('canvas.help.ctrlL') },
  { label: 'Delete / Backspace', value: t('canvas.help.delete') },
  { label: 'Escape', value: t('canvas.help.escape') },
])

// 暴露给父组件：外部按钮也可触发快捷键弹窗
defineExpose({ openShortcuts })
</script>

<style scoped>
/* 容器：固定左下角 */
.canvas-zoom-controls {
  position: fixed;
  bottom: 20px; /* bottom-5 */
  left: 20px; /* left-5 */
  z-index: 50;
}

/* 工具栏 dock：h-14 圆角 xl 带边框/阴影/毛玻璃 */
.dock {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 56px; /* h-14 */
  padding: 0 8px;
  border: 1px solid;
  border-radius: 12px; /* rounded-xl */
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

/* dock 内按钮：8x8 图标按钮 */
.dock-btn {
  width: 32px; /* w-8 */
  height: 32px; /* h-8 */
  min-width: 32px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.dock-btn:hover {
  background: var(--agnes-bg-hover);
}

/* 图标尺寸 size-4 */
.dock-btn .icon {
  width: 16px;
  height: 16px;
}

/* 缩放滑块 w-24 */
.zoom-slider {
  width: 96px;
  cursor: pointer;
}

/* 缩放百分比 w-10 右对齐 */
.zoom-value {
  width: 40px; /* w-10 */
  text-align: right;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  user-select: none;
}

/* 快捷键弹窗内容 */
.shortcut-list {
  padding-top: 16px;
  border-top: 1px solid;
  display: flex;
  flex-direction: column;
  gap: 12px;
  font-size: 14px;
}

.shortcut-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.shortcut-label {
  font-size: 15px;
  font-weight: 500;
}

.shortcut-value {
  opacity: 0.6;
}
</style>
