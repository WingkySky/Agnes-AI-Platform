<!--
  CanvasToolbar.vue
  画布底部浮动工具栏组件
  1:1 复刻参考项目 infinite-canvas 的 canvas-toolbar 设计
  提供移动/选择、撤销/重做、新增节点（文本/图片/视频/音频/配置/上传）、
  素材库、画布外观、删除选中、清空画布等操作入口
  按钮通过 emits 让父组件处理具体逻辑
-->
<template>
  <div class="canvas-toolbar-wrap" ref="wrapRef">
    <!-- 顶部悬浮提示 -->
    <span
      v-if="tip"
      class="dock-tip"
      :style="tipStyle"
    >{{ tip }}</span>

    <!-- 工具栏主体 -->
    <div class="canvas-toolbar" :style="dockStyle">
      <template v-for="(group, gIdx) in buttonGroups" :key="gIdx">
        <!-- 组间分隔符：1px 竖线 -->
        <span
          v-if="gIdx > 0"
          class="toolbar-divider"
          :style="{ background: theme.toolbar.border }"
        ></span>

        <!-- 组内按钮 -->
        <template v-for="btn in group" :key="btn.id">
          <button
            v-if="!btn.conditional || hasSelection"
            type="button"
            class="toolbar-btn"
            :aria-label="btn.label"
            :disabled="btn.disabled"
            :style="btnStyle(btn)"
            @mouseenter="onHover(btn.id, $event)"
            @mouseleave="onLeave"
            @click="onBtnClick(btn)"
          >
            <component :is="btn.icon" :size="18" />
          </button>
        </template>
      </template>
    </div>

    <!-- 画布外观面板 -->
    <CanvasAppearancePanel
      v-if="showAppearancePanel"
      :theme="theme"
      :theme-mode="themeMode"
      :background-mode="backgroundMode"
      :show-image-info="showImageInfo"
      @set-theme="(mode) => $emit('set-theme', mode)"
      @set-background="(mode) => $emit('set-background', mode)"
      @toggle-image-info="(val) => $emit('toggle-image-info', val)"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Hand, Undo2, Redo2, Type, Image, Video, Music2, Settings2, Upload,
  FolderOpen, Palette, Trash2, Eraser,
} from 'lucide-vue-next'
import CanvasAppearancePanel from './CanvasAppearancePanel.vue'

const props = defineProps({
  theme: { type: Object, required: true },
  hasSelection: { type: Boolean, default: false },
  canUndo: { type: Boolean, default: false },
  canRedo: { type: Boolean, default: false },
  showAppearancePanel: { type: Boolean, default: false },
  themeMode: { type: String, default: 'dark' },
  backgroundMode: { type: String, default: 'dots' },
  showImageInfo: { type: Boolean, default: false },
})

const emit = defineEmits([
  'select-tool',
  'undo', 'redo',
  'add-node',
  'upload-asset',
  'open-asset-library',
  'toggle-appearance-panel',
  'delete-selected',
  'clear-canvas',
  'set-theme',
  'set-background',
  'toggle-image-info',
])

// 工具栏容器引用，用于计算 tooltip 水平位置
const wrapRef = ref<HTMLElement | null>(null)
// 当前 hover 的按钮 id
const hovered = ref<string | null>(null)
// tooltip 的水平偏移（相对工具栏容器）
const tipX = ref(0)

// 按钮分组配置：组间会渲染分隔符
const buttonGroups = computed<any[][]>(() => [
  // 组1：移动/选择（无选中时高亮）
  [
    { id: 'tool-hand', label: '移动/选择', icon: Hand, active: !props.hasSelection, emit: 'select-tool' },
  ],
  // 组2：撤销/重做
  [
    { id: 'tool-undo', label: '撤销', icon: Undo2, disabled: !props.canUndo, emit: 'undo' },
    { id: 'tool-redo', label: '重做', icon: Redo2, disabled: !props.canRedo, emit: 'redo' },
  ],
  // 组3：新增节点（文本/图片/视频/音频/生成配置/上传素材）
  [
    { id: 'tool-text', label: '文本', icon: Type, emit: 'add-node', payload: 'text' },
    { id: 'tool-image', label: '图片', icon: Image, emit: 'add-node', payload: 'image' },
    { id: 'tool-video', label: '视频', icon: Video, emit: 'add-node', payload: 'video' },
    { id: 'tool-audio', label: '音频', icon: Music2, emit: 'add-node', payload: 'audio' },
    { id: 'tool-config', label: '生成配置', icon: Settings2, emit: 'add-node', payload: 'config' },
    { id: 'tool-upload', label: '上传素材', icon: Upload, emit: 'upload-asset' },
  ],
  // 组4：我的素材/画布外观
  [
    { id: 'tool-assets', label: '我的素材', icon: FolderOpen, emit: 'open-asset-library' },
    { id: 'tool-style', label: '画布外观', icon: Palette, active: props.showAppearancePanel, emit: 'toggle-appearance-panel' },
  ],
  // 组5：删除选中（仅选中时显示，红色）+ 清空画布（红色）
  [
    { id: 'tool-delete', label: '删除选中', icon: Trash2, danger: true, conditional: true, emit: 'delete-selected' },
    { id: 'tool-clear', label: '清空画布', icon: Eraser, danger: true, emit: 'clear-canvas' },
  ],
])

