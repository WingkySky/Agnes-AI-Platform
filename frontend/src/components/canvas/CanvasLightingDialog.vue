<!-- =====================================================
     AI 打光对话框
     - 左列：光源方向球（打光模拟实时作用于原图/占位剪影，拖拽调方位角/仰角）+ 主光源快捷
     - 右列：亮度 / 光色 / 轮廓光 / 智能模式 + 风格预设效果图（程序化渲染的采样场景）
     - 确认时组装"只改光照不改实体"提示词（由 CanvasView 调图生图 API）
     ===================================================== -->

<template>
  <teleport to="body">
    <div v-if="visible" class="lighting-overlay" @click.self="$emit('cancel')">
      <div class="lighting-dialog" :style="dialogStyle">
        <!-- 标题栏 -->
        <div class="lighting-header">
          <span class="lighting-title">{{ t('canvas.imageOps.lightingTitle') }}</span>
          <button class="lighting-close" :aria-label="t('canvas.imageOps.closeLighting')" @click="$emit('cancel')">
            <X :size="18" />
          </button>
        </div>

        <div class="lighting-body">
          <!-- 左列：方向球 + 主光源快捷 -->
          <div class="sphere-column">
            <div class="mode-segment">
              <button :class="{ active: viewMode === 'perspective' }" @click="viewMode = 'perspective'">{{ t('canvas.imageOps.viewPerspective') }}</button>
              <button :class="{ active: viewMode === 'front' }" @click="viewMode = 'front'">{{ t('canvas.imageOps.viewFront') }}</button>
            </div>
            <canvas
              ref="sphereCanvas"
              :width="SPHERE_SIZE * dpr"
              :height="SPHERE_SIZE * dpr"
              class="light-sphere"
              :aria-label="t('canvas.imageOps.lightSphereAria')"
              @pointerdown="startDrag"
              @pointermove="onDrag"
              @pointerup="endDrag"
              @pointercancel="endDrag"
            />
            <div class="lower-block">
              <label class="lower-label">{{ t('canvas.imageOps.keyLight') }}</label>
              <div class="position-grid">
                <button
                  v-for="position in LIGHT_POSITIONS"
                  :key="position.labelKey"
                  class="position-btn"
                  :class="{ active: isActivePosition(position) }"
                  @click="applyPosition(position)"
                >{{ t(position.labelKey) }}</button>
              </div>
            </div>
          </div>

          <!-- 右列：参数 + 风格预设 -->
          <div class="param-column">
            <div class="param-row">
              <label>{{ t('canvas.imageOps.lightBrightness') }}</label>
              <input type="range" v-model.number="options.brightness" min="0" max="100" />
              <span class="param-value">{{ options.brightness }}%</span>
            </div>
            <div class="param-row param-row-auto">
              <label>{{ t('canvas.imageOps.lightColor') }}</label>
              <div class="color-row">
                <label class="color-swatch" :class="{ 'is-white': isWhiteLight }" :style="swatchStyle">
                  <input type="color" v-model="options.lightColor" :aria-label="t('canvas.imageOps.colorAria')" />
                </label>
                <span class="color-hex">{{ options.lightColor }}</span>
              </div>
              <label class="switch-row">
                <span>{{ t('canvas.imageOps.lightRim') }}</span>
                <button type="button" class="switch" :class="{ on: options.rimLight }" role="switch" :aria-checked="options.rimLight" @click="options.rimLight = !options.rimLight">
                  <span class="switch-knob" />
                </button>
              </label>
            </div>
            <div class="smart-row">
              <label class="switch-row">
                <span>{{ t('canvas.imageOps.smartMode') }}</span>
                <button type="button" class="switch" :class="{ on: options.smartMode }" role="switch" :aria-checked="options.smartMode" @click="options.smartMode = !options.smartMode">
                  <span class="switch-knob" />
                </button>
              </label>
              <textarea
                v-model="smartDesc"
                class="smart-desc"
                rows="2"
                :disabled="!options.smartMode"
                :placeholder="t('canvas.imageOps.smartModePlaceholder')"
              />
            </div>

            <div class="lower-block">
              <label class="lower-label">{{ t('canvas.imageOps.stylePresetLabel') }}</label>
              <div class="preset-grid">
                <button
                  v-for="preset in LIGHTING_STYLE_PRESETS"
                  :key="preset.id"
                  class="style-preset"
                  :class="{ active: options.stylePreset === preset.id }"
                  :title="t(preset.labelKey)"
                  @click="applyPreset(preset.id)"
                >
                  <canvas :ref="el => registerThumb(preset.id, el)" :width="SAMPLE_W * dpr" :height="SAMPLE_H * dpr" class="preset-thumb" />
                  <span class="preset-name">{{ t(preset.labelKey) }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="lighting-actions">
          <button class="lighting-btn-reset" @click="resetParams">
            <RotateCcw :size="14" />
            {{ t('canvas.imageOps.resetParams') }}
          </button>
          <span class="spacer" />
          <button class="lighting-btn-copy" @click="copyPrompt">{{ t('canvas.imageOps.copyLightingPrompt') }}</button>
          <button class="lighting-btn-confirm" @click="confirm">{{ t('canvas.imageOps.generateLighting') }}</button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount, type ComponentPublicInstance } from 'vue'
