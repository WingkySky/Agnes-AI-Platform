<!-- =====================================================
     时间线片段 TimelineClip
     - 单个片段的视觉呈现（视频/音频/字幕三种 track_type）
     - 拖拽整体移动、左右手柄裁剪 trim_start/trim_end
     - 选中态 + 转场标记（none/fade/slide/wipe/dissolve）
     - 拖拽时吸附（snap）到：0 时间点 / 播放头 / 同轨其他片段边界
     - 拖拽时显示新起始时间读数 tooltip
     - 拖拽时与同轨其他片段防止重叠
     - 与父组件通过 emit 交互，不直接调用 store
     ===================================================== -->

<template>
  <div
    class="timeline-clip"
    :class="[`track-${clip.track_type}`, { selected: selected, 'playing-clip': isPlayingClip }]"
    :style="clipStyle"
    @mousedown="onDragStart"
    @click.stop="$emit('select', clip.id)"
    @contextmenu.prevent="onContextMenu"
  >
    <!-- 左侧裁剪手柄 -->
    <div
      v-if="editable"
      class="trim-handle trim-left"
      @mousedown.stop="onTrimStart('left', $event)"
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
      @mousedown.stop="onTrimStart('right', $event)"
    >
      <el-icon><DArrowRight /></el-icon>
    </div>

    <!-- 拖拽/裁剪读数 tooltip -->
    <div v-if="tooltipVisible" class="drag-tooltip" :style="tooltipStyle">
      {{ tooltipText }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
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
  /** 是否为当前播放中的片段（高亮显示） */
  isPlayingClip?: boolean
  /** 同轨其他片段（含自身，用于 snap 与防重叠计算），按 start_time 排序 */
  siblingClips?: TimelineClip[]
  /** 播放头时间（秒），用于拖拽吸附 */
  playheadTime?: number
}>()

const emit = defineEmits<{
  (e: 'select', clipId: number): void
  /** 拖动整体片段，delta 为秒数（正/负） */
  (e: 'drag', clipId: number, deltaSeconds: number): void
  /** 裁剪，side='left' 调整 trim_start，side='right' 调整 trim_end，delta 为秒数 */
  (e: 'trim', clipId: number, side: 'left' | 'right', deltaSeconds: number): void
  /** 拖拽结束（提交保存） */
  (e: 'drag-end', clipId: number): void
  /** 右键菜单：带鼠标坐标用于定位菜单 */
  (e: 'context-menu', clipId: number, x: number, y: number): void
}>()

// 右键菜单：阻止浏览器默认菜单，emit 给父组件定位显示
function onContextMenu(e: MouseEvent) {
  emit('context-menu', props.clip.id, e.clientX, e.clientY)
}

// ---------- 吸附阈值（按像素换算成秒） ----------
// 鼠标距离候选点 8 像素以内时吸附
const SNAP_PIXELS = 8
const snapThresholdSeconds = computed(() => SNAP_PIXELS / props.pixelsPerSecond)

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

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  const cs = Math.floor((seconds - Math.floor(seconds)) * 100)
  return `${m}:${s.toString().padStart(2, '0')}.${cs.toString().padStart(2, '0')}`
}

// ---------- 拖拽 tooltip 状态 ----------
const tooltipVisible = ref(false)
const tooltipText = ref('')
const tooltipStyle = ref<Record<string, string>>({})
// 拖拽过程中实时显示新的起始时间；裁剪过程显示新边界时间
function showDragTooltip(text: string) {
  tooltipVisible.value = true
  tooltipText.value = text
  // 显示在片段顶部中央
  tooltipStyle.value = { left: '50%', transform: 'translateX(-50%)' }
}
function hideDragTooltip() {
  tooltipVisible.value = false
}

