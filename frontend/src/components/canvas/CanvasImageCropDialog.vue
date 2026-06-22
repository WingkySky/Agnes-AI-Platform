<!-- =====================================================
     图片裁剪对话框（可视化裁剪）
     - 在原图上拖拽裁剪框、8 个手柄调整
     - 九宫格辅助线、锁比例切换
     - 确认时输出相对坐标 { x, y, w, h }（0~1）
     ===================================================== -->

<template>
  <teleport to="body">
    <div v-if="visible" class="crop-overlay" @click.self="$emit('cancel')">
      <div class="crop-dialog" :style="dialogStyle">
        <!-- 标题栏 -->
        <div class="crop-header">
          <span class="crop-title">{{ t('canvas.imageOps.cropTitle') }}</span>
          <button class="crop-close" @click="$emit('cancel')">
            <X :size="18" />
          </button>
        </div>

        <!-- 裁剪画布区域 -->
        <div class="crop-canvas-area" ref="canvasAreaRef">
          <div class="crop-image-wrapper" :style="wrapperStyle">
            <img ref="imgRef" :src="imageUrl" class="crop-image" @load="onImageLoad" />
            <!-- 四块半透明蒙版 -->
            <div class="crop-mask mask-top" :style="maskTopStyle"></div>
            <div class="crop-mask mask-bottom" :style="maskBottomStyle"></div>
            <div class="crop-mask mask-left" :style="maskLeftStyle"></div>
            <div class="crop-mask mask-right" :style="maskRightStyle"></div>
            <!-- 裁剪框 -->
            <div class="crop-rect" :style="cropRectStyle"
              @pointerdown="onRectPointerDown">
              <!-- 九宫格辅助线 -->
              <div class="grid-line grid-v1"></div>
              <div class="grid-line grid-v2"></div>
              <div class="grid-line grid-h1"></div>
              <div class="grid-line grid-h2"></div>
              <!-- 8 个手柄 -->
              <div v-for="h in handles" :key="h"
                class="crop-handle"
                :class="'handle-' + h"
                @pointerdown.stop="onHandlePointerDown($event, h)"></div>
            </div>
          </div>
        </div>

        <!-- 信息栏 -->
        <div class="crop-info">
          <span>{{ t('canvas.imageOps.cropSize') }}: {{ cropPixelW }} × {{ cropPixelH }}</span>
          <span>{{ t('canvas.imageOps.cropRatio') }}: {{ ratioLabel }}</span>
          <span>{{ t('canvas.imageOps.originalSize') }}: {{ imgNaturalW }} × {{ imgNaturalH }}</span>
        </div>

        <!-- 操作按钮 -->
        <div class="crop-actions">
          <label class="crop-lock-toggle">
            <input type="checkbox" v-model="locked" />
            {{ t('canvas.imageOps.lockRatio') }}
          </label>
          <button class="crop-btn-secondary" @click="resetCrop">
            <RotateCcw :size="16" /> {{ t('canvas.imageOps.reset') }}
          </button>
          <button class="crop-btn-cancel" @click="$emit('cancel')">{{ t('canvas.imageOps.cancel') }}</button>
          <button class="crop-btn-confirm" @click="confirm">
            {{ t('canvas.imageOps.confirmCrop') }}
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { X, RotateCcw } from 'lucide-vue-next'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const props = defineProps({
  visible: { type: Boolean, default: false },
  imageUrl: { type: String, default: '' },
  theme: { type: Object, required: true },
})

const emit = defineEmits(['confirm', 'cancel'])

// 裁剪框相对坐标（0~1）
const cropRect = ref({ x: 0.12, y: 0.12, w: 0.76, h: 0.76 })
const locked = ref(true)
const imgNaturalW = ref(0)
const imgNaturalH = ref(0)
const imgRef = ref<HTMLImageElement | null>(null)
const canvasAreaRef = ref<HTMLElement | null>(null)
const dialogStyle = ref({})

// 图片显示尺寸（受 max-width/max-height 约束后的实际渲染尺寸）
const displayW = ref(0)
const displayH = ref(0)

// 裁剪框像素尺寸（基于原图）
const cropPixelW = computed(() => Math.round(cropRect.value.w * imgNaturalW.value))
const cropPixelH = computed(() => Math.round(cropRect.value.h * imgNaturalH.value))

// 比例标签（化简）
const ratioLabel = computed(() => {
  const w = cropPixelW.value
  const h = cropPixelH.value
  if (!w || !h) return '-'
  const g = gcd(w, h)
  return `${w / g}:${h / g}`
})

function gcd(a: number, b: number): number {
  return b === 0 ? a : gcd(b, a % b)
}

// 图片容器样式（居中 + 最大尺寸约束）
const wrapperStyle = computed(() => ({
  width: displayW.value ? displayW.value + 'px' : 'auto',
  height: displayH.value ? displayH.value + 'px' : 'auto',
}))

