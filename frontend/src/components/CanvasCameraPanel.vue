<!-- =====================================================
     CanvasCameraPanel — 画布节点内嵌摄像机控制面板
     - enabled 开关：控制是否启用摄像机参数
     - 预设选择器模式：从预设库快速加载
     - 手动参数模式：直接调整各摄像参数
     - 嵌入画布节点内容区使用
     ===================================================== -->

<template>
  <div class="canvas-camera-panel">
    <!-- 启用开关 -->
    <div class="panel-toggle">
      <div class="toggle-label">
        <el-icon><VideoCamera /></el-icon>
        <span>{{ t('canvasCamera.title') }}</span>
      </div>
      <el-switch v-model="enabled" size="small" @change="onToggle" />
    </div>

    <!-- 面板内容（仅在启用时显示） -->
    <div v-if="enabled" class="panel-body">
      <!-- 模式切换 -->
      <div class="mode-switch">
        <el-radio-group v-model="mode" size="small" @change="onModeChange">
          <el-radio-button value="preset">{{ t('canvasCamera.presetMode') }}</el-radio-button>
          <el-radio-button value="manual">{{ t('canvasCamera.manualMode') }}</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 预设模式 -->
      <div v-if="mode === 'preset'" class="preset-section">
        <CameraPresetSelector
          v-model="selectedPresetId"
          :placeholder="t('canvasCamera.selectPreset')"
          @select="onPresetSelect"
        />
      </div>

      <!-- 手动模式：紧凑参数输入 -->
      <div v-else class="manual-section">
        <div class="param-grid">
          <div class="param-item">
            <label>{{ t('cameraPresets.formCameraModel') }}</label>
            <el-input
              v-model="params.camera_model"
              size="small"
              :placeholder="t('cameraPresets.formCameraModelPlaceholder')"
            />
          </div>
          <div class="param-item">
            <label>{{ t('cameraPresets.formFocalLength') }}</label>
            <el-input
              v-model="params.focal_length"
              size="small"
              :placeholder="t('cameraPresets.formFocalLengthPlaceholder')"
            />
          </div>
          <div class="param-item">
            <label>{{ t('cameraPresets.formAperture') }}</label>
            <el-input
              v-model="params.aperture"
              size="small"
              :placeholder="t('cameraPresets.formAperturePlaceholder')"
            />
          </div>
          <div class="param-item">
            <label>{{ t('cameraPresets.formDepthOfField') }}</label>
            <el-select v-model="params.depth_of_field" size="small" clearable style="width: 100%">
              <el-option :label="t('cameraPresets.dofShallow')" value="浅景深" />
              <el-option :label="t('cameraPresets.dofDeep')" value="深景深" />
              <el-option :label="t('cameraPresets.dofMedium')" value="中等景深" />
            </el-select>
          </div>
          <div class="param-item">
            <label>{{ t('cameraPresets.formShutterSpeed') }}</label>
            <el-input
              v-model="params.shutter_speed"
              size="small"
              :placeholder="t('cameraPresets.formShutterSpeedPlaceholder')"
            />
          </div>
          <div class="param-item">
            <label>{{ t('cameraPresets.formShutterAngle') }}</label>
            <el-input
              v-model="params.shutter_angle"
              size="small"
              :placeholder="t('cameraPresets.formShutterAnglePlaceholder')"
            />
          </div>
          <div class="param-item">
            <label>{{ t('cameraPresets.formCameraMovement') }}</label>
            <el-select v-model="params.camera_movement" size="small" clearable style="width: 100%">
              <el-option :label="t('cameraPresets.movStatic')" value="固定机位" />
              <el-option :label="t('cameraPresets.movHandheld')" value="手持运镜" />
              <el-option :label="t('cameraPresets.movDolly')" value="推拉运镜" />
              <el-option :label="t('cameraPresets.movPan')" value="摇摄" />
              <el-option :label="t('cameraPresets.movTracking')" value="跟拍" />
              <el-option :label="t('cameraPresets.movAerial')" value="航拍" />
              <el-option :label="t('cameraPresets.movSteadicam')" value="稳定器" />
            </el-select>
          </div>
          <div class="param-item">
            <label>{{ t('cameraPresets.formCameraAngle') }}</label>
            <el-select v-model="params.camera_angle" size="small" clearable style="width: 100%">
              <el-option :label="t('cameraPresets.angleEyeLevel')" value="平视" />
              <el-option :label="t('cameraPresets.angleLow')" value="低角度仰拍" />
              <el-option :label="t('cameraPresets.angleHigh')" value="高角度俯拍" />
              <el-option :label="t('cameraPresets.angleDutch')" value="倾斜构图" />
              <el-option :label="t('cameraPresets.angleOverhead')" value="顶视" />
            </el-select>
          </div>
          <div class="param-item">
            <label>{{ t('cameraPresets.formAspectRatio') }}</label>
            <el-select v-model="params.aspect_ratio" size="small" clearable style="width: 100%">
              <el-option label="16:9" value="16:9" />
              <el-option label="2.35:1" value="2.35:1" />
              <el-option label="1:1" value="1:1" />
              <el-option label="4:3" value="4:3" />
              <el-option label="3:2" value="3:2" />
              <el-option label="9:16" value="9:16" />
            </el-select>
          </div>
          <div class="param-item">
            <label>{{ t('cameraPresets.formVisualStyle') }}</label>
            <el-input
              v-model="params.visual_style"
              size="small"
              :placeholder="t('cameraPresets.formVisualStylePlaceholder')"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * CanvasCameraPanel — 画布节点内嵌摄像机控制面板
 *
 * 暴露 cameraParams 对象给父组件（画布节点），
 * 结构：{ enabled: boolean, ...10 个摄像参数 }
 */
