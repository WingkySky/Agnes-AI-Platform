<!-- =====================================================
     ImageViewer —— 独立的图片放大查看组件
     功能：
       - 鼠标滚轮 / 按钮缩放（10% ~ 500%）
       - 鼠标拖动 / 触控拖动平移
       - 按钮旋转 90°
       - 按钮左右 / 上下 翻转
       - 双击图片一键放大到 100% / 还原
       - 右上角关闭按钮 + ESC 键
       - 底部工具栏：缩放按钮 / 旋转 / 下载 / 重置
       - 点击背景遮罩关闭
       - 图片水印显示 + 防右键另存保护
     使用方式：
       <ImageViewer v-model:visible="show" :url="imageUrl" :download-url="downloadUrl" />
     其中：
       - url：图片显示的 URL（必填，显示带水印）
       - download-url：下载时使用的 URL（可选，应为后端带水印下载接口）
     ===================================================== -->

<template>
  <transition name="viewer-fade">
    <div v-if="visible && url" class="image-viewer-mask" @click.self="close">
      <!-- 顶部栏：标题 + 关闭按钮 -->
      <div class="viewer-top-bar">
        <div class="viewer-title">{{ t('imageViewer.title') }}</div>
        <button class="viewer-close-btn" @click="close" :title="t('imageViewer.closeHint')">
          <el-icon :size="22"><Close></Close></el-icon>
        </button>
      </div>

      <!-- 中间图片区：可拖动、可滚轮缩放 -->
      <div
        class="viewer-stage"
        ref="stageEl"
        @wheel.prevent="onWheel"
        @mousedown="onMouseDown"
        @touchstart.passive="onTouchStart"
        @touchmove.prevent="onTouchMove"
        @touchend="onTouchEnd"
        @dblclick="onDblClick"
        @contextmenu.prevent="handleContextMenu"
      >
        <!-- 图片容器：应用缩放/旋转/翻转 transform -->
        <div
          ref="imgContainerEl"
          class="viewer-img-container"
          :class="[`wm-position-${wmConfig?.position || 'bottom-right'}`]"
          :style="imgContainerStyle"
          @click.stop
          @dragstart.prevent
        >
          <!-- 原图 -->
          <img
            ref="imgEl"
            :src="url"
            class="viewer-img"
            draggable="false"
            @load="onImgLoaded"
            @error="onImgError"
          />
          <!-- 文字水印 -->
          <div
            v-if="shouldShowWatermark && wmConfig?.type === 'text' && wmConfig.text"
            class="viewer-wm-text"
            :style="wmTextStyle"
          >
            {{ wmConfig.text }}
          </div>
          <!-- 图片水印 -->
          <img
            v-else-if="shouldShowWatermark && wmConfig?.type === 'image' && wmConfig.image_url"
            class="viewer-wm-image"
            :src="wmConfig.image_url"
            :style="wmImageStyle"
            alt="watermark"
            draggable="false"
          />
          <!-- 透明拦截层：覆盖在图片上方，阻止右键直接保存原图 -->
          <div
            v-if="shouldShowWatermark"
            class="viewer-wm-intercept"
            :title="interceptTitle"
          />
        </div>
        <!-- 图片加载失败提示 -->
        <div v-if="loadFailed" class="viewer-load-failed">
          <el-icon :size="36"><Warning></Warning></el-icon>
          <span>{{ t('imageViewer.loadFailed') }}</span>
        </div>
      </div>

      <!-- 底部工具栏：缩放信息 + 操作按钮 -->
      <div class="viewer-toolbar">
        <div class="viewer-zoom-info">
          <span class="zoom-value">{{ Math.round(scale * 100) }}%</span>
          <span v-if="rotate !== 0" class="rotate-value"> {{ rotate }}°</span>
        </div>
        <div class="viewer-btns">
          <button class="viewer-btn" @click="zoomOut" :title="t('imageViewer.zoomOut')">
            <el-icon :size="18"><ZoomOut></ZoomOut></el-icon>
          </button>
          <button class="viewer-btn" @click="zoomIn" :title="t('imageViewer.zoomIn')">
            <el-icon :size="18"><ZoomIn></ZoomIn></el-icon>
          </button>
          <span class="btn-divider"></span>
          <button class="viewer-btn" @click="rotateLeft" :title="t('imageViewer.rotateLeft')">
            <el-icon :size="18"><RefreshLeft></RefreshLeft></el-icon>
          </button>
          <button class="viewer-btn" @click="rotateRight" :title="t('imageViewer.rotateRight')">
            <el-icon :size="18"><RefreshRight></RefreshRight></el-icon>
          </button>
          <span class="btn-divider"></span>
          <button class="viewer-btn" @click="flipX" :title="t('imageViewer.flipH')">
            <svg viewBox="0 0 24 24" width="18" height="18">
              <path d="M11 3 L11 21 M3 7 L9 12 L3 17 Z M21 7 L15 12 L21 17 Z" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linejoin="round"></path>
            </svg>
          </button>
          <button class="viewer-btn" @click="flipY" :title="t('imageViewer.flipV')">
            <svg viewBox="0 0 24 24" width="18" height="18" style="transform: rotate(90deg);">
              <path d="M11 3 L11 21 M3 7 L9 12 L3 17 Z M21 7 L15 12 L21 17 Z" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linejoin="round"></path>
            </svg>
          </button>
          <span class="btn-divider"></span>
          <button class="viewer-btn" @click="resetView" :title="t('imageViewer.reset')">
            <el-icon :size="18"><Refresh></Refresh></el-icon>
          </button>
          <span class="btn-divider"></span>
          <button class="viewer-btn viewer-btn-primary" @click="handleDownload" :title="t('imageViewer.download')">
            <el-icon :size="18"><Download></Download></el-icon>
          </button>
        </div>
        <div class="viewer-hint">
          <span>{{ t('imageViewer.hintShort') }}</span>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
