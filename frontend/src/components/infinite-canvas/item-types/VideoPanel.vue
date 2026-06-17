/* =====================================================
 * 视频预览面板
 * - 任务 9：从纯展示升级为可生成面板
 *   · 支持文生视频（text2video）：本地 prompt
 *   · 支持图生视频（image2video）：上游 ImagePanel 的图 + 本地 prompt
 *   · 接入 createVideoTask + getVideoStatus 轮询
 *   · 完成后通过 emit('produced', { videoUrl }) 通知 BaseNode 回填下游
 * - 视频播放：优先用 /api/videos/{task_id}/stream 代理（解决 CORS）
 * ===================================================== */

<template>
  <div class="video-panel">
    <!-- 已有视频：播放 -->
    <video
      v-if="videoUrl"
      controls
      preload="metadata"
      :src="videoUrl"
    />
    <!-- 生成中：进度提示 -->
    <div v-else-if="taskStatus === 'pending'" class="video-placeholder">
      <el-icon :size="32" class="is-loading"><Loading /></el-icon>
      <p>{{ t('canvas.generating', '生成中...') }}{{ progressText }}</p>
    </div>
    <!-- 可生成：输入 prompt + 生成按钮 -->
    <div v-else class="video-gen-area">
      <el-input
        v-model="prompt"
        type="textarea"
        :rows="2"
        :placeholder="t('canvas.enterPrompt')"
        resize="none"
        size="small"
      />
      <div v-if="upstreamSummary" class="upstream-summary">
        <span class="upstream-label">{{ t('canvas.upstreamInputs', '上游输入') }}:</span>
        <span class="upstream-content">{{ upstreamSummary }}</span>
      </div>
      <el-button
        type="primary"
        size="small"
        :loading="generating"
        :disabled="!canGenerate"
        @click="handleGenerate"
      >
        {{ generating ? t('canvas.generating', '生成中...') : t('canvas.generateVideo', '生成视频') }}
      </el-button>
      <div v-if="statusText" class="status-line" :class="statusClass">{{ statusText }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useCanvasStore } from '@/stores/canvas'
import { createVideoTask, getVideoStatus } from '@/api/videos'

const { t } = useI18n()
const store = useCanvasStore()

const props = defineProps({
  panel: { type: Object, required: true },
})

const emit = defineEmits(['update', 'produced'])

const prompt = ref(props.panel.content?.prompt ?? '')
const generating = ref(false)
// 任务状态：'idle' | 'pending' | 'success' | 'failed'
const taskStatus = ref(props.panel.content?.taskStatus ?? 'idle')
const errorMsg = ref('')
const progress = ref(0)

let pollTimer = null
const POLL_INTERVAL = 5000   // 视频生成较慢，5s 轮询一次
const MAX_POLL_COUNT = 120    // 约 10 分钟超时

/** 上游输入：图生视频的参考图 + 拼接 prompt */
const upstreamInputs = computed(() => store.collectUpstreamInputs(props.panel.id))
const upstreamSummary = computed(() => {
  const imgs = upstreamInputs.value.images.length
  const texts = upstreamInputs.value.texts.length
  if (imgs === 0 && texts === 0) return ''
  const parts = []
  if (imgs > 0) parts.push(`${imgs} 张图`)
  if (texts > 0) parts.push(`${texts} 段文本`)
  return parts.join(' + ')
})

/** 视频播放 URL：用后端代理避免 CORS */
const videoUrl = computed(() => {
  const content = props.panel.content || {}
  if (content.taskStatus === 'pending') return null
  // 优先用 task_id 走代理（解决 CORS），其次直接用 videoUrl
  const taskId = content.task_id
  if (taskId && content.taskStatus === 'success') {
    return `/api/videos/${taskId}/stream`
  }
  return content.videoUrl ?? null
})

const canGenerate = computed(() => {
  // 有本地 prompt 或有上游文本即可生成；图生视频需要至少一张上游图
  const hasPrompt = prompt.value.trim().length > 0
  const hasUpstreamText = upstreamInputs.value.texts.length > 0
  const hasUpstreamImage = upstreamInputs.value.images.length > 0
  return hasPrompt || hasUpstreamText || hasUpstreamImage
})

const progressText = computed(() => {
  if (progress.value > 0) return ` ${progress.value}%`
  return ''
})

const statusText = computed(() => {
  switch (taskStatus.value) {
    case 'success': return t('canvas.genSuccess', '生成完成')
    case 'failed': return t('canvas.genFailed', '生成失败') + (errorMsg.value ? `：${errorMsg.value}` : '')
    default: return ''
  }
})
const statusClass = computed(() => ({
  'is-success': taskStatus.value === 'success',
  'is-failed': taskStatus.value === 'failed',
}))

