<!-- =====================================================
     表情控制对话框（多角色一次生成）
     - 阶段：识别人脸 → 选择人脸（可连续选多个；识别失败/补充可手动框选）→ 编辑情绪 → 生成
     - 每个选中人脸=一个角色，角色各自持有情绪预设；情绪盘编辑当前激活角色
     - 「应用到全部」把当前情绪套到所有角色；「添加角色」回到选择阶段继续加人
     - 确认时裁切联合编辑区+各角色脸部参考图并组装多角色提示词（由 CanvasView 一次图生图 + 逐脸椭圆羽化合成）
     ===================================================== -->

<template>
  <teleport to="body">
    <div v-if="visible" class="emotion-overlay" @click.self="$emit('cancel')">
      <div class="emotion-dialog" :style="dialogStyle">
        <!-- 标题栏 -->
        <div class="emotion-header">
          <span class="emotion-title">{{ t('canvas.imageOps.emotionTitle') }}</span>
          <button class="emotion-close" :aria-label="t('canvas.imageOps.cancel')" @click="$emit('cancel')">
            <X :size="18" />
          </button>
        </div>

        <!-- 图片舞台：人脸识别框 / 手动框选 -->
        <div class="emotion-stage">
          <div
            class="image-box"
            :class="{ 'is-manual': stage === 'manual' }"
            :style="imageBoxStyle"
            @pointerdown="onManualStart"
            @pointermove="onManualMove"
            @pointerup="onManualEnd"
            @pointercancel="onManualEnd"
          >
            <img :src="sourceDataUrl" class="stage-image" draggable="false" :aria-label="t('canvas.imageOps.emotionTitle')" />
            <svg v-if="stage !== 'editing'" class="dim-layer" :viewBox="`0 0 ${imageSize.width} ${imageSize.height}`" preserveAspectRatio="none" aria-hidden="true">
              <defs>
                <mask :id="`emotion-face-mask-${uid}`">
                  <rect width="100%" height="100%" fill="white" />
                  <rect v-for="face in displayFaces" :key="face.id" :x="face.x" :y="face.y" :width="face.width" :height="face.height" :rx="Math.min(face.width, face.height) * 0.16" fill="black" />
                </mask>
              </defs>
              <rect width="100%" height="100%" fill="rgba(0,0,0,.38)" :mask="`url(#emotion-face-mask-${uid})`" />
            </svg>
            <button
              v-for="face in displayFaces"
              :key="face.id"
              type="button"
              class="face-box"
              :class="{ active: isActiveFace(face) }"
              :style="faceBoxStyle(face)"
              :aria-label="t('canvas.imageOps.emotionSelectThisFace')"
              @pointerdown.stop
              @click.stop="onFaceClick(face)"
            >
              <span v-if="characterOfFace(face)" class="face-tag">{{ characterOfFace(face)!.name }}</span>
            </button>
            <div v-if="manualDraft" class="manual-draft" :style="faceBoxStyle(manualDraft)" />
          </div>
        </div>

        <!-- 状态/提示条（编辑阶段由角色行承担信息，隐藏省出高度） -->
        <div v-if="stage !== 'editing'" class="status-bar">
          <Loader2 v-if="stage === 'detecting'" class="spin" :size="16" />
          <ScanFace v-else :size="16" />
          <span class="status-text">{{ statusText }}</span>
          <span class="spacer" />
          <button v-if="stage === 'selecting'" class="mini-btn" @click="beginManual">{{ t('canvas.imageOps.emotionManualSelect') }}</button>
          <button v-if="stage === 'manual'" class="mini-btn" @click="cancelManual">{{ t('canvas.imageOps.emotionCancelManual') }}</button>
        </div>

        <!-- 编辑区：角色切换 + 实时预览 + 情绪盘 -->
        <div v-if="stage === 'editing' && characters.length" class="editing-area">
          <div class="character-row">
            <button
              v-for="character in characters"
              :key="character.id"
              type="button"
              class="character-chip"
              :class="{ active: character.id === activeCharacterId }"
              @click="activeCharacterId = character.id"
            >
              <span class="face-thumbnail"><img :src="sourceDataUrl" :style="thumbnailStyle(character.faceBox)" draggable="false" alt="" /></span>
              <span class="chip-text">{{ character.name }} · {{ t(character.preset.labelKey) }}</span>
              <span class="chip-remove" role="button" :aria-label="t('canvas.imageOps.emotionRemoveCharacter')" @click.stop="removeCharacter(character.id)">
                <X :size="12" />
              </span>
            </button>
            <button class="mini-btn" @click="stage = 'selecting'">{{ t('canvas.imageOps.emotionAddCharacter') }}</button>
            <button v-if="characters.length > 1" class="mini-btn" @click="applyToAll">{{ t('canvas.imageOps.emotionApplyAll') }}</button>
          </div>

          <div class="emotion-grid">
            <div class="preview-box">
              <canvas ref="previewCanvas" class="preview-canvas" />
              <span v-if="previewFailed" class="preview-label">{{ t('canvas.imageOps.emotionPreviewFailed') }}</span>
              <span v-else class="preview-label">{{ t('canvas.imageOps.emotionPreviewLabel') }} · {{ t(preset.labelKey) }}</span>
            </div>
            <div class="pad-box">
              <span class="pad-axis pad-top">{{ t('canvas.imageOps.emotionPadUp') }}</span>
              <span class="pad-axis pad-bottom">{{ t('canvas.imageOps.emotionPadDown') }}</span>
              <span class="pad-axis pad-left">{{ t('canvas.imageOps.emotionPadClose') }}</span>
              <span class="pad-axis pad-right">{{ t('canvas.imageOps.emotionPadDistant') }}</span>
              <div class="pad-grid" role="slider" :aria-label="t('canvas.imageOps.emotionPadAria')" :aria-valuetext="t(preset.labelKey)">
                <button
                  v-for="item in EMOTION_PRESETS"
                  :key="item.id"
                  type="button"
                  class="pad-dot"
                  :class="{ active: item.id === preset.id, onpath: item.intimacy === preset.intimacy || item.arousal === preset.arousal }"
                  :aria-label="t(item.labelKey)"
                  :title="t(item.labelKey)"
                  @click="preset = item"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="emotion-actions">
          <span class="mood-label">{{ t('canvas.imageOps.emotionMoodLabel') }}: <b>{{ t(preset.labelKey) }}</b><template v-if="activeCharacter"> · {{ activeCharacter.name }}</template></span>
          <span class="error-text">{{ error }}</span>
          <span class="spacer" />
          <button class="emotion-btn-confirm" :disabled="!characters.length" @click="confirmGeneration">
            {{ t('canvas.imageOps.emotionGenerate') }}
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { X, ScanFace, Loader2 } from 'lucide-vue-next'
import { useI18n } from '@/i18n'
import {
  EMOTION_PRESETS, NEUTRAL_EMOTION_PRESET, emotionBlendshapes, emotionPresetLabel,
  type EmotionFaceBox, type EmotionPreset, type EmotionGeneratePayload,
} from '@/lib/canvas-emotion'
import { detectFaces } from '@/lib/canvas-face-detection'
import { createEmotionFacePreview, type EmotionFacePreview } from '@/lib/canvas-emotion-preview'
import { toBase64IfNeeded } from '@/lib/canvas-image-ops'

