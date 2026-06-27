<!--
  FinalVideoPlayer —— 最终成片播放器
  - 基于 HTML5 <video> + <track> 标签
  - 支持字幕开关（加载 SRT 字幕文件）
  - 支持倍速播放（0.5x / 1x / 1.5x / 2x）
  - 支持下载（通过后端代理，确保带水印和 Content-Disposition）
-->
<template>
  <div class="final-video-player">
    <!-- 视频播放器（原生 controls + track 字幕） -->
    <video
      ref="videoRef"
      :src="src"
      controls
      class="video-element"
      crossorigin="anonymous"
      @timeupdate="onTimeUpdate"
    >
      <!-- 字幕轨道：通过 <track> 加载 SRT，浏览器原生渲染字幕 -->
      <track
        v-if="subtitleUrl && showSubtitle"
        :src="subtitleUrl"
        kind="subtitles"
        srclang="zh"
        label="中文"
        default
      />
    </video>

    <!-- 播放器控制条 -->
    <div class="player-controls">
      <!-- 左侧：字幕开关 -->
      <div v-if="subtitleUrl" class="control-group">
        <el-tooltip :content="showSubtitle ? t('pipelinePlayer.hideSubtitle') : t('pipelinePlayer.showSubtitle')" placement="top">
          <el-button
            :type="showSubtitle ? 'primary' : 'default'"
            size="small"
            circle
            @click="toggleSubtitle"
          >
            <el-icon><ChatRound /></el-icon>
          </el-button>
        </el-tooltip>
      </div>

      <!-- 中间：倍速控制 -->
      <div class="control-group">
        <el-tooltip :content="t('pipelinePlayer.playbackRate')" placement="top">
          <el-select
            v-model="currentRate"
            size="small"
            style="width: 90px"
            @change="changeRate"
          >
            <el-option
              v-for="rate in rateOptions"
              :key="rate"
              :value="rate"
              :label="`${rate}x`"
            />
          </el-select>
        </el-tooltip>
      </div>

      <!-- 右侧：下载按钮 -->
      <div class="control-group">
        <el-button size="small" @click="handleDownload">
          <el-icon><Download /></el-icon>
          <span class="btn-text">{{ t('pipelinePlayer.download') }}</span>
        </el-button>
      </div>
    </div>

    <!-- 视频元信息（时长 + 片段数） -->
    <div v-if="duration || segmentsCount" class="video-meta">
      <span v-if="duration">
        {{ t('pipelinePlayer.duration') }}: {{ formatDuration(duration) }}
      </span>
      <span v-if="segmentsCount">
        {{ t('pipelinePlayer.segments') }}: {{ segmentsCount }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { ElButton, ElIcon, ElTooltip, ElSelect, ElOption } from 'element-plus'
import { ChatRound, Download } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'

const props = defineProps<{
  src: string
  subtitleUrl?: string
  duration?: number
  segmentsCount?: number
  downloadUrl?: string
}>()

const emit = defineEmits<{
  (e: 'download'): void
  (e: 'time-update', time: number): void
}>()

const { t } = useI18n()

// 视频元素引用
const videoRef = ref<HTMLVideoElement | null>(null)

// 字幕显示状态（默认显示，有 SRT 时自动开启）
const showSubtitle = ref(true)

// 倍速选项
const rateOptions = [0.5, 0.75, 1, 1.25, 1.5, 2]
const currentRate = ref(1)

// 字幕可用时自动显示
watch(
  () => props.subtitleUrl,
  (url) => {
    showSubtitle.value = !!url
  },
  { immediate: true }
)

// 切换字幕显示
function toggleSubtitle() {
  showSubtitle.value = !showSubtitle.value
}

// 切换倍速
function changeRate(rate: number) {
  if (videoRef.value) {
    videoRef.value.playbackRate = rate
  }
}

// 视频加载后同步初始倍速
onMounted(() => {
  if (videoRef.value) {
    videoRef.value.playbackRate = currentRate.value
  }
})

// 视频播放进度变化（供父组件 TimelinePreview 同步游标位置）
function onTimeUpdate() {
  if (videoRef.value) {
    emit('time-update', videoRef.value.currentTime)
  }
}

// ================ 暴露给父组件的方法 ================
// 跳转到指定时间（秒）
function seek(time: number) {
  if (videoRef.value) {
    videoRef.value.currentTime = Math.max(0, time)
  }
}

// 获取当前播放时间
function getCurrentTime(): number {
  return videoRef.value?.currentTime || 0
}

defineExpose({ seek, getCurrentTime })

// 下载处理：优先用传入的 downloadUrl（带水印路由），否则用 src
function handleDownload() {
  emit('download')
  // 优先用父组件传入的 downloadUrl（应为 buildDownloadUrl 构造的带水印 URL）
  // 否则回退到 src（静态文件直链）
  const url = props.downloadUrl || props.src
  if (!url) return
  // 用 <a> 标签触发下载（后端已设 Content-Disposition: attachment）
  // 对带水印路由返回 attachment，会直接下载；对静态文件 URL 也兼容
  const a = document.createElement('a')
  a.href = url
  a.download = ''
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

// 格式化时长（秒 → m:ss）
function formatDuration(seconds?: number): string {
  if (!seconds) return ''
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}
</script>

<style scoped>
.final-video-player {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.video-element {
  width: 100%;
  max-width: 960px;
  border-radius: 8px;
  display: block;
  background: #000;
  border: 1px solid var(--agnes-border);
}
.player-controls {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 0;
  flex-wrap: wrap;
}
.control-group {
  display: flex;
  align-items: center;
  gap: 8px;
}
.btn-text {
  margin-left: 4px;
}
.video-meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: var(--agnes-text-secondary);
}
</style>
