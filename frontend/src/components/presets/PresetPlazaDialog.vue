<!-- =====================================================
     PresetPlazaDialog — 统一预设广场弹窗
     生成页（生图/生视频）点击"风格库/特效库"按钮弹出，
     内嵌 PresetGallery，应用后关闭并回传预设。
     ===================================================== -->

<template>
  <el-dialog
    :model-value="modelValue"
    width="1240px"
    top="4vh"
    :close-on-click-modal="true"
    destroy-on-close
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <template #header>
      <span class="plaza-title">{{ title }}</span>
    </template>
    <PresetGallery :context="context" @apply="onApply" />
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '@/i18n'
import PresetGallery from './PresetGallery.vue'
import type { PromptPreset, PresetContext } from '@/types/preset'

const props = defineProps<{
  modelValue: boolean
  context: PresetContext
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  apply: [preset: PromptPreset]
}>()

const { t } = useI18n()

const title = computed(() =>
  props.context === 'video' ? t('presets.plaza.videoTitle') : t('presets.plaza.imageTitle')
)

function onApply(preset: PromptPreset) {
  emit('apply', preset)
  emit('update:modelValue', false)
}
</script>

<style scoped>
.plaza-title {
  font-size: 16px;
  font-weight: 600;
}
</style>
