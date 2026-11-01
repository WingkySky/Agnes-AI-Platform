<script setup lang="ts">
/* =====================================================
 * 预览区：浏览器本地预览（双路径）
 * - WebCodecs 可用：canvas 路径（EditorCanvasStage，mediabunny 解码 +
 *   音频统一调度，音频时钟主控推进播放头）
 * - 不可用：DOM 路径，每条视频轨一个 <video>、音频轨一个 <audio>，
 *   rAF 推进 store.playhead；音量/fade 经 WebAudio GainNode（clipGainAt）
 * - 字幕层与控制条两路径共用；激活片段素材缓存两条路径共用
 * ===================================================== */

import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Headset } from '@element-plus/icons-vue'
import { ArrowLeftToLine, ArrowRightToLine, ChevronsLeft, ChevronsRight, Pause, Play, StepBack, StepForward } from 'lucide-vue-next'

import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'
import { clipEnd, type EditorClip } from '@/lib/editor-types'
import { formatTimecode } from '@/lib/editor-timecode'
import { clipGainAt, clipFadeAlphaAt } from '@/lib/editor-audio'
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
    fontFamily: `"${style.font}", "Noto Sans CJK SC", sans-serif`,
    fontSize: `${style.size * 0.5}px`,
    color: style.color,
    fontWeight: style.outline ? '700' : '400',
    textShadow: style.outline ? '0 0 4px rgba(0,0,0,0.9)' : 'none',
  }
})

const videoTracks = computed(() =>
  (store.doc?.tracks ?? []).filter((tr) => tr.kind === 'video').sort((a, b) => a.order - b.order),
)

/** 逐 cue 样式覆盖（缺键继承工程 subtitleStyle；position 用 align-self 模拟 top/center/bottom）。
 *  x/y 自由位=绝对定位在画面归一化中心（与渲染 \an5\pos 语义一致）；拖拽/缩放手势本地态实时覆盖。 */
function subtitleClipStyle(clip: EditorClip): Record<string, string> {
  const style = clip.props.style
  if (!style && subDrag.value?.id !== clip.id) return {}
  const out: Record<string, string> = {}
  const drag = subDrag.value?.id === clip.id ? subDrag.value : null
  const scale = subScale.value?.id === clip.id ? subScale.value : null
  const font = style?.font
  const color = style?.color
  const size = scale ? scale.size : style?.size
  const position = style?.position
  const x = drag ? drag.x : style?.x
  const y = drag ? drag.y : style?.y
  if (font) out.fontFamily = `"${font}", "Noto Sans CJK SC", sans-serif`
  if (color) out.color = color
  if (size) out.fontSize = `${size * 0.5}px`
  if (x != null && y != null) {
    out.position = 'absolute'
    out.left = `${x * 100}%`
    out.top = `${y * 100}%`
    out.transform = 'translate(-50%, -50%)'
    out.alignSelf = 'unset'
  } else if (position) {
    out.alignSelf = position === 'top' ? 'flex-start' : position === 'center' ? 'center' : 'flex-end'
  }
  return out
}

// ---------- 字幕预览交互：点选/拖动改位/缩放把手（手势本地态，pointerup 一次入栈可撤销） ----------

const stageRef = ref<HTMLElement | null>(null)
const subDrag = ref<{ id: string; x: number; y: number } | null>(null)
const subScale = ref<{ id: string; size: number } | null>(null)

function stageRect(): DOMRect | null {
  return stageRef.value?.getBoundingClientRect() ?? null
}

