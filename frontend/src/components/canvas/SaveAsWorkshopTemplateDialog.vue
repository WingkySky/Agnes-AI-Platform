<!--
  SaveAsWorkshopTemplateDialog.vue
  将当前画布保存为创意工坊模板（PipelineTemplate）
  - 填写模板名称、描述、分类、是否公开
  - 自动分析画布流程，将节点转换为 steps_config
-->
<template>
  <el-dialog
    :model-value="visible"
    :title="t('canvas.saveAsWorkshopTemplate')"
    width="520px"
    :append-to-body="true"
    @close="handleClose"
  >
    <div class="workshop-template-form">
      <div class="form-item">
        <label>{{ t('workshop.templateName') }}</label>
        <el-input
          v-model="form.name"
          :placeholder="t('workshop.templateNamePlaceholder')"
          maxlength="200"
          show-word-limit
        />
      </div>
      <div class="form-item">
        <label>{{ t('workshop.templateDescription') }}</label>
        <el-input
          v-model="form.description"
          type="textarea"
          :placeholder="t('workshop.templateDescriptionPlaceholder')"
          :rows="3"
          maxlength="1000"
          show-word-limit
        />
      </div>
      <div class="form-item">
        <label>{{ t('workshop.templateCategory') }}</label>
        <el-select v-model="form.category" :placeholder="t('workshop.templateCategoryPlaceholder')">
          <el-option label="漫剧" value="drama" />
          <el-option label="广告" value="ad" />
          <el-option label="教育" value="education" />
          <el-option label="艺术" value="art" />
        </el-select>
      </div>
      <div class="form-item">
        <label>{{ t('workshop.templateTags') }}</label>
        <el-select
          v-model="form.tags"
          multiple
          filterable
          allow-create
          :placeholder="t('workshop.templateTagsPlaceholder')"
        >
          <el-option label="漫剧" value="漫剧" />
          <el-option label="广告" value="广告" />
          <el-option label="教育" value="教育" />
          <el-option label="二次元" value="二次元" />
          <el-option label="写实" value="写实" />
        </el-select>
      </div>
      <div class="form-item">
        <el-checkbox v-model="form.is_public">{{ t('workshop.templateIsPublic') }}</el-checkbox>
      </div>

      <!-- 步骤预览 -->
      <div class="form-item" v-if="previewSteps.length > 0">
        <label>将保存为以下步骤（共 {{ previewSteps.length }} 步）</label>
        <div class="step-preview-list">
          <div v-for="(step, idx) in previewSteps" :key="idx" class="step-preview-item">
            <span class="step-idx">{{ idx + 1 }}</span>
            <span class="step-type">{{ step.type }}</span>
            <span class="step-name">{{ step.name }}</span>
            <span class="step-deps" v-if="step.depends_on && step.depends_on.length > 0">依赖: {{ step.depends_on.length }} 个上游步骤</span>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleClose">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" :loading="loading" @click="handleSave">{{ t('common.save') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useI18n } from '@/i18n'
import { ElMessage } from 'element-plus'
import { createTemplate } from '@/api/pipeline'
import { useCanvasStore } from '@/stores/canvas'
import { analyzeFlow, analyzeExecutionOrder } from '@/lib/canvas-flow-analyzer'
import type { CanvasPanel, CanvasConnection } from '@/stores/canvas'

const { t } = useI18n()
const store = useCanvasStore()

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['close', 'saved'])

const loading = ref(false)

// 步骤预览（实时计算）
const previewSteps = computed(() => {
  try {
    return convertPanelsToSteps(store.panels, store.connections)
  } catch {
    return []
  }
})

const form = reactive({
  name: '',
  description: '',
  category: 'drama',
  tags: [] as string[],
  is_public: false,
})

// 节点类型到步骤类型的映射
const NODE_TYPE_TO_STEP_TYPE: Record<string, string> = {
  text: 'llm_generate',
  image: 'image_gen',
  video: 'video_gen',
  audio: 'audio_gen',
  config: 'composite',
}

