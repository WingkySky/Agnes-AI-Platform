<!-- =====================================================
     片段属性面板 ClipPropertyPanel
     - 展示并编辑选中片段的属性
     - 视频片段：起始时间/时长/裁剪/转场类型/转场时长
     - 音频片段：起始时间/时长/裁剪（不可调转场）
     - 字幕片段：起始时间/时长/字幕文本
     - 删除片段按钮
     - 未选中时显示提示
     ===================================================== -->

<template>
  <div class="clip-property-panel">
    <div v-if="!clip" class="empty-state">
      <el-icon :size="32"><InfoFilled /></el-icon>
      <span>请选择一个片段查看属性</span>
    </div>

    <template v-else>
      <div class="panel-header">
        <el-icon :size="18">
          <VideoCamera v-if="clip.track_type === 'video'" />
          <Microphone v-else-if="clip.track_type === 'audio'" />
          <Document v-else />
        </el-icon>
        <span class="header-title">{{ trackTypeLabel }}片段 #{{ clip.id }}</span>
        <el-tag size="small" type="info" effect="plain">序号 {{ clip.sort_order + 1 }}</el-tag>
      </div>

      <el-form label-width="90px" size="small" :disabled="!editable">
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

        <el-form-item v-if="clip.track_type !== 'subtitle'" label="裁剪起点">
          <el-input-number
            v-model="form.trim_start"
            :min="0"
            :step="0.1"
            :precision="2"
            controls-position="right"
          />
          <span class="unit">秒</span>
        </el-form-item>

        <el-form-item v-if="clip.track_type !== 'subtitle'" label="裁剪终点">
          <el-input-number
            v-model="form.trim_end"
            :min="0"
            :step="0.1"
            :precision="2"
            controls-position="right"
          />
          <span class="unit">秒</span>
        </el-form-item>

        <!-- 视频片段：转场设置 -->
        <template v-if="clip.track_type === 'video'">
          <el-divider content-position="left">转场</el-divider>

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

        <!-- 字幕片段：文本编辑 -->
        <template v-if="clip.track_type === 'subtitle'">
          <el-divider content-position="left">字幕内容</el-divider>
          <el-form-item label="字幕文本">
            <el-input
              v-model="form.subtitle_text"
              type="textarea"
              :rows="3"
              placeholder="请输入字幕文本"
              maxlength="200"
              show-word-limit
            />
          </el-form-item>
        </template>
      </el-form>

      <!-- 底部操作 -->
      <div v-if="editable" class="panel-actions">
        <el-button type="primary" :icon="Check" @click="onSave">保存</el-button>
        <el-button type="danger" :icon="Delete" @click="$emit('delete', clip.id)">删除片段</el-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, reactive } from 'vue'
import {
  InfoFilled, VideoCamera, Microphone, Document, Check, Delete,
} from '@element-plus/icons-vue'
import type { TimelineClip, TransitionType } from '@/types/project'

const props = defineProps<{
  clip: TimelineClip | null
  editable?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', clipId: number, data: Partial<TimelineClip>): void
  (e: 'delete', clipId: number): void
}>()

const form = reactive({
  start_time: 0,
  duration: 0,
  trim_start: 0,
  trim_end: 0 as number | null,
  transition_type: 'none' as TransitionType,
  transition_duration: 0,
  subtitle_text: '',
})

// 切换选中片段时回填
watch(
  () => props.clip,
  (c) => {
    if (!c) return
    form.start_time = c.start_time
    form.duration = c.duration
    form.trim_start = c.trim_start
    form.trim_end = c.trim_end ?? 0
    form.transition_type = c.transition_type
    form.transition_duration = c.transition_duration
    form.subtitle_text = c.subtitle_text ?? ''
  },
  { immediate: true },
)

const trackTypeLabel = ref('视频')
watch(
  () => props.clip?.track_type,
  (t) => {
    if (t === 'video') trackTypeLabel.value = '视频'
    else if (t === 'audio') trackTypeLabel.value = '音频'
    else if (t === 'subtitle') trackTypeLabel.value = '字幕'
  },
  { immediate: true },
)

function onSave() {
  if (!props.clip) return
  emit('save', props.clip.id, {
    start_time: form.start_time,
    duration: form.duration,
    trim_start: form.trim_start,
    trim_end: form.trim_end,
    transition_type: form.transition_type,
    transition_duration: form.transition_duration,
    subtitle_text: form.subtitle_text,
  })
}
</script>

<style scoped>
.clip-property-panel {
  width: 320px;
  flex-shrink: 0;
  padding: 12px 16px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 64px 0;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}

.panel-header {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.header-title {
  font-weight: 600;
  font-size: 14px;
  flex: 1;
}

.unit {
  margin-left: 6px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.panel-actions {
  display: flex;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}
</style>