import { X, RotateCcw } from 'lucide-vue-next'
import { useI18n } from '@/i18n'
import { useCopyText } from '@/composables/useCopyText'
import {
  DEFAULT_LIGHTING_OPTIONS, LIGHT_POSITIONS, LIGHTING_STYLE_PRESETS,
  buildLightingPrompt, buildLightingLabel,
  type LightingOptions,
} from '@/lib/canvas-lighting'
import { drawLightSphereControl, drawLightingSample } from '@/lib/canvas-lighting-preview'

const { t } = useI18n()
const { copyText } = useCopyText()

const props = defineProps({
  visible: { type: Boolean, default: false },
  imageUrl: { type: String, default: '' },
  theme: { type: Object, required: true },
})

const emit = defineEmits(['confirm', 'cancel'])

const SPHERE_SIZE = 210
const SAMPLE_W = 120
const SAMPLE_H = 76
const dpr = Math.min(2, window.devicePixelRatio || 1)

const options = ref<LightingOptions>({ ...DEFAULT_LIGHTING_OPTIONS })
const smartDesc = ref('')
const viewMode = ref<'perspective' | 'front'>('perspective')
const dialogStyle = ref<Record<string, string>>({})

const isWhiteLight = computed(() => options.value.lightColor.toLowerCase() === '#ffffff')
// 色块底色：白光显示棋盘格（表示不着色），非白光直接显示所选颜色
const swatchStyle = computed(() => isWhiteLight.value ? undefined : { background: options.value.lightColor })

function isActivePosition(position: { azimuth: number; elevation: number }): boolean {
  return position.azimuth === options.value.azimuth && position.elevation === options.value.elevation
}
function applyPosition(position: { azimuth: number; elevation: number }) {
  options.value.azimuth = position.azimuth
  options.value.elevation = position.elevation
}
function applyPreset(id: string) {
  options.value.stylePreset = options.value.stylePreset === id ? '' : id
}
function resetParams() {
  options.value = { ...DEFAULT_LIGHTING_OPTIONS }
  smartDesc.value = ''
  viewMode.value = 'perspective'
}
function currentPrompt(): string {
  return buildLightingPrompt(options.value, smartDesc.value)
}
async function copyPrompt() {
  await copyText(currentPrompt(), t('canvas.imageOps.promptCopied'))
}
function confirm() {
  emit('confirm', { prompt: currentPrompt(), label: buildLightingLabel(options.value) })
}

/* ---------- 方向球绘制（打光模拟实时作用于原图） ---------- */
const sphereCanvas = ref<HTMLCanvasElement | null>(null)
const sphereImage = ref<HTMLImageElement | null>(null)
const sphereImageReady = ref(false)

function drawSphere() {
  const canvas = sphereCanvas.value
  const ctx = canvas?.getContext('2d')
  if (!canvas || !ctx) return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  drawLightSphereControl(ctx, SPHERE_SIZE, {
    options: options.value,
    viewMode: viewMode.value,
    image: sphereImage.value,
    imageReady: sphereImageReady.value,
  })
}

