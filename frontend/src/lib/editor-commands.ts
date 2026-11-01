/* =====================================================
 * 剪辑器命令状态机 — 17 op 纯函数命令表
 *
 * - 每个命令 (doc, payload) => 新 doc，不可变更新（未变子树结构共享）
 * - fail-closed：未知 op / 非法 payload 抛 EditorCommandError，不改状态（可安全回放）
 * - 碰撞拒绝：video/audio 轨禁止重叠（lib/editor-placement 半开区间判定，贴边不冲突）；
 *   字幕轨 cue 可共存豁免
 * - 命令可序列化 {op, payload}；持久化的只有 document 快照，命令表回放仅用于测试
 * - 文案不在此层：错误码由组件层 i18n 转译
 * ===================================================== */

import {
  type ClipEffect,
  type ClipProps,
  type EditorClip,
  type EditorDocument,
  type EditorTrack,
  EMPTY_TRACK_FLAGS,
  MIN_CLIP_DURATION,
  clipEnd,
  isEffectType,
  isTransitionType,
  isTrackFlagsPatch,
  isTrackKind,
} from './editor-types'
import { canPlaceOnTrack, needsCollisionCheck } from './editor-placement'
import { isCameraType } from './editor-camera-registry'

/** 命令错误码（组件层负责 i18n） */
export type CommandErrorCode =
  | 'unknown_op'
  | 'invalid_payload'
  | 'clip_not_found'
  | 'track_not_found'
  | 'track_locked'
  | 'duplicate_id'
  | 'track_not_empty'
  | 'not_subtitle_track'
  | 'split_outside_clip'
  | 'split_too_close'
  | 'overlap'
  | 'not_audio_track'

export class EditorCommandError extends Error {
  readonly code: CommandErrorCode
  constructor(code: CommandErrorCode, detail = '') {
    super(detail ? `${code}: ${detail}` : code)
    this.code = code
  }
}

export type CommandPayload = Record<string, unknown>

export interface EditorCommand {
  op: EditorOp
  payload: CommandPayload
}

export const EDITOR_OPS = [
  'addClip', 'moveClip', 'trimClip', 'splitClip', 'removeClip', 'detachAudio', 'setClipProperty',
  'addSubtitle', 'removeSubtitle', 'rebuildSubtitleClips',
  'addTrack', 'removeTrack', 'setTrackFlags', 'moveTrack',
  'setTransition', 'removeTransition', 'setClipEffects', 'setDocumentMeta',
  'addMarker', 'removeMarker', 'rippleRemoveClip', 'closeGaps',
  'replaceSource', 'unlinkClip', 'setSubtitleStyle',
] as const
export type EditorOp = (typeof EDITOR_OPS)[number]

// ---------- 基础校验 ----------

function requireDoc(doc: EditorDocument): void {
  if (!doc || !Array.isArray(doc.tracks) || !Array.isArray(doc.clips)) {
    throw new EditorCommandError('invalid_payload', 'document')
  }
}

function findTrack(doc: EditorDocument, trackId: unknown): EditorTrack {
  const track = doc.tracks.find((t) => t.id === trackId)
  if (!track) throw new EditorCommandError('track_not_found', String(trackId))
  return track
}

function findClip(doc: EditorDocument, clipId: unknown): { clip: EditorClip; index: number } {
  const index = doc.clips.findIndex((c) => c.id === clipId)
  if (index < 0) throw new EditorCommandError('clip_not_found', String(clipId))
  return { clip: doc.clips[index], index }
}

function ensureUnlocked(track: EditorTrack): void {
  if (track.flags.locked) throw new EditorCommandError('track_locked', track.id)
}

function requirePositive(v: unknown, name: string): number {
  if (typeof v !== 'number' || !Number.isFinite(v) || v <= 0) {
    throw new EditorCommandError('invalid_payload', name)
  }
  return v
}

function requireNonNegative(v: unknown, name: string): number {
  if (typeof v !== 'number' || !Number.isFinite(v) || v < 0) {
    throw new EditorCommandError('invalid_payload', name)
  }
  return v
}

