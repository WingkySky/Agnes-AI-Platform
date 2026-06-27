<!-- =====================================================
     模板编辑器 - TemplateEditorView
     - 创建/编辑自定义流水线模板
     ===================================================== -->

<template>
  <div class="template-editor">
    <div class="editor-header">
      <el-page-header @back="goBack">
        <template #content>
          <span class="header-title">
            {{ isEdit ? t('templateEditor.editTitle') : t('templateEditor.createTitle') }}
          </span>
        </template>
        <!-- 编辑模式下提供导出当前模板入口 -->
        <template #extra>
          <el-button
            v-if="isEdit"
            link
            type="primary"
            size="small"
            @click="openExportCurrent">
            <el-icon><Download /></el-icon>
            {{ t('workshop.importExport.exportThis') }}
          </el-button>
        </template>
      </el-page-header>
    </div>

    <div v-loading="loading" class="editor-body">
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="120px"
        class="editor-form"
      >
        <!-- 模板名称 -->
        <el-form-item :label="t('templateEditor.name')" prop="name">
          <el-input v-model="form.name" :placeholder="t('templateEditor.namePlaceholder')" />
        </el-form-item>

        <!-- 模板 Key -->
        <el-form-item :label="t('templateEditor.key')" prop="key">
          <el-input
            v-model="form.key"
            :placeholder="t('templateEditor.keyPlaceholder')"
            :disabled="isEdit"
          />
          <div class="form-hint">{{ t('templateEditor.keyHint') }}</div>
        </el-form-item>

        <!-- 分类 -->
        <el-form-item :label="t('templateEditor.category')" prop="category">
          <el-select v-model="form.category" :placeholder="t('templateEditor.categoryPlaceholder')">
            <el-option
              v-for="cat in categoryOptions"
              :key="cat.value"
              :label="cat.label"
              :value="cat.value"
            />
          </el-select>
        </el-form-item>

        <!-- 描述 -->
        <el-form-item :label="t('templateEditor.description')" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="2"
            :placeholder="t('templateEditor.descriptionPlaceholder')"
          />
        </el-form-item>

        <!-- 缩略图 URL -->
        <el-form-item :label="t('templateEditor.thumbnailUrl')">
          <el-input v-model="form.thumbnail_url" :placeholder="t('templateEditor.thumbnailUrlPlaceholder')" />
          <div v-if="form.thumbnail_url" class="thumbnail-preview">
            <img :src="form.thumbnail_url" alt="缩略图预览" @error="onThumbError" />
          </div>
        </el-form-item>

        <!-- Tags -->
        <el-form-item :label="t('templateEditor.tags')">
          <el-select
            v-model="form.tags"
            multiple
            filterable
            allow-create
            :placeholder="t('templateEditor.tagsPlaceholder')"
          />
        </el-form-item>

        <!-- 公开/私有 -->
        <el-form-item :label="t('templateEditor.visibility')">
          <el-switch
            v-model="form.is_public"
            :active-text="t('templateEditor.public')"
            :inactive-text="t('templateEditor.private')"
          />
        </el-form-item>

        <!-- inputs_config -->
        <el-form-item :label="t('templateEditor.inputsConfig')" prop="inputs_config">
          <el-input
            v-model="inputsConfigText"
            type="textarea"
            :rows="8"
            :placeholder="inputsConfigPlaceholder"
          />
          <div class="form-hint">{{ t('templateEditor.inputsConfigHint') }}</div>
        </el-form-item>

        <!-- steps_config -->
        <el-form-item :label="t('templateEditor.stepsConfig')" prop="steps_config">
          <el-input
            v-model="stepsConfigText"
            type="textarea"
            :rows="12"
            :placeholder="stepsConfigPlaceholder"
          />
          <div class="form-hint">{{ t('templateEditor.stepsConfigHint') }}</div>
        </el-form-item>

        <!-- 操作按钮 -->
        <el-form-item>
          <el-button type="primary" @click="handleSave" :loading="saving">
            {{ t('common.save') }}
          </el-button>
          <el-button @click="goBack">{{ t('common.cancel') }}</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 模板导入/导出对话框（编辑模式下用于导出当前模板） -->
    <TemplateImportExportDialog
      v-model="ioDialogVisible"
      :preset-template-ids="presetExportIds"
      :initial-tab="ioDialogTab"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import {
  createTemplate,
  updateTemplate,
  getPipelineTemplateDetail,
} from '@/api/pipeline'
import type { FormInstance, FormRules } from 'element-plus'
import TemplateImportExportDialog from '@/components/pipeline/TemplateImportExportDialog.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

// 是否编辑模式
const templateId = computed(() => (route.params.id as string) || '')
const isEdit = computed(() => !!templateId.value)

const loading = ref(false)
const saving = ref(false)
const formRef = ref<FormInstance>()

// 模板导入/导出对话框状态
const ioDialogVisible = ref(false)
const ioDialogTab = ref<'export' | 'import'>('export')
const presetExportIds = ref<number[]>([])

