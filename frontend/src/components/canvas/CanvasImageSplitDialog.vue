<!-- =====================================================
     图片拆分对话框
     - 选择行列数（1~8），实时预览网格
     - 确认时输出 { rows, cols }
     ===================================================== -->

<template>
  <teleport to="body">
    <div v-if="visible" class="split-overlay" @click.self="$emit('cancel')">
      <div class="split-dialog" :style="dialogStyle">
        <!-- 标题栏 -->
        <div class="split-header">
          <span class="split-title">{{ t('canvas.imageOps.splitTitle') }}</span>
          <button class="split-close" @click="$emit('cancel')">
            <X :size="18" />
          </button>
        </div>

        <!-- 主体：左侧预览 + 右侧配置 -->
        <div class="split-body">
          <!-- 左侧：图片网格预览 -->
          <div class="split-preview-area">
            <div class="split-preview-wrapper">
              <img :src="imageUrl" class="split-preview-img" @load="onImageLoad" />
              <!-- 网格线覆盖层 -->
              <div class="split-grid-overlay">
                <div v-for="r in rows" :key="'r' + r"
                  class="grid-row" :style="{ height: (100 / rows) + '%' }">
                  <div v-for="c in cols" :key="'c' + c"
                    class="grid-cell"
                    :style="{ width: (100 / cols) + '%' }">
                    <span class="cell-label">{{ (r - 1) * cols + c }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 右侧：配置 -->
          <div class="split-config">
            <div class="config-row">
              <label>{{ t('canvas.imageOps.rows') }}</label>
              <div class="number-input">
                <button @click="rows = Math.max(1, rows - 1)">−</button>
                <input type="number" v-model.number="rows" min="1" max="8" />
                <button @click="rows = Math.min(8, rows + 1)">+</button>
              </div>
            </div>
            <div class="config-row">
              <label>{{ t('canvas.imageOps.cols') }}</label>
              <div class="number-input">
                <button @click="cols = Math.max(1, cols - 1)">−</button>
                <input type="number" v-model.number="cols" min="1" max="8" />
                <button @click="cols = Math.min(8, cols + 1)">+</button>
              </div>
            </div>

            <div class="split-summary">
              <div>{{ t('canvas.imageOps.totalPieces') }}: <strong>{{ rows * cols }}</strong></div>
              <div v-if="imgW > 0">{{ t('canvas.imageOps.pieceSize') }}: ~{{ Math.floor(imgW / cols) }} × {{ Math.floor(imgH / rows) }}</div>
            </div>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="split-actions">
          <button class="split-btn-cancel" @click="$emit('cancel')">{{ t('canvas.imageOps.cancel') }}</button>
          <button class="split-btn-confirm" @click="confirm">
            {{ t('canvas.imageOps.confirmSplit') }}
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { X } from 'lucide-vue-next'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const props = defineProps({
  visible: { type: Boolean, default: false },
  imageUrl: { type: String, default: '' },
  theme: { type: Object, required: true },
})

const emit = defineEmits(['confirm', 'cancel'])

const rows = ref(2)
const cols = ref(2)
const imgW = ref(0)
const imgH = ref(0)
const dialogStyle = ref({})

watch(() => props.visible, async (val) => {
  if (val) {
    rows.value = 2
    cols.value = 2
    await nextTick()
    dialogStyle.value = {
      // 弹窗需要不透明背景，避免与下方画布混在一起（toolbar.panel 是半透明的）
      background: props.theme.toolbar.panel.startsWith('rgba(15,') ? '#0f1626' : '#ffffff',
      borderColor: props.theme.toolbar.border,
      color: props.theme.node.text,
    }
  }
})

function onImageLoad(e: Event) {
  const img = e.target as HTMLImageElement
  imgW.value = img.naturalWidth
  imgH.value = img.naturalHeight
}

function confirm() {
  emit('confirm', { rows: rows.value, cols: cols.value })
}
</script>

<style scoped>
.split-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: var(--agnes-overlay-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.split-dialog {
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

.split-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--agnes-border);
}

.split-title { font-size: 16px; font-weight: 600; }

.split-close {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px;
  border: none; border-radius: 8px;
  background: transparent; cursor: pointer;
  color: inherit; opacity: 0.6;
}
.split-close:hover { opacity: 1; background: var(--agnes-bg-hover); }

.split-body {
  display: flex;
  gap: 20px;
  padding: 20px;
}

.split-preview-area {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  background: var(--agnes-bg-dark-surface);
  border-radius: 8px;
  padding: 12px;
}

.split-preview-wrapper {
  position: relative;
  display: inline-block;
  max-width: 100%;
  max-height: 360px;
}

.split-preview-img {
  display: block;
  max-width: 100%;
  max-height: 360px;
  user-select: none;
  -webkit-user-drag: none;
}

.split-grid-overlay {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  display: flex;
  flex-direction: column;
  pointer-events: none;
}

.grid-row {
  display: flex;
  width: 100%;
}

.grid-cell {
  border: 1px solid rgba(255, 255, 255, 0.7);
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
}

.cell-label {
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
}

.split-config {
  width: 200px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.config-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.config-row label {
  font-size: 13px;
  opacity: 0.8;
}

.number-input {
  display: flex;
  align-items: center;
  gap: 0;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  overflow: hidden;
}

.number-input button {
  width: 36px;
  height: 36px;
  border: none;
  background: var(--agnes-bg-hover);
  cursor: pointer;
  color: inherit;
  font-size: 18px;
}

.number-input button:hover { opacity: 0.8; }

.number-input input {
  flex: 1;
  width: 100%;
  height: 36px;
  border: none;
  text-align: center;
  background: transparent;
  color: inherit;
  font-size: 16px;
  outline: none;
  -moz-appearance: textfield;
}
.number-input input::-webkit-outer-spin-button,
.number-input input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.split-summary {
  padding: 12px;
  background: var(--agnes-bg-hover);
  border-radius: 8px;
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.split-summary strong { color: var(--agnes-primary); }

.split-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--agnes-border);
}

.split-btn-cancel {
  padding: 8px 20px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  color: inherit;
  font-size: 14px;
}
.split-btn-cancel:hover { background: var(--agnes-bg-hover); }

.split-btn-confirm {
  padding: 8px 20px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--agnes-primary), var(--agnes-accent));
  cursor: pointer;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
}
.split-btn-confirm:hover { opacity: 0.9; }
</style>