// ---------- snap 候选点收集 ----------
// 返回当前轨道上所有可作为吸附目标的候选时间点（排除当前片段自身）
function collectSnapCandidates(excludeClipId: number): number[] {
  const candidates: number[] = [0]
  if (typeof props.playheadTime === 'number' && props.playheadTime >= 0) {
    candidates.push(props.playheadTime)
  }
  const sibs = props.siblingClips ?? []
  for (const c of sibs) {
    if (c.id === excludeClipId) continue
    candidates.push(c.start_time)
    candidates.push(c.start_time + c.duration)
  }
  return candidates
}

// 找到最接近 target 的候选点，若在阈值内返回该候选点，否则返回 null
function findSnap(target: number, candidates: number[]): number | null {
  let best: number | null = null
  let bestDist = Infinity
  const threshold = snapThresholdSeconds.value
  for (const c of candidates) {
    const d = Math.abs(c - target)
    if (d < bestDist && d <= threshold) {
      bestDist = d
      best = c
    }
  }
  return best
}

// 防重叠：将 newStart 限制在不与同轨其他片段重叠的范围内
// 返回调整后的 newStart
function clampToAvoidOverlap(
  newStart: number,
  duration: number,
  excludeClipId: number,
): number {
  const sibs = props.siblingClips ?? []
  let lo = 0 // 左边界（前一片段 end 或 0）
  let hi = Infinity // 右边界（后一片段 start）
  for (const c of sibs) {
    if (c.id === excludeClipId) continue
    const cEnd = c.start_time + c.duration
    if (cEnd <= newStart) {
      // 该片段在 newStart 之前，作为左边界候选
      if (cEnd > lo) lo = cEnd
    } else if (c.start_time >= newStart) {
      // 该片段在 newStart 之后，作为右边界候选
      if (c.start_time < hi) hi = c.start_time
    } else {
      // 已经发生重叠（newStart 落在某片段内部），以该片段时间为界
      // 选择更近的一端作为避让目标
      const distToLeft = newStart - c.start_time
      const distToRight = cEnd - newStart
      if (distToLeft < distToRight) {
        // 退到该片段左侧（前一片段 end）
        hi = Math.min(hi, c.start_time)
      } else {
        // 退到该片段右侧（后一片段 start）
        lo = Math.max(lo, cEnd)
      }
    }
  }
  // newStart 不能小于 lo，且 newStart + duration 不能大于 hi
  const clamped = Math.max(lo, Math.min(newStart, hi - duration))
  return Math.max(0, clamped)
}