// 将画布节点转换为 steps_config
function convertPanelsToSteps(panels: CanvasPanel[], connections: CanvasConnection[]): Record<string, any>[] {
  // 分析执行顺序
  const executionOrder = analyzeExecutionOrder(panels, connections)
  const steps: Record<string, any>[] = []

  // 为每个节点创建一个步骤
  for (let i = 0; i < executionOrder.length; i++) {
    const panelId = executionOrder[i]
    const panel = panels.find(p => p.id === panelId)
    if (!panel) continue

    // 找到该节点的所有上游节点（incoming 连线）
    const dependsOn = connections
      .filter(c => c.target_panel_id === panelId)
      .map(c => {
        const sourcePanel = panels.find(p => p.id === c.source_panel_id)
        return sourcePanel ? `step_${executionOrder.indexOf(c.source_panel_id)}` : null
      })
      .filter(Boolean) as string[]

    const stepType = NODE_TYPE_TO_STEP_TYPE[panel.type || 'text'] || 'llm_generate'

    const step: Record<string, any> = {
      key: `step_${i}`,
      name: panel.name || `${panel.type || 'text'} 步骤`,
      type: stepType,
      depends_on: dependsOn,
      config: buildStepConfig(panel, stepType),
      max_retries: 2,
      timeout: 300,
    }

    steps.push(step)
  }

  return steps
}

// 根据节点内容构建步骤配置
function buildStepConfig(panel: CanvasPanel, stepType: string): Record<string, any> {
  const content = panel.content || {}
  const config: Record<string, any> = {}
  const nodeType = panel.type || 'text'

  // 通用字段：提示词（从 content.content 或 content.prompt 读取）
  const prompt = (content as any).prompt || (content as any).content || ''
  config.prompt = prompt

  if (stepType === 'llm_generate') {
    config.model = (content as any).model || 'agnes-2.0-flash'
    config.temperature = (content as any).temperature || 0.8
    config.max_tokens = (content as any).max_tokens || 2048
  } else if (stepType === 'image_gen') {
    config.model = (content as any).model || 'agnes-2.0-flash'
    config.size = (content as any).size || '1024x1024'
    config.style = (content as any).style || 'photorealistic'
  } else if (stepType === 'video_gen') {
    config.model = (content as any).model || 'agnes-video-1.0'
    config.seconds = (content as any).seconds || 5
    config.aspect_ratio = (content as any).aspect_ratio || '16:9'
  } else if (stepType === 'audio_gen') {
    config.model = (content as any).model || 'agnes-audio-1.0'
    config.duration = (content as any).duration || 10
  } else if (stepType === 'composite') {
    // 合成节点：读取合成配置
    config.output_format = (content as any).output_format || 'mp4'
    config.quality = (content as any).quality || 'high'
  }

  return config
}

// 生成唯一的模板 key
function generateTemplateKey(name: string): string {
  const base = name
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]/g, '_')
    .replace(/_+/g, '_')
    .slice(0, 50)
  return `canvas_${base}_${Date.now()}`
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning(t('workshop.templateNameRequired'))
    return
  }

  if (store.panels.length === 0) {
    ElMessage.warning(t('canvas.templates.emptyCanvas'))
    return
  }

  loading.value = true
  try {
    // 转换画布节点为 steps_config
    const stepsConfig = convertPanelsToSteps(store.panels, store.connections)

    // 构建 inputs_config（从第一个步骤的 config 中提取）
    const inputsConfig: Record<string, any>[] = []
    if (stepsConfig.length > 0) {
      const firstStepConfig = stepsConfig[0].config || {}
      if (firstStepConfig.prompt) {
        inputsConfig.push({
          key: 'prompt',
          name: '提示词',
          type: 'text',
          required: true,
          default: firstStepConfig.prompt,
        })
      }
    }

    // 创建模板
    const templateData = {
      key: generateTemplateKey(form.name),
      name: form.name.trim(),
      description: form.description || undefined,
      category: form.category,
      inputs_config: inputsConfig,
      steps_config: stepsConfig,
      tags: form.tags.length > 0 ? form.tags : undefined,
      is_public: form.is_public,
    }

    const result = await createTemplate(templateData as any)
    ElMessage.success(t('workshop.templateCreated'))
    emit('saved', result)
    handleClose()
  } catch (err: any) {
    console.error('[canvas] save as workshop template failed:', err)
    ElMessage.error(`${t('workshop.templateCreateFailed')}: ${err.message || err}`)
  } finally {
    loading.value = false
  }
}

function handleClose() {
  emit('close')
}
</script>

<style scoped>
.workshop-template-form {
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

.form-item :deep(.el-select) {
  width: 100%;
}

.step-preview-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 200px;
  overflow-y: auto;
  padding: 8px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.step-preview-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--el-bg-color);
  border-radius: 4px;
  font-size: 12px;
}

.step-idx {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  background: var(--el-color-primary);
  color: #fff;
  border-radius: 50%;
  font-weight: bold;
  font-size: 11px;
  flex-shrink: 0;
}

.step-type {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.step-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-deps {
  color: var(--el-text-color-placeholder);
  font-size: 11px;
  flex-shrink: 0;
}
</style>
