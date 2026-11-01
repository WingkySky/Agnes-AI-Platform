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

import { computed, onUnmounted, ref, type Component } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close, Delete, Headset, Mute, QuestionFilled, RefreshLeft, RefreshRight, Scissor, Switch } from '@element-plus/icons-vue'
import { Eye, EyeOff, Flag, GripVertical, Headphones, Link2, Lock, LockOpen, Subtitles, Volume2, VolumeX } from 'lucide-vue-next'

import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'
import { ImagePlay, Wand2 } from 'lucide-vue-next'
import EditorCoverDialog from './EditorCoverDialog.vue'
import EditorSubtitleDialog from './EditorSubtitleDialog.vue'
import EditorRoughCutDialog from './EditorRoughCutDialog.vue'
import { MIN_CLIP_DURATION, clipEnd, type EditorClip, type EditorTrack, type TrackFlagKey, type TrackKind, type TrackTransition, type TransitionType } from '@/lib/editor-types'
import type { EditorCommand } from '@/lib/editor-commands'
import { TRANSITION_TYPES } from '@/lib/editor-fx-registry'
import { formatSrtCues, parseSrt } from '@/lib/canvas-media'
import { clearStripCaches } from '@/lib/editor-strips'
import { useDownload } from '@/composables/useDownload'
import EditorClipMedia from './EditorClipMedia.vue'
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
  const r = dragRender.value
  if (r?.clipId === clip.id) {
    return {
      left: `${timeToX(r.start, PX_PER_SEC.value)}px`,
      width: `${Math.max(r.duration * PX_PER_SEC.value, 6)}px`,
    }
  }
  const g = r?.group?.find((x) => x.id === clip.id)
  if (g) {
    return {
      left: `${timeToX(g.current, PX_PER_SEC.value)}px`,
      width: `${Math.max(clip.duration * PX_PER_SEC.value, 6)}px`,
    }
  }
  return {
    left: `${timeToX(clip.start, PX_PER_SEC.value)}px`,
    width: `${Math.max(clip.duration * PX_PER_SEC.value, 6)}px`,
  }
}

// ---------- 拖拽 / 裁剪（手势态不入历史） ----------

interface DragRender {
  clipId: string; start: number; duration: number; trimStart: number
  mode: 'move' | 'trim-left' | 'trim-right' | 'slip'; trackId: string; originTrackId: string; kind: string; toNewTrack?: boolean
  /** 整体拖移组（多选+音画联动）：随主片段同位移的其余片段（不含主片段；trackId 不变） */
  group?: Array<{ id: string; start: number; current: number }>
}
const dragRender = ref<DragRender | null>(null)
/** slip 滑切预览（源内入点滑动，位置/时长不变；缩略图条随 trimStart 重绘） */
const slipRender = ref<{ clipId: string; trimStart: number } | null>(null)
/** roll 滚动修剪预览（相邻切点滚动：左片段右缘与右片段左缘同步移动，总长不变） */
const rollRender = ref<{ prevId: string; prevDur: number; selfId: string; selfStart: number; selfDur: number; selfTrim: number; nextStart: number } | null>(null)
/** 拖素材悬停的换源目标片段 */
const dropClipTarget = ref<string | null>(null)

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

/** 同类型显示顶层 lane（order 大在上）；无同类型轨返回 null */
function sameKindLanesTop(kind: string): { trackId: string; el: HTMLElement } | null {
  const lanes = [...laneRefs.entries()]
    .map(([trackId, el]) => ({ trackId, el, track: store.doc?.tracks.find((tr) => tr.id === trackId) }))
    .filter((x) => x.track?.kind === kind)
    .sort((a, b) => b.track!.order - a.track!.order)
  return lanes[0] ?? null
}

/** 跨轨拖动中的幽灵块：画在非原轨目标轨；新建轨态画在顶层 lane 上 */
function moveGhost(trackId: string): boolean {
  const r = dragRender.value
  return !!r && r.mode === 'move' && r.trackId === trackId
    && (r.trackId !== r.originTrackId || !!r.toNewTrack)
}

function ghostStyle(): Record<string, string> {
  const r = dragRender.value!
  return {
    left: `${timeToX(r.start, PX_PER_SEC.value)}px`,
    width: `${Math.max(r.duration * PX_PER_SEC.value, 6)}px`,
  }
}

