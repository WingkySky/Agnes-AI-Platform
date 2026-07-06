<!-- =====================================================
     时间线核心编辑器 TimelineEditor
     - 时间标尺（按秒刻度，自适应缩放）
     - 多轨道区（视频/音频/字幕，按 track_index 分组）
     - 播放头（点击标尺跳转 / 拖拽移动）
     - 缩放控件（pixelsPerSecond 调节）
     - 顶部工具条集成剪辑操作（分割/波纹删除/帧步进/播放控制）
       剪辑按钮紧贴时间线，避免被预览区割裂
     - 本地维护 clipDrafts 副本，拖拽/裁剪实时更新；结束时 emit 保存
     ===================================================== -->

<template>
  <div class="timeline-editor">
    <!-- 顶部工具条：缩放 + 剪辑操作 + 播放头读数 -->
    <div class="zoom-bar">
      <!-- 左侧：缩放控件 -->
      <span class="zoom-label">缩放</span>
      <el-slider
        v-model="zoomLevel"
        :min="20"
        :max="200"
        :step="10"
        style="width: 140px"
        @input="onZoom"
      />
      <span class="zoom-value">{{ pixelsPerSecond }} px/s</span>

      <el-divider direction="vertical" />

      <!-- 撤销 / 重做 -->
      <el-tooltip content="撤销（Ctrl+Z）" placement="bottom">
        <span>
          <el-button
            size="small"
            :icon="RefreshLeft"
            :disabled="!canUndo"
            @click="$emit('undo')"
          />
        </span>
      </el-tooltip>
      <el-tooltip content="重做（Ctrl+Shift+Z）" placement="bottom">
        <span>
          <el-button
            size="small"
            :icon="RefreshRight"
            :disabled="!canRedo"
            @click="$emit('redo')"
          />
        </span>
      </el-tooltip>

      <el-divider direction="vertical" />

      <!-- 添加片段 -->
      <el-button size="small" type="success" :icon="Plus" @click="$emit('add-clip')">添加片段</el-button>

      <el-divider direction="vertical" />

      <!-- 中间：剪辑操作按钮组（紧贴时间线） -->
      <el-button-group>
        <el-button size="small" :icon="VideoPause" @click="seekTo(0)" title="回到起点">起点</el-button>
        <el-button size="small" :icon="VideoPlay" @click="$emit('play')" title="播放/暂停">播放</el-button>
      </el-button-group>

      <el-button-group>
        <el-button
          size="small"
          :icon="Back"
          @click="$emit('seek-by-frames', -1)"
          title="后退 1 帧（←）"
        />
        <el-button
          size="small"
          :icon="Right"
          @click="$emit('seek-by-frames', 1)"
          title="前进 1 帧（→）"
        />
      </el-button-group>

      <el-tooltip content="在播放头位置分割选中片段（Ctrl+K）" placement="bottom">
        <span>
          <el-button
            size="small"
            type="primary"
            :icon="Switch"
            :disabled="!editable || !hasSelectedClip"
            @click="$emit('split-at-playhead')"
          >分割</el-button>
        </span>
      </el-tooltip>

      <el-tooltip content="波纹删除选中片段，同轨后续自动前移（Delete）" placement="bottom">
        <span>
          <el-button
            size="small"
            type="danger"
            :icon="Delete"
            :disabled="!editable || !hasSelectedClip"
            @click="$emit('ripple-delete')"
          >波纹删除</el-button>
        </span>
      </el-tooltip>

      <!-- 右侧：播放头时间读数 -->
      <span class="playhead-label">播放头：{{ formatTime(playheadTime) }}</span>
    </div>

    <!-- 滚动容器 -->
    <div ref="scrollEl" class="editor-scroll">
      <!-- 标记旗帜条（标尺上方） -->
      <MarkersRuler
        v-if="markers && markers.length"
        :markers="markers"
        :pixels-per-second="pixelsPerSecond"
        :total-width="rulerWidth"
        @seek="$emit('marker-seek', $event)"
        @delete="$emit('marker-delete', $event)"
      />
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
          :playhead-time="playheadTime"
          :muted="trackStates ? !!(trackStates[`${trackType}:0`]?.muted) : false"
          :locked="trackStates ? !!(trackStates[`${trackType}:0`]?.locked) : false"
          @deselect="$emit('deselect')"
          @select-clip="$emit('select-clip', $event)"
          @clip-drag="onClipDrag"
          @clip-trim="onClipTrim"
          @clip-updated="$emit('clip-updated', $event)"
          @context-menu="(clipId: number, x: number, y: number) => $emit('context-menu', clipId, x, y)"
          @toggle-mute="$emit('toggle-track-mute', trackType, 0)"
          @toggle-lock="$emit('toggle-track-lock', trackType, 0)"
          @drop-media="(item: MediaLibraryItem, tt: string, ti: number, st: number) => $emit('drop-media', item, tt, ti, st)"
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
import {
  VideoPlay, VideoPause, Film, Switch, Delete, Back, Right,
  RefreshLeft, RefreshRight, Plus,
} from '@element-plus/icons-vue'
import TimelineTrack from './TimelineTrack.vue'
import MarkersRuler from './MarkersRuler.vue'
import type { MediaLibraryItem, ProjectMarker, TimelineClip, TimelineTrackType, TrackState } from '@/types/project'

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
  /** 是否可撤销 */
  canUndo?: boolean
  /** 是否可重做 */
  canRedo?: boolean
  /** 标记列表（用于标尺上方旗帜渲染） */
  markers?: ProjectMarker[]
  /** 轨道状态（用于轨道头部 M/L 按钮） */
  trackStates?: Record<string, TrackState>
}>()

const emit = defineEmits<{
  (e: 'select-clip', clipId: number): void
  (e: 'deselect'): void
  (e: 'clip-drag', clipId: number, deltaSeconds: number): void
  (e: 'clip-trim', clipId: number, side: 'left' | 'right', deltaSeconds: number): void
  (e: 'clip-updated', clipId: number): void
  (e: 'play'): void
  (e: 'seek', time: number): void
  /** 在播放头处分割选中片段 */
  (e: 'split-at-playhead'): void
  /** 波纹删除选中片段 */
  (e: 'ripple-delete'): void
  /** 帧步进（正/负帧数） */
  (e: 'seek-by-frames', deltaFrames: number): void
  /** 右键菜单 */
  (e: 'context-menu', clipId: number, x: number, y: number): void
  /** 撤销 */
  (e: 'undo'): void
  /** 重做 */
  (e: 'redo'): void
  /** 添加片段 */
  (e: 'add-clip'): void
  /** 拖拽素材到轨道 */
  (e: 'drop-media', item: MediaLibraryItem, trackType: string, trackIndex: number, startTime: number): void
  /** 轨道静音切换 */
  (e: 'toggle-track-mute', trackType: string, trackIndex: number): void
  /** 轨道锁定切换 */
  (e: 'toggle-track-lock', trackType: string, trackIndex: number): void
  /** 标记：点击旗帜跳转 */
  (e: 'marker-seek', time: number): void
  /** 标记：右键删除 */
  (e: 'marker-delete', markerId: number): void
}>()

// 是否有选中片段（控制分割/波纹删除按钮启用）
const hasSelectedClip = computed(() => props.selectedClipId != null)

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
  const x = e.clientX - rect.left
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
  gap: 8px;
  padding: 8px 12px;
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
  min-width: 56px;
}

.playhead-label {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: 'Menlo', monospace;
  background: var(--el-fill-color);
  padding: 2px 8px;
  border-radius: 3px;
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
