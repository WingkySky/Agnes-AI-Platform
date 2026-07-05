<!-- =====================================================
     时间线片段 TimelineClip
     - 单个片段的视觉呈现（视频/音频/字幕三种 track_type）
     - 拖拽整体移动、左右手柄裁剪 trim_start/trim_end
     - 选中态 + 转场标记（none/fade/slide/wipe/dissolve）
     - 与父组件通过 emit 交互，不直接调用 store
     ===================================================== -->

<template>
  <div
    class="timeline-clip"
    :class="[`track-${clip.track_type}`, { selected: selected }]"
    :style="clipStyle"
    @mousedown="onDragStart"
    @click.stop="$emit('select', clip.id)"
  >
    <!-- 左侧裁剪手柄 -->
    <div
      v-if="editable"
      class="trim-handle trim-left"
      @mousedown.stop="onTrimStart('left')"
    >
      <el-icon><DArrowLeft /></el-icon>
    </div>

    <!-- 片段内容 -->
    <div class="clip-content">
      <div class="clip-label">
        <el-icon v-if="clip.track_type === 'video'"><VideoCamera /></el-icon>
        <el-icon v-else-if="clip.track_type === 'audio'"><Microphone /></el-icon>
        <el-icon v-else><Document /></el-icon>
        <span class="label-text">{{ displayLabel }}</span>
      </div>
      <!-- 字幕片段显示文本预览 -->
      <div v-if="clip.track_type === 'subtitle' && clip.subtitle_text" class="subtitle-text">
        {{ clip.subtitle_text }}
      </div>
      <!-- 视频片段显示转场标记 -->
      <div
        v-if="clip.track_type === 'video' && clip.transition_type !== 'none'"
        class="transition-badge"
      >
        <el-icon><Connection /></el-icon>
        <span>{{ transitionLabel }} · {{ clip.transition_duration }}s</span>
      </div>
    </div>

    <!-- 右侧裁剪手柄 -->
    <div
      v-if="editable"
      class="trim-handle trim-right"
      @mousedown.stop="onTrimStart('right')"
    >
      <el-icon><DArrowRight /></el-icon>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  DArrowLeft, DArrowRight, VideoCamera, Microphone, Document, Connection,
} from '@element-plus/icons-vue'
import type { TimelineClip, TransitionType } from '@/types/project'

const props = defineProps<{
  clip: TimelineClip
  /** 像素/秒 比例（决定宽度） */
  pixelsPerSecond: number
  selected?: boolean
  editable?: boolean
}>()

const emit = defineEmits<{
  (e: 'select', clipId: number): void
  /** 拖动整体片段，delta 为秒数（正/负） */
  (e: 'drag', clipId: number, deltaSeconds: number): void
  /** 裁剪，side='left' 调整 trim_start，side='right' 调整 trim_end，delta 为秒数 */
  (e: 'trim', clipId: number, side: 'left' | 'right', deltaSeconds: number): void
  /** 拖拽结束（提交保存） */
  (e: 'drag-end', clipId: number): void
}>()

// 计算片段在轨道中的样式
const clipStyle = computed(() => {
  const width = Math.max(20, props.clip.duration * props.pixelsPerSecond)
  return {
    width: `${width}px`,
  }
})

// 显示标签
const displayLabel = computed(() => {
  const c = props.clip
  if (c.track_type === 'subtitle') {
    return c.subtitle_text ? truncate(c.subtitle_text, 24) : `字幕 ${c.sort_order + 1}`
  }
  if (c.track_type === 'audio') {
    return c.source_type === 'tts' ? `配音 ${c.sort_order + 1}` : `音频 ${c.sort_order + 1}`
  }
  // video
  return c.shot_id ? `镜 ${c.sort_order + 1}` : `片段 ${c.sort_order + 1}`
})

const transitionLabel = computed(() => {
  const map: Record<TransitionType, string> = {
    none: '无',
    fade: '淡入淡出',
    slide: '滑动',
    wipe: '擦除',
    dissolve: '溶解',
  }
  return map[props.clip.transition_type] || props.clip.transition_type
})

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + '…' : s
}

// ---------- 拖拽（整体移动） ----------
function onDragStart(e: MouseEvent) {
  if (!props.editable) return
  e.preventDefault()
  const startX = e.clientX
  let lastDelta = 0
  let moved = false

  const onMove = (ev: MouseEvent) => {
    const dx = ev.clientX - startX
    const delta = dx / props.pixelsPerSecond
    if (Math.abs(dx) > 2) moved = true
    // 仅 emit 增量变化（避免父组件累积）
    const inc = delta - lastDelta
    lastDelta = delta
    if (inc !== 0) emit('drag', props.clip.id, inc)
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    if (moved) emit('drag-end', props.clip.id)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ---------- 裁剪（trim_start / trim_end） ----------
function onTrimStart(side: 'left' | 'right') {
  if (!props.editable) return
  const startX = (event as MouseEvent)?.clientX ?? 0
  let lastDelta = 0

  const onMove = (ev: MouseEvent) => {
    const dx = ev.clientX - startX
    const delta = dx / props.pixelsPerSecond
    const inc = delta - lastDelta
    lastDelta = delta
    if (inc !== 0) emit('trim', props.clip.id, side, inc)
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    emit('drag-end', props.clip.id)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}
</script>

<style scoped>
.timeline-clip {
  position: absolute;
  top: 6px;
  bottom: 6px;
  left: 0;
  border-radius: 4px;
  cursor: grab;
  user-select: none;
  display: flex;
  align-items: stretch;
  border: 1.5px solid transparent;
  transition: box-shadow 0.15s, border-color 0.15s;
  overflow: hidden;
}

.timeline-clip:hover {
  border-color: var(--el-color-primary-light-5);
}

.timeline-clip.selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-7);
}

/* 三种轨道类型背景色 */
.timeline-clip.track-video {
  background: linear-gradient(135deg, #409eff 0%, #66b1ff 100%);
  color: #fff;
}

.timeline-clip.track-audio {
  background: linear-gradient(135deg, #67c23a 0%, #85ce61 100%);
  color: #fff;
}

.timeline-clip.track-subtitle {
  background: linear-gradient(135deg, #e6a23c 0%, #ebb563 100%);
  color: #fff;
}

.clip-content {
  flex: 1;
  padding: 4px 8px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  overflow: hidden;
  min-width: 0;
}

.clip-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.label-text {
  overflow: hidden;
  text-overflow: ellipsis;
}

.subtitle-text {
  font-size: 11px;
  line-height: 1.2;
  opacity: 0.95;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.transition-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  background: rgba(255, 255, 255, 0.25);
  padding: 1px 4px;
  border-radius: 3px;
  align-self: flex-start;
  margin-top: 2px;
}

.trim-handle {
  width: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: ew-resize;
  background: rgba(0, 0, 0, 0.18);
  font-size: 10px;
  flex-shrink: 0;
}

.trim-handle:hover {
  background: rgba(0, 0, 0, 0.35);
}

.trim-left {
  border-radius: 4px 0 0 4px;
}

.trim-right {
  border-radius: 0 4px 4px 0;
}
</style>
