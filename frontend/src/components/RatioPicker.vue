<template>
  <div class="ratio-picker">
    <!-- 自动适配：图生跟随参考图比例 / 文生跟随偏好比例，档位取偏好档 -->
    <div v-if="showAuto" class="auto-row">
      <button
        class="auto-btn"
        :class="{ active: isAuto }"
        :title="t('params.autoRatioHint')"
        @click="selectAuto"
      >
        <el-icon><MagicStick /></el-icon>
        <span>{{ t('params.autoRatio') }}</span>
      </button>
    </div>

    <!-- 档位 tab：图片=清晰度档（sd/hd/4k）· 视频=分辨率档（480p~4K） -->
    <div class="tier-tabs">
      <button
        v-for="tab in tierTabs"
        :key="tab.value"
        class="tier-tab"
        :class="{ 'tier-tab--active': currentTabValue === tab.value }"
        :style="tab.dot ? { '--tier-color': tab.dot } : {}"
        @click="selectTab(tab)"
      >
        <span v-if="tab.dot" class="tier-dot" :style="{ background: tab.dot }"></span>
        {{ tab.label }}
      </button>
    </div>

    <!-- 比例分组：横/方/竖（两模式同构；自定义档下隐藏） -->
    <div v-if="!isCustomActive" class="ratio-group-list">
      <div v-for="group in ratioGroups" :key="group.label" class="ratio-group">
        <div class="group-label">{{ group.label }}</div>
        <div class="ratio-btns">
          <button
            v-for="opt in group.options"
            :key="opt.value"
            class="ratio-btn"
            :class="{ active: modelValue === opt.value, square: opt.w === opt.h }"
            @click="selectRatio(opt)"
          >
            <div
              class="ratio-box"
              :class="{ square: opt.w === opt.h }"
              :style="opt.w === opt.h ? {} : getBoxStyle(opt.w, opt.h)"
            ></div>
            <span class="ratio-text">{{ opt.w }}:{{ opt.h }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- 选中信息 + 自定义入口 -->
    <div v-if="!isCustomActive" class="size-info">
      <span>{{ infoText }}</span>
      <button class="custom-btn" @click="enterCustom">
        {{ t('image.customInput') }}
      </button>
    </div>

    <!-- 图片自定义：宽高输入（16 对齐） -->
    <div v-else-if="!isVideo" class="custom-size-input">
      <div class="input-row">
        <div class="input-item">
          <label>{{ t('image.width') }}</label>
          <el-input-number
            v-model="customWidth"
            :min="CUSTOM_IMAGE_SIZE.minWidth"
            :max="CUSTOM_IMAGE_SIZE.maxWidth"
            :step="16"
            controls-position="right"
            @change="applyCustomSize"
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
            @change="applyCustomSize"
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
          <button class="back-btn" @click="exitCustom">{{ t('image.usePreset') }}</button>
        </div>
      </div>
    </div>

    <!-- 视频自定义：高度输入（8 对齐，宽度按当前比例实时计算） -->
    <div v-else class="custom-size-input">
      <div class="input-row">
        <div class="input-item">
          <label>{{ t('video.height') }}</label>
          <el-input-number
            v-model="customVideoHeight"
            :min="CUSTOM_VIDEO_SIZE.minHeight"
            :max="CUSTOM_VIDEO_SIZE.maxHeight"
            :step="8"
            controls-position="right"
            @change="applyCustomVideo"
          />
        </div>
        <span class="times-sign">×</span>
        <div class="input-item">
          <label>{{ t('image.width') }}</label>
          <span class="computed-width">{{ calculatedVideoWidth }}</span>
        </div>
      </div>
      <div class="custom-info">
        <span v-if="customVideoValid" class="info-ok">
          {{ calculatedVideoWidth }}×{{ alignedVideoHeight }} · {{ videoCustomMp }}MP
        </span>
        <span v-else class="info-error">
          {{ t('video.resolutionRange', { min: CUSTOM_VIDEO_SIZE.minHeight, max: CUSTOM_VIDEO_SIZE.maxHeight }) }}
        </span>
        <div class="custom-actions">
          <span class="align-tip">{{ t('video.alignTo8') }}</span>
          <button class="back-btn" @click="exitCustom">{{ t('video.usePresetResolution') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * RatioPicker 组件 - 统一比例/档位选择面板
 * 图片模式与视频模式同构：自动按钮 + 档位 tab + 比例分组（横/方/竖）+ 选中信息 + 自定义
 * - 图片：档位=清晰度（sd/hd/4k），选中值=具体尺寸 "WxH" 或 'auto'
 * - 视频：档位=分辨率高度（480~2160），比例与档位为两个独立值（可分别处于自动/手动）
 */
import { computed, ref, watch } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import {
  type ImageSizeOption,
  type ImageTier,
  type VideoAspectRatioOption,
  type VideoResolutionOption,
  getSizesByTier,
  getAvailableTiers,
  getModelParams,
  matchSizeByRatio,
  formatPixels,
  IMAGE_TIER_CONFIG,
  CUSTOM_IMAGE_SIZE,
  CUSTOM_VIDEO_SIZE,
  alignToMultiple,
  validateCustomImageSize,
  validateCustomVideoSize,
  calculateVideoWidth,
  estimateImageCredits,
  sizeToDimensions,
  AUTO_RATIO_VALUE as AUTO,
} from '@/config/model-params'

const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    /** 图片=尺寸 "WxH" | 'auto'；视频=比例 "16:9" | 'auto' */
    modelValue: string
    mode?: 'image' | 'video'
    tier?: 'sd' | 'hd' | '4k'
    videoAspectRatios?: VideoAspectRatioOption[]
    videoResolutions?: VideoResolutionOption[]
    /** 视频当前档位（高度值 | 'auto'） */
    resolution?: number | 'auto'
    /** 是否显示「自动」选项（默认显示） */
    auto?: boolean
    /** 图片自动模式的解析尺寸（信息行展示实际生效值） */
    resolvedSize?: string
    /** 视频自动模式的解析比例 / 档位（信息行展示实际生效值） */
    resolvedRatio?: string
    resolvedResolution?: number
  }>(),
  {
    // Vue 会把未传的可选 boolean prop 转成 false，默认显示必须显式声明默认值
    auto: true,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:resolution': [value: number | 'auto']
}>()

const isVideo = computed(() => props.mode === 'video')
const showAuto = computed(() => props.auto !== false)
// 「自动」完全生效：图片=size 为 auto；视频=比例与档位都为 auto
const isAuto = computed(() =>
  isVideo.value
    ? props.modelValue === AUTO && props.resolution === 'auto'
    : props.modelValue === AUTO,
)

// ========== 图片模式状态 ==========
const availableTiers = computed<ImageTier[]>(() => {
  const tiers = getAvailableTiers()
  if (!tiers.includes('custom')) tiers.push('custom')
  return tiers
})

const currentTier = ref<ImageTier>(props.tier || 'sd')

const tierOptions = computed<ImageSizeOption[]>(() =>
  getSizesByTier(currentTier.value as Exclude<ImageTier, 'custom'>),
)

// ========== 视频模式状态 ==========
const isCustomVideo = ref(false)
const customVideoHeight = ref(720)

/** 视频比例的生效值（auto 用解析值代入，供宽度计算与信息行展示） */
const effectiveRatio = computed(
  () => (props.modelValue === AUTO ? props.resolvedRatio || '16:9' : props.modelValue) || '16:9',
)

const alignedVideoHeight = computed(() =>
  alignToMultiple(customVideoHeight.value, CUSTOM_VIDEO_SIZE.align),
)
const calculatedVideoWidth = computed(() =>
  calculateVideoWidth(effectiveRatio.value, alignedVideoHeight.value),
)
const customVideoValid = computed(
  () => validateCustomVideoSize(calculatedVideoWidth.value, alignedVideoHeight.value).valid,
)
const videoCustomMp = computed(() =>
  ((calculatedVideoWidth.value * alignedVideoHeight.value) / 1e6).toFixed(2),
)

// ========== 档位 tab（两模式同构） ==========
interface TabOption {
  value: string | number
  label: string
  dot?: string
}

const tierTabs = computed<TabOption[]>(() => {
  if (isVideo.value) {
    const tabs: TabOption[] = (props.videoResolutions || []).map(r => ({
      value: r.value,
      label: r.label.split(' ')[0],
    }))
    tabs.push({ value: 'custom', label: t('image.custom'), dot: IMAGE_TIER_CONFIG.custom.color })
    return tabs
  }
  return availableTiers.value.map(tier => ({
    value: tier,
    label: tier === 'custom' ? t('image.custom') : IMAGE_TIER_CONFIG[tier].label,
    dot: tier === 'custom' ? undefined : IMAGE_TIER_CONFIG[tier].color,
  }))
})

const currentTabValue = computed(() => {
  if (isVideo.value) return isCustomVideo.value ? 'custom' : props.resolution
  return currentTier.value
})

const isCustomActive = computed(() =>
  isVideo.value ? isCustomVideo.value : currentTier.value === 'custom',
)

// ========== 比例分组（两模式同构，选项均为 {value,w,h}） ==========
interface RatioOption {
  value: string
  w: number
  h: number
}

const ratioOptions = computed<RatioOption[]>(() =>
  isVideo.value ? (props.videoAspectRatios || []) : tierOptions.value,
)

const ratioGroups = computed(() => [
  { label: t('image.landscape'), options: ratioOptions.value.filter(o => o.w > o.h) },
  { label: t('image.square'), options: ratioOptions.value.filter(o => o.w === o.h) },
  { label: t('image.portrait'), options: ratioOptions.value.filter(o => o.w < o.h) },
])

// ========== 选中信息行（永远显示解析后的实际生效组合） ==========
const infoText = computed(() => {
  if (isVideo.value) {
    const res = props.resolution === AUTO ? props.resolvedResolution : props.resolution
    const ratio = props.modelValue === AUTO ? effectiveRatio.value : props.modelValue
    if (!res) return t('params.autoRatio')
    const resOpt = (props.videoResolutions || []).find(o => o.value === res)
    const width = calculateVideoWidth(ratio, res)
    return `${resOpt ? resOpt.label : `${width}×${res}`} · ${ratio} · ${width}×${res}`
  }
  const base = props.modelValue === AUTO ? props.resolvedSize : props.modelValue
  if (!base) return t('params.autoRatio')
  const opt = getModelParams().imageSizes.find(o => o.value === base)
  if (opt) return `${opt.label} · ${opt.value} · ${formatPixels(opt.pixels)}`
  const dims = sizeToDimensions(base)
  return dims ? `${base} · ${formatPixels(dims.w * dims.h)}` : base
})

// ========== 交互 ==========
function selectAuto() {
  if (isVideo.value) {
    isCustomVideo.value = false
    emit('update:resolution', 'auto')
  } else {
    currentTier.value = 'sd'
  }
  emit('update:modelValue', AUTO)
}

function selectTab(tab: TabOption) {
  if (tab.value === 'custom') {
    enterCustom()
    return
  }
  if (isVideo.value) {
    isCustomVideo.value = false
    emit('update:resolution', tab.value as number)
    return
  }
  // 图片切档：保持当前比例（auto 用解析比例），在新档内取最接近的尺寸
  currentTier.value = tab.value as ImageTier
  const base = props.modelValue === AUTO ? props.resolvedSize || '' : props.modelValue
  const dims = base ? sizeToDimensions(base) : null
  const value = dims
    ? matchSizeByRatio(`${dims.w}:${dims.h}`, currentTier.value)
    : getSizesByTier(currentTier.value as Exclude<ImageTier, 'custom'>)[0]?.value
  if (value) emit('update:modelValue', value)
}

function selectRatio(opt: RatioOption) {
  emit('update:modelValue', opt.value)
}

function enterCustom() {
  if (isVideo.value) {
    enterCustomVideo()
  } else {
    enterCustomMode()
  }
}

function exitCustom() {
  if (isVideo.value) {
    isCustomVideo.value = false
    const first = props.videoResolutions?.[0]?.value
    if (first !== undefined) emit('update:resolution', first)
  } else {
    currentTier.value = 'sd'
    const firstOpt = getSizesByTier('sd')[0]
    if (firstOpt) emit('update:modelValue', firstOpt.value)
  }
}

// ========== 图片自定义尺寸 ==========
const customWidth = ref(1024)
const customHeight = ref(1024)
const alignedWidth = computed(() => alignToMultiple(customWidth.value, CUSTOM_IMAGE_SIZE.align))
const alignedHeight = computed(() => alignToMultiple(customHeight.value, CUSTOM_IMAGE_SIZE.align))
const customValidation = computed(() => validateCustomImageSize(customWidth.value, customHeight.value))
const customPixels = computed(() => alignedWidth.value * alignedHeight.value)
const estimateCredits = computed(() => estimateImageCredits(customPixels.value))

function enterCustomMode() {
  // 用当前生效尺寸（auto 用解析尺寸）初始化输入
  const base = props.modelValue === AUTO ? props.resolvedSize || '' : props.modelValue
  if (base && base.includes('x')) {
    const [w, h] = base.split('x').map(Number)
    customWidth.value = w || 1024
    customHeight.value = h || 1024
  }
  currentTier.value = 'custom'
  applyCustomSize()
}

function applyCustomSize() {
  if (!customValidation.value.valid) return
  emit('update:modelValue', `${alignedWidth.value}x${alignedHeight.value}`)
}

// ========== 视频自定义高度 ==========
function enterCustomVideo() {
  const base = props.resolution === 'auto' ? props.resolvedResolution : props.resolution
  customVideoHeight.value = base || 720
  isCustomVideo.value = true
  applyCustomVideo()
}

function applyCustomVideo() {
  if (!customVideoValid.value) return
  emit('update:resolution', alignedVideoHeight.value)
}

// ========== 外部值同步 ==========
// 图片：外部值变化时同步清晰度档（预设→对应档；自定义格式→custom）
watch(() => props.modelValue, (newVal) => {
  if (isVideo.value) return
  const allPresets = [...getSizesByTier('sd'), ...getSizesByTier('hd'), ...getSizesByTier('4k')]
  const preset = allPresets.find(o => o.value === newVal)
  if (preset && preset.tier) {
    currentTier.value = preset.tier
  } else if (newVal && newVal.includes('x')) {
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

// 视频：外部档位变回预设值时退出自定义态
watch(() => props.resolution, (val) => {
  if (val === 'auto') {
    isCustomVideo.value = false
    return
  }
  if (val !== undefined && (props.videoResolutions || []).some(o => o.value === val)) {
    isCustomVideo.value = false
  }
})

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
</script>

<style scoped>
.ratio-picker {
  width: 100%;
}

/* 自动适配按钮 */
.auto-row {
  margin-bottom: 10px;
}

.auto-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px dashed rgba(107, 126, 156, 0.4);
  border-radius: 8px;
  background: var(--agnes-bg-input);
  color: var(--agnes-text-secondary);
  cursor: pointer;
  font-size: 12px;
  font-family: inherit;
  transition: all 0.15s ease;
}

.auto-btn:hover {
  border-color: var(--agnes-primary);
  color: var(--agnes-primary);
}

.auto-btn.active {
  border-style: solid;
  border-color: var(--agnes-primary);
  background: var(--agnes-info-bg);
  color: #fff;
  font-weight: 500;
}

.auto-icon,
.auto-btn .el-icon {
  font-size: 13px;
}

/* 清晰度/分辨率档标签页 */
.tier-tabs {
  display: flex;
  flex-wrap: wrap;
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
  gap: 8px;
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
  white-space: nowrap;
}

.custom-btn:hover {
  border-color: var(--agnes-primary);
  color: var(--agnes-primary);
}

/* 自定义输入 */
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

.computed-width {
  font-size: 14px;
  font-weight: 500;
  color: var(--agnes-text-primary);
  text-align: center;
  padding-bottom: 6px;
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
