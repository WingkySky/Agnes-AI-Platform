<!-- =====================================================
     音色选择对话框 VoicePickerDialog
     - 展示内置音色库（8 个音色，按性别分组）
     - 支持为角色固定音色（同角色同声音策略）
     - 暴露 v-model:visible + 选中的 voice_id
     ===================================================== -->

<template>
  <el-dialog
    v-model="visible"
    title="选择音色"
    width="600px"
    :close-on-click-modal="false"
    append-to-body
  >
    <el-radio-group v-model="selectedVoiceId" class="voice-group">
      <div
        v-for="voice in voices"
        :key="voice.voice_id"
        class="voice-option"
        :class="{ selected: selectedVoiceId === voice.voice_id }"
      >
        <el-radio :value="voice.voice_id">
          <div class="voice-info">
            <span class="voice-name">{{ voice.name }}</span>
            <el-tag
              size="small"
              :type="genderTagType(voice.gender)"
              effect="plain"
            >{{ genderLabel(voice.gender) }}</el-tag>
            <span class="voice-suitable">{{ voice.suitable_for }}</span>
          </div>
        </el-radio>
      </div>
    </el-radio-group>

    <div v-if="voices.length === 0" class="empty-tip">
      <el-icon :size="32"><Microphone /></el-icon>
      <span>音色列表加载中...</span>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :disabled="!selectedVoiceId"
        @click="handleConfirm"
      >确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { Microphone } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import type { VoiceOption } from '@/types/project'

const props = defineProps<{
  /** 默认选中的音色 ID */
  defaultVoiceId?: string | null
}>()

const emit = defineEmits<{
  (e: 'confirm', voiceId: string, voiceName: string): void
}>()

const visible = defineModel<boolean>('visible', { default: false })

const projectStore = useProjectStore()

// 选中的音色 ID
const selectedVoiceId = ref<string | null>(props.defaultVoiceId || null)

// 内置音色列表
const voices = computed<VoiceOption[]>(() => projectStore.builtinVoices)

// 对话框打开时加载音色列表 + 同步默认值
watch(visible, (open) => {
  if (open) {
    selectedVoiceId.value = props.defaultVoiceId || null
    if (voices.value.length === 0) {
      projectStore.fetchBuiltinVoices()
    }
  }
})

function genderLabel(gender: string): string {
  if (gender === 'male') return '男'
  if (gender === 'female') return '女'
  return '中'
}

function genderTagType(gender: string): 'info' | 'danger' | 'warning' {
  if (gender === 'male') return 'info'
  if (gender === 'female') return 'danger'
  return 'warning'
}

function handleConfirm() {
  if (!selectedVoiceId.value) return
  const voice = voices.value.find((v) => v.voice_id === selectedVoiceId.value)
  emit('confirm', selectedVoiceId.value, voice?.name || selectedVoiceId.value)
  visible.value = false
}
</script>

<style scoped>
.voice-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.voice-option {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  transition: all 0.2s;
  cursor: pointer;
}

.voice-option:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}

.voice-option.selected {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.voice-info {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.voice-name {
  font-weight: 600;
  font-size: 14px;
}

.voice-suitable {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.empty-tip {
  padding: 32px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
