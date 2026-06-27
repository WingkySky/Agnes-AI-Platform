<!-- =====================================================
     流水线运行配置页面 PipelineRunView
     - 显示模板详情和步骤概览
     - 基于 inputs_config 动态渲染输入表单
     - 预估积分消耗（复用 useCreditEstimate）
     - 启动流水线并跳转到结果页
     ===================================================== -->

<template>
  <div class="pipeline-run-view">
    <!-- 返回按钮 + 标题 -->
    <div class="page-header">
      <el-button type="primary" link @click="goBack">
        <el-icon><ArrowLeft /></el-icon>
        {{ t('pipelineRun.back') }}
      </el-button>
      <h2 class="page-title">{{ template?.name || t('pipelineRun.title') }}</h2>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading-wrap">
      <el-icon :size="32" class="spinner"><Loading /></el-icon>
      <span>{{ t('common.loading') }}</span>
    </div>

    <!-- 主内容 -->
    <div v-else-if="template" class="run-content">
      <!-- 左侧：配置区 -->
      <div class="config-panel">
        <el-card class="config-card">
          <template #header>
            <div class="card-header">
              <span>{{ t('pipelineRun.configTitle') }}</span>
            </div>
          </template>

          <!-- 运行名称 -->
          <div class="form-item">
            <label class="form-label">{{ t('pipelineRun.runName') }}</label>
            <el-input
              v-model="runName"
              :placeholder="t('pipelineRun.runNamePlaceholder')"
              maxlength="50"
              show-word-limit />
          </div>

          <!-- 动态渲染输入配置项（基于 template.inputs_config） -->
          <el-divider v-if="template.inputs_config?.length" />

          <template v-for="(field, idx) in template.inputs_config" :key="field.key">
            <!-- 文本/主题输入 -->
            <div v-if="field.type === 'text'" class="form-item">
              <label class="form-label">
                {{ field.label }}
                <span v-if="field.required" class="required">*</span>
              </label>
              <el-input
                v-model="inputs[field.key]"
                type="textarea"
                :rows="4"
                :placeholder="field.placeholder || t('pipelineRun.promptPlaceholder')"
                maxlength="2000"
                show-word-limit />
              <div v-if="field.description" class="field-desc">{{ field.description }}</div>
            </div>

            <!-- 数字输入 -->
            <div v-else-if="field.type === 'number'" class="form-item">
              <label class="form-label">
                {{ field.label }}
                <span v-if="field.required" class="required">*</span>
                <span v-if="field.min !== undefined || field.max !== undefined" class="hint">
                  （{{ field.min || 1 }}-{{ field.max || 100 }}）
                </span>
              </label>
              <el-input-number
                v-model="inputs[field.key]"
                :min="field.min || 1"
                :max="field.max || 100"
                :step="1" />
              <div v-if="field.description" class="field-desc">{{ field.description }}</div>
            </div>

            <!-- 风格预设选择：支持套装预设 / 分层组合两种模式 -->
            <div v-else-if="field.type === 'style_select'" class="form-item">
              <label class="form-label">
                {{ field.label }}
                <span v-if="field.required" class="required">*</span>
              </label>
              <!-- 模式切换 -->
              <el-radio-group v-model="styleMode" size="small" class="style-mode-radio">
                <el-radio-button value="preset">{{ t('pipelineRun.styleModePreset') }}</el-radio-button>
                <el-radio-button value="elements">{{ t('pipelineRun.styleModeElements') }}</el-radio-button>
              </el-radio-group>
              <!-- 路径 A：套装预设（保留现有 StyleSelector） -->
              <div v-if="styleMode === 'preset'">
                <StyleSelector v-model="inputs[field.key]" />
              </div>
              <!-- 路径 B：分层组合 -->
              <div v-else>
                <StyleElementPicker
                  :base-prompt="basePromptForStyle"
                  @change="onStyleElementsChange" />
                <el-button
                  type="primary"
                  text
                  size="small"
                  class="create-custom-btn"
                  @click="showElementEditor = true">
                  <el-icon><Plus /></el-icon>
                  {{ t('styleElement.createCustom') }}
                </el-button>
                <StyleElementEditor
                  v-model="showElementEditor"
                  @created="onElementCreated" />
              </div>
              <div v-if="field.description" class="field-desc">{{ field.description }}</div>
            </div>

            <!-- 布尔开关 -->
            <div v-else-if="field.type === 'boolean'" class="form-item form-item-switch">
              <label class="form-label">{{ field.label }}</label>
              <el-switch v-model="inputs[field.key]" />
              <div v-if="field.description" class="field-desc">{{ field.description }}</div>
            </div>

            <!-- 普通下拉选择 -->
            <div v-else-if="field.type === 'select'" class="form-item">
              <label class="form-label">
                {{ field.label }}
                <span v-if="field.required" class="required">*</span>
              </label>
              <el-select
                v-model="inputs[field.key]"
                :placeholder="field.placeholder || ''"
                class="full-width"
                clearable>
                <el-option
                  v-for="opt in field.options"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value" />
              </el-select>
              <div v-if="field.description" class="field-desc">{{ field.description }}</div>
            </div>

            <el-divider v-if="idx < template.inputs_config.length - 1" />
          </template>

          <!-- 摄像机参数（步骤级，适用于 ImageBatch / VideoBatch） -->
          <el-divider />
          <div class="form-item">
            <label class="form-label">{{ t('pipelineRun.cameraParams') || '摄像机参数' }}</label>
            <CameraPresetSelector
              :model-value="cameraPresetId"
              @update:model-value="onCameraPresetSelect($event as number | null)" />
            <div class="camera-toggle-row">
              <el-switch v-model="cameraEnabled" size="small" />
              <span class="toggle-label">启用摄像机参数</span>
            </div>
          </div>

          <!-- 积分预估：来自 useCreditEstimate -->
          <el-divider />
          <div class="credit-estimate">
            <div class="estimate-label">
              <el-icon><Coin /></el-icon>
              <span>{{ t('pipelineRun.estimatedCredits') }}</span>
            </div>
            <div v-if="estimating" class="estimate-value estimating">
              <el-icon class="spinner"><Loading /></el-icon>
              {{ t('pipelineRun.estimating') }}
            </div>
            <div v-else class="estimate-value">
              <span class="credit-num">{{ estimatedCredits ?? template.estimated_credits ?? 0 }}</span>
              {{ t('pipelineRun.credits') }}
            </div>
          </div>

          <!-- 启动按钮（受 pipeline:run 权限控制） -->
          <el-button
            v-permission="'pipeline:run'"
            type="primary"
            size="large"
            class="start-btn"
            :loading="starting"
            :disabled="!canStart"
            @click="startPipeline">
            <el-icon v-if="!starting"><VideoPlay /></el-icon>
            {{ starting ? t('pipelineRun.starting') : t('pipelineRun.start') }}
          </el-button>
        </el-card>
      </div>

      <!-- 右侧：模板信息 + 步骤概览 -->
      <div class="info-panel">
        <!-- 模板信息卡片 -->
        <el-card class="template-card">
          <template #header>
            <span>{{ t('pipelineRun.templateInfo') }}</span>
          </template>
          <div class="template-thumb">
            <img v-if="template.thumbnail" :src="template.thumbnail" :alt="template.name" />
            <div v-else class="thumb-placeholder">
              <el-icon :size="48"><MagicStick /></el-icon>
            </div>
          </div>
          <p class="template-desc">{{ template.description }}</p>
          <div v-if="template.tags && template.tags.length > 0" class="template-tags">
            <el-tag
              v-for="tag in template.tags"
              :key="tag"
              size="small"
              type="info"
              effect="plain">
              {{ tag }}
            </el-tag>
          </div>
          <div class="template-meta">
            <div class="meta-row">
              <span class="meta-label">{{ t('pipelineRun.estimatedTime') }}</span>
              <span class="meta-value">{{ template.estimated_time }}</span>
            </div>
            <div class="meta-row">
              <span class="meta-label">{{ t('pipelineRun.stepCount') }}</span>
              <span class="meta-value">{{ template.steps_config?.length || 0 }} {{ t('pipelineRun.steps') }}</span>
            </div>
          </div>
        </el-card>

        <!-- 步骤概览 -->
        <el-card class="steps-card">
          <template #header>
            <span>{{ t('pipelineRun.stepOverview') }}</span>
          </template>
          <div class="steps-list">
            <div
              v-for="(step, idx) in template.steps_config"
              :key="step.key"
              class="step-item">
              <div class="step-index">{{ idx + 1 }}</div>
              <div class="step-info">
                <div class="step-name">{{ step.name || step.key }}</div>
                <div class="step-type">{{ getStepTypeLabel(step.type) }}</div>
              </div>
            </div>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from '@/i18n'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, Loading, Coin, VideoPlay, MagicStick, Plus
} from '@element-plus/icons-vue'
import {
  getPipelineTemplateDetail,
  type PipelineTemplate,
  type PipelineInputConfig,
} from '@/api/pipeline'
import { usePipelineStore } from '@/stores/pipeline'
import { useCreditEstimate } from '@/composables/useCreditEstimate'
import StyleSelector from '@/components/pipeline/StyleSelector.vue'
import StyleElementPicker from '@/components/pipeline/StyleElementPicker.vue'
import StyleElementEditor from '@/components/pipeline/StyleElementEditor.vue'
import CameraPresetSelector from '@/components/CameraPresetSelector.vue'
import { useCameraStore } from '@/stores/camera'
import type { ResolvedElementItem } from '@/api/styleElement'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const pipelineStore = usePipelineStore()
const cameraStore = useCameraStore()

