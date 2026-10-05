<script setup lang="ts">
/* =====================================================
 * 预览区：浏览器本地预览
 * - 每条视频轨一个 <video>，按 rect 绝对定位层叠（PIP）
 * - 每条音频轨一个 <audio>
 * - 播放 = rAF 推进 store.playhead（单一时间源）；片段切换时换 src 重定位
 * - 音量/fade：媒体元素接入 WebAudio GainNode，每帧写入瞬时增益
 *   （lib/editor-audio 纯函数，与渲染 Plan 的 afade 语义一致）；
 *   跨域资源不进音频图，退回元素音量近似
 * ===================================================== */

import { computed, onBeforeUnmount, watch } from 'vue'

import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'
import { clipEnd, type EditorClip } from '@/lib/editor-types'
import { clipGainAt } from '@/lib/editor-audio'

const store = useEditorStore()

const emptyStyle: Record<string, string> = {}
const { t } = useI18n()

/** subtitleStyle → 字幕层 CSS */
const subtitleStyleVars = computed<Record<string, string>>(() => {
  const style = store.doc?.subtitleStyle
  if (!style) return emptyStyle
  return {
    fontSize: `${style.size * 0.5}px`,
    color: style.color,
    fontWeight: style.outline ? '700' : '400',
    textShadow: style.outline ? '0 0 4px rgba(0,0,0,0.9)' : 'none',
  }
})

const videoTracks = computed(() =>
  (store.doc?.tracks ?? []).filter((tr) => tr.kind === 'video').sort((a, b) => a.order - b.order),
)
const audioTracks = computed(() =>
  (store.doc?.tracks ?? []).filter((tr) => tr.kind === 'audio'),
)

function activeClip(trackId: string): EditorClip | null {
  const clips = (store.doc?.clips ?? [])
    .filter((c) => c.trackId === trackId && store.playhead >= c.start && store.playhead < clipEnd(c))
  return clips[0] ?? null
}

interface ActiveClipState { clipId: string | null; assetId: number | null; url: string | null }

/** trackId -> 当前激活片段状态（模板渲染 + 元素同步共用） */
const videoStates = computed<Record<string, ActiveClipState>>(() => {
  const out: Record<string, ActiveClipState> = {}
  for (const track of videoTracks.value) {
    const clip = activeClip(track.id)
    const asset = clip?.assetId != null ? store.assetCache.get(clip.assetId) : undefined
    out[track.id] = {
      clipId: clip?.id ?? null,
      assetId: clip?.assetId ?? null,
      url: asset?.asset_url ?? null,
    }
  }
  return out
})

const audioStates = computed<Record<string, ActiveClipState>>(() => {
  const out: Record<string, ActiveClipState> = {}
  for (const track of audioTracks.value) {
    const clip = activeClip(track.id)
    const asset = clip?.assetId != null ? store.assetCache.get(clip.assetId) : undefined
    out[track.id] = {
      clipId: clip?.id ?? null,
      assetId: clip?.assetId ?? null,
      url: asset?.asset_url ?? null,
    }
  }
  return out
})

// 确保激活片段的素材已缓存
watch(videoStates, (states) => {
  for (const s of Object.values(states)) if (s.assetId != null && !s.url) void store.fetchAsset(s.assetId)
}, { immediate: true })
watch(audioStates, (states) => {
  for (const s of Object.values(states)) if (s.assetId != null && !s.url) void store.fetchAsset(s.assetId)
}, { immediate: true })

const activeSubtitles = computed(() =>
  (store.doc?.clips ?? [])
    .filter((c) => {
      const track = store.doc?.tracks.find((tr) => tr.id === c.trackId)
      return track?.kind === 'subtitle' && store.playhead >= c.start && store.playhead < clipEnd(c) && c.text
    })
    .sort((a, b) => a.start - b.start),
)

function clipRectStyle(clip: EditorClip): Record<string, string> {
  const r = clip.props.rect ?? { x: 0, y: 0, w: 1, h: 1 }
  return {
    left: `${r.x * 100}%`,
    top: `${r.y * 100}%`,
    width: `${r.w * 100}%`,
    height: `${r.h * 100}%`,
  }
}

// ---------- 媒体元素同步 ----------

const videoEls = new Map<string, HTMLVideoElement>()
const audioEls = new Map<string, HTMLAudioElement>()

function setVideoEl(trackId: string, el: unknown): void {
  if (el instanceof HTMLVideoElement) videoEls.set(trackId, el)
}
function setAudioEl(trackId: string, el: unknown): void {
  if (el instanceof HTMLAudioElement) audioEls.set(trackId, el)
}

function syncMedia(): void {
  if (!store.doc) return
  for (const track of videoTracks.value) {
    const el = videoEls.get(track.id)
    if (!el) continue
    const clip = activeClip(track.id)
    if (!clip || !el.src) continue
    const speed = clip.props.speed ?? 1
    const expected = clip.trimStart + (store.playhead - clip.start) * speed
    if (Math.abs(el.currentTime - expected) > 0.3) el.currentTime = Math.max(0, expected)
    el.playbackRate = Math.min(Math.max(speed, 0.25), 4)
    el.muted = track.flag === 'muted'
    applyGain(el, clip)
    if (store.isPlaying && el.paused) void el.play().catch(() => undefined)
    if (!store.isPlaying && !el.paused) el.pause()
  }
  for (const track of audioTracks.value) {
    const el = audioEls.get(track.id)
    if (!el) continue
    const clip = activeClip(track.id)
    if (!clip || !el.src) continue
    const speed = clip.props.speed ?? 1
    const expected = clip.trimStart + (store.playhead - clip.start) * speed
    if (Math.abs(el.currentTime - expected) > 0.3) el.currentTime = Math.max(0, expected)
    el.playbackRate = Math.min(Math.max(speed, 0.25), 4)
    el.muted = track.flag === 'muted'
    applyGain(el, clip)
    if (store.isPlaying && el.paused) void el.play().catch(() => undefined)
    if (!store.isPlaying && !el.paused) el.pause()
  }
}

