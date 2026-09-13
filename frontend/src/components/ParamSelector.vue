<!-- =====================================================
     ParamSelector：紧凑参数选择器
     将分辨率/比例/时长/帧率/模型等参数压缩为一行标签，
     点击标签弹出 Popover 修改，页面更简洁。

     用法：
       <ParamSelector mode="image" v-model:size="size" v-model:model="model" />
       <ParamSelector mode="video" v-model:aspectRatio="ar" v-model:seconds="sec"
                      v-model:frameRate="fps" v-model:model="model" />
     ===================================================== -->

<template>
  <div class="param-selector">
    <!-- 尺寸/比例标签 -->
    <el-popover
      v-model:visible="sizePopoverVisible"
      placement="bottom-start"
      :width="popoverWidth"
      trigger="click"
    >
      <template #reference>
        <span class="param-tag" :title="sizeTagTitle">
          <!-- 图片模式：清晰度等级小圆点 -->
          <span
            v-if="mode === 'image' && currentTierColor"
            class="param-tag__tier-dot"
            :style="{ background: currentTierColor }"
          ></span>
          <span class="param-tag__icon">
            <span class="param-tag__shape" :class="{ 'param-tag__shape--auto': currentSize === 'auto' }" :style="currentShapeStyle"></span>
          </span>
          <span class="param-tag__text">{{ currentSizeLabel }}</span>
          <!-- 图片模式：实际像素数 -->
          <span v-if="mode === 'image' && currentPixels" class="param-tag__pixels">{{ formatPixels(currentPixels) }}</span>
          <el-icon class="param-tag__arrow"><ArrowDown /></el-icon>
        </span>
      </template>
      <RatioPicker
        v-model="currentSize"
        :mode="sizeMode"
        :auto="enableAuto"
        :video-aspect-ratios="config.videoAspectRatios"
        :video-resolutions="config.videoResolutions"
        :resolution="currentResolution"
        :resolved-size="resolvedSize"
        :resolved-ratio="resolvedAspectRatio"
        :resolved-resolution="resolvedResolution"
        @update:resolution="currentResolution = $event"
      />
    </el-popover>

    <!-- 时长标签（视频模式） -->
    <el-popover
      v-if="mode === 'video'"
      v-model:visible="durationPopoverVisible"
      placement="bottom-start"
      :width="200"
      trigger="click"
    >
      <template #reference>
        <span class="param-tag">
          <el-icon><VideoCamera /></el-icon>
          <span class="param-tag__text">{{ currentSeconds }}s</span>
          <el-icon class="param-tag__arrow"><ArrowDown /></el-icon>
        </span>
      </template>
      <div class="param-btn-group">
        <button
          v-for="sec in availableDurations"
          :key="sec"
          type="button"
          class="param-btn"
          :class="{ 'param-btn--active': currentSeconds === sec }"
          @click="currentSeconds = sec; durationPopoverVisible = false"
        >{{ sec }}s</button>
      </div>
    </el-popover>

    <!-- 分辨率已并入「尺寸」标签的统一面板（RatioPicker） -->

    <!-- 帧率标签（视频模式） -->
    <el-popover
      v-if="mode === 'video'"
      v-model:visible="fpsPopoverVisible"
      placement="bottom-start"
      :width="160"
      trigger="click"
    >
      <template #reference>
        <span class="param-tag">
          <el-icon><Film /></el-icon>
          <span class="param-tag__text">{{ currentFrameRate }}fps</span>
          <el-icon class="param-tag__arrow"><ArrowDown /></el-icon>
        </span>
      </template>
      <div class="param-btn-group">
        <button
          v-for="fps in frameRateOptions"
          :key="fps"
          type="button"
          class="param-btn"
          :class="{ 'param-btn--active': currentFrameRate === fps }"
          @click="currentFrameRate = fps; fpsPopoverVisible = false"
        >{{ fps }}fps</button>
      </div>
    </el-popover>

    <!-- 模型标签 -->
    <el-popover
      v-model:visible="modelPopoverVisible"
      placement="bottom-start"
      :width="260"
      trigger="click"
    >
      <template #reference>
        <span class="param-tag">
          <svg class="param-tag__icon-cpu" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M15 9H9v6h6V9zm-2 4h-2v-2h2v2zm8-2V9h-2V7c0-1.1-.9-2-2-2h-2V3h-2v2h-2V3H9v2H7c-1.1 0-2 .9-2 2v2H3v2h2v2H3v2h2v2c0 1.1.9 2 2 2h2v2h2v-2h2v2h2v-2h2c1.1 0 2-.9 2-2v-2h2v-2h-2v-2h2zm-4 6H7V7h10v10z"/></svg>
          <span class="param-tag__text">{{ currentModelLabel }}</span>
          <el-icon class="param-tag__arrow"><ArrowDown /></el-icon>
        </span>
      </template>
      <div class="param-model-popover">
        <!-- Provider 标签页切换 -->
        <div v-if="modelGroups.length > 1" class="param-model-tabs">
          <button
            v-for="group in modelGroups"
            :key="group.provider"
            type="button"
            class="param-model-tab"
            :class="{ 'param-model-tab--active': selectedProvider === group.provider }"
            @click="selectedProvider = group.provider"
          >{{ group.provider }}</button>
        </div>
        <!-- 当前 Provider 的模型列表 -->
        <div class="param-model-list">
          <div
            v-for="m in filteredModels"
            :key="m.id"
            class="param-model-item"
            :class="{ 'param-model-item--active': currentModel === m.id }"
            @click="currentModel = m.id; modelPopoverVisible = false"
          >
            <span class="param-model-item__name">{{ m.name }}</span>
            <span v-if="m.capabilities.length" class="param-model-item__badge">{{ m.capabilities[0] }}</span>
          </div>
        </div>
      </div>
    </el-popover>
  </div>
