/* =====================================================
 * 剪辑器类型定义 + 轻量运行时校验
 * - document 是时间线唯一事实源（前端权威，后端只做骨架校验）
 * - clips 扁平数组（命令按 clipId 操作，结构共享撤销依赖不可变更新）
 * ===================================================== */

export type TrackKind = 'video' | 'audio' | 'subtitle'

/** 轨道开关键：hidden 画面不渲染 / locked 禁编辑 / muted 不出声 / solo 预览监听独奏 */
export type TrackFlagKey = 'hidden' | 'locked' | 'muted' | 'solo'
export type TrackFlags = Record<TrackFlagKey, boolean>

export const TRACK_FLAG_KEYS: TrackFlagKey[] = ['hidden', 'locked', 'muted', 'solo']

export const EMPTY_TRACK_FLAGS: TrackFlags = { hidden: false, locked: false, muted: false, solo: false }

/** 轨道；order 大=上层（多视频轨 PIP 依据） */
export interface EditorTrack {
  id: string
  kind: TrackKind
  order: number
  flags: TrackFlags
  /** 轨级衔接点转场：afterClipId 与其同轨紧随片段之间的过渡（仅视频轨全帧链生效） */
  transitions?: TrackTransition[]
}

export type TransitionType = 'crossfade' | 'fade' | 'wipe'

/** 轨级衔接点转场实体：挂在「前一片段」上，作用于它与紧随片段的交界 */
export interface TrackTransition {
  id: string
  afterClipId: string
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

/** 视觉效果器（video/image 片段可挂多种；渲染端 lowering 为 ffmpeg 滤镜，预览端 canvas filter） */
export type EffectType = 'grayscale' | 'blur'

export function isEffectType(v: unknown): v is EffectType {
  return v === 'grayscale' || v === 'blur'
}

export interface ClipEffect {
  id: string
  type: EffectType
  /** 0~1：blur→gblur sigma（×20）；grayscale 恒定黑白（strength 留作灰度混合） */
  strength: number
}

export interface ClipProps {
  speed?: number
  volume?: number
  fadeIn?: number
  fadeOut?: number
  rect?: ClipRect
  effects?: ClipEffect[]
  /** 音画分离后源片段静音：自带音频不再进预览与渲染 */
  muted?: boolean
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

/** 片段最短时长（秒），trim 下限 */
export const MIN_CLIP_DURATION = 0.1

export function isTrackKind(v: unknown): v is TrackKind {
  return v === 'video' || v === 'audio' || v === 'subtitle'
}

/** 校验轨道开关补丁：键限定四开、值必须布尔（setTrackFlags payload 用） */
export function isTrackFlagsPatch(v: unknown): v is Partial<TrackFlags> {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) return false
  return Object.entries(v).every(([k, val]) => TRACK_FLAG_KEYS.includes(k as TrackFlagKey) && typeof val === 'boolean')
}

export function isTransitionType(v: unknown): v is TransitionType {
  return v === 'crossfade' || v === 'fade' || v === 'wipe'
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