// ---------- 状态 ----------
const loading = ref(false)
const starting = ref(false)
const template = ref<PipelineTemplate | null>(null)
const runName = ref('')
const inputs = ref<Record<string, any>>({})

// 风格选择模式：preset 套装预设 / elements 分层组合
const styleMode = ref<'preset' | 'elements'>('preset')
// 分层组合模式下用户已选的风格元素列表（带权重）
const styleElements = ref<ResolvedElementItem[]>([])
// 用户自建风格元素弹窗显隐
const showElementEditor = ref(false)

// 摄像机参数状态
const cameraEnabled = ref(false)
const cameraPresetId = ref<number | null>(null)

/** 摄像机预设选择回调 */
function onCameraPresetSelect(presetId: number | null) {
  cameraPresetId.value = presetId
  if (presetId !== null) {
    cameraStore.selectPreset(presetId)
  }
}

/** 分层组合模式下，传给 StyleElementPicker 的 basePrompt（从 topic/prompt 字段取值） */
const basePromptForStyle = computed(() => {
  return String(inputs.value.topic || inputs.value.prompt || '')
})

/** 判断必填项是否已填写，按钮是否可点击 */
const canStart = computed(() => {
  if (!template.value || starting.value) return false
  const configs = template.value.inputs_config || []
  for (const field of configs) {
    if (!field.required) continue
    // 分层组合模式下，style_select 必填校验改为：已选至少 1 个风格元素
    if (field.type === 'style_select' && styleMode.value === 'elements') {
      if (styleElements.value.length === 0) return false
      continue
    }
    const val = inputs.value[field.key]
    if (val === undefined || val === null || val === '') return false
    if (typeof val === 'string' && !val.trim()) return false
  }
  return true
})

