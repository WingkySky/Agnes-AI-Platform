<!-- =====================================================
     图片放大对话框
     - 选择目标长边尺寸（1K/2K/4K）
     - 选择放大算法（高清插值/双线性/最近邻）
     - 确认时输出 { targetLongEdge, algorithm }
     ===================================================== -->

<template>
  <teleport to="body">
    <div v-if="visible" class="upscale-overlay" @click.self="$emit('cancel')">
      <div class="upscale-dialog" :style="dialogStyle">
        <!-- 标题栏 -->
        <div class="upscale-header">
          <span class="upscale-title">{{ t('canvas.imageOps.upscaleTitle') }}</span>
          <button class="upscale-close" @click="$emit('cancel')">
            <X :size="18" />
          </button>
        </div>

        <!-- 主体 -->
        <div class="upscale-body">
          <!-- 原图信息 -->
          <div class="upscale-info" v-if="imgW > 0">
            {{ t('canvas.imageOps.originalSize') }}: {{ imgW }} × {{ imgH }}
            ({{ t('canvas.imageOps.longEdge') }}: {{ Math.max(imgW, imgH) }}px)
          </div>

          <!-- 目标尺寸选择 -->
          <div class="upscale-section">
            <label class="section-label">{{ t('canvas.imageOps.targetSize') }}</label>
            <div class="size-options">
              <button v-for="opt in sizeOptions" :key="opt.value"
                class="size-option"
                :class="{ active: targetLongEdge === opt.value, disabled: opt.disabled }"
                :disabled="opt.disabled"
                @click="targetLongEdge = opt.value">
                <span class="size-label">{{ opt.label }}</span>
                <span class="size-desc">{{ opt.value }}px</span>
              </button>
            </div>
          </div>

          <!-- 算法选择 -->
          <div class="upscale-section">
            <label class="section-label">{{ t('canvas.imageOps.algorithm') }}</label>
            <div class="algo-options">
              <button v-for="opt in algoOptions" :key="opt.value"
                class="algo-option"
                :class="{ active: algorithm === opt.value }"
                @click="algorithm = opt.value">
                <span class="algo-label">{{ opt.label }}</span>
                <span class="algo-desc">{{ opt.desc }}</span>
              </button>
            </div>
          </div>

          <!-- 输出预览 -->
          <div class="upscale-preview" v-if="outputW > 0">
            {{ t('canvas.imageOps.outputSize') }}: {{ outputW }} × {{ outputH }}
            <span class="upscale-scale">({{ scaleLabel }})</span>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="upscale-actions">
          <button class="upscale-btn-cancel" @click="$emit('cancel')">{{ t('canvas.imageOps.cancel') }}</button>
          <button class="upscale-btn-confirm" :disabled="!canConfirm" @click="confirm">
            {{ t('canvas.imageOps.confirmUpscale') }}
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
import { getImageSize } from '@/lib/canvas-image-ops'

const { t } = useI18n()

const props = defineProps({
  visible: { type: Boolean, default: false },
  imageUrl: { type: String, default: '' },
  theme: { type: Object, required: true },
})

const emit = defineEmits(['confirm', 'cancel'])

const targetLongEdge = ref(2048)
const algorithm = ref<'high' | 'bilinear' | 'nearest'>('high')
const imgW = ref(0)
const imgH = ref(0)
const dialogStyle = ref({})

const sizeOptions = computed(() => {
  const longEdge = Math.max(imgW.value, imgH.value)
  return [
    { label: '1K', value: 1024, disabled: longEdge >= 1024 },
    { label: '2K', value: 2048, disabled: longEdge >= 2048 },
    { label: '4K', value: 4096, disabled: longEdge >= 4096 },
  ]
})

const algoOptions = computed(() => [
  { label: t('canvas.imageOps.algoHigh'), value: 'high' as const, desc: t('canvas.imageOps.algoHighDesc') },
  { label: t('canvas.imageOps.algoBilinear'), value: 'bilinear' as const, desc: t('canvas.imageOps.algoBilinearDesc') },
  { label: t('canvas.imageOps.algoNearest'), value: 'nearest' as const, desc: t('canvas.imageOps.algoNearestDesc') },
])

const outputW = computed(() => {
  const longEdge = Math.max(imgW.value, imgH.value)
  if (longEdge === 0) return 0
  const scale = targetLongEdge.value / longEdge
  return Math.round(imgW.value * scale)
})

const outputH = computed(() => {
  const longEdge = Math.max(imgW.value, imgH.value)
  if (longEdge === 0) return 0
  const scale = targetLongEdge.value / longEdge
  return Math.round(imgH.value * scale)
})

