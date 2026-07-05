<!-- =====================================================
     时间线预览容器 TimelinePreview
     - 渲染隐藏的视频/音频元素池（按 clip 注册）
     - 显示当前激活的视频片段
     - HTML overlay 显示字幕（CSS 映射 SubtitleStyle）
     - 控件：播放/暂停、当前时间、总时长
     ===================================================== -->

<template>
  <div class="timeline-preview" :class="{ playing: isPlaying }">
    <!-- 预览画面区 -->
    <div class="preview-stage">
      <!-- 视频元素池：每个 video clip 一个 <video>，通过 v-show 控制显示 -->
      <video
        v-for="clip in videoClips"
        :key="'v-' + clip.id"
        v-show="activeVideoClipId === clip.id"
        :ref="(el) => registerVideoEl(clip.id, el as HTMLVideoElement | null)"
        :src="clip.source_file_url || undefined"
        :poster="clip.source_thumbnail_url || undefined"
        class="preview-video"
        muted
        playsinline
        preload="auto"
        @error="onMediaError(clip.id, $event)"
      />

      <!-- 空状态 -->
      <div v-if="!activeVideoClipId" class="preview-empty">
        <el-icon :size="48"><VideoPlay /></el-icon>
        <span class="empty-text">{{ emptyText }}</span>
      </div>

      <!-- 字幕 overlay -->
      <div class="subtitle-overlay" v-if="activeSubtitleText">
        <span class="subtitle-text" :style="subtitleStyleCss">{{ activeSubtitleText }}</span>
      </div>
    </div>

    <!-- 音频元素池（隐藏，不显示画面） -->
    <div class="audio-pool" aria-hidden="true">
      <audio
        v-for="clip in audioClips"
        :key="'a-' + clip.id"
        :ref="(el) => registerAudioEl(clip.id, el as HTMLAudioElement | null)"
        :src="clip.source_file_url || undefined"
        preload="auto"
      />
    </div>

    <!-- 预览控件 -->
    <div class="preview-controls">
      <el-button-group>
        <el-button
          size="small"
          :icon="isPlaying ? VideoPause : VideoPlay"
          :disabled="!canPlay"
          @click="togglePlayPause"
        >
          {{ isPlaying ? '暂停' : '播放' }}
        </el-button>
        <el-button size="small" :icon="RefreshLeft" :disabled="!canPlay" @click="onRestart">
          重置
        </el-button>
      </el-button-group>

      <span class="time-display">
        {{ formatTime(currentTime) }} / {{ formatTime(totalDuration) }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { VideoPlay, VideoPause, RefreshLeft } from '@element-plus/icons-vue'
import type { TimelineClip, SubtitleStyle } from '@/types/project'

interface Props {
  clips: TimelineClip[]
  subtitleStyle: SubtitleStyle | null
  totalDuration: number
  isPlaying: boolean
  currentTime: number
  activeVideoClipId: number | null
  activeAudioClipId: number | null
  activeSubtitleClipId: number | null
  activeSubtitleText: string
  subtitleStyleCss: Record<string, string>
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'register-video', clipId: number, el: HTMLVideoElement | null): void
  (e: 'register-audio', clipId: number, el: HTMLAudioElement | null): void
  (e: 'toggle-play-pause'): void
  (e: 'restart'): void
}>()

// 主轨视频片段
const videoClips = computed(() =>
  props.clips.filter((c) => c.track_type === 'video' && c.track_index === 0),
)

// 主轨音频片段
const audioClips = computed(() =>
  props.clips.filter((c) => c.track_type === 'audio' && c.track_index === 0),
)

// 是否可播放（至少有一个有效视频片段）
const canPlay = computed(() =>
  videoClips.value.some((c) => c.source_file_url),
)

// 空状态文案
const emptyText = computed(() => {
  if (videoClips.value.length === 0) return '暂无视频片段，请先初始化时间线'
  if (!canPlay.value) return '视频片段源文件缺失，请检查分镜视频是否已生成'
  return '点击播放按钮开始预览'
})

// ---------- 元素注册转发 ----------
function registerVideoEl(clipId: number, el: HTMLVideoElement | null) {
  emit('register-video', clipId, el)
}

function registerAudioEl(clipId: number, el: HTMLAudioElement | null) {
  emit('register-audio', clipId, el)
}

// ---------- 控件事件 ----------
function togglePlayPause() {
  emit('toggle-play-pause')
}

function onRestart() {
  emit('restart')
}

// ---------- 媒体错误处理 ----------
function onMediaError(clipId: number, _e: Event) {
  // 静默处理：预览中某个片段加载失败不应阻断整体流程
  console.warn(`[TimelinePreview] 视频 ${clipId} 加载失败`, _e)
}

// ---------- 时间格式化 ----------
function formatTime(seconds: number): string {
  if (!seconds || !isFinite(seconds)) return '00:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
</script>

<style scoped>
.timeline-preview {
  background: #1a1a1a;
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 12px;
}

.preview-stage {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}

.preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #888;
}

.empty-text {
  font-size: 14px;
}

.subtitle-overlay {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  justify-content: center;
  padding: 0 20px;
  pointer-events: none;
  z-index: 10;
}

.subtitle-text {
  display: inline-block;
  max-width: 80%;
  text-align: center;
  line-height: 1.4;
  word-break: break-word;
  /* 字幕样式由父组件通过 :style 注入 */
}

.audio-pool {
  position: absolute;
  width: 0;
  height: 0;
  overflow: hidden;
  visibility: hidden;
}

.preview-controls {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 12px;
  background: #252525;
  border-top: 1px solid #333;
}

.time-display {
  color: #ccc;
  font-family: 'Menlo', 'Monaco', monospace;
  font-size: 13px;
  user-select: none;
}
</style>
