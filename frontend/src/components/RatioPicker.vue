<!-- =====================================================
     RatioPicker：图形化比例/尺寸选择器（复刻官方紧凑版）
     - 一排横向小按钮，每个按钮 = 小矩形（按真实比例绘制）+ 下方数字
     - 无多余中文，整体超紧凑
     - 两种模式：
         mode="image"  → 传出 WxH（如 "1280x720"）
         mode="video"  → 传出 ratio（如 "16:9"）
     ===================================================== -->

<template>
  <div class="ratio-picker">
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      class="ratio-btn"
      :class="{ 'ratio-btn--active': modelValue === opt.value }"
      :title="opt.value"
      @click="select(opt)"
    >
      <!-- 小方形容器，内部绘制一个按真实宽高比的矩形 -->
      <span class="ratio-btn__icon-box">
        <span class="ratio-btn__icon" :style="shapeStyle(opt)"></span>
      </span>
      <span class="ratio-btn__label">{{ opt.value }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, type PropType } from 'vue'

// 选项类型定义
interface RatioOption {
  value: string
  w: number
  h: number
}

const props = defineProps({
  modelValue: { type: String, default: '' },
  // "image" 表示按具体尺寸；"video" 表示按宽高比
  mode: { type: String, default: 'image' },
  // 自定义选项；未传则用默认集
  options: { type: Array as PropType<RatioOption[]>, default: null },
})

const emit = defineEmits(['update:modelValue'])

/**
 * 默认选项（全符合 Agnes 文档的允许规格）
 */
const DEFAULT_IMAGE_OPTIONS = [
  { value: '1280x720',  w: 16, h: 9  },
  { value: '1536x1024', w: 3,  h: 2  },
  { value: '1024x1024', w: 1,  h: 1  },
  { value: '1024x1536', w: 2,  h: 3  },
  { value: '720x1280',  w: 9,  h: 16 },
  { value: '1792x1024', w: 7,  h: 4  },
  { value: '1024x1792', w: 4,  h: 7  },
  { value: '1024x768',  w: 4,  h: 3  },
]

const DEFAULT_VIDEO_OPTIONS = [
  { value: '16:9', w: 16, h: 9  },
  { value: '9:16', w: 9,  h: 16 },
  { value: '1:1',  w: 1,  h: 1  },
  { value: '4:3',  w: 4,  h: 3  },
  { value: '3:4',  w: 3,  h: 4  },
]

const options = computed(() => {
  if (props.options && props.options.length) return props.options
  return props.mode === 'video' ? DEFAULT_VIDEO_OPTIONS : DEFAULT_IMAGE_OPTIONS
})

/**
 * 计算形状的尺寸：在固定容器内，按真实比例渲染
 * - 用 aspect-ratio 保证真实比例
 * - 横向（w >= h）时按最大宽度限制，纵向时按最大高度限制
 */
function shapeStyle(opt: RatioOption) {
  const w = opt.w || 1
  const h = opt.h || 1
  return {
    aspectRatio: `${w} / ${h}`,
    // 让 shape 按最长边撑满容器的 70~90%，保证比例正确且不溢出
    ...(w >= h
      ? { width: '92%', maxHeight: '70%' }
      : { height: '92%', maxWidth: '70%' }),
  }
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

/* ============== 单个按钮：图标在上，数字在下，整体极小 ============== */
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

/* ============== 图标容器：固定小方块，内部绘制真实比例矩形 ============== */
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

/* ============== 数字标签：超小字体，等宽 ============== */
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