/* =====================================================
 * ImageViewer 核心逻辑：
 * 1. 接收 visible（双向）与 url 控制显示
 * 2. 通过 ref(stageEl) 监听 mouse / wheel / touch 事件
 * 3. 使用 scale / translate / rotate / flip 组合 transform
 * 4. transform 绑定到图片容器（imgContainerEl），水印和拦截层一起变换
 * 5. ESC 键关闭；打开时自动锁定 body 滚动
 * 6. 显示 CSS 水印 + 透明拦截层防右键另存
 * ===================================================== */

import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Close,
  ZoomIn,
  ZoomOut,
  Refresh,
  RefreshLeft,
  RefreshRight,
  Download,
  Warning,
} from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useModelsStore } from '@/stores/models'
import { useUserStore } from '@/stores/user'

const { t } = useI18n()
const modelsStore = useModelsStore()
const userStore = useUserStore()

/* ---------- Props / Emits ---------- */
const props = defineProps({
  visible: { type: Boolean, default: false },
  url: { type: String, default: '' },
  downloadUrl: { type: String, default: '' },
  type: { type: String, default: 'image' },
})
const emit = defineEmits(['update:visible', 'close'])

/* ---------- 状态 ---------- */
const stageEl = ref<HTMLElement | null>(null)
const imgEl = ref<HTMLImageElement | null>(null)
const imgContainerEl = ref<HTMLDivElement | null>(null)
const scale = ref(1)
const translateX = ref(0)
const translateY = ref(0)
const rotate = ref(0)
const flippedX = ref(false)
const flippedY = ref(false)
const loadFailed = ref(false)

// 拖动临时状态
const dragging = ref(false)
const dragStart = ref({ x: 0, y: 0, tx: 0, ty: 0 })

// 触控缩放临时状态
const pinchStartDist = ref(0)
const pinchStartScale = ref(1)

/* ---------- 最小/最大缩放 ---------- */
const MIN_SCALE = 0.1
const MAX_SCALE = 5
const ZOOM_STEP = 0.15

/* ---------- 计算图片容器样式（transform 应用到容器，水印一起变换） ---------- */
const imgContainerStyle = computed(() => ({
  transform: 'translate(' + translateX.value + 'px, ' + translateY.value + 'px) scale(' + scale.value + ') rotate(' + rotate.value + 'deg) scaleX(' + (flippedX.value ? -1 : 1) + ') scaleY(' + (flippedY.value ? -1 : 1) + ')',
  transition: dragging.value ? 'none' : 'transform 0.18s ease-out',
}))