const scaleLabel = computed(() => {
  const longEdge = Math.max(imgW.value, imgH.value)
  if (longEdge === 0) return ''
  const scale = targetLongEdge.value / longEdge
  return `${scale.toFixed(1)}x`
})

const canConfirm = computed(() => {
  const longEdge = Math.max(imgW.value, imgH.value)
  return longEdge > 0 && targetLongEdge.value > longEdge
})

watch(() => props.visible, async (val) => {
  if (val) {
    targetLongEdge.value = 2048
    algorithm.value = 'high'
    imgW.value = 0
    imgH.value = 0
    await nextTick()
    dialogStyle.value = {
      // 弹窗需要不透明背景，避免与下方画布混在一起（toolbar.panel 是半透明的）
      background: props.theme.toolbar.panel.startsWith('rgba(15,') ? '#0f1626' : '#ffffff',
      borderColor: props.theme.toolbar.border,
      color: props.theme.node.text,
    }
    // 用 getImageSize 统一获取尺寸（远程 URL 自动走代理，避免 cors 问题）
    try {
      const { width, height } = await getImageSize(props.imageUrl)
      imgW.value = width
      imgH.value = height
      const longEdge = Math.max(width, height)
      if (longEdge >= 2048) targetLongEdge.value = 4096
      else if (longEdge >= 1024) targetLongEdge.value = 2048
      else targetLongEdge.value = 1024
    } catch (err) {
      console.error('[UpscaleDialog] 获取图片尺寸失败:', err)
    }
  }
})

function confirm() {
  if (!canConfirm.value) return
  emit('confirm', { targetLongEdge: targetLongEdge.value, algorithm: algorithm.value })
}
</script>

<style scoped>
.upscale-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: var(--agnes-overlay-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.upscale-dialog {
  width: 560px;
  max-width: 90vw;
  border: 1px solid;
  border-radius: 16px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--agnes-bg-dialog); /* 不透明背景，避免与画布内容混在一起 */
}

.upscale-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--agnes-border);
}

.upscale-title { font-size: 16px; font-weight: 600; }

.upscale-close {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px;
  border: none; border-radius: 8px;
  background: transparent; cursor: pointer;
  color: inherit; opacity: 0.6;
}
.upscale-close:hover { opacity: 1; background: var(--agnes-bg-hover); }

.upscale-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.upscale-info {
  font-size: 13px;
  opacity: 0.7;
  padding: 8px 12px;
  background: var(--agnes-bg-hover);
  border-radius: 8px;
}

.upscale-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-label {
  font-size: 14px;
  font-weight: 500;
}

.size-options {
  display: flex;
  gap: 12px;
}

.size-option {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 16px;
  border: 1px solid var(--agnes-border);
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  color: inherit;
  transition: all 0.15s;
}

.size-option:hover:not(.disabled) {
  border-color: var(--agnes-primary);
}

.size-option.active {
  border-color: var(--agnes-primary);
  background: rgba(var(--agnes-primary-rgb, 64, 158, 255), 0.1);
}

.size-option.disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.size-label { font-size: 18px; font-weight: 600; }
.size-desc { font-size: 12px; opacity: 0.6; }

.algo-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.algo-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid var(--agnes-border);
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  color: inherit;
  text-align: left;
  transition: all 0.15s;
}

.algo-option:hover { border-color: var(--agnes-primary); }

.algo-option.active {
  border-color: var(--agnes-primary);
  background: rgba(var(--agnes-primary-rgb, 64, 158, 255), 0.1);
}

.algo-label { font-size: 14px; font-weight: 500; min-width: 80px; }
.algo-desc { font-size: 12px; opacity: 0.6; }

.upscale-preview {
  font-size: 13px;
  padding: 8px 12px;
  background: var(--agnes-bg-hover);
  border-radius: 8px;
}

.upscale-scale {
  color: var(--agnes-primary);
  font-weight: 600;
  margin-left: 8px;
}

.upscale-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--agnes-border);
}

.upscale-btn-cancel {
  padding: 8px 20px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  color: inherit;
  font-size: 14px;
}
.upscale-btn-cancel:hover { background: var(--agnes-bg-hover); }

.upscale-btn-confirm {
  padding: 8px 20px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--agnes-primary), var(--agnes-accent));
  cursor: pointer;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
}
.upscale-btn-confirm:disabled { opacity: 0.4; cursor: not-allowed; }
.upscale-btn-confirm:not(:disabled):hover { opacity: 0.9; }
</style>
