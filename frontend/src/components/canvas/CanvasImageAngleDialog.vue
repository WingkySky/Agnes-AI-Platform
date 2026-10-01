<!-- =====================================================
     AI 多角度对话框
     - 双模式 CSS 3D 预览：摄像头（轨道环+相机模型绕主体转）/ 天空盒（图片贴立方体六面）
     - 6 个快捷视角预设 + 方向箭头步进 + 预览区拖拽调角度
     - 水平 ±180（可绕到背面）、俯仰 ±60、景别缩放（近景/中景/全景）、标准/广角
     - 确认时输出构造好的 prompt（由 CanvasView 调图生图 API）
     ===================================================== -->

<template>
  <teleport to="body">
    <div v-if="visible" class="angle-overlay" @click.self="$emit('cancel')">
      <div class="angle-dialog" :style="dialogStyle">
        <!-- 标题栏 -->
        <div class="angle-header">
          <span class="angle-title">{{ t('canvas.imageOps.angleTitle') }}</span>
          <button class="angle-close" @click="$emit('cancel')">
            <X :size="18" />
          </button>
        </div>

        <!-- 快捷视角预设 tab -->
        <div class="angle-tabs">
          <button
            class="angle-tab"
            :class="{ active: !activePreset }"
            @click="applyPreset(null)"
          >{{ t('canvas.imageOps.presetTabCustom') }}</button>
          <button
            v-for="preset in ANGLE_PRESETS"
            :key="preset.id"
            class="angle-tab"
            :class="{ active: activePreset?.id === preset.id }"
            @click="applyPreset(preset)"
          >{{ t(preset.labelKey) }}</button>
        </div>

        <!-- 主体：左侧 3D 预览 + 右侧配置 -->
        <div class="angle-body">
          <div class="angle-preview-area">
            <div class="mode-segment">
              <button :class="{ active: mode === 'camera' }" @click="mode = 'camera'">{{ t('canvas.imageOps.previewModeCamera') }}</button>
              <button :class="{ active: mode === 'skybox' }" @click="mode = 'skybox'">{{ t('canvas.imageOps.previewModeSkybox') }}</button>
            </div>

            <!-- 预览舞台：按下拖动调角度 -->
            <div
              class="angle-stage"
              @pointerdown.prevent="startDrag"
              @pointermove="onDrag"
              @pointerup="endDrag"
              @pointercancel="endDrag"
            >
              <!-- 摄像头模式：主体 + 轨道环 + 相机模型 -->
              <div v-if="mode === 'camera'" class="scene3d">
                <div class="orbit-core" :style="coreStyle">
                  <div v-for="deg in orbitDegrees" :key="'y' + deg" class="orbit-ring" :style="{ transform: `rotateY(${deg * 15}deg)` }" />
                  <div v-for="deg in orbitDegrees" :key="'x' + deg" class="orbit-ring" :style="{ transform: `rotateX(${deg * 15}deg)` }" />
                </div>
                <img :src="imageUrl" class="angle-subject" alt="" />
                <div class="cam-pivot" :style="coreStyle">
                  <div class="cam-pos" :style="{ transform: `translate(-50%, -50%) translateZ(${camRadius}px)` }">
                    <Camera :size="20" />
                  </div>
                </div>
              </div>

              <!-- 天空盒模式：图片贴立方体六面 -->
              <div v-else class="scene3d">
                <div class="sky-cube" :style="cubeStyle">
                  <div v-for="face in cubeFaces" :key="face.id" class="sky-face" :class="face.id" :style="face.style">
                    <img :src="imageUrl" alt="" />
                    <span v-if="face.labelKey" class="face-label">{{ t(face.labelKey) }}</span>
                  </div>
                </div>
              </div>

              <!-- 方向箭头 -->
              <button class="stage-arrow up" :title="t('canvas.imageOps.stepUp', { angle: ANGLE_STEP })" @pointerdown.stop @click="step('up')"><ChevronUp :size="16" /></button>
              <button class="stage-arrow down" :title="t('canvas.imageOps.stepDown', { angle: ANGLE_STEP })" @pointerdown.stop @click="step('down')"><ChevronDown :size="16" /></button>
              <button class="stage-arrow left" :title="t('canvas.imageOps.stepLeft', { angle: ANGLE_STEP })" @pointerdown.stop @click="step('left')"><ChevronLeft :size="16" /></button>
              <button class="stage-arrow right" :title="t('canvas.imageOps.stepRight', { angle: ANGLE_STEP })" @pointerdown.stop @click="step('right')"><ChevronRight :size="16" /></button>
            </div>
            <div class="angle-preview-hint">{{ t('canvas.imageOps.previewHint') }}</div>
          </div>

          <!-- 右侧：参数配置 -->
          <div class="angle-config">
            <div class="preset-grid">
              <button
                v-for="preset in ANGLE_PRESETS"
                :key="preset.id"
                class="preset-btn"
                :class="{ active: activePreset?.id === preset.id }"
                @click="applyPreset(preset)"
              >{{ t(preset.labelKey) }}</button>
            </div>

            <div class="param-row">
              <label>{{ t('canvas.imageOps.horizontalAngle') }}</label>
              <input type="range" v-model.number="params.horizontalAngle" :min="ANGLE_LIMITS.rotateMin" :max="ANGLE_LIMITS.rotateMax" :step="ANGLE_STEP" />
              <span class="param-value">{{ params.horizontalAngle }}°</span>
            </div>
            <div class="param-row">
              <label>{{ t('canvas.imageOps.pitchAngle') }}</label>
              <input type="range" v-model.number="params.pitchAngle" :min="ANGLE_LIMITS.tiltMin" :max="ANGLE_LIMITS.tiltMax" :step="ANGLE_STEP" />
              <span class="param-value">{{ params.pitchAngle }}°</span>
            </div>
            <div class="param-row">
              <label>{{ t('canvas.imageOps.cameraDistance') }}</label>
              <input type="range" v-model.number="params.cameraDistance" :min="ANGLE_LIMITS.distanceMin" :max="ANGLE_LIMITS.distanceMax" step="0.1" />
              <span class="param-value">{{ tierLabel }}</span>
            </div>
            <div class="param-row">
              <label>{{ t('canvas.imageOps.lensType') }}</label>
              <div class="segmented">
                <button :class="{ active: !params.wideAngle }" @click="params.wideAngle = false">
                  {{ t('canvas.imageOps.standardLens') }}
                </button>
                <button :class="{ active: params.wideAngle }" @click="params.wideAngle = true">
                  {{ t('canvas.imageOps.wideAngleLens') }}
                </button>
              </div>
            </div>

            <!-- prompt 预览 -->
            <div class="prompt-preview">
              <label>{{ t('canvas.imageOps.generatedPrompt') }}</label>
              <div class="prompt-text">{{ generatedPrompt }}</div>
            </div>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="angle-actions">
          <div class="view-summary">
            <span class="view-label">{{ t('canvas.imageOps.currentView') }}</span>
            <span class="view-name">{{ activePreset ? t(activePreset.labelKey) : t('canvas.imageOps.presetTabCustom') }}</span>
            <span class="view-detail">{{ params.horizontalAngle }}° / {{ params.pitchAngle }}° · {{ params.cameraDistance.toFixed(1) }} {{ tierLabel }}</span>
          </div>
          <button class="angle-btn-reset" @click="resetParams">
            <RotateCcw :size="14" />
            {{ t('canvas.imageOps.resetParams') }}
          </button>
          <button class="angle-btn-cancel" @click="$emit('cancel')">{{ t('canvas.imageOps.cancel') }}</button>
          <button class="angle-btn-confirm" @click="confirm">
            {{ t('canvas.imageOps.confirmAngle') }}
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { X, Camera, RotateCcw, ChevronUp, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { useI18n } from '@/i18n'
import {
  ANGLE_PRESETS, ANGLE_LIMITS, ANGLE_STEP,
  clamp, normalizeAngle, findAnglePreset, distanceTierKey,
  buildAnglePrompt, type AngleParams, type AnglePreset,
} from '@/lib/canvas-angle'

const { t } = useI18n()

const props = defineProps({
  visible: { type: Boolean, default: false },
  imageUrl: { type: String, default: '' },
  theme: { type: Object, required: true },
})

const emit = defineEmits(['confirm', 'cancel'])

const params = ref<AngleParams>({ horizontalAngle: 0, pitchAngle: 0, cameraDistance: 4.8, wideAngle: false })
const mode = ref<'camera' | 'skybox'>('camera')
const dialogStyle = ref<Record<string, string>>({})

/* ---------- 预览区拖拽调角度 ---------- */
const dragging = ref(false)
const dragStart = ref({ x: 0, y: 0, horizontalAngle: 0, pitchAngle: 0 })

/* ---------- 预览 3D 变换 ---------- */
const orbitDegrees = Array.from({ length: 12 }, (_, i) => i)
const cubeSize = 120

const coreStyle = computed(() => ({
  transform: `rotateX(${params.value.pitchAngle}deg) rotateY(${params.value.horizontalAngle}deg)`,
  transition: dragging.value ? 'none' : 'transform 120ms ease-out',
}))

/** 镜头距离 → 相机轨道半径（越近越靠近主体） */
const camRadius = computed(() => 30 + (params.value.cameraDistance - 1) * 9)

const cubeStyle = computed(() => ({
  width: `${cubeSize}px`,
  height: `${cubeSize}px`,
  transform: `translate(-50%, -50%) rotateX(${-params.value.pitchAngle}deg) rotateY(${params.value.horizontalAngle}deg)`,
  transition: dragging.value ? 'none' : 'transform 120ms ease-out',
}))

const half = `${cubeSize / 2}px`
const cubeFaces = [
  { id: 'front', labelKey: '', style: { transform: `translateZ(${half})` } },
  { id: 'back', labelKey: 'canvas.imageOps.faceBack', style: { transform: `rotateY(180deg) translateZ(${half})` } },
  { id: 'right', labelKey: 'canvas.imageOps.faceRight', style: { transform: `rotateY(90deg) translateZ(${half})` } },
  { id: 'left', labelKey: 'canvas.imageOps.faceLeft', style: { transform: `rotateY(-90deg) translateZ(${half})` } },
  { id: 'top', labelKey: 'canvas.imageOps.faceTop', style: { transform: `rotateX(90deg) translateZ(${half})` } },
  { id: 'bottom', labelKey: 'canvas.imageOps.faceBottom', style: { transform: `rotateX(-90deg) translateZ(${half})` } },
]

/* ---------- 参数联动 ---------- */
const activePreset = computed(() => findAnglePreset(params.value.horizontalAngle, params.value.pitchAngle))
const tierLabel = computed(() => t(distanceTierKey(params.value.cameraDistance)))
const generatedPrompt = computed(() => buildAnglePrompt(params.value))

function setHorizontal(value: number) {
  params.value.horizontalAngle = Math.round(normalizeAngle(value))
}
function setPitch(value: number) {
  params.value.pitchAngle = Math.round(clamp(value, ANGLE_LIMITS.tiltMin, ANGLE_LIMITS.tiltMax))
}
function applyPreset(preset: AnglePreset | null) {
  if (!preset) return
  params.value.horizontalAngle = preset.horizontalAngle
  params.value.pitchAngle = preset.pitchAngle
}
function step(dir: 'up' | 'down' | 'left' | 'right') {
  if (dir === 'up') setPitch(params.value.pitchAngle + ANGLE_STEP)
  else if (dir === 'down') setPitch(params.value.pitchAngle - ANGLE_STEP)
  else if (dir === 'left') setHorizontal(params.value.horizontalAngle - ANGLE_STEP)
  else setHorizontal(params.value.horizontalAngle + ANGLE_STEP)
}
function resetParams() {
  params.value = { horizontalAngle: 0, pitchAngle: 0, cameraDistance: 4.8, wideAngle: false }
  mode.value = 'camera'
}

/* ---------- 预览区拖拽调角度 ---------- */
function startDrag(event: PointerEvent) {
  dragging.value = true
  dragStart.value = { x: event.clientX, y: event.clientY, horizontalAngle: params.value.horizontalAngle, pitchAngle: params.value.pitchAngle }
  if (event.currentTarget instanceof HTMLElement) event.currentTarget.setPointerCapture(event.pointerId)
}
function onDrag(event: PointerEvent) {
  if (!dragging.value) return
  const deltaX = event.clientX - dragStart.value.x
  const deltaY = event.clientY - dragStart.value.y
  setHorizontal(dragStart.value.horizontalAngle + deltaX * 1.5)
  setPitch(dragStart.value.pitchAngle - deltaY)
}
function endDrag(event: PointerEvent) {
  dragging.value = false
  if (event.currentTarget instanceof HTMLElement && event.currentTarget.hasPointerCapture(event.pointerId)) {
    event.currentTarget.releasePointerCapture(event.pointerId)
  }
}

function confirm() {
  emit('confirm', { prompt: generatedPrompt.value })
}

watch(() => props.visible, async (val) => {
  if (val) {
    resetParams()
    await nextTick()
    dialogStyle.value = {
      // 弹窗需要不透明背景，避免与下方画布混在一起（toolbar.panel 是半透明的）
      background: props.theme.toolbar.panel.startsWith('rgba(15,') ? '#0f1626' : '#ffffff',
      borderColor: props.theme.toolbar.border,
      color: props.theme.node.text,
    }
  }
})
</script>

<style scoped>
.angle-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: var(--agnes-overlay-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.angle-dialog {
  width: 860px;
  max-width: 90vw;
  border: 1px solid;
  border-radius: 16px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--agnes-bg-dialog);
}

.angle-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--agnes-border);
}

