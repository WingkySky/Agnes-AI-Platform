<!-- =====================================================
     RatioPicker：图形化比例/尺寸选择器
     - 一排横向小按钮，每个按钮 = 小矩形（按真实比例绘制）+ 下方数字
     - 两种模式：
         mode="image"  → 传出 WxH（如 "1024x1024"）
         mode="video"  → 传出 ratio（如 "16:9"）
     - 图片模式下增加清晰度选择器（标清/超清/4K），
       根据所选清晰度过滤可选比例，并显示实际像素
     - 选项来源优先级：props.options > store 配置 > 本地默认
     ===================================================== -->

<template>
  <div class="ratio-picker">
    <!-- 清晰度选择器（仅图片模式显示） -->
    <div v-if="mode === 'image' && availableTiers.length > 1" class="tier-bar">
      <button
        v-for="tier in availableTiers"
        :key="tier"
        type="button"
        class="tier-btn"
        :class="{ 'tier-btn--active': currentTier === tier }"
        :style="currentTier === tier ? { borderColor: tierConfig(tier).color, color: tierConfig(tier).color } : {}"
        :title="tierConfig(tier).desc"
        @click="selectTier(tier)"
      >
        <span class="tier-btn__dot" :style="{ background: tierConfig(tier).color }"></span>
        <span class="tier-btn__label">{{ tierConfig(tier).label }}</span>
        <span class="tier-btn__desc">{{ tierConfig(tier).desc }}</span>
      </button>
    </div>

    <!-- 比例按钮列表 -->
    <div class="ratio-list">
      <button
        v-for="opt in currentOptions"
        :key="opt.value"
        type="button"
        class="ratio-btn"
        :class="{ 'ratio-btn--active': modelValue === opt.value }"
        :title="optionTooltip(opt)"
        @click="select(opt)"
      >
        <!-- 小方形容器，内部绘制一个按真实宽高比的矩形 -->
        <span class="ratio-btn__icon-box">
          <span class="ratio-btn__icon" :style="shapeStyle(opt)"></span>
        </span>
        <span class="ratio-btn__label">{{ displayLabel(opt) }}</span>
        <span v-if="opt.pixels" class="ratio-btn__pixels">{{ formatPixels(opt.pixels) }}</span>
      </button>

      <!-- 当前清晰度下无可选比例的提示 -->
      <div v-if="currentOptions.length === 0" class="ratio-empty">
        {{ emptyHint }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, type PropType } from 'vue'
import { useModelsStore } from '@/stores/models'
import { useI18n } from '@/i18n'
import {
  IMAGE_TIER_CONFIG,
  getTierBySize,
  formatPixels,
  type ImageTier,
} from '@/config/model-params'

const { t } = useI18n()

// 选项类型定义
interface RatioOption {
  value: string
  w: number
  h: number
  label?: string
  tier?: ImageTier
  pixels?: number
}

const props = defineProps({
  modelValue: { type: String, default: '' },
  // "image" 表示按具体尺寸；"video" 表示按宽高比
  mode: { type: String, default: 'image' },
  // 自定义选项；未传则从 store 获取
  options: { type: Array as PropType<RatioOption[]>, default: null },
})

const emit = defineEmits(['update:modelValue'])

const modelsStore = useModelsStore()

// 当前选中的清晰度等级（图片模式）
const currentTier = ref<ImageTier>('sd')

/**
 * 从 store 配置或本地默认中获取所有图片尺寸选项
 */
const allImageOptions = computed<RatioOption[]>(() => {
  if (props.options && props.options.length) return props.options
  const config = modelsStore.getModelParamsConfig()
  if (config.imageSizes.length > 0) return config.imageSizes
  return DEFAULT_IMAGE_OPTIONS
})

/**
 * 当前可选的清晰度等级列表
 * 仅图片模式且选项中存在 tier 字段时返回
 */
