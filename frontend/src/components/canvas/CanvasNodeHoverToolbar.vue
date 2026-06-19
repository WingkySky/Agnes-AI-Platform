<!-- =====================================================
     CanvasNodeHoverToolbar 节点悬停工具栏
     - 1:1 复刻参考项目 infinite-canvas 的 canvas-node-hover-toolbar
     - 固定在节点上方居中（由父组件定位，本组件只负责内容和样式）
     - h-12（48px）高、rounded-[18px]（18px 圆角）容器
     - 按节点类型和状态计算按钮列表：
       · 基础：信息、删除
       · 错误：重试
       · 有内容：存素材、下载、编辑
       · text：编辑文字、生图、缩小字号、放大字号
       · image 空图：上传图片
       · video：上传视频
       · audio：上传音频
       · image 有图：复制提示词、反推、替换、锁比例、局部编辑、裁剪、拆分、放大、超分、角度、查看大图
     - 每个按钮 32×32px，hover 显示中文 tooltip
     ===================================================== -->

<template>
  <div
    class="canvas-node-hover-toolbar"
    :style="toolbarStyle"
    @mousedown.stop
    @pointerdown.stop
  >
    <button
      v-for="tool in tools"
      :key="tool.id"
      type="button"
      class="toolbar-btn"
      :class="{ 'is-danger': tool.danger }"
      :style="btnStyle(tool)"
      :title="tool.title"
      :aria-label="tool.title"
      @click="handleClick(tool)"
    >
      <component :is="tool.icon" :size="16" />
    </button>
  </div>
</template>

<script setup>
/* =====================================================
 * CanvasNodeHoverToolbar 节点悬停工具栏
 * 1:1 复刻参考项目 infinite-canvas 的节点悬停工具栏设计
 *
 * 数据约定：panel.content 作为节点元数据
 *   - content.content：文本内容 / 媒体 URL
 *   - content.status：'idle' | 'loading' | 'error' | 'success'
 *   - content.freeResize：是否自由缩放（不保持比例）
 * ===================================================== */

import { computed } from 'vue'
import {
  Info, Trash2, RefreshCw, FolderPlus, Download, MessageSquare,
  Pencil, Image as ImageIcon, Minus, Plus, Upload, Video, Music2,
  Copy, FileText, Lock, LockOpen, Brush, Scissors, Grid2x2,
  ZoomIn, Sparkles, Camera, Maximize2,
} from 'lucide-vue-next'

/* ---------- Props 定义 ---------- */
const props = defineProps({
  panel: { type: Object, required: true },
  theme: { type: Object, required: true },
})

/* ---------- Emits 定义 ---------- */
const emit = defineEmits([
  'info', 'delete', 'retry', 'save-asset', 'download', 'edit',
  'edit-text', 'generate-image', 'font-size-down', 'font-size-up',
  'upload-image', 'upload-video', 'upload-audio',
  'copy-prompt', 'describe', 'replace-image', 'toggle-ratio',
  'mask-edit', 'crop', 'split', 'upscale', 'super-resolution', 'angle', 'view-large',
])

/* ---------- 节点元数据计算 ---------- */

/** 节点元数据（统一访问 panel.content） */
const content = computed(() => props.panel.content || {})

/** 节点类型 */
const panelType = computed(() => props.panel.type)

/** 是否有媒体/文本内容 */
const hasContent = computed(() => Boolean(content.value.content))

/** 是否处于错误状态 */
const isError = computed(() => content.value.status === 'error')

/** 各类型判断 */
const isText = computed(() => panelType.value === 'text')
const isImage = computed(() => panelType.value === 'image')
const isVideo = computed(() => panelType.value === 'video')
const isAudio = computed(() => panelType.value === 'audio')

/** 图片节点是否有图 */
const hasImage = computed(() => isImage.value && hasContent.value)

/* ---------- 容器样式 ---------- */

/** 工具栏容器样式：背景 + 边框 + hover 背景变量 */
const toolbarStyle = computed(() => ({
  background: props.theme.node.panel,
  borderColor: props.theme.toolbar.border,
  '--hover-bg': props.theme.toolbar.itemHover,
}))

/* ---------- 按钮样式 ---------- */

/** 按钮样式：图标颜色（删除按钮用红色） */
function btnStyle(tool) {
  return {
    color: tool.danger ? '#ef4444' : props.theme.toolbar.item,
  }
}

