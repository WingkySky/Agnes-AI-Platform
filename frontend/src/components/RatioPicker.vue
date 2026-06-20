<!-- =====================================================
     RatioPicker：图形化比例/尺寸选择器
     - 一排横向小按钮，每个按钮 = 小矩形（按真实比例绘制）+ 下方数字
     - 两种模式：
         mode="image"  → 传出 WxH（如 "1280x720"）
         mode="video"  → 传出 ratio（如 "16:9"）
     - 选项来源优先级：props.options > store 配置 > 本地默认
     ===================================================== -->

<template>
  <div class="ratio-picker">
    <button
      v-for="opt in currentOptions"
      :key="opt.value"
      type="button"
      class="ratio-btn"
      :class="{ 'ratio-btn--active': modelValue === opt.value }"
      :title="opt.label || opt.value"
      @click="select(opt)"
    >
      <!-- 小方形容器，内部绘制一个按真实宽高比的矩形 -->
      <span class="ratio-btn__icon-box">
        <span class="ratio-btn__icon" :style="shapeStyle(opt)"></span>
      </span>
      <span class="ratio-btn__label">{{ displayLabel(opt) }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, type PropType } from 'vue'
import { useModelsStore } from '@/stores/models'

// 选项类型定义
interface RatioOption {
  value: string
  w: number
  h: number
  label?: string
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

/**
 * 当前使用的选项列表
 * 优先级：props.options > store 配置 > 本地兜底
 */
const currentOptions = computed(() => {
  // 1. 优先使用传入的自定义选项
  if (props.options && props.options.length) return props.options

  // 2. 从 store 获取后端配置
  const config = modelsStore.getModelParamsConfig()
  if (props.mode === 'video') {
    const storeOpts = config.videoAspectRatios
    if (storeOpts.length > 0) return storeOpts
  } else {
    const storeOpts = config.imageSizes
    if (storeOpts.length > 0) return storeOpts
  }

  // 3. 兜底：本地默认选项
  return props.mode === 'video' ? DEFAULT_VIDEO_OPTIONS : DEFAULT_IMAGE_OPTIONS
})

// 本地兜底默认选项
const DEFAULT_IMAGE_OPTIONS: RatioOption[] = [
  { value: '1280x720',  w: 16, h: 9,  label: '16:9 横屏' },
  { value: '1536x1024', w: 3,  h: 2,  label: '3:2 横屏' },
  { value: '1024x1024', w: 1,  h: 1,  label: '1:1 方形' },
  { value: '1024x1536', w: 2,  h: 3,  label: '2:3 竖屏' },
  { value: '720x1280',  w: 9,  h: 16, label: '9:16 竖屏' },
  { value: '1792x1024', w: 7,  h: 4,  label: '7:4 宽幅' },
  { value: '1024x1792', w: 4,  h: 7,  label: '4:7 窄幅' },
  { value: '1024x768',  w: 4,  h: 3,  label: '4:3 横屏' },
]

const DEFAULT_VIDEO_OPTIONS: RatioOption[] = [
  { value: '16:9', w: 16, h: 9,  label: '16:9 横屏' },
  { value: '9:16', w: 9,  h: 16, label: '9:16 竖屏' },
  { value: '1:1',  w: 1,  h: 1,  label: '1:1 方形' },
  { value: '4:3',  w: 4,  h: 3,  label: '4:3 横屏' },
  { value: '3:4',  w: 3,  h: 4,  label: '3:4 竖屏' },
]

/**
 * 计算形状的尺寸：在固定容器内，按真实比例渲染
 */
function shapeStyle(opt: RatioOption) {
  const w = opt.w || 1
  const h = opt.h || 1
  return {
    aspectRatio: `${w} / ${h}`,
    ...(w >= h
      ? { width: '92%', maxHeight: '70%' }
      : { height: '92%', maxWidth: '70%' }),
  }
}

/**
 * 显示标签：图片模式优先显示比例（如"16:9"），视频模式直接显示值
 */
function displayLabel(opt: RatioOption): string {
  if (props.mode === 'image' && opt.label) {
    // 图片模式：从 label 提取比例部分，如 "16:9 横屏" → "16:9"
    return opt.label.replace(/\s+.+$/, '')
  }
  return opt.value
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
  flex-wrap: wrap;
  gap: 6px;
  align-items: flex-start;
}

/* 单个按钮：图标在上，数字在下，整体极小 */
.ratio-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  gap: 4px;
  padding: 6px 8px 6px;
  min-width: 0;
  background: rgba(18, 27, 50, 0.5);
  border: 1px solid rgba(107, 126, 156, 0.22);
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
  color: #a0b4d6;
  font-family: inherit;
  line-height: 1;
}

.ratio-btn:hover {
  border-color: rgba(139, 176, 255, 0.5);
  background: rgba(26, 40, 72, 0.7);
  color: #d5e3f7;
}

.ratio-btn--active {
  border-color: #8bb0ff;
  background: rgba(107, 156, 255, 0.14);
  color: #fff;
}

/* 图标容器：固定小方块，内部绘制真实比例矩形 */
.ratio-btn__icon-box {
  width: 28px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
}

.ratio-btn__icon {
  display: block;
  border-radius: 2px;
  background: rgba(150, 170, 210, 0.55);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
}

.ratio-btn--active .ratio-btn__icon {
  background: linear-gradient(135deg, #7fa6ff 0%, #a8c1ff 100%);
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.25),
    0 1px 3px rgba(107, 156, 255, 0.4);
}

/* 数字标签：超小字体，等宽 */
.ratio-btn__label {
  font-size: 11px;
  font-weight: 500;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: 0.2px;
  line-height: 1;
  white-space: nowrap;
}

/* 响应式：小屏略微缩小 */
@media (max-width: 520px) {
  .ratio-picker {
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
}
</style>
