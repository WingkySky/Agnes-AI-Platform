<script setup lang="ts">
/* =====================================================
 * 时间线区域：轨头（显隐/锁定）+ 轨道片段块 + 播放头
 * 交互：拖拽移动（moveClip）、边缘裁剪（trimClip）、播放头定位、
 *       素材拖入建片段（addClip）；拖拽中只改渲染态，pointerup 才入命令栈
 * ===================================================== */

import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'
import { clipEnd, type EditorClip } from '@/lib/editor-types'

const props = defineProps<{ totalDuration: number }>()

const store = useEditorStore()
const { t } = useI18n()

const PX_PER_SEC = ref(80)
const TIMELINE_PAD = 8

const trackRows = computed(() => {
  const doc = store.doc
  if (!doc) return []
  const kindOrder = { video: 0, audio: 1, subtitle: 2 } as const
  return [...doc.tracks]
    .sort((a, b) => kindOrder[a.kind] - kindOrder[b.kind] || a.order - b.order)
    .map((track) => ({
      track,
      clips: doc.clips
        .filter((c) => c.trackId === track.id)
        .sort((a, b) => a.start - b.start),
    }))
})

const contentWidth = computed(() =>
  Math.max(600, (props.totalDuration + 6) * PX_PER_SEC.value + TIMELINE_PAD * 2),
)

const timelineWidth = computed(() => (props.totalDuration + 6) * PX_PER_SEC.value)

// ---------- 播放头 ----------

const laneRef = ref<HTMLElement | null>(null)

function seekByEvent(e: PointerEvent): void {
  const lane = laneRef.value
  if (!lane) return
  const rect = lane.getBoundingClientRect()
  const sec = (e.clientX - rect.left + lane.scrollLeft) / PX_PER_SEC.value
  store.playhead = Math.max(0, Math.min(sec, props.totalDuration))
}

function onRulerPointerDown(e: PointerEvent): void {
  seekByEvent(e)
  const move = (ev: PointerEvent) => seekByEvent(ev)
  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}

// ---------- 片段几何 ----------

function clipStyle(clip: EditorClip): Record<string, string> {
  const left = (dragRender.value?.clipId === clip.id ? dragRender.value.start : clip.start) * PX_PER_SEC.value
  const duration = dragRender.value?.clipId === clip.id ? dragRender.value.duration : clip.duration
  return {
    left: `${TIMELINE_PAD + left}px`,
    width: `${Math.max(duration * PX_PER_SEC.value, 6)}px`,
  }
}

// ---------- 拖拽 / 裁剪（手势态不入历史） ----------

interface DragRender { clipId: string; start: number; duration: number; trimStart: number; mode: 'move' | 'trim-left' | 'trim-right' }
const dragRender = ref<DragRender | null>(null)

function beginDrag(e: PointerEvent, clip: EditorClip, mode: DragRender['mode']): void {
  e.stopPropagation()
  store.select(clip.id)
  const startX = e.clientX
  const orig = { start: clip.start, duration: clip.duration, trimStart: clip.trimStart }
  dragRender.value = { clipId: clip.id, ...orig, mode }

  const move = (ev: PointerEvent) => {
    if (!dragRender.value) return
    const delta = (ev.clientX - startX) / PX_PER_SEC.value
    const r = dragRender.value
    if (mode === 'move') {
      r.start = Math.max(0, orig.start + delta)
    } else if (mode === 'trim-right') {
      r.duration = Math.max(0.1, orig.duration + delta)
    } else {
      // trim-left：start 右移吃掉时长，源内入点右移（speed=1 近似）
      const maxShift = orig.duration - 0.1
      const shift = Math.min(Math.max(delta, -orig.start), maxShift)
      r.start = orig.start + shift
      r.duration = orig.duration - shift
      r.trimStart = Math.max(0, orig.trimStart + shift)
    }
  }
  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
    commitDrag()
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}

function commitDrag(): void {
  const r = dragRender.value
  dragRender.value = null
  if (!r) return
  if (r.mode === 'move') {
    store.applyOrToast({ op: 'moveClip', payload: { clipId: r.clipId, start: Math.round(r.start * 1000) / 1000 } }, t('editor.ops.moveClip'))
  } else {
    store.applyOrToast({
      op: 'trimClip',
      payload: {
        clipId: r.clipId,
        start: Math.round(r.start * 1000) / 1000,
        duration: Math.round(r.duration * 1000) / 1000,
        trimStart: Math.round(r.trimStart * 1000) / 1000,
      },
    }, t('editor.ops.trimClip'))
  }
}

