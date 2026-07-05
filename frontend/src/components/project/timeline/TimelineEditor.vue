<!-- =====================================================
     时间线核心编辑器 TimelineEditor
     - 时间标尺（按秒刻度，自适应缩放）
     - 多轨道区（视频/音频/字幕，按 track_index 分组）
     - 播放头（点击标尺跳转 / 拖拽移动）
     - 缩放控件（pixelsPerSecond 调节）
     - 本地维护 clipDrafts 副本，拖拽/裁剪实时更新；结束时 emit 保存
     ===================================================== -->

<template>
  <div class="timeline-editor">
    <!-- 缩放控件 -->
    <div class="zoom-bar">
      <span class="zoom-label">缩放</span>
      <el-slider
        v-model="zoomLevel"
        :min="20"
        :max="200"
        :step="10"
        style="width: 180px"
        @input="onZoom"
      />
      <span class="zoom-value">{{ pixelsPerSecond }} px/s</span>
      <el-divider direction="vertical" />
      <span class="playhead-label">播放头：{{ formatTime(playheadTime) }}</span>
      <el-button-group>
        <el-button size="small" :icon="VideoPause" @click="seekTo(0)">回起点</el-button>
        <el-button size="small" :icon="VideoPlay" @click="$emit('play')">播放</el-button>
      </el-button-group>
    </div>

    <!-- 滚动容器 -->
    <div ref="scrollEl" class="editor-scroll">
      <!-- 时间标尺 -->
      <div class="ruler" :style="{ width: rulerWidth + 'px' }" @mousedown="onRulerClick">
        <div
          v-for="tick in ticks"
          :key="tick.second"
          class="tick"
          :class="{ major: tick.major }"
          :style="{ left: tick.position + 'px' }"
        >
          <span v-if="tick.major" class="tick-label">{{ formatTime(tick.second) }}</span>
        </div>
        <!-- 播放头 -->
        <div
          class="playhead"
          :style="{ left: playheadPosition + 'px' }"
          @mousedown.stop="onPlayheadDrag"
        >
          <div class="playhead-handle" />
          <div class="playhead-line" />
        </div>
      </div>

      <!-- 三类轨道（按 track_type 分组渲染） -->
      <div v-for="trackType in trackTypes" :key="trackType" class="track-row">
        <TimelineTrack
          :track-type="trackType"
          :track-index="0"
          :clips="clipsForTrack(trackType)"
          :pixels-per-second="pixelsPerSecond"
          :total-duration="totalDuration"
          :selected-clip-id="selectedClipId"
          :active-clip-id="activeClipIdForTrack(trackType)"
          :editable="editable"
          @deselect="$emit('deselect')"
          @select-clip="$emit('select-clip', $event)"
          @clip-drag="onClipDrag"
          @clip-trim="onClipTrim"
          @clip-updated="$emit('clip-updated', $event)"
        />
      </div>

      <!-- 空状态 -->
      <div v-if="allClips.length === 0" class="empty-state">
        <el-icon :size="32"><Film /></el-icon>
        <span>暂无时间线数据，请先点击「初始化时间线」</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { VideoPlay, VideoPause, Film } from '@element-plus/icons-vue'
import TimelineTrack from './TimelineTrack.vue'
import type { TimelineClip, TimelineTrackType } from '@/types/project'

const props = defineProps<{
  /** 所有片段（含三种 track_type） */
  clips: TimelineClip[]
  totalDuration: number
  selectedClipId?: number | null
  editable?: boolean
  /** 受控播放头时间（秒），由父组件传入；不传则使用内部状态 */
  playheadTime?: number
  /** 当前播放中的视频片段 ID（高亮显示） */
  activeVideoClipId?: number | null
  /** 当前播放中的音频片段 ID */
  activeAudioClipId?: number | null
  /** 当前播放中的字幕片段 ID */
  activeSubtitleClipId?: number | null
}>()

const emit = defineEmits<{
  (e: 'select-clip', clipId: number): void
  (e: 'deselect'): void
  (e: 'clip-drag', clipId: number, deltaSeconds: number): void
  (e: 'clip-trim', clipId: number, side: 'left' | 'right', deltaSeconds: number): void
  (e: 'clip-updated', clipId: number): void
  (e: 'play'): void
  (e: 'seek', time: number): void
}>()

const trackTypes: TimelineTrackType[] = ['video', 'audio', 'subtitle']

// ---------- 缩放 ----------
const zoomLevel = ref(60) // 滑块值
const pixelsPerSecond = ref(60)

function onZoom(val: number | number[]) {
  const v = Array.isArray(val) ? val[0] : val
  pixelsPerSecond.value = v
}

// ---------- 时间标尺 ----------
const rulerWidth = computed(() => {
  return Math.max(props.totalDuration * pixelsPerSecond.value + 200, 800)
})

