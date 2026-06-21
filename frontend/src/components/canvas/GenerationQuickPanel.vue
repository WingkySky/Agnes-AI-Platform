<!--
  GenerationQuickPanel.vue
  轻量级生成配置弹窗：从文本/图片节点快速触发生图/生视频
  - 源内容预览（文本内容或图片缩略图）
  - 辅助提示词输入（文本源可选，图片源必填）
  - 模型/尺寸/比例/时长等简单参数选择
  - 点击生成后 emit generate(payload)，由父组件执行实际生成
-->
<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    :title="title"
    width="480px"
    align-center
    append-to-body
  >
    <!-- 源内容预览 -->
    <div class="source-preview">
      <div class="source-label">{{ sourceLabel }}</div>
      <div v-if="isTextSource" class="source-text">{{ sourceContent }}</div>
      <img v-else-if="isImageSource && sourceContent" :src="sourceContent" class="source-image" />
    </div>

    <!-- 辅助提示词 -->
    <div class="field">
      <label class="field-label">{{ t('canvas.quickGenerate.auxPrompt') }}</label>
      <textarea
        v-model="auxPrompt"
        class="field-textarea"
        :placeholder="promptPlaceholder"
        rows="3"
      />
    </div>

    <!-- 模型选择 -->
    <div class="field">
      <label class="field-label">{{ t('canvas.quickGenerate.model') }}</label>
      <select v-model="selectedModel" class="field-select">
        <option v-for="m in availableModels" :key="m.id" :value="m.id">{{ m.name }}</option>
      </select>
    </div>

    <!-- 图片模式：尺寸选择 -->
    <div v-if="isImageMode" class="field">
      <label class="field-label">{{ t('canvas.quickGenerate.size') }}</label>
      <select v-model="selectedSize" class="field-select">
        <option v-for="s in imageSizeOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
      </select>
    </div>

    <!-- 视频模式：比例 + 时长 -->
    <template v-if="isVideoMode">
      <div class="field">
        <label class="field-label">{{ t('canvas.quickGenerate.aspectRatio') }}</label>
        <select v-model="selectedAspectRatio" class="field-select">
          <option v-for="r in videoAspectRatioOptions" :key="r.value" :value="r.value">{{ r.label }}</option>
        </select>
      </div>
      <div class="field">
        <label class="field-label">{{ t('canvas.quickGenerate.duration') }}</label>
        <select v-model="selectedSeconds" class="field-select">
          <option v-for="s in availableDurations" :key="s" :value="s">{{ s }}{{ t('canvas.node.secondsSuffix') }}</option>
        </select>
      </div>
    </template>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">{{ t('canvas.quickGenerate.cancel') }}</el-button>
      <el-button type="primary" @click="handleGenerate">
        {{ isVideoMode ? t('canvas.node.generateVideoBtn') : t('canvas.node.generateImageBtn') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from '@/i18n'
import { useModelsStore } from '@/stores/models'

const { t } = useI18n()
const modelsStore = useModelsStore()

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  sourcePanel: { type: Object, default: null },
  mode: { type: String, default: 'text2image' },
})

const emit = defineEmits(['update:modelValue', 'generate'])

// 弹窗标题（根据模式动态显示：文生图/文生视频/图生图/图生视频）
const title = computed(() => t(`canvas.node.configMode.${props.mode}`))

// 源内容预览
const sourceContent = computed(() => props.sourcePanel?.content?.content || '')
const isTextSource = computed(() => props.mode.startsWith('text'))
const isImageSource = computed(() => props.mode.startsWith('image'))
const sourceLabel = computed(() =>
  isTextSource.value ? t('canvas.quickGenerate.sourceText') : t('canvas.quickGenerate.sourceImage')
)

// 模式判断：视频模式 = mode 包含 'video'，图片模式 = 其他
const isVideoMode = computed(() => props.mode.includes('video'))
const isImageMode = computed(() => !isVideoMode.value)

// 模型列表（按模式筛选）
const availableModels = computed(() => modelsStore.getModelsByMode(props.mode))

// 图片尺寸选项（结构化，含友好标签）
const imageSizeOptions = computed(() => {
  const opts = modelsStore.imageSizeOptions
  if (opts.length > 0) return opts
  return (modelsStore.imageSizes.length > 0 ? modelsStore.imageSizes : ['1024x1024', '768x1024', '1024x768', '1280x720'])
    .map(v => ({ value: v, w: 1, h: 1, label: v }))
})

// 视频宽高比选项
const videoAspectRatioOptions = computed(() => modelsStore.getModelParamsConfig().videoAspectRatios)

// 可用视频时长
const availableDurations = computed(() => modelsStore.getModelParamsConfig().videoDurations)

// 表单状态
const auxPrompt = ref('')
const selectedModel = ref('')
const selectedSize = ref('1024x1024')
const selectedAspectRatio = ref('16:9')
const selectedSeconds = ref(5)

// 辅助提示词 placeholder（文本源可选，图片源必填）
const promptPlaceholder = computed(() =>
  isTextSource.value
    ? t('canvas.quickGenerate.auxPromptPlaceholderText')
    : t('canvas.quickGenerate.auxPromptPlaceholderImage')
)

// 弹窗打开时初始化默认值
watch(() => props.modelValue, (val) => {
  if (val) initDefaults()
})

// 初始化表单默认值：模型用默认模型，尺寸/比例/时长用第一项
function initDefaults() {
  auxPrompt.value = ''
  selectedModel.value = modelsStore.getDefaultModelByMode(props.mode) || ''
  if (isImageMode.value) {
    selectedSize.value = imageSizeOptions.value[0]?.value || '1024x1024'
  }
  if (isVideoMode.value) {
    selectedAspectRatio.value = videoAspectRatioOptions.value[0]?.value || '16:9'
    selectedSeconds.value = availableDurations.value[0] || 5
  }
}

// 生成按钮点击：校验后 emit generate 并关闭弹窗
function handleGenerate() {
  // 图片源时辅助提示词必填（图生图/图生视频都需要 prompt）
  if (isImageSource.value && !auxPrompt.value.trim()) {
    ElMessage.warning(t('canvas.quickGenerate.promptRequired'))
    return
  }

  const payload: any = {
    mode: props.mode,
    prompt: auxPrompt.value,
    model: selectedModel.value,
  }
  if (isImageMode.value) {
    payload.size = selectedSize.value
  }
  if (isVideoMode.value) {
    payload.aspect_ratio = selectedAspectRatio.value
    payload.seconds = Number(selectedSeconds.value)
  }

  emit('generate', payload)
  emit('update:modelValue', false)
}
</script>

<style scoped>
/* 源内容预览区 */
.source-preview {
  margin-bottom: 16px;
  padding: 12px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: var(--agnes-bg-hover);
}

.source-label {
  font-size: 12px;
  color: var(--agnes-text-muted);
  margin-bottom: 8px;
}

.source-text {
  font-size: 14px;
  line-height: 1.6;
  max-height: 120px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.source-image {
  max-width: 100%;
  max-height: 200px;
  border-radius: 6px;
  object-fit: contain;
}

/* 表单字段 */
.field {
  margin-bottom: 16px;
}

.field-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
}

.field-textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--agnes-border);
  border-radius: 6px;
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
  background: var(--agnes-bg);
  color: var(--agnes-text);
}

.field-textarea:focus {
  outline: none;
  border-color: var(--agnes-primary);
}

.field-select {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--agnes-border);
  border-radius: 6px;
  font-size: 14px;
  background: var(--agnes-bg);
  color: var(--agnes-text);
}
</style>
