/* =====================================================
 * 片段素材条数据层：音波峰值 + 缩略图帧（asset 级缓存）
 * - 缓存按 asset URL 复用：同素材多片段只解码一次，缩放/trim 只重绘不重解码
 * - 解码任务走全局串行队列，让位预览解码（共享 editor-media Input 池）
 * - 失败负缓存避免重试风暴；全部静默降级（不弹错），由调用方回落到纯色块
 * ===================================================== */

import type { CanvasSink } from 'mediabunny'
import { createAudioSink, createThumbSink, probeDuration } from './editor-media'
import { type EditorClip, sourceSpan } from './editor-types'

/** 缓存上限（每类各自独立 LRU，按源 URL 计） */
const CACHE_LIMIT = 40

// ---------- 音波峰值 ----------

export interface WavePeaks {
  mins: Float32Array
  maxs: Float32Array
  /** 每桶覆盖的源时长（秒） */
  bucketSec: number
}

/** 峰值桶数：每秒 50 桶，256~4096 钳制 */
export function bucketCountFor(duration: number): number {
  return Math.min(4096, Math.max(256, Math.ceil(duration * 50)))
}

/** 把 [srcFrom,srcTo] 源跨度重采样为 columns 列振幅（0~1，列内聚合取峰值；空桶计 0） */
export function resamplePeaks(peaks: WavePeaks, srcFrom: number, srcTo: number, columns: number): Float32Array {
  const out = new Float32Array(Math.max(0, columns))
  const total = peaks.mins.length
  if (columns <= 0 || srcTo <= srcFrom || total === 0) return out
  for (let c = 0; c < columns; c++) {
    const s0 = srcFrom + (srcTo - srcFrom) * (c / columns)
    const s1 = srcFrom + (srcTo - srcFrom) * ((c + 1) / columns)
    const b0 = Math.max(0, Math.floor(s0 / peaks.bucketSec))
    const b1 = Math.min(total, Math.max(b0 + 1, Math.ceil(s1 / peaks.bucketSec)))
    let peak = 0
    for (let b = b0; b < b1; b++) {
      if (peaks.maxs[b] < peaks.mins[b]) continue // 空桶（无样本覆盖）
      peak = Math.max(peak, Math.abs(peaks.mins[b]), Math.abs(peaks.maxs[b]))
    }
    out[c] = peak
  }
  return out
}

async function computePeaks(url: string): Promise<WavePeaks | null> {
  const duration = await probeDuration(url)
  if (!(duration > 0)) return null
  const sink = await createAudioSink(url)
  if (!sink) return null
  const count = bucketCountFor(duration)
  const mins = new Float32Array(count).fill(1)
  const maxs = new Float32Array(count).fill(-1)
  const bucketSec = duration / count
  try {
    for await (const wb of sink.buffers()) {
      const data = wb.buffer.getChannelData(0)
      const rate = wb.buffer.sampleRate
      for (let i = 0; i < data.length; i++) {
        const b = Math.min(count - 1, Math.max(0, Math.floor((wb.timestamp + i / rate) / bucketSec)))
        const v = data[i]
        if (v < mins[b]) mins[b] = v
        if (v > maxs[b]) maxs[b] = v
      }
    }
  } catch {
    return null
  }
  return { mins, maxs, bucketSec }
}

const peaksCache = new Map<string, Promise<WavePeaks | null>>()

/** 音波峰值（失败负缓存 resolve null） */
export function getWaveformPeaks(url: string): Promise<WavePeaks | null> {
  const cached = peaksCache.get(url)
  if (cached) {
    peaksCache.delete(url)
    peaksCache.set(url, cached) // LRU touch
    return cached
  }
  const promise = computePeaks(url)
  peaksCache.set(url, promise)
  while (peaksCache.size > CACHE_LIMIT) {
    const oldest = peaksCache.keys().next().value
    if (oldest === undefined) break
    peaksCache.delete(oldest)
  }
  return promise
}

// ---------- 缩略图帧 ----------

/** 缩略图网格步长：每源约 24 帧，0.5~4s 钳制 */
export function thumbStep(duration: number): number {
  if (!(duration > 0)) return 1
  return Math.min(4, Math.max(0.5, duration / 24))
}

/** 覆盖 [srcFrom,srcTo] 的网格时刻（0 起步长对齐；tile [t, t+step) 与跨度相交） */
export function gridIndices(srcFrom: number, srcTo: number, step: number): number[] {
  if (!(step > 0) || srcTo <= Math.max(0, srcFrom)) return []
  const i0 = Math.floor(Math.max(0, srcFrom) / step)
  const i1 = Math.max(i0, Math.floor((srcTo - 1e-6) / step))
  const out: number[] = []
  for (let i = i0; i <= i1; i++) out.push(i * step)
  return out
}

/** 网格时刻 → 缓存键（毫秒整型，消浮点误差） */
export function thumbKey(t: number): number {
  return Math.round(t * 1000)
}

export interface ThumbSource {
  step: number
  ready: boolean
  sink: CanvasSink | null
  sinkTried: boolean
  preparing?: Promise<void>
  /** gridKey → 位图；null = 取帧失败的负缓存 */
  frames: Map<number, ImageBitmap | null>
  inflight: Set<number>
  waiters: Set<() => void>
}

const thumbSources = new Map<string, ThumbSource>()

function getSource(url: string): ThumbSource {
  const existing = thumbSources.get(url)
  if (existing) {
    thumbSources.delete(url)
    thumbSources.set(url, existing) // LRU touch
    return existing
  }
  const src: ThumbSource = {
    step: 0,
    ready: false,
    sink: null,
    sinkTried: false,
    frames: new Map(),
    inflight: new Set(),
    waiters: new Set(),
  }
  thumbSources.set(url, src)
  while (thumbSources.size > CACHE_LIMIT) {
    const oldest = thumbSources.keys().next().value
    if (oldest === undefined) break
    const evicted = thumbSources.get(oldest)
    thumbSources.delete(oldest)
    for (const bmp of evicted?.frames.values() ?? []) bmp?.close()
  }
  return src
}

