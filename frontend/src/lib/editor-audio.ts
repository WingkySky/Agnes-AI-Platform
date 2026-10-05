/* =====================================================
 * 预览音频增益（纯函数）
 * - gain = volume × fade 包络；fade 窗口以时间线时间计（与渲染 Plan 的
 *   afade 语义一致：转场/淡变都在变速之后的时间线域）
 * - 变速不影响包络：speed 只作用于媒体内位置（trimStart 换算），不缩放 fade
 * - 组件层每帧用 setTargetAtTime 把返回值写入 GainNode（10ms 平滑，无爆音）
 * ===================================================== */

import { clipEnd, type EditorClip } from './editor-types'

/** 片段在时间线时刻 now 的瞬时增益（未钳制，volume 允许 0~2 提升量） */
export function clipGainAt(clip: EditorClip, now: number): number {
  const volume = clip.props.volume ?? 1
  const { fadeIn = 0, fadeOut = 0 } = clip.props
  let factor = 1
  if (fadeIn > 0) factor *= Math.min(1, Math.max(0, (now - clip.start) / fadeIn))
  const end = clipEnd(clip)
  if (fadeOut > 0) factor *= Math.min(1, Math.max(0, (end - now) / fadeOut))
  return volume * factor
}
