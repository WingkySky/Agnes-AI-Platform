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
            <span class="param-tag__shape" :style="currentShapeStyle"></span>
          </span>
          <span class="param-tag__text">{{ currentSizeLabel }}</span>
          <!-- 图片模式：实际像素数 -->
          <span v-if="mode === 'image' && currentPixels" class="param-tag__pixels">{{ formatPixels(currentPixels) }}</span>
          <el-icon class="param-tag__arrow"><ArrowDown /></el-icon>
        </span>
      </template>
      <RatioPicker v-model="currentSize" :mode="sizeMode" />
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
          v-for="sec in durationOptions"
          :key="sec"
          type="button"
          class="param-btn"
          :class="{ 'param-btn--active': currentSeconds === sec }"
          @click="currentSeconds = sec; durationPopoverVisible = false"
        >{{ sec }}s</button>
      </div>
    </el-popover>

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
      :width="240"
      trigger="click"
    >
      <template #reference>
        <span class="param-tag">
          <svg class="param-tag__icon-cpu" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M15 9H9v6h6V9zm-2 4h-2v-2h2v2zm8-2V9h-2V7c0-1.1-.9-2-2-2h-2V3h-2v2h-2V3H9v2H7c-1.1 0-2 .9-2 2v2H3v2h2v2H3v2h2v2c0 1.1.9 2 2 2h2v2h2v-2h2v2h2v-2h2c1.1 0 2-.9 2-2v-2h2v-2h-2v-2h2zm-4 6H7V7h10v10z"/></svg>
          <span class="param-tag__text">{{ currentModelLabel }}</span>
          <el-icon class="param-tag__arrow"><ArrowDown /></el-icon>
        </span>
      </template>
      <div class="param-model-list">
        <div
          v-for="m in modelList"
          :key="m.id"
          class="param-model-item"
          :class="{ 'param-model-item--active': currentModel === m.id }"
          @click="currentModel = m.id; modelPopoverVisible = false"
        >
          <span class="param-model-item__name">{{ m.name }}</span>
          <span v-if="m.provider" class="param-model-item__provider">{{ m.provider }}</span>
        </div>
      </div>
    </el-popover>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ArrowDown, VideoCamera, Film } from '@element-plus/icons-vue'
import RatioPicker from '@/components/RatioPicker.vue'
import { useModelsStore } from '@/stores/models'
import {
  getImageSizeLabel,
  getVideoAspectRatioLabel,
  getTierBySize,
  formatPixels,
  IMAGE_TIER_CONFIG,
} from '@/config/model-params'
import type { ModelInfo } from '@/types'

const props = defineProps<{
  mode: 'image' | 'video'
  /** 图片尺寸，如 "1024x1024" */
  size?: string
  /** 视频宽高比，如 "16:9" */
  aspectRatio?: string
  /** 视频时长（秒） */
  seconds?: number
  /** 视频帧率 */
  frameRate?: number
  /** 模型 ID */
  model?: string
  /** 模型列表（外部传入，不传则从 store 获取） */
  modelList?: ModelInfo[]
}>()

const emit = defineEmits<{
  'update:size': [value: string]
  'update:aspectRatio': [value: string]
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
const currentModel = computed({
  get: () => props.model || '',
  set: (v) => emit('update:model', v),
})

// 选项列表
const config = computed(() => modelsStore.getModelParamsConfig())
const durationOptions = computed(() => config.value.videoDurations)
const frameRateOptions = computed(() => config.value.videoFrameRates)
const modelList = computed(() => props.modelList || (
  props.mode === 'video' ? modelsStore.videoModels : modelsStore.imageModels
))

// 当前尺寸对应的清晰度等级（图片模式）
const currentTier = computed(() => {
  if (props.mode !== 'image') return null
  return getTierBySize(currentSize.value) || null
})

// 当前尺寸对应的实际像素数（图片模式）
const currentPixels = computed(() => {
  if (props.mode !== 'image') return 0
  const opt = config.value.imageSizes.find(o => o.value === currentSize.value)
  return opt?.pixels || 0
})

// 当前尺寸/比例的友好标签
// 图片模式：清晰度等级 + 比例（如"标清 · 1:1"）
// 视频模式：直接显示比例（如"16:9 横屏"）
const currentSizeLabel = computed(() => {
  if (props.mode === 'video') {
    return getVideoAspectRatioLabel(currentSize.value)
  }
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
    const opt = config.value.videoAspectRatios.find(o => o.value === currentSize.value)
    w = opt?.w || 16
    h = opt?.h || 9
  } else {
    const opt = config.value.imageSizes.find(o => o.value === currentSize.value)
    w = opt?.w || 16
    h = opt?.h || 9
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
    return getVideoAspectRatioLabel(currentSize.value)
  }
  const tier = currentTier.value
  if (!tier) return currentSize.value
  const cfg = IMAGE_TIER_CONFIG[tier]
  const px = formatPixels(currentPixels.value)
  return `${cfg.label} · ${cfg.desc}${px ? ' · ' + px : ''}`
})

// Popover 宽度
const popoverWidth = computed(() => props.mode === 'video' ? 320 : 400)
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

/* 模型列表 */
.param-model-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px;
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

.param-model-item__provider {
  font-size: 11px;
  opacity: 0.5;
  margin-left: 8px;
}
</style>
