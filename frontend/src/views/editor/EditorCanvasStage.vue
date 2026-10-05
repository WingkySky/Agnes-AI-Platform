<script setup lang="ts">
/* =====================================================
 * canvas 预览路径（WebCodecs 可用时启用）
 * - 画面：mediabunny 逐帧解码 → planFrame 绘制清单 → 2D canvas drawImage
 * - 音频：AudioEngine 统一调度（音频时钟主控），rAF 只读投影时间
 * - 播放头推进/外部 seek 检测/end-of-doc 都在本组件；字幕与控制条在壳层
 * ===================================================== */

import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { AudioBufferSink, CanvasSink } from 'mediabunny'

import { useEditorStore } from '@/stores/editor'
import { planFrame } from '@/lib/editor-compositor'
import { AudioEngine, sourceTimeAt } from '@/lib/editor-audio-engine'
import { clearMediaPool, createAudioSink, createVideoSink, getImageBitmap } from '@/lib/editor-media'
import { clipEnd, type EditorClip } from '@/lib/editor-types'

const store = useEditorStore()

/** 视为外部 seek 的播放头偏差（秒） */
const SEEK_EPS = 0.15
/** 同一请求时刻不重复拉帧 */
const REQ_EPS = 1e-6

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

async function pullFrame(st: VideoFrameState, clip: EditorClip, url: string): Promise<void> {
  const t = sourceTimeAt(clip, store.playhead)
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

// ---------- 绘制 ----------

function drawImageItem(item: { x: number; y: number; w: number; h: number }, src: CanvasImageSource): void {
  if (!ctx2d) return
  ctx2d.drawImage(src, item.x, item.y, item.w, item.h)
}

function draw(): void {
  const canvas = canvasRef.value
  const doc = store.doc
  if (!canvas || !ctx2d || !doc) return
  const version = ++planVersion
  ctx2d.fillStyle = '#000'
  ctx2d.fillRect(0, 0, cssW, cssH)
  const plan = planFrame(doc, store.playhead, cssW, cssH)
  const active = new Set<string>()
  for (const item of plan) {
    if (item.w <= 0 || item.h <= 0) continue
    active.add(item.clipId)
    const asset = store.assetCache.get(item.assetId)
    const url = asset?.asset_url
    if (!url) {
      void store.fetchAsset(item.assetId)
      continue
    }
    if (asset.media_type === 'image') {
      void getImageBitmap(url).then((bmp) => {
        if (bmp && mounted && version === planVersion) drawImageItem(item, bmp)
      })
    } else {
      const clip = doc.clips.find((c) => c.id === item.clipId)
      if (!clip) continue
      const st = ensureVideoState(item.clipId, url)
      if (st.canvas) drawImageItem(item, st.canvas)
      void pullFrame(st, clip, url)
    }
  }
  for (const id of videoStates.keys()) {
    if (!active.has(id)) videoStates.delete(id)
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
  <canvas ref="canvasRef" class="stage-canvas" />
</template>

<style scoped>
.stage-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
</style>
