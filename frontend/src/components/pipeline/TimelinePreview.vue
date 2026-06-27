<!--
  TimelinePreview —— 可视化时间轴预览组件
  - 横向时间轴，按时间比例显示每个字幕片段
  - 每个片段显示场景序号 + 字幕文本（截断）
  - 鼠标 hover 显示完整字幕 + 时长
  - 点击某片段 emit 'seek' 事件，父组件可跳转视频到对应时间
  - 当前播放位置高亮（可选，通过 current-time prop 同步）
-->
<template>
  <div class="timeline-preview">
    <!-- 标题栏 -->
    <div class="timeline-header">
      <span class="timeline-title">{{ t('timelinePreview.title') }}</span>
      <span v-if="totalDuration > 0" class="timeline-duration">
        {{ formatDuration(totalDuration) }}
      </span>
    </div>

    <!-- 空状态 -->
    <el-empty v-if="!subtitles.length" :description="t('timelinePreview.empty')" :image-size="60" />

    <!-- 时间轴主体（按时间比例横向排布） -->
    <div v-else class="timeline-track" @click="onTrackClick">
      <!-- 时间刻度（0% / 25% / 50% / 75% / 100%） -->
      <div class="timeline-scale">
        <span v-for="pct in [0, 25, 50, 75, 100]" :key="pct" class="scale-mark" :style="{ left: pct + '%' }">
          {{ formatDuration((totalDuration * pct) / 100) }}
        </span>
      </div>

      <!-- 字幕片段块（按 start/end 计算宽度和位置） -->
      <div
        v-for="(sub, idx) in subtitles"
        :key="idx"
        class="segment-block"
        :class="{
          'segment-block--active': isActive(sub),
          'segment-block--empty': !sub.text,
        }"
        :style="segmentStyle(sub)"
        @click.stop="onSegmentClick(sub)"
      >
        <!-- 场景序号 -->
        <span class="segment-index">#{{ sub.scene_index ?? idx }}</span>
        <!-- 字幕文本（截断显示） -->
        <span class="segment-text">{{ sub.text || t('timelinePreview.noSubtitle') }}</span>
        <!-- tooltip：完整字幕 + 时长 -->
        <el-tooltip placement="top" :show-after="200">
          <template #content>
            <div class="segment-tooltip">
              <div class="tooltip-line">
                <strong>{{ t('timelinePreview.sceneLabel', { n: sub.scene_index ?? idx }) }}</strong>
              </div>
              <div class="tooltip-line">
                {{ t('timelinePreview.durationLabel', { s: formatDuration((sub.end - sub.start)) }) }}
              </div>
              <div class="tooltip-line tooltip-time">
                {{ formatTime(sub.start) }} → {{ formatTime(sub.end) }}
              </div>
              <div class="tooltip-line tooltip-text">{{ sub.text || t('timelinePreview.noSubtitle') }}</div>
            </div>
          </template>
          <span class="segment-tooltip-trigger" />
        </el-tooltip>
      </div>

      <!-- 播放游标（current-time 同步时显示） -->
      <div
        v-if="typeof currentTime === 'number' && currentTime > 0 && totalDuration > 0"
        class="play-cursor"
        :style="{ left: playCursorPercent + '%' }"
      >
        <div class="cursor-line" />
        <div class="cursor-handle" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElEmpty, ElTooltip } from 'element-plus'
import { useI18n } from '@/i18n'

/** 字幕条目结构（与后端 ffmpeg_composite 输出的 subtitles 字段一致） */
interface SubtitleEntry {
  index: number
  scene_index?: number
  start: number
  end: number
  text: string
}

const props = defineProps<{
  /** 字幕条目列表 */
  subtitles: SubtitleEntry[]
  /** 总时长（秒）；不传则取最后一条 end */
  duration?: number
  /** 当前播放时间（秒），用于游标位置 */
  currentTime?: number
}>()

const emit = defineEmits<{
  (e: 'seek', time: number): void
  (e: 'select', sub: SubtitleEntry): void
}>()

const { t } = useI18n()

// 总时长：优先用 prop，否则取最后一条字幕的 end
const totalDuration = computed(() => {
  if (props.duration && props.duration > 0) return props.duration
  if (!props.subtitles.length) return 0
  return Math.max(...props.subtitles.map(s => s.end || 0))
})

