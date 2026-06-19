<!-- =====================================================
     蒙版编辑对话框
     - 在图片上用画笔涂抹选择编辑区域
     - 生成 mask base64 用于 image2image 局部编辑
     ===================================================== -->

<template>
  <teleport to="body">
    <div v-if="visible" class="mask-edit-overlay" @click.self="$emit('cancel')">
      <div class="mask-edit-dialog" :style="dialogStyle">
        <!-- 标题栏 -->
        <div class="mask-header">
          <span class="mask-title">蒙版编辑</span>
          <button class="mask-close" @click="$emit('cancel')">
            <X :size="18" />
          </button>
        </div>

        <!-- 画布区域 -->
        <div class="mask-canvas-area">
          <canvas ref="canvasRef"
            @pointerdown="startDraw"
            @pointermove="draw"
            @pointerup="stopDraw"
            @pointerleave="stopDraw" />
        </div>

        <!-- 工具栏 -->
        <div class="mask-tools">
          <label class="mask-tool-label">
            画笔大小
            <input type="range" v-model.number="brushSize" min="5" max="80" step="5" />
            <span>{{ brushSize }}px</span>
          </label>
          <button class="mask-tool-btn" @click="clearMask">
            <Eraser :size="16" /> 清除
          </button>
        </div>

        <!-- 提示词输入 -->
        <div class="mask-prompt-area">
          <textarea v-model="prompt"
            placeholder="输入要编辑的内容描述，如：将背景改为星空"
            rows="2" />
        </div>

        <!-- 操作按钮 -->
        <div class="mask-actions">
          <button class="mask-btn-cancel" @click="$emit('cancel')">取消</button>
          <button class="mask-btn-confirm" :disabled="!hasMask || !prompt.trim()"
            @click="confirm">
            开始编辑
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { X, Eraser } from 'lucide-vue-next'

const props = defineProps({
  visible: { type: Boolean, default: false },
  imageUrl: { type: String, default: '' },
  theme: { type: Object, required: true },
})

const emit = defineEmits(['confirm', 'cancel'])

const canvasRef = ref(null)
const brushSize = ref(30)
const prompt = ref('')
const isDrawing = ref(false)
const hasMask = ref(false)
let ctx = null
let imageEl = null

// 画布尺寸
const CANVAS_MAX_WIDTH = 600
const CANVAS_MAX_HEIGHT = 400

const dialogStyle = ref({})
const maskCanvas = ref(null) // 离屏 mask canvas

watch(() => props.visible, async (val) => {
  if (val) {
    prompt.value = ''
    hasMask.value = false
    await nextTick()
    await initCanvas()
    dialogStyle.value = {
      background: props.theme.toolbar.panel,
      borderColor: props.theme.toolbar.border,
      color: props.theme.node.text,
    }
  }
})

async function initCanvas() {
  const canvas = canvasRef.value
  if (!canvas || !props.imageUrl) return

  // 加载图片
  imageEl = new Image()
  imageEl.crossOrigin = 'anonymous'
  imageEl.onload = () => {
    // 计算画布尺寸（保持比例）
    let w = imageEl.width
    let h = imageEl.height
    if (w > CANVAS_MAX_WIDTH) {
      h = h * (CANVAS_MAX_WIDTH / w)
      w = CANVAS_MAX_WIDTH
    }
    if (h > CANVAS_MAX_HEIGHT) {
      w = w * (CANVAS_MAX_HEIGHT / h)
      h = CANVAS_MAX_HEIGHT
    }
    canvas.width = w
    canvas.height = h

    ctx = canvas.getContext('2d')
    // 绘制图片（半透明显示）
    ctx.globalAlpha = 0.7
    ctx.drawImage(imageEl, 0, 0, w, h)
    ctx.globalAlpha = 1

    // 创建离屏 mask canvas（纯黑白）
    maskCanvas.value = document.createElement('canvas')
    maskCanvas.value.width = imageEl.width
    maskCanvas.value.height = imageEl.height
    const maskCtx = maskCanvas.value.getContext('2d')
    maskCtx.fillStyle = '#000'
    maskCtx.fillRect(0, 0, imageEl.width, imageEl.height)
  }
  imageEl.src = props.imageUrl
}