.angle-title { font-size: 16px; font-weight: 600; }

.angle-close {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px;
  border: none; border-radius: 8px;
  background: transparent; cursor: pointer;
  color: inherit; opacity: 0.6;
}
.angle-close:hover { opacity: 1; background: var(--agnes-bg-hover); }

.angle-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 20px 0;
  overflow-x: auto;
}

.angle-tab {
  padding: 5px 12px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  opacity: 0.6;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.angle-tab:hover { background: var(--agnes-bg-hover); }
.angle-tab.active { background: var(--agnes-primary); color: #fff; opacity: 1; }

.angle-body {
  display: flex;
  gap: 20px;
  padding: 16px 20px;
}

.angle-preview-area {
  width: 320px;
  display: flex;
  flex-direction: column;
  gap: 8px;
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

.angle-stage {
  position: relative;
  height: 260px;
  border-radius: 12px;
  background: var(--agnes-bg-dark-surface);
  overflow: hidden;
  cursor: grab;
  touch-action: none;
}
.angle-stage:active { cursor: grabbing; }

.scene3d {
  position: absolute;
  inset: 0;
  perspective: 900px;
}

/* 摄像头模式 */
.orbit-core,
.cam-pivot {
  position: absolute;
  top: 50%; left: 50%;
  width: 0; height: 0;
  transform-style: preserve-3d;
}

.orbit-ring {
  position: absolute;
  top: 0; left: 0;
  width: 150px; height: 150px;
  margin: -75px 0 0 -75px;
  border: 1px dashed var(--agnes-border);
  border-radius: 50%;
  opacity: 0.5;
}

.angle-subject {
  position: absolute;
  top: 50%; left: 50%;
  width: 110px; height: 110px;
  object-fit: cover;
  border-radius: 8px;
  transform: translate(-50%, -50%);
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.4);
}

.cam-pos {
  position: absolute;
  top: 50%; left: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px; height: 34px;
  border-radius: 10px;
  background: var(--agnes-primary);
  color: #fff;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
  transition: transform 120ms ease-out;
}

/* 天空盒模式 */
.sky-cube {
  position: absolute;
  top: 50%; left: 50%;
  transform-style: preserve-3d;
}

.sky-face {
  position: absolute;
  top: 0; left: 0;
  width: 100%; height: 100%;
  overflow: hidden;
  border-radius: 6px;
}
.sky-face img {
  width: 100%; height: 100%;
  object-fit: cover;
  display: block;
}
.sky-face:not(.front) img { filter: brightness(0.35); }
.sky-face:not(.front)::after {
  content: '';
  position: absolute;
  inset: 0;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 6px;
}
.face-label {
  position: absolute;
  left: 0; right: 0; bottom: 6px;
  text-align: center;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.85);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6);
}

