<!-- =====================================================
     StyleSelector 风格选择器组件
     - 从 useStylesStore 加载风格预设
     - 复用 PromptTemplates 芯片组件展示
     - 通过 v-model 双向绑定选中的 styleId
     ===================================================== -->

<template>
  <div class="style-selector">
    <PromptTemplates
      :title="t('pipelineRun.styleSelectorTitle')"
      :templates="styleChips"
      type="style"
      @select="onSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '@/i18n'
import PromptTemplates from '@/components/PromptTemplates.vue'
import { useStylesStore } from '@/stores/styles'

const props = defineProps<{
  modelValue?: number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [id: number]
}>()

const stylesStore = useStylesStore()
const { t } = useI18n()

/** 将风格预设转为 PromptTemplates 所需的芯片格式 */
const styleChips = computed(() =>
  stylesStore.stylePresets.map(s => ({
    label: s.name,
    prompt: String(s.id), // 复用 chip 机制，传 id
    preview: s.preview_image,
  }))
)

function onSelect(prompt: string) {
  emit('update:modelValue', Number(prompt))
}
</script>

<style scoped>
.style-selector {
  width: 100%;
}
</style>
