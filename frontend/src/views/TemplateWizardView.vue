<!--
  TemplateWizardView.vue
  场景化模板创建向导
  - 步骤1：选择场景（漫剧、广告、教育、二次元、写实）
  - 步骤2：填写输入参数（根据场景预设动态生成表单）
  - 步骤3：预览生成的步骤配置和预估积分
  - 步骤4：创建模板（跳转到编辑页或运行页）
-->
<template>
  <div class="template-wizard">
    <!-- 头部 -->
    <div class="wizard-header">
      <el-page-header @back="goBack">
        <template #content>
          <span class="header-title">{{ t('workshop.templateWizard.title') }}</span>
        </template>
      </el-page-header>
      <!-- 步骤进度条 -->
      <el-steps :active="currentStep" align-center class="wizard-steps">
        <el-step :title="t('workshop.templateWizard.stepSelect')" />
        <el-step :title="t('workshop.templateWizard.stepConfig')" />
        <el-step :title="t('workshop.templateWizard.stepCustomize')" />
        <el-step :title="t('workshop.templateWizard.stepPreview')" />
        <el-step :title="t('workshop.templateWizard.stepCreate')" />
      </el-steps>
    </div>

    <!-- 步骤内容 -->
    <div class="wizard-body">
      <!-- 步骤1：选择场景 -->
      <template v-if="currentStep === 0">
        <div class="step-content">
          <h3 class="step-title">{{ t('workshop.templateWizard.selectScenario') }}</h3>
          <p class="step-desc">{{ t('workshop.templateWizard.selectScenarioDesc') }}</p>
          <div class="scenario-grid">
            <div
              v-for="scenario in scenarios"
              :key="scenario.key"
              class="scenario-card"
              :class="{ active: selectedScenario?.key === scenario.key }"
              :style="{ '--scenario-color': scenario.color }"
              @click="selectScenario(scenario)"
            >
              <div class="scenario-icon">
                <el-icon :size="32"><component :is="scenarioIconMap[scenario.icon] || 'Document'" /></el-icon>
              </div>
              <div class="scenario-name">{{ scenarioI18n(scenario, 'name') }}</div>
              <div class="scenario-desc">{{ scenarioI18n(scenario, 'desc') }}</div>
            </div>
          </div>
        </div>
      </template>

      <!-- 步骤2：填写输入参数 -->
      <template v-if="currentStep === 1">
        <div class="step-content">
          <h3 class="step-title">{{ t('workshop.templateWizard.configInputs') }}</h3>
          <p class="step-desc">{{ t('workshop.templateWizard.configInputsDesc') }}</p>
          <el-form
            ref="inputsFormRef"
            :model="inputsForm"
            label-width="120px"
            class="inputs-form"
          >
            <el-form-item
              v-for="input in selectedScenario?.inputs_config"
              :key="input.key"
              :label="inputI18n(input, 'label')"
              :required="input.required"
            >
              <!-- text 类型 -->
              <el-input
                v-if="input.type === 'text'"
                v-model="inputsForm[input.key]"
                :placeholder="inputI18n(input, 'placeholder')"
                :maxlength="input.maxlength || 200"
                show-word-limit
              />
              <!-- number 类型 -->
              <el-input-number
                v-if="input.type === 'number'"
                v-model="inputsForm[input.key]"
                :min="input.min || 0"
                :max="input.max || 100"
                :step="input.step || 1"
              />
              <!-- style_select 类型 -->
              <el-select
                v-if="input.type === 'style_select'"
                v-model="inputsForm[input.key]"
                :placeholder="inputI18n(input, 'placeholder')"
              >
                <el-option
                  v-for="opt in input.options"
                  :key="opt"
                  :label="optionI18n(input, opt)"
                  :value="opt"
                />
              </el-select>
              <!-- boolean 类型 -->
              <el-switch
                v-if="input.type === 'boolean'"
                v-model="inputsForm[input.key]"
              />
            </el-form-item>
          </el-form>
        </div>
      </template>

  <!-- 步骤3：配置步骤 -->
  <template v-if="currentStep === 2">
    <div class="step-content">
      <h3 class="step-title">{{ t('workshop.templateWizard.configSteps') }}</h3>
      <p class="step-desc">{{ t('workshop.templateWizard.configStepsDesc') }}</p>
      <!-- 步骤配置列表 -->
      <div class="steps-config-list">
        <div
          v-for="(step, idx) in editableSteps"
          :key="idx"
          class="step-config-card"
          :class="{ expanded: expandedStepIndex === idx }"
        >
          <!-- 步骤卡片头部 -->
          <div class="step-card-header" @click="toggleStepExpand(idx)">
            <div class="step-card-left">
              <span class="step-idx">{{ idx + 1 }}</span>
              <span class="step-name">{{ stepI18n(step) }}</span>
              <el-tag size="small" :type="stepTypeColor(step.type)">{{ step.type }}</el-tag>
            </div>
            <el-icon :class="{ 'is-rotate': expandedStepIndex === idx }">
              <ArrowDown />
            </el-icon>
          </div>
          <!-- 步骤卡片内容（可展开） -->
          <div v-if="expandedStepIndex === idx" class="step-card-body">
            <!-- 提示词编辑（llm_generate 类型） -->
            <div v-if="step.type === 'llm_generate'" class="config-field">
              <label class="field-label">{{ t('workshop.templateWizard.promptTemplate') }}</label>
              <el-input
                v-model="step.config.prompt_template"
                type="textarea"
                :rows="6"
                :placeholder="t('workshop.templateWizard.promptPlaceholder')"
              />
              <div class="field-hint">{{ t('workshop.templateWizard.promptHint') }}</div>
            </div>
            <!-- 模型选择 -->
            <div class="config-field">
              <label class="field-label">{{ t('workshop.templateWizard.model') }}</label>
              <el-select v-model="step.config.model" class="config-select" :loading="modelsLoading">
                <el-option
                  v-for="model in getModelsForStep(step.type)"
                  :key="model.model_id || model.id_field"
                  :label="model.name || model.model_id"
                  :value="model.model_id || model.id_field"
                />
              </el-select>
            </div>
            <!-- 温度调节（llm_generate 类型） -->
            <div v-if="step.type === 'llm_generate'" class="config-field">
              <label class="field-label">{{ t('workshop.templateWizard.temperature') }}: {{ step.config.temperature }}</label>
              <el-slider v-model="step.config.temperature" :min="0" :max="1" :step="0.1" />
            </div>
            <!-- 图片尺寸（image_gen 类型） -->
            <div v-if="step.type === 'image_gen'" class="config-field">
              <label class="field-label">{{ t('workshop.templateWizard.imageSize') }}</label>
              <el-select v-model="step.config.size" class="config-select">
                <el-option label="1024x1024" value="1024x1024" />
                <el-option label="1024x1792" value="1024x1792" />
                <el-option label="1792x1024" value="1792x1024" />
              </el-select>
            </div>
            <!-- 视频时长（video_gen 类型） -->
            <div v-if="step.type === 'video_gen'" class="config-field">
              <label class="field-label">{{ t('workshop.templateWizard.videoSeconds') }}</label>
              <el-input-number v-model="step.config.seconds" :min="5" :max="180" :step="5" />
            </div>
            <!-- 视频宽高比（video_gen 类型） -->
            <div v-if="step.type === 'video_gen'" class="config-field">
              <label class="field-label">{{ t('workshop.templateWizard.videoRatio') }}</label>
              <el-select v-model="step.config.aspect_ratio" class="config-select">
                <el-option label="16:9" value="16:9" />
                <el-option label="9:16" value="9:16" />
                <el-option label="1:1" value="1:1" />
              </el-select>
            </div>
          </div>
        </div>
      </div>
    </div>
  </template>

  <!-- 步骤4：预览 -->
  <template v-if="currentStep === 3">
    <div class="step-content">
      <h3 class="step-title">{{ t('workshop.templateWizard.preview') }}</h3>
      <p class="step-desc">{{ t('workshop.templateWizard.previewDesc') }}</p>
      <!-- 步骤预览 -->
      <div class="preview-section">
        <h4>{{ t('workshop.templateWizard.stepsPreview') }}</h4>
        <div class="step-list">
          <div
            v-for="(step, idx) in previewSteps"
            :key="idx"
            class="step-item"
          >
            <span class="step-idx">{{ idx + 1 }}</span>
            <span class="step-name">{{ stepI18n(step) }}</span>
            <span class="step-type">{{ step.type }}</span>
          </div>
        </div>
      </div>
      <!-- 积分预览 -->
      <div class="preview-section">
        <h4>{{ t('workshop.templateWizard.creditsPreview') }}</h4>
        <div class="credits-preview">
          <span class="credits-num">{{ previewCredits }}</span>
          <span class="credits-label">{{ t('workshop.templateWizard.creditsUnit') }}</span>
        </div>
      </div>
      <!-- 时长预览 -->
      <div class="preview-section">
        <h4>{{ t('workshop.templateWizard.timePreview') }}</h4>
        <div class="time-preview">
          {{ previewTime }} {{ t('workshop.templateWizard.timeUnit') }}
        </div>
      </div>
    </div>
  </template>

      <!-- 步骤5：创建成功 -->
      <template v-if="currentStep === 4">
        <div class="step-content success-state">
          <el-icon :size="56" color="#67c23a"><Check /></el-icon>
          <h3 class="success-title">{{ t('workshop.templateWizard.createdTitle') }}</h3>
          <p class="success-desc">{{ t('workshop.templateWizard.createdDesc') }}</p>
          <div class="success-actions">
            <el-button type="primary" size="large" @click="runCreated">
              <el-icon><VideoPlay /></el-icon>
              {{ t('workshop.templateWizard.runNow') }}
            </el-button>
            <el-button size="large" @click="goToWorkshopAfterCreate">
              <el-icon><Menu /></el-icon>
              {{ t('workshop.templateWizard.backToWorkshop') }}
            </el-button>
          </div>
        </div>
      </template>
    </div>

    <!-- 底部操作栏 -->
    <div class="wizard-footer">
      <el-button v-if="currentStep > 0 && currentStep < 4" @click="prevStep">
        {{ t('common.prev') }}
      </el-button>
      <el-button
        v-if="currentStep < 3"
        type="primary"
        :disabled="currentStep === 0 && !selectedScenario"
        @click="nextStep"
      >
        {{ t('common.next') }}
      </el-button>
      <el-button
        v-if="currentStep === 3"
        type="primary"
        :loading="creating"
        @click="handleCreate"
      >
        {{ t('workshop.templateWizard.create') }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from '@/i18n'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading, Film, Promotion, School, Star, Check, VideoPlay, Menu, ArrowDown } from '@element-plus/icons-vue'
