<!-- =====================================================
     ImageNode —— 图片生成节点内容组件
     - 表单：提示词 / 模型 / 尺寸
     - 生成按钮：调用 taskQueue.submitImageTask
     - 状态联动：节点状态徽章（generating / done / error）
     - 预览区：任务完成后展示图片
     ===================================================== -->

<template>
  <div class="image-node">
    <!-- 表单区 -->
    <div class="image-node-form">
      <div class="node-field">
        <label class="node-field-label">提示词</label>
        <textarea
          class="node-field-textarea"
          :value="panel.content?.prompt || ''"
          placeholder="描述图片内容..."
          rows="2"
          @input="(e) => $emit('update-content', { prompt: e.target.value })"
        />
      </div>

      <div class="node-row">
        <div class="node-field node-field-flex">
          <label class="node-field-label">模型</label>
          <select
            class="node-field-select"
            :value="panel.content?.model || 'sdxl'"
            @change="(e) => $emit('update-content', { model: e.target.value })"
          >
            <option value="sdxl">SDXL</option>
            <option value="flux">Flux</option>
            <option value="sd3">SD 3</option>
          </select>
        </div>
        <div class="node-field node-field-flex" style="margin-left: 8px">
          <label class="node-field-label">尺寸</label>
          <select
            class="node-field-select"
            :value="panel.content?.size || '1:1'"
            @change="(e) => $emit('update-content', { size: e.target.value })"
          >
            <option value="1:1">1:1</option>
            <option value="16:9">16:9</option>
            <option value="9:16">9:16</option>
            <option value="4:3">4:3</option>
          </select>
        </div>
      </div>
    </div>

    <!-- 操作区（应用上游 / 生成/取消按钮） -->
    <div class="image-node-actions">
      <button
        v-if="hasUpstream"
        class="node-btn node-btn-ghost"
        @click="handleApplyUpstream"
        title="把上游节点的数据（提示词/配置）注入到此节点"
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
        <el-icon :size="14"><MagicStick /></el-icon>
        <span>生成图片</span>
      </button>
      <button
        v-else
        class="node-btn node-btn-danger"
        @click="handleCancel"
      >
        <el-icon :size="14"><Close /></el-icon>
        <span>取消任务</span>
      </button>
    </div>

    <!-- 预览区（优先显示 taskQueue 中最新结果，其次 panel 自身的 resultUrl） -->
    <div class="image-node-preview">
      <div v-if="finalImageUrl" class="image-preview-wrap">
        <img :src="finalImageUrl" alt="图片预览" class="image-preview-img" />
      </div>
      <div v-else-if="isRunning" class="image-preview-empty">
        <el-icon :size="28"><Loading /></el-icon>
        <span>正在生成（{{ currentProgress }}%）</span>
      </div>
      <div v-else-if="lastError" class="image-preview-empty image-preview-error">
        <el-icon :size="28"><Warning /></el-icon>
        <span>{{ lastError }}</span>
      </div>
      <div v-else class="image-preview-empty">
        <el-icon :size="28"><PictureFilled /></el-icon>
        <span>暂无图片 · 填写提示词后生成</span>
      </div>
    </div>
  </div>
</template>

<script setup>
/* =====================================================
 * ImageNode 核心逻辑：
 * 1. 通过 props.panel 接收节点数据
 * 2. 点击「生成图片」时调用 taskQueue.submitImageTask
 * 3. 把该任务的 taskId 写入 panel.content.taskId，便于追踪
 * 4. 计算属性 currentTask 从 taskQueue 读取最新任务状态
 * 5. 任务完成后：把 resultUrl 写回 panel.content.resultUrl
 * 6. isRunning / currentProgress / lastError 派生自 currentTask
 ===================================================== */

import { computed, watch } from 'vue'
import {
  MagicStick,
  Close,
  Loading,
  Warning,
  PictureFilled,
  Link,
} from '@element-plus/icons-vue'
import { useTaskQueueStore } from '@/stores/taskQueue'
import { useCanvasStore } from '@/stores/canvas'

/* ---------- Props / Emits ---------- */
const props = defineProps({
  panel: { type: Object, required: true },
})
const emit = defineEmits(['update-content', 'update-status'])

/* ---------- Stores ---------- */
const taskQueue = useTaskQueueStore()
const store = useCanvasStore()

/* ---------- 派生状态 ---------- */

/* 当前节点关联的任务：
 * 优先取 panel.content.taskId 对应的任务（如果存在且非终态）
 * 否则尝试从 taskQueue.tasks 的最新同来源 image 任务中匹配
 */
const currentTask = computed(() => {
  const tid = props.panel.content?.taskId
  if (tid && taskQueue.tasks[tid]) return taskQueue.tasks[tid]
  return null
})

