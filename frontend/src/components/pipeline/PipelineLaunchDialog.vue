<template>
  <el-dialog
    v-model="visible"
    :title="t('canvas.pipelineLaunch.title')"
    width="640px"
    :close-on-click-modal="false"
    destroy-on-close
    @closed="resetState"
  >
    <!-- 步骤1：选择模板 -->
    <template v-if="step === 1">
      <div class="launch-section">
        <p class="launch-desc">{{ t('canvas.pipelineLaunch.selectTemplate') }}</p>
        <el-scrollbar max-height="380px">
          <div class="template-list">
            <div
              v-for="tpl in templates"
              :key="tpl.id"
              class="template-item"
              :class="{ selected: selectedTemplateId === tpl.id }"
              @click="selectTemplate(tpl)"
            >
              <div class="template-thumb">
                <img v-if="tpl.thumbnail" :src="tpl.thumbnail" :alt="tpl.name" />
                <Film v-else :size="48" />
              </div>
              <div class="template-info">
                <div class="template-name">{{ tpl.name }}</div>
                <div class="template-desc">{{ tpl.description }}</div>
                <div class="template-meta">
                  <el-tag size="small" type="info">{{ tpl.category }}</el-tag>
                  <span class="meta-credits">{{ tpl.estimated_credits }} {{ t('common.credits') }}</span>
                  <span class="meta-time">{{ tpl.estimated_time }}</span>
                </div>
              </div>
            </div>
          </div>
        </el-scrollbar>
      </div>
    </template>

    <!-- 步骤2：配置参数 -->
    <template v-if="step === 2">
      <div class="launch-section">
        <p class="launch-desc">{{ t('canvas.pipelineLaunch.configParams') }}</p>
        <el-form label-position="top" class="param-form">
          <el-form-item
            v-for="input in selectedTemplate?.inputs_config"
            :key="input.key"
            :label="input.label || input.key"
          >
            <!-- 文本输入 -->
            <el-input
              v-if="input.type === 'text' || input.type === 'string'"
              v-model="formInputs[input.key]"
              :placeholder="input.placeholder || input.description"
              type="textarea"
              :rows="input.key === 'story' || input.key === 'prompt' ? 4 : 2"
            />
            <!-- 数字输入 -->
            <el-input-number
              v-else-if="input.type === 'number' || input.type === 'int'"
              v-model="formInputs[input.key]"
              :min="input.min ?? 1"
              :max="input.max ?? 100"
              style="width: 100%"
            />
            <!-- 布尔开关 -->
            <el-switch
              v-else-if="input.type === 'boolean' || input.type === 'bool'"
              v-model="formInputs[input.key]"
            />
            <!-- 下拉选择 -->
            <el-select
              v-else-if="input.type === 'select' || input.type === 'enum'"
              v-model="formInputs[input.key]"
              style="width: 100%"
              :placeholder="input.placeholder || input.description"
            >
              <el-option
                v-for="opt in (input.options || [])"
                :key="typeof opt === 'string' ? opt : opt.value"
                :label="typeof opt === 'string' ? opt : opt.label"
                :value="typeof opt === 'string' ? opt : opt.value"
              />
            </el-select>
            <!-- 兜底：文本输入 -->
            <el-input
              v-else
              v-model="formInputs[input.key]"
              :placeholder="input.placeholder || input.description"
            />
          </el-form-item>
        </el-form>
      </div>
    </template>

    <!-- 步骤3：确认 -->
    <template v-if="step === 3">
      <div class="launch-section">
        <p class="launch-desc">{{ t('canvas.pipelineLaunch.confirmSubmit') }}</p>
        <el-descriptions :column="1" border>
          <el-descriptions-item :label="t('canvas.pipelineLaunch.templateLabel')">
            {{ selectedTemplate?.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('canvas.pipelineLaunch.creditsLabel')">
            {{ selectedTemplate?.estimated_credits }} {{ t('common.credits') }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('canvas.pipelineLaunch.timeLabel')">
            {{ selectedTemplate?.estimated_time }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </template>

    <!-- 错误提示 -->
    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
      style="margin-top: 12px"
    />

    <template #footer>
      <div class="launch-footer">
        <el-button @click="visible = false">{{ t('common.cancel') }}</el-button>
        <el-button v-if="step > 1" @click="step--">{{ t('common.prevStep') }}</el-button>
        <el-button
          v-if="step === 1"
          type="primary"
          :disabled="!selectedTemplateId"
          @click="nextStep"
        >
          {{ t('common.nextStep') }}
        </el-button>
        <el-button
          v-if="step === 2"
          type="primary"
          @click="nextStep"
        >
          {{ t('common.nextStep') }}
        </el-button>
        <el-button
          v-if="step === 3"
          type="primary"
          :loading="submitting"
          @click="handleSubmit"
        >
          {{ t('canvas.pipelineLaunch.startGen') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from '@/i18n'
import {
  ElDialog, ElScrollbar, ElForm, ElFormItem, ElInput, ElInputNumber,
  ElSwitch, ElSelect, ElOption, ElDescriptions, ElDescriptionsItem,
  ElTag, ElButton, ElAlert, ElMessage,
} from 'element-plus'
import { Film } from 'lucide-vue-next'
import { getPipelineTemplates, createPipelineRun } from '@/api/pipeline'
import type { PipelineTemplate } from '@/types'

const router = useRouter()
const { t } = useI18n()

// ---------- props / emit ----------
const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [val: boolean] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

// ---------- 状态 ----------
const step = ref(1)
const templates = ref<PipelineTemplate[]>([])
const selectedTemplateId = ref<number | null>(null)
const selectedTemplate = computed(() => templates.value.find(t => t.id === selectedTemplateId.value))
const formInputs = ref<Record<string, any>>({})
const submitting = ref(false)
const errorMessage = ref('')

// ---------- 加载模板 ----------
async function loadTemplates() {
  try {
    const res = await (getPipelineTemplates as any)()
    if (Array.isArray(res)) {
      templates.value = res
    } else if (res?.data && Array.isArray(res.data)) {
      templates.value = res.data
    } else if (res?.templates && Array.isArray(res.templates)) {
      templates.value = res.templates
    }
  } catch (e: any) {
    errorMessage.value = e?.message || t('canvas.pipelineLaunch.loadFailed')
  }
}

// ---------- 步骤切换 ----------
function selectTemplate(tpl: PipelineTemplate) {
  selectedTemplateId.value = tpl.id
}

function nextStep() {
  if (step.value === 1) {
    if (!selectedTemplateId.value) return
    // 初始化表单默认值
    const cfg = selectedTemplate.value?.inputs_config || []
    for (const input of cfg) {
      if (!(input.key in formInputs.value)) {
        formInputs.value[input.key] = input.default ?? ''
      }
    }
  }
  errorMessage.value = ''
  step.value++
}

async function handleSubmit() {
  if (!selectedTemplateId.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    const payload: any = {
      template_id: selectedTemplateId.value,
      inputs: formInputs.value,
    }
    // 如果有 name 字段使用模板名
    if (selectedTemplate.value) {
      payload.name = `${selectedTemplate.value.name} - ${new Date().toLocaleTimeString()}`
    }
    const res = await (createPipelineRun as any)(payload)
    const runId = res?.id || res?.run_id || res?.data?.id
    ElMessage.success(t('canvas.pipelineLaunch.createSuccess'))
    visible.value = false
    if (runId) {
      router.push(`/workshop/result/${runId}`)
    } else {
      router.push('/workshop/history')
    }
  } catch (e: any) {
    errorMessage.value = e?.message || t('canvas.pipelineLaunch.createFailed')
  } finally {
    submitting.value = false
  }
}

function resetState() {
  step.value = 1
  selectedTemplateId.value = null
  formInputs.value = {}
  errorMessage.value = ''
}

// 打开时加载模板
watch(visible, (val) => {
  if (val && templates.value.length === 0) {
    loadTemplates()
  }
})
</script>

<style scoped>
.launch-section {
  min-height: 200px;
}
.launch-desc {
  font-size: 13px;
  color: var(--agnes-text-secondary);
  margin: 0 0 12px;
}
.template-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.template-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color .2s, background .2s;
}
.template-item:hover {
  background: var(--agnes-bg-hover, rgba(0,0,0,.04));
}
.template-item.selected {
  border-color: var(--agnes-primary);
  background: var(--agnes-primary-light-9, rgba(64,158,255,.08));
}
.template-thumb {
  width: 72px;
  height: 72px;
  border-radius: 6px;
  background: var(--agnes-bg-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
  color: var(--agnes-text-secondary);
}
.template-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.template-info {
  flex: 1;
  min-width: 0;
}
.template-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--agnes-text-primary);
  margin-bottom: 4px;
}
.template-desc {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  margin-bottom: 8px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.template-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--agnes-text-secondary);
}
.meta-credits, .meta-time {
  opacity: 0.7;
}
.param-form {
  max-height: 380px;
  overflow-y: auto;
  padding-right: 4px;
}
.launch-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