// ---------- 积分预估：复用 useCreditEstimate 组合式函数 ----------
const {
  cost: estimatedCredits,
  loading: estimating,
  insufficient,
  refresh: refreshEstimate,
} = useCreditEstimate(
  () => ({
    type: 'pipeline' as const,
    templateId: Number(route.params.templateId),
    inputs: collectInputs(),
  })
)

// ---------- 方法 ----------
function goBack() {
  router.push('/workshop')
}

/** 分层风格选择器：已选元素变化回调 */
function onStyleElementsChange(elements: ResolvedElementItem[]) {
  styleElements.value = elements
}

/** 用户自建风格元素创建成功回调 */
function onElementCreated() {
  ElMessage.success(t('styleElement.createSuccess'))
}

async function loadTemplate() {
  const templateId = Number(route.params.templateId)
  if (!templateId) {
    ElMessage.error(t('pipelineRun.invalidTemplate'))
    router.push('/workshop')
    return
  }

  loading.value = true
  try {
    template.value = await getPipelineTemplateDetail(templateId)
    initDefaultInputs()
    // 模板加载完成后刷新一次预估（useCreditEstimate 内部也会 watch，这里显式触发一次以避免首次入参时机问题）
    refreshEstimate()
  } catch (e: any) {
    ElMessage.error(e?.message || t('pipelineRun.loadTemplateFailed'))
    router.push('/workshop')
  } finally {
    loading.value = false
  }
}

/** 根据 inputs_config 初始化表单默认值 */
function initDefaultInputs() {
  if (!template.value?.inputs_config) return

  template.value.inputs_config.forEach((field: PipelineInputConfig) => {
    if (field.default !== undefined) {
      inputs.value[field.key] = field.default
    } else if (field.type === 'number') {
      inputs.value[field.key] = field.min || 1
    } else if (field.type === 'boolean') {
      inputs.value[field.key] = false
    } else if (field.type === 'style_select') {
      // styleId 期望 number | null，避免传空字符串给 StyleSelector 触发类型告警
      inputs.value[field.key] = null
    } else {
      inputs.value[field.key] = ''
    }
  })
}