const { t } = useI18n()

const props = defineProps({
  visible: { type: Boolean, default: false },
  imageUrl: { type: String, default: '' },
  theme: { type: Object, required: true },
})

const emit = defineEmits(['confirm', 'cancel'])

type Stage = 'detecting' | 'selecting' | 'manual' | 'editing'
interface EmotionCharacter {
  id: string
  name: string
  faceBox: EmotionFaceBox
  preset: EmotionPreset
}

const uid = Math.random().toString(36).slice(2, 8)
const stage = ref<Stage>('detecting')
const sourceDataUrl = ref('')
const imageSize = ref({ width: 0, height: 0 })
const faces = ref<EmotionFaceBox[]>([])
const characters = ref<EmotionCharacter[]>([])
const activeCharacterId = ref('')
const manualDraft = ref<EmotionFaceBox | null>(null)
const error = ref('')
const dialogStyle = ref<Record<string, string>>({})

const previewCanvas = ref<HTMLCanvasElement | null>(null)
const previewFailed = ref('')
let preview: EmotionFacePreview | null = null
// 预览实例绑定创建时的 canvas；编辑区因 v-if 重挂会换新 canvas，此时必须重建实例
let previewBoundCanvas: HTMLCanvasElement | null = null

const activeCharacter = computed(() => characters.value.find(c => c.id === activeCharacterId.value))

