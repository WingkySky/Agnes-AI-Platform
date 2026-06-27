<template>
  <div class="pipeline-progress">
    <!-- 整体进度条 -->
    <div class="progress-summary">
      <el-progress
        :percentage="overallProgress"
        :status="progressStatus"
        :stroke-width="8"
      />
      <span class="progress-text">
        {{ t('pipelineResult.steps.completed', { completed: completedCount, total: steps.length }) }}
      </span>
      <!-- 暂停按钮（仅 running 状态显示） -->
      <el-button
        v-if="runStatus === 'running'"
        size="small"
        type="warning"
        @click="$emit('pause')"
      >
        {{ t('pipelineResult.pause') }}
      </el-button>
      <!-- 暂停状态提示 + 恢复按钮 -->
      <template v-if="runStatus === 'paused'">
        <el-tag type="warning" size="small">{{ t('pipelineResult.paused') }}</el-tag>
        <el-button
          size="small"
          type="primary"
          @click="$emit('resume')"
        >
          <el-icon><VideoPlay /></el-icon>
          {{ t('pipelineResult.continueRun') }}
        </el-button>
      </template>
    </div>

    <!-- 步骤时间线 -->
    <el-timeline class="steps-timeline">
      <el-timeline-item
        v-for="step in steps"
        :key="step.step_key"
        :type="getTimelineNodeType(step)"
        :hollow="step.status === 'pending'"
        :timestamp="step.finished_at || step.started_at"
        placement="top"
      >
        <div
          class="step-item"
          :class="{
            'step-item--selected': step.step_key === selectedStepKey,
            'step-item--clickable': step.status === 'success',
          }"
          @click="step.status === 'success' && $emit('select-step', step.step_key)"
        >
          <div class="step-header">
            <el-icon class="step-icon"><component :is="getStepIcon(step.step_type)" /></el-icon>
            <span class="step-name">{{ step.name }}</span>
            <el-tag :type="getStatusTagType(step.status)" size="small">
              {{ t(`pipelineResult.stepStatus.${step.status}`) }}
            </el-tag>
          </div>

          <!-- 失败步骤：错误信息 + 重试按钮 -->
          <div v-if="step.status === 'failed'" class="step-error">
            <span class="error-text">{{ step.error_message }}</span>
            <el-button
              v-permission="'pipeline:run'"
              size="small"
              type="primary"
              @click.stop="$emit('retry-step', step.step_key)"
            >
              {{ t('pipelineResult.retryStep') }}
            </el-button>
          </div>

          <!-- 成功步骤：悬浮重试按钮（二次确认：重新执行会清空下游） -->
          <div
            v-if="step.status === 'success' && runStatus !== 'running'"
            class="step-retry-hint"
          >
            <el-button
              v-permission="'pipeline:run'"
              size="small"
              type="warning"
              plain
              @click.stop="handleRetrySuccessStep(step)"
            >
              {{ t('pipelineResult.rerunStep') }}
            </el-button>
          </div>

          <!-- 运行中步骤：实时进度反馈（进度条 + 元素计数 + 阶段文案） -->
          <div v-if="step.status === 'running'" class="step-running">
            <!-- 第一行：旋转图标 + 阶段文案 + 元素计数 -->
            <div class="running-header">
              <el-icon class="is-loading running-spinner"><Loading /></el-icon>
              <span class="running-phase">
                {{ runningPhaseText(step) }}
              </span>
              <span
                v-if="hasItemCount(step)"
                class="running-count"
              >
                {{ step.progress_detail?.current ?? 0 }}/{{ step.progress_detail?.total }}
              </span>
            </div>
            <!-- 第二行：步骤内进度条（仅在收到 progress_detail 时显示） -->
            <el-progress
              v-if="hasItemCount(step) || typeof step.progress === 'number'"
              :percentage="stepPercent(step)"
              :show-text="false"
              :stroke-width="6"
              :status="undefined"
              class="running-progress"
            />
            <!-- 第三行：百分比 + 兜底文案 -->
            <div class="running-meta">
              <span v-if="hasItemCount(step)" class="meta-percent">
                {{ stepPercent(step) }}%
              </span>
              <span v-else-if="typeof step.progress === 'number'" class="meta-percent">
                {{ stepPercent(step) }}%
              </span>
              <span v-else class="meta-hint">
                {{ t('pipelineResult.steps.preparing') }}
              </span>
            </div>
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '@/i18n'
import { ElTimeline, ElTimelineItem, ElProgress, ElTag, ElButton, ElIcon, ElMessageBox } from 'element-plus'
import { Document, Picture, VideoPlay, Loading, Film, Microphone, Edit } from '@element-plus/icons-vue'
import type { PipelineStep, PipelineRunStatus } from '@/types'

const props = defineProps<{
  steps: PipelineStep[]
  currentStepKey?: string
  runStatus: PipelineRunStatus | string
  selectedStepKey?: string
}>()

const emit = defineEmits<{
  'select-step': [stepKey: string]
  'retry-step': [stepKey: string]
  'pause': []
  'resume': []
}>()

const { t } = useI18n()

const completedCount = computed(() =>
  props.steps.filter(s => s.status === 'success').length
)

const overallProgress = computed(() => {
  if (!props.steps.length) return 0
  return Math.round((completedCount.value / props.steps.length) * 100)
})