// 裁剪框样式（绝对定位在图片容器内）
const cropRectStyle = computed(() => ({
  left: cropRect.value.x * 100 + '%',
  top: cropRect.value.y * 100 + '%',
  width: cropRect.value.w * 100 + '%',
  height: cropRect.value.h * 100 + '%',
}))

// 四块蒙版样式
const maskTopStyle = computed(() => ({
  left: '0', top: '0',
  width: '100%', height: cropRect.value.y * 100 + '%',
}))
const maskBottomStyle = computed(() => ({
  left: '0', top: (cropRect.value.y + cropRect.value.h) * 100 + '%',
  width: '100%', height: (1 - cropRect.value.y - cropRect.value.h) * 100 + '%',
}))
const maskLeftStyle = computed(() => ({
  left: '0', top: cropRect.value.y * 100 + '%',
  width: cropRect.value.x * 100 + '%', height: cropRect.value.h * 100 + '%',
}))
const maskRightStyle = computed(() => ({
  left: (cropRect.value.x + cropRect.value.w) * 100 + '%',
  top: cropRect.value.y * 100 + '%',
  width: (1 - cropRect.value.x - cropRect.value.w) * 100 + '%',
  height: cropRect.value.h * 100 + '%',
}))

const handles = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'] as const
type Handle = typeof handles[number]

watch(() => props.visible, async (val) => {
  if (val) {
    // 重置裁剪框
    cropRect.value = { x: 0.12, y: 0.12, w: 0.76, h: 0.76 }
    locked.value = true
    await nextTick()
    dialogStyle.value = {
      // 弹窗需要不透明背景，避免与下方画布混在一起（toolbar.panel 是半透明的）
      background: props.theme.toolbar.panel.startsWith('rgba(15,') ? '#0f1626' : '#ffffff',
      borderColor: props.theme.toolbar.border,
      color: props.theme.node.text,
    }
  }
})

function onImageLoad() {
  const img = imgRef.value
  if (!img) return
  imgNaturalW.value = img.naturalWidth
  imgNaturalH.value = img.naturalHeight
  // 计算显示尺寸（最大 600x400，保持比例）
  const maxW = 600
  const maxH = 400
  let w = img.naturalWidth
  let h = img.naturalHeight
  if (w > maxW) { h = h * (maxW / w); w = maxW }
  if (h > maxH) { w = w * (maxH / h); h = maxH }
  displayW.value = Math.round(w)
  displayH.value = Math.round(h)
}

// 拖动裁剪框移动
let dragStart = { px: 0, py: 0, rect: { x: 0, y: 0, w: 0, h: 0 } }

function onRectPointerDown(e: PointerEvent) {
  e.preventDefault()
  dragStart = {
    px: e.clientX, py: e.clientY,
    rect: { ...cropRect.value },
  }
  window.addEventListener('pointermove', onRectPointerMove)
  window.addEventListener('pointerup', onPointerUp)
}

function onRectPointerMove(e: PointerEvent) {
  const dx = (e.clientX - dragStart.px) / displayW.value
  const dy = (e.clientY - dragStart.py) / displayH.value
  let nx = dragStart.rect.x + dx
  let ny = dragStart.rect.y + dy
  // 边界约束
  nx = Math.max(0, Math.min(1 - dragStart.rect.w, nx))
  ny = Math.max(0, Math.min(1 - dragStart.rect.h, ny))
  cropRect.value = { ...cropRect.value, x: nx, y: ny }
}

// 拖动手柄调整大小
let handleDragStart = { px: 0, py: 0, rect: { x: 0, y: 0, w: 0, h: 0 }, handle: '' as Handle }

function onHandlePointerDown(e: PointerEvent, handle: Handle) {
  e.preventDefault()
  handleDragStart = {
    px: e.clientX, py: e.clientY,
    rect: { ...cropRect.value },
    handle,
  }
  window.addEventListener('pointermove', onHandlePointerMove)
  window.addEventListener('pointerup', onPointerUp)
}