/** 字幕逐 cue 样式增量校验：内键 color/size/position，null 删除该键（合并语义见 setClipProperty） */
function normalizeStyleDelta(delta: unknown): Record<string, unknown> {
  if (typeof delta !== 'object' || delta === null || Array.isArray(delta)) {
    throw new EditorCommandError('invalid_payload', 'style')
  }
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(delta)) {
    if (value === null) {
      out[key] = null
      continue
    }
    if (key === 'color') {
      if (typeof value !== 'string' || !/^#[0-9a-fA-F]{6}$/.test(value)) {
        throw new EditorCommandError('invalid_payload', 'style.color')
      }
    } else if (key === 'size') {
      if (typeof value !== 'number' || !Number.isInteger(value) || value < 8 || value > 200) {
        throw new EditorCommandError('invalid_payload', 'style.size')
      }
    } else if (key === 'font') {
      // 字体名清洗：剥掉会破坏 ASS override 块/名字边界的字符，trim 后须非空
      const cleaned = typeof value === 'string' ? value.replace(/[{}\\]/g, '').trim() : ''
      if (!cleaned || value.length > 64) {
        throw new EditorCommandError('invalid_payload', 'style.font')
      }
      out[key] = cleaned
      continue // 已写入清洗值，跳过末尾原样落盘
    } else if (key === 'position') {
      if (value !== 'bottom' && value !== 'center' && value !== 'top') {
        throw new EditorCommandError('invalid_payload', 'style.position')
      }
    } else {
      throw new EditorCommandError('invalid_payload', `unknown style key: ${key}`)
    }
    out[key] = value
  }
  return out
}

/** 音量包络点数组校验：[{t:0~1, v:0~2}] ≤16 点、t 升序去重 */
function normalizeVolumePoints(value: unknown): Array<{ t: number; v: number }> {
  if (!Array.isArray(value)) {
    throw new EditorCommandError('invalid_payload', 'volumePoints')
  }
  if (value.length > 16) {
    throw new EditorCommandError('invalid_payload', 'volumePoints.length')
  }
  const out: Array<{ t: number; v: number }> = value.map((raw) => {
    const p = raw as Record<string, unknown>
    if (typeof p?.t !== 'number' || !Number.isFinite(p.t) || p.t < 0 || p.t > 1
      || typeof p?.v !== 'number' || !Number.isFinite(p.v) || p.v < 0 || p.v > 2) {
      throw new EditorCommandError('invalid_payload', 'volumePoints[]')
    }
    return { t: Math.round(p.t * 1000) / 1000, v: Math.round(p.v * 100) / 100 }
  })
  for (let i = 1; i < out.length; i++) {
    if (out[i]!.t <= out[i - 1]!.t) {
      throw new EditorCommandError('invalid_payload', 'volumePoints.t 升序')
    }
  }
  return out
}

/** 校验并规范 setClipProperty 的 props 增量（浅合并语义，null 删除键） */
function normalizePropsDelta(delta: unknown): Partial<Record<keyof ClipProps, unknown>> {
  if (typeof delta !== 'object' || delta === null || Array.isArray(delta)) {
    throw new EditorCommandError('invalid_payload', 'props')
  }
  const out: Partial<Record<keyof ClipProps, unknown>> = {}
  for (const [key, value] of Object.entries(delta)) {
    if (value === null) {
      out[key as keyof ClipProps] = null
      continue
    }
    if (key === 'speed') requirePositive(value, 'speed')
    else if (key === 'volume') {
      if (typeof value !== 'number' || value < 0 || value > 2) {
        throw new EditorCommandError('invalid_payload', 'volume')
      }
    } else if (key === 'fadeIn' || key === 'fadeOut') requireNonNegative(value, key)
    else if (key === 'muted') {
      if (typeof value !== 'boolean') {
        throw new EditorCommandError('invalid_payload', 'muted')
      }
    } else if (key === 'rect') {
      const r = value as Record<string, unknown>
      if (typeof r !== 'object' || r === null || ['x', 'y', 'w', 'h'].some((k) => {
        const v = r[k]
        return typeof v !== 'number' || !Number.isFinite(v) || v < 0 || v > 1
      })) {
        throw new EditorCommandError('invalid_payload', 'rect')
      }
    } else if (key === 'camera') {
      // 运镜 { type, strength }（预设白名单见 editor-camera-registry）；null 清除由上方通用分支处理
      const c = value as Record<string, unknown>
      if (typeof c !== 'object' || c === null || !isCameraType(c.type)
        || typeof c.strength !== 'number' || !Number.isFinite(c.strength) || c.strength < 0 || c.strength > 1) {
        throw new EditorCommandError('invalid_payload', 'camera')
      }
    } else if (key === 'style') {
      // 字幕逐 cue 样式增量：嵌套合并（normalizeStyleDelta 校验，null 内键删除）
      out[key as keyof ClipProps] = normalizeStyleDelta(value) as unknown as ClipProps[keyof ClipProps]
      continue
    } else if (key === 'volumePoints') {
      if (value === null) {
        out[key as keyof ClipProps] = null
        continue
      }
      out[key as keyof ClipProps] = normalizeVolumePoints(value) as unknown as ClipProps[keyof ClipProps]
      continue
    } else {
      throw new EditorCommandError('invalid_payload', `unknown prop: ${key}`)
    }
    out[key as keyof ClipProps] = value
  }
  return out
}

