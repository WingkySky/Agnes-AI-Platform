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
          <el-option :label="t('workshop.catDrama')" value="drama" />
          <el-option :label="t('workshop.catAd')" value="ad" />
          <el-option :label="t('workshop.catEducation')" value="education" />
          <el-option :label="t('workshop.catArt')" value="art" />
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
          <el-option :label="t('workshop.styleDrama')" value="drama" />
          <el-option :label="t('workshop.styleAd')" value="ad" />
          <el-option :label="t('workshop.styleEducation')" value="education" />
          <el-option :label="t('workshop.styleComic')" value="comic" />
          <el-option :label="t('workshop.styleRealistic')" value="realistic" />
        </el-select>
      </div>
      <div class="form-item">
        <el-checkbox v-model="form.is_public">{{ t('workshop.templateIsPublic') }}</el-checkbox>
      </div>

      <!-- 步骤预览 -->
      <div class="form-item" v-if="previewSteps.length > 0">
        <label>{{ t('workshop.stepPreview').replace('{n}', previewSteps.length) }}</label>
        <div class="step-preview-list">
          <div v-for="(step, idx) in previewSteps" :key="idx" class="step-preview-item">
            <span class="step-idx">{{ idx + 1 }}</span>
            <span class="step-type">{{ step.type }}</span>
            <span class="step-name">{{ step.name }}</span>
            <span class="step-deps" v-if="step.depends_on && step.depends_on.length > 0">{{ t('workshop.dependsOn').replace('{n}', step.depends_on.length) }}</span>
          </div>
        </div>
      </div>

      <!-- 校验错误列表 -->
      <div class="form-item" v-if="validationErrors.length > 0">
        <label style="color: var(--el-color-danger)">{{ t('workshop.validationFailed').replace('{n}', validationErrors.length) }}</label>
        <div class="validation-errors">
          <div v-for="(err, idx) in validationErrors" :key="idx" class="validation-error-item">
            <el-icon><WarningFilled /></el-icon>
            <span class="err-step">{{ err.step_key || t('workshop.globalFallback') }}</span>
            <span class="err-field">[{{ err.field }}]</span>
            <span class="err-reason">{{ err.reason }}</span>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleClose">{{ t('common.cancel') }}</el-button>
      <el-button :loading="loading" @click="handleExportJson">
        <el-icon><Download /></el-icon>
        {{ t('canvas.templates.exportJson') }}
      </el-button>
      <el-button type="primary" :loading="loading" @click="handleSave">{{ t('common.save') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { useI18n, t } from '@/i18n'
import { ElMessage } from 'element-plus'
import { WarningFilled, Download } from '@element-plus/icons-vue'
import { createTemplate, validateTemplate } from '@/api/pipeline'
import { useCanvasStore } from '@/stores/canvas'
import { analyzeFlow, analyzeExecutionOrder } from '@/lib/canvas-flow-analyzer'
import { WORKSHOP_STEP_PRESETS, getPresetByType } from '@/config/workshop-step-presets'
import type { WorkshopStepType } from '@/config/workshop-step-presets'
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
// 校验错误列表（保存前调 validate 接口填充）
const validationErrors = ref<{ step_key: string | null; field: string; reason: string }[]>([])

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

// =====================================================
// 节点类型 → 后端 step_type 映射（修正版，spec 5.3.1）
// =====================================================
// 旧代码用的 image_gen/video_gen/audio_gen/composite 在后端注册表里都不存在，
// 导致画布保存的工坊模板运行即报"未知步骤类型"。
// 修正为后端权威 step_type 清单：
//   llm_generate / image_batch / video_batch / tts_generate / ffmpeg_composite
// 同时支持新增的 tts / subtitle / compose 三种画布节点类型。
const NODE_TYPE_TO_STEP_TYPE: Record<string, WorkshopStepType> = {
  text: 'llm_generate',
  image: 'image_batch',
  video: 'video_batch',
  tts: 'tts_generate',          // 新节点类型
  subtitle: 'llm_generate',     // 字幕用 llm_generate 产出 SRT 文本
  compose: 'ffmpeg_composite',  // 新节点类型
  // 兼容旧节点类型
  audio: 'tts_generate',
  config: 'ffmpeg_composite',
}

// 后端 step_type → 期望的上游 step_type（用于自动填充 from_step）
const STEP_UPSTREAM_MAP: Record<WorkshopStepType, WorkshopStepType[]> = {
  llm_generate: [],
  image_batch: ['llm_generate'],
  video_batch: ['image_batch'],
  tts_generate: ['llm_generate'],
  ffmpeg_composite: ['video_batch'],
  // 调色：上游可以是视频生成或成片合成
  color_grade: ['video_batch', 'ffmpeg_composite'],
  // 视频剪辑：上游可以是视频生成、成片合成或调色
  video_edit: ['video_batch', 'ffmpeg_composite', 'color_grade'],
}

// 字幕步骤(llm_generate 但 presetKey='subtitle') 的上游是 text/llm_generate
// 通过节点 type='subtitle' 单独判断，在 fillFromStep 里处理

// 占位符 → i18n 标签映射（inputs_config 自动生成用，spec 5.3.4）
// 直接使用 t()，回退到 field 名

/**
 * 将画布节点转换为 steps_config（修正版，spec 5.3）
 *
 * 修复点：
 *   1. NODE_TYPE_TO_STEP_TYPE 映射全错 → 修正为后端权威清单
 *   2. buildStepConfig 字段名与执行器不符 → 用预设 defaultConfig 作基础
 *   3. depends_on 推断 + from_step 引用补全
 *   4. inputs_config 只生成 prompt → 扫描 {{xxx}} 占位符自动生成
 */
function convertPanelsToSteps(
  panels: CanvasPanel[],
  connections: CanvasConnection[],
): Record<string, any>[] {
  // 分析执行顺序
  const executionOrder = analyzeExecutionOrder(panels, connections)
  const steps: Record<string, any>[] = []

  // 为每个节点创建一个步骤
  for (let i = 0; i < executionOrder.length; i++) {
    const panelId = executionOrder[i]
    const panel = panels.find((p) => p.id === panelId)
    if (!panel) continue

    const nodeType = (panel.type || 'text').toLowerCase()
    const stepType = NODE_TYPE_TO_STEP_TYPE[nodeType] || 'llm_generate'
    const preset = getPresetByType(stepType)

    // 找到该节点的所有上游节点（incoming 连线）
    const dependsOn = connections
      .filter((c) => c.target_panel_id === panelId)
      .map((c) => {
        const sourcePanel = panels.find((p) => p.id === c.source_panel_id)
        return sourcePanel ? `step_${executionOrder.indexOf(c.source_panel_id)}` : null
      })
      .filter(Boolean) as string[]

    // 用预设的 defaultConfig 作为基础（保证字段名与执行器一致）
    const baseConfig = preset ? { ...preset.defaultConfig } : {}
    const stepConfig = buildStepConfig(panel, stepType, nodeType, baseConfig)

    const step: Record<string, any> = {
      key: `step_${i}`,
      name: panel.name || t('workshop.nodeTypeStep', { type: nodeType }),
      type: stepType,
      depends_on: dependsOn,
      config: stepConfig,
      max_retries: 2,
      timeout: 300,
    }

    steps.push(step)
  }

  // 第二遍：填充 from_step / audio_from_step / subtitle_from_step
  fillFromStepReferences(steps)

  return steps
}

/**
 * 根据节点内容构建步骤配置（spec 5.3.2）
 *
 * 以预设 defaultConfig 为基础（保证字段名正确），再用节点 content 覆盖可读字段。
 * from_step 等引用字段在 fillFromStepReferences 统一填充，这里置 null。
 */
function buildStepConfig(
  panel: CanvasPanel,
  stepType: WorkshopStepType,
  nodeType: string,
  baseConfig: Record<string, any>,
): Record<string, any> {
  const content = (panel.content || {}) as Record<string, any>
  const config: Record<string, any> = { ...baseConfig }

  // from_step 等引用字段先置 null，由 fillFromStepReferences 统一填充
  config.from_step = null
  if ('audio_from_step' in config) config.audio_from_step = null
  if ('subtitle_from_step' in config) config.subtitle_from_step = null

  // 通用：提示词模板（llm_generate 类型，执行器期望 prompt_template）
  if (stepType === 'llm_generate') {
    const prompt = content.prompt || content.content || ''
    config.prompt_template = prompt || getSubtitleDefaultPrompt(nodeType)
  }

  // 各类型从节点 content 覆盖可读字段（用户在画布里设过的值）
  if (stepType === 'llm_generate') {
    if (content.model) config.model = content.model
    if (content.temperature !== undefined) config.temperature = content.temperature
    if (content.max_tokens) config.max_tokens = content.max_tokens
    if (content.output_format) config.output_format = content.output_format
  } else if (stepType === 'image_batch') {
    // image_batch 用 prompt_field 而非 prompt 字面量
    if (content.size) config.size = content.size
    if (content.batch_size) config.batch_size = content.batch_size
    if (content.model) config.model = content.model
    // prompt_field 默认 'prompt'（从上游 llm_generate 的 JSON 输出取 prompt 字段）
    config.prompt_field = content.prompt_field || 'prompt'
    // source 默认 parsed_result（从上游步骤输出中提取）
    // items_path 由后端自动推断，前端无需指定
    if (content.source) config.source = content.source
  } else if (stepType === 'video_batch') {
    if (content.model) config.model = content.model
    if (content.seconds) config.seconds = content.seconds
    if (content.aspect_ratio) config.aspect_ratio = content.aspect_ratio
    // items_path 由后端自动推断，前端无需指定
    if (content.source) config.source = content.source
  } else if (stepType === 'tts_generate') {
    if (content.voice) config.voice = content.voice
    if (content.speed !== undefined) config.speed = content.speed
    if (content.provider) config.provider = content.provider
  } else if (stepType === 'ffmpeg_composite') {
    if (content.with_subtitle !== undefined) config.with_subtitle = content.with_subtitle
  }

  return config
}

/**
 * 字幕节点（type='subtitle'）若用户未填 prompt，给默认 SRT 提示词
 */
function getSubtitleDefaultPrompt(nodeType: string): string {
  if (nodeType === 'subtitle') {
    return t('workshop.subtitleDefaultPrompt') || '根据上游剧本内容生成 SRT 格式字幕，每条字幕不超过 20 字'
  }
  return ''
}

/**
 * 填充 from_step / audio_from_step / subtitle_from_step（spec 5.3.3）
 *
 * 规则：按步骤顺序找最近的、位置在当前步骤之前的、对应类型的上游 step.key。
 * 若引用的 key 不在 depends_on 中，自动追加。
 */
function fillFromStepReferences(steps: Record<string, any>[]): void {
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i]
    const stepType = step.type as WorkshopStepType
    const config = step.config || {}

    // 普通 from_step（image_batch/video_batch/tts_generate 都有）
    if ('from_step' in config) {
      const upstreamTypes = STEP_UPSTREAM_MAP[stepType] || []
      if (upstreamTypes.length > 0) {
        const fromKey = findLatestUpstreamStep(steps, i, upstreamTypes)
        config.from_step = fromKey
        if (fromKey && !step.depends_on.includes(fromKey)) {
          step.depends_on.push(fromKey)
        }
      }
    }

    // 字幕节点(subtitle)的 from_step：找最近的 llm_generate
    // （已在上面的 STEP_UPSTREAM_MAP 处理，因为 type=llm_generate 上游为空，
    //  这里单独处理 subtitle 节点的 from_step）
    // 注意：subtitle 节点转成 step.type='llm_generate'，
    // 但它仍需 from_step 指向上游文本。通过节点 panel.type='subtitle' 标记。
    // 这里 steps 已经丢失原节点类型，所以 subtitle 的 from_step 依赖 depends_on
    // 已在 convertPanelsToSteps 第一遍按画布连线推断好了。

    // ffmpeg_composite 的 audio_from_step：找最近的 tts_generate
    if (stepType === 'ffmpeg_composite' && 'audio_from_step' in config) {
      const audioKey = findLatestUpstreamStep(steps, i, ['tts_generate'])
      config.audio_from_step = audioKey
      if (audioKey && !step.depends_on.includes(audioKey)) {
        step.depends_on.push(audioKey)
      }
    }

    // ffmpeg_composite 的 subtitle_from_step：找最近的 subtitle（即产出 SRT 的 llm_generate）
    // 注意：subtitle 节点转成 type='llm_generate'，无法在 steps 里区分。
    // 简化处理：留给用户在工坊编辑器里手动指定（高级区有字段）。
    // 这里不自动填充 subtitle_from_step，保持 null。
  }
}