/* ---------- 水印相关配置 ---------- */
/** 拦截层标题提示 */
const interceptTitle = computed(() => t('watermark.useDownloadButton'))

/** 是否应该显示水印 */
const shouldShowWatermark = computed(() => {
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
const wmTextStyle = computed(() => {
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
  }
})

/** 图片水印样式 */
const wmImageStyle = computed(() => {
  const wm = wmConfig.value
  if (!wm) return {}
  return {
    width: `${wm.image_width}px`,
    opacity: wm.opacity / 100,
    '--wm-margin': `${wm.margin}px`,
  }
})

/**
 * 右键菜单处理：提示用户使用下载按钮下载带水印图片
 */
const handleContextMenu = () => {
  if (shouldShowWatermark.value) {
    ElMessage.warning(t('watermark.useDownloadButton'))
  }
}

/* ---------- 打开/关闭 ---------- */
function close() {
  emit('update:visible', false)
  emit('close')
}

watch(
  () => props.visible,
  (val) => {
    if (val) {
      resetTransform()
      document.body.style.overflow = 'hidden'
      nextTick(() => {
        if (stageEl.value && stageEl.value.focus) {
          stageEl.value.focus()
        }
      })
    } else {
      document.body.style.overflow = ''
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  document.body.style.overflow = ''
})

/* ---------- 重置视图 ---------- */
function resetTransform() {
  scale.value = 1
  translateX.value = 0
  translateY.value = 0
  rotate.value = 0
  flippedX.value = false
  flippedY.value = false
  loadFailed.value = false
}

function resetView() {
  resetTransform()
}

/* ---------- 缩放 ---------- */
function applyScale(next: number, centerX?: number | null, centerY?: number | null) {
  const clamped = Math.max(MIN_SCALE, Math.min(MAX_SCALE, next))
  if (centerX != null && centerY != null) {
    // 以鼠标为中心进行缩放：让 (centerX, centerY) 点在缩放前后保持相对位置不变
    const ratio = clamped / scale.value
    translateX.value = centerX - ratio * (centerX - translateX.value)
    translateY.value = centerY - ratio * (centerY - translateY.value)
  }
  scale.value = clamped
}

function zoomIn() {
  applyScale(scale.value + ZOOM_STEP, 0, 0)
}
function zoomOut() {
  applyScale(scale.value - ZOOM_STEP, 0, 0)
}

/* ---------- 滚轮缩放：以鼠标位置为中心 ---------- */
function onWheel(e: WheelEvent) {
  const stage = stageEl.value
  if (!stage) return
  const rect = stage.getBoundingClientRect()
  // stage 坐标系原点在中心
  const cx = e.clientX - rect.left - rect.width / 2
  const cy = e.clientY - rect.top - rect.height / 2
  const delta = e.deltaY < 0 ? 1 + ZOOM_STEP : 1 - ZOOM_STEP
  applyScale(scale.value * delta, cx, cy)
}

/* ---------- 鼠标拖动平移 ---------- */
function onMouseDown(e: MouseEvent) {
  if (e.button !== 0) return // 只响应左键
  dragging.value = true
  dragStart.value = {
    x: e.clientX,
    y: e.clientY,
    tx: translateX.value,
    ty: translateY.value,
  }
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}
function onMouseMove(e: MouseEvent) {
  if (!dragging.value) return
  translateX.value = dragStart.value.tx + (e.clientX - dragStart.value.x)
  translateY.value = dragStart.value.ty + (e.clientY - dragStart.value.y)
}
function onMouseUp() {
  dragging.value = false
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
}

/* ---------- 触控：单指拖动 + 双指捏合 ---------- */
const touchPoints = ref<{ x: number; y: number }[]>([])
function onTouchStart(e: TouchEvent) {
  touchPoints.value = Array.from(e.touches).map((tp: Touch) => ({ x: tp.clientX, y: tp.clientY }))
  if (touchPoints.value.length === 1) {
    dragging.value = true
    dragStart.value = {
      x: touchPoints.value[0].x,
      y: touchPoints.value[0].y,
      tx: translateX.value,
      ty: translateY.value,
    }
  } else if (touchPoints.value.length === 2) {
    dragging.value = false
    pinchStartDist.value = touchDistance(touchPoints.value[0], touchPoints.value[1])
    pinchStartScale.value = scale.value
  }
}
function onTouchMove(e: TouchEvent) {
  const pts = Array.from(e.touches).map((tp: Touch) => ({ x: tp.clientX, y: tp.clientY }))
  if (pts.length === 1 && dragging.value) {
    translateX.value = dragStart.value.tx + (pts[0].x - dragStart.value.x)
    translateY.value = dragStart.value.ty + (pts[0].y - dragStart.value.y)
  } else if (pts.length === 2) {
    const dist = touchDistance(pts[0], pts[1])
    if (pinchStartDist.value > 0) {
      const ratio = dist / pinchStartDist.value
      applyScale(pinchStartScale.value * ratio, 0, 0)
    }
  }
}
function onTouchEnd(e: TouchEvent) {
  if (e.touches.length === 0) {
    dragging.value = false
    pinchStartDist.value = 0
  }
}
function touchDistance(a: { x: number; y: number }, b: { x: number; y: number }) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

/* ---------- 双击：100% / 还原 ---------- */
function onDblClick() {
  if (scale.value === 1) {
    scale.value = 2
  } else {
    resetTransform()
  }
}

/* ---------- 旋转 / 翻转 ---------- */
function rotateLeft() {
  rotate.value = (rotate.value - 90) % 360
}
function rotateRight() {
  rotate.value = (rotate.value + 90) % 360
}
function flipX() {
  flippedX.value = !flippedX.value
}
function flipY() {
  flippedY.value = !flippedY.value
}

/* ---------- 键盘快捷键：ESC 关闭 / +/- 缩放 / R 旋转 ---------- */
function onKeyDown(e: KeyboardEvent) {
  if (!props.visible) return
  if (e.key === 'Escape') {
    e.preventDefault()
    close()
  } else if (e.key === '+' || e.key === '=') {
    e.preventDefault()
    zoomIn()
  } else if (e.key === '-' || e.key === '_') {
    e.preventDefault()
    zoomOut()
  } else if (e.key === 'r' || e.key === 'R') {
    rotateRight()
  } else if (e.key === '0') {
    resetTransform()
  }
}
onMounted(() => window.addEventListener('keydown', onKeyDown))
onUnmounted(() => window.removeEventListener('keydown', onKeyDown))

/* ---------- 图片加载状态 ---------- */
function onImgLoaded() {
  loadFailed.value = false
}
function onImgError() {
  loadFailed.value = true
  console.warn('[ImageViewer] 图片加载失败：', props.url)
}

/* ---------- 下载 ---------- */
async function handleDownload() {
  const target = props.downloadUrl || props.url
  if (!target) {
    ElMessage.warning(t('imageViewer.emptyUrl'))
    return
  }
  try {
    // 使用 fetch + blob 方式触发下载，避免直接打开图片
    const response = await fetch(target)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const blob = await response.blob()
    const blobUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = blobUrl
    // 从 URL 中尝试提取文件名，否则使用默认名
    const urlPath = target.split('?')[0]
    const fileName = urlPath.split('/').pop() || `agnes-image-${Date.now()}.png`
    a.download = fileName
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(blobUrl)
    ElMessage.success(t('imageViewer.downloadStarted'))
  } catch (err) {
    console.warn('[ImageViewer] 下载失败：', err)
    ElMessage.error(t('canvas.messages.downloadFailed'))
  }
}
</script>

<style scoped>
/* 遮罩层：全屏暗色，点击空白关闭 */
.image-viewer-mask {
  position: fixed;
  inset: 0;
  background: var(--viewer-overlay-bg);
  z-index: 3000;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
  user-select: none;
}

/* 顶部栏：图片查看器始终保持深色沉浸式风格，不跟随主题切换 */
.viewer-top-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  color: var(--viewer-text);
  background: var(--viewer-top-bar-gradient);
  z-index: 2;
}
.viewer-title {
  font-size: 15px;
  font-weight: 500;
  color: var(--viewer-text-muted);
}
.viewer-close-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--viewer-close-bg);
  border: 1px solid var(--viewer-close-border);
  color: var(--viewer-close-text);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}