/** 情绪盘读写当前激活角色的预设 */
const preset = computed<EmotionPreset>({
  get: () => activeCharacter.value?.preset ?? NEUTRAL_EMOTION_PRESET,
  set: (value) => {
    if (activeCharacter.value) activeCharacter.value.preset = value
  },
})

/** 编辑阶段展示全部已选角色人脸框（高亮当前），选择/框选阶段展示全部识别框 */
const displayFaces = computed(() => {
  if (stage.value === 'editing') return characters.value.map(c => c.faceBox)
  return faces.value
})

const statusText = computed(() => {
  if (stage.value === 'detecting') return t('canvas.imageOps.emotionDetecting')
  if (stage.value === 'manual') return t('canvas.imageOps.emotionManualHint')
  if (stage.value === 'selecting') {
    return error.value || (faces.value.length
      ? t('canvas.imageOps.emotionSelectFace', { n: faces.value.length })
      : t('canvas.imageOps.emotionNoFace'))
  }
  return ''
})

/** 图片展示框：按图片比例适配，最高 300px */
const imageBoxStyle = computed(() => {
  const { width, height } = imageSize.value
  if (!width || !height) return { height: '200px' }
  return { aspectRatio: `${width} / ${height}`, maxHeight: '300px', maxWidth: '100%' }
})

function faceBoxStyle(face: EmotionFaceBox) {
  return {
    left: `${(face.x / Math.max(1, imageSize.value.width)) * 100}%`,
    top: `${(face.y / Math.max(1, imageSize.value.height)) * 100}%`,
    width: `${(face.width / Math.max(1, imageSize.value.width)) * 100}%`,
    height: `${(face.height / Math.max(1, imageSize.value.height)) * 100}%`,
  }
}

function thumbnailStyle(box: EmotionFaceBox) {
  return {
    width: `${(imageSize.value.width / Math.max(1, box.width)) * 100}%`,
    height: `${(imageSize.value.height / Math.max(1, box.height)) * 100}%`,
    left: `${-(box.x / Math.max(1, box.width)) * 100}%`,
    top: `${-(box.y / Math.max(1, box.height)) * 100}%`,
  }
}

function characterOfFace(face: EmotionFaceBox) {
  return characters.value.find(c => sameFace(c.faceBox, face))
}

function isActiveFace(face: EmotionFaceBox) {
  return characterOfFace(face)?.id === activeCharacterId.value
}

/** 编辑阶段点击人脸框=切换激活角色，选择阶段=加入/激活角色 */
function onFaceClick(face: EmotionFaceBox) {
  if (stage.value === 'editing') {
    const character = characterOfFace(face)
    if (character) activeCharacterId.value = character.id
    return
  }
  selectFace(face)
}

/* ---------- 初始化：图片转 dataURL → 读取尺寸 → 人脸检测 ---------- */