function beginDrag(e: PointerEvent, clip: EditorClip, mode: DragRender['mode'], group: Array<{ id: string; start: number }> = []): void {
  e.stopPropagation()
  const startX = e.clientX
  const orig = { start: clip.start, duration: clip.duration, trimStart: clip.trimStart }
  dragRender.value = {
    clipId: clip.id, ...orig, mode, trackId: clip.trackId, originTrackId: clip.trackId,
    kind: store.doc?.tracks.find((tr) => tr.id === clip.trackId)?.kind ?? '',
    group: group.filter((g) => g.id !== clip.id).map((g) => ({ ...g, current: g.start })),
  }
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
      // 整体拖移组：位移下限=组内最早片段不越过 0
      const minStart = r.group?.length ? Math.min(...r.group.map((g) => g.start), orig.start) : orig.start
      let next = Math.max(0, orig.start + Math.max(delta, -minStart))
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
      for (const g of r.group ?? []) g.current = g.start + (r.start - orig.start)
      const target = laneUnderPointer(ev.clientY, r.kind)
      // 指针拉出到同类型 lane 群上方（原轨之上）：新建轨态，ghost 画在显示顶层 lane
      const topLane = sameKindLanesTop(r.kind)
      if (!target && topLane && ev.clientY < topLane.el.getBoundingClientRect().top) {
        r.toNewTrack = true
        r.trackId = topLane.trackId
      } else {
        r.toNewTrack = false
        if (target) r.trackId = target
      }
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

async function commitDrag(): Promise<void> {
  const r = dragRender.value
  dragRender.value = null
  if (!r) return
  if (r.mode === 'move') {
    const payload: Record<string, unknown> = { clipId: r.clipId, start: Math.round(r.start * 1000) / 1000 }
    if (r.toNewTrack) {
      // 上移新建轨：顶层开新轨（无轨数上限）再把片段挪进去；两步各自可撤销
      const nt = await store.createTopTrackOfKind(r.kind as 'video' | 'audio')
      if (!nt) return
      payload.trackId = nt.id
    } else if (r.trackId !== r.originTrackId) {
      payload.trackId = r.trackId
    }
    if (r.group?.length) {
      // 整体拖移：主片段+组内片段一批入单历史（任一碰撞整批不动）
      store.applyBatch(
        [
          { op: 'moveClip', payload } as EditorCommand,
          ...r.group.map((g) => ({ op: 'moveClip', payload: { clipId: g.id, start: Math.round(g.current * 1000) / 1000 } } as EditorCommand)),
        ],
        t('editor.ops.moveClip'),
      )
    } else {
      store.applyOrToast({ op: 'moveClip', payload }, t('editor.ops.moveClip'))
    }
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

// ---------- 多选（Ctrl/Cmd 点选切换）与框选 ----------

function clipSelected(clip: EditorClip): boolean {
  return store.selectedClipIds.includes(clip.id)
}

/** 片段按下：Alt+拖块=滑切；Alt+拖缘=滚动修剪；Ctrl/Cmd 切换多选；已在多选/联动组里则整组拖移；否则单选 */
function onClipPointerDown(e: PointerEvent, clip: EditorClip, mode: DragRender['mode']): void {
  if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
    if (mode === 'move') {
      void beginSlip(e, clip)
      return
    }
    if (mode === 'trim-left' || mode === 'trim-right') {
      void beginRoll(e, clip, mode)
      return
    }
  }
  if (mode === 'move' && (e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey) {
    e.stopPropagation()
    store.selectMany([clip.id], 'toggle')
    return
  }
  const groupIds = mode === 'move' && clipSelected(clip)
    ? [...store.selectedClipIds]
    : mode === 'move' ? [clip.id] : []
  if (!clipSelected(clip)) store.select(clip.id)
  // 音画联动：拖组内任一片段，同组其余片段自动并入（无论是否多选）
  if (mode === 'move' && clip.linkId) {
    for (const c of store.doc?.clips ?? []) {
      if (c.linkId === clip.linkId && c.id !== clip.id && !groupIds.includes(c.id)) groupIds.push(c.id)
    }
  }
  const group = groupIds
    .map((id) => store.doc?.clips.find((c) => c.id === id))
    .filter((c): c is EditorClip => !!c)
    .filter((c) => c.id === clip.id || !store.doc?.tracks.find((tr) => tr.id === c.trackId)?.flags.locked)
    .map((c) => ({ id: c.id, start: c.start }))
  beginDrag(e, clip, mode, group)
}

/** slip 滑切：位置/时长不变，源内入点滑动（Alt+拖块主体）；越界钳制在源可用跨度内 */
async function beginSlip(e: PointerEvent, clip: EditorClip): Promise<void> {
  e.stopPropagation()
  store.select(clip.id)
  const track = store.doc?.tracks.find((tr) => tr.id === clip.trackId)
  if (!track || track.kind === 'subtitle' || clip.assetId == null) return
  const asset = await store.fetchAsset(clip.assetId)
  if (!asset?.asset_url || asset.media_type === 'image') {
    ElMessage.info(t('editor.slipNoMedia'))
    return
  }
  const origTrim = clip.trimStart
  const startX = e.clientX
  // probe 期间可能已松手（快速点按）：先挂一次性取消哨兵，再异步探测
  let cancelled = false
  const cancel = (): void => { cancelled = true }
  window.addEventListener('pointerup', cancel, { once: true })
  try {
    const srcDur = await store.probeMediaDuration(asset.asset_url)
    const speed = clip.props.speed ?? 1
    const maxTrim = Math.max(0, srcDur - clip.duration * speed)
    if (cancelled || !(srcDur > 0) || maxTrim <= 0) {
      if (!cancelled && maxTrim <= 0) ElMessage.info(t('editor.slipNoRoom'))
      return
    }
    slipRender.value = { clipId: clip.id, trimStart: origTrim }
    const move = (ev: PointerEvent): void => {
      const s = slipRender.value
      if (!s) return
      // 屏幕位移 → 时间线位移 → 源内位移（×speed）；拖左=入点前移看更早的画面
      const delta = ((ev.clientX - startX) / PX_PER_SEC.value) * speed
      s.trimStart = Math.round(Math.min(maxTrim, Math.max(0, origTrim + delta)) * 1000) / 1000
    }
    const up = (): void => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      const s = slipRender.value
      slipRender.value = null
      if (s && s.trimStart !== origTrim) {
        store.applyOrToast({ op: 'trimClip', payload: { clipId: clip.id, trimStart: s.trimStart } }, t('editor.ops.trimClip'))
      }
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  } finally {
    window.removeEventListener('pointerup', cancel)
  }
}

/** slip 中传给素材条的片段（trimStart 实时跟随，缩略图随源内滑动） */
function renderClip(clip: EditorClip): EditorClip {
  const s = slipRender.value
  if (s?.clipId === clip.id) return { ...clip, trimStart: s.trimStart }
  const r = rollRender.value
  if (r) {
    if (r.prevId === clip.id) return { ...clip, duration: r.prevDur }
    if (r.selfId === clip.id) return { ...clip, start: r.selfStart, duration: r.selfDur, trimStart: r.selfTrim }
  }
  return clip
}

/** roll 滚动修剪：Alt+拖缘=相邻切点滚动（左片段右缘=右片段左缘同步移动，总长不变）。
 *  无相邻片段则不启动（普通修剪走无修饰键手势）。双源素材时长探测做源内钳制，
 *  probe 期间松手取消（slip 同款哨兵）。 */
async function beginRoll(e: PointerEvent, clip: EditorClip, side: 'trim-left' | 'trim-right'): Promise<void> {
  e.stopPropagation()
  store.select(clip.id)
  const doc = store.doc
  const track = doc?.tracks.find((tr) => tr.id === clip.trackId)
  if (!doc || !track || track.kind === 'subtitle') return
  const ordered = doc.clips.filter((c) => c.trackId === track.id).sort((a, b) => a.start - b.start)
  const idx = ordered.findIndex((c) => c.id === clip.id)
  if (idx < 0) return
  const left = side === 'trim-left' ? ordered[idx - 1] : clip
  const right = side === 'trim-left' ? clip : ordered[idx + 1]
  if (!left || !right) return
  if (Math.abs(clipEnd(left) - right.start) >= 0.02) return // 无缝邻接才成 roll
  const locked = doc.tracks.find((tr) => tr.id === left.trackId)?.flags.locked
    || doc.tracks.find((tr) => tr.id === right.trackId)?.flags.locked
  if (locked) return

  let cancelled = false
  const cancel = (): void => { cancelled = true }
  window.addEventListener('pointerup', cancel, { once: true })
  const startX = e.clientX
  try {
    // 双源探测（图片素材 Infinity=无源内钳制）
    const probeOf = async (c: EditorClip): Promise<number> => {
      if (c.assetId == null) return Infinity
      const a = await store.fetchAsset(c.assetId)
      if (!a?.asset_url || a.media_type === 'image') return Infinity
      return store.probeMediaDuration(a.asset_url)
    }
    const [leftSrc, rightSrc] = await Promise.all([probeOf(left), probeOf(right)])
    const leftSpeed = left.props.speed ?? 1
    const rightSpeed = right.props.speed ?? 1
    const rightEnd = clipEnd(right)
    // 切点域：两片段各保 MIN 时长；左源出点/右源出点不越源（右入点不越源起点）
    const cutMin = Math.max(
      left.start + MIN_CLIP_DURATION,
      rightEnd - (rightSrc - right.trimStart) / rightSpeed,
      right.start - right.trimStart / rightSpeed,
    )
    const cutMax = Math.min(
      rightEnd - MIN_CLIP_DURATION,
      left.start + (leftSrc - left.trimStart) / leftSpeed,
    )
    if (cancelled || !(cutMax > cutMin)) return
    const origCut = clipEnd(left)
    rollRender.value = {
      prevId: left.id, prevDur: left.duration,
      selfId: right.id, selfStart: right.start, selfDur: right.duration, selfTrim: right.trimStart,
      nextStart: right.start,
    }
    const move = (ev: PointerEvent): void => {
      const rr = rollRender.value
      if (!rr) return
      const cut = Math.round(Math.min(cutMax, Math.max(cutMin, origCut + (ev.clientX - startX) / PX_PER_SEC.value)) * 1000) / 1000
      rr.prevDur = Math.round((cut - left.start) * 1000) / 1000
      rr.selfStart = cut
      rr.selfDur = Math.round((rightEnd - cut) * 1000) / 1000
      rr.selfTrim = Math.round((right.trimStart + (cut - right.start) * rightSpeed) * 1000) / 1000
      rr.nextStart = cut
    }
    const up = (): void => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      const rr = rollRender.value
      rollRender.value = null
      if (!rr || (rr.prevDur === left.duration && rr.selfStart === right.start)) return
      // 顺序敏感：切点右移=左片段先长进去会撞右片段旧位置——右片段先让位；左移反之
      const leftCmd = { op: 'trimClip', payload: { clipId: left.id, duration: rr.prevDur } }
      const rightCmd = { op: 'trimClip', payload: { clipId: right.id, start: rr.selfStart, duration: rr.selfDur, trimStart: rr.selfTrim } }
      const cmds: EditorCommand[] = rr.selfStart >= right.start
        ? [rightCmd, leftCmd] as EditorCommand[]
        : [leftCmd, rightCmd] as EditorCommand[]
      store.applyBatch(cmds, t('editor.ops.trimClip'))
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  } finally {
    window.removeEventListener('pointerup', cancel)
  }
}

interface MarqueeState { x0: number; y0: number; x1: number; y1: number }
const marquee = ref<MarqueeState | null>(null)
const contentEl = ref<HTMLElement | null>(null)

const marqueeStyle = computed((): Record<string, string> => {
  const m = marquee.value
  const content = contentEl.value
  if (!m || !content) return {}
  const o = content.getBoundingClientRect()
  return {
    left: `${Math.min(m.x0, m.x1) - o.left}px`,
    top: `${Math.min(m.y0, m.y1) - o.top}px`,
    width: `${Math.abs(m.x1 - m.x0)}px`,
    height: `${Math.abs(m.y1 - m.y0)}px`,
  }
})

/** 轨道空白按下：先选中轨道；拖动超阈值转框选（跨轨批量选择，松手按矩形相交） */
function onLanePointerDown(e: PointerEvent, trackId: string): void {
  store.selectTrack(trackId)
  const x0 = e.clientX
  const y0 = e.clientY
  let active = false
  const move = (ev: PointerEvent) => {
    if (!active && Math.hypot(ev.clientX - x0, ev.clientY - y0) < 6) return
    active = true
    marquee.value = { x0, y0, x1: ev.clientX, y1: ev.clientY }
  }
  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
    const m = marquee.value
    marquee.value = null
    if (active && m) commitMarquee(m)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}

function commitMarquee(m: MarqueeState): void {
  const doc = store.doc
  if (!doc) return
  const left = Math.min(m.x0, m.x1)
  const right = Math.max(m.x0, m.x1)
  const top = Math.min(m.y0, m.y1)
  const bottom = Math.max(m.y0, m.y1)
  const hit: string[] = []
  for (const c of doc.clips) {
    const lane = laneRefs.get(c.trackId)
    const track = doc.tracks.find((tr) => tr.id === c.trackId)
    if (!lane || !track || track.flags.locked) continue
    const rect = lane.getBoundingClientRect()
    const cx0 = rect.left + timeToX(c.start, PX_PER_SEC.value)
    const cx1 = rect.left + timeToX(clipEnd(c), PX_PER_SEC.value)
    if (cx1 > left && cx0 < right && rect.bottom > top && rect.top < bottom) hit.push(c.id)
  }
  if (hit.length) store.selectMany(hit)
}

// ---------- 轨道选中 / 状态开关 / 轨头拖拽重排 ----------

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

/** 删除选中片段（音画联动组整组删；多选整批单历史） */
function deleteSelected(): void {
  const ids = store.selectedClipIds
  if (!ids.length) return
  if (ids.length === 1) {
    store.removeClipWithLink(ids[0])
    return
  }
  store.applyBatch(
    ids.map((id) => ({ op: 'removeClip', payload: { clipId: id } } as EditorCommand)),
    t('editor.ops.removeClip'),
  )
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

/** 拖素材悬停的换源目标判定：媒体轨片段且素材类型匹配 */
function canReplace(clip: EditorClip, kind: string): boolean {
  if (kind === 'subtitle' || clip.assetId == null) return false
  const dragType = store.assetCache.get(lastDragAssetId())?.media_type
  if (!dragType) return true // 素材未缓存时先允许悬停高亮，drop 时再校验
  return kind === 'audio' ? dragType === 'audio' : dragType === 'video' || dragType === 'image'
}

/** 最近一次拖入的素材 id（EditorAssets 卡片 dragstart 写入 dataTransfer；缓存同款便于悬停判定） */
let lastDragAsset = 0
function lastDragAssetId(): number {
  return lastDragAsset
}

/** 拖素材到片段上松手 = 换源（保留位置与属性，confirm 后替换） */
async function onDropReplace(e: DragEvent, clip: EditorClip): Promise<void> {
  dropClipTarget.value = null
  const assetId = Number(e.dataTransfer?.getData('text/asset-id'))
  if (!assetId || clip.assetId == null) return
  lastDragAsset = assetId
  if (assetId === clip.assetId) return
  const asset = await store.fetchAsset(assetId)
  if (!asset) return
  try {
    await ElMessageBox.confirm(
      t('editor.replaceConfirm', { name: asset.name || assetId }),
      t('editor.ops.replaceSource'),
      { confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel'), type: 'warning' },
    )
  } catch {
    return
  }
  await store.replaceClipSource(clip.id, asset)
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

/** 包络填充/描边跟轨道主色：填充是素材条之上的半透明色罩（fill-opacity 见下），
 * 曲线之上露出 lane 底色；描边全强度保证曲线在缩略图/音波上可读 */
const ENVELOPE_FILL_OPACITY = 0.5
const ENVELOPE_COLORS: Record<string, { fill: string; stroke: string }> = {
  video: { fill: 'var(--el-color-primary-light-8)', stroke: 'var(--el-color-primary-light-5)' },
  audio: { fill: 'var(--el-color-success-light-8)', stroke: 'var(--el-color-success-light-5)' },
  subtitle: { fill: 'var(--el-color-warning-light-8)', stroke: 'var(--el-color-warning-light-5)' },
}

/** 同轨相邻接缝（整轨全帧链才有转场链路）：转场挂在前一片段，接缝处可点击选取 */
function rowJunctions(row: { track: EditorTrack; clips: EditorClip[] }): { clip: EditorClip; x: number; transition: TrackTransition | null }[] {
  if (!row.clips.length || row.track.kind !== 'video') return []
  const fullFrame = row.clips.every((c) => !c.props.rect || (c.props.rect.w >= 1 && c.props.rect.h >= 1))
  if (!fullFrame) return []
  const out: { clip: EditorClip; x: number; transition: TrackTransition | null }[] = []
  for (let i = 0; i + 1 < row.clips.length; i++) {
    if (Math.abs(clipEnd(row.clips[i]) - row.clips[i + 1].start) < 0.02) {
      const transition = row.track.transitions?.find((tr) => tr.afterClipId === row.clips[i].id) ?? null
      out.push({ clip: row.clips[i], x: clipEnd(row.clips[i]), transition })
    }
  }
  return out
}

interface JunctionState { x: number; y: number; trackId: string; clipId: string; type: TransitionType | null; duration: number }
const junctionMenu = ref<JunctionState | null>(null)
const coverDialogVisible = ref(false)
const subtitleDialogVisible = ref(false)
const roughCutDialogVisible = ref(false)

function openJunctionMenu(e: MouseEvent, clip: EditorClip, transition: TrackTransition | null): void {
  junctionMenu.value = {
    x: Math.min(e.clientX, window.innerWidth - 200),
    y: Math.min(e.clientY, window.innerHeight - 230),
    trackId: clip.trackId,
    clipId: clip.id,
    type: transition?.type ?? null,
    duration: transition?.duration ?? 0.5,
  }
}

function applyJunction(type: TransitionType | null): void {
  const j = junctionMenu.value!
  store.applyOrToast(
    type
      ? { op: 'setTransition', payload: { trackId: j.trackId, afterClipId: j.clipId, transitionId: `tr_${Date.now().toString(36)}`, type, duration: j.duration } }
      : { op: 'removeTransition', payload: { trackId: j.trackId, afterClipId: j.clipId } },
    t('editor.propTransition'),
  )
  junctionMenu.value = null
}

/** 转场已激活时改时长立即生效（菜单不关闭） */
function setJunctionDuration(v: number | undefined): void {
  const j = junctionMenu.value
  if (!j) return
  j.duration = v ?? 0.5
  if (j.type) {
    store.applyOrToast({ op: 'setTransition', payload: { trackId: j.trackId, afterClipId: j.clipId, transitionId: `tr_${Date.now().toString(36)}`, type: j.type, duration: j.duration } }, t('editor.propTransition'))
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

interface CtxMenuState { x: number; y: number; clip: EditorClip | null; kind: string | null; trackId: string | null; multi: boolean }
const ctxMenu = ref<CtxMenuState | null>(null)

function openClipMenu(e: MouseEvent, clip: EditorClip, kind: string): void {
  // 右键片段已在多选组内 → 整组菜单；否则单选该片段
  const multi = clipSelected(clip) && store.selectedClipIds.length > 1
  if (!multi) store.select(clip.id)
  ctxMenu.value = { x: Math.min(e.clientX, window.innerWidth - 190), y: Math.min(e.clientY, window.innerHeight - 240), clip, kind, trackId: null, multi }
}
function openLaneMenu(e: MouseEvent, track: EditorTrack): void {
  ctxMenu.value = { x: Math.min(e.clientX, window.innerWidth - 190), y: Math.min(e.clientY, window.innerHeight - 240), clip: null, kind: track.kind, trackId: track.id, multi: false }
}

interface CtxItem { label: string; disabled: boolean; run: () => void }

const ctxItems = computed<CtxItem[]>(() => {
  const m = ctxMenu.value
  if (!m) return []
  if (m.clip && m.multi) {
    // 多选整组：批量删除/批量静音（视频+音频组）
    const ids = store.selectedClipIds
    const clips = ids.map((id) => store.doc?.clips.find((c) => c.id === id)).filter((c): c is EditorClip => !!c)
    const mediaClips = clips.filter((c) => {
      const kind = store.doc?.tracks.find((tr) => tr.id === c.trackId)?.kind
      return kind === 'video' || kind === 'audio'
    })
    const allMuted = mediaClips.length > 0 && mediaClips.every((c) => c.props.muted === true)
    return [
      {
        label: t('editor.menuDeleteSelected', { n: ids.length }),
        disabled: false,
        run: () => store.applyBatch(ids.map((id) => ({ op: 'removeClip', payload: { clipId: id } } as EditorCommand)), t('editor.ops.removeClip')),
      },
      ...(mediaClips.length ? [{
        label: allMuted ? t('editor.menuUnmuteSelected') : t('editor.menuMuteSelected'),
        disabled: false,
        run: () => store.applyBatch(
          mediaClips.map((c) => ({ op: 'setClipProperty', payload: { clipId: c.id, props: { muted: !allMuted } } } as EditorCommand)),
          t('editor.ops.setClipProperty'),
        ),
      }] : []),
    ]
  }
  if (m.clip) {
    const clip = m.clip
    const items: CtxItem[] = [{
      label: t('editor.split'),
      disabled: store.playhead <= clip.start || store.playhead >= clipEnd(clip),
      run: () => store.splitSelectedAtPlayhead(),
    }]
    if (m.kind === 'video') {
      items.push({ label: t('editor.ops.detachAudio'), disabled: clip.assetId == null, run: () => void store.detachAudio(clip.id) })
      items.push({
        label: t('editor.menuFreezeFrame'),
        disabled: store.playhead <= clip.start || store.playhead >= clipEnd(clip),
        run: () => void store.freezeFrame(clip.id),
      })
    }
    if (m.kind !== 'subtitle') {
      items.push({
        label: clip.props.muted ? t('editor.menuUnmute') : t('editor.menuMute'),
        disabled: false,
        run: () => store.applyOrToast({ op: 'setClipProperty', payload: { clipId: clip.id, props: { muted: !clip.props.muted } } }, t('editor.ops.setClipProperty')),
      })
      items.push({
        label: t('editor.menuRippleRemove'),
        disabled: false,
        run: () => store.applyOrToast({ op: 'rippleRemoveClip', payload: { clipId: clip.id } }, t('editor.ops.rippleRemoveClip')),
      })
    }
    if (clip.linkId) {
      items.push({
        label: t('editor.menuUnlink'),
        disabled: false,
        run: () => store.unlinkClipGroup(clip.id),
      })
    }
    items.push({ label: t('common.delete'), disabled: false, run: () => store.removeClipWithLink(clip.id) })
    return items
  }
  if (m.kind === 'subtitle' && m.trackId) {
    const trackId = m.trackId
    const hasClips = store.doc?.clips.some((c) => c.trackId === trackId) ?? false
    return [
      { label: t('editor.importSrt'), disabled: false, run: () => importSrt(trackId) },
      { label: t('editor.exportSrt'), disabled: !hasClips, run: () => exportSrt(trackId) },
    ]
  }
  if (m.kind === 'video' || m.kind === 'audio') {
    const trackId = m.trackId!
    const clipCount = store.doc?.clips.filter((c) => c.trackId === trackId).length ?? 0
    return [
      {
        label: t('editor.menuCloseGaps'),
        disabled: clipCount < 2,
        run: () => store.applyOrToast({ op: 'closeGaps', payload: { trackId } }, t('editor.ops.closeGaps')),
      },
      {
        label: t('editor.menuAddSameTrack'),
        disabled: false,
        run: () => store.applyOrToast({ op: 'addTrack', payload: { track: { id: store.newId('track'), kind: m.kind } } }, t('editor.ops.addTrack')),
      },
    ]
  }
  return []
})

function importSrt(trackId: string): void {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.srt,text/plain'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const segments = parseSrt(await file.text())
    if (!segments.length) {
      ElMessage.warning(t('editor.srtEmpty'))
      return
    }
    const ok = store.applyOrToast({
      op: 'rebuildSubtitleClips',
      payload: {
        trackId,
        clips: segments.map((s) => ({ id: store.newId('clip'), start: s.start_time, duration: s.duration, text: s.text })),
      },
    }, t('editor.ops.rebuildSubtitleClips'))
    if (ok) ElMessage.success(t('editor.srtImported', { n: segments.length }))
  }
  input.click()
}

function exportSrt(trackId: string): void {
  const doc = store.doc
  if (!doc) return
  const clips = doc.clips
    .filter((c) => c.trackId === trackId)
    .sort((a, b) => a.start - b.start)
    .map((c) => ({ start_time: c.start, duration: c.duration, text: c.text ?? '' }))
  const srt = formatSrtCues(clips)
  void useDownload().triggerDownload(
    new Blob([srt], { type: 'application/x-subrip' }),
    `${store.title || 'subtitles'}.srt`,
  )
}

onUnmounted(clearStripCaches)

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
  { keys: 'Alt+拖', label: t('editor.shortcutSlip') },
  { keys: 'Alt+拖缘', label: t('editor.shortcutRoll') },
  { keys: 'Delete', label: t('common.delete') },
  { keys: 'M', label: t('editor.ops.addMarker') },
  { keys: 'I/O', label: `${t('editor.ioIn')} / ${t('editor.ioOut')}` },
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

// ---------- I/O 点可视化（标尺括号 + 区间淡色带；会话本地态不落文档） ----------

const ioBand = computed((): Record<string, string> => {
  const a = store.inPoint
  const b = store.outPoint
  if (a == null || b == null || b <= a) return {}
  return {
    left: `${TRACK_HEAD_W + timeToX(a, PX_PER_SEC.value)}px`,
    width: `${timeToX(b - a, PX_PER_SEC.value)}px`,
  }
})
</script>

<template>
  <!-- 点击时间线任意处退出素材临时预览、恢复时间线画面 -->
  <div class="timeline" @pointerdown="store.endAssetPreview()">
    <!-- 时间线工具栏（剪映式：编辑动作在左，缩放/时间在右） -->
    <div class="timeline-toolbar">
      <el-button size="small" text :icon="ImagePlay" :title="t('editor.coverButton')" @click="coverDialogVisible = true">{{ t('editor.coverButton') }}</el-button>
      <el-button size="small" text :icon="Subtitles" :title="t('editor.subtitleWorkspaceTitle')" @click="subtitleDialogVisible = true">{{ t('editor.subtitleWorkspace') }}</el-button>
      <el-button size="small" text :icon="Wand2" :title="t('editor.roughCutTitle')" @click="roughCutDialogVisible = true">{{ t('editor.roughCutEntry') }}</el-button>
      <el-button size="small" text :icon="RefreshLeft" :disabled="!store.history.canUndo" :title="t('editor.undo')" @click="store.undo()" />
      <el-button size="small" text :icon="RefreshRight" :disabled="!store.history.canRedo" :title="t('editor.redo')" @click="store.redo()" />
      <span class="toolbar-divider" />
      <el-button size="small" :icon="Scissor" :disabled="!store.selectedClipId" @click="splitSelected">
        {{ t('editor.split') }}
      </el-button>
      <el-button size="small" :icon="Delete" :disabled="!store.selectedClipIds.length" :title="t('common.delete')" @click="deleteSelected" />
      <el-button size="small" text :icon="Flag" :title="t('editor.markerAdd')" @click="store.addMarkerAtPlayhead()">{{ t('editor.markerAddButton') }}</el-button>
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
      <div ref="contentEl" class="timeline-content" :style="{ width: `${contentWidth}px` }">
        <!-- 标尺（时间 0 点在轨头列之后，与轨道 lane 坐标对齐） -->
        <div class="timeline-ruler" @pointerdown="onRulerPointerDown">
          <div class="ruler-head" />
          <span
            v-for="tick in rulerTicks"
            :key="tick"
            class="ruler-tick"
            :style="{ left: `${TRACK_HEAD_W + timeToX(tick, PX_PER_SEC)}px` }"
          >{{ tick }}s</span>
          <!-- 时间线标记：点击跳转、双击删除（随文档持久化） -->
          <button
            v-for="m in store.doc?.markers ?? []"
            :key="m.id"
            class="ruler-marker"
            :style="{ left: `${TRACK_HEAD_W + timeToX(m.time, PX_PER_SEC) - 5}px` }"
            :title="`${m.label || `${m.time}s`} · ${t('editor.markerRemoveHint')}`"
            @pointerdown.stop="store.playhead = m.time"
            @dblclick.stop="store.applyOrToast({ op: 'removeMarker', payload: { markerId: m.id } }, t('editor.ops.removeMarker'))"
          />
          <!-- I/O 点（I/O 键；同点再按=清除） -->
          <div
            v-if="store.inPoint != null"
            class="io-tick io-in"
            :style="{ left: `${TRACK_HEAD_W + timeToX(store.inPoint, PX_PER_SEC)}px` }"
            :title="t('editor.ioIn')"
          >I</div>
          <div
            v-if="store.outPoint != null"
            class="io-tick io-out"
            :style="{ left: `${TRACK_HEAD_W + timeToX(store.outPoint, PX_PER_SEC)}px` }"
            :title="t('editor.ioOut')"
          >O</div>
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
            @pointerdown="onLanePointerDown($event, row.track.id)"
            @dragover.prevent="dropActive = row.track.id"
            @dragleave="dropActive = null"
            @drop.prevent="onDropAsset($event, row.track.id)"
            @contextmenu.prevent="openLaneMenu($event, row.track)"
          >
            <div
              v-for="clip in row.clips"
              :key="clip.id"
              class="clip-block"
              :class="{
                selected: clipSelected(clip),
                video: row.track.kind === 'video',
                audio: row.track.kind === 'audio',
                subtitle: row.track.kind === 'subtitle',
                ghost: dragRender?.clipId === clip.id || !!dragRender?.group?.some((g) => g.id === clip.id),
                draggedOut: dragRender?.clipId === clip.id && dragRender?.trackId !== dragRender?.originTrackId,
                enveloped: !!clipEnvelope(clip),
                'drop-replace': dropClipTarget === clip.id,
              }"
              :style="clipStyle(clip)"
              @pointerdown="onClipPointerDown($event, clip, 'move')"
              @contextmenu.prevent.stop="openClipMenu($event, clip, row.track.kind)"
              @dragover.prevent.stop="canReplace(clip, row.track.kind) && (dropClipTarget = clip.id)"
              @dragleave.stop="dropClipTarget === clip.id && (dropClipTarget = null)"
              @drop.prevent.stop="onDropReplace($event, clip)"
            >
              <EditorClipMedia v-if="row.track.kind !== 'subtitle'" :clip="renderClip(clip)" :kind="row.track.kind" />
              <svg v-if="clipEnvelope(clip)" class="clip-envelope" viewBox="0 0 100 100" preserveAspectRatio="none">
                <path
                  :d="`${clipEnvelope(clip)} Z`"
                  :style="{ fill: ENVELOPE_COLORS[row.track.kind].fill, fillOpacity: ENVELOPE_FILL_OPACITY }"
                />
                <path
                  :d="clipEnvelope(clip) ?? undefined"
                  :style="{ fill: 'none', stroke: ENVELOPE_COLORS[row.track.kind].stroke, strokeWidth: '1.5px' }"
                  vector-effect="non-scaling-stroke"
                />
              </svg>
              <span class="clip-handle left" @pointerdown="onClipPointerDown($event, clip, 'trim-left')" />
              <span class="clip-label">{{ clip.text || (clip.assetId ? `#${clip.assetId}` : clip.id) }}</span>
              <span v-if="audioBadge(clip, row.track.kind)" class="clip-audio">
                <el-icon>
                  <Mute v-if="audioBadge(clip, row.track.kind) === 'muted'" />
                  <Headset v-else />
                </el-icon>
              </span>
              <span v-if="clip.linkId" class="clip-audio clip-link" :title="t('editor.linkBadge')">
                <el-icon><Link2 /></el-icon>
              </span>
              <span class="clip-handle right" @pointerdown="onClipPointerDown($event, clip, 'trim-right')" />
            </div>
            <div
              v-if="moveGhost(row.track.id)"
              class="ghost-block"
              :class="[row.track.kind, { 'new-track': dragRender?.toNewTrack && dragRender.trackId === row.track.id }]"
              :style="ghostStyle()"
            />
            <button
              v-for="j in rowJunctions(row)"
              :key="`junc_${j.clip.id}`"
              class="junction-btn"
              :class="{ active: !!j.transition }"
              :style="{ left: `${timeToX(j.x, PX_PER_SEC) - 9}px` }"
              :title="j.transition ? t(`editor.transitions.${j.transition.type}`) : t('editor.propTransition')"
              @pointerdown.stop
              @click.stop="openJunctionMenu($event, j.clip, j.transition)"
            >
              <el-icon><Switch /></el-icon>
            </button>
          </div>
        </div>

        <!-- I/O 区间淡色带（齐备且 out>in 时显示；盖在 lane 区、不挡交互） -->
        <div v-if="ioBand.left" class="io-band" :style="ioBand" />

        <!-- 框选矩形（拖动中） -->
        <div v-if="marquee" class="marquee-rect" :style="marqueeStyle" />

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

    <EditorCoverDialog v-model="coverDialogVisible" />
    <EditorSubtitleDialog v-model="subtitleDialogVisible" />
    <EditorRoughCutDialog v-model="roughCutDialogVisible" />
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
/* 时间线标记（菱形，贴标尺下缘）：点击跳转、双击删除 */
.ruler-marker {
  position: absolute;
  bottom: 2px;
  width: 10px;
  height: 10px;
  padding: 0;
  border: none;
  background: var(--el-color-warning);
  transform: rotate(45deg);
  border-radius: 2px;
  cursor: pointer;
  z-index: 4;
}
.ruler-marker:hover { background: var(--el-color-warning-light-3); }
/* 框选矩形 */
.marquee-rect {
  position: absolute;
  border: 1px solid var(--el-color-primary);
  background: var(--el-color-primary-light-8);
  pointer-events: none;
  z-index: 5;
}
/* I/O 点标尺括号 + 区间淡色带 */
.io-tick {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 8px;
  font-weight: 700;
  color: #fff;
  pointer-events: none;
  z-index: 4;
}
.io-in { background: var(--el-color-success); margin-left: -3px; }
.io-out { background: var(--el-color-danger); }
.io-band {
  position: absolute;
  top: 22px;
  bottom: 0;
  background: rgba(64, 158, 255, 0.07);
  border-left: 1px solid var(--el-color-success);
  border-right: 1px solid var(--el-color-danger);
  pointer-events: none;
  z-index: 0;
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
.ghost-block.new-track {
  border: 1px dashed var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  opacity: 0.9;
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
  position: relative;
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
.clip-link { right: 26px; color: var(--el-color-success); }
.clip-block.drop-replace { outline: 2px dashed var(--el-color-success); }
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