.viewer-close-btn:hover {
  background: var(--viewer-close-hover-bg);
  border-color: var(--viewer-close-hover-border);
}

/* 中间舞台：可滚动 / 拖动的区域 */
.viewer-stage {
  flex: 1;
  width: 100%;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  cursor: grab;
  perspective: 1000px;
}
.viewer-stage:active {
  cursor: grabbing;
}

/* 图片容器：包含原图、水印、拦截层，统一应用 transform */
.viewer-img-container {
  position: relative;
  display: inline-block;
  transform-origin: center center;
  will-change: transform;
}

/* 图片 */
.viewer-img {
  max-width: 90vw;
  max-height: 75vh;
  display: block;
  box-shadow: var(--viewer-img-shadow);
  border-radius: 4px;
  background: var(--agnes-bg-dark-surface);
  -webkit-user-drag: none;
  user-select: none;
}

/* 透明拦截层：覆盖在图片上方，阻止右键直接保存原图 */
.viewer-wm-intercept {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 3;
  cursor: default;
  background: transparent;
}

/* 水印位置默认（右下） */
.viewer-img-container .viewer-wm-text,
.viewer-img-container .viewer-wm-image {
  position: absolute;
  pointer-events: none;
  user-select: none;
  z-index: 2;
}

/* 位置：左上 */
.wm-position-top-left .viewer-wm-text,
.wm-position-top-left .viewer-wm-image {
  top: var(--wm-margin, 20px);
  left: var(--wm-margin, 20px);
}