import { getTemplateScenarios, createTemplateFromScenario, getAvailableModels } from '@/api/pipeline'
import type { TemplateScenario } from '@/types'

const { t } = useI18n()
const router = useRouter()

// 当前步骤（0-3）
const currentStep = ref(0)
// 场景列表
const scenarios = ref<TemplateScenario[]>([])
// 选中的场景
const selectedScenario = ref<TemplateScenario | null>(null)

// 场景图标映射（后端 icon 名 → Element Plus 图标组件）
const scenarioIconMap: Record<string, any> = {
  film: Film,
  megaphone: Promotion,
  'graduation-cap': School,
  star: Star,
}
// 输入表单
const inputsForm = reactive<Record<string, any>>({})
// 预览数据
const previewSteps = ref<any[]>([])
const previewCredits = ref(0)
const previewTime = ref(0)
// 可编辑的步骤配置
const editableSteps = ref<any[]>([])
// 当前展开的步骤索引
const expandedStepIndex = ref(-1)
// 创建中
const creating = ref(false)
// 创建成功的模板 ID
const createdTemplateId = ref<number | null>(null)
// 可用模型列表
const availableModels = ref<any[]>([])
// 模型加载状态
const modelsLoading = ref(false)

// ---------- i18n 辅助函数 ----------
const i18nBase = 'workshop.templateWizard.scenarios'

