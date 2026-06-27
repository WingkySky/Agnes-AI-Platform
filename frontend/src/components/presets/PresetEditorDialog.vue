<!-- =====================================================
     PresetEditorDialog — 新建/编辑预设弹窗
     - type 下拉（camera/prompt/style/script/pipeline）决定表单切换
     - 通用字段：名称 + 分类下拉 + 标签输入 + 文本编辑区
     - camera 类型：复用摄像机参数面板（10 个参数字段）
     ===================================================== -->

<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? t('presets.editor.editTitle') : t('presets.editor.createTitle')"
    width="720px"
    :close-on-click-modal="false"
    destroy-on-close
    @closed="resetForm"
  >
    <el-form ref="formRef" :model="form" label-width="110px" label-position="right">
      <!-- ====== 类型选择 ====== -->
      <el-form-item :label="t('presets.editor.typeLabel')" required>
        <el-select
          v-model="form.type"
          style="width: 100%"
          :disabled="isEdit"
          @change="onTypeChange"
        >
          <el-option :label="t('presets.editor.typePrompt')" value="prompt" />
          <el-option :label="t('presets.editor.typeCamera')" value="camera" />
          <el-option :label="t('presets.editor.typeStyle')" value="style" />
          <el-option :label="t('presets.editor.typeScript')" value="script" />
          <el-option :label="t('presets.editor.typePipeline')" value="pipeline" />
        </el-select>
      </el-form-item>

      <!-- ====== 基本信息（通用） ====== -->
      <el-form-item :label="t('presets.editor.nameLabel')" required>
        <el-input
          v-model="form.name"
          :placeholder="t('presets.editor.namePlaceholder')"
          maxlength="60"
          show-word-limit
        />
      </el-form-item>

      <el-form-item :label="t('presets.editor.descLabel')">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="2"
          :placeholder="t('presets.editor.descPlaceholder')"
          maxlength="300"
          show-word-limit
        />
      </el-form-item>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="t('presets.editor.categoryLabel')">
            <div style="display: flex; gap: 6px; width: 100%">
              <el-select v-model="form.category" style="flex: 1">
                <el-option :label="t('presets.editor.catGeneral')" value="通用" />
                <el-option :label="t('presets.editor.catPortrait')" value="人像" />
                <el-option :label="t('presets.editor.catScene')" value="场景" />
                <el-option :label="t('presets.editor.catComposition')" value="构图" />
                <el-option :label="t('presets.editor.catAction')" value="动作" />
                <el-option :label="t('presets.editor.catLighting')" value="光影" />
                <el-option :label="t('presets.editor.catStyle')" value="风格" />
              </el-select>
              <el-tooltip :content="t('presets.editor.aiCategoryTip')" placement="top">
                <el-button
                  :icon="MagicStick"
                  circle
                  size="small"
                  :loading="aiClassifying"
                  @click="handleAiClassify"
                />
              </el-tooltip>
            </div>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('presets.editor.publicLabel')">
            <el-switch
              v-model="form.is_public"
              :active-text="t('presets.editor.publicActive')"
              :inactive-text="t('presets.editor.publicInactive')"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item :label="t('presets.editor.tagsLabel')">
        <el-select
          v-model="form.tags"
          multiple
          filterable
          allow-create
          default-first-option
          :placeholder="t('presets.editor.tagsPlaceholder')"
          style="width: 100%"
        />
      </el-form-item>

      <!-- ====== 提示词文本（prompt / style / script / camera 共用） ====== -->
      <el-form-item v-if="form.type !== 'pipeline'" :label="t('presets.editor.promptLabel')">
        <el-input
          v-model="form.prompt_text"
          type="textarea"
          :rows="4"
          :placeholder="promptTextPlaceholder"
        />
      </el-form-item>

      <!-- ====== Camera 专属：摄像机参数面板 ====== -->
      <template v-if="form.type === 'camera'">
        <el-divider content-position="left">
          <span class="section-title">{{ t('presets.editor.cameraSection') }}</span>
        </el-divider>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('presets.editor.cameraModel')">
              <el-input
                v-model="cameraParams.camera_model"
                :placeholder="t('presets.editor.cameraModelPlaceholder')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('presets.editor.focalLength')">
              <el-input
                v-model="cameraParams.focal_length"
                :placeholder="t('presets.editor.focalLengthPlaceholder')"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('presets.editor.aperture')">
              <el-input
                v-model="cameraParams.aperture"
                :placeholder="t('presets.editor.aperturePlaceholder')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('presets.editor.depthOfField')">
              <el-select v-model="cameraParams.depth_of_field" style="width: 100%" clearable>
                <el-option :label="t('presets.editor.dofShallow')" value="浅景深" />
                <el-option :label="t('presets.editor.dofDeep')" value="深景深" />
                <el-option :label="t('presets.editor.dofMedium')" value="中等景深" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('presets.editor.shutterSpeed')">
              <el-input
                v-model="cameraParams.shutter_speed"
                :placeholder="t('presets.editor.shutterSpeedPlaceholder')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('presets.editor.shutterAngle')">
              <el-input
                v-model="cameraParams.shutter_angle"
                :placeholder="t('presets.editor.shutterAnglePlaceholder')"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('presets.editor.cameraMovement')">
              <el-select v-model="cameraParams.camera_movement" style="width: 100%" clearable>
                <el-option :label="t('presets.editor.movStatic')" value="固定机位" />
                <el-option :label="t('presets.editor.movHandheld')" value="手持运镜" />
                <el-option :label="t('presets.editor.movDolly')" value="推拉运镜" />
                <el-option :label="t('presets.editor.movPan')" value="摇摄" />
                <el-option :label="t('presets.editor.movTracking')" value="跟拍" />
                <el-option :label="t('presets.editor.movAerial')" value="航拍" />
                <el-option :label="t('presets.editor.movSteadicam')" value="稳定器" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('presets.editor.cameraAngle')">
              <el-select v-model="cameraParams.camera_angle" style="width: 100%" clearable>
                <el-option :label="t('presets.editor.angleEyeLevel')" value="平视" />
                <el-option :label="t('presets.editor.angleLow')" value="低角度仰拍" />
                <el-option :label="t('presets.editor.angleHigh')" value="高角度俯拍" />
                <el-option :label="t('presets.editor.angleDutch')" value="倾斜构图" />
                <el-option :label="t('presets.editor.angleOverhead')" value="顶视" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('presets.editor.aspectRatio')">
              <el-select v-model="cameraParams.aspect_ratio" style="width: 100%" clearable>
                <el-option label="16:9" value="16:9" />
                <el-option label="2.35:1" value="2.35:1" />
                <el-option label="1:1" value="1:1" />
                <el-option label="4:3" value="4:3" />
                <el-option label="3:2" value="3:2" />
                <el-option label="9:16" value="9:16" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('presets.editor.visualStyle')">
              <el-input
                v-model="cameraParams.visual_style"
                :placeholder="t('presets.editor.visualStylePlaceholder')"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </template>

      <!-- ====== Script 专属 ====== -->
      <template v-if="form.type === 'script'">
        <el-divider content-position="left">
          <span class="section-title">{{ t('presets.editor.scriptSection') }}</span>
        </el-divider>
        <el-form-item :label="t('presets.editor.scriptContent')">
          <el-input
            v-model="form.script_text"
            type="textarea"
            :rows="6"
            :placeholder="t('presets.editor.scriptPlaceholder')"
          />
        </el-form-item>
      </template>

      <!-- ====== Pipeline 专属 ====== -->
      <template v-if="form.type === 'pipeline'">
        <el-divider content-position="left">
          <span class="section-title">{{ t('presets.editor.pipelineSection') }}</span>
        </el-divider>
        <el-form-item :label="t('presets.editor.pipelineJson')">
          <el-input
            v-model="pipelineConfigStr"
            type="textarea"
            :rows="6"
            placeholder='{ "steps": [{ "type": "image", "prompt": "..." }] }'
          />
        </el-form-item>
      </template>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">{{ t('presets.editor.cancel') }}</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        {{ isEdit ? t('presets.editor.save') : t('presets.editor.create') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * PresetEditorDialog — 提示词预设创建/编辑弹窗
 * 通过 v-model 控制显隐，通过 submit 事件回传表单数据。
 */