function onSubtitlePointerDown(e: PointerEvent, clip: EditorClip): void {
  e.stopPropagation()
  store.select(clip.id)
  store.endAssetPreview()
  store.isPlaying = false
  const rect = stageRect()
  if (!rect || clip.trackId !== subtitleTrackId()) return
  const startX = e.clientX
  const startY = e.clientY
  const origX = clip.props.style?.x ?? (rect.left + rect.width / 2 === 0 ? 0.5 : (e.clientX - rect.left) / rect.width)
  const origY = clip.props.style?.y ?? (e.clientY - rect.top) / rect.height
  // 首次拖动：以当前渲染位置为自由位起点（预设位=居中/底部近似当前位置）
  const baseX = clip.props.style?.x ?? Math.min(0.98, Math.max(0.02, (e.clientX - rect.left) / rect.width))
  const baseY = clip.props.style?.y ?? Math.min(0.98, Math.max(0.02, (e.clientY - rect.top) / rect.height))
  void origX; void origY
  let moved = false
  const move = (ev: PointerEvent): void => {
    const dx = (ev.clientX - startX) / rect.width
    const dy = (ev.clientY - startY) / rect.height
    if (!moved && Math.hypot(ev.clientX - startX, ev.clientY - startY) < 4) return
    moved = true
    subDrag.value = {
      id: clip.id,
      x: Math.round(Math.min(0.98, Math.max(0.02, baseX + dx)) * 1000) / 1000,
      y: Math.round(Math.min(0.98, Math.max(0.02, baseY + dy)) * 1000) / 1000,
    }
  }
  const up = (): void => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
    const d = subDrag.value
    subDrag.value = null
    if (!d || !moved) return
    const style = { ...(clip.props.style ?? {}), x: d.x, y: d.y }
    store.applyOrToast({ op: 'setClipProperty', payload: { clipId: clip.id, props: { style } } }, t('editor.cueStyleMove'))
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}

function onSubtitleScaleDown(e: PointerEvent, clip: EditorClip): void {
  e.stopPropagation()
  const startY = e.clientY
  const origSize = clip.props.style?.size ?? store.doc?.subtitleStyle?.size ?? 48
  subScale.value = { id: clip.id, size: origSize }
  const move = (ev: PointerEvent): void => {
    const s = subScale.value
    if (!s) return
    // 竖直拖动 → 字号（向上放大）；步进 1px 钳 8~200
    s.size = Math.round(Math.min(200, Math.max(8, origSize - (ev.clientY - startY) / 2)))
  }
  const up = (): void => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
    const s = subScale.value
    subScale.value = null
    if (!s || s.size === origSize) return
    const style = { ...(clip.props.style ?? {}), size: s.size }
    store.applyOrToast({ op: 'setClipProperty', payload: { clipId: clip.id, props: { style } } }, t('editor.cueStyleSize'))
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}

function subtitleTrackId(): string | null {
  return store.doc?.tracks.find((tr) => tr.kind === 'subtitle')?.id ?? null
}
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

/** 字幕全程显示（非播放头区间的半透明，可点选/拖动编辑——标准剪辑器行为） */
const activeSubtitles = computed(() =>
  (store.doc?.clips ?? [])
    .filter((c) => {
      const track = store.doc?.tracks.find((tr) => tr.id === c.trackId)
      return track?.kind === 'subtitle' && !track.flags.hidden && c.text
    })
    .sort((a, b) => a.start - b.start),
)