// 计算单个片段的样式（位置 + 宽度按比例）
function segmentStyle(sub: SubtitleEntry): Record<string, string> {
  const total = totalDuration.value
  if (total <= 0) return { left: '0%', width: '100%' }
  const leftPct = (sub.start / total) * 100
  const widthPct = Math.max(((sub.end - sub.start) / total) * 100, 2) // 最小 2% 宽度
  return {
    left: leftPct + '%',
    width: widthPct + '%',
  }
}

// 判断片段是否在当前播放区间
function isActive(sub: SubtitleEntry): boolean {
  if (typeof props.currentTime !== 'number') return false
  return props.currentTime >= sub.start && props.currentTime < sub.end
}

// 播放游标位置百分比
const playCursorPercent = computed(() => {
  if (totalDuration.value <= 0) return 0
  return Math.min((props.currentTime || 0) / totalDuration.value * 100, 100)
})

// 点击整个时间轴：按点击位置计算时间，emit seek
function onTrackClick(ev: MouseEvent) {
  if (totalDuration.value <= 0) return
  const target = ev.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  const pct = (ev.clientX - rect.left) / rect.width
  const time = Math.max(0, Math.min(pct * totalDuration.value, totalDuration.value))
  emit('seek', time)
}

// 点击单个片段：跳到该片段开头
function onSegmentClick(sub: SubtitleEntry) {
  emit('seek', sub.start)
  emit('select', sub)
}

// ================ 格式化工具 ================

function formatDuration(seconds: number): string {
  if (!seconds || seconds < 0) return '0:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatTime(seconds: number): string {
  if (!seconds || seconds < 0) return '00:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}
</script>

<style scoped>
.timeline-preview {
  width: 100%;
  background: var(--agnes-bg-card);
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  padding: 12px 16px;
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.timeline-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--agnes-text-primary);
}
.timeline-duration {
  font-size: 12px;
  color: var(--agnes-text-secondary);
}

/* 时间轴主体 */
.timeline-track {
  position: relative;
  height: 60px;
  background: var(--agnes-bg-page);
  border-radius: 6px;
  margin-top: 20px; /* 给刻度留位置 */
  cursor: pointer;
  overflow: hidden;
}

/* 时间刻度 */
.timeline-scale {
  position: absolute;
  top: -18px;
  left: 0;
  right: 0;
  height: 16px;
}
.scale-mark {
  position: absolute;
  transform: translateX(-50%);
  font-size: 10px;
  color: var(--agnes-text-muted);
  white-space: nowrap;
}

/* 单个片段块 */
.segment-block {
  position: absolute;
  top: 6px;
  bottom: 6px;
  background: var(--agnes-primary);
  color: #fff;
  border-radius: 4px;
  padding: 4px 6px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
  cursor: pointer;
  transition: filter 0.2s, transform 0.2s;
  min-width: 24px;
}
.segment-block:hover {
  filter: brightness(1.1);
  transform: translateY(-1px);
}
.segment-block--active {
  outline: 2px solid var(--agnes-warning, #f0a020);
  outline-offset: -2px;
  z-index: 2;
}
.segment-block--empty {
  background: var(--agnes-bg-page);
  border: 1px dashed var(--agnes-border);
  color: var(--agnes-text-muted);
}
.segment-index {
  font-size: 10px;
  opacity: 0.85;
  font-weight: 500;
}
.segment-text {
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.segment-tooltip-trigger {
  position: absolute;
  inset: 0;
}

/* 播放游标 */
.play-cursor {
  position: absolute;
  top: 0;
  bottom: 0;
  pointer-events: none;
  z-index: 3;
  transform: translateX(-50%);
}
.cursor-line {
  width: 2px;
  height: 100%;
  background: var(--agnes-danger, #f56c6c);
  margin: 0 auto;
}
.cursor-handle {
  position: absolute;
  top: -4px;
  left: 50%;
  transform: translateX(-50%);
  width: 10px;
  height: 10px;
  background: var(--agnes-danger, #f56c6c);
  border-radius: 50%;
}

/* tooltip 内容 */
.segment-tooltip {
  max-width: 280px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tooltip-line {
  font-size: 12px;
}
.tooltip-time {
  color: #c0c4cc;
  font-size: 11px;
}
.tooltip-text {
  margin-top: 4px;
  line-height: 1.5;
  word-break: break-all;
}
</style>
