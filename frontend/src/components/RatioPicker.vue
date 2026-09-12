<template>
  <div class="ratio-picker">
    <!-- ========== 图片模式：清晰度分组的尺寸选择 ========== -->
    <template v-if="mode === 'image'">
      <!-- 清晰度等级标签页 -->
      <div class="tier-tabs">
        <button
          v-for="tier in availableTiers"
          :key="tier"
          class="tier-tab"
          :class="{ 'tier-tab--active': currentTier === tier }"
          :style="tier !== 'custom' ? { '--tier-color': IMAGE_TIER_CONFIG[tier].color } : {}"
          @click="switchTier(tier)"
        >
          <span
            v-if="tier !== 'custom'"
            class="tier-dot"
            :style="{ background: IMAGE_TIER_CONFIG[tier].color }"
          ></span>
          {{ tier !== 'custom' ? IMAGE_TIER_CONFIG[tier].label : t('image.custom') }}
        </button>
      </div>

      <!-- 预设尺寸：按横/方/竖分组 -->
      <template v-if="currentTier !== 'custom'">
        <div class="ratio-group-list">
          <!-- 横屏比例组（w > h） -->
          <div class="ratio-group landscape-group">
            <div class="group-label">{{ t('image.landscape') }}</div>
            <div class="ratio-btns">
              <button
                v-for="opt in landscapeOptions"
                :key="opt.value"
                class="ratio-btn"
                :class="{ active: modelValue === opt.value }"
                @click="selectPreset(opt)"
                :title="`${opt.label} · ${opt.value}`"
              >
                <div class="ratio-box" :style="getBoxStyle(opt.w, opt.h)"></div>
                <span class="ratio-text">{{ opt.w}}:{{ opt.h }}</span>
              </button>
            </div>
          </div>

          <!-- 方形比例组（w = h） -->
          <div class="ratio-group square-group">
            <div class="group-label">{{ t('image.square') }}</div>
            <div class="ratio-btns">
              <button
                v-for="opt in squareOptions"
                :key="opt.value"
                class="ratio-btn square"
                :class="{ active: modelValue === opt.value }"
                @click="selectPreset(opt)"
                :title="`${opt.label} · ${opt.value}`"
              >
                <div class="ratio-box square"></div>
                <span class="ratio-text">1:1</span>
              </button>
            </div>
          </div>

          <!-- 竖屏比例组（w < h） -->
          <div class="ratio-group portrait-group">
            <div class="group-label">{{ t('image.portrait') }}</div>
            <div class="ratio-btns">
              <button
                v-for="opt in portraitOptions"
                :key="opt.value"
                class="ratio-btn"
                :class="{ active: modelValue === opt.value }"
                @click="selectPreset(opt)"
                :title="`${opt.label} · ${opt.value}`"
              >
                <div class="ratio-box" :style="getBoxStyle(opt.w, opt.h)"></div>
                <span class="ratio-text">{{ opt.w}}:{{ opt.h }}</span>
              </button>
            </div>
          </div>
        </div>

        <!-- 选中尺寸信息 + 自定义按钮 -->
        <div class="size-info">
          <span v-if="currentOption">
            {{ currentOption.label }} · {{ currentOption.value }} · {{ formatPixels(currentOption.pixels) }}
          </span>
          <button class="custom-btn" @click="enterCustomMode">
            {{ t('image.customInput') }}
          </button>
        </div>
      </template>

      <!-- 自定义尺寸输入区域 -->
      <div v-else class="custom-size-input">
        <div class="input-row">
          <div class="input-item">
            <label>{{ t('image.width') }}</label>
            <el-input-number
              v-model="customWidth"
              :min="CUSTOM_IMAGE_SIZE.minWidth"
              :max="CUSTOM_IMAGE_SIZE.maxWidth"
              :step="16"
              controls-position="right"
              @change="onCustomSizeChange"
            />
          </div>
          <span class="times-sign">×</span>
          <div class="input-item">
            <label>{{ t('image.height') }}</label>
            <el-input-number
              v-model="customHeight"
              :min="CUSTOM_IMAGE_SIZE.minHeight"
              :max="CUSTOM_IMAGE_SIZE.maxHeight"
              :step="16"
              controls-position="right"
              @change="onCustomSizeChange"
            />
          </div>
        </div>
        <div class="custom-info">
          <span v-if="customValidation.valid" class="info-ok">
            {{ alignedWidth }}×{{ alignedHeight }} · {{ formatPixels(customPixels) }} · ~{{ estimateCredits }} {{ t('common.credits') }}
          </span>
          <span v-else class="info-error">
            {{ customValidation.message }}
          </span>
          <div class="custom-actions">
            <span class="align-tip">{{ t('image.alignTo16') }}</span>
            <button class="back-btn" @click="exitCustomMode">{{ t('image.usePreset') }}</button>
          </div>
        </div>
      </div>
    </template>

    <!-- ========== 视频模式：宽高比选择 ========== -->
    <template v-else>
      <div class="ratio-group-list">
        <div
          v-for="opt in videoAspectRatios"
          :key="opt.value"
          class="ratio-group"
        >
          <button
            class="ratio-btn video-ratio-btn"
            :class="{ active: modelValue === opt.value }"
            @click="emit('update:modelValue', opt.value)"
          >
            <div class="ratio-box" :style="getBoxStyle(opt.w, opt.h)"></div>
            <span class="ratio-text">{{ opt.label }}</span>
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * RatioPicker 组件 - 图片尺寸/视频比例选择器
 * 功能：
 * - 图片模式：清晰度标签页 + 分组比例选择 + 自定义宽高输入
 * - 视频模式：宽高比按钮选择
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import {
  type ImageSizeOption,
  type ImageTier,
  type VideoAspectRatioOption,
  getSizesByTier,
  getAvailableTiers,
  formatPixels,
  IMAGE_TIER_CONFIG,
  CUSTOM_IMAGE_SIZE,
  alignToMultiple,
  validateCustomImageSize,
  estimateImageCredits,
} from '@/config/model-params'