function syncToContent(extra = {}) {
  emit('update', {
    content: {
      ...(props.panel.content || {}),
      prompt: prompt.value,
      taskStatus: taskStatus.value,
      ...extra,
    },
  })
}

/** 触发生成：调 createVideoTask，拿到 task_id 后启动轮询 */
async function handleGenerate() {
  // 取消上一次轮询
  stopPolling()
  errorMsg.value = ''
  progress.value = 0
  generating.value = true
  taskStatus.value = 'pending'
  syncToContent({ videoUrl: null, task_id: null })

  try {
    const inputs = store.collectUpstreamInputs(props.panel.id)
    // 拼接 prompt
    const promptParts = [prompt.value.trim()]
    for (const txt of inputs.texts) {
      if (txt && !promptParts.includes(txt)) promptParts.push(txt)
    }
    const finalPrompt = promptParts.filter(Boolean).join('\n')

    // 构造请求参数
    const reqParams = {
      prompt: finalPrompt || 'generate a video',
      model: 'agnes-video-v2.0',
      num_frames: 121,
      frame_rate: 24,
      width: 1152,
      height: 768,
    }
    // 有上游图 → image2video 模式（取第一张作为参考图）
    if (inputs.images.length > 0) {
      reqParams.mode = 'image2video'
      reqParams.image = inputs.images[0]
      reqParams.image_mime_type = 'image/png'
    } else {
      reqParams.mode = 'text2video'
    }

    const resp = await createVideoTask(reqParams)
    const taskId = resp?.task_id || resp?.id
    if (!taskId) {
      throw new Error('后端未返回 task_id')
    }
    syncToContent({ task_id: taskId, videoUrl: null })
    startPolling(taskId)
  } catch (err) {
    generating.value = false
    taskStatus.value = 'failed'
    errorMsg.value = err?.message || '创建任务失败'
    syncToContent({ task_id: null, videoUrl: null })
  }
}

/** 启动轮询 */
function startPolling(taskId) {
  let count = 0
  stopPolling()
  pollTimer = setInterval(async () => {
    count++
    if (count > MAX_POLL_COUNT) {
      stopPolling()
      generating.value = false
      taskStatus.value = 'failed'
      errorMsg.value = '轮询超时'
      syncToContent({})
      return
    }
    try {
      const st = await getVideoStatus(taskId)
      const status = String(st?.status || '').toLowerCase()
      // 更新进度
      if (typeof st?.progress === 'number') {
        progress.value = st.progress
      }
      // 成功
      if (status === 'success' || status === 'succeeded' || status === 'completed') {
        stopPolling()
        generating.value = false
        const videoUrl = st?.video_url
        if (!videoUrl) {
          taskStatus.value = 'failed'
          errorMsg.value = '后端未返回视频地址'
          syncToContent({})
          return
        }
        taskStatus.value = 'success'
        progress.value = 100
        syncToContent({ videoUrl, task_id: taskId })
        emit('produced', { videoUrl, sourcePanelId: props.panel.id })
        ElMessage.success(t('canvas.genSuccess', '生成完成'))
        return
      }
      // 失败
      if (status === 'failed' || status === 'error') {
        stopPolling()
        generating.value = false
        taskStatus.value = 'failed'
        errorMsg.value = st?.message || ''
        syncToContent({})
        return
      }
      // 其它继续轮询
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[VideoPanel] 轮询失败，将继续重试：', err?.message)
    }
  }, POLL_INTERVAL)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

watch(
  () => props.panel.content?.prompt,
  (v) => {
    if (typeof v === 'string' && v !== prompt.value) prompt.value = v
  },
)

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.video-panel {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  overflow: hidden;
}

.video-panel video {
  max-width: 100%;
  max-height: 100%;
  border-radius: 6px;
}

.video-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #6b84aa;
  font-size: 12px;
}

.video-gen-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  height: 100%;
  padding: 4px;
  box-sizing: border-box;
}

/* 上游输入预览（与 QuickGeneratePanel 样式一致） */
.upstream-summary {
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--canvas-panel-bg, rgba(255,255,255,0.05));
  border: 1px solid var(--canvas-node-border, rgba(255,255,255,0.1));
  color: var(--canvas-node-muted-text, #6b84aa);
  display: flex;
  gap: 4px;
  align-items: center;
}
.upstream-label { flex-shrink: 0; opacity: 0.7; }
.upstream-content {
  color: var(--canvas-connection-active, #50a0ff);
  font-weight: 500;
}

.status-line {
  font-size: 12px;
  text-align: center;
  padding: 2px 0;
  color: var(--canvas-node-muted-text, #6b84aa);
}
.status-line.is-success { color: #67c23a; }
.status-line.is-failed  { color: #f56c6c; }
</style>