</template>

<script setup lang="ts">
/**
 * ParamSelector 组件 - 紧凑参数选择器
 * 功能：图片/视频生成参数选择，支持自定义尺寸/分辨率
 */
import { ref, computed, watch } from 'vue'
import { ArrowDown, VideoCamera, Film } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import RatioPicker from '@/components/RatioPicker.vue'
import { useModelsStore } from '@/stores/models'
import {
  getImageSizeLabel,
  getTierBySize,
  formatPixels,
  IMAGE_TIER_CONFIG,
} from '@/config/model-params'
import type { ModelInfo } from '@/types'

const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    mode: 'image' | 'video'
    /** 图片尺寸，如 "1024x1024"；'auto'=跟随参考图/偏好 */
    size?: string
    /** 视频宽高比，如 "16:9"；'auto'=跟随参考图/偏好 */
    aspectRatio?: string
    /** 视频分辨率档（高度值，如 720）；'auto'=跟随偏好 */
    resolution?: number | 'auto'
    /** 视频时长（秒） */
    seconds?: number
    /** 视频帧率 */
    frameRate?: number
    /** 模型 ID */
    model?: string
    /** 模型列表（外部传入，不传则从 store 获取） */
    modelList?: ModelInfo[]
    /** 是否显示「自动」选项（默认显示；画布等场景显式传 false 关闭） */
    enableAuto?: boolean
    /** 图片自动模式的解析尺寸（标签/面板展示实际生效值） */
    resolvedSize?: string
    /** 视频自动模式的解析比例 / 档位 */
    resolvedAspectRatio?: string
    resolvedResolution?: number
  }>(),
  {
    // 注意：Vue 对未传的可选 boolean prop 会转换为 false（resolvePropValue 缺省转换），
    // 「默认显示」必须用显式默认值表达，不能用 enableAuto !== false 判断
    enableAuto: true,
  },
)

const emit = defineEmits<{
  'update:size': [value: string]
  'update:aspectRatio': [value: string]
  'update:resolution': [value: number | 'auto']
  'update:seconds': [value: number]
  'update:frameRate': [value: number]
  'update:model': [value: string]
}>()

const modelsStore = useModelsStore()

// Popover 显隐
const sizePopoverVisible = ref(false)
const durationPopoverVisible = ref(false)
const fpsPopoverVisible = ref(false)
const modelPopoverVisible = ref(false)

// 当前选中的 Provider（用于 tabs 切换）
const selectedProvider = ref('')

