<!--
  PostProcessDialog.vue — 历史视频后期处理弹窗

  功能:
    对单个历史视频做二次后期处理（调色 / 剪辑），无需重跑整个流水线。
    - 调色：4 个预设（subtle/neutral_punch/warm_cinematic/none）+ 可选音频淡入淡出
    - 剪辑：trim（保留区间）/ cut（删除区间）多段操作，自动拼接

  调用方式:
    <PostProcessDialog
      v-model:visible="dialogVisible"
      :generation-id="selectedVideoId"
      :video-url="selectedVideoUrl"
      @success="handleSuccess"
    />

  事件:
    - success: 处理成功，返回 { result_url, new_generation_id, operation }
-->
<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    :title="t('history.postProcess.title')"
    width="640px"
    :close-on-click-modal="false"
    append-to-body
  >
    <!-- 操作类型切换 Tab -->
    <el-radio-group v-model="operation" class="op-tabs">
      <el-radio-button value="color_grade">{{ t('history.postProcess.colorGrade') }}</el-radio-button>
      <el-radio-button value="video_edit">{{ t('history.postProcess.videoEdit') }}</el-radio-button>
    </el-radio-group>

    <!-- ===== 调色配置 ===== -->
    <div v-if="operation === 'color_grade'" class="op-config">
      <div class="config-row">
        <label class="config-label">{{ t('history.postProcess.gradePreset') }}</label>
        <el-select v-model="gradeConfig.preset" style="width: 280px">
          <el-option :label="t('history.postProcess.presetNone')" value="none" />
          <el-option :label="t('history.postProcess.presetSubtle')" value="subtle" />
          <el-option :label="t('history.postProcess.presetNeutralPunch')" value="neutral_punch" />
          <el-option :label="t('history.postProcess.presetWarmCinematic')" value="warm_cinematic" />
          <el-option :label="t('history.postProcess.presetAuto')" value="auto" />
        </el-select>
      </div>
      <div class="config-row">
        <label class="config-label">{{ t('history.postProcess.audioFade') }}</label>
        <el-switch v-model="gradeConfig.with_audio_fade" />
        <span class="config-hint">{{ t('history.postProcess.audioFadeHint') }}</span>
      </div>
      <!-- 预设说明 -->
      <div class="preset-desc">
        <el-icon><InfoFilled /></el-icon>
        <span>{{ presetDescription }}</span>
      </div>
    </div>

    <!-- ===== 剪辑配置 ===== -->
    <div v-else class="op-config">
      <!-- 视频时长提示 -->
      <div v-if="videoDuration > 0" class="duration-hint">
        {{ t('history.postProcess.videoDuration', { duration: videoDuration.toFixed(1) }) }}
      </div>
      <!-- 操作列表 -->
      <div class="edit-ops">
        <div
          v-for="(op, idx) in editConfig.operations"
          :key="idx"
          class="edit-op-row">
          <el-select v-model="op.type" style="width: 100px" @change="validateOp(op)">
            <el-option :label="t('history.postProcess.trim')" value="trim" />
            <el-option :label="t('history.postProcess.cut')" value="cut" />
          </el-select>
          <span class="op-label">{{ t('history.postProcess.start') }}</span>
          <el-input-number
            v-model="op.start"
            :min="0"
            :max="videoDuration || 9999"
            :step="0.5"
            :precision="1"
            style="width: 110px"
            @change="validateOp(op)" />
          <span class="op-label">{{ t('history.postProcess.end') }}</span>
          <el-input-number
            v-model="op.end"
            :min="0"
            :max="videoDuration || 9999"
            :step="0.5"
            :precision="1"
            style="width: 110px"
            @change="validateOp(op)" />
          <el-button
            type="danger"
            :icon="Delete"
            circle
            size="small"
            @click="removeOperation(idx)" />
        </div>
        <div v-if="editConfig.operations.length === 0" class="empty-ops">
          {{ t('history.postProcess.noOperations') }}
        </div>
      </div>
      <el-button :icon="Plus" plain size="small" @click="addOperation">
        {{ t('history.postProcess.addOperation') }}
      </el-button>
      <!-- 剪辑预览 -->
      <div v-if="keepRanges.length > 0" class="keep-preview">
        <div class="keep-label">{{ t('history.postProcess.keepPreview') }}</div>
        <div class="keep-bar">
          <div
            v-for="(range, idx) in keepRanges"
            :key="idx"
            class="keep-segment"
            :style="keepSegmentStyle(range)">
            {{ range[0].toFixed(1) }}-{{ range[1].toFixed(1) }}s
          </div>
        </div>
        <div class="keep-summary">
          {{ t('history.postProcess.keepDuration', {
            keep: keepDuration.toFixed(1),
            total: videoDuration.toFixed(1)
          }) }}
        </div>
      </div>
    </div>

    <!-- 底部操作 -->
    <template #footer>
      <el-button @click="$emit('update:visible', false)">
        {{ t('common.cancel') }}
      </el-button>
      <el-button
        type="primary"
        :loading="processing"
        :disabled="!canProcess"
        @click="handleProcess">
        {{ t('history.postProcess.process') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
// =====================================================
// 历史视频后期处理弹窗
// 调用后端 /api/pipeline/generations/{id}/post-process 接口
// =====================================================
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, Plus, InfoFilled } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { postProcessVideo, type VideoEditOperation, type PostProcessResponse } from '@/api/history'

const props = defineProps<{
  visible: boolean
  generationId: number | null
  videoUrl?: string
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  success: [result: PostProcessResponse]
}>()

const { t } = useI18n()

// 操作类型
const operation = ref<'color_grade' | 'video_edit'>('color_grade')

// 调色配置
const gradeConfig = reactive({
  preset: 'neutral_punch',
  with_audio_fade: true,
})

// 剪辑配置
const editConfig = reactive<{ operations: VideoEditOperation[] }>({
  operations: [],
})

// 视频时长（秒，0 表示未知）
const videoDuration = ref(0)

// 处理中状态
const processing = ref(false)

// ---------- 预设说明 ----------
const presetDescription = computed(() => {
  const descs: Record<string, string> = {
    none: t('history.postProcess.presetNoneDesc'),
    subtle: t('history.postProcess.presetSubtleDesc'),
    neutral_punch: t('history.postProcess.presetNeutralPunchDesc'),
    warm_cinematic: t('history.postProcess.presetWarmCinematicDesc'),
    auto: t('history.postProcess.presetAutoDesc'),
  }
  return descs[gradeConfig.preset] || ''
})

// ---------- 剪辑区间计算（与后端 _compute_keep_ranges 逻辑一致）----------
const keepRanges = computed<[number, number][]>(() => {
  if (editConfig.operations.length === 0 || videoDuration.value <= 0) return []
  const duration = videoDuration.value
  const trims: [number, number][] = []
  const cuts: [number, number][] = []

  for (const op of editConfig.operations) {
    const start = Math.max(0, Math.min(op.start, duration))
    const end = Math.max(0, Math.min(op.end, duration))
    if (end <= start) continue
    if (op.type === 'trim') trims.push([start, end])
    else if (op.type === 'cut') cuts.push([start, end])
  }

  // 初始区间
  let keep: [number, number][]
  if (trims.length > 0) {
    keep = mergeRanges(trims)
  } else {
    keep = [[0, duration]]
  }

  // 应用 cut
  for (const [cs, ce] of cuts) {
    keep = subtractRange(keep, cs, ce)
  }

  return keep
})

const keepDuration = computed(() => {
  return keepRanges.value.reduce((sum, [s, e]) => sum + (e - s), 0)
})

const keepSegmentStyle = (range: [number, number]) => {
  if (videoDuration.value <= 0) return {}
  const leftPct = (range[0] / videoDuration.value) * 100
  const widthPct = ((range[1] - range[0]) / videoDuration.value) * 100
  return {
    left: `${leftPct}%`,
    width: `${widthPct}%`,
  }
}

// ---------- 是否可处理 ----------
const canProcess = computed(() => {
  if (processing.value) return false
  if (operation.value === 'color_grade') {
    return gradeConfig.preset !== 'none' || gradeConfig.with_audio_fade
  }
  // 剪辑：至少一个有效操作
  return editConfig.operations.some(op => op.end > op.start)
})

// ---------- 监听弹窗打开，加载视频时长 ----------
watch(() => props.visible, async (visible) => {
  if (visible && props.videoUrl) {
    // 重置状态
    operation.value = 'color_grade'
    gradeConfig.preset = 'neutral_punch'
    gradeConfig.with_audio_fade = true
    editConfig.operations = []
    videoDuration.value = 0

    // 加载视频时长
    await loadVideoDuration(props.videoUrl)
  }
})

async function loadVideoDuration(url: string) {
  try {
    // 通过 HTML5 video 元素获取时长
    const video = document.createElement('video')
    video.preload = 'metadata'
    video.src = url
    await new Promise<void>((resolve, reject) => {
      video.onloadedmetadata = () => resolve()
      video.onerror = () => reject(new Error('load metadata failed'))
      setTimeout(() => reject(new Error('timeout')), 5000)
    })
    videoDuration.value = video.duration || 0
  } catch {
    // 获取时长失败，仍允许操作（用户手动输入时间戳）
    videoDuration.value = 0
  }
}

// ---------- 剪辑操作编辑 ----------
function addOperation() {
  // 默认在视频末尾添加 1 秒的 trim
  const defaultStart = videoDuration.value > 1 ? videoDuration.value - 1 : 0
  const defaultEnd = videoDuration.value > 0 ? videoDuration.value : 1
  editConfig.operations.push({
    type: 'cut',
    start: defaultStart,
    end: defaultEnd,
  })
}

function removeOperation(idx: number) {
  editConfig.operations.splice(idx, 1)
}

function validateOp(op: VideoEditOperation) {
  if (op.end <= op.start) {
    ElMessage.warning(t('history.postProcess.invalidRange'))
  }
}

// ---------- 区间计算工具（与后端逻辑对齐）----------
function mergeRanges(ranges: [number, number][]): [number, number][] {
  if (ranges.length === 0) return []
  const sorted = [...ranges].sort((a, b) => a[0] - b[0])
  const merged: [number, number][] = [sorted[0]]
  for (let i = 1; i < sorted.length; i++) {
    const [s, e] = sorted[i]
    const last = merged[merged.length - 1]
    if (s <= last[1]) {
      last[1] = Math.max(last[1], e)
    } else {
      merged.push([s, e])
    }
  }
  return merged
}

function subtractRange(
  keep: [number, number][],
  cutStart: number,
  cutEnd: number,
): [number, number][] {
  const result: [number, number][] = []
  for (const [s, e] of keep) {
    if (cutEnd <= s || cutStart >= e) {
      result.push([s, e])
      continue
    }
    if (cutStart > s) result.push([s, cutStart])
    if (cutEnd < e) result.push([cutEnd, e])
  }
  return result
}

// ---------- 提交处理 ----------
async function handleProcess() {
  if (!props.generationId) {
    ElMessage.error(t('history.postProcess.noGenerationId'))
    return
  }

  processing.value = true
  try {
    let params: any
    if (operation.value === 'color_grade') {
      params = {
        operation: 'color_grade',
        preset: gradeConfig.preset,
        with_audio_fade: gradeConfig.with_audio_fade,
      }
    } else {
      // 过滤无效操作
      const validOps = editConfig.operations.filter(op => op.end > op.start)
      if (validOps.length === 0) {
        ElMessage.warning(t('history.postProcess.noValidOperations'))
        processing.value = false
        return
      }
      params = {
        operation: 'video_edit',
        operations: validOps,
      }
    }

    const result = await postProcessVideo(props.generationId, params)
    ElMessage.success(t('history.postProcess.processSuccess'))
    emit('success', result)
    emit('update:visible', false)
  } catch (err: any) {
    // 错误提示由 client 拦截器统一处理
    console.error('[PostProcess] 处理失败:', err)
  } finally {
    processing.value = false
  }
}
</script>

<style scoped>
/* 操作类型 Tab */
.op-tabs {
  margin-bottom: 20px;
  width: 100%;
}

.op-tabs :deep(.el-radio-button) {
  flex: 1;
}

.op-tabs :deep(.el-radio-button__inner) {
  width: 100%;
}

/* 配置区 */
.op-config {
  min-height: 120px;
}

.config-row {
  display: flex;
  align-items: center;
  margin-bottom: 16px;
  gap: 12px;
}

.config-label {
  width: 100px;
  font-size: 14px;
  color: var(--el-text-color-primary);
  flex-shrink: 0;
}

.config-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* 预设说明 */
.preset-desc {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  margin-top: 8px;
}

.preset-desc .el-icon {
  margin-top: 2px;
  flex-shrink: 0;
}

/* 剪辑操作列表 */
.duration-hint {
  padding: 8px 12px;
  background: var(--el-color-info-light-9);
  border-radius: 4px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  margin-bottom: 12px;
}

.edit-ops {
  margin-bottom: 12px;
}

.edit-op-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.op-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.empty-ops {
  padding: 20px;
  text-align: center;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}

/* 保留区间预览 */
.keep-preview {
  margin-top: 16px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.keep-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.keep-bar {
  position: relative;
  height: 28px;
  background: var(--el-fill-color-dark);
  border-radius: 4px;
  overflow: hidden;
}

.keep-segment {
  position: absolute;
  top: 0;
  bottom: 0;
  background: var(--el-color-success-light-3);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--el-color-success-dark-2);
  border-right: 1px solid var(--el-color-success-light-5);
  overflow: hidden;
  white-space: nowrap;
}

.keep-summary {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
</style>