// 工具栏主体样式：背景/边框/文字色由主题 token 控制，阴影随主题模式变化
const dockStyle = computed(() => ({
  background: props.theme.toolbar.panel,
  borderColor: props.theme.toolbar.border,
  color: props.theme.toolbar.item,
  boxShadow: props.themeMode === 'dark'
    ? '0 18px 45px rgba(0,0,0,.32)'
    : '0 16px 40px rgba(28,25,23,.12)',
}))

// 按钮 hover 样式
const hoverStyle = computed(() => ({
  background: props.theme.toolbar.itemHover,
  color: props.theme.toolbar.activeText,
}))

// 按钮激活样式
const activeStyle = computed(() => ({
  background: props.theme.toolbar.activeBg,
  color: props.theme.toolbar.activeText,
}))

// tooltip 文案映射
const tip = computed(() => {
  const map: Record<string, string> = {
    'tool-hand': '移动/选择',
    'tool-undo': '撤销',
    'tool-redo': '重做',
    'tool-text': '文本',
    'tool-image': '图片',
    'tool-video': '视频',
    'tool-audio': '音频',
    'tool-config': '生成配置',
    'tool-upload': '上传素材',
    'tool-assets': '我的素材',
    'tool-style': '画布外观',
    'tool-delete': '删除选中',
    'tool-clear': '清空画布',
  }
  return map[hovered.value!] || ''
})

// tooltip 样式：背景/文字色用 node token，水平位置跟随按钮中心
const tipStyle = computed(() => ({
  left: tipX.value + 'px',
  background: props.theme.node.text,
  color: props.theme.node.panel,
}))

// 计算按钮 style：激活态 > hover 态 > 默认态
function btnStyle(btn: any) {
  if (btn.active) return activeStyle.value
  if (hovered.value === btn.id && !btn.disabled) return hoverStyle.value
  return {
    color: btn.danger ? '#f87171' : props.theme.toolbar.item,
    opacity: btn.disabled ? 0.35 : 1,
  }
}

// 计算 tooltip 相对工具栏容器的水平位置（按钮中心）
function getTipX(target: HTMLElement) {
  const wrap = wrapRef.value
  if (!wrap) return 0
  const wrapBox = wrap.getBoundingClientRect()
  const box = target.getBoundingClientRect()
  return box.left - wrapBox.left + box.width / 2
}

// 按钮 hover：记录 id 和 tooltip 位置
function onHover(id: string, event: MouseEvent) {
  hovered.value = id
  tipX.value = getTipX(event.currentTarget as HTMLElement)
}

// 按钮 leave：清除 hover 状态
function onLeave() {
  hovered.value = null
}

// 按钮点击：根据配置 emit 对应事件（带 payload 时一并发出）
function onBtnClick(btn: any) {
  if (btn.disabled) return
  if (btn.payload !== undefined) {
    emit(btn.emit, btn.payload)
  } else {
    emit(btn.emit)
  }
}
</script>

<style scoped>
/* 工具栏外层容器：fixed 定位在画布底部中央 */
.canvas-toolbar-wrap {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 50;
  pointer-events: none;
}

/* 工具栏主体：56px 高、12px 圆角、毛玻璃效果 */
.canvas-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 56px;
  padding: 0 8px;
  border: 1px solid;
  border-radius: 12px;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  overflow-x: auto;
  pointer-events: auto;
}

/* 工具栏按钮：32×32px */
.toolbar-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.toolbar-btn:disabled {
  cursor: not-allowed;
}

/* 组间分隔符：1px 竖线 */
.toolbar-divider {
  flex-shrink: 0;
  display: inline-block;
  width: 1px;
  height: 24px;
  margin: 0 4px;
}

/* 顶部悬浮提示：浮于工具栏上方 */
.dock-tip {
  position: absolute;
  bottom: calc(100% + 8px);
  transform: translateX(-50%);
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 12px;
  white-space: nowrap;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.18);
  pointer-events: none;
}
</style>
