<!-- =====================================================
     AI 多角度对话框
     - 调整水平角度/俯仰角度/镜头距离/广角
     - 左侧用 CSS perspective 实时预览方向（仅预览）
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

        <!-- 主体：左侧预览 + 右侧配置 -->
        <div class="angle-body">
          <!-- 左侧：3D 预览 -->
          <div class="angle-preview-area">
            <div class="angle-preview-box">
              <img :src="imageUrl"
                class="angle-preview-img"
                :style="previewStyle" />
            </div>
            <div class="angle-preview-hint">{{ t('canvas.imageOps.previewHint') }}</div>
          </div>

          <!-- 右侧：参数配置 -->
          <div class="angle-config">
            <!-- 水平角度 -->
            <div class="param-row">
              <label>{{ t('canvas.imageOps.horizontalAngle') }}</label>
              <input type="range" v-model.number="horizontalAngle" min="-60" max="60" step="1" />
              <span class="param-value">{{ horizontalAngle }}°</span>
            </div>
            <!-- 俯仰角度 -->
            <div class="param-row">
              <label>{{ t('canvas.imageOps.pitchAngle') }}</label>
              <input type="range" v-model.number="pitchAngle" min="-45" max="45" step="1" />
              <span class="param-value">{{ pitchAngle }}°</span>
            </div>
            <!-- 镜头距离 -->
            <div class="param-row">
              <label>{{ t('canvas.imageOps.cameraDistance') }}</label>
              <input type="range" v-model.number="cameraDistance" min="1" max="10" step="0.1" />
              <span class="param-value">{{ cameraDistance.toFixed(1) }}</span>
            </div>
            <!-- 广角镜头 -->
            <div class="param-row">
              <label>{{ t('canvas.imageOps.lensType') }}</label>
              <div class="segmented">
                <button :class="{ active: !wideAngle }" @click="wideAngle = false">
                  {{ t('canvas.imageOps.standardLens') }}
                </button>
                <button :class="{ active: wideAngle }" @click="wideAngle = true">
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
import { X } from 'lucide-vue-next'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const props = defineProps({
  visible: { type: Boolean, default: false },
  imageUrl: { type: String, default: '' },
  theme: { type: Object, required: true },
})

const emit = defineEmits(['confirm', 'cancel'])

const horizontalAngle = ref(0)
const pitchAngle = ref(9)
const cameraDistance = ref(4.8)
const wideAngle = ref(false)
const dialogStyle = ref({})

// CSS 3D 预览样式（仅预览方向，不作为最终结果）
const previewStyle = computed(() => ({
  transform: `perspective(520px) rotateY(${horizontalAngle.value}deg) rotateX(${-pitchAngle.value}deg) scale(${1 / (cameraDistance.value / 4)})`,
  transition: 'transform 0.1s ease-out',
}))

// 构造 AI 多角度 prompt
const generatedPrompt = computed(() => {
  const hDir = horizontalAngle.value > 0
    ? t('canvas.imageOps.dirRight', { angle: horizontalAngle.value })
    : horizontalAngle.value < 0
      ? t('canvas.imageOps.dirLeft', { angle: Math.abs(horizontalAngle.value) })
      : t('canvas.imageOps.dirFront')
  const pDir = pitchAngle.value > 0
    ? t('canvas.imageOps.dirDown', { angle: pitchAngle.value })
    : pitchAngle.value < 0
      ? t('canvas.imageOps.dirUp', { angle: Math.abs(pitchAngle.value) })
      : t('canvas.imageOps.dirLevel')
  const lens = wideAngle.value
    ? t('canvas.imageOps.wideAngleLens')
    : t('canvas.imageOps.standardLens')
  return t('canvas.imageOps.anglePromptTemplate', {
    horizontal: hDir,
    pitch: pDir,
    distance: cameraDistance.value.toFixed(1),
    lens,
  })
})

watch(() => props.visible, async (val) => {
  if (val) {
    horizontalAngle.value = 0
    pitchAngle.value = 9
    cameraDistance.value = 4.8
    wideAngle.value = false
    await nextTick()
    dialogStyle.value = {
      // 弹窗需要不透明背景，避免与下方画布混在一起（toolbar.panel 是半透明的）
      background: props.theme.toolbar.panel.startsWith('rgba(15,') ? '#0f1626' : '#ffffff',
      borderColor: props.theme.toolbar.border,
      color: props.theme.node.text,
    }
  }
})

function confirm() {
  emit('confirm', { prompt: generatedPrompt.value })
}
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
  background-color: var(--agnes-bg-dialog); /* 不透明背景，避免与画布内容混在一起 */
}

.angle-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
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

.angle-body {
  display: flex;
  gap: 24px;
  padding: 24px;
}

.angle-preview-area {
  width: 280px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.angle-preview-box {
  width: 220px;
  height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--agnes-bg-dark-surface);
  border-radius: 12px;
  overflow: hidden;
}

.angle-preview-img {
  width: 180px;
  height: 180px;
  object-fit: cover;
  border-radius: 12px;
  transform-style: preserve-3d;
}

.angle-preview-hint {
  font-size: 12px;
  opacity: 0.5;
  text-align: center;
}

.angle-config {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.param-row {
  display: grid;
  grid-template-columns: 100px 1fr 50px;
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
  font-size: 13px;
  font-weight: 600;
  text-align: right;
  color: var(--agnes-primary);
}

.segmented {
  display: flex;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  overflow: hidden;
}

.segmented button {
  flex: 1;
  padding: 8px 12px;
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
  gap: 8px;
}

.prompt-preview label {
  font-size: 13px;
  opacity: 0.8;
}

.prompt-text {
  padding: 12px;
  background: var(--agnes-bg-hover);
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  max-height: 100px;
  overflow-y: auto;
}

.angle-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--agnes-border);
}

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