/** 场景级别翻译（name, desc） */
function scenarioI18n(scenario: TemplateScenario, field: 'name' | 'desc'): string {
  const key = scenario.i18n_key || scenario.key
  const fullKey = `${i18nBase}.${key}.${field}`
  const translated = t(fullKey)
  // 如果翻译键不存在则 fallback 到后端原始值
  return translated === fullKey ? (scenario as any)[field === 'desc' ? 'description' : 'name'] : translated
}

/** 输入字段翻译（label, placeholder） */
function inputI18n(input: any, field: 'label' | 'placeholder'): string {
  if (!selectedScenario.value) return input[field] || ''
  const sKey = selectedScenario.value.i18n_key || selectedScenario.value.key
  const i18nSuffix = input[field + '_i18n'] || field
  const fullKey = `${i18nBase}.${sKey}.input_${input.key}_${i18nSuffix}`
  const translated = t(fullKey)
  // 尝试更短的 key 格式: scenarios.{key}.{label_i18n}
  const shortKey = `${i18nBase}.${sKey}.${input.label_i18n || input.placeholder_i18n || field}`
  const translated2 = t(shortKey)
  if (translated2 !== shortKey) return translated2
  return translated !== fullKey ? translated : (input[field] || '')
}

/** 选项翻译 */
function optionI18n(input: any, optValue: string): string {
  if (!selectedScenario.value) return optValue
  const sKey = selectedScenario.value.i18n_key || selectedScenario.value.key
  const prefix = input.options_i18n_prefix || ''
  const fullKey = prefix ? `${i18nBase}.${sKey}.${prefix}${optValue}` : ''
  if (fullKey) {
    const translated = t(fullKey)
    if (translated !== fullKey) return translated
  }
  return optValue
}

