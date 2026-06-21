<!-- =====================================================
     TaskCard 组件
     - 展示单个任务的状态（排队中/生成中/成功/失败/已取消）
     - 展示进度条、提示词、耗时、错误信息
     - 支持操作：取消/重试/移除/查看详情
     - 通过 `task` prop 接收任务对象（由 taskQueue store 提供）
     ===================================================== -->

<template>
  <div
    class="task-card"
    :class="[
      `status-${task.status}`,
      { 'is-active': isActive, 'is-compact': compact }
    ]"
    @click="$emit('select', task.taskId)"
  >
    <!-- 左侧图标 -->
    <div class="task-icon" :class="task.type">
      <el-icon v-if="task.type === 'video'"><VideoPlay /></el-icon>
      <el-icon v-else><PictureFilled /></el-icon>
    </div>

    <!-- 中间内容区 -->
    <div class="task-body">
      <div class="task-header">
        <span class="task-status-badge" :class="task.status">
          {{ statusLabel }}
        </span>
        <span class="task-type-label">
          {{ task.type === 'video' ? t('taskStatus.video') : t('taskStatus.image') }}
        </span>
        <span class="task-time">{{ formatTime(task.createdAt) }}</span>
      </div>

      <!-- 提示词 -->
      <div class="task-prompt">{{ truncate(task.prompt, 80) }}</div>

      <!-- 进度条（仅进行中任务） -->
      <div v-if="isRunning" class="task-progress">
        <div class="progress-track">
          <div
            class="progress-fill"
            :style="{ width: task.progress + '%' }"
          ></div>
        </div>
        <span class="progress-text">{{ task.progress }}% · {{ elapsedSec }}s</span>
      </div>

      <!-- 成功状态：展示结果缩略图 -->
      <div v-else-if="task.status === 'success' && task.resultUrl" class="task-success">
        <el-icon class="success-icon"><Check /></el-icon>
        <span class="success-text">{{ t('taskStatus.successText') }} · {{ formatTime(task.updatedAt) }}</span>
      </div>

      <!-- 失败状态：展示错误信息 -->
      <div v-else-if="task.status === 'failed'" class="task-failed">
        <el-icon class="failed-icon"><Close /></el-icon>
        <span class="failed-text">{{ task.errorMessage || t('taskStatus.failedText') }}</span>
      </div>

      <!-- 已取消 -->
      <div v-else-if="task.status === 'cancelled'" class="task-cancelled">
        <el-icon class="cancelled-icon"><Remove /></el-icon>
        <span class="cancelled-text">{{ t('taskStatus.cancelledText') }}</span>
      </div>

      <!-- 排队中 -->
      <div v-else-if="task.status === 'queued'" class="task-queued">
        <span class="queued-text">{{ t('taskStatus.queuedText') }}</span>
      </div>
    </div>

    <!-- 右侧操作区 -->
    <div class="task-actions" @click.stop>
      <button
        v-if="isRunning"
        class="action-btn cancel-btn"
        :title="t('taskStatus.cancelTitle')"
        @click="handleCancel"
      >
        {{ t('taskStatus.cancel') }}
      </button>
      <button
        v-if="task.status === 'failed' || task.status === 'cancelled'"
        class="action-btn retry-btn"
        :title="t('taskStatus.retryTitle')"
        @click="handleRetry"
      >
        {{ t('taskStatus.retry') }}
      </button>
      <button
        class="action-btn remove-btn"
        :title="t('taskStatus.removeTitle')"
        @click="handleRemove"
      >
        {{ t('taskStatus.remove') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
// ------ 引入 i18n composable ------
import { computed } from 'vue'
import { VideoPlay, PictureFilled, Check, Close, Remove } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useTaskQueueStore } from '@/stores/taskQueue'

const { t } = useI18n()

const props = defineProps({
  task: {
    type: Object,
    required: true,
  },
  isActive: {
    type: Boolean,
    default: false,
  },
  compact: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['select'])

const queue = useTaskQueueStore()

const isRunning = computed(() => {
  return ['queued', 'pending', 'processing'].includes(props.task.status)
})

// ------ 状态标签国际化 ------
const statusLabel = computed(() => {
  switch (props.task.status) {
    case 'queued': return t('taskStatus.queued')
    case 'pending': return t('taskStatus.pending')
    case 'processing': return t('taskStatus.processing')
    case 'success': return t('taskStatus.success')
    case 'failed': return t('taskStatus.failed')
    case 'cancelled': return t('taskStatus.cancelled')
    default: return props.task.status
  }
})

const elapsedSec = computed(() => {
  // 通过 queue._tick 驱动每秒刷新
  queue._tick
  return Math.floor((Date.now() - props.task.createdAt) / 1000)
})

function truncate(text: string, max: number) {
  if (!text) return ''
  return text.length > max ? text.slice(0, max) + '...' : text
}

function formatTime(ts: number) {
  if (!ts) return ''
  const d = new Date(ts)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

async function handleCancel() {
  await queue.cancelTask(props.task.taskId)
}

function handleRetry() {
  queue.retryTask(props.task.taskId)
}

function handleRemove() {
  queue.removeTask(props.task.taskId)
}
</script>

<style scoped>
.task-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 12px;
  background: var(--agnes-bg-hover);
  border: 1px solid var(--agnes-info-bg);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}

.task-card:hover {
  background: var(--agnes-bg-hover);
  border-color: var(--agnes-info-bg);
}

.task-card.is-active {
  background: var(--agnes-border);
  border-color: var(--agnes-primary-border);
}

.task-card.status-success {
  border-left: 3px solid var(--agnes-success);
}
.task-card.status-failed {
  border-left: 3px solid var(--agnes-error);
}
.task-card.status-cancelled {
  border-left: 3px solid var(--agnes-text-faint);
}
.task-card.status-processing,
.task-card.status-pending,
.task-card.status-queued {
  border-left: 3px solid var(--agnes-primary);
}

.task-icon {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  font-size: 18px;
}
.task-icon.video { background: var(--agnes-info-bg); }
.task-icon.image { background: var(--agnes-error-bg); }

.task-body {
  flex: 1;
  min-width: 0;
}

.task-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.task-status-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
}
.task-status-badge.queued,
.task-status-badge.pending,
.task-status-badge.processing {
  background: var(--agnes-info-bg);
  color: var(--agnes-primary-soft);
}
.task-status-badge.success {
  background: var(--agnes-success-bg);
  color: var(--agnes-success);
}
.task-status-badge.failed {
  background: var(--agnes-error-bg);
  color: var(--agnes-error);
}
.task-status-badge.cancelled {
  background: var(--agnes-bg-hover);
  color: var(--agnes-text-muted);
}

.task-type-label {
  font-size: 11px;
  color: var(--agnes-text-muted);
}
.task-time {
  font-size: 11px;
  color: var(--agnes-text-faint);
  margin-left: auto;
}

.task-prompt {
  font-size: 13px;
  color: var(--agnes-text-primary);
  line-height: 1.5;
  margin: 2px 0 6px;
  word-break: break-word;
}

.task-progress {
  display: flex;
  align-items: center;
  gap: 10px;
}
.progress-track {
  flex: 1;
  height: 4px;
  background: var(--agnes-bg-hover);
  border-radius: 2px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--agnes-primary), var(--agnes-accent));
  border-radius: 2px;
  transition: width 0.3s ease;
  animation: pulse-shimmer 2s ease-in-out infinite;
}
@keyframes pulse-shimmer {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}
.progress-text {
  font-size: 11px;
  color: var(--agnes-primary-soft);
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  min-width: 60px;
  text-align: right;
}

.task-success,
.task-failed,
.task-cancelled,
.task-queued {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  margin-top: 4px;
}
.task-success { color: var(--agnes-success); }
.task-failed { color: var(--agnes-error); }
.task-cancelled { color: var(--agnes-text-muted); }
.task-queued { color: var(--agnes-primary-soft); }

.task-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex-shrink: 0;
}
.action-btn {
  background: transparent;
  border: 1px solid var(--agnes-info-bg);
  color: var(--agnes-text-muted);
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.action-btn:hover {
  background: var(--agnes-nav-hover-bg);
  color: var(--agnes-text-primary);
}
.cancel-btn:hover {
  background: var(--agnes-error-bg);
  border-color: var(--agnes-error-border);
  color: var(--agnes-error);
}
.retry-btn:hover {
  background: var(--agnes-success-bg);
  border-color: var(--agnes-success-border);
  color: var(--agnes-success);
}

/* 紧凑模式（用于队列面板） */
.task-card.is-compact {
  padding: 8px 10px;
}
.task-card.is-compact .task-icon {
  width: 32px;
  height: 32px;
  font-size: 16px;
}
.task-card.is-compact .task-prompt {
  font-size: 12px;
}
</style>
