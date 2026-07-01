<!--
  =====================================================
  带水印的图片组件（CSS 叠加方案）
  - 普通 <img> 标签显示图片，避免 Canvas 跨域污染问题
  - 水印使用绝对定位 CSS 叠加在图片上方
  - 水印开关：全局强制 + 用户级，任一开启则显示
  - 支持文字水印和图片水印
  - 透明拦截层阻止右键直接保存原图，提示使用下载按钮
  - 注意：此组件仅用于前端显示水印；下载带水印图片请走后端接口
  =====================================================
-->

<template>
  <div
    class="img-with-watermark"
    :class="[`wm-position-${wmConfig?.position || 'bottom-right'}`]"
    :style="wrapStyle"
    @contextmenu.prevent="handleContextMenu"
    @dragstart.prevent
  >
    <!-- 原图 + 水印层（加载失败时整体隐藏） -->
    <template v-if="!loadFailed">
      <!-- 原图（普通 img，无跨域问题） -->
      <img
        :src="src"
        :alt="alt"
        :loading="loading"
        :class="imgClass"
        :style="mergedImgStyle"
        :draggable="false"
        @load="$emit('load', $event)"
        @error="handleError"
      />
      <!-- 文字水印 -->
      <div
        v-if="shouldShow && wmConfig?.type === 'text' && wmConfig.text"
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
        draggable="false"
      />
      <!-- 透明拦截层：水印开启时覆盖在最上层，阻止右键直接保存原图 -->
      <div
        v-if="shouldShow"
        class="wm-intercept-layer"
        :title="interceptTitle"
      />
    </template>
    <!-- 加载失败占位：上游 URL 过期等导致图片加载失败时优雅降级 -->
    <div v-else class="image-failed-placeholder">
      <el-icon :size="48"><Picture /></el-icon>
      <span>{{ t('common.resourceExpired') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'
import { ElMessage } from 'element-plus'
import { Picture } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useModelsStore } from '@/stores/models'
import { useUserStore } from '@/stores/user'

const { t } = useI18n()

interface Props {
  src: string
  alt?: string
  loading?: 'lazy' | 'eager'
  imgClass?: string | string[] | Record<string, boolean>
  imgStyle?: CSSProperties
  fit?: 'contain' | 'cover' | 'fill'
  /** 自定义宽度，不传则自适应 */
  width?: number | string
  /** 自定义高度，不传则自适应 */
  height?: number | string
}

const props = withDefaults(defineProps<Props>(), {
  alt: '',
  loading: 'lazy',
  fit: 'contain',
  width: '',
  height: '',
})

const emit = defineEmits<{
  (e: 'load', event: Event): void
  (e: 'error', event: Event): void
}>()

/** 图片是否加载失败（用于切换占位显示） */
const loadFailed = ref(false)

/**
 * 图片加载失败处理：切换为占位显示，并向上抛出 error 事件
 * 注意：onerror 只触发一次占位切换，不做重试
 */
function handleError(event: Event) {
  loadFailed.value = true
  emit('error', event)
}

// src 变化时重置失败状态，便于列表中复用组件时重新尝试加载
watch(
  () => props.src,
  () => {
    loadFailed.value = false
  },
)

const modelsStore = useModelsStore()
const userStore = useUserStore()

/** 拦截层标题提示 */
const interceptTitle = computed(() => t('watermark.useDownloadButton'))

/**
 * 右键菜单处理：提示用户使用下载按钮下载带水印图片
 */
const handleContextMenu = () => {
  if (shouldShow.value) {
    ElMessage.warning(t('watermark.useDownloadButton'))
  }
}

/** 外层容器样式 */
const wrapStyle = computed<CSSProperties>(() => {
  const style: CSSProperties = {
    position: 'relative',
    display: 'inline-block',
    overflow: 'hidden',
  }
  if (props.width) style.width = typeof props.width === 'number' ? `${props.width}px` : props.width
  if (props.height) style.height = typeof props.height === 'number' ? `${props.height}px` : props.height
  return style
})

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
      text: userStore.user.username || userStore.user.nickname || '',
      font_size: 16,
      color: '#ffffff',
      opacity: 60,
      position: 'bottom-right' as const,
      margin: 20,
      image_url: '',
      image_width: 100,
    }
  }
  return null
})

/** 文字水印样式 */
const textStyle = computed<CSSProperties>(() => {
  const wm = wmConfig.value
  if (!wm) return {}
  return {
    fontSize: `${wm.font_size}px`,
    color: wm.color,
    opacity: wm.opacity / 100,
    textShadow: '1px 1px 2px rgba(0,0,0,0.5)',
    '--wm-margin': `${wm.margin}px`,
    fontWeight: 600,
    whiteSpace: 'nowrap',
    position: 'absolute',
    pointerEvents: 'none',
    userSelect: 'none',
    zIndex: 2,
  } as CSSProperties
})

/** 图片水印样式 */
const imageStyle = computed<CSSProperties>(() => {
  const wm = wmConfig.value
  if (!wm) return {}
  return {
    width: `${wm.image_width}px`,
    opacity: wm.opacity / 100,
    '--wm-margin': `${wm.margin}px`,
    position: 'absolute',
    pointerEvents: 'none',
    userSelect: 'none',
    zIndex: 2,
  } as CSSProperties
})

/** 合并 imgStyle 和 fit 样式 */
const mergedImgStyle = computed<CSSProperties>(() => {
  const style: CSSProperties = { ...props.imgStyle }
  if (props.width) style.width = typeof props.width === 'number' ? `${props.width}px` : props.width
  if (props.height) style.height = typeof props.height === 'number' ? `${props.height}px` : props.height
  if (props.fit === 'contain') style.objectFit = 'contain'
  else if (props.fit === 'cover') style.objectFit = 'cover'
  else if (props.fit === 'fill') style.objectFit = 'fill'
  return style
})
</script>

<style scoped>
.img-with-watermark :deep(img) {
  display: block;
  max-width: 100%;
  -webkit-user-drag: none;
  user-select: none;
}

/* 透明拦截层：覆盖在整个图片上方，阻止右键和拖拽直接保存原图 */
.wm-intercept-layer {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 3;
  cursor: default;
  background: transparent;
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

/* 加载失败占位：上游 URL 过期等导致图片加载失败时显示 */
.image-failed-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 100%;
  min-height: 200px;
  background: var(--el-fill-color-light, #f5f7fa);
  color: var(--el-text-color-secondary, #909399);
  border-radius: 4px;
}

.image-failed-placeholder span {
  font-size: 13px;
}
</style>