/* 任务是否进行中：queued / pending / processing 都算「正在处理」 */
const isRunning = computed(() => {
  const t = currentTask.value
  if (!t) return false
  return ['queued', 'pending', 'processing'].includes(t.status)
})

const currentProgress = computed(() => currentTask.value?.progress ?? 0)
const lastError = computed(() => currentTask.value?.errorMessage || '')

/* 图片预览 URL：优先取 taskQueue 中最新 resultUrl，其次 panel 自身 resultUrl */
const finalImageUrl = computed(() => {
  const t = currentTask.value
  if (t && t.resultUrl) return t.resultUrl
  return props.panel.content?.resultUrl || null
})

/* 生成按钮是否可用：必须有提示词，且当前没有进行中任务 */
const canSubmit = computed(() => {
  const p = props.panel.content?.prompt
  return p && p.trim().length > 0 && !isRunning.value
})

/* =====================================================
 * 上游节点数据联动：
 * - 提供「应用上游数据」按钮：把上游的 prompt/model/size 注入
 * - 自动监听：上游节点有新 resultUrl / prompt 时，
 *   如果当前节点该字段为空，自动填充
 * ===================================================== */

/* 上游节点输出 */
const upstreamOutput = computed(() => store.getUpstreamOutput(props.panel.id))

/* 是否有上游节点 */
const hasUpstream = computed(() => upstreamOutput.value.length > 0)

/* 应用上游数据：把上游节点的 prompt / model / size 注入到当前节点 */
function handleApplyUpstream() {
  const merged = store.resolveInputs(props.panel.id)
  if (!merged) return
  emit('update-content', merged)
}

/* 自动监听：上游节点有新 resultUrl / prompt 时，自动注入到当前节点（只注入空字段） */
watch(
  () => {
    // 监听上游节点的核心字段变化
    return upstreamOutput.value.map((item) => ({
      type: item.panel.type,
      prompt: item.output.prompt,
      resultUrl: item.output.resultUrl,
      model: item.output.model,
      size: item.output.size,
    }))
  },
  (newUpstream) => {
    if (!newUpstream || newUpstream.length === 0) return
    const current = props.panel.content ?? {}
    const patch = {}
    for (const item of newUpstream) {
      // 如果当前节点没有 prompt 但上游有 prompt → 自动填充
      if (item.prompt && (!current.prompt || current.prompt.trim() === '')) {
        patch.prompt = item.prompt
      }
      // 如果上游是 config 节点 → 自动应用 model/size（如果当前没设置）
      if (item.type === 'config') {
        if (item.model && !current.model) patch.model = item.model
        if (item.size && !current.size) patch.size = item.size
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
    const taskId = taskQueue.submitImageTask({
      prompt,
      model: content.model || 'sdxl',
      size: content.size || '1:1',
    })
    // 把 taskId 回写到节点，便于后续状态追踪
    emit('update-content', { taskId })
    // 触发节点状态更新（外壳显示「生成中」徽章）
    emit('update-status', 'generating')
  } catch (err) {
    console.error('[ImageNode] 提交任务失败:', err)
    emit('update-status', 'error')
  }
}

function handleCancel() {
  const t = currentTask.value
  if (!t) return
  taskQueue.cancelTask(t.taskId)
  emit('update-status', 'idle')
}

/* ---------- 监听任务状态变化 → 回写到节点 ----------
 * 任务完成/失败/取消后，把最新 resultUrl / 状态 写回 panel.content
 * 以便外壳正确显示状态徽章
 * ===================================================== */
watch(
  () => currentTask.value?.status,
  (status) => {
    if (!status) return
    const t = currentTask.value
    // 成功 → 写入 resultUrl
    if (status === 'success' && t?.resultUrl) {
      emit('update-content', { resultUrl: t.resultUrl })
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
.image-node {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.node-field {
  display: flex;
  flex-direction: column;
}

.node-field-flex {
  flex: 1;
}

.node-row {
  display: flex;
}

.node-field-label {
  font-size: 11px;
  color: #8ba3c9;
  margin-bottom: 4px;
}

.node-field-input,
.node-field-select,
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

/* 操作按钮区 */
.image-node-actions {
  display: flex;
  justify-content: flex-start;
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
  transition: background 0.15s ease, border-color 0.15s ease, opacity 0.15s ease;
  margin-right: 8px;
}

/* 辅助/幽灵按钮：用于「应用上游数据」这类次要操作 */
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

/* 预览区 */
.image-node-preview {
  margin-top: 4px;
}

.image-preview-wrap {
  border-radius: 8px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.25);
  max-height: 260px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.image-preview-img {
  width: 100%;
  display: block;
  max-height: 260px;
  object-fit: contain;
}

.image-preview-empty {
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

.image-preview-error {
  color: #ffa5ad;
}
</style>