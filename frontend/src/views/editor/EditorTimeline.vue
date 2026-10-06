<script setup lang="ts">
/* =====================================================
 * 时间线区域：轨头（状态图标钮 + 拖拽重排 + 选中）+ 轨道片段块 + 播放头
 * 交互：拖拽移动（moveClip）、边缘裁剪（trimClip）、轨头拖拽重排（moveTrack）、
 *       点轨头/轨道空白选中轨道（Delete 删空轨）、播放头定位、素材拖入建片段；
 *       拖拽中只改渲染态，pointerup 才入命令栈
 * 几何：px↔秒换算全部收口到 lib/editor-scale（刻度/播放头/片段块共用）
 * 吸附：片段边/播放头/0 点最近点吸附（lib/editor-snapping），Shift 临时禁用；
 *       放置回退（占用轨→同类型空闲轨→自动开新轨）在 store.placeAsset
 * ===================================================== */

import { computed, ref, type Component } from 'vue'
import { Close, Delete, Headset, Mute, QuestionFilled, RefreshLeft, RefreshRight, Scissor, Switch } from '@element-plus/icons-vue'
import { Eye, EyeOff, GripVertical, Headphones, Lock, LockOpen, Volume2, VolumeX } from 'lucide-vue-next'

import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'
import { MIN_CLIP_DURATION, TRANSITION_TYPES, clipEnd, type EditorClip, type EditorTrack, type TrackFlagKey, type TrackKind, type TransitionType } from '@/lib/editor-types'
import {
  PX_PER_SEC_MAX,
  PX_PER_SEC_MIN,
  TIMELINE_PAD,
  TRACK_HEAD_W,
  rulerStepSec,
  timeToX,
  xToTime,
} from '@/lib/editor-scale'
import { buildSnapPoints, resolveSnap, snapThresholdSec } from '@/lib/editor-snapping'

const props = defineProps<{ totalDuration: number }>()

const store = useEditorStore()
const { t } = useI18n()

const PX_PER_SEC = ref(80)

const trackRows = computed(() => {
  const doc = store.doc
  if (!doc) return []
  // 显示序 = 视觉层序：order 大（顶层）排在列表最上面，与预览/渲染的遮盖关系一致
  const kindOrder = { video: 0, audio: 1, subtitle: 2 } as const
  return [...doc.tracks]
    .sort((a, b) => kindOrder[a.kind] - kindOrder[b.kind] || b.order - a.order)
    .map((track) => ({
      track,
      clips: doc.clips
        .filter((c) => c.trackId === track.id)
        .sort((a, b) => a.start - b.start),
    }))
})

const contentWidth = computed(() =>
  Math.max(600, TRACK_HEAD_W + timeToX(props.totalDuration + 6, PX_PER_SEC.value) + TIMELINE_PAD),
)

const timelineWidth = computed(() => (props.totalDuration + 6) * PX_PER_SEC.value)

// ---------- 播放头 ----------

function seekByEvent(e: PointerEvent): void {
  // 取任一轨道 lane 作为时间 0 点基准（各 lane 左缘相同，且 viewport 相对坐标已含滚动）
  const lane = laneRefs.values().next().value
  if (!lane) return
  const rect = lane.getBoundingClientRect()
  const sec = xToTime(e.clientX - rect.left + lane.scrollLeft, PX_PER_SEC.value)
  store.playhead = Math.min(sec, props.totalDuration)
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
  const start = dragRender.value?.clipId === clip.id ? dragRender.value.start : clip.start
  const duration = dragRender.value?.clipId === clip.id ? dragRender.value.duration : clip.duration
  return {
    left: `${timeToX(start, PX_PER_SEC.value)}px`,
    width: `${Math.max(duration * PX_PER_SEC.value, 6)}px`,
  }
}

// ---------- 拖拽 / 裁剪（手势态不入历史） ----------

interface DragRender { clipId: string; start: number; duration: number; trimStart: number; mode: 'move' | 'trim-left' | 'trim-right'; trackId: string; originTrackId: string; kind: string }
const dragRender = ref<DragRender | null>(null)

/** 指针所在的可放置轨道（同类型且未锁定），无效返回 null（目标保持粘性） */
function laneUnderPointer(clientY: number, kind: string): string | null {
  for (const [trackId, el] of laneRefs) {
    const rect = el.getBoundingClientRect()
    if (clientY >= rect.top && clientY <= rect.bottom) {
      const track = store.doc?.tracks.find((tr) => tr.id === trackId)
      return track && track.kind === kind && !track.flags.locked ? trackId : null
    }
  }
  return null
}

