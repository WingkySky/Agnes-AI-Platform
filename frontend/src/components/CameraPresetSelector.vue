<!-- =====================================================
     CameraPresetSelector — 可复用的摄像机预设下拉选择器
     - 异步加载预设列表，支持搜索过滤
     - 选中后回传 camera_params 对象（名称 + 10 个参数）
     ===================================================== -->

<template>
  <div class="camera-preset-selector">
    <el-select
      v-model="selectedPresetId"
      :placeholder="placeholder"
      :disabled="disabled"
      :loading="loading"
      filterable
      clearable
      style="width: 100%"
      @change="onChange"
      @focus="onFocus"
    >
      <el-option
        v-for="item in presets"
        :key="item.id"
        :label="item.name"
        :value="item.id"
      >
        <div class="preset-option">
          <span class="preset-option__name">{{ item.name }}</span>
          <span class="preset-option__meta">
            <el-tag size="small" effect="plain">{{ item.category || '—' }}</el-tag>
            <span v-if="item.is_public" class="meta-public">{{ t('cameraPresets.public') }}</span>
          </span>
        </div>
      </el-option>
      <template #empty>
        <div class="empty-dropdown">
          <span>{{ t('cameraPresets.noPresets') }}</span>
        </div>
      </template>
    </el-select>
  </div>
</template>

<script setup lang="ts">
/**
 * CameraPresetSelector — 预设选择器组件
 *
 * Selected 事件传出 CameraParams 对象：
 * { name, camera_model, focal_length, aperture, depth_of_field,
 *   shutter_speed, shutter_angle, camera_movement, camera_angle,
 *   aspect_ratio, visual_style }
 */
import { ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import { getCameraPresets, type CameraPreset } from '@/api/cameraPresets'

const { t } = useI18n()

const props = defineProps<{
  /** 占位文本 */
  placeholder?: string
  /** 是否禁用 */
  disabled?: boolean
  /** 外部受控 preset_id（可选） */
  modelValue?: number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: number | null]
  /** 选中预设时，传出完整的摄像机参数 */
  select: [params: Record<string, string | undefined>]
}>()

const presets = ref<CameraPreset[]>([])
const loading = ref(false)
const selectedPresetId = ref<number | null>(props.modelValue ?? null)
const hasLoaded = ref(false)

const placeholder = computed(() => props.placeholder || t('cameraPresets.selectPreset'))

watch(() => props.modelValue, (val) => {
  selectedPresetId.value = val ?? null
})

function onFocus() {
  if (!hasLoaded.value) {
    loadPresets()
  }
}

async function loadPresets() {
  loading.value = true
  try {
    // 加载所有预设（后端支持列表，前端做本地搜索过滤）
    const res = await getCameraPresets({ page_size: 200 })
    presets.value = res.items
    hasLoaded.value = true
  } catch (_) {
    // 错误已统一处理
  } finally {
    loading.value = false
  }
}

function onChange(val: number | null) {
  emit('update:modelValue', val)
  if (val) {
    const preset = presets.value.find(p => p.id === val)
    if (preset) {
      emit('select', {
        name: preset.name,
        camera_model: preset.camera_model,
        focal_length: preset.focal_length,
        aperture: preset.aperture,
        depth_of_field: preset.depth_of_field,
        shutter_speed: preset.shutter_speed,
        shutter_angle: preset.shutter_angle,
        camera_movement: preset.camera_movement,
        camera_angle: preset.camera_angle,
        aspect_ratio: preset.aspect_ratio,
        visual_style: preset.visual_style,
      })
    }
  } else {
    emit('select', {})
  }
}

import { computed } from 'vue'
</script>

<style scoped>
.camera-preset-selector {
  width: 100%;
}

.preset-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.preset-option__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preset-option__meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 12px;
  flex-shrink: 0;
}

.meta-public {
  font-size: 11px;
  color: var(--agnes-text-tertiary);
}

.empty-dropdown {
  padding: 12px;
  text-align: center;
  color: var(--agnes-text-tertiary);
  font-size: 13px;
}
</style>
