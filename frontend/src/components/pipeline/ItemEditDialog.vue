<!--
  ItemEditDialog 元素编辑弹窗
  - 支持三种编辑模式：文本 / 图片 / 提示词
  - 文本模式下若 item 为分镜条目（含 scene_num / dialogue / camera_angle 等字段），
    自动切换为分镜字段编辑表单
  - 图片模式：el-upload 选择图片，前端校验格式（jpg/png/webp）和大小（≤10MB）
  - 提示词模式：编辑 prompt_override 用于重生时覆盖原 prompt
  - 通过 v-model:modelValue 控制显隐，save 事件回传编辑结果
-->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="60%"
    :close-on-click-modal="false"
    destroy-on-close
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
    @close="handleClose"
  >
    <el-form ref="formRef" :model="form" label-position="top" class="item-edit-form">
      <!-- ============ 文本模式 · 分镜条目 ============ -->
      <template v-if="mode === 'text' && isStoryboardItem">
        <el-form-item :label="t('itemEditDialog.sceneIndex')">
          <el-input-number
            v-model="storyboard.scene_num"
            :min="0"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item :label="t('itemEditDialog.sceneDescription')">
          <el-input
            v-model="storyboard.description"
            type="textarea"
            :rows="3"
            :placeholder="t('itemEditDialog.sceneDescriptionPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('itemEditDialog.sceneCharacters')">
          <el-input
            v-model="storyboard.charactersText"
            :placeholder="t('itemEditDialog.sceneCharactersPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('itemEditDialog.sceneDialogue')">
          <el-input
            v-model="storyboard.dialogue"
            type="textarea"
            :rows="2"
            :placeholder="t('itemEditDialog.sceneDialoguePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('itemEditDialog.sceneShot')">
          <el-input
            v-model="storyboard.camera_angle"
            :placeholder="t('itemEditDialog.sceneShotPlaceholder')"
          />
        </el-form-item>
      </template>

      <!-- ============ 文本模式 · 普通文本 ============ -->
      <template v-else-if="mode === 'text'">
        <el-form-item :label="t('itemEditDialog.settingTextLabel')">
          <el-input
            v-model="form.setting_text"
            type="textarea"
            :rows="4"
            :placeholder="t('itemEditDialog.settingTextPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('itemEditDialog.descriptionLabel')">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            :placeholder="t('itemEditDialog.descriptionPlaceholder')"
          />
        </el-form-item>
      </template>

      <!-- ============ 图片模式 · 上传图片 ============ -->
      <template v-else-if="mode === 'image'">
        <el-form-item :label="t('itemEditDialog.uploadImage')">
          <el-upload
            class="image-uploader"
            :auto-upload="false"
            :show-file-list="false"
            :on-change="handleFileChange"
            accept="image/jpeg,image/png,image/webp"
            drag
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div class="upload-text">{{ t('itemEditDialog.uploadHint') }}</div>
            <template #tip>
              <div class="upload-tip">
                {{ t('itemEditDialog.uploadDesc', { n: maxSizeMB }) }}
              </div>
            </template>
          </el-upload>
        </el-form-item>

        <!-- 新上传图片预览 -->
        <el-form-item v-if="previewUrl" :label="t('itemEditDialog.imagePreview')">
          <div class="preview-wrapper">
            <img :src="previewUrl" class="preview-img" :alt="t('itemEditDialog.imagePreview')" />
            <el-button size="small" type="danger" plain @click="clearImage">
              {{ t('common.delete') }}
            </el-button>
          </div>
        </el-form-item>
        <!-- 原图预览（尚未选择新图时展示） -->
        <el-form-item v-else-if="item?.image_url" :label="t('itemEditDialog.imagePreview')">
          <div class="preview-wrapper">
            <img :src="item.image_url" class="preview-img" :alt="t('itemEditDialog.imagePreview')" />
          </div>
        </el-form-item>
      </template>

      <!-- ============ 提示词模式 ============ -->
      <template v-else-if="mode === 'prompt'">
        <el-form-item :label="t('itemEditDialog.promptLabel')">
          <el-input
            v-model="form.prompt_override"
            type="textarea"
            :rows="6"
            :placeholder="t('itemEditDialog.promptPlaceholder')"
          />
        </el-form-item>
      </template>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSave">
        {{ t('common.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { useI18n } from '@/i18n'
import { ElMessage, type UploadFile, type FormInstance } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import type { StepItem } from '@/api/pipeline'

// ================ Props / Emits ================
const props = defineProps<{
  /** v-model 控制弹窗显隐 */
  modelValue: boolean
  /** 编辑的元素；为 null 时弹窗内容为空 */
  item: StepItem | null
  /** 编辑模式：text=文本 / image=图片 / prompt=提示词 */
  mode: 'text' | 'image' | 'prompt'
  /** 所属步骤 key（用于父组件区分来源） */
  stepKey: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  /** 保存事件；file 仅 image 模式携带，prompt_override 仅 prompt 模式携带 */
  (e: 'save', data: { item: StepItem; mode: string; file?: File; prompt_override?: string }): void
}>()

const { t } = useI18n()

// ================ 内部状态 ================
const formRef = ref<FormInstance>()
const submitting = ref(false)
// 图片上传限制
const maxSizeMB = 10
const allowedTypes = ['image/jpeg', 'image/png', 'image/webp']

// 文本 / 提示词模式表单
const form = reactive({
  setting_text: '',
  description: '',
  prompt_override: '',
})

// 图片模式状态
const selectedFile = ref<File | null>(null)
const previewUrl = ref<string>('')

// 分镜条目表单（mode='text' 且 item 为分镜条目时使用）
// characters_in_scene 在后端是数组，前端用逗号分隔字符串编辑
const storyboard = reactive({
  scene_num: 0,
  description: '',
  dialogue: '',
  camera_angle: '',
  charactersText: '',
})

// ================ 计算属性 ================
// 检测 item 是否为分镜条目（含 scene_num / dialogue / camera_angle 字段之一）
// StepItem 类型未直接声明这些字段，但实际数据可能携带（后端 storyboard 场景结构）
const isStoryboardItem = computed(() => {
  const raw = props.item as any
  return !!(
    raw &&
    (raw.scene_num !== undefined ||
      raw.dialogue !== undefined ||
      raw.camera_angle !== undefined)
  )
})

// 弹窗标题：基础标题 + 当前模式标签
const dialogTitle = computed(() => {
  const base = t('itemEditDialog.title')
  const modeLabel =
    props.mode === 'text'
      ? t('itemEditDialog.textTab')
      : props.mode === 'image'
        ? t('itemEditDialog.imageTab')
        : t('itemEditDialog.promptTab')
  return `${base} · ${modeLabel}`
})

// ================ 监听器：弹窗打开或 item 变化时初始化表单 ================
watch(
  () => props.modelValue,
  (visible) => {
    if (visible) initForm()
  },
)

watch(
  () => props.item,
  () => {
    if (props.modelValue) initForm()
  },
)

/** 根据当前 item 初始化所有表单字段 */
function initForm() {
  const item = props.item
  // 文本 / 提示词字段
  form.setting_text = item?.setting_text || ''
  form.description = item?.description || ''
  // prompt 模式优先使用 item.prompt，回退到 setting_text
  form.prompt_override = (item as any)?.prompt || item?.setting_text || ''

  // 图片模式重置
  selectedFile.value = null
  previewUrl.value = ''

  // 分镜字段初始化
  const raw = item as any
  storyboard.scene_num = raw?.scene_num ?? 0
  storyboard.description = raw?.description || item?.description || ''
  storyboard.dialogue = raw?.dialogue || ''
  storyboard.camera_angle = raw?.camera_angle || ''
  // characters_in_scene 数组转逗号分隔字符串
  const chars = raw?.characters_in_scene
  storyboard.charactersText = Array.isArray(chars) ? chars.join(', ') : ''
}

// ================ 图片上传：校验 + 选择 ================
/** 校验图片格式与大小，不符合时 ElMessage.error 提示 */
function validateImage(file: File): boolean {
  if (!allowedTypes.includes(file.type)) {
    ElMessage.error(t('itemEditDialog.imageInvalid'))
    return false
  }
  if (file.size > maxSizeMB * 1024 * 1024) {
    ElMessage.error(t('itemEditDialog.imageTooLarge', { n: maxSizeMB }))
    return false
  }
  return true
}

/** el-upload on-change：选择文件时触发，校验通过后生成预览 */
function handleFileChange(file: UploadFile) {
  if (!file.raw) return
  if (!validateImage(file.raw)) return
  // 替换已有文件：先释放旧预览 URL
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  selectedFile.value = file.raw
  previewUrl.value = URL.createObjectURL(file.raw)
}

/** 清除已选图片 */
function clearImage() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  selectedFile.value = null
  previewUrl.value = ''
}

// ================ 保存 ================
function handleSave() {
  if (!props.item) {
    ElMessage.error(t('itemEditDialog.invalidForm'))
    return
  }
  submitting.value = true
  try {
    // 基于原 item 浅拷贝，避免直接修改 props
    const baseItem: StepItem = { ...props.item }

    if (props.mode === 'text') {
      if (isStoryboardItem.value) {
        // 分镜模式：写回分镜字段到 item（扩展字段）
        const chars = storyboard.charactersText
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
        const extended = baseItem as any
        extended.scene_num = storyboard.scene_num
        extended.description = storyboard.description
        extended.dialogue = storyboard.dialogue
        extended.camera_angle = storyboard.camera_angle
        extended.characters_in_scene = chars
        // 同步 StepItem 标准 description 字段
        baseItem.description = storyboard.description
        emit('save', { item: baseItem, mode: 'text' })
      } else {
        // 普通文本模式
        baseItem.setting_text = form.setting_text
        baseItem.description = form.description
        emit('save', { item: baseItem, mode: 'text' })
      }
    } else if (props.mode === 'image') {
      if (!selectedFile.value) {
        ElMessage.error(t('itemEditDialog.noImage'))
        submitting.value = false
        return
      }
      emit('save', { item: baseItem, mode: 'image', file: selectedFile.value })
    } else {
      // prompt 模式
      if (!form.prompt_override.trim()) {
        ElMessage.error(t('itemEditDialog.invalidForm'))
        submitting.value = false
        return
      }
      emit('save', {
        item: baseItem,
        mode: 'prompt',
        prompt_override: form.prompt_override.trim(),
      })
    }
    emit('update:modelValue', false)
  } finally {
    submitting.value = false
  }
}

// ================ 关闭 ================
function handleClose() {
  // 释放本地预览 URL，避免内存泄漏
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  emit('update:modelValue', false)
}
</script>

<style scoped>
.item-edit-form {
  padding: 0 4px;
}

/* 图片上传区 */
.image-uploader {
  width: 100%;
}
.image-uploader :deep(.el-upload-dragger) {
  width: 100%;
  padding: 24px;
}
.upload-icon {
  font-size: 36px;
  color: var(--agnes-primary, #409eff);
  margin-bottom: 8px;
}
.upload-text {
  color: var(--agnes-text-primary, #303133);
  font-size: 14px;
}
.upload-tip {
  margin-top: 6px;
  font-size: 12px;
  color: var(--agnes-text-secondary, #909399);
}

/* 图片预览 */
.preview-wrapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
}
.preview-img {
  max-width: 100%;
  max-height: 360px;
  border-radius: 8px;
  border: 1px solid var(--agnes-border, #dcdfe6);
  object-fit: contain;
}
</style>