/** 跨轨拖动中的幽灵块：只画在非原轨的目标轨上 */
function moveGhost(trackId: string): boolean {
  const r = dragRender.value
  return !!r && r.mode === 'move' && r.trackId === trackId && r.trackId !== r.originTrackId
}

function ghostStyle(): Record<string, string> {
  const r = dragRender.value!
  return {
    left: `${timeToX(r.start, PX_PER_SEC.value)}px`,
    width: `${Math.max(r.duration * PX_PER_SEC.value, 6)}px`,
  }
}

function beginDrag(e: PointerEvent, clip: EditorClip, mode: DragRender['mode']): void {
  e.stopPropagation()
  store.select(clip.id)
  const startX = e.clientX
  const orig = { start: clip.start, duration: clip.duration, trimStart: clip.trimStart }
  dragRender.value = { clipId: clip.id, ...orig, mode, trackId: clip.trackId, originTrackId: clip.trackId, kind: store.doc?.tracks.find((tr) => tr.id === clip.trackId)?.kind ?? '' }
  // 吸附候选在手势开始时定格（手势期间文档与播放头不变）；Shift 按住临时禁用
  const snapPoints = store.doc && store.snappingEnabled
    ? buildSnapPoints(store.doc, { excludeClipId: clip.id, playhead: store.playhead })
    : null
  const threshold = snapThresholdSec(PX_PER_SEC.value)

  const move = (ev: PointerEvent) => {
    if (!dragRender.value) return
    const delta = (ev.clientX - startX) / PX_PER_SEC.value
    const r = dragRender.value
    const snapOn = snapPoints !== null && !ev.shiftKey
    if (mode === 'move') {
      let next = Math.max(0, orig.start + delta)
      if (snapOn) {
        // 首尾两个边缘都试吸附，取偏移小的一侧
        const a = resolveSnap(next, snapPoints, threshold)
        const b = resolveSnap(next + orig.duration, snapPoints, threshold)
        const da = a.point ? a.time - next : Infinity
        const db = b.point ? b.time - (next + orig.duration) : Infinity
        if (da !== Infinity && Math.abs(da) <= Math.abs(db)) next = Math.max(0, a.time)
        else if (db !== Infinity) next = Math.max(0, b.time - orig.duration)
      }
      r.start = next
      const target = laneUnderPointer(ev.clientY, r.kind)
      if (target) r.trackId = target
    } else if (mode === 'trim-right') {
      let end = orig.start + Math.max(MIN_CLIP_DURATION, orig.duration + delta)
      if (snapOn) end = Math.max(orig.start + MIN_CLIP_DURATION, resolveSnap(end, snapPoints, threshold).time)
      r.duration = end - orig.start
    } else {
      // trim-left：start 右移吃掉时长，源内入点右移（speed=1 近似）
      const maxShift = orig.duration - MIN_CLIP_DURATION
      let shift = Math.min(Math.max(delta, -orig.start), maxShift)
      if (snapOn) {
        const snapped = resolveSnap(orig.start + shift, snapPoints, threshold).time - orig.start
        shift = Math.min(Math.max(snapped, -orig.start), maxShift)
      }
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
    const payload: Record<string, unknown> = { clipId: r.clipId, start: Math.round(r.start * 1000) / 1000 }
    if (r.trackId !== r.originTrackId) payload.trackId = r.trackId
    store.applyOrToast({ op: 'moveClip', payload }, t('editor.ops.moveClip'))
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
  store.splitSelectedAtPlayhead()
}

// ---------- 轨道选中 / 状态开关 / 轨头拖拽重排 ----------

/** 点轨道空白处选中轨道（与片段选中互斥，Delete 删空轨） */
function onLanePointerDown(trackId: string): void {
  store.selectTrack(trackId)
}

/** 轨头状态图标钮配置：按轨道类型给开关集（音频无隐藏、字幕无声音开关） */
interface TrackFlagBtn { key: TrackFlagKey; icon: Component; title: string }

function trackFlagButtons(track: EditorTrack): TrackFlagBtn[] {
  const btns: TrackFlagBtn[] = []
  if (track.kind !== 'audio') {
    btns.push({ key: 'hidden', icon: track.flags.hidden ? EyeOff : Eye, title: track.flags.hidden ? 'editor.trackShow' : 'editor.trackHide' })
  }
  if (track.kind !== 'subtitle') {
    btns.push({ key: 'muted', icon: track.flags.muted ? VolumeX : Volume2, title: track.flags.muted ? 'editor.trackUnmute' : 'editor.trackMute' })
    btns.push({ key: 'solo', icon: Headphones, title: 'editor.trackSolo' })
  }
  btns.push({ key: 'locked', icon: track.flags.locked ? Lock : LockOpen, title: track.flags.locked ? 'editor.trackUnlock' : 'editor.trackLock' })
  return btns
}

function toggleTrackFlag(track: EditorTrack, key: TrackFlagKey): void {
  store.applyOrToast(
    { op: 'setTrackFlags', payload: { trackId: track.id, flags: { [key]: !track.flags[key] } } },
    t('editor.ops.setTrackFlags'),
  )
}

interface TrackDragState { trackId: string; kind: TrackKind; targetIndex: number | null }
const trackDrag = ref<TrackDragState | null>(null)

/** 轨头拖拽手柄起手：同类型轨内重排，指示线只画同类型行 */
function beginTrackDrag(e: PointerEvent, track: EditorTrack): void {
  e.preventDefault()
  store.selectTrack(track.id)
  trackDrag.value = { trackId: track.id, kind: track.kind, targetIndex: null }
  const move = (ev: PointerEvent) => {
    const d = trackDrag.value
    if (!d) return
    d.targetIndex = trackInsertIndex(ev.clientY, track)
  }
  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
    commitTrackDrag()
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}

/** 插入位（移除被拖轨后的同类型显示序）：越过行中点算落到其上方 */
function trackInsertIndex(clientY: number, track: EditorTrack): number {
  const rows = trackRows.value.filter((r) => r.track.kind === track.kind && r.track.id !== track.id)
  for (let i = 0; i < rows.length; i++) {
    const el = rowRefs.get(rows[i]!.track.id)
    if (!el) continue
    const rect = el.getBoundingClientRect()
    if (clientY < rect.top + rect.height / 2) return i
  }
  return rows.length
}

function commitTrackDrag(): void {
  const d = trackDrag.value
  trackDrag.value = null
  if (!d || d.targetIndex === null) return
  const cur = trackRows.value.filter((r) => r.track.kind === d.kind).findIndex((r) => r.track.id === d.trackId)
  if (d.targetIndex === cur) return // 原位放置不入栈
  store.applyOrToast({ op: 'moveTrack', payload: { trackId: d.trackId, toIndex: d.targetIndex } }, t('editor.ops.moveTrack'))
}

/** 重排指示：被拖行半透明；落点行上/下缘画插入线 */
function reorderMark(trackId: string): '' | 'dragging' | 'above' | 'below' {
  const d = trackDrag.value
  if (!d) return ''
  if (trackId === d.trackId) return 'dragging'
  const rows = trackRows.value.filter((r) => r.track.kind === d.kind && r.track.id !== d.trackId)
  const idx = rows.findIndex((r) => r.track.id === trackId)
  if (idx < 0) return ''
  if (idx === d.targetIndex) return 'above'
  if (d.targetIndex === rows.length && idx === rows.length - 1) return 'below'
  return ''
}

/** 删除选中片段（时间线工具栏按钮，与 Delete 键同路径） */
function deleteSelected(): void {
  if (!store.selectedClipId) return
  store.applyOrToast({ op: 'removeClip', payload: { clipId: store.selectedClipId } }, t('editor.ops.removeClip'))
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
  let start = xToTime(
    e.clientX - (lane?.getBoundingClientRect().left ?? 0) + (lane?.scrollLeft ?? 0),
    PX_PER_SEC.value,
  )
  if (store.snappingEnabled && !e.shiftKey) {
    start = resolveSnap(
      start,
      buildSnapPoints(store.doc, { playhead: store.playhead }),
      snapThresholdSec(PX_PER_SEC.value),
    ).time
  }
  // 放置回退（占用轨→同类型空闲轨→自动开新轨）+ 探测时长 + 重复落点防线都在 placeAsset
  await store.placeAsset(asset, { trackId, start: Math.round(start * 1000) / 1000 })
}

// ---------- 片段标注（音频/转场/淡变可视化） ----------

/** 片段音频态：分离后静音显示静音图标；视频片段自带音频显示音频图标 */
function audioBadge(clip: EditorClip, kind: string): 'muted' | 'audio' | null {
  if (kind === 'subtitle') return null
  if (clip.props.muted === true) return 'muted'
  return kind === 'video' && clip.assetId != null ? 'audio' : null
}

/** 片段淡变包络（剪映式穹顶）：淡入/淡出把整块内容塑成穹顶——上边缘沿包络曲线走，
 * 两端低（fade 区四分之一椭圆：边缘陡、顶部收平）、中间满高，曲线之上露出底色。
 * 音频=音量包络，视频/字幕=不透明度包络，全轨道共用同一种剪映淡变语言。
 * 返回开路 path（不含 Z，供描边复用）；无淡变返回 null（保持满框矩形）。 */
function clipEnvelope(clip: EditorClip): string | null {
  if ((clip.props.fadeIn ?? 0) <= 0 && (clip.props.fadeOut ?? 0) <= 0) return null
  const w = clip.duration * PX_PER_SEC.value
  if (w <= 0) return null
  let fi = Math.min((clip.props.fadeIn ?? 0) * PX_PER_SEC.value / w, 1) * 100
  let fo = Math.min((clip.props.fadeOut ?? 0) * PX_PER_SEC.value / w, 1) * 100
  if (fi + fo > 100) {
    const k = 100 / (fi + fo)
    fi *= k
    fo *= k
  }
  const rise = fi > 0 ? `C 0 ${100 - 55.23} ${fi * 0.4477} 0 ${fi} 0` : 'L 0 0'
  const fall = fo > 0 ? `C ${100 - fo * 0.4477} 0 100 ${100 - 55.23} 100 100` : 'L 100 100'
  return `M 0 100 ${rise} L ${100 - fo} 0 ${fall}`
}

/** 包络填充/描边跟轨道主色（fill 与片段底色同档，曲线之上露出 lane 底色） */
const ENVELOPE_COLORS: Record<string, { fill: string; stroke: string }> = {
  video: { fill: 'var(--el-color-primary-light-8)', stroke: 'var(--el-color-primary-light-5)' },
  audio: { fill: 'var(--el-color-success-light-8)', stroke: 'var(--el-color-success-light-5)' },
  subtitle: { fill: 'var(--el-color-warning-light-8)', stroke: 'var(--el-color-warning-light-5)' },
}

/** 同轨相邻接缝（整轨全帧链才有转场链路）：转场挂在前一片段，接缝处可点击选取 */
function rowJunctions(row: { track: { kind: string }; clips: EditorClip[] }): { clip: EditorClip; x: number }[] {
  if (!row.clips.length || row.track.kind === 'subtitle') return []
  const fullFrame = row.clips.every((c) => !c.props.rect || (c.props.rect.w >= 1 && c.props.rect.h >= 1))
  if (!fullFrame) return []
  const out: { clip: EditorClip; x: number }[] = []
  for (let i = 0; i + 1 < row.clips.length; i++) {
    if (Math.abs(clipEnd(row.clips[i]) - row.clips[i + 1].start) < 0.02) {
      out.push({ clip: row.clips[i], x: clipEnd(row.clips[i]) })
    }
  }
  return out
}

interface JunctionState { x: number; y: number; clipId: string; type: TransitionType | null; duration: number }
const junctionMenu = ref<JunctionState | null>(null)

function openJunctionMenu(e: MouseEvent, clip: EditorClip): void {
  const t = clip.props.transition
  junctionMenu.value = {
    x: Math.min(e.clientX, window.innerWidth - 200),
    y: Math.min(e.clientY, window.innerHeight - 230),
    clipId: clip.id,
    type: t?.type ?? null,
    duration: t?.duration ?? 0.5,
  }
}

function applyJunction(type: TransitionType | null): void {
  const j = junctionMenu.value!
  store.applyOrToast({ op: 'setClipProperty', payload: { clipId: j.clipId, props: { transition: type ? { type, duration: j.duration } : null } } }, t('editor.ops.setClipProperty'))
  junctionMenu.value = null
}

/** 转场已激活时改时长立即生效（菜单不关闭） */
function setJunctionDuration(v: number | undefined): void {
  const j = junctionMenu.value
  if (!j) return
  j.duration = v ?? 0.5
  if (j.type) {
    store.applyOrToast({ op: 'setClipProperty', payload: { clipId: j.clipId, props: { transition: { type: j.type, duration: j.duration } } } }, t('editor.ops.setClipProperty'))
  }
}

// 多轨 lane 引用（拖入定位用）
const laneRefs = new Map<string, HTMLElement>()
function setLaneRef(trackId: string, el: unknown): void {
  if (el) laneRefs.set(trackId, el as HTMLElement)
}

// 整行引用（轨道重排的插入位计算用）
const rowRefs = new Map<string, HTMLElement>()
function setRowRef(trackId: string, el: unknown): void {
  if (el) rowRefs.set(trackId, el as HTMLElement)
  else rowRefs.delete(trackId)
}

// ---------- 右键菜单（片段 / 轨道 lane） ----------

interface CtxMenuState { x: number; y: number; clip: EditorClip | null; kind: string | null }
const ctxMenu = ref<CtxMenuState | null>(null)

function openClipMenu(e: MouseEvent, clip: EditorClip, kind: string): void {
  store.select(clip.id)
  ctxMenu.value = { x: Math.min(e.clientX, window.innerWidth - 170), y: Math.min(e.clientY, window.innerHeight - 190), clip, kind }
}
function openLaneMenu(e: MouseEvent, kind: string): void {
  ctxMenu.value = { x: Math.min(e.clientX, window.innerWidth - 170), y: Math.min(e.clientY, window.innerHeight - 190), clip: null, kind }
}

interface CtxItem { label: string; disabled: boolean; run: () => void }

const ctxItems = computed<CtxItem[]>(() => {
  const m = ctxMenu.value
  if (!m) return []
  if (m.clip) {
    const clip = m.clip
    const items: CtxItem[] = [{
      label: t('editor.split'),
      disabled: store.playhead <= clip.start || store.playhead >= clipEnd(clip),
      run: () => store.splitSelectedAtPlayhead(),
    }]
    if (m.kind === 'video') {
      items.push({ label: t('editor.ops.detachAudio'), disabled: clip.assetId == null, run: () => void store.detachAudio(clip.id) })
    }
    if (m.kind !== 'subtitle') {
      items.push({
        label: clip.props.muted ? t('editor.menuUnmute') : t('editor.menuMute'),
        disabled: false,
        run: () => store.applyOrToast({ op: 'setClipProperty', payload: { clipId: clip.id, props: { muted: !clip.props.muted } } }, t('editor.ops.setClipProperty')),
      })
    }
    items.push({ label: t('common.delete'), disabled: false, run: () => store.applyOrToast({ op: 'removeClip', payload: { clipId: clip.id } }, t('editor.ops.removeClip')) })
    return items
  }
  if (m.kind === 'video' || m.kind === 'audio') {
    return [{
      label: t('editor.menuAddSameTrack'),
      disabled: false,
      run: () => store.applyOrToast({ op: 'addTrack', payload: { track: { id: store.newId('track'), kind: m.kind } } }, t('editor.ops.addTrack')),
    }]
  }
  return []
})

function onCtxItemClick(item: CtxItem): void {
  item.run()
  ctxMenu.value = null
}

// ---------- 快捷键提示 ----------

const isMac = typeof navigator !== 'undefined' && /Mac/i.test(navigator.userAgent)
const mod = isMac ? '⌘' : 'Ctrl'

const shortcutList = computed(() => [
  { keys: 'Space', label: `${t('editor.play')}/${t('editor.pause')}` },
  { keys: `${mod}+B`, label: t('editor.split') },
  { keys: `${mod}+C`, label: t('editor.shortcutDuplicate') },
  { keys: 'Delete', label: t('common.delete') },
  { keys: '←/→', label: t('editor.shortcutStepFrame') },
  { keys: 'Shift+←/→', label: t('editor.shortcutStepSecond') },
  { keys: 'Home/End', label: t('editor.shortcutHomeEnd') },
  { keys: `${mod}+Z`, label: t('editor.undo') },
  { keys: `${mod}+Shift+Z`, label: t('editor.redo') },
])

const rulerTicks = computed(() => {  const step = rulerStepSec(PX_PER_SEC.value)
  const ticks: number[] = []
  for (let s = 0; s <= props.totalDuration + 6; s += step) ticks.push(s)
  return ticks
})

const playheadLeft = computed(() => TRACK_HEAD_W + timeToX(store.playhead, PX_PER_SEC.value))
</script>

<template>
  <!-- 点击时间线任意处退出素材临时预览、恢复时间线画面 -->
  <div class="timeline" @pointerdown="store.endAssetPreview()">
    <!-- 时间线工具栏（剪映式：编辑动作在左，缩放/时间在右） -->
    <div class="timeline-toolbar">
      <el-button size="small" text :icon="RefreshLeft" :disabled="!store.history.canUndo" :title="t('editor.undo')" @click="store.undo()" />
      <el-button size="small" text :icon="RefreshRight" :disabled="!store.history.canRedo" :title="t('editor.redo')" @click="store.redo()" />
      <span class="toolbar-divider" />
      <el-button size="small" :icon="Scissor" :disabled="!store.selectedClipId" @click="splitSelected">
        {{ t('editor.split') }}
      </el-button>
      <el-button size="small" :icon="Delete" :disabled="!store.selectedClipId" :title="t('common.delete')" @click="deleteSelected" />
      <span class="toolbar-divider" />
      <el-checkbox
        class="snap-toggle"
        size="small"
        :model-value="store.snappingEnabled"
        @change="store.setSnapping(!store.snappingEnabled)"
      >{{ t('editor.snapToggle') }}</el-checkbox>
      <el-popover placement="bottom-end" :width="240" trigger="click">
        <template #reference>
          <el-button size="small" :icon="QuestionFilled" text :title="t('editor.shortcutsTitle')" />
        </template>
        <div class="shortcut-list">
          <div v-for="s in shortcutList" :key="s.keys + s.label" class="shortcut-row">
            <span class="shortcut-keys">{{ s.keys }}</span>
            <span class="shortcut-label">{{ s.label }}</span>
          </div>
        </div>
      </el-popover>
      <span class="toolbar-spacer" />
      <el-button-group class="zoom-group">
        <el-button size="small" @click="PX_PER_SEC = Math.max(PX_PER_SEC_MIN, PX_PER_SEC - 20)">−</el-button>
        <el-button size="small" @click="PX_PER_SEC = Math.min(PX_PER_SEC_MAX, PX_PER_SEC + 20)">+</el-button>
      </el-button-group>
      <span class="playhead-time">{{ store.playhead.toFixed(2) }}s</span>
    </div>

    <div class="timeline-scroll">
      <div class="timeline-content" :style="{ width: `${contentWidth}px` }">
        <!-- 标尺（时间 0 点在轨头列之后，与轨道 lane 坐标对齐） -->
        <div class="timeline-ruler" @pointerdown="onRulerPointerDown">
          <div class="ruler-head" />
          <span
            v-for="tick in rulerTicks"
            :key="tick"
            class="ruler-tick"
            :style="{ left: `${TRACK_HEAD_W + timeToX(tick, PX_PER_SEC)}px` }"
          >{{ tick }}s</span>
        </div>

        <!-- 轨道 -->
        <div
          v-for="row in trackRows"
          :key="row.track.id"
          :ref="(el) => setRowRef(row.track.id, el)"
          class="track-row"
          :class="{
            hidden: row.track.flags.hidden,
            selected: store.selectedTrackId === row.track.id,
            dragging: reorderMark(row.track.id) === 'dragging',
            'drop-above': reorderMark(row.track.id) === 'above',
            'drop-below': reorderMark(row.track.id) === 'below',
          }"
        >
          <div
            class="track-head"
            :class="{ selected: store.selectedTrackId === row.track.id }"
            @pointerdown="store.selectTrack(row.track.id)"
          >
            <div class="track-head-line">
              <span class="track-grip" :title="t('editor.trackReorder')" @pointerdown="beginTrackDrag($event, row.track)">
                <el-icon><GripVertical /></el-icon>
              </span>
              <span class="track-kind" :data-kind="row.track.kind">{{ t(`editor.trackKinds.${row.track.kind}`) }}</span>
              <span
                class="head-delete"
                :title="row.clips.length ? t('editor.errors.track_not_empty') : t('editor.ops.removeTrack')"
              >
                <el-button
                  class="track-delete"
                  :icon="Close"
                  text
                  size="small"
                  :disabled="row.clips.length > 0"
                  @click="store.applyOrToast({ op: 'removeTrack', payload: { trackId: row.track.id } }, t('editor.ops.removeTrack'))"
                />
              </span>
            </div>
            <div class="track-flag-row">
              <button
                v-for="f in trackFlagButtons(row.track)"
                :key="f.key"
                class="flag-btn"
                :data-key="f.key"
                :class="{ active: row.track.flags[f.key] }"
                :title="t(f.title)"
                @click="toggleTrackFlag(row.track, f.key)"
              >
                <component :is="f.icon" :size="14" />
              </button>
            </div>
          </div>
          <div
            :ref="(el) => setLaneRef(row.track.id, el)"
            class="track-lane"
            :class="{ drop: dropActive === row.track.id, locked: row.track.flags.locked }"
            @pointerdown="onLanePointerDown(row.track.id)"
            @dragover.prevent="dropActive = row.track.id"
            @dragleave="dropActive = null"
            @drop.prevent="onDropAsset($event, row.track.id)"
            @contextmenu.prevent="openLaneMenu($event, row.track.kind)"
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
                draggedOut: dragRender?.clipId === clip.id && dragRender?.trackId !== dragRender?.originTrackId,
                enveloped: !!clipEnvelope(clip),
              }"
              :style="clipStyle(clip)"
              @pointerdown="beginDrag($event, clip, 'move')"
              @contextmenu.prevent="openClipMenu($event, clip, row.track.kind)"
            >
              <svg v-if="clipEnvelope(clip)" class="clip-envelope" viewBox="0 0 100 100" preserveAspectRatio="none">
                <path
                  :d="`${clipEnvelope(clip)} Z`"
                  :style="{ fill: ENVELOPE_COLORS[row.track.kind].fill }"
                />
                <path
                  :d="clipEnvelope(clip) ?? undefined"
                  :style="{ fill: 'none', stroke: ENVELOPE_COLORS[row.track.kind].stroke, strokeWidth: '1.5px' }"
                  vector-effect="non-scaling-stroke"
                />
              </svg>
              <span class="clip-handle left" @pointerdown="beginDrag($event, clip, 'trim-left')" />
              <span class="clip-label">{{ clip.text || (clip.assetId ? `#${clip.assetId}` : clip.id) }}</span>
              <span v-if="audioBadge(clip, row.track.kind)" class="clip-audio">
                <el-icon>
                  <Mute v-if="audioBadge(clip, row.track.kind) === 'muted'" />
                  <Headset v-else />
                </el-icon>
              </span>
              <span class="clip-handle right" @pointerdown="beginDrag($event, clip, 'trim-right')" />
            </div>
            <div v-if="moveGhost(row.track.id)" class="ghost-block" :class="row.track.kind" :style="ghostStyle()" />
            <button
              v-for="j in rowJunctions(row)"
              :key="`junc_${j.clip.id}`"
              class="junction-btn"
              :class="{ active: !!j.clip.props.transition }"
              :style="{ left: `${timeToX(j.x, PX_PER_SEC) - 9}px` }"
              :title="j.clip.props.transition ? t(`editor.transitions.${j.clip.props.transition.type}`) : t('editor.propTransition')"
              @click.stop="openJunctionMenu($event, j.clip)"
            >
              <el-icon><Switch /></el-icon>
            </button>
          </div>
        </div>

        <!-- 播放头 -->
        <div class="playhead" :style="{ left: `${playheadLeft}px` }" />
      </div>
    </div>

    <!-- 右键菜单 -->
    <div v-if="ctxMenu" class="ctx-backdrop" @pointerdown="ctxMenu = null" @contextmenu.prevent="ctxMenu = null">
      <div class="ctx-menu" :style="{ left: `${ctxMenu.x}px`, top: `${ctxMenu.y}px` }" @pointerdown.stop>
        <button
          v-for="(item, i) in ctxItems"
          :key="i"
          class="ctx-item"
          :disabled="item.disabled"
          @click="onCtxItemClick(item)"
        >{{ item.label }}</button>
      </div>
    </div>

    <!-- 接缝转场菜单 -->
    <div v-if="junctionMenu" class="ctx-backdrop" @pointerdown="junctionMenu = null" @contextmenu.prevent="junctionMenu = null">
      <div class="ctx-menu" :style="{ left: `${junctionMenu.x}px`, top: `${junctionMenu.y}px` }" @pointerdown.stop>
        <button
          v-for="tr in TRANSITION_TYPES"
          :key="tr"
          class="ctx-item"
          :class="{ current: junctionMenu.type === tr }"
          @click="applyJunction(tr)"
        >{{ t(`editor.transitions.${tr}`) }}<span v-if="junctionMenu.type === tr"> ✓</span></button>
        <button class="ctx-item" :class="{ current: !junctionMenu.type }" @click="applyJunction(null)">
          {{ t('editor.none') }}<span v-if="!junctionMenu.type"> ✓</span>
        </button>
        <div class="junction-duration">
          <span>{{ t('editor.propTransitionDuration') }}</span>
          <el-input-number
            size="small"
            :model-value="junctionMenu.duration"
            :min="0.1"
            :max="3"
            :step="0.1"
            @change="setJunctionDuration"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.timeline {
  border-top: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
  height: 100%;
  flex-shrink: 0;
  background: var(--el-fill-color-lighter);
}
.timeline-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
}
.toolbar-divider {
  width: 1px;
  height: 16px;
  margin: 0 4px;
  background: var(--el-border-color);
}
.toolbar-spacer { flex: 1; }
.playhead-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-variant-numeric: tabular-nums;
  min-width: 48px;
  text-align: right;
}
.timeline-toolbar :deep(.el-checkbox) { height: 24px; margin-right: 0; }
.shortcut-list { display: flex; flex-direction: column; gap: 6px; }
.shortcut-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; font-size: 12px; }
.shortcut-keys {
  font-family: monospace;
  background: var(--el-fill-color);
  padding: 1px 6px;
  border-radius: 4px;
  white-space: nowrap;
}
.shortcut-label { color: var(--el-text-color-regular); }
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
  display: flex;
  align-items: stretch;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
  z-index: 3;
}
/* 标尺轨头占位：与轨道轨头同宽同底色，横向滚动时同步 sticky，保证刻度 0 点从 lane 起 */
.ruler-head {
  position: sticky;
  left: 0;
  width: 168px;
  flex-shrink: 0;
  background: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color-lighter);
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
.track-row.dragging { opacity: 0.35; }
.track-row.drop-above { box-shadow: inset 0 2px 0 0 var(--el-color-primary); }
.track-row.drop-below { box-shadow: inset 0 -2px 0 0 var(--el-color-primary); }
.track-row.selected .track-lane { background: var(--el-color-primary-light-9); }
.track-head {
  width: 168px;
  flex-shrink: 0;
  padding: 4px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color-lighter);
  position: sticky;
  left: 0;
  z-index: 2;
  user-select: none;
  cursor: pointer;
}
.track-head.selected {
  background: var(--el-color-primary-light-9);
  box-shadow: inset 3px 0 0 0 var(--el-color-primary);
}
.track-head-line {
  display: flex;
  align-items: center;
  gap: 4px;
}
.head-delete { margin-left: auto; }
.track-grip {
  display: flex;
  align-items: center;
  color: var(--el-text-color-placeholder);
  cursor: grab;
  touch-action: none;
}
.track-grip:hover { color: var(--el-text-color-secondary); }
.track-grip :deep(.el-icon) { font-size: 13px; }
.track-kind {
  font-size: 12px;
  font-weight: 600;
}
.track-delete { height: 20px; width: 20px; padding: 0; }
.track-flag-row {
  display: flex;
  align-items: center;
  gap: 4px;
}
.flag-btn {
  width: 26px;
  height: 20px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 4px;
  background: none;
  color: var(--el-text-color-secondary);
  cursor: pointer;
}
.flag-btn:hover { background: var(--el-fill-color); color: var(--el-text-color-primary); }
.flag-btn.active { color: var(--el-color-primary); background: var(--el-color-primary-light-9); border-color: var(--el-color-primary-light-5); }
.flag-btn.active[data-key='hidden'] { color: var(--el-color-info); background: var(--el-color-info-light-9); border-color: var(--el-color-info-light-5); }
.flag-btn.active[data-key='muted'] { color: var(--el-color-danger); background: var(--el-color-danger-light-9); border-color: var(--el-color-danger-light-5); }
.flag-btn.active[data-key='solo'] { color: var(--el-color-warning); background: var(--el-color-warning-light-9); border-color: var(--el-color-warning-light-5); }
.ctx-backdrop { position: fixed; inset: 0; z-index: 100; }
.ctx-menu {
  position: fixed;
  min-width: 140px;
  padding: 4px;
  background: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  box-shadow: var(--el-box-shadow-light);
  display: flex;
  flex-direction: column;
}
.ctx-item {
  border: none;
  background: none;
  text-align: left;
  padding: 6px 12px;
  font-size: 12px;
  color: var(--el-text-color-primary);
  border-radius: 4px;
  cursor: pointer;
}
.ctx-item:hover:not(:disabled) { background: var(--el-fill-color); }
.ctx-item:disabled { color: var(--el-text-color-placeholder); cursor: not-allowed; }
.track-kind[data-kind='video'] { color: var(--el-color-primary); }
.track-kind[data-kind='audio'] { color: var(--el-color-success); }
.track-kind[data-kind='subtitle'] { color: var(--el-color-warning); }
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
.clip-block.dragged-out { opacity: 0.15; }
.clip-block.enveloped { background: transparent; }
.clip-envelope {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
  pointer-events: none;
}
.ghost-block {
  position: absolute;
  top: 6px;
  height: 40px;
  border: 1px dashed var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 4px;
  pointer-events: none;
  z-index: 1;
}
.ghost-block.audio { border-color: var(--el-color-success); background: var(--el-color-success-light-9); }
.clip-label {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  pointer-events: none;
}
.clip-audio {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  color: var(--el-text-color-regular);
  opacity: 0.75;
  pointer-events: none;
}
.clip-audio :deep(.el-icon) { font-size: 12px; }
.junction-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background: var(--el-bg-color-overlay);
  color: var(--el-text-color-secondary);
  cursor: pointer;
  z-index: 2;
}
.junction-btn:hover { color: var(--el-color-primary); border-color: var(--el-color-primary); }
.junction-btn.active {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.junction-btn :deep(.el-icon) { font-size: 11px; }
.junction-duration {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 12px 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border-top: 1px solid var(--el-border-color-lighter);
  margin-top: 4px;
}
.ctx-item.current { color: var(--el-color-primary); }
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
  /* 低于 sticky 轨头（z=2）：横向滚动时播放头从轨头列下方穿过，不遮轨头 */
  z-index: 1;
  pointer-events: none;
}
</style>
