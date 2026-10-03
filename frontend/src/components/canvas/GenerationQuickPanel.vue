<!--
  GenerationQuickPanel.vue
  轻量级生成配置弹窗：从文本/图片节点快速触发生图/生视频
  - 源内容预览（文本内容或图片缩略图）
  - 辅助提示词输入（支持 @图片1/@文本2 引用源节点的上游节点）
  - 模型/尺寸/比例/时长/数量等简单参数选择；图生视频支持首尾帧模式
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
        ref="auxInputRef"
        v-model="auxPrompt"
        class="field-textarea"
        :placeholder="promptPlaceholder"
        rows="3"
        @input="handleMentionInput"
        @keydown="handleMentionKeyDown"
        @blur="handleMentionBlur"
      />
      <ComposerMentionPopup
        :visible="mentionPopupVisible"
        :candidates="mentionCandidates"
        :active-index="mentionActiveIndex"
        :position="mentionPopupPosition"
        @select="selectMention"
        @shield-blur="handlePopupMouseDown"
      />
    </div>

    <!-- 模型选择 -->
    <div class="field">
      <label class="field-label">{{ t('canvas.quickGenerate.model') }}</label>
      <select v-model="selectedModel" class="field-select">
        <option v-for="m in availableModels" :key="m.id" :value="m.id">{{ m.name }}</option>
      </select>
    </div>

    <!-- 图片模式：尺寸 + 生成数量 -->
    <template v-if="isImageMode">
      <div class="field">
        <label class="field-label">{{ t('canvas.quickGenerate.size') }}</label>
        <select v-model="selectedSize" class="field-select">
          <option v-for="s in imageSizeOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
        </select>
      </div>
      <div class="field">
        <label class="field-label">{{ t('canvas.quickGenerate.count') }}</label>
        <select v-model.number="selectedCount" class="field-select">
          <option v-for="n in 4" :key="n" :value="n">{{ n }}</option>
        </select>
      </div>
    </template>

    <!-- 视频模式：比例 + 时长 + 首尾帧 -->
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
      <!-- 首尾帧模式（仅图生视频）：源图为首帧，可选画布图片节点作尾帧 -->
      <template v-if="isImageSource">
        <div class="field field-inline">
          <el-switch v-model="useKeyframes" size="small" />
          <span class="field-inline-label">{{ t('canvas.quickGenerate.keyframesMode') }}</span>
        </div>
        <div v-if="useKeyframes" class="field">
          <label class="field-label">{{ t('canvas.quickGenerate.tailFrame') }}</label>
          <select v-model="tailFrameId" class="field-select">
            <option value="" disabled>{{ t('canvas.quickGenerate.tailFramePlaceholder') }}</option>
            <option v-for="p in imageNodeOptions" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
      </template>
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
import { ref, computed, watch, type PropType } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from '@/i18n'
import { useModelsStore } from '@/stores/models'
import { useCanvasStore } from '@/stores/canvas'
import { usePreferencesStore } from '@/stores/preferences'
import ComposerMentionPopup from '@/components/canvas/ComposerMentionPopup.vue'
import { useNodeMention } from '@/composables/useNodeMention'
import type { CanvasPanel } from '@/stores/canvas'

const { t } = useI18n()
const modelsStore = useModelsStore()
const canvasStore = useCanvasStore()
const prefsStore = usePreferencesStore()

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  sourcePanel: { type: Object as PropType<CanvasPanel | null>, default: null },
  mode: { type: String, default: 'text2image' },
})

const emit = defineEmits(['update:modelValue', 'generate'])

// 弹窗标题（根据模式动态显示：文生图/文生视频/图生图/图生视频）
const title = computed(() => t(`canvas.node.configMode.${props.mode}`))

// 源内容预览
const sourceContent = computed(() => String(props.sourcePanel?.content?.content ?? ''))
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

// 可用视频时长（按当前所选模型的 gen_params 档位，未配置用全局）
const availableDurations = computed(() => modelsStore.getModelVideoDurations(selectedModel.value))

