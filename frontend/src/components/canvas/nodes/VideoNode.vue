<!-- =====================================================
     VideoNode —— 视频生成节点内容组件
     ===================================================== -->

<template>
  <div class="video-node">
    <!-- 表单区 -->
    <div class="video-node-form">
      <div class="node-field">
        <label class="node-field-label">视频提示词</label>
        <textarea
          class="node-field-textarea"
          :value="panel.content?.prompt || ''"
          placeholder="描述视频内容、镜头、风格..."
          rows="2"
          @input="(e) => $emit('update-content', { prompt: e.target.value })"
        />
      </div>

      <div class="node-field">
        <label class="node-field-label">首帧图片 URL（可选）</label>
        <input
          class="node-field-input"
          type="text"
          :value="panel.content?.imageUrl || ''"
          placeholder="可留空，由模型自动生成首帧"
          @input="(e) => $emit('update-content', { imageUrl: e.target.value })"
        />
        <div v-if="panel.content?.imageUrl" class="image-url-preview">
          <img :src="panel.content.imageUrl" alt="首帧预览" />
        </div>
      </div>
    </div>

    <!-- 操作区 -->
    <div class="video-node-actions">
      <button
        v-if="hasUpstream"
        class="node-btn node-btn-ghost"
        @click="handleApplyUpstream"
        title="把上游节点的提示词/首帧图片注入到此节点"
      >
        <el-icon :size="14"><Link /></el-icon>
        <span>应用上游数据</span>
      </button>
      <button
        v-if="!isRunning"
        class="node-btn node-btn-primary"
        :disabled="!canSubmit"
        @click="handleGenerate"
      >
        <el-icon :size="14"><VideoCameraFilled /></el-icon>
        <span>生成视频</span>
      </button>
      <button v-else class="node-btn node-btn-danger" @click="handleCancel">
        <el-icon :size="14"><Close /></el-icon>
        <span>取消任务</span>
      </button>
    </div>

    <!-- 预览区 -->
    <div class="video-node-preview">
      <div v-if="finalVideoUrl" class="video-preview-wrap">
        <video :src="finalVideoUrl" controls class="video-preview-player" />
      </div>
      <div v-else-if="isRunning" class="video-preview-empty">
        <el-icon :size="28"><Loading /></el-icon>
        <span>正在生成（{{ currentProgress }}%）</span>
      </div>
      <div v-else-if="lastError" class="video-preview-empty video-preview-error">
        <el-icon :size="28"><Warning /></el-icon>
        <span>{{ lastError }}</span>
      </div>
      <div v-else class="video-preview-empty">
        <el-icon :size="28"><VideoCameraFilled /></el-icon>
        <span>暂无视频 · 填写提示词后生成</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'
import { VideoCameraFilled, Close, Loading, Warning, Link } from '@element-plus/icons-vue'
import { useTaskQueueStore } from '@/stores/taskQueue'
import { useCanvasStore } from '@/stores/canvas'

const props = defineProps({ panel: { type: Object, required: true } })
const emit = defineEmits(['update-content', 'update-status'])
const taskQueue = useTaskQueueStore()
const store = useCanvasStore()

/* 当前节点关联的任务 */
const currentTask = computed(() => {
  const tid = props.panel.content?.taskId
  if (tid && taskQueue.tasks[tid]) return taskQueue.tasks[tid]
  return null
})

/* 任务是否进行中 */
const isRunning = computed(() => {
  const t = currentTask.value
  return t && ['queued', 'pending', 'processing'].includes(t.status)
})

const currentProgress = computed(() => currentTask.value?.progress ?? 0)
const lastError = computed(() => currentTask.value?.errorMessage || '')

/* 视频预览 URL */
const finalVideoUrl = computed(() => {
  const t = currentTask.value
  if (t && t.resultUrl) return t.resultUrl
  return props.panel.content?.resultUrl || null
})

const canSubmit = computed(() => {
  const p = props.panel.content?.prompt
  return p && p.trim().length > 0 && !isRunning.value
})

/* =====================================================
 * 上游节点数据联动：
 * - text 节点 → prompt
 * - image 节点 → imageUrl（作为首帧）
 * - config 节点 → model/size（预留）
 * ===================================================== */

const upstreamOutput = computed(() => store.getUpstreamOutput(props.panel.id))
const hasUpstream = computed(() => upstreamOutput.value.length > 0)

function handleApplyUpstream() {
  const merged = store.resolveInputs(props.panel.id)
  if (!merged) return
  emit('update-content', merged)
}

