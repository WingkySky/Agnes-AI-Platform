<!--
  TimelinePreview —— 可视化时间轴预览组件
  - 横向时间轴，按时间比例显示每个字幕片段
  - 每个片段显示场景序号 + 字幕文本（截断）
  - 鼠标 hover 显示完整字幕 + 时长
  - 点击某片段 emit 'seek' 事件，父组件可跳转视频到对应时间
  - 当前播放位置高亮（可选，通过 current-time prop 同步）
  - 相邻片段之间渲染转场入口按钮（hasTransitionStep 控制显隐）
    点击按钮弹出 TransitionEditor，配置变更通过 update:transitions 同步给父组件
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

      <!-- 转场入口按钮：相邻片段之间，通过 hasTransitionStep 控制显隐 -->
      <template v-if="hasTransitionStep && subtitles.length > 1">
        <el-tooltip
          v-for="i in subtitles.length - 1"
          :key="`transition-${i}`"
          placement="top"
          :show-after="200"
        >
          <template #content>
            <div class="segment-tooltip">
              <div class="tooltip-line">
                <strong>{{ t('pipeline.transition.entryTip', { n: i }) }}</strong>
              </div>
              <div v-if="getTransition(i - 1)" class="tooltip-line">
                {{ t('pipeline.transition.currentLabel') }}: {{ getTransitionLabel(getTransition(i - 1)!) }}
              </div>
              <div v-else class="tooltip-line tooltip-time">
                {{ t('pipeline.transition.hardCutHint') }}
              </div>
            </div>
          </template>
          <button
            type="button"
            class="transition-entry"
            :class="{ 'transition-entry--active': !!getTransition(i - 1) }"
            :style="transitionEntryStyle(i - 1)"
            @click.stop="openTransitionEditor(i - 1)"
          >
            <el-icon :size="14">
              <Connection />
            </el-icon>
          </button>
        </el-tooltip>
      </template>

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

    <!-- 转场编辑器 Dialog -->
    <TransitionEditor
      v-model="transitionDialogVisible"
      :transition="editingTransition"
      :index="editingTransitionIndex"
      @update:transition="handleTransitionUpdate"
      @remove="handleTransitionRemove"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElEmpty, ElTooltip, ElIcon } from 'element-plus'
import { Connection } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import TransitionEditor from './TransitionEditor.vue'

/** 字幕条目结构（与后端 ffmpeg_composite 输出的 subtitles 字段一致） */
interface SubtitleEntry {
  index: number
  scene_index?: number
  start: number
  end: number
  text: string
}

/** 转场配置结构（与后端 transition_compose 的 input_data.transitions[] 对齐） */
interface TransitionConfig {
  type: string
  duration_ms: number
}

const props = defineProps<{
  /** 字幕条目列表 */
  subtitles: SubtitleEntry[]
  /** 总时长（秒）；不传则取最后一条 end */
  duration?: number
  /** 当前播放时间（秒），用于游标位置 */
  currentTime?: number
  /** 是否显示转场入口（父组件根据是否存在 transition_compose 步骤控制） */
  hasTransitionStep?: boolean
  /** 转场配置数组（对应 transition_compose 步骤的 input_data.transitions） */
  transitions?: TransitionConfig[]
}>()

const emit = defineEmits<{
  (e: 'seek', time: number): void
  (e: 'select', sub: SubtitleEntry): void
  (e: 'update:transitions', value: TransitionConfig[]): void
}>()

const { t } = useI18n()

// ================ 转场编辑器状态 ================
const transitionDialogVisible = ref(false)
const editingTransitionIndex = ref(0)
const editingTransition = ref<TransitionConfig | null>(null)

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

// ================ 转场入口逻辑 ================

// 获取第 i 个转场配置（i 对应 subtitles[i] 与 subtitles[i+1] 之间的转场）
function getTransition(i: number): TransitionConfig | null {
  if (!props.transitions || i < 0 || i >= props.transitions.length) return null
  const t = props.transitions[i]
  return t && typeof t === 'object' && t.type ? t : null
}

// 转场入口按钮位置：放在相邻片段交界处（前一片段 end 位置）
function transitionEntryStyle(i: number): Record<string, string> {
  const total = totalDuration.value
  if (total <= 0 || !props.subtitles.length) return { left: '50%' }
  const sub = props.subtitles[i]
  if (!sub) return { left: '50%' }
  const leftPct = (sub.end / total) * 100
  return { left: leftPct + '%' }
}

// 转场类型的本地化标签（用于 tooltip 显示）
function getTransitionLabel(trans: TransitionConfig): string {
  return t(`pipeline.transition.types.${trans.type}`)
}

// 打开转场编辑器
function openTransitionEditor(i: number) {
  editingTransitionIndex.value = i
  editingTransition.value = getTransition(i)
  transitionDialogVisible.value = true
}

// 转场配置更新（确认）：写入 transitions 数组并 emit 给父组件
function handleTransitionUpdate(updated: TransitionConfig | null) {
  const idx = editingTransitionIndex.value
  const list = [...(props.transitions || [])]
  // 补齐到 idx + 1 长度（中间空位用 hard cut 即 null 表示，但数组里保持 undefined）
  while (list.length <= idx) list.push(undefined as unknown as TransitionConfig)
  if (updated) {
    list[idx] = updated
  } else {
    // 删除：用 undefined 占位，过滤后输出
    list[idx] = undefined as unknown as TransitionConfig
  }
  // 过滤掉末尾的 undefined，但保留中间的 undefined（hard cut）
  // 实际上后端 _parse_transitions 会用 None 兜底，前端可以传稀疏数组
  // 但 JSON 序列化时 undefined 会丢失，所以这里转成 dense 数组（中间的 hard cut 用 null）
  const dense = list.map(item => item || null)
  emit('update:transitions', dense.filter((_, i) => i < props.subtitles.length - 1) as TransitionConfig[])
}

// 转场删除：与 update 等价（设为 null 后 emit）
function handleTransitionRemove() {
  handleTransitionUpdate(null)
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

/* 转场入口按钮：相邻片段交界处 */
.transition-entry {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1px solid var(--agnes-border);
  background: var(--agnes-bg-card);
  color: var(--agnes-text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 4;
  padding: 0;
  transition: background 0.2s, color 0.2s, transform 0.2s;
}
.transition-entry:hover {
  background: var(--agnes-primary);
  color: #fff;
  transform: translate(-50%, -50%) scale(1.1);
}
/* 已配置转场：高亮显示 */
.transition-entry--active {
  background: var(--agnes-primary);
  color: #fff;
  border-color: var(--agnes-primary);
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
