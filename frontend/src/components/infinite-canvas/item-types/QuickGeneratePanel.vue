/* =====================================================
 * 快捷生成面板
 * - 输入 prompt 触发生成
 * - 选择生成类型（图片/视频）
 * ===================================================== */

<template>
  <div class="quick-gen-panel">
    <el-input
      v-model="prompt"
      type="textarea"
      :rows="3"
      :placeholder="t('canvas.enterPrompt')"
      resize="none"
    />
    <div class="gen-type-selector">
      <el-radio-group v-model="genType">
        <el-radio-button value="image">{{ t('canvas.genTypeImage') }}</el-radio-button>
        <el-radio-button value="video">{{ t('canvas.genTypeVideo') }}</el-radio-button>
      </el-radio-group>
    </div>
    <el-button
      type="primary"
      size="small"
      class="gen-btn"
      :loading="generating"
      @click="handleGenerate"
    >
      {{ t('canvas.generate') }}
    </el-button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const props = defineProps({
  panel: { type: Object, required: true },
})

const emit = defineEmits(['update'])

const prompt = ref(props.panel.content?.prompt ?? '')
const genType = ref(props.panel.content?.genType ?? 'image')
const generating = ref(false)

function handleGenerate() {
  if (!prompt.value.trim()) return
  generating.value = true
  // TODO: 调用生成 API
  // 模拟延迟后完成
  setTimeout(() => {
    generating.value = false
    emit('update', {
      content: { prompt: prompt.value, genType: genType.value },
    })
  }, 2000)
}
</script>

<style scoped>
.quick-gen-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gen-type-selector {
  display: flex;
  justify-content: center;
}

.gen-btn {
  width: 100%;
}
</style>