function notifySource(src: ThumbSource): void {
  const waiters = [...src.waiters]
  src.waiters.clear()
  for (const w of waiters) w()
}

async function prepareSource(src: ThumbSource, url: string): Promise<void> {
  if (src.ready || src.preparing) {
    await src.preparing
    return
  }
  src.preparing = probeDuration(url)
    .then((duration) => {
      src.step = thumbStep(duration)
      src.ready = duration > 0
      notifySource(src)
    })
    .catch(() => {
      src.ready = false
      notifySource(src)
    })
    .finally(() => {
      src.preparing = undefined
    })
  await src.preparing
}

/** 取帧任务入全局串行队列（一次一个，让位预览解码） */
let queueTail: Promise<void> = Promise.resolve()
function enqueue(task: () => Promise<void>): void {
  queueTail = queueTail.then(task, task).catch(() => undefined)
}

async function toBitmap(canvas: HTMLCanvasElement | OffscreenCanvas): Promise<ImageBitmap | null> {
  try {
    return await createImageBitmap(canvas)
  } catch {
    return null
  }
}

/** 确保覆盖片段源跨度的网格帧就绪（缺帧入队，就绪/失败都回调 onReady）；未探测完时长返回 null */
export function ensureThumbs(url: string, clip: EditorClip, onReady: () => void): ThumbSource | null {
  const src = getSource(url)
  if (!src.ready) {
    src.waiters.add(onReady)
    void prepareSource(src, url)
    return null
  }
  const srcTo = clip.trimStart + sourceSpan(clip)
  for (const t of gridIndices(Math.max(0, clip.trimStart), srcTo, src.step)) {
    const key = thumbKey(t)
    if (src.frames.has(key) || src.inflight.has(key)) continue
    src.inflight.add(key)
    enqueue(async () => {
      const s = thumbSources.get(url)
      if (!s) return
      try {
        if (!s.sink && !s.sinkTried) {
          s.sink = await createThumbSink(url)
          s.sinkTried = true
        }
        if (!s.sink) {
          s.frames.set(key, null)
        } else {
          const wc = await s.sink.getCanvas(t)
          s.frames.set(key, wc ? await toBitmap(wc.canvas) : null)
        }
      } catch {
        s.frames.set(key, null)
      } finally {
        s.inflight.delete(key)
        notifySource(s)
      }
    })
  }
  return src
}

// ---------- 绘制（设备像素坐标系，缩放由 canvas.width 决定） ----------

function drawCover(ctx: CanvasRenderingContext2D, bmp: ImageBitmap, dx: number, dy: number, dw: number, dh: number): void {
  const scale = Math.max(dw / bmp.width, dh / bmp.height)
  const sw = dw / scale
  const sh = dh / scale
  ctx.drawImage(bmp, (bmp.width - sw) / 2, (bmp.height - sh) / 2, sw, sh, dx, dy, dw, dh)
}

/** 图片素材铺满（cover 裁切） */
export function drawImageFill(ctx: CanvasRenderingContext2D, w: number, h: number, bmp: ImageBitmap): void {
  drawCover(ctx, bmp, 0, 0, w, h)
}

/** 缩略图条：网格帧平铺（帧缺失的槽留空，等负缓存/补帧后重绘） */
export function drawThumbStrip(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  handle: ThumbSource,
  clip: EditorClip,
): void {
  const from = Math.max(0, clip.trimStart)
  const srcTo = clip.trimStart + sourceSpan(clip)
  if (srcTo <= from || handle.step <= 0) return
  const i0 = Math.floor(from / handle.step)
  const i1 = Math.max(i0, Math.floor((srcTo - 1e-6) / handle.step))
  for (let i = i0; i <= i1; i++) {
    const bmp = handle.frames.get(thumbKey(i * handle.step))
    if (!bmp) continue
    const x0 = ((Math.max(from, i * handle.step) - from) / (srcTo - from)) * w
    const x1 = ((Math.min(srcTo, (i + 1) * handle.step) - from) / (srcTo - from)) * w
    if (x1 - x0 <= 0.5) continue
    drawCover(ctx, bmp, x0, 0, x1 - x0, h)
  }
}

/** 音波条：中线对称柱状（每列取峰值），srcFrom 固定 trimStart、跨度 = sourceSpan */
export function drawWaveform(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  peaks: WavePeaks,
  clip: EditorClip,
  color: string,
): void {
  const srcFrom = clip.trimStart
  const srcTo = srcFrom + sourceSpan(clip)
  const columns = Math.max(1, Math.floor(w / 2))
  const amps = resamplePeaks(peaks, srcFrom, srcTo, columns)
  ctx.fillStyle = color
  const colW = w / columns
  const mid = h / 2
  for (let c = 0; c < columns; c++) {
    const amp = amps[c]
    if (amp <= 0.001) continue
    const bar = Math.max(1, amp * (h / 2 - 1))
    ctx.fillRect(c * colW, mid - bar, Math.max(1, colW - 0.5), bar * 2)
  }
}

// ---------- 生命周期 ----------

/** 组件卸载时清空全部素材条缓存（与 clearMediaPool 配对调用） */
export function clearStripCaches(): void {
  peaksCache.clear()
  for (const src of thumbSources.values()) {
    for (const bmp of src.frames.values()) bmp?.close()
  }
  thumbSources.clear()
  queueTail = Promise.resolve()
}