async function initDialog() {
  stage.value = 'detecting'
  error.value = ''
  faces.value = []
  characters.value = []
  activeCharacterId.value = ''
  manualDraft.value = null
  dialogStyle.value = {
    background: props.theme.toolbar.panel.startsWith('rgba(15,') ? '#0f1626' : '#ffffff',
    borderColor: props.theme.toolbar.border,
    color: props.theme.node.text,
  }
  if (!props.imageUrl) return
  try {
    sourceDataUrl.value = await toBase64IfNeeded(props.imageUrl)
    imageSize.value = await readImageSize(sourceDataUrl.value)
    const result = await detectFaces(sourceDataUrl.value)
    imageSize.value = { width: result.imageWidth, height: result.imageHeight }
    faces.value = result.faces
    stage.value = 'selecting'
  } catch (reason) {
    stage.value = 'selecting'
    error.value = reason instanceof Error ? `${reason.message}，${t('canvas.imageOps.emotionNoFace')}` : t('canvas.imageOps.emotionDetectFailed')
  }
}

function readImageSize(src: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight })
    image.onerror = () => reject(new Error(t('canvas.imageOps.emotionImageReadFailed')))
    image.src = src
  })
}

onMounted(() => { void initDialog() })
watch(() => props.visible, (val) => { if (val) void initDialog() })

/* ---------- 人脸选择与手动框选 ---------- */

function selectFace(face: EmotionFaceBox) {
  const existing = characters.value.find(c => sameFace(c.faceBox, face))
  if (existing) {
    activeCharacterId.value = existing.id
  } else {
    const character: EmotionCharacter = {
      id: `character-${face.id}`,
      name: t('canvas.imageOps.emotionCharacterN', { n: characters.value.length + 1 }),
      faceBox: face,
      preset: NEUTRAL_EMOTION_PRESET,
    }
    characters.value = [...characters.value, character]
    activeCharacterId.value = character.id
  }
  stage.value = 'editing'
  error.value = ''
}

function removeCharacter(id: string) {
  characters.value = characters.value.filter(c => c.id !== id)
  if (activeCharacterId.value === id) {
    activeCharacterId.value = characters.value[0]?.id || ''
    if (!characters.value.length) stage.value = 'selecting'
  }
}

/** 把当前角色的情绪套用到全部角色（统一调整） */
function applyToAll() {
  const current = preset.value
  characters.value = characters.value.map(c => ({ ...c, preset: current }))
}

function beginManual() {
  stage.value = 'manual'
  manualDraft.value = null
  error.value = ''
}

function cancelManual() {
  stage.value = characters.value.length ? 'editing' : 'selecting'
  manualDraft.value = null
}

const dragStart = ref<{ x: number; y: number } | null>(null)

function pointerToImage(event: PointerEvent) {
  const bounds = (event.currentTarget as HTMLElement).getBoundingClientRect()
  return {
    x: ((event.clientX - bounds.left) / Math.max(1, bounds.width)) * imageSize.value.width,
    y: ((event.clientY - bounds.top) / Math.max(1, bounds.height)) * imageSize.value.height,
  }
}

function onManualStart(event: PointerEvent) {
  if (stage.value !== 'manual') return
  event.preventDefault()
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  dragStart.value = pointerToImage(event)
  manualDraft.value = { id: `manual-${Date.now()}`, ...dragStart.value, width: 0, height: 0, source: 'manual' }
}

function onManualMove(event: PointerEvent) {
  if (stage.value !== 'manual' || !dragStart.value) return
  const current = pointerToImage(event)
  manualDraft.value = {
    id: manualDraft.value?.id || `manual-${Date.now()}`,
    x: Math.min(dragStart.value.x, current.x),
    y: Math.min(dragStart.value.y, current.y),
    width: Math.abs(current.x - dragStart.value.x),
    height: Math.abs(current.y - dragStart.value.y),
    source: 'manual',
  }
}

