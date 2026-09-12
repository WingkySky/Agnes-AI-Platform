<!-- =====================================================
     添加片段对话框 AddClipDialog
     - 选择轨道类型（video/audio/subtitle）
     - 设置起始时间、时长
     - 字幕片段可填字幕文本
     - 视频片段可选填转场类型与时长
     - 提交后 emit create 事件
     ===================================================== -->

<template>
  <el-dialog
    v-model="visible"
    title="添加片段"
    width="420px"
    :close-on-click-modal="false"
    @closed="resetForm"
  >
    <el-form :model="form" label-width="80px" size="small">
      <el-form-item label="轨道类型">
        <el-radio-group v-model="form.track_type">
          <el-radio-button label="video">视频</el-radio-button>
          <el-radio-button label="audio">音频</el-radio-button>
          <el-radio-button label="subtitle">字幕</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="起始时间">
        <el-input-number
          v-model="form.start_time"
          :min="0"
          :step="0.1"
          :precision="2"
          controls-position="right"
        />
        <span class="unit">秒</span>
      </el-form-item>

      <el-form-item label="时长">
        <el-input-number
          v-model="form.duration"
          :min="0.1"
          :step="0.1"
          :precision="2"
          controls-position="right"
        />
        <span class="unit">秒</span>
      </el-form-item>

      <!-- 字幕片段：字幕文本 -->
      <template v-if="form.track_type === 'subtitle'">
        <el-form-item label="字幕文本">
          <el-input
            v-model="form.subtitle_text"
            type="textarea"
            :rows="2"
            placeholder="请输入字幕文本"
            maxlength="200"
            show-word-limit
          />
        </el-form-item>
      </template>

      <!-- 视频片段：转场 -->
      <template v-if="form.track_type === 'video'">
        <el-form-item label="转场类型">
          <el-select v-model="form.transition_type" placeholder="选择转场">
            <el-option label="无" value="none" />
            <el-option label="淡入淡出" value="fade" />
            <el-option label="滑动" value="slide" />
            <el-option label="擦除" value="wipe" />
            <el-option label="溶解" value="dissolve" />
          </el-select>
        </el-form-item>
        <el-form-item label="转场时长">
          <el-input-number
            v-model="form.transition_duration"
            :min="0"
            :max="5"
            :step="0.1"
            :precision="2"
            :disabled="form.transition_type === 'none'"
            controls-position="right"
          />
          <span class="unit">秒</span>
        </el-form-item>
      </template>

      <el-form-item label="轨道序号">
        <el-input-number
          v-model="form.track_index"
          :min="0"
          :step="1"
          controls-position="right"
        />
        <span class="unit">默认 0（主轨道）</span>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="loading" @click="onSubmit">添加</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, reactive, computed } from 'vue'
import type {
  TimelineClipCreateRequest,
  TimelineTrackType,
  TransitionType,
} from '@/types/project'

const props = defineProps<{
  modelValue: boolean
  loading?: boolean
  /** 建议的起始时间（如当前播放头位置） */
  suggestedStartTime?: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'create', data: TimelineClipCreateRequest): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val: boolean) => emit('update:modelValue', val),
})

const form = reactive({
  track_type: 'video' as TimelineTrackType,
  track_index: 0,
  start_time: 0,
  duration: 3,
  transition_type: 'none' as TransitionType,
  transition_duration: 0.5,
  subtitle_text: '',
})

// 打开对话框时用 suggestedStartTime 预填起始时间
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      form.start_time = props.suggestedStartTime ?? 0
    }
  },
)

function resetForm() {
  form.track_type = 'video'
  form.track_index = 0
  form.start_time = 0
  form.duration = 3
  form.transition_type = 'none'
  form.transition_duration = 0.5
  form.subtitle_text = ''
}

function onSubmit() {
  const payload: TimelineClipCreateRequest = {
    track_type: form.track_type,
    track_index: form.track_index,
    start_time: form.start_time,
    duration: form.duration,
    transition_type: form.transition_type,
    transition_duration: form.transition_duration,
    sort_order: 0,
  }
  if (form.track_type === 'subtitle' && form.subtitle_text) {
    payload.subtitle_text = form.subtitle_text
  }
  emit('create', payload)
  visible.value = false
}
</script>

<style scoped>
.unit {
  margin-left: 6px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
</style>