// 尺寸模式：image 用 "image"，video 用 "video"
const sizeMode = computed(() => props.mode === 'video' ? 'video' : 'image')

// 当前值的本地代理（双向绑定）
const currentSize = computed({
  get: () => props.mode === 'video' ? (props.aspectRatio || '16:9') : (props.size || '1024x1024'),
  set: (v) => {
    if (props.mode === 'video') emit('update:aspectRatio', v)
    else emit('update:size', v)
    sizePopoverVisible.value = false
  },
})
const currentSeconds = computed({
  get: () => props.seconds ?? 5,
  set: (v) => emit('update:seconds', v),
})
const currentFrameRate = computed({
  get: () => props.frameRate ?? 24,
  set: (v) => emit('update:frameRate', v),
})
const currentResolution = computed({
  get: () => props.resolution ?? 'auto',
  set: (v) => emit('update:resolution', v),
})
const currentModel = computed({
  get: () => props.model || '',
  set: (v) => emit('update:model', v),
})

// 选项列表：当前模型 gen_params 覆盖尺寸选项/默认尺寸（如 Seedream 只出合法档），缺省用全局配置
const config = computed(() => {
  const base = modelsStore.getModelParamsConfig()
  const gp = modelsStore.getModelGenParams(props.model)
  if (!gp || (!gp.image_sizes?.length && !gp.default_size && !gp.video_durations?.length)) return base
  return {
    ...base,
    imageSizes: gp.image_sizes?.length ? gp.image_sizes : base.imageSizes,
    defaultImageSize: gp.default_size || base.defaultImageSize,
    videoDurations: gp.video_durations?.length ? gp.video_durations : base.videoDurations,
  }
})

// 视频时长（秒）：按 Agnes 官方 Q&A 限制随帧率联动
//   24 FPS → 最多 15s；30 FPS → 最多 10s；60 FPS → 最多 5s
// 返回当前 FPS 允许的最大时长（秒），找不到 fps 档位时不限
function getMaxDurationForFps(fps: number): number {
  if (fps >= 60) return 5
  if (fps >= 30) return 10
  if (fps >= 24) return 15
  return Number.POSITIVE_INFINITY
}

// 当前帧率允许的时长选项
const availableDurations = computed(() => {
  const max = getMaxDurationForFps(currentFrameRate.value || 24)
  return config.value.videoDurations.filter(sec => sec <= max)
})
const frameRateOptions = computed(() => config.value.videoFrameRates)
const modelList = computed(() => props.modelList || (
  props.mode === 'video' ? modelsStore.videoModels : modelsStore.imageModels
))

// 按 Provider 分组的模型列表
const modelGroups = computed(() => {
  const groups: { provider: string; models: ModelInfo[] }[] = []
  const providerMap = new Map<string, ModelInfo[]>()
  for (const m of modelList.value) {
    const p = m.provider || '其他'
    if (!providerMap.has(p)) providerMap.set(p, [])
    providerMap.get(p)!.push(m)
  }
  providerMap.forEach((models, provider) => {
    groups.push({ provider, models })
  })
  return groups
})

// 根据选中的 Provider 过滤模型列表
const filteredModels = computed(() => {
  if (!selectedProvider.value) {
    return modelList.value
  }
  return modelList.value.filter(m => m.provider === selectedProvider.value)
})

// 切换 FPS 时若当前时长超过新 FPS 的上限，自动降到允许的最大值
watch(() => currentFrameRate.value, (fps) => {
  const max = getMaxDurationForFps(fps || 24)
  if (currentSeconds.value > max) {
    // 在 videoDurations 列表中挑一个 ≤ max 的最大值
    const fallback = [...config.value.videoDurations]
      .filter(sec => sec <= max)
      .pop()
    if (fallback !== undefined) {
      currentSeconds.value = fallback
    }
  }
})

// 当前尺寸对应的清晰度等级（图片模式）
const currentTier = computed(() => {
  if (props.mode !== 'image') return null
  const tier = getTierBySize(currentSize.value)
  if (tier) return tier
  // 检查是否是自定义尺寸格式
  if (currentSize.value && currentSize.value.includes('x')) {
    return 'custom' as const
  }
  return null
})