function onHandlePointerMove(e: PointerEvent) {
  const dx = (e.clientX - handleDragStart.px) / displayW.value
  const dy = (e.clientY - handleDragStart.py) / displayH.value
  const r = { ...handleDragStart.rect }
  const h = handleDragStart.handle
  const minSize = 0.05 // 最小裁剪框尺寸

  // 根据手柄方向调整对应边
  if (h.includes('w')) {
    const newX = Math.max(0, Math.min(r.x + r.w - minSize, r.x + dx))
    r.w = r.x + r.w - newX
    r.x = newX
  }
  if (h.includes('e')) {
    r.w = Math.max(minSize, Math.min(1 - r.x, r.w + dx))
  }
  if (h.includes('n')) {
    const newY = Math.max(0, Math.min(r.y + r.h - minSize, r.y + dy))
    r.h = r.y + r.h - newY
    r.y = newY
  }
  if (h.includes('s')) {
    r.h = Math.max(minSize, Math.min(1 - r.y, r.h + dy))
  }

  // 锁比例时：以拖动方向的主轴为准，调整另一轴
  if (locked.value && r.w > 0 && r.h > 0) {
    const aspect = handleDragStart.rect.w / handleDragStart.rect.h
    // 角手柄：以宽为准调整高（或反之，取变化更大的轴）
    if (h === 'nw' || h === 'ne' || h === 'sw' || h === 'se') {
      if (Math.abs(dx) > Math.abs(dy)) {
        r.h = r.w / aspect
        if (h.includes('n')) r.y = handleDragStart.rect.y + handleDragStart.rect.h - r.h
      } else {
        r.w = r.h * aspect
        if (h.includes('w')) r.x = handleDragStart.rect.x + handleDragStart.rect.w - r.w
      }
    }
  }

  // 边界约束
  r.x = Math.max(0, r.x)
  r.y = Math.max(0, r.y)
  if (r.x + r.w > 1) r.w = 1 - r.x
  if (r.y + r.h > 1) r.h = 1 - r.y
  cropRect.value = r
}

function onPointerUp() {
  window.removeEventListener('pointermove', onRectPointerMove)
  window.removeEventListener('pointermove', onHandlePointerMove)
  window.removeEventListener('pointerup', onPointerUp)
}

function resetCrop() {
  cropRect.value = { x: 0.12, y: 0.12, w: 0.76, h: 0.76 }
}

function confirm() {
  emit('confirm', { ...cropRect.value })
}
</script>

<style scoped>
.crop-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: var(--agnes-overlay-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.crop-dialog {
  width: 780px;
  max-width: 90vw;
  border: 1px solid;
  border-radius: 16px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--agnes-bg-dialog); /* 不透明背景，避免与画布内容混在一起 */
}

.crop-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--agnes-border);
}

.crop-title { font-size: 16px; font-weight: 600; }

.crop-close {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px;
  border: none; border-radius: 8px;
  background: transparent; cursor: pointer;
  color: inherit; opacity: 0.6;
}
.crop-close:hover { opacity: 1; background: var(--agnes-bg-hover); }

.crop-canvas-area {
  padding: 20px;
  display: flex;
  justify-content: center;
  background: var(--agnes-bg-dark-surface);
}

.crop-image-wrapper {
  position: relative;
  display: inline-block;
}

.crop-image {
  display: block;
  width: 100%;
  height: 100%;
  user-select: none;
  -webkit-user-drag: none;
}

/* 四块蒙版 */
.crop-mask {
  position: absolute;
  background: rgba(0, 0, 0, 0.55);
  pointer-events: none;
}

/* 裁剪框 */
.crop-rect {
  position: absolute;
  border: 2px solid #fff;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.3);
  cursor: move;
}

/* 九宫格辅助线 */
.grid-line {
  position: absolute;
  background: rgba(255, 255, 255, 0.35);
  pointer-events: none;
}
.grid-v1 { left: 33.33%; top: 0; bottom: 0; width: 1px; }
.grid-v2 { left: 66.66%; top: 0; bottom: 0; width: 1px; }
.grid-h1 { top: 33.33%; left: 0; right: 0; height: 1px; }
.grid-h2 { top: 66.66%; left: 0; right: 0; height: 1px; }

/* 8 个手柄 */
.crop-handle {
  position: absolute;
  width: 12px; height: 12px;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.4);
  border-radius: 50%;
  z-index: 2;
}
.handle-nw { left: -6px; top: -6px; cursor: nwse-resize; }
.handle-n  { left: 50%; top: -6px; margin-left: -6px; cursor: ns-resize; }
.handle-ne { right: -6px; top: -6px; cursor: nesw-resize; }
.handle-e  { right: -6px; top: 50%; margin-top: -6px; cursor: ew-resize; }
.handle-se { right: -6px; bottom: -6px; cursor: nwse-resize; }
.handle-s  { left: 50%; bottom: -6px; margin-left: -6px; cursor: ns-resize; }
.handle-sw { left: -6px; bottom: -6px; cursor: nesw-resize; }
.handle-w  { left: -6px; top: 50%; margin-top: -6px; cursor: ew-resize; }

.crop-info {
  display: flex;
  gap: 24px;
  padding: 12px 20px;
  border-top: 1px solid var(--agnes-border);
  font-size: 13px;
  opacity: 0.8;
}

.crop-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--agnes-border);
}

.crop-lock-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  cursor: pointer;
  margin-right: auto;
}

.crop-btn-secondary,
.crop-btn-cancel {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 16px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  color: inherit;
  font-size: 14px;
}
.crop-btn-secondary:hover,
.crop-btn-cancel:hover { background: var(--agnes-bg-hover); }

.crop-btn-confirm {
  padding: 8px 20px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--agnes-primary), var(--agnes-accent));
  cursor: pointer;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
}
.crop-btn-confirm:hover { opacity: 0.9; }
</style>
