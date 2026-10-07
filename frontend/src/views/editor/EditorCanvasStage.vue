<script setup lang="ts">
/* =====================================================
 * canvas 预览路径（WebCodecs 可用时启用）
 * - 画面：mediabunny 逐帧解码 → planFrame 绘制清单 → 2D canvas drawImage
 * - 音频：AudioEngine 统一调度（音频时钟主控），rAF 只读投影时间
 * - 画中画直接操作：点选片段、拖动移动、四角等比缩放（松手经
 *   setClipProperty 入撤销栈；几何纯函数在 lib/editor-compositor）
 * - 播放头推进/外部 seek 检测/end-of-doc 都在本组件；字幕与控制条在壳层
 * ===================================================== */

import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { AudioBufferSink, CanvasSink } from 'mediabunny'

import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'
import {
  cornerHit,
  moveRect,
  pickDrawItem,
  planFrame,
  resizeRect,
  type DrawItem,
  type RectCorner,
} from '@/lib/editor-compositor'
import { AudioEngine, sourceTimeAt } from '@/lib/editor-audio-engine'
import { canvasFilterForEffects } from '@/lib/editor-fx-registry'
import { clearMediaPool, createAudioSink, createVideoSink, getImageBitmap } from '@/lib/editor-media'
import { clipEnd, FULL_RECT, type ClipRect, type EditorClip } from '@/lib/editor-types'

const store = useEditorStore()
const { t } = useI18n()

/** 视为外部 seek 的播放头偏差（秒） */
const SEEK_EPS = 0.15
/** 同一请求时刻不重复拉帧 */
const REQ_EPS = 1e-6
/** 角点手柄命中半径 / 绘制半边长（px） */
const HANDLE_HIT_R = 8
const HANDLE_DRAW = 4

const canvasRef = ref<HTMLCanvasElement | null>(null)
let ctx2d: CanvasRenderingContext2D | null = null
let cssW = 0
let cssH = 0
let mounted = true
let planVersion = 0

// ---------- 音频时钟 ----------

let audioCtx: AudioContext | null = null
let engine: AudioEngine | null = null

async function ensureEngine(): Promise<AudioEngine | null> {
  if (!audioCtx) audioCtx = new AudioContext()
  if (audioCtx.state === 'suspended') await audioCtx.resume().catch(() => undefined)
  if (!engine) engine = new AudioEngine(audioCtx)
  return engine
}

async function onPlayToggle(playing: boolean): Promise<void> {
  if (!playing) {
    engine?.stopAll()
    return
  }
  const e = await ensureEngine()
  if (!e) return
  e.anchor(store.playhead)
}

function sinkForEngine(clip: EditorClip): Promise<AudioBufferSink | null> {
  const asset = clip.assetId != null ? store.assetCache.get(clip.assetId) : undefined
  if (!asset?.asset_url) {
    if (clip.assetId != null) void store.fetchAsset(clip.assetId)
    return Promise.resolve(null)
  }
  return createAudioSink(asset.asset_url)
}

watch(() => store.isPlaying, (playing) => void onPlayToggle(playing))

// ---------- 视频帧状态（按 clipId） ----------

interface VideoFrameState {
  url: string | null
  sink: CanvasSink | null
  canvas: HTMLCanvasElement | OffscreenCanvas | null
  reqT: number
  fetching: boolean
}

const videoStates = new Map<string, VideoFrameState>()

function ensureVideoState(clipId: string, url: string): VideoFrameState {
  let st = videoStates.get(clipId)
  if (!st) {
    st = { url: null, sink: null, canvas: null, reqT: -1, fetching: false }
    videoStates.set(clipId, st)
  }
  return st
}

async function pullFrame(st: VideoFrameState, clip: EditorClip, url: string, timelineT: number): Promise<void> {
  // 转场 blend 项在播放头未到其 start 时拉帧：钳到片段起点（显示后段开头内容，
  // 与渲染端 xfade 链中后段自其 trim 起播的语义对齐）
  const t = sourceTimeAt(clip, Math.max(timelineT, clip.start))
  if (st.fetching || (st.canvas && Math.abs(t - st.reqT) < REQ_EPS)) return
  st.fetching = true
  try {
    if (!st.sink || st.url !== url) {
      st.sink = await createVideoSink(url)
      st.url = url
      st.canvas = null
      if (!st.sink) return
    }
    const frame = await st.sink.getCanvas(t)
    if (frame) st.canvas = frame.canvas
    st.reqT = t
  } catch {
    st.canvas = null // 解码失败画黑块（预览层静默）
  } finally {
    st.fetching = false
  }
}

// ---------- 画中画直接操作（拖动/缩放） ----------

interface DragState {
  clipId: string
  mode: 'move' | RectCorner
  startRect: ClipRect
  startX: number
  startY: number
}

let drag: DragState | null = null
/** 拖拽中的矩形视觉覆盖（pointerup 才入命令栈） */
let dragRect: ClipRect | null = null