const { t } = useI18n()

const props = defineProps<{
  modelValue: string
  mode?: 'image' | 'video'
  tier?: 'sd' | 'hd' | '4k'
  videoAspectRatios?: VideoAspectRatioOption[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

// ========== 图片模式状态 ==========
const availableTiers = computed<ImageTier[]>(() => {
  // 返回包含 custom 的等级列表
  const tiers = getAvailableTiers()
  if (!tiers.includes('custom')) tiers.push('custom')
  return tiers
})

// 当前选中的清晰度等级
const currentTier = ref<ImageTier>(props.tier || 'sd')

// 当前等级的尺寸选项
const tierOptions = computed<ImageSizeOption[]>(() => getSizesByTier(currentTier.value as Exclude<ImageTier, 'custom'>))

// 按比例方向分组
const landscapeOptions = computed(() => tierOptions.value.filter(o => o.w > o.h))
const squareOptions = computed(() => tierOptions.value.filter(o => o.w === o.h))
const portraitOptions = computed(() => tierOptions.value.filter(o => o.w < o.h))

// 当前选中的预设选项
const currentOption = computed(() => tierOptions.value.find(o => o.value === props.modelValue))

// ========== 自定义尺寸状态 ==========
const customWidth = ref(1024)
const customHeight = ref(1024)

// 对齐后的宽高
const alignedWidth = computed(() => alignToMultiple(customWidth.value, CUSTOM_IMAGE_SIZE.align))
const alignedHeight = computed(() => alignToMultiple(customHeight.value, CUSTOM_IMAGE_SIZE.align))

// 校验结果
const customValidation = computed(() => validateCustomImageSize(customWidth.value, customHeight.value))

// 像素数
const customPixels = computed(() => alignedWidth.value * alignedHeight.value)

// 估算积分
const estimateCredits = computed(() => estimateImageCredits(customPixels.value))

/**
 * 切换清晰度等级
 */
function switchTier(tier: ImageTier) {
  if (tier === 'custom') {
    enterCustomMode()
    return
  }
  currentTier.value = tier
  // 切换到新等级时，默认选第一个尺寸
  const firstOpt = getSizesByTier(tier)[0]
  if (firstOpt) emit('update:modelValue', firstOpt.value)
}

/**
 * 选择预设尺寸
 */
function selectPreset(opt: ImageSizeOption) {
  emit('update:modelValue', opt.value)
}

/**
 * 进入自定义模式
 */
function enterCustomMode() {
  // 用当前选中尺寸初始化输入
  const allSizes = [...getSizesByTier('sd'), ...getSizesByTier('hd'), ...getSizesByTier('4k')]
  const current = allSizes.find(o => o.value === props.modelValue)
  if (current) {
    const [w, h] = current.value.split('x').map(Number)
    customWidth.value = w || 1024
    customHeight.value = h || 1024
  } else if (props.modelValue && props.modelValue.includes('x')) {
    const [w, h] = props.modelValue.split('x').map(Number)
    customWidth.value = w || 1024
    customHeight.value = h || 1024
  }
  currentTier.value = 'custom'
  applyCustomSize()
}

/**
 * 退出自定义模式，回到预设
 */
function exitCustomMode() {
  currentTier.value = 'sd'
  const firstOpt = getSizesByTier('sd')[0]
  if (firstOpt) emit('update:modelValue', firstOpt.value)
}

/**
 * 自定义尺寸变化时应用
 */
function onCustomSizeChange() {
  applyCustomSize()
}

/**
 * 应用自定义尺寸
 */
function applyCustomSize() {
  if (!customValidation.value.valid) return
  const customValue = `${alignedWidth.value}x${alignedHeight.value}`
  emit('update:modelValue', customValue)
}

/**
 * 计算比例预览框样式
 */
function getBoxStyle(w: number, h: number) {
  const maxSide = 24
  const ratio = w / h
  let width: number, height: number
  if (ratio > 1) {
    width = maxSide
    height = maxSide / ratio
  } else {
    height = maxSide
    width = maxSide * ratio
  }
  return { width: `${width}px`, height: `${height}px` }
}

// 监听外部值变化，同步状态
watch(() => props.modelValue, (newVal) => {
  if (props.mode === 'video') return
  // 检查是否是预设尺寸
  const allPresets = [...getSizesByTier('sd'), ...getSizesByTier('hd'), ...getSizesByTier('4k')]
  const preset = allPresets.find(o => o.value === newVal)
  if (preset && preset.tier) {
    currentTier.value = preset.tier
  } else if (newVal && newVal.includes('x') && props.mode === 'image') {
    // 自定义尺寸格式
    currentTier.value = 'custom'
    const [w, h] = newVal.split('x').map(Number)
    if (w) customWidth.value = w
    if (h) customHeight.value = h
  }
}, { immediate: true })

watch(() => props.tier, (newTier) => {
  if (newTier && currentTier.value !== 'custom') {
    currentTier.value = newTier
  }
})
</script>

<style scoped>
.ratio-picker {
  width: 100%;
}

/* 清晰度标签页 */
.tier-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(107, 126, 156, 0.15);
}

.tier-tab {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border: 1px solid rgba(107, 126, 156, 0.25);
  border-radius: 12px;
  background: var(--agnes-bg-input);
  color: var(--agnes-text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.tier-tab:hover {
  border-color: var(--agnes-primary);
  color: var(--agnes-primary);
}

.tier-tab--active {
  border-color: var(--tier-color, var(--agnes-primary));
  background: color-mix(in srgb, var(--tier-color, var(--agnes-primary)) 12%, transparent);
  color: var(--tier-color, var(--agnes-primary));
  font-weight: 500;
}

.tier-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

/* 比例分组 */
.ratio-group-list {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.ratio-group {
  flex: 1;
}

.group-label {
  font-size: 11px;
  color: var(--agnes-text-tertiary);
  margin-bottom: 6px;
  text-align: center;
}

.ratio-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
}

.ratio-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 8px 10px;
  border: 1px solid rgba(107, 126, 156, 0.25);
  border-radius: 8px;
  background: var(--agnes-bg-input);
  cursor: pointer;
  transition: all 0.15s ease;
  min-width: 52px;
  color: var(--agnes-text-secondary);
  font-family: inherit;
}

.ratio-btn:hover {
  border-color: var(--agnes-primary);
  background: var(--agnes-bg-hover);
  color: var(--agnes-text-primary);
}

.ratio-btn.active {
  border-color: var(--agnes-primary);
  background: var(--agnes-info-bg);
  color: #fff;
}

.ratio-btn.video-ratio-btn {
  min-width: auto;
  padding: 10px 14px;
}

.ratio-box {
  border: 1.5px solid currentColor;
  border-radius: 2px;
  opacity: 0.9;
}

.ratio-box.square {
  width: 20px;
  height: 20px;
}

.ratio-text {
  font-size: 11px;
  font-weight: 500;
}

/* 选中信息 */
.size-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--agnes-text-secondary);
  padding: 8px 12px;
  background: var(--agnes-bg-hover);
  border-radius: 6px;
}