/** 步骤名称翻译 */
function stepI18n(step: any): string {
  if (!selectedScenario.value) return step.name || ''
  const sKey = selectedScenario.value.i18n_key || selectedScenario.value.key
  const nameKey = step.name_i18n || step.key
  const fullKey = `${i18nBase}.${sKey}.${nameKey}`
  const translated = t(fullKey)
  return translated !== fullKey ? translated : (step.name || '')
}

// 加载场景列表
async function loadScenarios() {
  try {
    const res = await getTemplateScenarios()
    scenarios.value = res.items || []
  } catch (err: any) {
    ElMessage.error(`${t('workshop.templateWizard.loadFailed')}: ${err.message || err}`)
  }
}

// 选择场景
function selectScenario(scenario: TemplateScenario) {
  selectedScenario.value = scenario
  // 初始化输入表单
  if (scenario.inputs_config) {
    for (const input of scenario.inputs_config) {
      if (inputsForm[input.key] === undefined) {
        inputsForm[input.key] = input.default ?? ''
      }
    }
  }
}

// 下一步
async function nextStep() {
  if (currentStep.value === 0 && !selectedScenario.value) {
    ElMessage.warning(t('workshop.templateWizard.pleaseSelectScenario'))
    return
  }
  if (currentStep.value === 1) {
    // 校验必填字段
    if (selectedScenario.value?.inputs_config) {
      for (const input of selectedScenario.value.inputs_config) {
        if (input.required && !inputsForm[input.key]) {
          ElMessage.warning(`${inputI18n(input, 'label')} ${t('common.required')}`)
          return
        }
      }
    }
    // 生成预览（等待完成后再切换步骤）
    await generatePreview()
  }
  currentStep.value++
}

// 上一步
function prevStep() {
  currentStep.value--
}

// 切换步骤展开/折叠
function toggleStepExpand(idx: number) {
  expandedStepIndex.value = expandedStepIndex.value === idx ? -1 : idx
}

// 步骤类型对应的颜色
function stepTypeColor(type: string) {
  const colorMap: Record<string, string> = {
    llm_generate: 'primary',
    image_gen: 'success',
    video_gen: 'warning',
    audio_gen: 'info',
    composite: 'danger',
  }
  return colorMap[type] || 'info'
}

