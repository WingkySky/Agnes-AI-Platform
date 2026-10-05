/* =====================================================
 * 剪辑器命令状态机 — 12 op 纯函数命令表
 *
 * - 每个命令 (doc, payload) => 新 doc，不可变更新（未变子树结构共享）
 * - fail-closed：未知 op / 非法 payload 抛 EditorCommandError，不改状态（可安全回放）
 * - 碰撞拒绝：video/audio 轨禁止重叠（lib/editor-placement 半开区间判定，贴边不冲突）；
 *   字幕轨 cue 可共存豁免
 * - 命令可序列化 {op, payload}；持久化的只有 document 快照，命令表回放仅用于测试
 * - 文案不在此层：错误码由组件层 i18n 转译
 * ===================================================== */

import {
  type ClipProps,
  type EditorClip,
  type EditorDocument,
  type EditorTrack,
  type TrackFlag,
  MIN_CLIP_DURATION,
  clipEnd,
  isTransitionType,
  isTrackFlag,
  isTrackKind,
} from './editor-types'
import { canPlaceOnTrack, needsCollisionCheck } from './editor-placement'

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
  'addClip', 'moveClip', 'trimClip', 'splitClip', 'removeClip', 'setClipProperty',
  'addSubtitle', 'removeSubtitle', 'rebuildSubtitleClips',
  'addTrack', 'removeTrack', 'setTrackFlag',
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
  if (track.flag === 'locked') throw new EditorCommandError('track_locked', track.id)
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
    else if (key === 'transition') {
      if (typeof value !== 'object' || value === null || !isTransitionType((value as Record<string, unknown>).type)) {
        throw new EditorCommandError('invalid_payload', 'transition.type')
      }
      requirePositive((value as Record<string, unknown>).duration, 'transition.duration')
    } else if (key === 'rect') {
      const r = value as Record<string, unknown>
      if (typeof r !== 'object' || r === null || ['x', 'y', 'w', 'h'].some((k) => {
        const v = r[k]
        return typeof v !== 'number' || !Number.isFinite(v) || v < 0 || v > 1
      })) {
        throw new EditorCommandError('invalid_payload', 'rect')
      }
    } else {
      throw new EditorCommandError('invalid_payload', `unknown prop: ${key}`)
    }
    out[key as keyof ClipProps] = value
  }
  return out
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

// ---------- 12 op 实现 ----------

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
    const second: EditorClip = {
      ...clip,
      id: newId,
      start: at,
      duration: clipEnd(clip) - at,
      // 源内入点按变速换算；属性留前半段，后半段取默认（设计档 splitClip 语义）
      trimStart: clip.trimStart + (at - clip.start) * speed,
      props: {},
      ...(track.kind === 'subtitle' ? { text: clip.text ?? '' } : {}),
    }
    const first: EditorClip = { ...clip, duration: at - clip.start }
    const clips = doc.clips.map((c) => (c.id === clip.id ? first : c))
    return { ...doc, clips: [...clips, second] }
  },

  removeClip: (doc, payload) => {
    findClip(doc, payload.clipId)
    return { ...doc, clips: doc.clips.filter((c) => c.id !== payload.clipId) }
  },

  setClipProperty: (doc, payload) => {
    const delta = normalizePropsDelta(payload.props)
    return withClip(doc, payload.clipId as string, (clip) => {
      const props: ClipProps = { ...clip.props }
      for (const [key, value] of Object.entries(delta)) {
        if (value === null) delete props[key as keyof ClipProps]
        else (props as Record<string, unknown>)[key] = value
      }
      return { ...clip, props }
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
    const next: EditorTrack = { id: track.id, kind: track.kind, order, flag: null }
    return { ...doc, tracks: [...doc.tracks, next] }
  },

  removeTrack: (doc, payload) => {
    const track = findTrack(doc, payload.trackId)
    if (doc.clips.some((c) => c.trackId === track.id)) {
      throw new EditorCommandError('track_not_empty', track.id)
    }
    return { ...doc, tracks: doc.tracks.filter((t) => t.id !== track.id) }
  },

  setTrackFlag: (doc, payload) => {
    findTrack(doc, payload.trackId)
    const flag = payload.flag
    if (flag !== null && !isTrackFlag(flag)) {
      throw new EditorCommandError('invalid_payload', 'flag')
    }
    return {
      ...doc,
      tracks: doc.tracks.map((t) => (t.id === payload.trackId ? { ...t, flag: flag as TrackFlag | null } : t)),
    }
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