import { reactive, ref, watch } from 'vue'
import { VideoCamera } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import CameraPresetSelector from '@/components/CameraPresetSelector.vue'

const { t } = useI18n()

const props = defineProps<{
  /** 外部传入的摄像机参数对象（可选双向绑定） */
  modelValue?: {
    enabled?: boolean
    camera_model?: string
    focal_length?: string
    aperture?: string
    depth_of_field?: string
    shutter_speed?: string
    shutter_angle?: string
    camera_movement?: string
    camera_angle?: string
    aspect_ratio?: string
    visual_style?: string
  } | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, any>]
}>()

const enabled = ref(props.modelValue?.enabled ?? false)
const mode = ref<'preset' | 'manual'>('preset')
const selectedPresetId = ref<number | null>(null)

const params = reactive({
  camera_model: props.modelValue?.camera_model || '',
  focal_length: props.modelValue?.focal_length || '',
  aperture: props.modelValue?.aperture || '',
  depth_of_field: props.modelValue?.depth_of_field || '',
  shutter_speed: props.modelValue?.shutter_speed || '',
  shutter_angle: props.modelValue?.shutter_angle || '',
  camera_movement: props.modelValue?.camera_movement || '',
  camera_angle: props.modelValue?.camera_angle || '',
  aspect_ratio: props.modelValue?.aspect_ratio || '',
  visual_style: props.modelValue?.visual_style || '',
})

function buildOutput() {
  return {
    enabled: enabled.value,
    ...params,
  }
}

function emitUpdate() {
  emit('update:modelValue', buildOutput())
}

function onToggle() {
  emitUpdate()
}

function onModeChange() {
  // 模式切换时清空之前来源的参数
  if (mode.value === 'preset') {
    // 切换到预设模式，保留手动填入的参数作为默认值（不清空）
  }
  emitUpdate()
}

function onPresetSelect(presetParams: Record<string, string | undefined>) {
  // 将预设参数填入手动参数对象
  params.camera_model = presetParams.camera_model || ''
  params.focal_length = presetParams.focal_length || ''
  params.aperture = presetParams.aperture || ''
  params.depth_of_field = presetParams.depth_of_field || ''
  params.shutter_speed = presetParams.shutter_speed || ''
  params.shutter_angle = presetParams.shutter_angle || ''
  params.camera_movement = presetParams.camera_movement || ''
  params.camera_angle = presetParams.camera_angle || ''
  params.aspect_ratio = presetParams.aspect_ratio || ''
  params.visual_style = presetParams.visual_style || ''
  emitUpdate()
}

// 手动模式下参数变更时发出事件
watch(params, () => {
  if (mode.value === 'manual') {
    emitUpdate()
  }
}, { deep: true })

// 外部 modelValue 输入同步
watch(() => props.modelValue, (val) => {
  if (!val) return
  enabled.value = val.enabled ?? enabled.value
  if (val.camera_model !== undefined) params.camera_model = val.camera_model || ''
  if (val.focal_length !== undefined) params.focal_length = val.focal_length || ''
  if (val.aperture !== undefined) params.aperture = val.aperture || ''
  if (val.depth_of_field !== undefined) params.depth_of_field = val.depth_of_field || ''
  if (val.shutter_speed !== undefined) params.shutter_speed = val.shutter_speed || ''
  if (val.shutter_angle !== undefined) params.shutter_angle = val.shutter_angle || ''
  if (val.camera_movement !== undefined) params.camera_movement = val.camera_movement || ''
  if (val.camera_angle !== undefined) params.camera_angle = val.camera_angle || ''
  if (val.aspect_ratio !== undefined) params.aspect_ratio = val.aspect_ratio || ''
  if (val.visual_style !== undefined) params.visual_style = val.visual_style || ''
})
</script>

<style scoped>
.canvas-camera-panel {
  padding: 8px;
  background: var(--agnes-bg-input);
  border-radius: 8px;
  font-size: 12px;
}

.panel-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--agnes-text-secondary);
  font-weight: 500;
  font-size: 13px;
}

.panel-body {
  margin-top: 10px;
  padding-top: 10px;
  /* 修复：原 rgba(107, 126, 156, 0.15) 硬编码，改用项目 CSS 变量 */
  border-top: 1px solid var(--agnes-border-faint);
}

.mode-switch {
  margin-bottom: 10px;
}

.preset-section {
  margin-bottom: 4px;
}

.manual-section {
  margin-top: 4px;
}

.param-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.param-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.param-item label {
  font-size: 11px;
  color: var(--agnes-text-tertiary);
}
</style>