.custom-btn {
  padding: 3px 10px;
  font-size: 11px;
  border: 1px solid rgba(107, 126, 156, 0.3);
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  color: var(--agnes-text-secondary);
  transition: all 0.15s ease;
  font-family: inherit;
}

.custom-btn:hover {
  border-color: var(--agnes-primary);
  color: var(--agnes-primary);
}

/* 自定义尺寸输入 */
.custom-size-input {
  background: color-mix(in srgb, #e6a23c 8%, transparent);
  border: 1px solid color-mix(in srgb, #e6a23c 30%, transparent);
  border-radius: 8px;
  padding: 12px;
}

.input-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  justify-content: center;
  margin-bottom: 10px;
}

.input-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.input-item label {
  font-size: 11px;
  color: var(--agnes-text-tertiary);
  text-align: center;
}

.times-sign {
  font-size: 18px;
  font-weight: bold;
  color: #e6a23c;
  padding-bottom: 8px;
}

.custom-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.info-ok {
  color: #67c23a;
  font-weight: 500;
}

.info-error {
  color: #f56c6c;
}

.custom-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
}

.align-tip {
  color: var(--agnes-text-tertiary);
  font-size: 11px;
}

.back-btn {
  padding: 3px 10px;
  font-size: 11px;
  border: 1px solid rgba(107, 126, 156, 0.3);
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  color: var(--agnes-text-secondary);
  font-family: inherit;
  transition: all 0.15s ease;
}

.back-btn:hover {
  border-color: var(--agnes-primary);
  color: var(--agnes-primary);
}
</style>