// 当前尺寸对应的实际像素数（图片模式）
const currentPixels = computed(() => {
  if (props.mode !== 'image') return 0
  const opt = config.value.imageSizes.find(o => o.value === currentSize.value)
  if (opt?.pixels) return opt.pixels
  // 自定义尺寸：手动计算
  const dims = parseSizeString(currentSize.value)
  return dims ? dims.w * dims.h : 0
})

/**
 * 解析尺寸字符串 "1024x1024" → {w, h}
 */
function parseSizeString(size: string): { w: number; h: number } | null {
  const m = size.match(/^(\d+)x(\d+)$/i)
  if (!m) return null
  return { w: parseInt(m[1], 10), h: parseInt(m[2], 10) }
}

// 视频「尺寸」的两个维度当前值（auto 用解析值代入）与档位文案
const videoSizeParts = computed(() => {
  const ratioAuto = currentSize.value === 'auto'
  const resAuto = currentResolution.value === 'auto'
  const resValue = resAuto ? props.resolvedResolution : (currentResolution.value as number)
  const ratioValue = ratioAuto ? (props.resolvedAspectRatio || '16:9') : currentSize.value
  const resOpt = config.value.videoResolutions.find(o => o.value === resValue)
  return {
    bothAuto: ratioAuto && resAuto,
    ratioValue,
    full: resOpt ? resOpt.label : `${resValue ?? ''}p`,
    short: resOpt ? resOpt.label.split(' ')[0] : `${resValue ?? ''}p`,
  }
})

// 当前尺寸/比例的友好标签
// 「自动」：跟随参考图（图生）或偏好（文生）
// 图片模式：清晰度等级 + 比例（如"标清 · 1:1"）
// 视频模式：档位 · 比例（如"720p · 16:9"），自动维度用解析值代入
const currentSizeLabel = computed(() => {
  if (props.mode === 'video') {
    const parts = videoSizeParts.value
    return parts.bothAuto ? t('params.autoRatio') : `${parts.short} · ${parts.ratioValue}`
  }
  if (currentSize.value === 'auto') return t('params.autoRatio')
  const tier = currentTier.value
  const sizeLabel = getImageSizeLabel(currentSize.value)
  // 提取比例部分（如 "1:1 方形" → "1:1"）
  const ratioPart = sizeLabel.replace(/\s+.+$/, '')
  if (tier) {
    return `${IMAGE_TIER_CONFIG[tier].label} · ${ratioPart}`
  }
  return ratioPart
})

// 当前模型显示名
const currentModelLabel = computed(() => {
  const m = modelList.value.find(m => m.id === currentModel.value)
  return m?.name || currentModel.value
})

// 尺寸/比例小图标样式：统一用配置中的 w/h 绘制
const currentShapeStyle = computed(() => {
  let w = 16, h = 9
  if (props.mode === 'video') {
    const ratio = currentSize.value === 'auto' ? (props.resolvedAspectRatio || '16:9') : currentSize.value
    const opt = config.value.videoAspectRatios.find(o => o.value === ratio)
    w = opt?.w || 16
    h = opt?.h || 9
  } else {
    const opt = config.value.imageSizes.find(o => o.value === currentSize.value)
    if (opt) {
      w = opt.w
      h = opt.h
    } else {
      // 自定义尺寸：解析宽高比
      const dims = parseSizeString(currentSize.value)
      if (dims) {
        w = dims.w
        h = dims.h
      }
    }
  }
  return {
    aspectRatio: `${w} / ${h}`,
    ...(w >= h
      ? { width: '100%', maxHeight: '100%' }
      : { height: '100%', maxWidth: '100%' }),
  }
})

// 清晰度等级小圆点颜色（图片模式）
const currentTierColor = computed(() => {
  const tier = currentTier.value
  return tier ? IMAGE_TIER_CONFIG[tier].color : ''
})