function openExportCurrent() {
  if (!templateId.value) return
  presetExportIds.value = [Number(templateId.value)]
  ioDialogTab.value = 'export'
  ioDialogVisible.value = true
}

// 分类选项
const categoryOptions = [
  { value: 'comic', label: t('workshop.category.comic') },
  { value: 'commercial', label: t('workshop.category.commercial') },
  { value: 'education', label: t('workshop.category.education') },
  { value: 'entertainment', label: t('workshop.category.entertainment') },
]

// JSON 文本区域（独立字符串，避免双向绑定 JSON 对象）
const inputsConfigText = ref('[\n  {\n    "key": "theme",\n    "label": "主题",\n    "type": "text",\n    "required": true,\n    "placeholder": "请输入主题"\n  }\n]')
const stepsConfigText = ref('[\n  {\n    "key": "my_step",\n    "name": "我的步骤",\n    "type": "tts",\n    "config": {}\n  }\n]')

const inputsConfigPlaceholder = 'JSON 数组，每个元素为 {key, label, type, required, placeholder, default}'
const stepsConfigPlaceholder = 'JSON 数组，每个元素为 {key, name, type, config, depends_on}'

const form = reactive({
  key: '',
  name: '',
  description: '',
  category: 'comic',
  thumbnail_url: '',
  tags: [] as string[],
  is_public: false,
  inputs_config: [] as Record<string, any>[],
  steps_config: [] as Record<string, any>[],
})

const rules: FormRules = {
  name: [{ required: true, message: '请输入模板名称', trigger: 'blur' }],
  key: [
    { required: true, message: '请输入模板 Key', trigger: 'blur' },
    { pattern: /^[a-z][a-z0-9_]*$/, message: 'Key 只能包含小写字母、数字和下划线，以字母开头', trigger: 'blur' },
  ],
  category: [{ required: true, message: '请选择分类', trigger: 'change' }],
  inputs_config: [{ required: true, message: '请输入输入配置', trigger: 'blur' }],
  steps_config: [{ required: true, message: '请输入步骤配置', trigger: 'blur' }],
}

function goBack() {
  router.push('/workshop')
}

function onThumbError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.display = 'none'
}

onMounted(async () => {
  if (!isEdit.value) return

  loading.value = true
  try {
    const tpl = await getPipelineTemplateDetail(Number(templateId.value))
    form.key = tpl.key
    form.name = tpl.name
    form.description = tpl.description || ''
    form.category = tpl.category || 'comic'
    form.thumbnail_url = tpl.thumbnail_url || ''
    form.tags = tpl.tags || []
    form.is_public = tpl.is_public || false
    form.inputs_config = tpl.inputs_config || []
    form.steps_config = tpl.steps_config || []
    inputsConfigText.value = JSON.stringify(tpl.inputs_config, null, 2)
    stepsConfigText.value = JSON.stringify(tpl.steps_config, null, 2)
    // 内置模板不可编辑
    if (tpl.is_builtin) {
      ElMessage.warning('内置模板不可编辑')
      router.push('/workshop')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载模板失败')
    router.push('/workshop')
  } finally {
    loading.value = false
  }
})

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  // 解析 JSON
  try {
    form.inputs_config = JSON.parse(inputsConfigText.value)
  } catch {
    ElMessage.error('inputs_config JSON 格式不正确')
    return
  }
  try {
    form.steps_config = JSON.parse(stepsConfigText.value)
  } catch {
    ElMessage.error('steps_config JSON 格式不正确')
    return
  }

  saving.value = true
  try {
    if (isEdit.value) {
      await updateTemplate(Number(templateId.value), {
        name: form.name,
        description: form.description,
        category: form.category,
        thumbnail_url: form.thumbnail_url || undefined,
        inputs_config: form.inputs_config,
        steps_config: form.steps_config,
        tags: form.tags.length > 0 ? form.tags : undefined,
        is_public: form.is_public,
      })
      ElMessage.success('模板已更新')
    } else {
      await createTemplate({
        key: form.key,
        name: form.name,
        description: form.description || undefined,
        category: form.category,
        thumbnail_url: form.thumbnail_url || undefined,
        inputs_config: form.inputs_config,
        steps_config: form.steps_config,
        tags: form.tags.length > 0 ? form.tags : undefined,
        is_public: form.is_public,
      })
      ElMessage.success('模板已创建')
    }
    router.push('/workshop')
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.template-editor {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;

  .editor-header {
    margin-bottom: 24px;
    .header-title {
      font-size: 18px;
      font-weight: 600;
    }
  }

  .editor-body {
    background: var(--el-bg-color);
    border-radius: 8px;
    padding: 24px;
  }

  .editor-form {
    max-width: 680px;
  }

  .form-hint {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    margin-top: 4px;
  }

  .thumbnail-preview {
    margin-top: 8px;
    max-width: 300px;
    img {
      width: 100%;
      height: auto;
      border-radius: 6px;
      border: 1px solid var(--el-border-color);
      object-fit: cover;
    }
  }
}
</style>
