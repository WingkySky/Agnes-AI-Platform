<!--
  StepResultGallery —— 流水线步骤结果画廊
  - 接收单个 PipelineStep，根据 step_type 渲染不同类型产物
    · llm_generate：渲染文本（剧本/解析结果），可展开/收起
    · image_batch：图片网格，点击放大查看
    · video_batch：视频播放器网格
    · tts_generate：音频播放器列表（每条配音对应一个分镜）
    · ffmpeg_composite：最终成片视频（突出展示，带"最终成片"标签）
    · 其他：兜底空状态
  - 复用全局 ImageWithWatermark 与 ImageViewer 组件
  - 所有用户可见文案通过 i18n（t 函数）获取
-->
<template>
  <div class="step-result-gallery">
    <!-- 文本结果（LLM 剧本生成） -->
    <div v-if="step.step_type === 'llm_generate'" class="text-result">
      <div class="result-header">
        <span class="result-title">{{ step.name }}</span>
        <el-button text size="small" @click="textExpanded = !textExpanded">
          {{ textExpanded ? t('common.collapse') : t('common.expand') }}
        </el-button>
      </div>
      <pre class="script-content" :class="{ 'script-content--collapsed': !textExpanded }">{{
        scriptText
      }}</pre>
    </div>

    <!-- 最终成片（ffmpeg_composite 步骤，突出展示） -->
    <div v-else-if="step.step_type === 'ffmpeg_composite' && finalVideoUrl" class="final-video-section">
      <div class="result-header">
        <span class="result-title">{{ step.name }}</span>
        <el-tag type="success" size="small" effect="dark">{{ t('pipelineResult.finalVideo') }}</el-tag>
      </div>
      <!-- 增强版成片播放器：字幕切换 + 倍速 + 下载 -->
      <FinalVideoPlayer
        :src="finalVideoUrl"
        :subtitle-url="srtUrl"
        :duration="finalDuration"
        :segments-count="finalSegments"
      />
    </div>

    <!-- 图片网格 -->
    <div v-else-if="images.length" class="image-grid">
      <div
        v-for="(img, idx) in images"
        :key="idx"
        class="image-item"
        @click="openImageViewer(idx)"
      >
        <ImageWithWatermark :src="img.url" :alt="`结果 ${idx + 1}`" />
      </div>
    </div>

    <!-- 视频网格 -->
    <div v-else-if="videos.length" class="video-grid">
      <div v-for="(vid, idx) in videos" :key="idx" class="video-item">
        <video :src="vid.url" controls :poster="vid.poster" class="video-player" />
        <span class="video-duration">{{ formatDuration(vid.duration) }}</span>
        <!-- Prompt 已被自动改写标记（内容审核拒绝后 LLM 改写重试成功） -->
        <el-tooltip
          v-if="vid.was_rewritten"
          placement="top"
          :show-after="200"
          effect="light"
        >
          <template #content>
            <div class="rewrite-tooltip">
              <div class="rewrite-section">
                <div class="rewrite-label">{{ t('pipelineResult.originalPrompt') }}</div>
                <div class="rewrite-text">{{ vid.original_prompt }}</div>
              </div>
              <div class="rewrite-section">
                <div class="rewrite-label">{{ t('pipelineResult.rewrittenPrompt') }}</div>
                <div class="rewrite-text">{{ vid.rewritten_prompt }}</div>
              </div>
            </div>
          </template>
          <el-tag type="warning" size="small" effect="plain" class="rewrite-tag">
            {{ t('pipelineResult.promptRewritten') }}
          </el-tag>
        </el-tooltip>
      </div>
    </div>

    <!-- 音频列表（tts_generate 步骤） -->
    <div v-else-if="audios.length" class="audio-list">
      <div v-for="(audio, idx) in audios" :key="idx" class="audio-item">
        <div class="audio-info">
          <span class="audio-index">#{{ idx + 1 }}</span>
          <span class="audio-voice">{{ audio.voice }}</span>
          <span v-if="audio.duration" class="audio-duration">{{ formatDuration(audio.duration) }}</span>
        </div>
        <audio :src="audio.url" controls class="audio-player" />
        <div v-if="audio.text" class="audio-text">{{ audio.text }}</div>
      </div>
    </div>

    <!-- 空状态 -->
    <el-empty v-else :description="t('pipelineResult.noResult')" />

    <!-- 图片查看器（单图查看，复用全局 ImageViewer） -->
    <ImageViewer
      v-if="images.length && viewerVisible"
      :visible="viewerVisible"
      :url="images[viewerIndex]?.url"
      @close="viewerVisible = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from '@/i18n'
import { ElEmpty, ElButton, ElTag, ElTooltip } from 'element-plus'
import ImageWithWatermark from '@/components/ImageWithWatermark.vue'
import ImageViewer from '@/components/ImageViewer.vue'
import FinalVideoPlayer from '@/components/pipeline/FinalVideoPlayer.vue'
import type { PipelineStep } from '@/types'

const props = defineProps<{
  step: PipelineStep
}>()

const { t } = useI18n()

const textExpanded = ref(false)
const viewerVisible = ref(false)
const viewerIndex = ref(0)

/** 从 output_data 提取文本结果 */
const scriptText = computed(() => {
  const out = props.step.output_data || {}
  // 兼容多种字段名
  return out.parsed_result || out.text || out.script || JSON.stringify(out, null, 2)
})

/** 最终合成视频 URL（ffmpeg_composite 步骤）
 * 优先用 final_video_url 字段，其次从 videos 数组提取
 */