/** 校验并规范 effects 整组数组（setClipEffects 整组替换语义） */
function normalizeEffects(value: unknown): ClipEffect[] {
  if (!Array.isArray(value)) {
    throw new EditorCommandError('invalid_payload', 'effects')
  }
  return value.map((raw) => {
    const e = raw as Record<string, unknown>
    if (typeof e?.id !== 'string' || !e.id || !isEffectType(e.type)) {
      throw new EditorCommandError('invalid_payload', 'effects[]')
    }
    const strength = e.strength
    if (typeof strength !== 'number' || !Number.isFinite(strength) || strength < 0 || strength > 1) {
      throw new EditorCommandError('invalid_payload', 'effects[].strength')
    }
    return { id: e.id, type: e.type, strength }
  })
}

/** 同轨紧随片段：afterClip 按 start 排序后的下一个（无则无相邻性，转场不成立） */
function nextClipOnTrack(doc: EditorDocument, trackId: string, afterClipId: string): EditorClip | null {
  const clips = doc.clips
    .filter((c) => c.trackId === trackId)
    .sort((a, b) => a.start - b.start || a.id.localeCompare(b.id))
  const idx = clips.findIndex((c) => c.id === afterClipId)
  return idx >= 0 && idx + 1 < clips.length ? clips[idx + 1]! : null
}

/** 不可变更新 tracks 数组中某条轨道 */
function withTrack(doc: EditorDocument, trackId: string, mutate: (t: EditorTrack) => EditorTrack): EditorDocument {
  const track = findTrack(doc, trackId)
  ensureUnlocked(track)
  return { ...doc, tracks: doc.tracks.map((t) => (t.id === trackId ? mutate(t) : t)) }
}

/** 不可变更新 clips 数组中某个片段 */
function withClip(doc: EditorDocument, clipId: string, mutate: (c: EditorClip) => EditorClip): EditorDocument {
  const { clip, index } = findClip(doc, clipId)
  const track = findTrack(doc, clip.trackId)
  ensureUnlocked(track)
  const next = mutate(clip)
  const clips = doc.clips.slice()
  clips[index] = next
  return { ...doc, clips }
}

// ---------- 17 op 实现 ----------