function loadSphereImage() {
  sphereImage.value = null
  sphereImageReady.value = false
  if (!props.imageUrl) return
  const image = new Image()
  // 不设 crossOrigin：仅用于显示不读取像素，非同源图片也能加载
  image.onload = () => {
    sphereImageReady.value = true
    drawSphere()
  }
  image.onerror = () => {
    sphereImageReady.value = false
    drawSphere()
  }
  image.src = props.imageUrl
  sphereImage.value = image
}

watch([options, viewMode], () => drawSphere(), { deep: true })

/* ---------- 方向球拖拽 ---------- */
const dragging = ref(false)
const dragStart = ref({ x: 0, y: 0, azimuth: 0, elevation: 0 })

function startDrag(event: PointerEvent) {
  event.preventDefault()
  dragging.value = true
  dragStart.value = { x: event.clientX, y: event.clientY, azimuth: options.value.azimuth, elevation: options.value.elevation }
  if (event.currentTarget instanceof HTMLElement) event.currentTarget.setPointerCapture(event.pointerId)
}
function onDrag(event: PointerEvent) {
  if (!dragging.value) return
  const deltaX = event.clientX - dragStart.value.x
  const deltaY = event.clientY - dragStart.value.y
  let azimuth = (dragStart.value.azimuth + deltaX * 1.5) % 360
  if (azimuth < 0) azimuth += 360
  const elevation = Math.max(-90, Math.min(90, dragStart.value.elevation - deltaY))
  options.value.azimuth = Math.round(azimuth)
  options.value.elevation = Math.round(elevation)
}
function endDrag(event: PointerEvent) {
  dragging.value = false
  if (event.currentTarget instanceof HTMLElement && event.currentTarget.hasPointerCapture(event.pointerId)) {
    event.currentTarget.releasePointerCapture(event.pointerId)
  }
}

/* ---------- 风格预设效果图 ---------- */
const thumbCanvases = new Map<string, HTMLCanvasElement>()

function registerThumb(presetId: string, el: Element | ComponentPublicInstance | null) {
  if (el instanceof HTMLCanvasElement) thumbCanvases.set(presetId, el)
  else thumbCanvases.delete(presetId)
}

function drawPresetThumbs() {
  for (const preset of LIGHTING_STYLE_PRESETS) {
    const canvas = thumbCanvases.get(preset.id)
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) continue
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    drawLightingSample(ctx, SAMPLE_W, SAMPLE_H, preset, sphereImage.value, sphereImageReady.value)
  }
}

// 弹窗由外层 v-if 控制每次挂载，visible 挂载时即为 true，必须用 onMounted 初始化；
// watch 兜底处理"组件常驻、visible 翻转"的挂载方式
async function initDialog() {
  resetParams()
  await nextTick()
  dialogStyle.value = {
    // 弹窗需要不透明背景，避免与下方画布混在一起（toolbar.panel 是半透明的）
    background: props.theme.toolbar.panel.startsWith('rgba(15,') ? '#0f1626' : '#ffffff',
    borderColor: props.theme.toolbar.border,
    color: props.theme.node.text,
  }
  loadSphereImage()
  drawPresetThumbs()
  drawSphere()
}

onMounted(() => { void initDialog() })

watch(() => props.visible, (val) => {
  if (val) void initDialog()
})

// 原图异步加载完成后，方向球与预设缩略图都换成原图效果
watch(sphereImageReady, () => {
  drawSphere()
  drawPresetThumbs()
})

onBeforeUnmount(() => {
  sphereImage.value = null
  thumbCanvases.clear()
})
</script>

<style scoped>
.lighting-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: var(--agnes-overlay-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.lighting-dialog {
  width: 780px;
  max-width: 90vw;
  border: 1px solid;
  border-radius: 16px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--agnes-bg-dialog);
}

.lighting-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--agnes-border);
}

.lighting-title { font-size: 16px; font-weight: 600; }

.lighting-close {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px;
  border: none; border-radius: 8px;
  background: transparent; cursor: pointer;
  color: inherit; opacity: 0.6;
}
.lighting-close:hover { opacity: 1; background: var(--agnes-bg-hover); }

.lighting-body {
  display: grid;
  grid-template-columns: 250px minmax(0, 1fr);
  gap: 18px;
  padding: 14px 20px;
}

