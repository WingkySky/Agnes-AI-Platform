<!-- =====================================================
     PromptTemplates 预设风格芯片组件
     - 传入 templates 数组：{ label, prompt }
     - 点击时触发 @select 事件，返回选中的 prompt
     ===================================================== -->

<template>
  <div class="prompt-templates">
    <!-- 标题已国际化（title prop 可选，默认为 i18n 文案） -->
    <div class="section-title">{{ title || defaultTitle }}</div>
    <div class="tags-wrap">
      <el-tag
        v-for="(item, idx) in templates"
        :key="idx"
        :type="type"
        effect="dark"
        size="large"
        round
        class="preset-tag"
        @click="$emit('select', item.prompt)"
      >
        {{ item.label }}
      </el-tag>
    </div>
  </div>
</template>

<script setup lang="ts">
// ------ 引入 i18n ------
import { computed, type PropType } from 'vue'
import { useI18n } from '@/i18n'

const { t } = useI18n()

// 模板项类型定义
interface TemplateItem {
  label: string
  prompt: string
}

const props = defineProps({
  title: {
    type: String,
    default: ''
  },
  templates: {
    type: Array as PropType<TemplateItem[]>,
    required: true
  },
  type: {
    type: String,
    default: 'primary'
  }
})

defineEmits(['select'])

// ------ 标题默认值走 i18n ------
const defaultTitle = computed(() => t('params.stylePresets'))
</script>

<style scoped>
.prompt-templates {
  margin-bottom: 16px;
}

.section-title {
  font-size: 13px;
  color: #a0b4d6;
  margin-bottom: 10px;
  font-weight: 500;
}

.tags-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.preset-tag {
  font-size: 13px !important;
  padding: 6px 14px !important;
  height: auto !important;
  background: linear-gradient(135deg, rgba(90, 134, 255, 0.25) 0%, rgba(154, 123, 255, 0.25) 100%) !important;
  border: 1px solid rgba(120, 170, 255, 0.35) !important;
  color: #d4e3ff !important;
  font-weight: 500;
  transition: all 0.2s ease !important;
}
.preset-tag:hover {
  background: linear-gradient(135deg, rgba(90, 134, 255, 0.45) 0%, rgba(154, 123, 255, 0.45) 100%) !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(100, 150, 255, 0.3);
}
</style>