import { ref, reactive, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import type { PromptPreset, PresetCreate, PresetUpdate, PresetType } from '@/types/preset'

const { t } = useI18n()

const props = defineProps<{
  modelValue: boolean
  preset?: PromptPreset | null  // 编辑模式：传入已有预设
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'submit': [data: PresetCreate | PresetUpdate]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const isEdit = computed(() => !!props.preset)
const submitting = ref(false)
const aiClassifying = ref(false)
const formRef = ref()

// 摄像机参数子表单
const cameraParams = reactive({
  camera_model: '',
  focal_length: '',
  aperture: '',
  depth_of_field: '',
  shutter_speed: '',
  shutter_angle: '',
  camera_movement: '',
  camera_angle: '',
  aspect_ratio: '',
  visual_style: '',
})

// 流水线配置 JSON 字符串
const pipelineConfigStr = ref('{}')

interface FormData {
  name: string
  description: string
  type: PresetType
  category: string
  tags: string[]
  prompt_text: string
  script_text: string
  is_public: boolean
}

const form = reactive<FormData>({
  name: '',
  description: '',
  type: 'prompt',
  category: '通用',
  tags: [],
  prompt_text: '',
  script_text: '',
  is_public: false,
})

// 提示词文本占位符（按类型走 i18n）
const promptTextPlaceholder = computed(() => {
  const map: Record<string, string> = {
    prompt: t('presets.editor.promptPlaceholderPrompt'),
    camera: t('presets.editor.promptPlaceholderPrompt'),
    style: t('presets.editor.promptPlaceholderStyle'),
    script: t('presets.editor.promptPlaceholderScript'),
  }
  return map[form.type] || t('presets.editor.promptPlaceholderPrompt')
})

// 类型切换时清理不相关字段
function onTypeChange() {
  // 清空摄像机参数
  Object.keys(cameraParams).forEach((k) => {
    (cameraParams as any)[k] = ''
  })
  pipelineConfigStr.value = '{}'
}

function resetForm() {
  form.name = ''
  form.description = ''
  form.type = 'prompt'
  form.category = '通用'
  form.tags = []
  form.prompt_text = ''
  form.script_text = ''
  form.is_public = false
  onTypeChange()
}

// 编辑模式：加载已有预设数据
function loadPreset() {
  if (!props.preset) return
  const p = props.preset
  form.name = p.name
  form.description = p.description || ''
  form.type = p.type
  form.category = p.category
  form.tags = p.tags || []
  form.prompt_text = p.prompt_text || ''
  form.script_text = p.script_text || ''
  form.is_public = p.is_public

  // 加载摄像机参数
  if (p.camera_params && typeof p.camera_params === 'object') {
    const cp = p.camera_params as Record<string, any>
    cameraParams.camera_model = cp.camera_model || ''
    cameraParams.focal_length = cp.focal_length || ''
    cameraParams.aperture = cp.aperture || ''
    cameraParams.depth_of_field = cp.depth_of_field || ''
    cameraParams.shutter_speed = cp.shutter_speed || ''
    cameraParams.shutter_angle = cp.shutter_angle || ''
    cameraParams.camera_movement = cp.camera_movement || ''
    cameraParams.camera_angle = cp.camera_angle || ''
    cameraParams.aspect_ratio = cp.aspect_ratio || ''
    cameraParams.visual_style = cp.visual_style || ''
  }

  // 加载流水线配置
  if (p.pipeline_config) {
    pipelineConfigStr.value = JSON.stringify(p.pipeline_config, null, 2)
  }
}

// 弹窗打开时加载
watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      resetForm()
      if (props.preset) {
        loadPreset()
      }
    }
  }
)