/**
 * 在 steps 中往前找最近的、类型匹配的上游 step.key
 */
function findLatestUpstreamStep(
  steps: Record<string, any>[],
  currentIndex: number,
  upstreamTypes: WorkshopStepType[],
): string | null {
  for (let j = currentIndex - 1; j >= 0; j--) {
    if (upstreamTypes.includes(steps[j].type as WorkshopStepType)) {
      return steps[j].key
    }
  }
  return null
}

/**
 * 从所有 llm_generate 步骤的 prompt 模板提取 {{xxx}} 占位符，
 * 生成 inputs_config（spec 5.3.4）
 */
function buildInputsConfigFromSteps(steps: Record<string, any>[]): Record<string, any>[] {
  const placeholderSet = new Set<string>()
  const placeholderRegex = /\{\{\s*(\w+)\s*\}\}/g

  for (const step of steps) {
    if (step.type !== 'llm_generate') continue
    const prompt = step.config?.prompt || ''
    if (typeof prompt !== 'string') continue
    let match: RegExpExecArray | null
    while ((match = placeholderRegex.exec(prompt)) !== null) {
      placeholderSet.add(match[1])
    }
  }

  const inputsConfig: Record<string, any>[] = []
  for (const key of placeholderSet) {
    inputsConfig.push({
      key,
      label: t('workshop.placeholder.' + key) || key,
      type: 'text',
      required: true,
      default: '',
    })
  }

  // 若没有提取到任何占位符，给一个默认的 theme 输入（避免空 inputs_config）
  if (inputsConfig.length === 0) {
    inputsConfig.push({
      key: 'theme',
      label: t('workshop.placeholderTheme'),
      type: 'text',
      required: true,
      default: '',
    })
  }

  return inputsConfig
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

/**
 * 构建完整的模板数据（供保存到工坊 / 导出为 JSON 复用）
 */
function buildTemplateData() {
  const stepsConfig = convertPanelsToSteps(store.panels, store.connections)
  const inputsConfig = buildInputsConfigFromSteps(stepsConfig)

  return {
    key: generateTemplateKey(form.name),
    name: form.name.trim(),
    description: form.description || undefined,
    category: form.category,
    inputs_config: inputsConfig,
    steps_config: stepsConfig,
    tags: form.tags.length > 0 ? form.tags : undefined,
    is_public: form.is_public,
  }
}

/**
 * 保存到工坊（spec 5.3.5：保存前预校验）
 */
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
  validationErrors.value = []
  try {
    const templateData = buildTemplateData()

    // 保存前预校验（spec 5.3.5）
    const validateRes = await validateTemplate(templateData as any)
    if (!validateRes.is_valid) {
      validationErrors.value = validateRes.errors
      ElMessage.warning(
        `${t('canvas.templates.validateFailed') || '校验失败'}：${validateRes.errors.length} 处错误`,
      )
      return
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

/**
 * 导出为 JSON 文件（spec 5.4.6）
 *
 * 走同样的转换逻辑，但不调创建接口，
 * 而是把 {version, exported_at, templates:[...]} 打包下载。
 * 导出的文件可直接拖进工坊导入框，格式完全一致。
 */
async function handleExportJson() {
  if (!form.name.trim()) {
    ElMessage.warning(t('workshop.templateNameRequired'))
    return
  }
  if (store.panels.length === 0) {
    ElMessage.warning(t('canvas.templates.emptyCanvas'))
    return
  }

  loading.value = true
  validationErrors.value = []
  try {
    const templateData = buildTemplateData()

    // 导出前也做一次校验（避免导出坏文件）
    const validateRes = await validateTemplate(templateData as any)
    if (!validateRes.is_valid) {
      validationErrors.value = validateRes.errors
      ElMessage.warning(
        `${t('canvas.templates.validateFailed') || '校验失败'}：${validateRes.errors.length} 处错误`,
      )
      return
    }

    const exportPayload = {
      version: '1.0',
      exported_at: new Date().toISOString(),
      templates: [templateData],
      script_templates: [],
      style_presets: [],
    }

    const jsonStr = JSON.stringify(exportPayload, null, 2)
    const blob = new Blob([jsonStr], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `agnes-canvas-template-${Date.now()}.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)

    ElMessage.success(t('canvas.templates.exportJsonSuccess') || '已导出为 JSON 文件')
  } catch (err: any) {
    console.error('[canvas] export as json failed:', err)
    ElMessage.error(`${t('canvas.templates.exportJsonFailed') || '导出失败'}: ${err.message || err}`)
  } finally {
    loading.value = false
  }
}

function handleClose() {
  validationErrors.value = []
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

.validation-errors {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 200px;
  overflow-y: auto;
  padding: 8px;
  background: var(--el-color-danger-light-9);
  border-radius: 6px;
  border: 1px solid var(--el-color-danger-light-5);
}

.validation-error-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  background: var(--el-bg-color);
  border-radius: 4px;
  font-size: 12px;
  color: var(--el-color-danger);
}

.validation-error-item .el-icon {
  flex-shrink: 0;
}

.err-step {
  font-weight: 500;
  flex-shrink: 0;
}

.err-field {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
  font-family: monospace;
}

.err-reason {
  flex: 1;
  color: var(--el-text-color-regular);
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
