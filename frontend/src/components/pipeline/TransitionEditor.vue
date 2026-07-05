<!--
  TransitionEditor —— 转场配置编辑器组件
  - Dialog 形式弹出，配置相邻场景片段之间的 xfade 转场
  - 转场类型下拉：14 种 xfade 类型（fade/wipeleft/...）
  - 时长滑块：100-3000ms，步进 100，默认 500
  - 支持"移除转场"操作（回退为 hard cut 硬切）
  - 与后端 transition_compose 步骤的 input_data.transitions[i] 结构对齐：{type, duration_ms}
-->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="480px"
    append-to-body
    destroy-on-close
    @update:model-value="onVisibleChange"
  >
    <el-form label-width="100px" size="small">
      <!-- 转场类型选择 -->
      <el-form-item :label="t('pipeline.transition.typeLabel')">
        <el-select
          v-model="localType"
          :placeholder="t('pipeline.transition.typePlaceholder')"
          style="width: 100%"
          @change="onTypeChange"
        >
          <el-option
            v-for="opt in transitionTypeOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>

      <!-- 转场时长滑块 -->
      <el-form-item :label="t('pipeline.transition.durationLabel')">
        <div class="duration-row">
          <el-slider
            v-model="localDuration"
            :min="MIN_DURATION_MS"
            :max="MAX_DURATION_MS"
            :step="DURATION_STEP"
            show-input
            :format-tooltip="formatTooltip"
            class="duration-slider"
          />
          <span class="duration-unit">{{ t('pipeline.transition.ms') }}</span>
        </div>
      </el-form-item>

      <!-- 提示信息：未配置时为 hard cut -->
      <p v-if="!localType" class="hint-text">
        {{ t('pipeline.transition.hardCutHint') }}
      </p>
    </el-form>

    <template #footer>
      <div class="footer-actions">
        <!-- 移除转场按钮（仅当前已有配置时可用） -->
        <el-button
          v-if="hasTransition"
          type="danger"
          plain
          :icon="Delete"
          @click="handleRemove"
        >
          {{ t('pipeline.transition.remove') }}
        </el-button>
        <div class="footer-right">
          <el-button @click="onCancel">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" @click="onConfirm">
            {{ t('common.confirm') }}
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElDialog, ElForm, ElFormItem, ElSelect, ElOption, ElSlider, ElButton } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'

/** 转场配置结构（与后端 transition_compose.steps[].transitions[] 对齐） */
interface TransitionConfig {
  type: string
  duration_ms: number
}

// ================ 转场类型常量 ================
// 14 种 FFmpeg xfade 转场类型，与后端 _SUPPORTED_XFADE_TYPES 对齐
const TRANSITION_TYPES = [
  'fade',
  'wipeleft',
  'wiperight',
  'wipeup',
  'wipedown',
  'slideleft',
  'slideright',
  'slideup',
  'slidedown',
  'circleopen',
  'circleclose',
  'dissolve',
  'pixelize',
  'radialsmooth',
] as const

// 时长范围与步进（与后端 _MIN/_MAX/_DEFAULT_DURATION_MS 对齐）
const MIN_DURATION_MS = 100
const MAX_DURATION_MS = 3000
const DURATION_STEP = 100
const DEFAULT_DURATION_MS = 500

const props = defineProps<{
  /** Dialog 可见性（v-model） */
  modelValue: boolean
  /** 当前转场配置（null 表示未配置，回退为 hard cut） */
  transition: TransitionConfig | null
  /** 当前编辑的是第几个转场（用于标题展示） */
  index: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'update:transition', value: TransitionConfig | null): void
  (e: 'remove'): void
}>()

const { t } = useI18n()

// ================ 内部编辑状态 ================
// 深拷贝 props.transition，避免直接修改父组件状态
const localType = ref<string>('')
const localDuration = ref<number>(DEFAULT_DURATION_MS)

// 同步 props.transition 到内部状态（每次 Dialog 打开时刷新）
watch(
  () => [props.modelValue, props.transition],
  ([visible, trans]) => {
    if (visible) {
      if (trans && typeof trans === 'object') {
        localType.value = trans.type || ''
        localDuration.value = clampDuration(trans.duration_ms)
      } else {
        // 未配置：默认值
        localType.value = 'fade'
        localDuration.value = DEFAULT_DURATION_MS
      }
    }
  },
  { immediate: true }
)

// ================ 计算属性 ================

// 当前是否已有转场配置（用于显示"移除"按钮）
const hasTransition = computed(() => !!props.transition)

// Dialog 标题：包含转场序号
const dialogTitle = computed(() =>
  t('pipeline.transition.dialogTitle', { n: props.index + 1 })
)

// 转场类型下拉选项（含中文名）
const transitionTypeOptions = computed(() =>
  TRANSITION_TYPES.map(type => ({
    value: type,
    label: t(`pipeline.transition.types.${type}`),
  }))
)

// ================ 工具函数 ================

// clamp 时长到合法范围
function clampDuration(ms: number): number {
  const v = Math.round(ms / DURATION_STEP) * DURATION_STEP
  return Math.max(MIN_DURATION_MS, Math.min(MAX_DURATION_MS, v))
}

// 滑块 tooltip 格式化
function formatTooltip(val: number): string {
  return `${val} ${t('pipeline.transition.ms')}`
}

// ================ 事件处理 ================

// 可见性变更（v-model 同步）
function onVisibleChange(val: boolean) {
  emit('update:modelValue', val)
}

// 类型变更：同步到时长默认值（保持当前时长不变，仅触发响应式）
function onTypeChange(_val: string) {
  // 类型变更不影响时长，无需特殊处理
}

// 取消按钮
function onCancel() {
  emit('update:modelValue', false)
}

// 确认按钮：emit 配置并关闭
function onConfirm() {
  const transition: TransitionConfig = {
    type: localType.value || 'fade',
    duration_ms: clampDuration(localDuration.value),
  }
  emit('update:transition', transition)
  emit('update:modelValue', false)
}

// 移除转场：emit null 并关闭
function handleRemove() {
  emit('update:transition', null)
  emit('remove')
  emit('update:modelValue', false)
}
</script>

<style scoped>
/* 时长滑块行 */
.duration-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.duration-slider {
  flex: 1;
}
.duration-unit {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  white-space: nowrap;
}

/* 提示信息 */
.hint-text {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--agnes-text-muted);
}

/* 底部操作区 */
.footer-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
.footer-right {
  display: flex;
  gap: 8px;
}
</style>