function pointerPos(e: PointerEvent, canvas: HTMLCanvasElement): { px: number; py: number } {
  const rect = canvas.getBoundingClientRect()
  return { px: e.clientX - rect.left, py: e.clientY - rect.top }
}

function currentPlan(): DrawItem[] {
  const doc = store.doc
  return doc ? planFrame(doc, store.playhead, cssW, cssH) : []
}

function onPointerDown(e: PointerEvent): void {
  const canvas = canvasRef.value
  if (!canvas || !store.doc) return
  const { px, py } = pointerPos(e, canvas)
  const plan = currentPlan()
  const selItem = store.selectedClipId ? plan.find((i) => i.clipId === store.selectedClipId) : undefined
  const corner = selItem ? cornerHit(selItem, px, py, HANDLE_HIT_R) : null
  const item = corner && selItem ? selItem : pickDrawItem(plan, px, py)
  if (!item) {
    store.select(null)
    return
  }
  if (item.clipId !== store.selectedClipId) store.select(item.clipId)
  const clip = store.doc.clips.find((c) => c.id === item.clipId)
  if (!clip) return
  drag = {
    clipId: item.clipId,
    mode: corner ?? 'move',
    startRect: { ...(clip.props.rect ?? FULL_RECT) },
    startX: px,
    startY: py,
  }
  dragRect = { ...drag.startRect }
  canvas.setPointerCapture(e.pointerId)
}

function onPointerMove(e: PointerEvent): void {
  const canvas = canvasRef.value
  if (!canvas) return
  const { px, py } = pointerPos(e, canvas)
  if (drag && dragRect) {
    const dx = (px - drag.startX) / cssW
    const dy = (py - drag.startY) / cssH
    dragRect = drag.mode === 'move'
      ? moveRect(drag.startRect, dx, dy)
      : resizeRect(drag.startRect, drag.mode, dx, dy)
    return
  }
  updateCursor(canvas, px, py)
}

function onPointerUp(): void {
  if (!drag) return
  const clipId = drag.clipId
  const final = dragRect
  const start = drag.startRect
  drag = null
  dragRect = null
  const changed = final
    && (final.x !== start.x || final.y !== start.y || final.w !== start.w || final.h !== start.h)
  if (final && changed) {
    store.applyOrToast(
      { op: 'setClipProperty', payload: { clipId, props: { rect: final } } },
      t('editor.ops.setClipProperty'),
    )
  }
}

function updateCursor(canvas: HTMLCanvasElement, px: number, py: number): void {
  const plan = currentPlan()
  const selItem = store.selectedClipId ? plan.find((i) => i.clipId === store.selectedClipId) : undefined
  const corner = selItem ? cornerHit(selItem, px, py, HANDLE_HIT_R) : null
  if (corner) {
    canvas.style.cursor = corner === 'nw' || corner === 'se' ? 'nwse-resize' : 'nesw-resize'
    return
  }
  canvas.style.cursor = pickDrawItem(plan, px, py) ? 'move' : 'default'
}

// ---------- 绘制 ----------

function drawImageItem(item: { x: number; y: number; w: number; h: number }, src: CanvasImageSource): void {
  if (!ctx2d) return
  ctx2d.drawImage(src, item.x, item.y, item.w, item.h)
}

/** 转场混合绘制后段（前段已在画布上）：crossfade=alpha 混合 / fade=黑场插值 / wipe=擦除显现 */
function drawBlendItem(item: DrawItem, src: CanvasImageSource): void {
  if (!ctx2d) return
  const blend = item.blend!
  if (blend.type === 'crossfade') {
    ctx2d.globalAlpha = blend.progress
    ctx2d.drawImage(src, item.x, item.y, item.w, item.h)
    ctx2d.globalAlpha = 1
    return
  }
  if (blend.type === 'wipe') {
    ctx2d.save()
    ctx2d.beginPath()
    ctx2d.rect(item.x, item.y, item.w * blend.progress, item.h)
    ctx2d.clip()
    ctx2d.drawImage(src, item.x, item.y, item.w, item.h)
    ctx2d.restore()
    return
  }
  // fade：前半 前段→黑，后半 黑→后段（fadeblack 语义近似）
  if (blend.progress < 0.5) {
    ctx2d.globalAlpha = blend.progress * 2
    ctx2d.fillStyle = '#000'
    ctx2d.fillRect(item.x, item.y, item.w, item.h)
    ctx2d.globalAlpha = 1
  } else {
    ctx2d.fillStyle = '#000'
    ctx2d.fillRect(item.x, item.y, item.w, item.h)
    ctx2d.globalAlpha = (blend.progress - 0.5) * 2
    ctx2d.drawImage(src, item.x, item.y, item.w, item.h)
    ctx2d.globalAlpha = 1
  }
}

/** 施加片段效果器滤镜（canvas filter 与渲染端 ffmpeg 滤镜同源，见 editor-fx-registry） */
function applyEffectFilter(clip: EditorClip | undefined): void {
  if (!ctx2d) return
  const filter = clip ? canvasFilterForEffects(clip.props.effects) : null
  ctx2d.filter = filter ?? 'none'
}

