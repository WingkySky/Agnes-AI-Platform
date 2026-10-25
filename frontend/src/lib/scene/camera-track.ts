/* =====================================================
 * 相机关键帧插值（纯函数）
 * 语义：keyframes 按时间升序；第 i 帧的 easing 描述「从第 i-1 帧到第 i 帧」
 * 的过渡（linear 线性 / smooth 缓入缓出 / cut 先保持上一帧姿态到本帧时刻再切）。
 * ===================================================== */

import type { CameraKeyframe, ShotData, Vec3 } from '@/types/scene'

export interface CameraPose {
  position: Vec3
  target: Vec3
  fov: number
}

function lerp(a: number, b: number, p: number): number {
  return a + (b - a) * p
}

function lerpVec3(a: Vec3, b: Vec3, p: number): Vec3 {
  return { x: lerp(a.x, b.x, p), y: lerp(a.y, b.y, p), z: lerp(a.z, b.z, p) }
}

function ease(kind: CameraKeyframe['easing'], p: number): number {
  if (kind === 'smooth') return p * p * (3 - 2 * p)
  return p
}

/** 采样镜头在 t 秒的相机姿态（t 越界取首/末帧；空关键帧返回 null） */
export function sampleCameraTrack(keyframes: CameraKeyframe[], t: number): CameraPose | null {
  if (!keyframes.length) return null
  const frames = [...keyframes].sort((a, b) => a.time - b.time)
  if (t <= frames[0].time) return poseOf(frames[0])
  const last = frames[frames.length - 1]
  if (t >= last.time) return poseOf(last)
  // 找到覆盖 t 的段 [prev, cur]
  for (let i = 1; i < frames.length; i++) {
    const prev = frames[i - 1]
    const cur = frames[i]
    if (t <= cur.time) {
      // cur.easing 描述从 prev 到 cur 的过渡；cut = 保持 prev 姿态到 cur 时刻
      if (cur.easing === 'cut') return poseOf(prev)
      const p = ease(cur.easing, (t - prev.time) / (cur.time - prev.time || 1))
      return {
        position: lerpVec3(prev.position, cur.position, p),
        target: lerpVec3(prev.target, cur.target, p),
        fov: lerp(prev.fov, cur.fov, p),
      }
    }
  }
  return poseOf(last)
}

function poseOf(k: CameraKeyframe): CameraPose {
  return { position: { ...k.position }, target: { ...k.target }, fov: k.fov }
}

/** 序列总时长（秒） */
export function shotsTotalDuration(shots: ShotData[]): number {
  return shots.reduce((sum, s) => sum + (s.duration || 0), 0)
}