const isSubtitleActive = (clip: EditorClip): boolean =>
  store.playhead >= clip.start && store.playhead < clipEnd(clip)

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
  // 独奏是预览监听态：存在独奏轨时只出独奏轨的声音（成片渲染不受影响）
  const anySolo = store.doc.tracks.some((tr) => tr.flags.solo)
  for (const track of videoTracks.value) {
    const el = videoEls.get(track.id)
    if (!el) continue
    const clip = activeClip(track.id)
    if (!clip || !el.src) continue
    const speed = clip.props.speed ?? 1
    const expected = clip.trimStart + (store.playhead - clip.start) * speed
    if (Math.abs(el.currentTime - expected) > 0.3) el.currentTime = Math.max(0, expected)
    el.playbackRate = Math.min(Math.max(speed, 0.25), 4)
    el.muted = track.flags.muted || (anySolo && !track.flags.solo) || clip.props.muted === true
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
    el.muted = track.flags.muted || (anySolo && !track.flags.solo) || clip.props.muted === true
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

// ---------- 传输控制条（与键盘快捷键同一套语义：EditorView.onKeydown） ----------

const frameStep = computed(() => 1 / (store.doc?.timebase || 30))
const totalDuration = computed(() => Math.max(0, ...(store.doc?.clips ?? []).map(clipEnd)))

function nudge(delta: number): void {
  store.playhead = Math.min(totalDuration.value, Math.max(0, store.playhead + delta))
}

function goEnd(): void {
  store.playhead = totalDuration.value
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
      <div ref="stageRef" class="stage" :style="stageStyle">
        <template v-if="store.doc">
          <EditorCanvasStage v-if="useCanvasPath" />
          <template v-else>
            <template v-for="track in videoTracks" :key="track.id">
              <video
                v-if="videoStates[track.id]?.url && !track.flags.hidden"
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
            <p
              v-for="clip in activeSubtitles"
              :key="clip.id"
              class="subtitle-text"
              :class="{
                'is-selected': store.selectedClipId === clip.id,
                'is-idle': !isSubtitleActive(clip),
              }"
              :style="{
                ...subtitleStyleVars,
                ...subtitleClipStyle(clip),
                opacity: isSubtitleActive(clip) ? clipFadeAlphaAt(clip, store.playhead) : 0.4,
              }"
              @pointerdown.stop="onSubtitlePointerDown($event, clip)"
            >
              {{ clip.text }}
              <span
                v-if="store.selectedClipId === clip.id"
                class="subtitle-scale-handle"
                @pointerdown.stop="onSubtitleScaleDown($event, clip)"
              />
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
      <div class="preview-timecode">
        <span class="current">{{ formatTimecode(store.playhead) }}</span>
        <span class="sep">/</span>
        <span class="total">{{ formatTimecode(totalDuration) }}</span>
      </div>
      <div class="transport">
        <el-button circle text size="small" :icon="ArrowLeftToLine" :title="t('editor.goStartTip')" :disabled="store.playhead <= 0" @click="store.playhead = 0" />
        <el-button circle text size="small" :icon="ChevronsLeft" :title="t('editor.rewind1sTip')" :disabled="store.playhead <= 0" @click="nudge(-1)" />
        <el-button circle text size="small" :icon="StepBack" :title="t('editor.prevFrameTip')" :disabled="store.playhead <= 0" @click="nudge(-frameStep)" />
        <el-button circle size="small" type="primary" :icon="store.isPlaying ? Pause : Play" :title="store.isPlaying ? t('editor.pauseBtnTip') : t('editor.playBtnTip')" @click="togglePlay" />
        <el-button circle text size="small" :icon="StepForward" :title="t('editor.nextFrameTip')" :disabled="store.playhead >= totalDuration" @click="nudge(frameStep)" />
        <el-button circle text size="small" :icon="ChevronsRight" :title="t('editor.forward1sTip')" :disabled="store.playhead >= totalDuration" @click="nudge(1)" />
        <el-button circle text size="small" :icon="ArrowRightToLine" :title="t('editor.goEndTip')" :disabled="store.playhead >= totalDuration" @click="goEnd" />
      </div>
      <div />
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
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  padding-bottom: 6%;
  pointer-events: none; /* 层空白区穿透到画面；文本自身 auto 可点选 */
}
.subtitle-text {
  margin: 0;
  padding: 2px 10px;
  color: #fff;
  font-size: 24px;
  line-height: 1.3;
  pointer-events: auto; /* 可点选/拖动 */
  position: relative;
  cursor: move;
  touch-action: none;
  user-select: none;
}
.subtitle-text.is-idle { opacity: 0.4; }
.subtitle-text.is-selected { outline: 1.5px dashed var(--el-color-primary); outline-offset: 3px; }
.subtitle-scale-handle {
  position: absolute;
  right: -7px;
  bottom: -7px;
  width: 12px;
  height: 12px;
  border-radius: 3px;
  background: var(--el-color-primary);
  border: 2px solid #fff;
  cursor: nwse-resize;
  touch-action: none;
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
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 4px 12px 6px;
}
.preview-timecode {
  justify-self: start;
  display: flex;
  align-items: baseline;
  gap: 4px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.preview-timecode .current { color: var(--el-text-color-primary); font-weight: 600; }
.preview-timecode .sep,
.preview-timecode .total { color: var(--el-text-color-secondary); }
.transport {
  display: flex;
  align-items: center;
  gap: 2px;
}
.transport :deep(.el-button + .el-button) { margin-left: 0; }
</style>