// 尺寸标签的悬停提示：显示完整信息（清晰度 + 比例 + 像素 + 耗时）
const sizeTagTitle = computed(() => {
  if (props.mode === 'video') {
    const parts = videoSizeParts.value
    return parts.bothAuto ? t('params.autoRatioHint') : `${parts.full} · ${parts.ratioValue}`
  }
  if (currentSize.value === 'auto') return t('params.autoRatioHint')
  const tier = currentTier.value
  if (!tier) return currentSize.value
  const cfg = IMAGE_TIER_CONFIG[tier]
  const px = formatPixels(currentPixels.value)
  return `${cfg.label} · ${cfg.desc}${px ? ' · ' + px : ''}`
})

// Popover 宽度（统一面板两模式同宽）
const popoverWidth = computed(() => 400)
</script>

<style scoped>
.param-selector {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

/* 标签样式 */
.param-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  background: var(--agnes-bg-input);
  border: 1px solid rgba(107, 126, 156, 0.25);
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.15s ease;
  color: var(--agnes-text-secondary);
  font-size: 13px;
  line-height: 1;
  user-select: none;
  white-space: nowrap;
}

.param-tag:hover {
  border-color: var(--agnes-primary);
  background: var(--agnes-bg-hover);
  color: var(--agnes-text-primary);
}

/* 清晰度等级小圆点（图片模式） */
.param-tag__tier-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* 实际像素数标签（图片模式） */
.param-tag__pixels {
  font-size: 10px;
  opacity: 0.6;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  margin-left: 2px;
}

/* 标签内的小比例图标：**正方形容器**，内部图形按比例自然呈现
 * 16:9 → 矮横；1:1 → 正方形；9:16 → 瘦高 */
.param-tag__icon {
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.param-tag__shape {
  display: block;
  border-radius: 2px;
  background: var(--agnes-primary);
}

/* 自动模式：虚线框表示跟随参考图 */
.param-tag__shape--auto {
  background: transparent;
  border: 1.5px dashed var(--agnes-primary);
}

.param-tag__text {
  font-weight: 500;
}

.param-tag__arrow {
  font-size: 10px;
  opacity: 0.5;
  margin-left: 2px;
}

/* 模型标签内的 CPU 图标 */
.param-tag__icon-cpu {
  width: 1em;
  height: 1em;
  flex-shrink: 0;
}

/* 按钮组（时长/帧率） */
.param-btn-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px;
}

.param-btn {
  padding: 6px 14px;
  border: 1px solid rgba(107, 126, 156, 0.25);
  border-radius: 8px;
  background: var(--agnes-bg-input);
  color: var(--agnes-text-secondary);
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
  transition: all 0.15s ease;
}

.param-btn:hover {
  border-color: var(--agnes-primary);
  background: var(--agnes-bg-hover);
  color: var(--agnes-text-primary);
}

.param-btn--active {
  border-color: #8bb0ff;
  background: var(--agnes-info-bg);
  color: #fff;
}

/* 模型选择弹窗容器 */
.param-model-popover {
  display: flex;
  flex-direction: column;
  padding: 4px;
}

/* Provider 标签页切换 */
.param-model-tabs {
  display: flex;
  gap: 4px;
  padding: 4px 4px 8px;
  border-bottom: 1px solid var(--agnes-border);
  margin-bottom: 4px;
}

.param-model-tab {
  padding: 4px 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--agnes-text-secondary);
  cursor: pointer;
  font-size: 12px;
  font-family: inherit;
  transition: all 0.15s ease;
}

.param-model-tab:hover {
  background: var(--agnes-bg-hover);
  color: var(--agnes-text-primary);
}

.param-model-tab--active {
  background: var(--agnes-info-bg);
  color: #fff;
  font-weight: 500;
}

/* 模型列表 */
.param-model-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 240px;
  overflow-y: auto;
}

.param-model-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
  color: var(--agnes-text-secondary);
}

.param-model-item:hover {
  background: var(--agnes-bg-hover);
  color: var(--agnes-text-primary);
}

.param-model-item--active {
  background: var(--agnes-info-bg);
  color: #fff;
}

.param-model-item__name {
  font-size: 13px;
  font-weight: 500;
}

.param-model-item__badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(107, 156, 255, 0.2);
  color: var(--agnes-primary-soft);
  margin-left: 8px;
}
</style>
