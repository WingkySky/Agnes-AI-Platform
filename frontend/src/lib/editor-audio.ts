/* =====================================================
 * 预览音频增益 / 画面淡变包络（纯函数）
 * - gain = volume × fade 包络；fade 窗口以时间线时间计（与渲染 Plan 的
 *   afade 语义一致：转场/淡变都在变速之后的时间线域）
 * - 变速不影响包络：speed 只作用于媒体内位置（trimStart 换算），不缩放 fade
 * - 组件层每帧用 setTargetAtTime 把增益写进 GainNode（10ms 平滑，无爆音）
 * - 画面淡变透明度（clipFadeAlphaAt）与增益同包络但不含 volume，供预览
 *   画布 globalAlpha 与渲染端 fade 滤镜（全帧变黑 / PIP alpha）对齐
 * ===================================================== */

import { clipEnd, type EditorClip } from './editor-types'

/** 片段在时间线时刻 now 的画面淡变透明度（0~1，仅 fade 包络） */
export function clipFadeAlphaAt(clip: EditorClip, now: number): number {
  const { fadeIn = 0, fadeOut = 0 } = clip.props
  let factor = 1
  if (fadeIn > 0) factor *= Math.min(1, Math.max(0, (now - clip.start) / fadeIn))
  const end = clipEnd(clip)
  if (fadeOut > 0) factor *= Math.min(1, Math.max(0, (end - now) / fadeOut))
  return factor
}

/** 片段在时间线时刻 now 的瞬时增益（未钳制，volume 允许 0~2 提升量） */
export function clipGainAt(clip: EditorClip, now: number): number {
  return (clip.props.volume ?? 1) * clipFadeAlphaAt(clip, now)
}