// ---------- WebAudio 增益（精确音量/fade） ----------

let audioCtx: AudioContext | null = null
/** 元素 → 增益节点；null = 已判定直连（跨域资源不进图，避免静音回退不了） */
const audioGraph = new WeakMap<HTMLMediaElement, GainNode | null>()

function isSameOrigin(url: string): boolean {
  try {
    return new URL(url, location.origin).origin === location.origin
  } catch {
    return false
  }
}

function gainFor(el: HTMLMediaElement): GainNode | null {
  if (audioGraph.has(el)) return audioGraph.get(el) ?? null
  if (!isSameOrigin(el.currentSrc || el.src)) {
    audioGraph.set(el, null)
    return null
  }
  if (!audioCtx) audioCtx = new AudioContext()
  const source = audioCtx.createMediaElementSource(el)
  const gain = audioCtx.createGain()
  source.connect(gain).connect(audioCtx.destination)
  audioGraph.set(el, gain)
  return gain
}

/** 每帧把片段瞬时增益写入 GainNode（10ms 平滑无爆音）；播前确保上下文已恢复 */
function applyGain(el: HTMLMediaElement, clip: EditorClip): void {
  const gain = gainFor(el)
  if (gain && audioCtx) {
    el.volume = 1
    if (audioCtx.state === 'suspended' && store.isPlaying) void audioCtx.resume()
    gain.gain.setTargetAtTime(clipGainAt(clip, store.playhead), audioCtx.currentTime, 0.01)
  } else {
    el.volume = Math.min(1, Math.max(0, clipGainAt(clip, store.playhead)))
  }
}

/** 播放按钮走用户手势恢复 AudioContext（空格键等路径由 applyGain 内的 resume 兜底） */
async function togglePlay(): Promise<void> {
  if (audioCtx?.state === 'suspended') await audioCtx.resume().catch(() => undefined)
  store.isPlaying = !store.isPlaying
}

// 播放循环：rAF 推进 playhead，逐帧同步媒体元素
let rafId = 0
let lastTs = 0

function tick(ts: number): void {
  if (store.isPlaying) {
    if (lastTs) store.playhead += (ts - lastTs) / 1000
    lastTs = ts
    const total = Math.max(1, ...(store.doc?.clips ?? []).map(clipEnd))
    if (store.playhead >= total) {
      store.playhead = total
      store.isPlaying = false
    }
  } else {
    lastTs = 0
  }
  syncMedia()
  rafId = requestAnimationFrame(tick)
}
rafId = requestAnimationFrame(tick)

onBeforeUnmount(() => {
  cancelAnimationFrame(rafId)
  void audioCtx?.close().catch(() => undefined)
  audioCtx = null
})
</script>

<template>
  <div class="preview">
    <div class="stage" :style="{ aspectRatio: store.doc ? `${store.doc.width} / ${store.doc.height}` : '16 / 9' }">
      <template v-if="store.doc">
        <template v-for="track in videoTracks" :key="track.id">
          <video
            v-if="videoStates[track.id]?.url && track.flag !== 'hidden'"
            :ref="(el) => setVideoEl(track.id, el)"
            class="stage-video"
            :style="activeClip(track.id) ? clipRectStyle(activeClip(track.id)!) : {}"
            :src="videoStates[track.id]!.url ?? undefined"
            playsinline
          />
        </template>
        <template v-for="track in audioTracks" :key="track.id">
          <audio
            v-if="audioStates[track.id]?.url"
            :ref="(el) => setAudioEl(track.id, el)"
            :src="audioStates[track.id]!.url ?? undefined"
          />
        </template>
        <div class="subtitle-layer">
          <p v-for="clip in activeSubtitles" :key="clip.id" class="subtitle-text" :style="subtitleStyleVars">
            {{ clip.text }}
          </p>
        </div>
      </template>
      <div v-else class="stage-empty">{{ t('editor.previewEmpty') }}</div>
    </div>

    <div class="preview-controls">
      <el-button size="small" @click="store.playhead = 0">⏮</el-button>
      <el-button size="small" type="primary" @click="togglePlay">
        {{ store.isPlaying ? t('editor.pause') : t('editor.play') }}
      </el-button>
      <span class="preview-time">{{ store.playhead.toFixed(2) }}s</span>
    </div>
  </div>
</template>

<style scoped>
.preview {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--el-fill-color-darker);
}
.stage {
  position: relative;
  flex: 1;
  margin: 12px auto;
  max-width: 100%;
  max-height: 100%;
  background: #000;
  overflow: hidden;
  border-radius: 4px;
}
.stage-video {
  position: absolute;
  object-fit: fill;
}
.subtitle-layer {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 6%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  pointer-events: none;
}
.subtitle-text {
  margin: 0;
  padding: 2px 10px;
  color: #fff;
  font-size: 24px;
  line-height: 1.3;
}
.stage-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-secondary);
}
.preview-controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 6px 0 10px;
}
.preview-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-variant-numeric: tabular-nums;
  min-width: 64px;
}
</style>