/* 方向箭头 */
.stage-arrow {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px; height: 24px;
  border: none;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.35);
  color: #fff;
  cursor: pointer;
  z-index: 2;
}
.stage-arrow:hover { background: var(--agnes-primary); }
.stage-arrow.up { top: 8px; left: 50%; transform: translateX(-50%); }
.stage-arrow.down { bottom: 8px; left: 50%; transform: translateX(-50%); }
.stage-arrow.left { left: 8px; top: 50%; transform: translateY(-50%); }
.stage-arrow.right { right: 8px; top: 50%; transform: translateY(-50%); }

.angle-preview-hint {
  font-size: 12px;
  opacity: 0.5;
  text-align: center;
}

.angle-config {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.preset-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}
.preset-btn {
  padding: 6px 0;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font-size: 12px;
  cursor: pointer;
}
.preset-btn:hover { background: var(--agnes-bg-hover); }
.preset-btn.active { background: var(--agnes-primary); border-color: var(--agnes-primary); color: #fff; }

.param-row {
  display: grid;
  grid-template-columns: 80px 1fr 56px;
  align-items: center;
  gap: 12px;
}

.param-row label {
  font-size: 13px;
  opacity: 0.8;
}

.param-row input[type="range"] {
  width: 100%;
}

.param-value {
  font-size: 12px;
  font-weight: 600;
  text-align: right;
  color: var(--agnes-primary);
  white-space: nowrap;
}

.segmented {
  display: flex;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  overflow: hidden;
}

.segmented button {
  flex: 1;
  padding: 6px 12px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: inherit;
  font-size: 13px;
}

.segmented button.active {
  background: var(--agnes-primary);
  color: #fff;
}

.prompt-preview {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.prompt-preview label {
  font-size: 13px;
  opacity: 0.8;
}

.prompt-text {
  padding: 10px;
  background: var(--agnes-bg-hover);
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.6;
  max-height: 96px;
  overflow-y: auto;
}

.angle-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  border-top: 1px solid var(--agnes-border);
}

.view-summary {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
  margin-right: auto;
}
.view-label { font-size: 12px; opacity: 0.5; }
.view-name { font-size: 13px; font-weight: 600; }
.view-detail { font-size: 12px; opacity: 0.5; white-space: nowrap; }

.angle-btn-reset {
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
.angle-btn-reset:hover { background: var(--agnes-bg-hover); opacity: 1; }

.angle-btn-cancel {
  padding: 8px 20px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  color: inherit;
  font-size: 14px;
}
.angle-btn-cancel:hover { background: var(--agnes-bg-hover); }

.angle-btn-confirm {
  padding: 8px 20px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--agnes-primary), var(--agnes-accent));
  cursor: pointer;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
}
.angle-btn-confirm:hover { opacity: 0.9; }
</style>