const progressStatus = computed(() => {
  if (props.runStatus === 'failed') return 'exception'
  if (props.runStatus === 'success') return 'success'
  return undefined
})

function getStepIcon(stepType: string) {
  const iconMap: Record<string, any> = {
    llm_generate: Document,
    image_batch: Picture,
    video_batch: VideoPlay,
    ffmpeg_composite: Film,
    tts_generate: Microphone,
    human_review: Edit,
  }
  return iconMap[stepType] || Document
}

function getTimelineNodeType(step: PipelineStep): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
    success: 'success',
    running: 'primary',
    failed: 'danger',
    skipped: 'info',
    pending: 'info',
  }
  return map[step.status] || 'info'
}

function getStatusTagType(status: string): 'success' | 'warning' | 'danger' | 'info' | '' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | ''> = {
    success: 'success',
    running: 'warning',
    failed: 'danger',
    skipped: 'info',
    pending: 'info',
  }
  return map[status] || ''
}

async function handleRetrySuccessStep(step: PipelineStep) {
  try {
    await ElMessageBox.confirm(
      t('pipelineResult.rerunStepConfirm', { name: step.name }) ||
        `重新执行「${step.name}」将清空该步骤及所有下游步骤的结果，确定继续？`,
      t('pipelineResult.rerunStepTitle') || '重新执行步骤',
      { confirmButtonText: t('common.confirm') || '确定', cancelButtonText: t('common.cancel') || '取消', type: 'warning' }
    )
    emit('retry-step', step.step_key)
  } catch {
    // 用户取消
  }
}

// ================ 运行中步骤的实时进度计算 ================
/**
 * 判断步骤是否上报了元素级计数（current/total）
 * 用于决定是否显示"3/8"计数和进度条
 */
function hasItemCount(step: PipelineStep): boolean {
  const d = step.progress_detail
  return !!(d && typeof d.total === 'number' && d.total > 0)
}

/**
 * 计算步骤内百分比（0~100，用于 el-progress）
 * 优先用 progress_detail.percent，其次用 step.progress
 * 兼容后端 0~1 和 0~100 两种范围
 */
function stepPercent(step: PipelineStep): number {
  const d = step.progress_detail
  let p: number | undefined
  if (d && typeof d.percent === 'number') p = d.percent
  else if (typeof step.progress === 'number') p = step.progress
  if (p == null) return 0
  // 兼容 0~1 与 0~100 两种范围
  return p > 1 ? Math.round(p) : Math.round(p * 100)
}

/**
 * 运行中步骤的阶段文案
 * 优先用后端 phase_text（如"创建视频任务中"），其次按 phase 映射 i18n，
 * 最后回退到通用"执行中"
 */
function runningPhaseText(step: PipelineStep): string {
  const d = step.progress_detail
  if (d?.phase_text) return d.phase_text
  if (d?.phase === 'creating') return t('pipelineResult.steps.phaseCreating')
  if (d?.phase === 'polling') return t('pipelineResult.steps.phasePolling')
  if (d?.message) return d.message
  if (step.output_summary) return step.output_summary
  return t('pipelineResult.stepStatus.running')
}
</script>

<style scoped>
.pipeline-progress {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.progress-summary {
  display: flex;
  align-items: center;
  gap: 12px;
}
.progress-summary .el-progress {
  flex: 1;
}
.progress-text {
  font-size: 13px;
  color: var(--agnes-text-secondary);
  white-space: nowrap;
}
.steps-timeline {
  padding-left: 8px;
}
.step-item {
  cursor: default;
  padding: 8px 12px;
  border-radius: 6px;
  transition: background 0.2s;
}
.step-item--clickable {
  cursor: pointer;
}
.step-item--clickable:hover {
  background: var(--agnes-bg-hover, rgba(0, 0, 0, 0.04));
}
.step-item--selected {
  background: var(--agnes-primary-light-9, rgba(64, 158, 255, 0.1));
}
.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.step-icon {
  font-size: 16px;
  color: var(--agnes-text-secondary);
}
.step-name {
  flex: 1;
  font-size: 14px;
  color: var(--agnes-text-primary);
}
.step-error {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.error-text {
  flex: 1;
  font-size: 12px;
  color: var(--agnes-danger);
  word-break: break-all;
}
/* 运行中步骤的实时进度区块 */
.step-running {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  background: var(--agnes-primary-light-9, rgba(64, 158, 255, 0.08));
  border-radius: 6px;
  border-left: 3px solid var(--agnes-primary, #409eff);
}
.running-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--agnes-primary);
}
.running-spinner {
  font-size: 14px;
  flex-shrink: 0;
}
.running-phase {
  flex: 1;
  font-weight: 500;
  /* 阶段文案过长时省略号，避免撑破时间线 */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.running-count {
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--agnes-primary);
  background: var(--agnes-bg-color, #fff);
  padding: 1px 8px;
  border-radius: 10px;
  border: 1px solid var(--agnes-primary-light-7, rgba(64, 158, 255, 0.3));
  flex-shrink: 0;
}
.running-progress {
  margin-top: 2px;
}
.running-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  color: var(--agnes-text-secondary);
}
.meta-percent {
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  color: var(--agnes-primary);
  font-weight: 500;
}
.meta-hint {
  color: var(--agnes-text-placeholder, #909399);
  font-style: italic;
}
.step-retry-hint {
  margin-top: 8px;
  display: flex;
  align-items: center;
}
</style>
