<!--
  StepEditDialog.vue
  步骤编辑弹窗
  - 编辑步骤名称、颜色
  - 从流程模式指示条或步骤分组框触发
-->
<template>
  <el-dialog
    :model-value="visible"
    :title="t('canvas.stepEditTitle')"
    width="400px"
    :append-to-body="true"
    @close="handleClose"
  >
    <div class="step-edit-form">
      <div class="form-item">
        <label>{{ t('canvas.stepName') }}</label>
        <el-input
          v-model="form.name"
          :placeholder="t('canvas.stepNamePlaceholder')"
          maxlength="30"
          show-word-limit
        />
      </div>
      <div class="form-item">
        <label>{{ t('canvas.stepColor') }}</label>
        <div class="color-picker">
          <button
            v-for="c in colorOptions"
            :key="c"
            class="color-swatch"
            :class="{ active: form.color === c }"
            :style="{ background: c }"
            @click="form.color = c"
          />
        </div>
      </div>
      <div class="form-item">
        <label>{{ t('canvas.stepDescription') }}</label>
        <el-input
          v-model="form.description"
          type="textarea"
          :placeholder="t('canvas.stepDescriptionPlaceholder')"
          :rows="2"
          maxlength="200"
          show-word-limit
        />
      </div>
    </div>

    <template #footer>
      <el-button @click="handleClose">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" @click="handleSave">{{ t('common.save') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import type { CanvasStep } from '@/stores/canvas'

const { t } = useI18n()

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  step: {
    type: Object as () => CanvasStep | null,
    default: null,
  },
})

const emit = defineEmits(['close', 'save'])

const colorOptions = [
  '#409eff',
  '#67c23a',
  '#e6a23c',
  '#f56c6c',
  '#9b59b6',
  '#1abc9c',
  '#3498db',
  '#e74c3c',
]

const form = ref({
  name: '',
  color: '#409eff',
  description: '',
})

// 当 step 变化时，初始化表单
watch(
  () => props.step,
  (step) => {
    if (step) {
      form.value = {
        name: step.name || '',
        color: step.color || '#409eff',
        description: step.description || '',
      }
    }
  },
  { immediate: true }
)

function handleClose() {
  emit('close')
}

function handleSave() {
  if (!form.value.name.trim()) return
  emit('save', {
    id: props.step?.id,
    name: form.value.name.trim(),
    color: form.value.color,
    description: form.value.description?.trim() || undefined,
  })
}
</script>

<style scoped>
.step-edit-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-item label {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-regular);
}

.color-picker {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.color-swatch {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.15s ease;
  padding: 0;
}

.color-swatch:hover {
  transform: scale(1.15);
}

.color-swatch.active {
  border-color: #fff;
  box-shadow: 0 0 0 2px var(--el-color-primary);
}
</style>
