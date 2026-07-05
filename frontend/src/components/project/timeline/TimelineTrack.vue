<!-- =====================================================
     时间线单轨道 TimelineTrack
     - 渲染一条轨道（视频/音频/字幕）
     - 左侧轨道头（图标 + 名称 + clip 数量）
     - 右侧轨道体（按 start_time 排序的片段列表）
     - 支持点击空白区域取消选中
     ===================================================== -->

<template>
  <div class="timeline-track" :class="`track-${trackType}`">
    <!-- 左侧：轨道头 -->
    <div class="track-header">
      <el-icon class="track-icon">
        <VideoCamera v-if="trackType === 'video'" />
        <Microphone v-else-if="trackType === 'audio'" />
        <Document v-else />
      </el-icon>
      <div class="track-meta">
        <div class="track-name">{{ trackName }}</div>
        <div class="track-count">{{ clips.length }} 个片段</div>
      </div>
    </div>

    <!-- 右侧：轨道体（含时间标尺对齐） -->
    <div
      class="track-body"
      :style="{ width: bodyWidth + 'px' }"
      @click.self="$emit('deselect')"
    >
      <!-- 空轨道提示 -->
      <div v-if="clips.length === 0" class="empty-track">
        <span>暂无{{ trackName }}片段</span>
      </div>

      <!-- 片段列表 -->
      <TimelineClip
        v-for="clip in sortedClips"
        :key="clip.id"
        :clip="clip"
        :pixels-per-second="pixelsPerSecond"
        :selected="clip.id === selectedClipId"
        :editable="editable"
        :style="{ left: (clip.start_time * pixelsPerSecond) + 'px' }"
        @select="$emit('select-clip', $event)"
        @drag="onClipDrag"
        @trim="onClipTrim"
        @drag-end="$emit('clip-updated', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { VideoCamera, Microphone, Document } from '@element-plus/icons-vue'
import TimelineClip from './TimelineClip.vue'
import type { TimelineClip as Clip, TimelineTrackType } from '@/types/project'

const props = defineProps<{
  trackType: TimelineTrackType
  trackIndex: number
  clips: Clip[]
  pixelsPerSecond: number
  totalDuration: number
  selectedClipId?: number | null
  editable?: boolean
}>()

const emit = defineEmits<{
  (e: 'deselect'): void
  (e: 'select-clip', clipId: number): void
  /** 片段拖拽产生增量（秒），由父组件更新 clip.start_time */
  (e: 'clip-drag', clipId: number, deltaSeconds: number): void
  /** 片段裁剪产生增量（秒） */
  (e: 'clip-trim', clipId: number, side: 'left' | 'right', deltaSeconds: number): void
  /** 拖拽/裁剪结束，触发保存 */
  (e: 'clip-updated', clipId: number): void
}>()

const trackName = computed(() => {
  const map: Record<TimelineTrackType, string> = {
    video: '视频轨',
    audio: '音频轨',
    subtitle: '字幕轨',
  }
  return map[props.trackType]
})

const sortedClips = computed(() =>
  [...props.clips].sort((a, b) => a.start_time - b.start_time),
)

// 轨道体宽度（至少铺满总时长 + 100px 缓冲）
const bodyWidth = computed(() => {
  const minByDuration = props.totalDuration * props.pixelsPerSecond + 100
  const minByClips = props.clips.length > 0
    ? Math.max(...props.clips.map((c) => c.start_time + c.duration)) * props.pixelsPerSecond + 100
    : 0
  return Math.max(minByDuration, minByClips, 600)
})

function onClipDrag(clipId: number, deltaSeconds: number) {
  emit('clip-drag', clipId, deltaSeconds)
}

function onClipTrim(clipId: number, side: 'left' | 'right', deltaSeconds: number) {
  emit('clip-trim', clipId, side, deltaSeconds)
}
</script>

<style scoped>
.timeline-track {
  display: flex;
  border-bottom: 1px solid var(--el-border-color-lighter);
  min-height: 64px;
}

.timeline-track:last-child {
  border-bottom: none;
}

.track-header {
  width: 120px;
  flex-shrink: 0;
  padding: 8px 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--el-fill-color-light);
  border-right: 1px solid var(--el-border-color-lighter);
}

.track-icon {
  font-size: 18px;
  color: var(--el-color-primary);
}

.track-video .track-icon {
  color: var(--el-color-primary);
}

.track-audio .track-icon {
  color: var(--el-color-success);
}

.track-subtitle .track-icon {
  color: var(--el-color-warning);
}

.track-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.track-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.track-count {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.track-body {
  position: relative;
  flex: 1;
  min-height: 52px;
  background-image: linear-gradient(
    to right,
    var(--el-border-color-lighter) 1px,
    transparent 1px
  );
  background-size: 50px 100%;
}

.empty-track {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>
