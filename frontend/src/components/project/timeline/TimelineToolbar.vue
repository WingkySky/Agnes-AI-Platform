<!-- =====================================================
     时间线工具栏 TimelineToolbar
     - 入口：初始化时间线 / 生成字幕（LLM/Whisper）/ 字幕样式 / 选择 BGM / 高级合成
     - 仅展示状态信息（时长 / Whisper 可用性 / 当前 BGM）
     - 实际业务调用通过 emit 触发父组件处理
     ===================================================== -->

<template>
  <div class="timeline-toolbar">
    <!-- 左侧：主要操作 -->
    <div class="toolbar-group">
      <el-button
        type="primary"
        :icon="Refresh"
        :loading="loading"
        :disabled="!editable"
        @click="$emit('init')"
      >初始化时间线</el-button>

      <el-divider direction="vertical" />

      <el-button
        :icon="Document"
        :loading="subtitleLoading"
        :disabled="!editable || !hasTimeline"
        @click="$emit('generate-subtitles', 'llm')"
      >生成字幕</el-button>

      <el-tooltip
        :content="whisperAvailable ? '使用 Whisper 强制对齐生成精确字幕' : '未安装 faster-whisper，无法使用此模式'"
        placement="bottom"
      >
        <span>
          <el-button
            :icon="Microphone"
            :loading="whisperLoading"
            :disabled="!editable || !hasTimeline || !whisperAvailable"
            @click="$emit('generate-subtitles', 'whisper')"
          >Whisper 字幕</el-button>
        </span>
      </el-tooltip>

      <el-button
        :icon="Brush"
        :disabled="!hasTimeline"
        @click="$emit('open-subtitle-style')"
      >字幕样式</el-button>
    </div>

    <!-- 右侧：BGM + 合成 + 状态 -->
    <div class="toolbar-group">
      <el-button
        :icon="Headset"
        :disabled="!editable || !hasTimeline"
        @click="$emit('open-bgm-picker')"
      >
        <span>BGM：</span>
        <el-tag v-if="currentBgm" size="small" type="success" effect="plain">{{ currentBgm.name }}</el-tag>
        <el-tag v-else size="small" type="info" effect="plain">未选</el-tag>
      </el-button>

      <el-button
        type="success"
        :icon="VideoCamera"
        :loading="mergeLoading"
        :disabled="!hasTimeline || mergeLoading"
        @click="$emit('merge-advanced')"
      >合成视频</el-button>

      <el-divider direction="vertical" />

      <div class="status-info">
        <el-tag v-if="mergeLoading && mergeProgress" :type="mergeProgress.status === 'failed' ? 'danger' : 'warning'" size="small" effect="plain">
          {{ mergeProgressText }}
        </el-tag>
        <el-tag v-else-if="totalDuration > 0" type="info" effect="plain" size="small">
          时长 {{ formatDuration(totalDuration) }}
        </el-tag>
        <el-tag v-if="whisperAvailable" type="warning" effect="plain" size="small">Whisper 已就绪</el-tag>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  Refresh, Document, Microphone, Brush, Headset, VideoCamera,
} from '@element-plus/icons-vue'
import type { BGMItem } from '@/types/project'

const props = defineProps<{
  /** 是否可编辑（项目状态） */
  editable: boolean
  /** 是否已有时间线数据 */
  hasTimeline: boolean
  /** 总时长（秒） */
  totalDuration: number
  /** Whisper 是否可用 */
  whisperAvailable: boolean
  /** 当前选中的 BGM */
  currentBgm?: BGMItem | null
  /** 通用 loading */
  loading?: boolean
  subtitleLoading?: boolean
  whisperLoading?: boolean
  mergeLoading?: boolean
  /** 合成进度 SSE 事件 */
  mergeProgress?: Record<string, any> | null
}>()

defineEmits<{
  (e: 'init'): void
  (e: 'generate-subtitles', mode: 'llm' | 'whisper'): void
  (e: 'open-subtitle-style'): void
  (e: 'open-bgm-picker'): void
  (e: 'merge-advanced'): void
}>()

/** 合成进度文案 */
const mergeProgressText = computed(() => {
  const p = props.mergeProgress
  if (!p) return '合成中...'
  const stage = p.status || ''
  const stageTextMap: Record<string, string> = {
    started: '合成任务已启动',
    downloading: `下载分镜视频中 (${p.progress ?? 0}%)`,
    compositing: `ffmpeg 拼接中 (${p.progress ?? 0}%)`,
    completed: '合成完成',
    failed: p.error || '合成失败',
  }
  return stageTextMap[stage] || p.message || `合成中 (${p.progress ?? 0}%)`
})

/** 格式化秒为 mm:ss */
function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return '0:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}
</script>

<style scoped>
.timeline-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  flex-wrap: wrap;
}

.toolbar-group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.status-info {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
</style>