/* ---------- 按钮列表计算（按节点类型和状态） ---------- */
const tools = computed(() => {
  const list = []

  // 1. 基础按钮（所有类型）：信息、删除
  list.push({
    id: 'info',
    title: '查看节点信息',
    icon: Info,
    onClick: () => emit('info', props.panel),
  })
  list.push({
    id: 'delete',
    title: '删除节点',
    icon: Trash2,
    danger: true,
    onClick: () => emit('delete', props.panel),
  })

  // 2. 错误状态：重试
  if (isError.value) {
    list.push({
      id: 'retry',
      title: '重新生成',
      icon: RefreshCw,
      onClick: () => emit('retry', props.panel),
    })
  }

  // 3. 有内容时：存素材、下载、编辑
  if (hasContent.value) {
    list.push({
      id: 'save-asset',
      title: '存素材',
      icon: FolderPlus,
      onClick: () => emit('save-asset', props.panel),
    })
    list.push({
      id: 'download',
      title: '下载',
      icon: Download,
      onClick: () => emit('download', props.panel),
    })
    list.push({
      id: 'edit',
      title: '编辑',
      icon: MessageSquare,
      onClick: () => emit('edit', props.panel),
    })
  }

  // 4. text 类型：编辑文字、生图、缩小字号、放大字号
  if (isText.value) {
    list.push({
      id: 'edit-text',
      title: '编辑文字',
      icon: Pencil,
      onClick: () => emit('edit-text', props.panel),
    })
    list.push({
      id: 'generate-image',
      title: '生图',
      icon: ImageIcon,
      onClick: () => emit('generate-image', props.panel),
    })
    list.push({
      id: 'font-size-down',
      title: '缩小字号',
      icon: Minus,
      onClick: () => emit('font-size-down', props.panel),
    })
    list.push({
      id: 'font-size-up',
      title: '放大字号',
      icon: Plus,
      onClick: () => emit('font-size-up', props.panel),
    })
  }

  // 5. image 空图：上传图片
  if (isImage.value && !hasContent.value) {
    list.push({
      id: 'upload-image',
      title: '上传图片',
      icon: Upload,
      onClick: () => emit('upload-image', props.panel),
    })
  }

  // 6. video 类型：上传视频（有内容时显示"替换视频"）
  if (isVideo.value) {
    list.push({
      id: 'upload-video',
      title: hasContent.value ? '替换视频' : '上传视频',
      icon: Video,
      onClick: () => emit('upload-video', props.panel),
    })
  }

  // 7. audio 类型：上传音频（有内容时显示"替换音频"）
  if (isAudio.value) {
    list.push({
      id: 'upload-audio',
      title: hasContent.value ? '替换音频' : '上传音频',
      icon: Music2,
      onClick: () => emit('upload-audio', props.panel),
    })
  }

  // 8. image 有图：复制提示词、反推、替换、锁比例、局部编辑、裁剪、拆分、放大、超分、角度、查看大图
  if (hasImage.value) {
    list.push({
      id: 'copy-prompt',
      title: '复制提示词',
      icon: Copy,
      onClick: () => emit('copy-prompt', props.panel),
    })
    list.push({
      id: 'describe',
      title: '反推提示词',
      icon: FileText,
      onClick: () => emit('describe', props.panel),
    })
    list.push({
      id: 'replace-image',
      title: '替换图片',
      icon: Upload,
      onClick: () => emit('replace-image', props.panel),
    })
    list.push({
      id: 'toggle-ratio',
      title: content.value.freeResize ? '锁定比例' : '自由比例',
      icon: content.value.freeResize ? Lock : LockOpen,
      onClick: () => emit('toggle-ratio', props.panel),
    })
    list.push({
      id: 'mask-edit',
      title: '局部编辑',
      icon: Brush,
      onClick: () => emit('mask-edit', props.panel),
    })
    list.push({
      id: 'crop',
      title: '裁剪',
      icon: Scissors,
      onClick: () => emit('crop', props.panel),
    })
    list.push({
      id: 'split',
      title: '拆分',
      icon: Grid2x2,
      onClick: () => emit('split', props.panel),
    })
    list.push({
      id: 'upscale',
      title: '放大',
      icon: ZoomIn,
      onClick: () => emit('upscale', props.panel),
    })
    list.push({
      id: 'super-resolution',
      title: '超分',
      icon: Sparkles,
      onClick: () => emit('super-resolution', props.panel),
    })
    list.push({
      id: 'angle',
      title: '角度',
      icon: Camera,
      onClick: () => emit('angle', props.panel),
    })
    list.push({
      id: 'view-large',
      title: '查看大图',
      icon: Maximize2,
      onClick: () => emit('view-large', props.panel),
    })
  }

  return list
})

/* ---------- 按钮点击处理 ---------- */
function handleClick(tool) {
  if (tool.onClick) tool.onClick()
}
</script>

<style scoped>
/* ===== 工具栏容器：h-12（48px）+ rounded-[18px] + 边框 + 阴影 ===== */
.canvas-node-hover-toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 48px;
  padding: 0 8px;
  border-radius: 18px;
  border: 1px solid;
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(8px);
  overflow: visible;
}

/* ===== 工具栏按钮：32×32px ===== */
.toolbar-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  transition: background-color 150ms ease;
  flex-shrink: 0;
}

.toolbar-btn:hover {
  background-color: var(--hover-bg, #e7e5df);
}
</style>
