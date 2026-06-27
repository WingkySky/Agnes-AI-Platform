<!-- =====================================================
     StyleElementEditor 用户自建风格表单
     - 弹窗形式，用于创建自定义风格元素
     - 表单字段：名称、层级、分类、提示词内容、负面提示词、默认权重、标签、公开
     - 创建成功后 emit created 事件
     ===================================================== -->

<template>
  <el-dialog
    :model-value="modelValue"
    :title="t('styleElement.createTitle')"
    width="560px"
    @update:model-value="emit('update:modelValue', $event)"
    @close="resetForm">
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="100px"
      label-position="top">
      <!-- 名称 -->
      <el-form-item :label="t('styleElement.name')" prop="name">
        <el-input
          v-model="form.name"
          :placeholder="t('styleElement.namePlaceholder')"
          maxlength="200" />
      </el-form-item>

      <!-- 层级 -->
      <el-form-item :label="t('styleElement.layer')" prop="layer">
        <el-select v-model="form.layer" :placeholder="t('styleElement.layerPlaceholder')" class="full-width">
          <el-option
            v-for="layer in layerOptions"
            :key="layer.key"
            :label="layer.name"
            :value="layer.key" />
        </el-select>
      </el-form-item>

      <!-- 细分类 -->
      <el-form-item :label="t('styleElement.category')">
        <el-input
          v-model="form.category"
          :placeholder="t('styleElement.categoryPlaceholder')"
          maxlength="50" />
      </el-form-item>

      <!-- 提示词内容 -->
      <el-form-item :label="t('styleElement.content')" prop="content">
        <el-input
          v-model="form.content"
          type="textarea"
          :rows="3"
          :placeholder="t('styleElement.contentPlaceholder')" />
      </el-form-item>

      <!-- 负面提示词 -->
      <el-form-item :label="t('styleElement.negativeContent')">
        <el-input
          v-model="form.negative_content"
          type="textarea"
          :rows="2"
          :placeholder="t('styleElement.negativePlaceholder')" />
      </el-form-item>

      <!-- 默认权重 -->
      <el-form-item :label="t('styleElement.weightDefault')">
        <el-slider
          v-model="form.weight_default"
          :min="0"
          :max="1"
          :step="0.1"
          show-input
          input-size="small" />
      </el-form-item>

      <!-- 标签 -->
      <el-form-item :label="t('styleElement.tags')">
        <el-select
          v-model="form.tags"
          multiple
          filterable
          allow-create
          default-first-option
          :placeholder="t('styleElement.tagsPlaceholder')"
          class="full-width" />
      </el-form-item>

      <!-- 是否公开 -->
      <el-form-item :label="t('styleElement.isPublic')">
        <el-switch v-model="form.is_public" />
        <span class="form-hint">{{ t('styleElement.isPublicHint') }}</span>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        {{ t('common.confirm') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from '@/i18n'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import {
  createStyleElement,
  listLayers,
  type StyleLayer,
  type LayerInfo,
  type StyleElementCreate,
} from '@/api/styleElement'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  created: []
}>()

const { t } = useI18n()

// ---------- 状态 ----------
const formRef = ref<FormInstance>()
const submitting = ref(false)
const layerOptions = ref<LayerInfo[]>([])

const form = reactive({
  name: '',
  layer: '' as StyleLayer | '',
  category: '',
  content: '',
  negative_content: '',
  weight_default: 1.0,
  tags: [] as string[],
  is_public: false,
})

// 表单校验规则
const rules = reactive<FormRules>({
  name: [{ required: true, message: () => t('styleElement.nameRequired'), trigger: 'blur' }],
  layer: [{ required: true, message: () => t('styleElement.layerRequired'), trigger: 'change' }],
  content: [{ required: true, message: () => t('styleElement.contentRequired'), trigger: 'blur' }],
})

// ---------- 方法 ----------
function resetForm() {
  form.name = ''
  form.layer = ''
  form.category = ''
  form.content = ''
  form.negative_content = ''
  form.weight_default = 1.0
  form.tags = []
  form.is_public = false
  formRef.value?.clearValidate()
}

async function handleSubmit() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    const payload: StyleElementCreate = {
      name: form.name,
      layer: form.layer as StyleLayer,
      category: form.category || undefined,
      content: form.content,
      negative_content: form.negative_content || undefined,
      weight_default: form.weight_default,
      tags: form.tags,
      is_public: form.is_public,
    }
    await createStyleElement(payload)
    ElMessage.success(t('styleElement.createSuccess'))
    emit('update:modelValue', false)
    emit('created')
  } catch (e: any) {
    ElMessage.error(e?.message || t('styleElement.createFailed'))
  } finally {
    submitting.value = false
  }
}

async function loadLayers() {
  try {
    const res = await listLayers()
    layerOptions.value = res.layers
  } catch {
    // 静默失败
  }
}

// ---------- 生命周期 ----------
onMounted(() => {
  loadLayers()
})
</script>

<style scoped>
.full-width {
  width: 100%;
}

.form-hint {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  margin-left: 8px;
}
</style>