/** 加载可用模型列表（从后端 model_definitions 表动态获取） */
async function loadAvailableModels() {
  modelsLoading.value = true
  try {
    const res = await getAvailableModels()
    availableModels.value = res.items || []
  } catch (err: any) {
    console.error('Failed to load available models:', err)
    // 使用默认模型列表作为 fallback
    availableModels.value = [
      { model_id: 'agnes-2.0-flash', name: 'Agnes 2.0 Flash', type: 'chat' },
      { model_id: 'agnes-2.0-pro', name: 'Agnes 2.0 Pro', type: 'chat' },
      { model_id: 'agnes-image-2.1-flash', name: 'Agnes Image 2.1 Flash', type: 'image' },
      { model_id: 'agnes-video-1.0', name: 'Agnes Video 1.0', type: 'video' },
    ]
  } finally {
    modelsLoading.value = false
  }
}

/** 根据步骤类型过滤可用模型列表 */
function getModelsForStep(stepType: string): any[] {
  if (availableModels.value.length === 0) return []
  const typeMap: Record<string, string> = {
    llm_generate: 'chat',
    image_gen: 'image',
    video_gen: 'video',
    audio_gen: 'audio',
  }
  const targetType = typeMap[stepType]
  return targetType
    ? availableModels.value.filter((m: any) => m.type === targetType)
    : availableModels.value
}

/**
 * 渲染模板字符串：将 config 中的 {variable} 替换为 inputsForm 中的实际值
 * 同时保证数值字段为 number 类型（el-input-number 要求）
 */
function renderConfigTemplates(config: Record<string, any>): Record<string, any> {
  const rendered: Record<string, any> = {}
  for (const key of Object.keys(config)) {
    let val: any = config[key]
    // 字符串类型：做变量替换
    if (typeof val === 'string') {
      rendered[key] = val.replace(/\{(.+?)\}/g, (_: string, varName: string) => {
        const inputVal = inputsForm[varName]
        return inputVal !== undefined ? String(inputVal) : `{${varName}}`
      })
      // 尝试转为数字（seconds / duration 等字段）
      const num = Number(rendered[key])
      if (!isNaN(num) && rendered[key].trim() !== '') {
        rendered[key] = num
      }
    } else {
      rendered[key] = val
    }
  }
  return rendered
}

// 生成预览（包括可编辑的步骤配置）
async function generatePreview() {
  if (!selectedScenario.value) return
  const scenario = selectedScenario.value
  
  // 从 steps_config_template 提取步骤，并渲染模板变量
  const stepsTemplate = (scenario as any).steps_config_template || []

  editableSteps.value = stepsTemplate.map((step: any) => {
    const renderedConfig = renderConfigTemplates(step.config_template || {})
    return {
      ...step,
      config: { ...renderedConfig },
    }
  })
  
  // 生成预览步骤列表
  previewSteps.value = editableSteps.value.map((step: any) => ({
    name: step.name || step.key || 'Unknown',
    name_i18n: step.name_i18n,
    type: step.type || 'unknown',
    key: step.key,
  }))
  
  // 使用场景预设的预估积分和时长
  previewCredits.value = scenario.estimated_credits || 100
  previewTime.value = scenario.estimated_time_minutes || 10
  
  // 默认展开第一个步骤
  if (editableSteps.value.length > 0) {
    expandedStepIndex.value = 0
  }
  
  // 加载可用模型列表
  await loadAvailableModels()
}

// 创建模板
async function handleCreate() {
  if (!selectedScenario.value) return
  creating.value = true
  try {
    // 构建自定义的 steps_config（使用用户编辑后的配置）
    const customStepsConfig = editableSteps.value.map((step: any) => ({
      key: step.key,
      name: step.name,
      name_i18n: step.name_i18n,
      type: step.type,
      depends_on: step.depends_on || [],
      config: { ...step.config },
    }))
    
    const res = await createTemplateFromScenario({
      scenario_key: selectedScenario.value.key,
      inputs: { ...inputsForm },
      name: `${scenarioI18n(selectedScenario.value, 'name')}-${inputsForm.topic || inputsForm.product || t('workshop.templateWizard.title')}`,
      is_public: false,
      custom_steps_config: customStepsConfig, // 传递用户自定义的步骤配置
    })
    createdTemplateId.value = res.id
    currentStep.value = 4
  } catch (err: any) {
    ElMessage.error(`${t('workshop.templateWizard.createFailed')}: ${err.message || err}`)
  } finally {
    creating.value = false
  }
}