// 画布图片节点候选（首尾帧尾帧选择，排除源节点自身）
const imageNodeOptions = computed(() =>
  canvasStore.panels
    .filter(p => p.type === 'image' && p.id !== props.sourcePanel?.id && p.content?.content)
    .map(p => ({ id: p.id, name: p.name || t('canvas.quickGenerate.sourceImage') }))
)

// 表单状态
const auxPrompt = ref('')
const selectedModel = ref('')
const selectedSize = ref('1024x1024')
const selectedCount = ref(1)
const selectedAspectRatio = ref('16:9')
const selectedSeconds = ref(5)
const useKeyframes = ref(false)
const tailFrameId = ref('')

// 辅助提示词 placeholder（文本源可选，图片源必填）
const promptPlaceholder = computed(() =>
  isTextSource.value
    ? t('canvas.quickGenerate.auxPromptPlaceholderText')
    : t('canvas.quickGenerate.auxPromptPlaceholderImage')
)

/* ---------- @ 提及（引用源节点的上游节点，与生成时的序号解析同源） ---------- */
const auxInputRef = ref<HTMLTextAreaElement | null>(null)
const {
  mentionPopupVisible,
  mentionActiveIndex,
  mentionCandidates,
  mentionPopupPosition,
  handleInput: handleMentionInput,
  handleKeyDown: handleMentionKeyDown,
  handleBlur: handleMentionBlur,
  handlePopupMouseDown,
  selectMention,
  setCurrentPanel,
} = useNodeMention(auxInputRef)

// 弹窗打开时初始化默认值
watch(() => props.modelValue, (val) => {
  if (val) {
    initDefaults()
    setCurrentPanel(props.sourcePanel?.id || null)
  } else {
    setCurrentPanel(null)
  }
})

// 初始化表单默认值：模型用默认模型，尺寸/比例/时长用第一项，数量跟随偏好
function initDefaults() {
  auxPrompt.value = ''
  selectedModel.value = modelsStore.getDefaultModelByMode(props.mode) || ''
  selectedCount.value = Math.max(1, Number(prefsStore.generation?.default_image_count) || 1)
  useKeyframes.value = false
  tailFrameId.value = ''
  if (isImageMode.value) {
    selectedSize.value = imageSizeOptions.value[0]?.value || '1024x1024'
  }
  if (isVideoMode.value) {
    selectedAspectRatio.value = videoAspectRatioOptions.value[0]?.value || '16:9'
    selectedSeconds.value = availableDurations.value[0] || 5
  }
}

// 生成按钮点击：校验后 emit generate 并关闭弹窗
async function handleGenerate() {
  // 图片源时辅助提示词必填（图生图/图生视频都需要 prompt）
  if (isImageSource.value && !auxPrompt.value.trim()) {
    ElMessage.warning(t('canvas.quickGenerate.promptRequired'))
    return
  }
  // 首尾帧模式必须选尾帧
  if (isVideoMode.value && useKeyframes.value && !tailFrameId.value) {
    ElMessage.warning(t('canvas.quickGenerate.tailFrameRequired'))
    return
  }

  const payload: any = {
    mode: props.mode,
    prompt: auxPrompt.value,
    model: selectedModel.value,
  }
  if (isImageMode.value) {
    payload.size = selectedSize.value
    payload.count = selectedCount.value
    // 数量选择回写偏好（下次打开记住）
    if (selectedCount.value !== (Number(prefsStore.generation?.default_image_count) || 1)) {
      void prefsStore.updatePreferences({ generation: { default_image_count: selectedCount.value } })
    }
  }
  if (isVideoMode.value) {
    payload.aspect_ratio = selectedAspectRatio.value
    payload.seconds = Number(selectedSeconds.value)
    if (isImageSource.value && useKeyframes.value) {
      payload.use_keyframes = true
      payload.tail_frame_id = tailFrameId.value
    }
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

.field-inline {
  display: flex;
  align-items: center;
  gap: 8px;
}

.field-inline-label {
  font-size: 13px;
  font-weight: 500;
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