function onManualEnd(event: PointerEvent) {
  if (stage.value !== 'manual' || !dragStart.value) return
  const start = dragStart.value
  dragStart.value = null
  if (event.currentTarget instanceof HTMLElement && event.currentTarget.hasPointerCapture(event.pointerId)) {
    event.currentTarget.releasePointerCapture(event.pointerId)
  }
  const current = pointerToImage(event)
  const box: EmotionFaceBox = {
    id: manualDraft.value?.id || `manual-${Date.now()}`,
    x: Math.min(start.x, current.x),
    y: Math.min(start.y, current.y),
    width: Math.abs(current.x - start.x),
    height: Math.abs(current.y - start.y),
    source: 'manual',
  }
  const minW = Math.max(18, imageSize.value.width * 0.025)
  const minH = Math.max(18, imageSize.value.height * 0.025)
  if (box.width >= minW && box.height >= minH) {
    faces.value = [...faces.value, box]
    selectFace(box)
  }
  manualDraft.value = null
}

function sameFace(left: EmotionFaceBox, right: EmotionFaceBox) {
  return left.id === right.id
    || (Math.abs(left.x - right.x) < 1 && Math.abs(left.y - right.y) < 1 && Math.abs(left.width - right.width) < 1 && Math.abs(left.height - right.height) < 1)
}

/* ---------- 实时预览（跟随当前激活角色；canvas 重挂后重建实例） ---------- */

async function ensurePreview() {
  if (stage.value !== 'editing') return
  await nextTick()
  const canvas = previewCanvas.value
  if (!canvas) return
  if (preview && previewBoundCanvas !== canvas) {
    preview.dispose()
    preview = null
  }
  if (!preview) {
    previewBoundCanvas = canvas
    previewFailed.value = ''
    try {
      preview = createEmotionFacePreview(canvas, () => { previewFailed.value = '1' })
    } catch {
      previewFailed.value = '1'
    }
  }
  preview?.setShapes(emotionBlendshapes(preset.value))
}

watch([stage, activeCharacterId], () => { void ensurePreview() })

watch(preset, (value) => {
  preview?.setShapes(emotionBlendshapes(value))
})

/* ---------- 确认生成（逐脸紧裁切由画布侧执行，这里只上交角色与情绪） ---------- */

function confirmGeneration() {
  if (!characters.value.length || !imageSize.value.width) return
  const payload: EmotionGeneratePayload = {
    characters: characters.value.map(c => ({
      name: c.name,
      presetId: c.preset.id,
      label: emotionPresetLabel(c.preset),
      intimacy: c.preset.intimacy,
      arousal: c.preset.arousal,
      faceBox: c.faceBox,
    })),
    imageWidth: imageSize.value.width,
    imageHeight: imageSize.value.height,
  }
  emit('confirm', payload)
}

onBeforeUnmount(() => {
  preview?.dispose()
  preview = null
  previewBoundCanvas = null
})
</script>

<style scoped>
.emotion-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: var(--agnes-overlay-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.emotion-dialog {
  width: 640px;
  max-width: 92vw;
  max-height: 92vh;
  border: 1px solid;
  border-radius: 16px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  overflow: hidden auto;
  background-color: var(--agnes-bg-dialog);
}

.emotion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px 10px;
}

.emotion-title { font-size: 16px; font-weight: 600; }

.emotion-close {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px;
  border: none; border-radius: 8px;
  background: transparent; cursor: pointer;
  color: inherit; opacity: 0.6;
}
.emotion-close:hover { opacity: 1; background: var(--agnes-bg-hover); }

.emotion-stage {
  display: flex;
  justify-content: center;
  padding: 0 20px;
}

.image-box {
  position: relative;
  overflow: hidden;
  border-radius: 10px;
  background: var(--agnes-bg-dark-surface);
}
.image-box.is-manual { cursor: crosshair; touch-action: none; }

.stage-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  user-select: none;
}

.dim-layer {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.face-box {
  position: absolute;
  border: 2px solid rgba(255, 255, 255, 0.92);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  padding: 0;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.18);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.face-box:hover { border-color: var(--agnes-primary); }
.face-box.active {
  border-color: var(--agnes-primary);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--agnes-primary) 30%, transparent);
}