/* 自动监听：上游 prompt / imageUrl 变化时，如果当前为空则自动填充 */
watch(
  () => {
    return upstreamOutput.value.map((item) => ({
      type: item.panel.type,
      prompt: item.output.prompt,
      imageUrl: item.output.imageUrl || item.output.resultUrl,
    }))
  },
  (newUpstream) => {
    if (!newUpstream || newUpstream.length === 0) return
    const current = props.panel.content ?? {}
    const patch = {}
    for (const item of newUpstream) {
      if (item.prompt && (!current.prompt || current.prompt.trim() === '')) {
        patch.prompt = item.prompt
      }
      if (item.type === 'image' && item.imageUrl && !current.imageUrl) {
        patch.imageUrl = item.imageUrl
      }
    }
    if (Object.keys(patch).length > 0) {
      emit('update-content', patch)
    }
  },
  { deep: true },
)

/* ---------- 事件处理 ---------- */
function handleGenerate() {
  const content = props.panel.content || {}
  const prompt = (content.prompt || '').trim()
  if (!prompt) return
  try {
    const taskId = taskQueue.submitVideoTask({
      prompt: prompt,
      imageUrl: content.imageUrl || '',
    })
    emit('update-content', { taskId: taskId })
    emit('update-status', 'generating')
  } catch (err) {
    console.error('[VideoNode] 提交任务失败:', err)
    emit('update-status', 'error')
  }
}

function handleCancel() {
  const t = currentTask.value
  if (t) taskQueue.cancelTask(t.taskId)
  emit('update-status', 'idle')
}

/* ---------- 监听任务状态变化 → 回写节点 ---------- */
watch(
  () => currentTask.value?.status,
  (status) => {
    if (!status) return
    const t = currentTask.value
    if (status === 'success') {
      if (t && t.resultUrl) emit('update-content', { resultUrl: t.resultUrl })
      emit('update-status', 'done')
    } else if (status === 'failed') {
      emit('update-status', 'error')
    } else if (status === 'cancelled') {
      emit('update-status', 'idle')
    } else if (['queued', 'pending', 'processing'].includes(status)) {
      emit('update-status', 'generating')
    }
  },
  { immediate: true },
)
</script>

<style scoped>
.video-node {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.node-field {
  display: flex;
  flex-direction: column;
}

.node-field-label {
  font-size: 11px;
  color: #8ba3c9;
  margin-bottom: 4px;
}

.node-field-input,
.node-field-textarea {
  width: 100%;
  background: rgba(15, 24, 42, 0.7);
  border: 1px solid rgba(120, 170, 230, 0.2);
  border-radius: 6px;
  color: #e8eef7;
  padding: 6px 8px;
  font-size: 12px;
  outline: none;
  box-sizing: border-box;
  font-family: inherit;
}

.node-field-textarea {
  resize: vertical;
  min-height: 50px;
}

.image-url-preview {
  margin-top: 6px;
  border-radius: 6px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.25);
}

.image-url-preview img {
  width: 100%;
  max-height: 120px;
  object-fit: contain;
  display: block;
}

.video-node-actions {
  display: flex;
}

.node-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  border: 1px solid transparent;
  margin-right: 8px;
}

.node-btn-ghost {
  background: rgba(120, 170, 230, 0.08);
  border-color: rgba(120, 170, 230, 0.3);
  color: #9ac7ff;
}

.node-btn-ghost:hover {
  background: rgba(120, 170, 230, 0.18);
  border-color: rgba(120, 170, 230, 0.5);
}

.node-btn-primary {
  background: rgba(86, 156, 214, 0.2);
  border-color: rgba(86, 156, 214, 0.5);
  color: #9ac7ff;
}

.node-btn-primary:hover:not(:disabled) {
  background: rgba(86, 156, 214, 0.35);
}

.node-btn-primary:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.node-btn-danger {
  background: rgba(224, 108, 117, 0.18);
  border-color: rgba(224, 108, 117, 0.5);
  color: #ffa5ad;
}

.node-btn-danger:hover {
  background: rgba(224, 108, 117, 0.3);
}

.video-node-preview {
  margin-top: 4px;
}

.video-preview-wrap {
  border-radius: 8px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.3);
}

.video-preview-player {
  width: 100%;
  max-height: 260px;
  display: block;
}

.video-preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px 16px;
  background: rgba(0, 0, 0, 0.18);
  border-radius: 8px;
  color: #8ba3c9;
  font-size: 12px;
}

.video-preview-error {
  color: #ffa5ad;
}
</style>