// 创建后运行
function runCreated() {
  if (!createdTemplateId.value) return
  router.push(`/workshop/run/${createdTemplateId.value}`)
}

// 创建后返回工坊
function goToWorkshopAfterCreate() {
  router.push('/workshop')
}

// 返回
function goBack() {
  router.push('/workshop')
}

onMounted(() => {
  loadScenarios()
})
</script>

<style scoped>
.template-wizard {
  padding: 24px;
  max-width: 960px;
  margin: 0 auto;
}

.wizard-header {
  margin-bottom: 32px;
}

.header-title {
  font-size: 20px;
  font-weight: 600;
}

.wizard-steps {
  margin-top: 24px;
}

.wizard-body {
  min-height: 400px;
}

.step-content {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}

.step-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 8px;
}

.step-desc {
  color: var(--el-text-color-secondary);
  margin-bottom: 24px;
}

/* 场景卡片网格 */
.scenario-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.scenario-card {
  padding: 20px;
  border: 2px solid var(--el-border-color);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.scenario-card:hover {
  border-color: var(--scenario-color);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.scenario-card.active {
  border-color: var(--scenario-color);
  background: color-mix(var(--scenario-color) 8%, var(--el-bg-color));
}

.scenario-icon {
  font-size: 32px;
  margin-bottom: 12px;
}

.scenario-name {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}

.scenario-desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

/* 输入表单 */
.inputs-form {
  max-width: 600px;
}

/* 预览区域 */
.preview-section {
  margin-bottom: 24px;
  padding: 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}

.step-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--el-bg-color);
  border-radius: 6px;
}

.step-idx {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: var(--el-color-primary);
  color: #fff;
  border-radius: 50%;
  font-size: 12px;
  font-weight: bold;
}

.credits-preview {
  margin-top: 12px;
  font-size: 24px;
  font-weight: bold;
  color: var(--el-color-primary);
}

/* 创建成功状态 */
.success-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 320px;
  text-align: center;
  animation: fadeIn 0.4s ease;
}

.success-title {
  font-size: 22px;
  font-weight: 700;
  margin-top: 20px;
  margin-bottom: 12px;
  color: var(--el-color-success);
}

.success-desc {
  font-size: 15px;
  color: var(--el-text-color-secondary);
  margin-bottom: 32px;
  max-width: 420px;
  line-height: 1.6;
}

.success-actions {
  display: flex;
  gap: 16px;
}

/* 步骤配置列表 */
.steps-config-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 24px;
}

.step-config-card {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.3s ease;
}

.step-config-card:hover {
  border-color: var(--el-color-primary);
}

.step-config-card.expanded {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.step-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  background: var(--el-fill-color-light);
  transition: background 0.2s ease;
}

.step-card-header:hover {
  background: var(--el-fill-color);
}

.step-card-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.step-card-header .el-icon {
  transition: transform 0.3s ease;
}

.step-card-header .el-icon.is-rotate {
  transform: rotate(180deg);
}

.step-card-body {
  padding: 16px;
  border-top: 1px solid var(--el-border-color);
  animation: slideDown 0.3s ease;
}

@keyframes slideDown {
  from {
    opacity: 0;
    max-height: 0;
  }
  to {
    opacity: 1;
    max-height: 500px;
  }
}

.config-field {
  margin-bottom: 16px;
}

.config-field:last-child {
  margin-bottom: 0;
}

.field-label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
}

.field-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.config-select {
  width: 100%;
  max-width: 400px;
}

/* 底部操作栏 */
.wizard-footer {
  display: flex;
  justify-content: space-between;
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid var(--el-border-color);
}
</style>