function getCanvasPos(event) {
  const canvas = canvasRef.value
  const rect = canvas.getBoundingClientRect()
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  }
}

function startDraw(event) {
  isDrawing.value = true
  draw(event)
}

function draw(event) {
  if (!isDrawing.value || !ctx) return
  const { x, y } = getCanvasPos(event)

  // 在显示画布上画半透明红色（标识选中区域）
  ctx.globalCompositeOperation = 'source-over'
  ctx.fillStyle = 'rgba(255, 100, 100, 0.5)'
  ctx.beginPath()
  ctx.arc(x, y, brushSize.value / 2, 0, Math.PI * 2)
  ctx.fill()

  // 在离屏 mask canvas 上画纯白色（按原始图片尺寸缩放）
  if (maskCanvas.value && imageEl) {
    const maskCtx = maskCanvas.value.getContext('2d')
    const scaleX = imageEl.width / canvasRef.value.width
    const scaleY = imageEl.height / canvasRef.value.height
    maskCtx.fillStyle = '#fff'
    maskCtx.beginPath()
    maskCtx.arc(x * scaleX, y * scaleY, (brushSize.value / 2) * scaleX, 0, Math.PI * 2)
    maskCtx.fill()
  }

  hasMask.value = true
}

function stopDraw() {
  isDrawing.value = false
}

function clearMask() {
  if (!ctx || !canvasRef.value) return
  // 清除显示画布
  ctx.clearRect(0, 0, canvasRef.value.width, canvasRef.value.height)
  ctx.globalAlpha = 0.7
  ctx.drawImage(imageEl, 0, 0, canvasRef.value.width, canvasRef.value.height)
  ctx.globalAlpha = 1

  // 清除 mask canvas
  if (maskCanvas.value) {
    const maskCtx = maskCanvas.value.getContext('2d')
    maskCtx.fillStyle = '#000'
    maskCtx.fillRect(0, 0, maskCanvas.value.width, maskCanvas.value.height)
  }
  hasMask.value = false
}

function confirm() {
  if (!hasMask.value || !prompt.value.trim()) return

  // 生成 mask base64
  const maskBase64 = maskCanvas.value.toDataURL('image/png')

  emit('confirm', {
    mask: maskBase64,
    prompt: prompt.value.trim(),
  })
}
</script>

<style scoped>
.mask-edit-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.mask-edit-dialog {
  width: 680px;
  max-width: 90vw;
  border: 1px solid;
  border-radius: 16px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.mask-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(128, 128, 128, 0.15);
}

.mask-title {
  font-size: 16px;
  font-weight: 600;
}

.mask-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  color: inherit;
  opacity: 0.6;
}

.mask-close:hover {
  opacity: 1;
  background: rgba(128, 128, 128, 0.15);
}

.mask-canvas-area {
  padding: 20px;
  display: flex;
  justify-content: center;
  background: rgba(0, 0, 0, 0.2);
}

.mask-canvas-area canvas {
  cursor: crosshair;
  border-radius: 8px;
  max-width: 100%;
}

.mask-tools {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
  border-top: 1px solid rgba(128, 128, 128, 0.1);
}

.mask-tool-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  opacity: 0.8;
}

.mask-tool-label input[type="range"] {
  width: 120px;
}

.mask-tool-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: 1px solid rgba(128, 128, 128, 0.2);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  color: inherit;
  font-size: 13px;
}

.mask-tool-btn:hover {
  background: rgba(128, 128, 128, 0.1);
}

.mask-prompt-area {
  padding: 12px 20px;
}

.mask-prompt-area textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid rgba(128, 128, 128, 0.2);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.15);
  color: inherit;
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
  outline: none;
}

.mask-prompt-area textarea:focus {
  border-color: #6b9cff;
}

.mask-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid rgba(128, 128, 128, 0.1);
}

.mask-btn-cancel {
  padding: 8px 20px;
  border: 1px solid rgba(128, 128, 128, 0.2);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  color: inherit;
  font-size: 14px;
}

.mask-btn-cancel:hover {
  background: rgba(128, 128, 128, 0.1);
}

.mask-btn-confirm {
  padding: 8px 20px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, #6b9cff, #a78bff);
  cursor: pointer;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
}

.mask-btn-confirm:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.mask-btn-confirm:not(:disabled):hover {
  opacity: 0.9;
}
</style>