const availableTiers = computed<ImageTier[]>(() => {
  if (props.mode !== 'image') return []
  // 从选项中提取实际存在的 tier
  const tiers = new Set<ImageTier>()
  for (const opt of allImageOptions.value) {
    if (opt.tier) tiers.add(opt.tier)
  }
  return ['sd', 'hd', '4k'].filter(t => tiers.has(t as ImageTier)) as ImageTier[]
})

/**
 * 当前清晰度下的可选比例列表
 * 视频模式直接返回所有视频选项
 */
const currentOptions = computed<RatioOption[]>(() => {
  if (props.mode === 'video') {
    if (props.options && props.options.length) return props.options
    const config = modelsStore.getModelParamsConfig()
    if (config.videoAspectRatios.length > 0) return config.videoAspectRatios
    return DEFAULT_VIDEO_OPTIONS
  }
  // 图片模式：按清晰度过滤
  return allImageOptions.value.filter(o => !o.tier || o.tier === currentTier.value)
})

// 当前清晰度下无可选比例的提示
const emptyHint = computed(() => {
  const cfg = IMAGE_TIER_CONFIG[currentTier.value]
  return `${cfg.label} 暂无可选比例`
})

/**
 * 初始化清晰度：根据当前 modelValue 反推所属 tier
 */
watch(
  () => props.modelValue,
  (val) => {
    if (props.mode !== 'image') return
    const tier = getTierBySize(val)
    if (tier && availableTiers.value.includes(tier)) {
      currentTier.value = tier
    }
  },
  { immediate: true },
)

// 本地兜底默认选项
const DEFAULT_IMAGE_OPTIONS: RatioOption[] = [
  { value: '1024x1024', w: 1,  h: 1,  label: `1:1 ${t('ratio.square')}`,     tier: 'sd', pixels: 1048576 },
  { value: '1312x736',  w: 16, h: 9,  label: `16:9 ${t('ratio.landscape')}`, tier: 'sd', pixels: 965632 },
  { value: '1248x832',  w: 3,  h: 2,  label: `3:2 ${t('ratio.landscape')}`,  tier: 'sd', pixels: 1038336 },
  { value: '832x1248',  w: 2,  h: 3,  label: `2:3 ${t('ratio.portrait')}`,   tier: 'sd', pixels: 1038336 },
  { value: '2048x2048', w: 1,  h: 1,  label: `1:1 ${t('ratio.square')}`,     tier: 'hd', pixels: 4194304 },
  { value: '3840x2160', w: 16, h: 9,  label: `16:9 ${t('ratio.landscape')}`, tier: '4k', pixels: 8294400 },
  { value: '4096x4096', w: 1,  h: 1,  label: `1:1 ${t('ratio.square')}`,     tier: '4k', pixels: 16777216 },
]

const DEFAULT_VIDEO_OPTIONS: RatioOption[] = [
  { value: '16:9', w: 16, h: 9,  label: `16:9 ${t('ratio.landscape')}` },
  { value: '9:16', w: 9,  h: 16, label: `9:16 ${t('ratio.portrait')}` },
  { value: '1:1',  w: 1,  h: 1,  label: `1:1 ${t('ratio.square')}` },
  { value: '4:3',  w: 4,  h: 3,  label: `4:3 ${t('ratio.landscape')}` },
  { value: '3:4',  w: 3,  h: 4,  label: `3:4 ${t('ratio.portrait')}` },
]

/**
 * 清晰度等级配置
 */
function tierConfig(tier: ImageTier) {
  return IMAGE_TIER_CONFIG[tier]
}

/**
 * 切换清晰度等级
 * 如果当前选中的尺寸不在新等级下，自动选中该等级的第一个尺寸
 */
function selectTier(tier: ImageTier) {
  if (currentTier.value === tier) return
  currentTier.value = tier
  // 若当前尺寸不在新等级中，自动切换到该等级的第一个尺寸
  const sizes = allImageOptions.value.filter(o => o.tier === tier)
  if (sizes.length > 0 && !sizes.some(o => o.value === props.modelValue)) {
    emit('update:modelValue', sizes[0].value)
  }
}

/**
 * 计算形状的尺寸：容器是正方形，内部图形按宽高比自然渲染
 */