const ticks = computed(() => {
  const result: Array<{ second: number; position: number; major: boolean }> = []
  const pps = pixelsPerSecond.value
  // 决定主刻度间隔（保证主刻度间距 >= 80px）
  let majorStep = 1
  if (pps * 1 < 80) majorStep = 5
  if (pps * 5 < 80) majorStep = 10
  if (pps * 10 < 80) majorStep = 30
  if (pps * 30 < 80) majorStep = 60
  const totalSec = Math.ceil(props.totalDuration) + 5
  for (let s = 0; s <= totalSec; s++) {
    const major = s % majorStep === 0
    if (major || pps >= 100) {
      result.push({
        second: s,
        position: s * pps,
        major,
      })
    }
  }
  return result
})

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

// ---------- 播放头 ----------
// 受控模式：优先使用 props.playheadTime（父组件驱动，如预览调度）
// 非受控模式：props.playheadTime 未传时使用内部状态
const internalPlayheadTime = ref(0)
const playheadTime = computed({
  get: () => {
    return props.playheadTime !== undefined ? props.playheadTime : internalPlayheadTime.value
  },
  set: (val: number) => {
    if (props.playheadTime === undefined) {
      internalPlayheadTime.value = val
    }
    // 受控模式下 set 不直接修改（由父组件通过 props 更新），但仍 emit seek 事件
  },
})
const playheadPosition = computed(() => playheadTime.value * pixelsPerSecond.value)

function onRulerClick(e: MouseEvent) {
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  const x = e.clientX - rect.left + (scrollEl.value?.scrollLeft ?? 0)
  const t = Math.max(0, x / pixelsPerSecond.value)
  internalPlayheadTime.value = t
  emit('seek', t)
}

function onPlayheadDrag(e: MouseEvent) {
  e.preventDefault()
  const onMove = (ev: MouseEvent) => {
    const rect = scrollEl.value?.getBoundingClientRect()
    if (!rect) return
    const x = ev.clientX - rect.left + (scrollEl.value?.scrollLeft ?? 0)
    const t = Math.max(0, x / pixelsPerSecond.value)
    internalPlayheadTime.value = t
    emit('seek', t)
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function seekTo(t: number) {
  internalPlayheadTime.value = t
  emit('seek', t)
}

// 外部 seek 事件同步（仅非受控模式生效）
watch(() => props.totalDuration, () => {
  if (internalPlayheadTime.value > props.totalDuration) {
    internalPlayheadTime.value = props.totalDuration
  }
})

// ---------- 片段分组 ----------
const allClips = computed(() => props.clips)

function clipsForTrack(type: TimelineTrackType): TimelineClip[] {
  return props.clips.filter((c) => c.track_type === type)
}

// 根据轨道类型返回当前播放中的片段 ID（用于高亮）
function activeClipIdForTrack(type: TimelineTrackType): number | null {
  if (type === 'video') return props.activeVideoClipId ?? null
  if (type === 'audio') return props.activeAudioClipId ?? null
  if (type === 'subtitle') return props.activeSubtitleClipId ?? null
  return null
}

// ---------- 拖拽 / 裁剪代理 ----------
function onClipDrag(clipId: number, deltaSeconds: number) {
  emit('clip-drag', clipId, deltaSeconds)
}

function onClipTrim(clipId: number, side: 'left' | 'right', deltaSeconds: number) {
  emit('clip-trim', clipId, side, deltaSeconds)
}

const scrollEl = ref<HTMLElement | null>(null)
</script>

<style scoped>
.timeline-editor {
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  overflow: hidden;
}

.zoom-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-wrap: wrap;
}

.zoom-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.zoom-value {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: 'Menlo', monospace;
  min-width: 60px;
}

.playhead-label {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: 'Menlo', monospace;
}

.editor-scroll {
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
  min-height: 280px;
}

.ruler {
  position: relative;
  height: 28px;
  background: var(--el-fill-color-lighter);
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
  user-select: none;
}

.tick {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--el-border-color);
}

.tick.major {
  background: var(--el-text-color-placeholder);
}

.tick-label {
  position: absolute;
  top: 4px;
  left: 4px;
  font-size: 10px;
  color: var(--el-text-color-secondary);
  font-family: 'Menlo', monospace;
}

.playhead {
  position: absolute;
  top: 0;
  bottom: -2000px;
  width: 2px;
  background: var(--el-color-danger);
  z-index: 10;
  pointer-events: none;
}

.playhead-handle {
  position: absolute;
  top: 0;
  left: -5px;
  width: 12px;
  height: 12px;
  background: var(--el-color-danger);
  border-radius: 50%;
  pointer-events: auto;
  cursor: ew-resize;
}

.playhead-line {
  position: absolute;
  top: 12px;
  left: 0;
  bottom: 0;
  width: 2px;
  background: var(--el-color-danger);
}

.track-row {
  display: flex;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.track-row:last-child {
  border-bottom: none;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 48px 0;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}
</style>
