/* =====================================================
 * 剪辑器类型定义 + 轻量运行时校验
 * - document 是时间线唯一事实源（前端权威，后端只做骨架校验）
 * - clips 扁平数组（命令按 clipId 操作，结构共享撤销依赖不可变更新）
 * ===================================================== */

export type TrackKind = 'video' | 'audio' | 'subtitle'
export type TrackFlag = 'hidden' | 'locked' | 'muted'

/** 轨道；order 大=上层（多视频轨 PIP 依据） */
export interface EditorTrack {
  id: string
  kind: TrackKind
  order: number
  flag: TrackFlag | null
}

export type TransitionType = 'crossfade' | 'fade' | 'wipe'

export interface ClipTransition {
  type: TransitionType
  duration: number
}

/** 片段在画幅中的位置尺寸（归一化 0~1，默认全帧；上层轨缩小即 PIP） */
export interface ClipRect {
  x: number
  y: number
  w: number
  h: number
}

export interface ClipProps {
  speed?: number
  volume?: number
  fadeIn?: number
  fadeOut?: number
  rect?: ClipRect
  transition?: ClipTransition
}

export interface EditorClip {
  id: string
  trackId: string
  assetId: number | null
  /** 时间线位置（秒） */
  start: number
  /** 时间线占用（秒，变速后 = 源时长 / speed） */
  duration: number
  /** 源内入点（秒） */
  trimStart: number
  props: ClipProps
  /** 字幕片段文本（仅 subtitle 轨） */
  text?: string
}

export interface SubtitleStyle {
  font: string
  size: number
  color: string
  outline: boolean
  position: 'bottom' | 'center' | 'top'
}

export interface EditorDocument {
  timebase: number
  width: number
  height: number
  tracks: EditorTrack[]
  clips: EditorClip[]
  subtitleStyle?: SubtitleStyle
}

export const TRANSITION_TYPES: TransitionType[] = ['crossfade', 'fade', 'wipe']

/** 片段最短时长（秒），trim 下限 */
export const MIN_CLIP_DURATION = 0.1

export function isTrackKind(v: unknown): v is TrackKind {
  return v === 'video' || v === 'audio' || v === 'subtitle'
}

export function isTrackFlag(v: unknown): v is TrackFlag {
  return v === 'hidden' || v === 'locked' || v === 'muted'
}

export function isTransitionType(v: unknown): v is TransitionType {
  return TRANSITION_TYPES.includes(v as TransitionType)
}

function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

/** 片段在时间线上的结束位置 */
export function clipEnd(clip: EditorClip): number {
  return clip.start + clip.duration
}

/** 变速下的源内跨度（秒）：duration = 源跨度 / speed */
export function sourceSpan(clip: EditorClip): number {
  return clip.duration * (clip.props.speed ?? 1)
}

/** 默认全帧 rect */
export const FULL_RECT: ClipRect = { x: 0, y: 0, w: 1, h: 1 }