function draw(): void {
  const canvas = canvasRef.value
  const doc = store.doc
  if (!canvas || !ctx2d || !doc) return
  const version = ++planVersion
  ctx2d.fillStyle = '#000'
  ctx2d.fillRect(0, 0, cssW, cssH)
  const plan = planFrame(doc, store.playhead, cssW, cssH)
  // 拖拽中的片段用覆盖矩形替换（文档在 pointerup 才更新）
  let items = plan
  if (drag && dragRect) {
    const clipId = drag.clipId
    const r = dragRect
    items = plan.map((it) => it.clipId === clipId
      ? { ...it, x: r.x * cssW, y: r.y * cssH, w: r.w * cssW, h: r.h * cssH }
      : it)
  }
  const active = new Set<string>()
  for (const item of items) {
    if (item.w <= 0 || item.h <= 0) continue
    active.add(item.clipId)
    const asset = store.assetCache.get(item.assetId)
    const url = asset?.asset_url
    if (!url) {
      void store.fetchAsset(item.assetId)
      continue
    }
    const itemClip = doc.clips.find((c) => c.id === item.clipId)
    if (asset.media_type === 'image') {
      void getImageBitmap(url).then((bmp) => {
        if (bmp && mounted && version === planVersion) {
          applyEffectFilter(itemClip)
          if (item.blend) drawBlendItem(item, bmp)
          else drawImageItem(item, bmp)
          ctx2d!.filter = 'none'
        }
      })
    } else {
      if (!itemClip) continue
      const st = ensureVideoState(item.clipId, url)
      if (st.canvas) {
        applyEffectFilter(itemClip)
        if (item.blend) drawBlendItem(item, st.canvas)
        else drawImageItem(item, st.canvas)
        ctx2d.filter = 'none'
      }
      void pullFrame(st, itemClip, url, store.playhead)
    }
  }
  drawSelection(items)
  for (const id of videoStates.keys()) {
    if (!active.has(id)) videoStates.delete(id)
  }
}

/** 选中片段描边 + 四角手柄 */
function drawSelection(items: DrawItem[]): void {
  if (!ctx2d || !store.selectedClipId) return
  const sel = items.find((i) => i.clipId === store.selectedClipId)
  if (!sel || sel.w <= 0 || sel.h <= 0) return
  ctx2d.strokeStyle = 'rgba(255,255,255,0.9)'
  ctx2d.lineWidth = 1
  ctx2d.strokeRect(sel.x + 0.5, sel.y + 0.5, sel.w - 1, sel.h - 1)
  ctx2d.fillStyle = '#fff'
  for (const [cx, cy] of [
    [sel.x, sel.y],
    [sel.x + sel.w, sel.y],
    [sel.x, sel.y + sel.h],
    [sel.x + sel.w, sel.y + sel.h],
  ]) {
    ctx2d.fillRect(cx - HANDLE_DRAW, cy - HANDLE_DRAW, HANDLE_DRAW * 2, HANDLE_DRAW * 2)
  }
}

// ---------- 播放循环 ----------

function docTotal(doc: { clips: EditorClip[] }): number {
  return Math.max(1, ...doc.clips.map(clipEnd))
}

function tick(): void {
  if (!mounted) return
  const doc = store.doc
  if (doc && store.isPlaying && engine) {
    const projected = engine.now()
    if (Number.isFinite(projected)) {
      if (Math.abs(store.playhead - projected) > SEEK_EPS) {
        // 外部 seek（时间线点击/方向键）：重锚 + 重建调度
        engine.anchor(store.playhead)
        engine.stopAll()
      } else {
        const total = docTotal(doc)
        store.playhead = Math.min(projected, total)
        if (projected >= total) store.isPlaying = false
      }
    }
    if (store.isPlaying) engine.tick(doc, store.playhead, sinkForEngine)
  }
  draw()
  requestAnimationFrame(tick)
}

// ---------- 尺寸 ----------

function resize(): void {
  const canvas = canvasRef.value
  if (!canvas) return
  const dpr = window.devicePixelRatio || 1
  cssW = canvas.clientWidth
  cssH = canvas.clientHeight
  canvas.width = Math.max(1, Math.round(cssW * dpr))
  canvas.height = Math.max(1, Math.round(cssH * dpr))
  ctx2d = canvas.getContext('2d')
  ctx2d?.setTransform(dpr, 0, 0, dpr, 0, 0)
}

let observer: ResizeObserver | null = null

onMounted(() => {
  resize()
  observer = new ResizeObserver(resize)
  if (canvasRef.value) observer.observe(canvasRef.value)
  requestAnimationFrame(tick)
})

onBeforeUnmount(() => {
  mounted = false
  observer?.disconnect()
  engine?.stopAll()
  void audioCtx?.close().catch(() => undefined)
  audioCtx = null
  engine = null
  clearMediaPool()
})
</script>

<template>
  <canvas
    ref="canvasRef"
    class="stage-canvas"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
  />
</template>

<style scoped>
.stage-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  touch-action: none;
}
</style>