// ---------- 拖拽（整体移动） ----------
function onDragStart(e: MouseEvent) {
  if (!props.editable) return
  e.preventDefault()
  const startX = e.clientX
  const origStart = props.clip.start_time
  const duration = props.clip.duration
  let lastAppliedDelta = 0
  let moved = false

  const candidates = collectSnapCandidates(props.clip.id)

  const onMove = (ev: MouseEvent) => {
    const dx = ev.clientX - startX
    if (Math.abs(dx) > 2) moved = true
    // 鼠标累计位移对应的秒数
    const rawDelta = dx / props.pixelsPerSecond
    let newStart = origStart + rawDelta

    // 1. snap 吸附
    const snapped = findSnap(newStart, candidates)
    if (snapped !== null) {
      newStart = snapped
    }

    // 2. 防重叠 clamp
    newStart = clampToAvoidOverlap(newStart, duration, props.clip.id)

    // 3. 转成相对父组件已应用状态的增量
    const newDelta = newStart - origStart
    const inc = newDelta - lastAppliedDelta
    lastAppliedDelta = newDelta
    if (inc !== 0) emit('drag', props.clip.id, inc)

    // 4. 显示 tooltip（注意：父组件已经按增量更新了 clip.start_time，所以这里用 newStart 即时显示）
    showDragTooltip(`起始 ${formatTime(newStart)}`)
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    hideDragTooltip()
    if (moved) emit('drag-end', props.clip.id)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ---------- 裁剪（trim_start / trim_end） ----------
function onTrimStart(side: 'left' | 'right', e: MouseEvent) {
  if (!props.editable) return
  e.preventDefault()
  e.stopPropagation()
  const startX = e.clientX
  const origTrimStart = props.clip.trim_start
  const origDuration = props.clip.duration
  const origStart = props.clip.start_time
  const sourceDur = props.clip.source_duration_ms
    ? props.clip.source_duration_ms / 1000
    : Infinity
  let lastAppliedDelta = 0

  // 裁剪 snap 候选：播放头 + 同轨其他片段边界
  const candidates: number[] = []
  if (typeof props.playheadTime === 'number' && props.playheadTime >= 0) {
    candidates.push(props.playheadTime)
  }
  for (const c of props.siblingClips ?? []) {
    if (c.id === props.clip.id) continue
    candidates.push(c.start_time)
    candidates.push(c.start_time + c.duration)
  }

  const onMove = (ev: MouseEvent) => {
    const dx = ev.clientX - startX
    const rawDelta = dx / props.pixelsPerSecond
    let appliedDelta = rawDelta

    // 对左侧裁剪：snap 目标是新的 trim_start 对应的时间线位置 = origStart + delta
    // 对右侧裁剪：snap 目标是新的 end = origStart + origDuration + delta
    const snapTarget = side === 'left'
      ? origStart + appliedDelta
      : origStart + origDuration + appliedDelta
    const snapped = findSnap(snapTarget, candidates)
    if (snapped !== null) {
      appliedDelta = side === 'left'
        ? snapped - origStart
        : snapped - (origStart + origDuration)
    }

    // 源素材时长边界校验
    if (side === 'left') {
      // trim_start 不能小于 0，不能超过 sourceDur - 0.1 - origDuration
      const newTrim = Math.max(0, origTrimStart + appliedDelta)
      const maxTrim = Math.max(0, sourceDur - 0.1) - origDuration
      const clampedTrim = Math.min(newTrim, Math.max(0, maxTrim))
      appliedDelta = clampedTrim - origTrimStart
    } else {
      // 右侧不能超过源素材剩余可用时长
      const remaining = sourceDur === Infinity ? Infinity : sourceDur - origTrimStart
      const newDuration = Math.max(0.1, origDuration + appliedDelta)
      const clampedDuration = Math.min(newDuration, remaining)
      appliedDelta = clampedDuration - origDuration
    }

    const inc = appliedDelta - lastAppliedDelta
    lastAppliedDelta = appliedDelta
    if (inc !== 0) emit('trim', props.clip.id, side, inc)

    // 显示 tooltip：左侧显示新 trim_start，右侧显示新 duration
    if (side === 'left') {
      showDragTooltip(`入点 ${formatTime(origTrimStart + appliedDelta)}`)
    } else {
      showDragTooltip(`时长 ${formatTime(origDuration + appliedDelta)}`)
    }
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    hideDragTooltip()
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

/* 播放中片段高亮（脉冲动画提示当前播放位置） */
.timeline-clip.playing-clip {
  border-color: var(--el-color-success);
  box-shadow: 0 0 0 2px var(--el-color-success-light-7), 0 0 12px var(--el-color-success-light-5);
  animation: clip-pulse 1.5s ease-in-out infinite;
}

@keyframes clip-pulse {
  0%, 100% { box-shadow: 0 0 0 2px var(--el-color-success-light-7), 0 0 8px var(--el-color-success-light-5); }
  50% { box-shadow: 0 0 0 2px var(--el-color-success-light-5), 0 0 16px var(--el-color-success-light-3); }
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

/* 拖拽/裁剪读数 tooltip */
.drag-tooltip {
  position: absolute;
  top: -22px;
  background: var(--el-color-primary);
  color: #fff;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-family: 'Menlo', monospace;
  white-space: nowrap;
  pointer-events: none;
  z-index: 20;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
}

.drag-tooltip::after {
  content: '';
  position: absolute;
  bottom: -4px;
  left: 50%;
  transform: translateX(-50%);
  border: 4px solid transparent;
  border-top-color: var(--el-color-primary);
  border-bottom: 0;
}
</style>