const finalVideoUrl = computed(() => {
  const out = props.step.output_data || {}
  if (out.final_video_url) return out.final_video_url
  // 兜底：从 videos 数组提取
  const vids = out.videos || []
  const final = vids.find((v: any) => v?.is_final) || vids[0]
  return final?.video_url || final?.url || ''
})

/** 最终视频时长（秒） */
const finalDuration = computed(() => {
  const out = props.step.output_data || {}
  return out.duration_seconds || 0
})

/** SRT 字幕文件 URL（ffmpeg_composite 步骤生成的独立字幕文件） */
const srtUrl = computed(() => {
  const out = props.step.output_data || {}
  return out.srt_url || ''
})

/** 最终视频片段数 */
const finalSegments = computed(() => {
  const out = props.step.output_data || {}
  return out.segments_count || 0
})

/** 从 output_data 提取图片列表
 * 兼容后端 image_batch 步骤返回的多种字段名：
 *   - image_url（Agnes API 返回的图片地址，最常见）
 *   - url（通用 URL 字段）
 *   - b64_json（base64 编码图片，需加 data: 前缀）
 * 同时过滤掉 success=false 的失败项
 */
const images = computed(() => {
  const out = props.step.output_data || {}
  return (out.images || [])
    .filter((img: any) => img?.success !== false)
    .map((img: any) => {
      // 兼容字符串数组（直接是 URL）
      if (typeof img === 'string') return { url: img, prompt: '' }
      const url = img.image_url || img.url || ''
      const b64 = img.b64_json
      return {
        url: url || (b64 ? `data:image/png;base64,${b64}` : ''),
        prompt: img.prompt,
      }
    })
    .filter((img: any) => img.url)
})

/** 从 output_data 提取视频列表
 * 兼容后端 video_batch 步骤返回的多种字段名：
 *   - video_url（视频地址，最常见）
 *   - url（通用 URL 字段）
 *   - cover_url / poster_url / poster（封面图）
 */
const videos = computed(() => {
  const out = props.step.output_data || {}
  return (out.videos || [])
    .filter((vid: any) => vid?.success !== false)
    .map((vid: any) => {
      if (typeof vid === 'string') return { url: vid, poster: '', duration: 0 }
      return {
        url: vid.video_url || vid.url || '',
        poster: vid.cover_url || vid.poster_url || vid.poster || '',
        duration: vid.duration,
        // 内容审核拒绝后 LLM 改写重试相关字段（无则不展示改写标记）
        was_rewritten: vid.was_rewritten === true,
        original_prompt: vid.original_prompt || '',
        rewritten_prompt: vid.rewritten_prompt || '',
      }
    })
    .filter((vid: any) => vid.url)
})

/** 从 output_data 提取音频列表（tts_generate 步骤）
 * 兼容字段名：audio_url / url / audio_path
 */
const audios = computed(() => {
  const out = props.step.output_data || {}
  return (out.audios || [])
    .filter((audio: any) => audio?.success !== false)
    .map((audio: any) => ({
      url: audio.audio_url || audio.url || '',
      voice: audio.voice || '',
      text: audio.text || '',
      duration: audio.duration_seconds || audio.duration || 0,
    }))
    .filter((audio: any) => audio.url)
})

/** 打开图片查看器，定位到指定索引 */
function openImageViewer(idx: number) {
  viewerIndex.value = idx
  viewerVisible.value = true
}

/** 格式化视频时长（秒 → m:ss） */
function formatDuration(seconds?: number): string {
  if (!seconds) return ''
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}
</script>

<style scoped>
.step-result-gallery {
  width: 100%;
}
.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.result-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--agnes-text-primary);
}
.script-content {
  background: var(--agnes-bg-page);
  padding: 12px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: none;
  overflow: hidden;
  transition: max-height 0.3s;
}
.script-content--collapsed {
  max-height: 200px;
}
/* 最终成片视频 */
.final-video-section {
  width: 100%;
}
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}
.image-item {
  cursor: pointer;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--agnes-border);
  transition: transform 0.2s;
}
.image-item:hover {
  transform: scale(1.02);
}
.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.video-item {
  position: relative;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--agnes-border);
}
.video-player {
  width: 100%;
  display: block;
}
.video-duration {
  position: absolute;
  bottom: 8px;
  right: 8px;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
}
/* Prompt 改写标记 */
.rewrite-tag {
  position: absolute;
  top: 8px;
  left: 8px;
  cursor: help;
  backdrop-filter: blur(4px);
}
.rewrite-tooltip {
  max-width: 360px;
  font-size: 12px;
  line-height: 1.5;
}
.rewrite-section {
  margin-bottom: 8px;
}
.rewrite-section:last-child {
  margin-bottom: 0;
}
.rewrite-label {
  font-weight: 600;
  color: var(--agnes-text-primary);
  margin-bottom: 4px;
}
.rewrite-text {
  color: var(--agnes-text-regular);
  word-break: break-word;
  white-space: pre-wrap;
}
/* 音频列表 */
.audio-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.audio-item {
  background: var(--agnes-bg-page);
  padding: 12px;
  border-radius: 6px;
  border: 1px solid var(--agnes-border);
}
.audio-info {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 13px;
}
.audio-index {
  font-weight: 500;
  color: var(--agnes-text-primary);
}
.audio-voice {
  color: var(--agnes-text-secondary);
  font-size: 12px;
}
.audio-duration {
  color: var(--agnes-text-secondary);
  font-size: 12px;
}
.audio-player {
  width: 100%;
  height: 36px;
}
.audio-text {
  margin-top: 6px;
  font-size: 12px;
  color: var(--agnes-text-secondary);
  line-height: 1.5;
}
</style>
