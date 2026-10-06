<template>
  <canvas ref="canvasRef" class="clip-media" />
</template>

<script setup lang="ts">
/* =====================================================
 * 片段素材条绘制层（片段块内绝对填充，pointer-events 穿透）
 * - video 轨：缩略图条（媒体帧）或图片位图铺满；audio 轨：音波条
 * - 数据按 asset URL 缓存在 lib/editor-strips；解码失败/无 WebCodecs 静默留空
 * ===================================================== */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useEditorStore } from '@/stores/editor'
import type { EditorClip, TrackKind } from '@/lib/editor-types'
import { getImageBitmap, hasWebCodecs } from '@/lib/editor-media'
import {
  drawImageFill,
  drawThumbStrip,
  drawWaveform,
  ensureThumbs,
  getWaveformPeaks,
  type WavePeaks,
} from '@/lib/editor-strips'

const props = defineProps<{ clip: EditorClip; kind: TrackKind }>()
const store = useEditorStore()
const canvasRef = ref<HTMLCanvasElement | null>(null)

let url: string | null = null
let peaks: WavePeaks | null = null
let bitmap: ImageBitmap | null = null
let rafId = 0
let observer: ResizeObserver | null = null
let loadSeq = 0

function schedule(): void {
  if (rafId || !canvasRef.value) return
  rafId = requestAnimationFrame(() => {
    rafId = 0
    draw()
  })
}

function draw(): void {
  const canvas = canvasRef.value
  if (!canvas || !url) return
  const rect = canvas.getBoundingClientRect()
  if (rect.width < 2 || rect.height < 2) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const pw = Math.min(4096, Math.round(rect.width * dpr))
  const ph = Math.min(4096, Math.max(1, Math.round(rect.height * dpr)))
  if (canvas.width !== pw) canvas.width = pw
  if (canvas.height !== ph) canvas.height = ph
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  if (props.kind === 'audio') {
    if (!peaks) return
    const color = getComputedStyle(canvas).getPropertyValue('--el-color-success').trim() || '#67c23a'
    drawWaveform(ctx, canvas.width, canvas.height, peaks, props.clip, color)
  } else if (props.kind === 'video') {
    const asset = props.clip.assetId != null ? store.assetCache.get(props.clip.assetId) : undefined
    if (asset?.media_type === 'image') {
      if (bitmap) drawImageFill(ctx, canvas.width, canvas.height, bitmap)
    } else {
      const handle = ensureThumbs(url, props.clip, schedule)
      if (handle) drawThumbStrip(ctx, canvas.width, canvas.height, handle, props.clip)
    }
  }
}

async function loadData(): Promise<void> {
  const seq = ++loadSeq
  peaks = null
  bitmap = null
  const assetId = props.clip.assetId
  if (assetId == null) {
    url = null
    return
  }
  const asset = store.assetCache.get(assetId) ?? (await store.fetchAsset(assetId))
  if (seq !== loadSeq) return
  url = asset?.asset_url ?? null
  if (!url) return
  if (props.kind === 'audio') {
    if (hasWebCodecs()) peaks = await getWaveformPeaks(url)
  } else if (props.kind === 'video' && asset?.media_type === 'image') {
    bitmap = await getImageBitmap(url)
  }
  if (seq !== loadSeq) return
  schedule()
}

onMounted(() => {
  observer = new ResizeObserver(schedule)
  if (canvasRef.value) observer.observe(canvasRef.value)
  void loadData()
})

watch(() => props.clip.assetId, () => { void loadData() })
// 命令应用后 clip 引用更换（trim/变速等影响源跨度映射）→ 重绘
watch(() => props.clip, schedule)

onBeforeUnmount(() => {
  if (rafId) cancelAnimationFrame(rafId)
  rafId = 0
  observer?.disconnect()
  observer = null
})
</script>

<style scoped>
.clip-media {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
  pointer-events: none;
  z-index: 0;
}
</style>