function shapeStyle(opt: RatioOption) {
  const w = opt.w || 1
  const h = opt.h || 1
  if (w >= h) {
    return { aspectRatio: `${w} / ${h}`, width: '100%' }
  } else {
    return { aspectRatio: `${w} / ${h}`, height: '100%' }
  }
}

/**
 * 显示标签：图片模式优先显示比例（如"16:9"），视频模式直接显示值
 */
function displayLabel(opt: RatioOption): string {
  if (props.mode === 'image' && opt.label) {
    return opt.label.replace(/\s+.+$/, '')
  }
  return opt.value
}

/**
 * 鼠标悬停提示：显示完整标签 + 实际像素
 */
function optionTooltip(opt: RatioOption): string {
  const parts: string[] = []
  if (opt.label) parts.push(opt.label)
  if (opt.pixels) parts.push(formatPixels(opt.pixels))
  return parts.join(' · ')
}

function select(opt: RatioOption) {
  if (props.modelValue !== opt.value) {
    emit('update:modelValue', opt.value)
  }
}
</script>

<style scoped>
.ratio-picker {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 清晰度选择器 */
.tier-bar {
  display: flex;
  gap: 6px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(107, 126, 156, 0.15);
  flex-wrap: wrap;
}

.tier-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  background: var(--agnes-bg-input);
  border: 1px solid rgba(107, 126, 156, 0.22);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.15s ease;
  color: var(--agnes-text-secondary);
  font-size: 12px;
  font-family: inherit;
  line-height: 1;
}

.tier-btn:hover {
  background: var(--agnes-bg-hover);
  color: var(--agnes-text-primary);
}

.tier-btn--active {
  background: var(--agnes-info-bg);
  color: #fff;
}

.tier-btn__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tier-btn__label {
  font-weight: 600;
  letter-spacing: 0.3px;
}

.tier-btn__desc {
  font-size: 10px;
  opacity: 0.7;
  margin-left: 2px;
}

/* 比例按钮列表 */
.ratio-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: flex-start;
}

/* 单个按钮：图标在上，数字在下 */
.ratio-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  gap: 4px;
  padding: 6px 8px 6px;
  min-width: 0;
  background: var(--agnes-bg-input);
  border: 1px solid rgba(107, 126, 156, 0.22);
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
  color: var(--agnes-text-secondary);
  font-family: inherit;
  line-height: 1;
}

.ratio-btn:hover {
  border-color: var(--agnes-primary);
  background: var(--agnes-bg-hover);
  color: var(--agnes-text-primary);
}

.ratio-btn--active {
  border-color: var(--agnes-primary-soft);
  background: var(--agnes-info-bg);
  color: #fff;
}

/* 图标容器：正方形 */
.ratio-btn__icon-box {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
}

.ratio-btn__icon {
  display: block;
  border-radius: 2px;
  background: var(--agnes-border);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
}

.ratio-btn--active .ratio-btn__icon {
  background: linear-gradient(135deg, var(--agnes-primary) 0%, var(--agnes-primary-soft) 100%);
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.25),
    0 1px 3px var(--agnes-primary-border);
}

/* 比例标签 */
.ratio-btn__label {
  font-size: 11px;
  font-weight: 500;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: 0.2px;
  line-height: 1;
  white-space: nowrap;
}

/* 像素数标签 */
.ratio-btn__pixels {
  font-size: 9px;
  opacity: 0.6;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  line-height: 1;
  white-space: nowrap;
}

/* 空提示 */
.ratio-empty {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  padding: 12px;
  opacity: 0.6;
}

/* 响应式：小屏略微缩小 */
@media (max-width: 520px) {
  .ratio-list {
    gap: 4px;
  }
  .ratio-btn {
    padding: 5px 6px 5px;
  }
  .ratio-btn__icon-box {
    width: 24px;
    height: 16px;
  }
  .ratio-btn__label {
    font-size: 10px;
  }
  .tier-btn__desc {
    display: none;
  }
}
</style>
