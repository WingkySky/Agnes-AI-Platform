/* =====================================================
 * 预览解码池（mediabunny + WebCodecs）
 * - Input 每 asset URL 一个（LRU 上限），Sinks 按活跃片段生命周期创建（GC 兜底）
 * - 图片走 createImageBitmap 缓存，不进 mediabunny
 * - 时长探测：容器元数据 → 精确计算；WebCodecs 不可用时由调用方走元素探测
 * ===================================================== */

import {
  ALL_FORMATS,
  AudioBufferSink,
  CanvasSink,
  Input,
  UrlSource,
} from 'mediabunny'
import type { InputAudioTrack, InputVideoTrack } from 'mediabunny'

/** 预览解码宽度上限（PIP 多轨并发的性能预算） */
export const PREVIEW_SINK_WIDTH = 1280
/** Input 池上限（LRU） */
const INPUT_POOL_LIMIT = 8

/** WebCodecs 解码能力检测（canvas 预览路径的开关） */
export function hasWebCodecs(): boolean {
  return typeof VideoDecoder !== 'undefined' && typeof AudioDecoder !== 'undefined'
}

interface PoolEntry {
  input: Input
  video: InputVideoTrack | null
  audio: InputAudioTrack | null
}

/** 池值：promise 与 lastUsed 分离，保证 LRU 淘汰同步可判 */
interface PoolSlot {
  promise: Promise<PoolEntry>
  lastUsed: number
}

const inputPool = new Map<string, PoolSlot>()

function disposeSlot(url: string, slot: PoolSlot): void {
  void slot.promise.then(
    (e) => {
      try { e.input.dispose() } catch { /* 已释放时忽略 */ }
    },
    () => { /* 创建失败的占位直接丢弃 */ },
  )
  inputPool.delete(url)
}

async function openEntry(url: string): Promise<PoolEntry> {
  const input = new Input({ formats: ALL_FORMATS, source: new UrlSource(url) })
  const [video, audio] = await Promise.all([
    input.getPrimaryVideoTrack(),
    input.getPrimaryAudioTrack(),
  ])
  return { input, video, audio }
}

/** 取 asset 的轨道句柄（每 URL 缓存一个 Input，超出上限 LRU 释放） */
export function getMediaTracks(url: string): Promise<PoolEntry> {
  const cached = inputPool.get(url)
  if (cached) {
    cached.lastUsed = Date.now()
    return cached.promise
  }
  const slot: PoolSlot = { promise: openEntry(url), lastUsed: Date.now() }
  inputPool.set(url, slot)
  slot.promise.catch(() => { /* 失败占位留在池里避免重试风暴，可被 LRU 淘汰 */ })
  if (inputPool.size > INPUT_POOL_LIMIT) {
    let oldestUrl: string | null = null
    let oldest = Infinity
    for (const [u, s] of inputPool) {
      if (s.lastUsed < oldest) { oldest = s.lastUsed; oldestUrl = u }
    }
    if (oldestUrl && oldestUrl !== url && oldestUrl != null) disposeSlot(oldestUrl, inputPool.get(oldestUrl)!)
  }
  return slot.promise
}

/** 为视频轨建帧画布 sink（无视频轨返回 null；解码上限见 PREVIEW_SINK_WIDTH） */
export async function createVideoSink(url: string): Promise<CanvasSink | null> {
  try {
    const entry = await getMediaTracks(url)
    if (!entry.video) return null
    return new CanvasSink(entry.video, {
      width: Math.min(entry.video.displayWidth, PREVIEW_SINK_WIDTH),
      poolSize: 2,
    })
  } catch {
    return null
  }
}

/** 为音频轨建 PCM buffer sink（无音频轨返回 null，与渲染端滤无声流行为对齐） */
export async function createAudioSink(url: string): Promise<AudioBufferSink | null> {
  try {
    const entry = await getMediaTracks(url)
    if (!entry.audio) return null
    return new AudioBufferSink(entry.audio)
  } catch {
    return null
  }
}

/** 为素材条建小尺寸帧抓取 sink（无视频轨返回 null；160px 宽足够缩略图平铺） */
export async function createThumbSink(url: string): Promise<CanvasSink | null> {
  try {
    const entry = await getMediaTracks(url)
    if (!entry.video) return null
    return new CanvasSink(entry.video, { width: 160, poolSize: 1 })
  } catch {
    return null
  }
}

/** mediabunny 时长探测（秒）：容器元数据优先，缺失再精确计算；失败返回 0 */
export async function probeDuration(url: string): Promise<number> {
  try {
    const entry = await getMediaTracks(url)
    const meta = await entry.input.getDurationFromMetadata()
    if (meta != null && meta > 0) return meta
    return await entry.input.computeDuration()
  } catch {
    return 0
  }
}

/** 元素 loadedmetadata 时长探测（ mediabunny 不可用/容器元数据缺失时的回退；失败返回 0） */
export function probeElementDuration(url: string): Promise<number> {
  return new Promise((resolve) => {
    const el = document.createElement(/\.(mp3|wav|m4a|aac)(\?|$)/i.test(url) ? 'audio' : 'video')
    el.preload = 'metadata'
    el.onloadedmetadata = () => resolve(el.duration || 0)
    el.onerror = () => resolve(0)
    el.src = url
  })
}

/** 三级时长探测：mediabunny（WebCodecs 可用时）→ 元素探测回退 */
export async function probeMediaDuration(
  url: string,
  elementProbe: (url: string) => Promise<number> = probeElementDuration,
): Promise<number> {
  if (hasWebCodecs()) {
    const probed = await probeDuration(url)
    if (probed > 0) return probed
  }
  return elementProbe(url)
}

// ---------- 图片位图缓存 ----------

const bitmapCache = new Map<string, Promise<ImageBitmap | null>>()

/** 图片位图（含失败负缓存，避免 404 重试风暴） */
export function getImageBitmap(url: string): Promise<ImageBitmap | null> {
  const cached = bitmapCache.get(url)
  if (cached) return cached
  const bitmap = fetch(url)
    .then((res) => (res.ok ? res.blob() : Promise.reject(new Error(String(res.status)))))
    .then((blob) => createImageBitmap(blob))
    .catch(() => null)
  bitmapCache.set(url, bitmap)
  return bitmap
}

/** 组件卸载时全量释放（Input 取消未完请求；位图显式 close） */
export function clearMediaPool(): void {
  for (const [url, slot] of inputPool) disposeSlot(url, slot)
  for (const bitmap of bitmapCache.values()) {
    void bitmap.then((b) => { b?.close() }, () => undefined)
  }
  bitmapCache.clear()
}