function splitSelected(): void {
  const clipId = store.selectedClipId
  if (!clipId || !store.doc) return
  const clip = store.doc.clips.find((c) => c.id === clipId)
  if (!clip) return
  if (store.playhead <= clip.start || store.playhead >= clipEnd(clip)) {
    ElMessage.warning(t('editor.splitOutsideClip'))
    return
  }
  store.applyOrToast({ op: 'splitClip', payload: { clipId, at: store.playhead, newId: store.newId('clip') } }, t('editor.ops.splitClip'))
}

// ---------- 素材拖入 ----------

const dropActive = ref<string | null>(null)

async function onDropAsset(e: DragEvent, trackId: string): Promise<void> {
  dropActive.value = null
  const assetId = Number(e.dataTransfer?.getData('text/asset-id'))
  if (!assetId || !store.doc) return
  const track = store.doc.tracks.find((tr) => tr.id === trackId)
  if (!track || track.kind === 'subtitle') return
  const asset = await store.fetchAsset(assetId)
  if (!asset) return
  if (track.kind === 'video' && asset.media_type !== 'image' && asset.media_type !== 'video') return
  if (track.kind === 'audio' && asset.media_type !== 'audio') return
  const lane = laneRefs.get(trackId)
  const sec = (e.clientX - (lane?.getBoundingClientRect().left ?? 0) + (lane?.scrollLeft ?? 0)) / PX_PER_SEC.value
  const start = Math.max(0, Math.round(sec * 1000) / 1000)
  if (store.hasClipAt(trackId, assetId, start)) return  // 重复放置防线
  // 时长：图片默认 3s；视频/音频探测元数据真实时长（探测失败兜底 5s，可后续裁剪）
  let duration = 3
  if (asset.media_type !== 'image') {
    const probed = await store.probeMediaDuration(asset.asset_url)
    duration = probed > 0 ? probed : 5
  }
  store.applyOrToast({
    op: 'addClip',
    payload: { clip: { id: store.newId('clip'), trackId, assetId, start, duration: Math.round(duration * 1000) / 1000, trimStart: 0, props: {} } },
  }, t('editor.ops.addClip'))
}

// 多轨 lane 引用（拖入定位用）
const laneRefs = new Map<string, HTMLElement>()
function setLaneRef(trackId: string, el: unknown): void {
  if (el) laneRefs.set(trackId, el as HTMLElement)
}

const rulerTicks = computed(() => {
  const step = PX_PER_SEC.value >= 60 ? 1 : 5
  const ticks: number[] = []
  for (let s = 0; s <= props.totalDuration + 6; s += step) ticks.push(s)
  return ticks
})

const playheadLeft = computed(() => TIMELINE_PAD + store.playhead * PX_PER_SEC.value)
</script>