.face-tag {
  position: absolute;
  top: -22px;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(20, 20, 22, 0.82);
  color: #fff;
}

.manual-draft {
  position: absolute;
  border: 2px dashed #fff;
  border-radius: 8px;
  pointer-events: none;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.16);
}

.status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  font-size: 13px;
  min-height: 40px;
}
.status-text { opacity: 0.85; }
.spin { animation: emotion-spin 1s linear infinite; }
@keyframes emotion-spin { to { transform: rotate(360deg); } }

.mini-btn {
  padding: 5px 12px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font-size: 12px;
  cursor: pointer;
  flex-shrink: 0;
}
.mini-btn:hover { background: var(--agnes-bg-hover); }
.mini-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.mini-btn:disabled:hover { background: transparent; }

.editing-area {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 0 20px 10px;
}

.character-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  /* 角色很多时限高纵向滚动，保证情绪盘不被挤出视口 */
  max-height: 118px;
  overflow-y: auto;
}

.character-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px 4px 4px;
  border: 1px solid var(--agnes-border);
  border-radius: 10px;
  background: transparent;
  color: inherit;
  font-size: 12px;
  cursor: pointer;
  flex-shrink: 0;
}
.character-chip.active { border-color: var(--agnes-primary); background: var(--agnes-bg-hover); }

.chip-text { white-space: nowrap; }

.chip-remove {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  opacity: 0.5;
}
.chip-remove:hover { opacity: 1; background: var(--agnes-bg-hover); }

.face-thumbnail {
  position: relative;
  display: block;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.2);
  flex-shrink: 0;
}
.face-thumbnail img {
  position: absolute;
  max-width: none;
  pointer-events: none;
}

.emotion-grid {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 12px;
}

.preview-box {
  position: relative;
  height: 220px;
  border-radius: 12px;
  background: var(--agnes-bg-dark-surface);
  overflow: hidden;
}
.preview-canvas { width: 100%; height: 100%; display: block; }
.preview-label {
  position: absolute;
  left: 10px;
  bottom: 8px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.72);
}

.pad-box {
  position: relative;
  border: 1px solid var(--agnes-border);
  border-radius: 12px;
  padding: 22px 26px;
}
.pad-axis {
  position: absolute;
  font-size: 11px;
  opacity: 0.55;
}
.pad-top { top: 5px; left: 0; right: 0; text-align: center; }
.pad-bottom { bottom: 5px; left: 0; right: 0; text-align: center; }
.pad-left { left: 7px; top: 50%; transform: translateY(-50%); writing-mode: vertical-rl; }
.pad-right { right: 7px; top: 50%; transform: translateY(-50%); writing-mode: vertical-rl; }

.pad-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  grid-template-rows: repeat(5, 1fr);
  height: 168px;
}

.pad-dot {
  position: relative;
  width: 14px;
  height: 14px;
  margin: auto;
  border: none;
  border-radius: 50%;
  background: var(--agnes-border);
  cursor: pointer;
  padding: 0;
  transition: transform 0.15s, background 0.15s, box-shadow 0.15s;
}
.pad-dot.onpath { background: color-mix(in srgb, var(--agnes-primary) 45%, var(--agnes-border)); }
.pad-dot:hover { transform: scale(1.35); }
.pad-dot.active {
  transform: scale(1.6);
  background: var(--agnes-primary);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--agnes-primary) 22%, transparent);
}

.emotion-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px 16px;
  border-top: 1px solid var(--agnes-border);
}

.mood-label { font-size: 13px; opacity: 0.75; white-space: nowrap; }
.error-text {
  font-size: 12px;
  color: var(--agnes-error);
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.spacer { flex: 1; }

.emotion-btn-confirm {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--agnes-primary), var(--agnes-accent));
  cursor: pointer;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
}
.emotion-btn-confirm:hover { opacity: 0.9; }
.emotion-btn-confirm:disabled { cursor: not-allowed; opacity: 0.55; }
</style>