.sphere-column {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mode-segment {
  display: flex;
  gap: 4px;
  padding: 3px;
  border-radius: 8px;
  background: var(--agnes-bg-hover);
  align-self: flex-start;
}
.mode-segment button {
  padding: 3px 14px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  font-size: 12px;
  cursor: pointer;
}
.mode-segment button.active { background: var(--agnes-primary); color: #fff; }

.light-sphere {
  width: 210px;
  height: 210px;
  align-self: center;
  border-radius: 12px;
  background: var(--agnes-bg-dark-surface);
  cursor: grab;
  touch-action: none;
}
.light-sphere:active { cursor: grabbing; }

.param-column {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.param-row {
  display: grid;
  grid-template-columns: 56px 1fr 48px;
  align-items: center;
  gap: 12px;
}
.param-row-auto { grid-template-columns: 56px 1fr auto; }
.param-row label { font-size: 13px; opacity: 0.8; }
.param-row input[type="range"] { width: 100%; }
.param-value {
  font-size: 12px;
  font-weight: 600;
  text-align: right;
  color: var(--agnes-primary);
}

.color-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.color-swatch {
  position: relative;
  width: 40px; height: 24px;
  border-radius: 6px;
  border: 1px solid var(--agnes-border);
  overflow: hidden;
  cursor: pointer;
}
.color-swatch.is-white {
  background:
    linear-gradient(45deg, #cfcfcf 25%, transparent 25%, transparent 75%, #cfcfcf 75%),
    linear-gradient(45deg, #cfcfcf 25%, #ffffff 25%, #ffffff 75%, #cfcfcf 75%);
  background-size: 8px 8px;
  background-position: 0 0, 4px 4px;
}
.color-swatch input[type="color"] {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.color-hex {
  font-size: 12px;
  opacity: 0.6;
  text-transform: uppercase;
}

.switch-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  cursor: pointer;
}
.switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  width: 36px; height: 20px;
  border: none;
  border-radius: 10px;
  background: var(--agnes-bg-hover);
  cursor: pointer;
  transition: background 0.15s;
  flex-shrink: 0;
}
.switch.on { background: var(--agnes-primary); }
.switch-knob {
  display: block;
  width: 14px; height: 14px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  transform: translateX(3px);
  transition: transform 0.15s;
}
.switch.on .switch-knob { transform: translateX(19px); }

.smart-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.smart-desc {
  width: 100%;
  resize: none;
  padding: 8px 10px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: var(--agnes-bg-hover);
  color: inherit;
  font-size: 12px;
  outline: none;
}
.smart-desc:disabled { opacity: 0.55; }
.smart-desc:focus { border-color: var(--agnes-primary); }

.lower-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.lower-label {
  font-size: 12px;
  font-weight: 600;
  opacity: 0.6;
}

.position-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}
.position-btn {
  padding: 6px 0;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font-size: 12px;
  cursor: pointer;
}
.position-btn:hover { background: var(--agnes-bg-hover); }
.position-btn.active { background: var(--agnes-primary); border-color: var(--agnes-primary); color: #fff; }

.preset-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.style-preset {
  position: relative;
  height: 58px;
  padding: 0;
  border: none;
  border-radius: 8px;
  overflow: hidden;
  background: #0d0f15;
  cursor: pointer;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
  transition: box-shadow 0.15s;
}
.style-preset:hover { box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.35); }
.style-preset.active { box-shadow: 0 0 0 2px var(--agnes-primary); }
.preset-thumb {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
}
.preset-name {
  position: absolute;
  left: 0; right: 0; bottom: 4px;
  text-align: center;
  font-size: 11px;
  color: #fff;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.7);
}

.lighting-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  border-top: 1px solid var(--agnes-border);
}

.spacer { flex: 1; }

.lighting-btn-reset {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 8px 14px;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  color: inherit;
  opacity: 0.7;
  font-size: 13px;
}
.lighting-btn-reset:hover { background: var(--agnes-bg-hover); opacity: 1; }

.lighting-btn-copy {
  padding: 8px 16px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  color: inherit;
  font-size: 13px;
}
.lighting-btn-copy:hover { background: var(--agnes-bg-hover); }

.lighting-btn-confirm {
  padding: 8px 20px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--agnes-primary), var(--agnes-accent));
  cursor: pointer;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
}
.lighting-btn-confirm:hover { opacity: 0.9; }
</style>