<template>
  <div class="timeline">
    <div class="timeline-toolbar">
      <el-button-group>
        <el-button size="small" @click="PX_PER_SEC = Math.max(30, PX_PER_SEC - 20)">−</el-button>
        <el-button size="small" @click="PX_PER_SEC = Math.min(200, PX_PER_SEC + 20)">+</el-button>
      </el-button-group>
      <el-button size="small" :icon="'Scissor'" :disabled="!store.selectedClipId" @click="splitSelected">
        {{ t('editor.split') }}
      </el-button>
      <span class="playhead-time">{{ store.playhead.toFixed(2) }}s</span>
    </div>

    <div class="timeline-scroll">
      <div class="timeline-content" :style="{ width: `${contentWidth}px` }">
        <!-- 标尺 -->
        <div class="timeline-ruler" @pointerdown="onRulerPointerDown">
          <span
            v-for="tick in rulerTicks"
            :key="tick"
            class="ruler-tick"
            :style="{ left: `${TIMELINE_PAD + tick * PX_PER_SEC}px` }"
          >{{ tick }}s</span>
        </div>

        <!-- 轨道 -->
        <div
          v-for="row in trackRows"
          :key="row.track.id"
          class="track-row"
          :class="{ hidden: row.track.flag === 'hidden' }"
        >
          <div class="track-head">
            <span class="track-kind" :data-kind="row.track.kind">{{ t(`editor.trackKinds.${row.track.kind}`) }}</span>
            <el-checkbox
              v-if="row.track.kind !== 'audio'"
              :model-value="row.track.flag === 'hidden'"
              size="small"
              @change="store.applyOrToast({ op: 'setTrackFlag', payload: { trackId: row.track.id, flag: row.track.flag === 'hidden' ? null : 'hidden' } }, t('editor.ops.setTrackFlag'))"
            >{{ t('editor.trackHidden') }}</el-checkbox>
            <el-checkbox
              v-else
              :model-value="row.track.flag === 'muted'"
              size="small"
              @change="store.applyOrToast({ op: 'setTrackFlag', payload: { trackId: row.track.id, flag: row.track.flag === 'muted' ? null : 'muted' } }, t('editor.ops.setTrackFlag'))"
            >{{ t('editor.trackMuted') }}</el-checkbox>
            <el-checkbox
              :model-value="row.track.flag === 'locked'"
              size="small"
              @change="store.applyOrToast({ op: 'setTrackFlag', payload: { trackId: row.track.id, flag: row.track.flag === 'locked' ? null : 'locked' } }, t('editor.ops.setTrackFlag'))"
            >{{ t('editor.trackLocked') }}</el-checkbox>
          </div>
          <div
            :ref="(el) => setLaneRef(row.track.id, el)"
            class="track-lane"
            :class="{ drop: dropActive === row.track.id, locked: row.track.flag === 'locked' }"
            @dragover.prevent="dropActive = row.track.id"
            @dragleave="dropActive = null"
            @drop.prevent="onDropAsset($event, row.track.id)"
          >
            <div
              v-for="clip in row.clips"
              :key="clip.id"
              class="clip-block"
              :class="{
                selected: store.selectedClipId === clip.id,
                video: row.track.kind === 'video',
                audio: row.track.kind === 'audio',
                subtitle: row.track.kind === 'subtitle',
                ghost: dragRender?.clipId === clip.id,
              }"
              :style="clipStyle(clip)"
              @pointerdown="beginDrag($event, clip, 'move')"
            >
              <span class="clip-handle left" @pointerdown="beginDrag($event, clip, 'trim-left')" />
              <span class="clip-label">{{ clip.text || (clip.assetId ? `#${clip.assetId}` : clip.id) }}</span>
              <span class="clip-handle right" @pointerdown="beginDrag($event, clip, 'trim-right')" />
            </div>
          </div>
        </div>

        <!-- 播放头 -->
        <div class="playhead" :style="{ left: `${playheadLeft}px` }" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.timeline {
  border-top: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
  height: 300px;
  flex-shrink: 0;
  background: var(--el-fill-color-lighter);
}
.timeline-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 10px;
}
.playhead-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-variant-numeric: tabular-nums;
}
.timeline-scroll {
  overflow: auto;
  flex: 1;
}
.timeline-content {
  position: relative;
  min-height: 100%;
}
.timeline-ruler {
  position: sticky;
  top: 0;
  height: 22px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
  z-index: 3;
}
.ruler-tick {
  position: absolute;
  top: 2px;
  font-size: 10px;
  color: var(--el-text-color-secondary);
  border-left: 1px solid var(--el-border-color);
  padding-left: 2px;
}
.track-row {
  display: flex;
  align-items: stretch;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.track-row.hidden { opacity: 0.45; }
.track-head {
  width: 168px;
  flex-shrink: 0;
  padding: 4px 8px;
  display: flex;
  flex-direction: column;
  gap: 0;
  background: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color-lighter);
  position: sticky;
  left: 0;
  z-index: 2;
}
.track-kind {
  font-size: 12px;
  font-weight: 600;
}
.track-kind[data-kind='video'] { color: var(--el-color-primary); }
.track-kind[data-kind='audio'] { color: var(--el-color-success); }
.track-kind[data-kind='subtitle'] { color: var(--el-color-warning); }
.track-head :deep(.el-checkbox) { height: 18px; margin-right: 8px; }
.track-head :deep(.el-checkbox__label) { font-size: 11px; }
.track-lane {
  position: relative;
  height: 52px;
  flex: 1;
}
.track-lane.drop { outline: 2px dashed var(--el-color-primary); outline-offset: -2px; }
.track-lane.locked { background: var(--el-fill-color); }
.clip-block {
  position: absolute;
  top: 6px;
  height: 40px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  cursor: grab;
  user-select: none;
  overflow: hidden;
  border: 1px solid transparent;
}
.clip-block.video { background: var(--el-color-primary-light-8); border-color: var(--el-color-primary-light-5); }
.clip-block.audio { background: var(--el-color-success-light-8); border-color: var(--el-color-success-light-5); }
.clip-block.subtitle { background: var(--el-color-warning-light-8); border-color: var(--el-color-warning-light-5); }
.clip-block.selected { outline: 2px solid var(--el-color-primary); z-index: 1; }
.clip-block.ghost { opacity: 0.6; }
.clip-label {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  pointer-events: none;
}
.clip-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 8px;
  cursor: ew-resize;
}
.clip-handle.left { left: 0; }
.clip-handle.right { right: 0; }
.playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--el-color-danger);
  z-index: 4;
  pointer-events: none;
}
</style>
