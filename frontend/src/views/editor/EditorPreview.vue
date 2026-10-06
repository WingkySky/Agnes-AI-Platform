<script setup lang="ts">
/* =====================================================
 * 预览区：浏览器本地预览（双路径）
 * - WebCodecs 可用：canvas 路径（EditorCanvasStage，mediabunny 解码 +
 *   音频统一调度，音频时钟主控推进播放头）
 * - 不可用：DOM 路径，每条视频轨一个 <video>、音频轨一个 <audio>，
 *   rAF 推进 store.playhead；音量/fade 经 WebAudio GainNode（clipGainAt）
 * - 字幕层与控制条两路径共用；激活片段素材缓存两条路径共用
 * ===================================================== */

import { computed, onBeforeUnmount, watch } from 'vue'
import { Headset } from '@element-plus/icons-vue'

import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'
import { clipEnd, type EditorClip } from '@/lib/editor-types'
import { clipGainAt } from '@/lib/editor-audio'
import { hasWebCodecs } from '@/lib/editor-media'
import EditorCanvasStage from './EditorCanvasStage.vue'

const store = useEditorStore()

const emptyStyle: Record<string, string> = {}
const { t } = useI18n()

/** 画面尺寸：锁文档比例，取槽位内最大等比尺寸（cqw/cqh 随面板拖拽实时缩放；
 *  宽高都显式给出，避免 aspect-ratio 被单边钳制后比例破坏拉伸变形） */
const stageStyle = computed<Record<string, string>>(() => {
  const doc = store.doc
  const ratio = doc && doc.height > 0 ? doc.width / doc.height : 16 / 9
  return {
    width: `min(100cqw, calc(100cqh * ${ratio}))`,
    height: `min(100cqh, calc(100cqw / ${ratio}))`,
  }
})

/** canvas 路径开关（组件创建时判定一次） */
const useCanvasPath = hasWebCodecs()

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
    el.muted = track.flag === 'muted' || clip.props.muted === true
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
    el.muted = track.flag === 'muted' || clip.props.muted === true
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

// 播放循环（仅 DOM 路径）：rAF 推进 playhead，逐帧同步媒体元素；canvas 路径由 EditorCanvasStage 推进
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
if (!useCanvasPath) rafId = requestAnimationFrame(tick)

onBeforeUnmount(() => {
  cancelAnimationFrame(rafId)
  void audioCtx?.close().catch(() => undefined)
  audioCtx = null
})
</script>

<template>
  <div class="preview">
    <div class="stage-wrap">
      <div class="stage" :style="stageStyle">
        <template v-if="store.doc">
          <EditorCanvasStage v-if="useCanvasPath" />
          <template v-else>
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
          </template>
          <div class="subtitle-layer">
            <p v-for="clip in activeSubtitles" :key="clip.id" class="subtitle-text" :style="subtitleStyleVars">
              {{ clip.text }}
            </p>
          </div>
        </template>
        <div v-else class="stage-empty">{{ t('editor.previewEmpty') }}</div>

        <!-- 素材临时预览浮层：盖在时间线画面上方，不碰 playhead/文档；点时间线即恢复。
             点击进入是用户手势，带声自动播放合法（Safari 若拦截则用原生播放键，静默降级） -->
        <div v-if="store.previewingAsset" class="asset-preview">
          <video
            v-if="store.previewingAsset.media_type === 'video'"
            :key="store.previewingAsset.id"
            :src="store.previewingAsset.asset_url"
            controls
            autoplay
            playsinline
          />
          <img
            v-else-if="store.previewingAsset.media_type === 'image'"
            :key="store.previewingAsset.id"
            :src="store.previewingAsset.asset_url"
            :alt="store.previewingAsset.name"
          >
          <div v-else class="audio-preview">
            <el-icon :size="40"><Headset /></el-icon>
            <span class="audio-name">{{ store.previewingAsset.name }}</span>
            <audio :key="store.previewingAsset.id" :src="store.previewingAsset.asset_url" controls autoplay />
          </div>
          <span class="preview-badge">{{ t('editor.assetPreviewing') }}</span>
        </div>
      </div>
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
  /* 通铺纯黑：画面外的留白即信箱黑边，不露面板灰底 */
  background: #000;
}
/* 画面槽位：container-type 使 stage 可用 cqw/cqh 度量可用空间 */
.stage-wrap {
  flex: 1;
  min-height: 0;
  container-type: size;
  display: flex;
  align-items: center;
  justify-content: center;
}
.stage {
  position: relative;
  /* 兜底：内联 min(100cqw/100cqh) 不可用时退回撑满（老浏览器不塌陷） */
  width: 100%;
  height: 100%;
  background: #000;
  overflow: hidden;
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
/* 素材临时预览：盖住整个画面区（DOM 顺序在 canvas/字幕层之后，自然在上层） */
.asset-preview {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #000;
}
.asset-preview video, .asset-preview img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
.audio-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--el-text-color-secondary);
}
.audio-name {
  max-width: 70%;
  font-size: 13px;
  color: #fff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preview-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 2px 8px;
  font-size: 12px;
  color: #fff;
  background: rgba(0, 0, 0, 0.55);
  border-radius: 3px;
  pointer-events: none;
}
.preview-controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 4px 0 6px;
}
.preview-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-variant-numeric: tabular-nums;
  min-width: 64px;
}
</style>