/** 收集表单输入，构建提交给后端的 inputs 结构（顶层 key-value） */
function collectInputs(): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  if (!template.value?.inputs_config) return result

  template.value.inputs_config.forEach((field: PipelineInputConfig) => {
    // 分层组合模式：提交 style_elements 数组，不提交 style_id
    if (field.type === 'style_select' && styleMode.value === 'elements') {
      if (styleElements.value.length > 0) {
        result['style_elements'] = styleElements.value
      }
      return
    }
    const val = inputs.value[field.key]
    // 过滤掉 undefined/null 的值
    if (val !== undefined && val !== null && val !== '') {
      result[field.key] = val
    }
  })

  // 摄像机参数：启用时注入 camera_params
  if (cameraEnabled.value) {
    result['camera_params'] = { ...cameraStore.cameraParams, enabled: true }
  }

  return result
}

async function startPipeline() {
  if (!template.value || !canStart.value) return

  try {
    await ElMessageBox.confirm(
      t('pipelineRun.startConfirmText'),
      t('pipelineRun.startConfirmTitle'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'info',
      }
    )
  } catch {
    return
  }

  starting.value = true
  try {
    // 通过 pipelineStore.createRun 创建运行（内部会注册到任务队列）
    const run = await pipelineStore.createRun(
      template.value.id,
      collectInputs(),
      runName.value || undefined
    )

    ElMessage.success(t('pipelineRun.started'))
    router.push(`/workshop/result/${run.id}`)
  } catch (e: any) {
    ElMessage.error(e?.message || t('pipelineRun.startFailed'))
  } finally {
    starting.value = false
  }
}

function getStepTypeLabel(type: string): string {
  const map: Record<string, string> = {
    'llm_generate': 'LLM 剧本生成',
    'image_batch': '图片批量生成',
    'video_batch': '视频批量生成',
    'style_apply': '风格应用',
  }
  return map[type] || type
}

// ---------- 生命周期 ----------
onMounted(() => {
  loadTemplate()
})
</script>

<style scoped>
.pipeline-run-view {
  padding: 20px 32px 40px;
  max-width: 1280px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0;
  color: var(--agnes-text-primary);
}

.loading-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 80px;
  gap: 12px;
  color: var(--agnes-text-secondary);
}

.spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.run-content {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 24px;
  align-items: start;
}

.config-panel {
  min-width: 0;
}

.info-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.card-header {
  font-weight: 600;
  color: var(--agnes-text-primary);
}

.form-item {
  margin-bottom: 20px;
}

.form-item-switch {
  display: flex;
  align-items: center;
  gap: 12px;
}

.form-item-switch .form-label {
  margin-bottom: 0;
}

.form-label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: var(--agnes-text-primary);
  margin-bottom: 8px;
}

.required {
  color: var(--agnes-error);
  margin-left: 2px;
}

.hint {
  font-weight: 400;
  color: var(--agnes-text-secondary);
  font-size: 12px;
}

.field-desc {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  margin-top: 6px;
  line-height: 1.5;
}

.style-mode-radio {
  margin-bottom: 12px;
}

.create-custom-btn {
  margin-top: 8px;
}

.full-width {
  width: 100%;
}

.credit-estimate {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--agnes-credits-bg);
  border: 1px solid var(--agnes-credits-border);
  border-radius: 8px;
  margin-bottom: 20px;
}

.estimate-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--agnes-credits-text);
  font-weight: 500;
}

.estimate-value {
  font-size: 14px;
  color: var(--agnes-text-primary);
}

.estimate-value.estimating {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--agnes-text-secondary);
}

.credit-num {
  font-size: 20px;
  font-weight: 700;
  color: var(--agnes-credits-value);
  margin-right: 4px;
}

.start-btn {
  width: 100%;
  height: 48px;
  font-size: 16px;
  font-weight: 600;
  border-radius: 12px !important;
}

/* 模板信息卡片 */
.template-thumb {
  width: 100%;
  height: 140px;
  background: var(--agnes-bg-dark-surface);
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 12px;
}

.template-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--agnes-text-faint);
}

.template-desc {
  font-size: 13px;
  color: var(--agnes-text-secondary);
  line-height: 1.6;
  margin: 0 0 12px 0;
}

.template-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.template-meta {
  border-top: 1px solid var(--agnes-border);
  padding-top: 12px;
}

.meta-row {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 13px;
}

.meta-label {
  color: var(--agnes-text-secondary);
}

.meta-value {
  color: var(--agnes-text-primary);
  font-weight: 500;
}

/* 步骤概览 */
.steps-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.step-index {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--agnes-primary-border-faint);
  color: var(--agnes-primary);
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.step-info {
  flex: 1;
  min-width: 0;
}

.step-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--agnes-text-primary);
}

.step-type {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  margin-top: 2px;
}
</style>
