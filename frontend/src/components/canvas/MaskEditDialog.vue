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

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { X, Eraser } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { loadImage, toBase64IfNeeded } from '@/lib/canvas-image-ops'

const props = defineProps({
  visible: { type: Boolean, default: false },
  imageUrl: { type: String, default: '' },
  theme: { type: Object, required: true },
})

const emit = defineEmits(['confirm', 'cancel'])

const canvasRef = ref<HTMLCanvasElement | null>(null)
const brushSize = ref(30)
const prompt = ref('')
const isDrawing = ref(false)
const hasMask = ref(false)
let ctx: CanvasRenderingContext2D | null = null
let imageEl: HTMLImageElement | null = null
// 预转换的图片 base64（供调用方直接传给 image2image API，避免重复下载）
const loadedImageBase64 = ref<string>('')

// 画布尺寸
const CANVAS_MAX_WIDTH = 600
const CANVAS_MAX_HEIGHT = 400

const dialogStyle = ref({})
const maskCanvas = ref<HTMLCanvasElement | null>(null) // 离屏 mask canvas

// 监听 visible 变化初始化画布
// 注意：外层 CanvasView 用 v-if 控制 MaskEditDialog 挂载，组件每次显示都是全新挂载，
// props.visible 初始即为 true，普通 watch 不会触发，必须加 immediate: true 才能初始化画布
watch(() => props.visible, async (val) => {
  if (val) {
    prompt.value = ''
    hasMask.value = false
    loadedImageBase64.value = ''
    await nextTick()
    await initCanvas()
    dialogStyle.value = {
      // 弹窗需要不透明背景，避免与下方画布混在一起（toolbar.panel 是半透明的）
      background: props.theme.toolbar.panel.startsWith('rgba(15,') ? '#0f1626' : '#ffffff',
      borderColor: props.theme.toolbar.border,
      color: props.theme.node.text,
    }
  }
}, { immediate: true })

async function initCanvas() {
  const canvas = canvasRef.value
  if (!canvas || !props.imageUrl) return

  try {
    // 用统一的 loadImage 加载（远程 URL 自动走代理、自动设置 crossOrigin），
    // 从而避免后续 canvas 像素操作出现 tainted canvas
    imageEl = await loadImage(props.imageUrl)
    // 同时在后台把图片转成 base64，供 confirm 时使用（不阻塞弹窗打开）
    toBase64IfNeeded(props.imageUrl).then((b64) => {
      loadedImageBase64.value = b64
    }).catch(() => { /* 失败时 confirm 时会再转一次 */ })
  } catch (err) {
    console.error('[MaskEditDialog] 图片加载失败:', err)
    ElMessage.error(`蒙版编辑：图片加载失败`)
    return
  }

  if (!imageEl) return
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
  if (!ctx) return
  // 绘制图片（半透明显示）
  ctx.globalAlpha = 0.7
  ctx.drawImage(imageEl, 0, 0, w, h)
  ctx.globalAlpha = 1

  // 创建离屏 mask canvas（纯黑白）
  const maskEl = document.createElement('canvas')
  maskEl.width = imageEl.width
  maskEl.height = imageEl.height
  maskCanvas.value = maskEl
  const maskCtx = maskEl.getContext('2d')
  if (maskCtx) {
    maskCtx.fillStyle = '#000'
    maskCtx.fillRect(0, 0, imageEl.width, imageEl.height)
  }
}

function getCanvasPos(event: PointerEvent) {
  const canvas = canvasRef.value
  if (!canvas) return { x: 0, y: 0 }
  const rect = canvas.getBoundingClientRect()
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  }
}

function startDraw(event: PointerEvent) {
  isDrawing.value = true
  draw(event)
}

function draw(event: PointerEvent) {
  if (!isDrawing.value || !ctx) return
  const { x, y } = getCanvasPos(event)

  // 在显示画布上画半透明红色（标识选中区域）
  ctx.globalCompositeOperation = 'source-over'
  ctx.fillStyle = 'rgba(255, 100, 100, 0.5)'
  ctx.beginPath()
  ctx.arc(x, y, brushSize.value / 2, 0, Math.PI * 2)
  ctx.fill()

  // 在离屏 mask canvas 上画纯白色（按原始图片尺寸缩放）
  const maskEl = maskCanvas.value
  if (maskEl && imageEl && canvasRef.value) {
    const maskCtx = maskEl.getContext('2d')
    if (!maskCtx) return
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
  if (!ctx || !canvasRef.value || !imageEl) return
  // 清除显示画布
  ctx.clearRect(0, 0, canvasRef.value.width, canvasRef.value.height)
  ctx.globalAlpha = 0.7
  ctx.drawImage(imageEl, 0, 0, canvasRef.value.width, canvasRef.value.height)
  ctx.globalAlpha = 1

  // 清除 mask canvas
  const maskEl = maskCanvas.value
  if (maskEl) {
    const maskCtx = maskEl.getContext('2d')
    if (maskCtx) {
      maskCtx.fillStyle = '#000'
      maskCtx.fillRect(0, 0, maskEl.width, maskEl.height)
    }
  }
  hasMask.value = false
}

function confirm() {
  if (!hasMask.value || !prompt.value.trim()) return

  // 生成 mask base64
  const maskBase64 = maskCanvas.value?.toDataURL('image/png') || ''

  emit('confirm', {
    mask: maskBase64,
    // 提供预下载好的 base64 原图，供调用方直接上传 image2image API，
    // 避免再次从远端下载；若失败则回调方还可以回退到原 imageUrl
    base64_image: loadedImageBase64.value || (imageEl && (imageEl as any).src) || '',
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
  background: var(--agnes-overlay-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.mask-edit-dialog {
  width: 980px;
  max-width: 95vw;
  border: 1px solid;
  border-radius: 16px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--agnes-bg-dialog); /* 不透明背景，避免与画布内容混在一起 */
}

.mask-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--agnes-border);
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
  background: var(--agnes-bg-hover);
}

.mask-canvas-area {
  padding: 20px;
  display: flex;
  justify-content: center;
  background: var(--agnes-bg-dark-surface);
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
  border-top: 1px solid var(--agnes-border);
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
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  color: inherit;
  font-size: 13px;
}

.mask-tool-btn:hover {
  background: var(--agnes-bg-hover);
}

.mask-prompt-area {
  padding: 12px 20px;
}

.mask-prompt-area textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.15);
  color: inherit;
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
  outline: none;
}

.mask-prompt-area textarea:focus {
  border-color: var(--agnes-primary);
}

.mask-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--agnes-border);
}

.mask-btn-cancel {
  padding: 8px 20px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  color: inherit;
  font-size: 14px;
}

.mask-btn-cancel:hover {
  background: var(--agnes-bg-hover);
}

.mask-btn-confirm {
  padding: 8px 20px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--agnes-primary), var(--agnes-accent));
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