/** AI 自动分类：根据名称和描述推断分类和标签（预留后端接口） */
async function handleAiClassify() {
  if (!form.name.trim()) {
    ElMessage.warning(t('presets.editor.nameRequired'))
    return
  }
  aiClassifying.value = true
  try {
    // TODO: 接入后端 AI 分类 API
    // const result = await aiClassify({ name: form.name, description: form.description })
    // form.category = result.category
    // form.tags = [...result.tags]
    ElMessage.info(t('presets.editor.aiCategoryComingSoon'))
  } catch (_) {
    ElMessage.error(t('presets.editor.aiCategoryFailed'))
  } finally {
    aiClassifying.value = false
  }
}

async function handleSubmit() {
  if (!form.name.trim()) {
    ElMessage.warning(t('presets.editor.nameRequired'))
    return
  }

  submitting.value = true
  try {
    const data: PresetCreate = {
      name: form.name.trim(),
      description: form.description.trim() || undefined,
      type: form.type,
      category: form.category,
      tags: form.tags.length ? [...form.tags] : undefined,
      prompt_text: form.prompt_text,
      is_public: form.is_public,
    }

    // 按类型附加专属字段
    if (form.type === 'camera') {
      const hasCameraParam = Object.values(cameraParams).some((v) => v)
      if (hasCameraParam) {
        data.camera_params = { ...cameraParams }
      }
    }

    if (form.type === 'script' && form.script_text.trim()) {
      data.script_text = form.script_text.trim()
    }

    if (form.type === 'pipeline') {
      try {
        data.pipeline_config = JSON.parse(pipelineConfigStr.value || '{}')
      } catch {
        ElMessage.warning(t('presets.editor.pipelineJsonInvalid'))
        submitting.value = false
        return
      }
    }

    emit('submit', data)
    visible.value = false
  } catch (_) {
    // 错误由调用方处理
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.section-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--agnes-text-primary);
}
</style>
