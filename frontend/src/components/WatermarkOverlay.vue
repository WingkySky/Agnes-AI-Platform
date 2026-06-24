<!--
  =====================================================
  图片水印覆盖层组件
  - 在图片上叠加 CSS 水印（文字或图片）
  - 水印配置从 models store 获取
  - 用法：<WatermarkOverlay><img src="..." /></WatermarkOverlay>
  =====================================================
-->

<template>
  <div class="watermark-overlay" :class="[`wm-position-${wmConfig?.position || 'bottom-right'}`]">
    <slot></slot>
    <!-- 文字水印 -->
    <div
      v-if="shouldShow && wmConfig?.type === 'text'"
      class="wm-text"
      :style="textStyle"
    >
      {{ wmConfig.text }}
    </div>
    <!-- 图片水印 -->
    <img
      v-else-if="shouldShow && wmConfig?.type === 'image' && wmConfig.image_url"
      class="wm-image"
      :src="wmConfig.image_url"
      :style="imageStyle"
      alt="watermark"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useModelsStore } from '@/stores/models'
import { useUserStore } from '@/stores/user'

const modelsStore = useModelsStore()
const userStore = useUserStore()

/** 是否应该显示水印 */
const shouldShow = computed(() => {
  const wm = modelsStore.watermark
  // 全局强制开启
  if (wm?.enabled) return true
  // 用户自己开启了水印
  if (userStore.user?.watermark_enabled) return true
  return false
})

/** 水印配置（全局配置 + 用户级兜底默认值） */
const wmConfig = computed(() => {
  if (modelsStore.watermark) return modelsStore.watermark
  // 用户开了水印但没拿到全局配置时，给个默认配置
  if (userStore.user?.watermark_enabled) {
    return {
      type: 'text' as const,
      text: userStore.user.username || '',
      font_size: 16,
      color: '#ffffff',
      opacity: 60,
      position: 'bottom-right',
      margin: 20,
      image_url: '',
      image_width: 100,
    }
  }
  return null
})

/** 文字水印样式 */
const textStyle = computed(() => {
  const wm = wmConfig.value
  if (!wm) return {}
  return {
    fontSize: `${wm.font_size}px`,
    color: wm.color,
    opacity: wm.opacity / 100,
    textShadow: '1px 1px 2px rgba(0,0,0,0.5)',
  }
})

/** 图片水印样式 */
const imageStyle = computed(() => {
  const wm = wmConfig.value
  if (!wm) return {}
  return {
    width: `${wm.image_width}px`,
    opacity: wm.opacity / 100,
  }
})
</script>

<style scoped>
.watermark-overlay {
  position: relative;
  display: inline-block;
  overflow: hidden;
}

.watermark-overlay :deep(img) {
  display: block;
}

.wm-text,
.wm-image {
  position: absolute;
  pointer-events: none;
  user-select: none;
  z-index: 2;
}

/* 位置：左上 */
.wm-position-top-left .wm-text,
.wm-position-top-left .wm-image {
  top: var(--wm-margin, 20px);
  left: var(--wm-margin, 20px);
}

/* 位置：右上 */
.wm-position-top-right .wm-text,
.wm-position-top-right .wm-image {
  top: var(--wm-margin, 20px);
  right: var(--wm-margin, 20px);
}

/* 位置：左下 */
.wm-position-bottom-left .wm-text,
.wm-position-bottom-left .wm-image {
  bottom: var(--wm-margin, 20px);
  left: var(--wm-margin, 20px);
}

/* 位置：右下（默认） */
.wm-position-bottom-right .wm-text,
.wm-position-bottom-right .wm-image {
  bottom: var(--wm-margin, 20px);
  right: var(--wm-margin, 20px);
}

/* 位置：居中 */
.wm-position-center .wm-text,
.wm-position-center .wm-image {
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.wm-text {
  font-weight: 600;
  white-space: nowrap;
}
</style>