/* 位置：右上 */
.wm-position-top-right .viewer-wm-text,
.wm-position-top-right .viewer-wm-image {
  top: var(--wm-margin, 20px);
  right: var(--wm-margin, 20px);
}

/* 位置：左下 */
.wm-position-bottom-left .viewer-wm-text,
.wm-position-bottom-left .viewer-wm-image {
  bottom: var(--wm-margin, 20px);
  left: var(--wm-margin, 20px);
}

/* 位置：右下（默认） */
.wm-position-bottom-right .viewer-wm-text,
.wm-position-bottom-right .viewer-wm-image {
  bottom: var(--wm-margin, 20px);
  right: var(--wm-margin, 20px);
}

/* 位置：居中 */
.wm-position-center .viewer-wm-text,
.wm-position-center .viewer-wm-image {
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

/* 加载失败 */
.viewer-load-failed {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  color: var(--viewer-danger);
  font-size: 14px;
}

/* 底部工具栏：图片查看器始终保持深色沉浸式风格，不跟随主题切换 */
.viewer-toolbar {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 8px 16px;
  background: var(--viewer-toolbar-bg);
  border: 1px solid var(--viewer-border);
  border-radius: 14px;
  backdrop-filter: blur(8px);
  box-shadow: var(--viewer-shadow);
  z-index: 2;
  max-width: calc(100vw - 40px);
  flex-wrap: wrap;
  justify-content: center;
}
.viewer-zoom-info {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--viewer-text-muted);
  font-size: 13px;
  font-family: 'SF Mono', Menlo, monospace;
  min-width: 80px;
}
.zoom-value {
  color: var(--viewer-btn-hover);
  font-weight: 600;
  font-size: 14px;
}
.rotate-value {
  color: var(--viewer-text-muted);
  font-size: 12px;
}

.viewer-btns {
  display: flex;
  align-items: center;
  gap: 2px;
}
.viewer-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: transparent;
  border: 1px solid transparent;
  color: var(--viewer-btn);
  cursor: pointer;
  transition: all 0.15s ease;
}
.viewer-btn:hover {
  background: var(--viewer-btn-hover-bg);
  border-color: var(--viewer-btn-hover-border);
  color: var(--viewer-btn-hover);
}
.viewer-btn-primary {
  color: var(--viewer-btn-primary);
}
.viewer-btn-primary:hover {
  background: var(--viewer-btn-primary-hover-bg);
  color: var(--viewer-btn-hover);
}
.btn-divider {
  width: 1px;
  height: 18px;
  background: rgba(255, 255, 255, 0.12);
  margin: 0 6px;
}

.viewer-hint {
  color: var(--viewer-divider);
  font-size: 12px;
}

/* 过渡动画 */
.viewer-fade-enter-active,
.viewer-fade-leave-active {
  transition: opacity 0.2s ease;
}
.viewer-fade-enter-from,
.viewer-fade-leave-to {
  opacity: 0;
}
</style>