const commands: Record<EditorOp, (doc: EditorDocument, payload: CommandPayload) => EditorDocument> = {
  addClip: (doc, payload) => {
    const clip = payload.clip as EditorClip | undefined
    if (!clip || typeof clip.id !== 'string' || !clip.id) {
      throw new EditorCommandError('invalid_payload', 'clip')
    }
    const track = findTrack(doc, clip.trackId)
    ensureUnlocked(track)
    if (doc.clips.some((c) => c.id === clip.id)) {
      throw new EditorCommandError('duplicate_id', clip.id)
    }
    const normalized: EditorClip = {
      id: clip.id,
      trackId: track.id,
      assetId: typeof clip.assetId === 'number' ? clip.assetId : null,
      start: requireNonNegative(clip.start, 'start'),
      // duration>=0：0 为「送进剪辑器」草稿占位契约（前端 healDurations / 渲染 Plan 剔除 0 片段）
      duration: requireNonNegative(clip.duration, 'duration'),
      trimStart: requireNonNegative(clip.trimStart ?? 0, 'trimStart'),
      props: clip.props ?? {},
      ...(track.kind === 'subtitle' ? { text: typeof clip.text === 'string' ? clip.text : '' } : {}),
    }
    if (needsCollisionCheck(track) && !canPlaceOnTrack(
      doc.clips.filter((c) => c.trackId === track.id),
      { start: normalized.start, duration: normalized.duration },
    )) {
      throw new EditorCommandError('overlap', track.id)
    }
    return { ...doc, clips: [...doc.clips, normalized] }
  },

  moveClip: (doc, payload) => {
    const clipId = payload.clipId
    const start = requireNonNegative(payload.start, 'start')
    return withClip(doc, clipId as string, (clip) => {
      let trackId = clip.trackId
      if (payload.trackId !== undefined && payload.trackId !== clip.trackId) {
        const target = findTrack(doc, payload.trackId)
        ensureUnlocked(target)
        const source = findTrack(doc, clip.trackId)
        if (target.kind !== source.kind) {
          throw new EditorCommandError('invalid_payload', 'cross-kind move')
        }
        trackId = target.id
      }
      const track = findTrack(doc, trackId)
      if (needsCollisionCheck(track) && !canPlaceOnTrack(
        doc.clips.filter((c) => c.trackId === trackId),
        { start, duration: clip.duration, excludeClipId: clip.id },
      )) {
        throw new EditorCommandError('overlap', trackId)
      }
      return { ...clip, trackId, start }
    })
  },

  trimClip: (doc, payload) => {
    return withClip(doc, payload.clipId as string, (clip) => {
      const speed = clip.props.speed ?? 1
      let { start, duration, trimStart } = clip
      if (payload.start !== undefined) start = requireNonNegative(payload.start, 'start')
      if (payload.duration !== undefined) {
        duration = requirePositive(payload.duration, 'duration')
        if (duration < MIN_CLIP_DURATION) duration = MIN_CLIP_DURATION
      }
      if (payload.trimStart !== undefined) trimStart = requireNonNegative(payload.trimStart, 'trimStart')
      const track = findTrack(doc, clip.trackId)
      if (needsCollisionCheck(track) && !canPlaceOnTrack(
        doc.clips.filter((c) => c.trackId === clip.trackId),
        { start, duration, excludeClipId: clip.id },
      )) {
        throw new EditorCommandError('overlap', clip.trackId)
      }
      // duration 与 speed/trimStart 一致性由 UI 层保证；命令层只防负值与碎片化
      void speed
      return { ...clip, start, duration, trimStart }
    })
  },

  splitClip: (doc, payload) => {
    const at = requireNonNegative(payload.at, 'at')
    const newId = payload.newId
    if (typeof newId !== 'string' || !newId) {
      throw new EditorCommandError('invalid_payload', 'newId')
    }
    const { clip } = findClip(doc, payload.clipId)
    const track = findTrack(doc, clip.trackId)
    ensureUnlocked(track)
    if (at <= clip.start || at >= clipEnd(clip)) {
      throw new EditorCommandError('split_outside_clip', String(at))
    }
    if (at - clip.start < MIN_CLIP_DURATION || clipEnd(clip) - at < MIN_CLIP_DURATION) {
      throw new EditorCommandError('split_too_close', String(at))
    }
    if (doc.clips.some((c) => c.id === newId)) {
      throw new EditorCommandError('duplicate_id', newId)
    }
    const speed = clip.props.speed ?? 1
    // 属性拆分（语义 v2：后半段继承属性）——包络点按切分比例重映射；
    // fade 按半段归属拆分：前半丢 fadeOut（尾部已非片段末）、后半丢 fadeIn（头部已非片段首）
    const cutFrac = (at - clip.start) / clip.duration
    const remapPoints = (pts: Array<{ t: number; v: number }>, from: number, to: number) =>
      pts
        .filter((p) => p.t >= from && p.t <= to)
        .map((p) => ({ t: Math.round(((p.t - from) / (to - from)) * 1000) / 1000, v: p.v }))
    const splitProps = (half: 'first' | 'second'): ClipProps => {
      const next: ClipProps = { ...clip.props }
      if (next.volumePoints?.length) {
        const pts = half === 'first'
          ? remapPoints(next.volumePoints, 0, cutFrac)
          : remapPoints(next.volumePoints, cutFrac, 1)
        if (pts.length) next.volumePoints = pts
        else delete next.volumePoints
      }
      delete next[half === 'first' ? 'fadeOut' : 'fadeIn']
      return next
    }
    const second: EditorClip = {
      ...clip,
      id: newId,
      start: at,
      duration: clipEnd(clip) - at,
      // 源内入点按变速换算；属性继承（包络重映射 + fade 拆分）
      trimStart: clip.trimStart + (at - clip.start) * speed,
      props: splitProps('second'),
      ...(track.kind === 'subtitle' ? { text: clip.text ?? '' } : {}),
    }
    const first: EditorClip = { ...clip, duration: at - clip.start, props: splitProps('first') }
    const clips = doc.clips.map((c) => (c.id === clip.id ? first : c))
    return { ...doc, clips: [...clips, second] }
  },

  removeClip: (doc, payload) => {
    findClip(doc, payload.clipId)
    const clipId = payload.clipId as string
    // 衔接点转场清理：指向被删片段的转场一并移除（其余轨的转场保持引用相等）
    const tracks = doc.tracks.map((t) => (
      t.transitions?.some((tr) => tr.afterClipId === clipId)
        ? { ...t, transitions: t.transitions.filter((tr) => tr.afterClipId !== clipId) }
        : t
    ))
    return { ...doc, clips: doc.clips.filter((c) => c.id !== clipId), tracks }
  },

  detachAudio: (doc, payload) => {
    const { clip } = findClip(doc, payload.clipId)
    const sourceTrack = findTrack(doc, clip.trackId)
    if (sourceTrack.kind !== 'video') {
      throw new EditorCommandError('invalid_payload', 'detach requires video clip')
    }
    ensureUnlocked(sourceTrack)
    const newId = payload.newId
    if (typeof newId !== 'string' || !newId) {
      throw new EditorCommandError('invalid_payload', 'newId')
    }
    const targetTrack = findTrack(doc, payload.trackId)
    if (targetTrack.kind !== 'audio') {
      throw new EditorCommandError('not_audio_track', targetTrack.id)
    }
    ensureUnlocked(targetTrack)
    if (doc.clips.some((c) => c.id === newId)) {
      throw new EditorCommandError('duplicate_id', newId)
    }
    if (!canPlaceOnTrack(
      doc.clips.filter((c) => c.trackId === targetTrack.id),
      { start: clip.start, duration: clip.duration },
    )) {
      throw new EditorCommandError('overlap', targetTrack.id)
    }
    // 音画联动组：payload.linkId 可选（UI 层生成传入）；成对写入，组内移动/删除联动
    const linkId = payload.linkId
    if (linkId !== undefined && (typeof linkId !== 'string' || !linkId)) {
      throw new EditorCommandError('invalid_payload', 'linkId')
    }
    const detached: EditorClip = {
      id: newId,
      trackId: targetTrack.id,
      assetId: clip.assetId,
      start: clip.start,
      duration: clip.duration,
      trimStart: clip.trimStart,
      // 变速跟着媒体走（音频同一素材同速率）；音量/fade 从零起调，源片段静音
      props: clip.props.speed !== undefined ? { speed: clip.props.speed } : {},
      ...(typeof linkId === 'string' ? { linkId } : {}),
    }
    const clips = doc.clips.map((c) => (c.id === clip.id
      ? { ...c, props: { ...c.props, muted: true }, ...(typeof linkId === 'string' ? { linkId } : {}) }
      : c))
    return { ...doc, clips: [...clips, detached] }
  },

  setClipProperty: (doc, payload) => {
    const delta = normalizePropsDelta(payload.props)
    return withClip(doc, payload.clipId as string, (clip) => {
      const props: ClipProps = { ...clip.props }
      for (const [key, value] of Object.entries(delta)) {
        if (key === 'style') {
          // 逐 cue 样式嵌套合并：内键 null 删除；合并后为空则整键删除
          const merged: Record<string, unknown> = { ...(props.style as Record<string, unknown> | undefined) }
          for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
            if (v === null) delete merged[k]
            else merged[k] = v
          }
          if (Object.keys(merged).length) props.style = merged as ClipProps['style']
          else delete props.style
          continue
        }
        if (value === null) delete props[key as keyof ClipProps]
        else (props as Record<string, unknown>)[key] = value
      }
      // 变速保持源内跨度不变：duration = 源跨度 / speed（块长随倍率伸缩）。
      // 加速只缩短不会撞车；减速拉长需过同轨碰撞检查（fail-closed overlap）；
      // 加速到碎片化截底 MIN_CLIP_DURATION（此后源跨度随之收窄）
      let duration = clip.duration
      if (typeof delta.speed === 'number') {
        duration = Math.max(
          MIN_CLIP_DURATION,
          Math.round((clip.duration * (clip.props.speed ?? 1) / delta.speed) * 1000) / 1000,
        )
        const track = findTrack(doc, clip.trackId)
        if (duration > clip.duration && needsCollisionCheck(track) && !canPlaceOnTrack(
          doc.clips.filter((c) => c.trackId === clip.trackId),
          { start: clip.start, duration, excludeClipId: clip.id },
        )) {
          throw new EditorCommandError('overlap', clip.trackId)
        }
      }
      return { ...clip, props, duration }
    })
  },

  addSubtitle: (doc, payload) => {
    const clip = payload.clip as EditorClip | undefined
    if (!clip || typeof clip.id !== 'string' || !clip.id) {
      throw new EditorCommandError('invalid_payload', 'clip')
    }
    const track = findTrack(doc, clip.trackId)
    if (track.kind !== 'subtitle') throw new EditorCommandError('not_subtitle_track', track.id)
    ensureUnlocked(track)
    if (typeof clip.text !== 'string' || !clip.text.trim()) {
      throw new EditorCommandError('invalid_payload', 'text')
    }
    return commands.addClip(doc, payload)
  },

  removeSubtitle: (doc, payload) => {
    const { clip } = findClip(doc, payload.clipId)
    const track = findTrack(doc, clip.trackId)
    if (track.kind !== 'subtitle') throw new EditorCommandError('not_subtitle_track', track.id)
    return commands.removeClip(doc, payload)
  },

  rebuildSubtitleClips: (doc, payload) => {
    const trackId = payload.trackId
    const track = findTrack(doc, trackId)
    if (track.kind !== 'subtitle') throw new EditorCommandError('not_subtitle_track', String(trackId))
    ensureUnlocked(track)
    const clips = payload.clips
    if (!Array.isArray(clips)) throw new EditorCommandError('invalid_payload', 'clips')
    const next: EditorClip[] = clips.map((raw) => {
      const c = raw as Record<string, unknown>
      const id = c.id
      if (typeof id !== 'string' || !id) throw new EditorCommandError('invalid_payload', 'clip.id')
      if (typeof c.text !== 'string' || !c.text.trim()) {
        throw new EditorCommandError('invalid_payload', 'clip.text')
      }
      return {
        id,
        trackId: track.id,
        assetId: null,
        start: requireNonNegative(c.start, 'start'),
        duration: requirePositive(c.duration, 'duration'),
        trimStart: 0,
        props: {},
        text: c.text,
      }
    })
    const ids = new Set(next.map((c) => c.id))
    if (ids.size !== next.length) throw new EditorCommandError('duplicate_id', 'rebuild clips')
    return { ...doc, clips: [...doc.clips.filter((c) => c.trackId !== track.id), ...next] }
  },

  addTrack: (doc, payload) => {
    const track = payload.track as EditorTrack | undefined
    if (!track || typeof track.id !== 'string' || !track.id || !isTrackKind(track.kind)) {
      throw new EditorCommandError('invalid_payload', 'track')
    }
    if (doc.tracks.some((t) => t.id === track.id)) {
      throw new EditorCommandError('duplicate_id', track.id)
    }
    const sameKind = doc.tracks.filter((t) => t.kind === track.kind)
    const order = typeof track.order === 'number' ? track.order : sameKind.length
    const next: EditorTrack = { id: track.id, kind: track.kind, order, flags: { ...EMPTY_TRACK_FLAGS } }
    return { ...doc, tracks: [...doc.tracks, next] }
  },

  removeTrack: (doc, payload) => {
    const track = findTrack(doc, payload.trackId)
    if (doc.clips.some((c) => c.trackId === track.id)) {
      throw new EditorCommandError('track_not_empty', track.id)
    }
    return { ...doc, tracks: doc.tracks.filter((t) => t.id !== track.id) }
  },

  /** 轨道开关部分合并：payload.flags 是布尔增量，未提及的键保持原值（多开可并存） */
  setTrackFlags: (doc, payload) => {
    const track = findTrack(doc, payload.trackId)
    const patch = payload.flags
    if (!isTrackFlagsPatch(patch)) {
      throw new EditorCommandError('invalid_payload', 'flags')
    }
    return {
      ...doc,
      tracks: doc.tracks.map((t) => (t.id === track.id ? { ...t, flags: { ...t.flags, ...patch } } : t)),
    }
  },

  /** 同类型轨内重排：toIndex 为「移除被拖轨后」的同类型显示序插入位（0=顶），重编号 order 保持稠密 */
  moveTrack: (doc, payload) => {
    const track = findTrack(doc, payload.trackId)
    const toIndex = payload.toIndex
    if (typeof toIndex !== 'number' || !Number.isInteger(toIndex) || toIndex < 0) {
      throw new EditorCommandError('invalid_payload', 'toIndex')
    }
    const sameKind = doc.tracks
      .filter((t) => t.kind === track.kind)
      .sort((a, b) => b.order - a.order) // 显示序：order 大在上
    const cur = sameKind.findIndex((t) => t.id === track.id)
    const target = Math.min(toIndex, sameKind.length - 1) // 越界钳到末位
    if (target === cur) return doc // 原位放置：结构共享零变更
    const next = sameKind.filter((t) => t.id !== track.id)
    next.splice(target, 0, track)
    const n = next.length
    const orderById = new Map(next.map((t, i) => [t.id, n - 1 - i]))
    // 只替换同类型轨，其他轨保持引用相等（结构共享）
    return { ...doc, tracks: doc.tracks.map((t) => (orderById.has(t.id) ? { ...t, order: orderById.get(t.id)! } : t)) }
  },

  /** 衔接点转场 upsert：同 afterClipId 覆盖；仅视频轨且必须存在同轨紧随片段（fail-closed） */
  setTransition: (doc, payload) => {
    const trackId = payload.trackId as string
    const afterClipId = payload.afterClipId as string
    const track = findTrack(doc, trackId)
    if (track.kind !== 'video') {
      throw new EditorCommandError('invalid_payload', 'transition requires video track')
    }
    const afterClip = doc.clips.find((c) => c.id === afterClipId && c.trackId === trackId)
    if (!afterClip) {
      throw new EditorCommandError('clip_not_found', String(afterClipId))
    }
    if (!nextClipOnTrack(doc, trackId, afterClipId)) {
      throw new EditorCommandError('invalid_payload', 'transition requires a following clip')
    }
    if (!isTransitionType(payload.type)) {
      throw new EditorCommandError('invalid_payload', 'transition.type')
    }
    const duration = requirePositive(payload.duration, 'transition.duration')
    const transition = { id: payload.transitionId as string, afterClipId, type: payload.type, duration }
    if (typeof transition.id !== 'string' || !transition.id) {
      throw new EditorCommandError('invalid_payload', 'transitionId')
    }
    return withTrack(doc, trackId, (t) => {
      const transitions = (t.transitions ?? []).filter((tr) => tr.afterClipId !== afterClipId)
      return { ...t, transitions: [...transitions, transition] }
    })
  },

  /** 删除衔接点转场（按 afterClipId 定位；不存在报错 fail-closed） */
  removeTransition: (doc, payload) => {
    const trackId = payload.trackId as string
    const afterClipId = payload.afterClipId as string
    const track = findTrack(doc, trackId)
    if (!track.transitions?.some((tr) => tr.afterClipId === afterClipId)) {
      throw new EditorCommandError('invalid_payload', `no transition after ${afterClipId}`)
    }
    return withTrack(doc, trackId, (t) => ({ ...t, transitions: t.transitions!.filter((tr) => tr.afterClipId !== afterClipId) }))
  },

  /** 效果器整组替换：空数组删除 effects 键（文档保持精简） */
  setClipEffects: (doc, payload) => {
    const effects = normalizeEffects(payload.effects)
    return withClip(doc, payload.clipId as string, (clip) => {
      const props: ClipProps = { ...clip.props }
      if (effects.length === 0) delete props.effects
      else props.effects = effects
      return { ...clip, props }
    })
  },

  /** 工程级元数据（画布/帧率）：与渲染契约同域（后端骨架校验 16~7680、帧率四档白名单）；
   *  全缺省零变更原样返回（结构共享）。宽度变更时字幕字号按比例缩放保持视觉占比。 */
  setDocumentMeta: (doc, payload) => {
    const { width, height, timebase } = payload
    if (width === undefined && height === undefined && timebase === undefined) return doc
    let nextWidth = doc.width
    let nextHeight = doc.height
    if (width !== undefined) {
      if (typeof width !== 'number' || !Number.isInteger(width) || width % 2 || width < 16 || width > 7680) {
        throw new EditorCommandError('invalid_payload', 'width')
      }
      nextWidth = width
    }
    if (height !== undefined) {
      if (typeof height !== 'number' || !Number.isInteger(height) || height % 2 || height < 16 || height > 7680) {
        throw new EditorCommandError('invalid_payload', 'height')
      }
      nextHeight = height
    }
    if (timebase !== undefined && timebase !== 24 && timebase !== 25 && timebase !== 30 && timebase !== 60) {
      throw new EditorCommandError('invalid_payload', 'timebase')
    }
    let subtitleStyle = doc.subtitleStyle
    if (nextWidth !== doc.width && subtitleStyle) {
      subtitleStyle = { ...subtitleStyle, size: Math.max(12, Math.round(subtitleStyle.size * nextWidth / doc.width)) }
    }
    return {
      ...doc,
      width: nextWidth,
      height: nextHeight,
      ...(timebase !== undefined ? { timebase: timebase as number } : {}),
      ...(subtitleStyle !== doc.subtitleStyle ? { subtitleStyle } : {}),
    }
  },

  /** 时间线标记 upsert（id 相同覆盖）；time 非负 */
  addMarker: (doc, payload) => {
    const marker = payload.marker as { id?: unknown; time?: unknown; label?: unknown } | undefined
    if (!marker || typeof marker.id !== 'string' || !marker.id
      || typeof marker.time !== 'number' || !Number.isFinite(marker.time) || marker.time < 0) {
      throw new EditorCommandError('invalid_payload', 'marker')
    }
    if (marker.label !== undefined && typeof marker.label !== 'string') {
      throw new EditorCommandError('invalid_payload', 'marker.label')
    }
    const markerOut = { id: marker.id, time: Math.round(marker.time * 1000) / 1000, ...(typeof marker.label === 'string' && marker.label ? { label: marker.label } : {}) }
    const rest = (doc.markers ?? []).filter((m) => m.id !== marker.id)
    return { ...doc, markers: [...rest, markerOut].sort((a, b) => a.time - b.time) }
  },

  removeMarker: (doc, payload) => {
    const id = payload.markerId
    if (typeof id !== 'string' || !id) throw new EditorCommandError('invalid_payload', 'markerId')
    if (!(doc.markers ?? []).some((m) => m.id === id)) {
      throw new EditorCommandError('invalid_payload', `no marker ${id}`)
    }
    return { ...doc, markers: (doc.markers ?? []).filter((m) => m.id !== id) }
  },

  /** 波纹删除：删片段并把同轨其后片段整体左移补位（跨轨不受影响；转场清理同 removeClip） */
  rippleRemoveClip: (doc, payload) => {
    const { clip } = findClip(doc, payload.clipId)
    const track = findTrack(doc, clip.trackId)
    if (track.kind === 'subtitle') {
      throw new EditorCommandError('invalid_payload', 'ripple requires media track')
    }
    const removedEnd = clipEnd(clip)
    const tracks = doc.tracks.map((t) => (
      t.transitions?.some((tr) => tr.afterClipId === clip.id)
        ? { ...t, transitions: t.transitions.filter((tr) => tr.afterClipId !== clip.id) }
        : t
    ))
    return {
      ...doc,
      tracks,
      clips: doc.clips
        .filter((c) => c.id !== clip.id)
        .map((c) => (
          c.trackId === track.id && c.start >= removedEnd - 1e-6
            ? { ...c, start: Math.max(0, Math.round((c.start - clip.duration) * 1000) / 1000) }
            : c
        )),
    }
  },

  /** 闭合同轨空隙：该轨片段按序收紧（从 0 起光标铺满），字幕轨豁免（cue 可共存） */
  closeGaps: (doc, payload) => {
    const track = findTrack(doc, payload.trackId)
    if (track.kind === 'subtitle') {
      throw new EditorCommandError('invalid_payload', 'closeGaps requires media track')
    }
    const ordered = doc.clips
      .filter((c) => c.trackId === track.id)
      .sort((a, b) => a.start - b.start || a.id.localeCompare(b.id))
    let cursor = 0
    const offset = new Map<string, number>()
    for (const c of ordered) {
      offset.set(c.id, Math.round((cursor - c.start) * 1000) / 1000)
      cursor += c.duration
    }
    return { ...doc, clips: doc.clips.map((c) => (offset.has(c.id) ? { ...c, start: Math.max(0, Math.round((c.start + offset.get(c.id)!) * 1000) / 1000) } : c)) }
  },

  /** 换源：保留 start/duration/trimStart/props 只换素材文件（类型匹配由调用方保证，与 addClip 同约定）；
   *  start/duration/trimStart 可选覆盖（UI 层对新素材探测后钳制传入）；linkId 保留（音画组不变） */
  replaceSource: (doc, payload) => {
    const assetId = payload.assetId
    if (typeof assetId !== 'number' || !Number.isInteger(assetId)) {
      throw new EditorCommandError('invalid_payload', 'assetId')
    }
    // 同素材且无覆盖：结构共享零变更（在 withClip 之外短路，否则新建 clips 数组破坏引用相等）
    const target = doc.clips.find((c) => c.id === payload.clipId)
    if (target && target.assetId === assetId
      && payload.start === undefined && payload.duration === undefined && payload.trimStart === undefined) {
      return doc
    }
    return withClip(doc, payload.clipId as string, (clip) => {
      const start = payload.start !== undefined ? requireNonNegative(payload.start, 'start') : clip.start
      let duration = payload.duration !== undefined ? requirePositive(payload.duration, 'duration') : clip.duration
      if (duration < MIN_CLIP_DURATION) duration = MIN_CLIP_DURATION
      const trimStart = payload.trimStart !== undefined ? requireNonNegative(payload.trimStart, 'trimStart') : clip.trimStart
      return { ...clip, assetId, start: Math.round(start * 1000) / 1000, duration: Math.round(duration * 1000) / 1000, trimStart: Math.round(trimStart * 1000) / 1000 }
    })
  },

  /** 解除音画联动：清 linkId（组成员各自调用；同组其他片段保持） */
  unlinkClip: (doc, payload) => {
    return withClip(doc, payload.clipId as string, (clip) => {
      if (!clip.linkId) return clip
      const next = { ...clip }
      delete next.linkId
      return next
    })
  },

  /** 工程级字幕样式整体替换（字段与 SubtitleStyle 契约一致；形状校验 fail-closed） */
  setSubtitleStyle: (doc, payload) => {
    const style = payload.style as Record<string, unknown> | null
    if (typeof style !== 'object' || style === null || Array.isArray(style)) {
      throw new EditorCommandError('invalid_payload', 'style')
    }
    const font = style.font
    const size = style.size
    const color = style.color
    const outline = style.outline
    const position = style.position
    if (typeof font !== 'string' || !font.trim() || font.length > 64) {
      throw new EditorCommandError('invalid_payload', 'style.font')
    }
    if (typeof size !== 'number' || !Number.isInteger(size) || size < 8 || size > 200) {
      throw new EditorCommandError('invalid_payload', 'style.size')
    }
    if (typeof color !== 'string' || !/^#[0-9a-fA-F]{6}$/.test(color)) {
      throw new EditorCommandError('invalid_payload', 'style.color')
    }
    if (typeof outline !== 'boolean') {
      throw new EditorCommandError('invalid_payload', 'style.outline')
    }
    if (position !== 'bottom' && position !== 'center' && position !== 'top') {
      throw new EditorCommandError('invalid_payload', 'style.position')
    }
    return { ...doc, subtitleStyle: { font: font.trim(), size, color, outline, position } }
  },
}

/** 命令统一入口：未知 op 抛错（fail-closed） */
export function applyCommand(doc: EditorDocument, command: EditorCommand): EditorDocument {
  requireDoc(doc)
  const handler = commands[command.op]
  if (!handler) throw new EditorCommandError('unknown_op', String((command as { op?: unknown }).op))
  return handler(doc, command.payload ?? {})
}

/** 便捷构造 */
export function cmd(op: EditorOp, payload: CommandPayload): EditorCommand {
  return { op, payload }
}
