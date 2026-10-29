/* =====================================================
 * 运镜/走位路径（b3）：形状生成 + 沿径采样机位关键帧（纯函数）
 * 路径 = 世界坐标点串；采样沿折线按弧长均匀取点，
 * 产物是普通 CameraKeyframe[]，预演/派生直接复用关键帧链路。
 * ===================================================== */

import type { CameraKeyframe, MotionPath, PathShape, Vec3 } from '@/types/scene'

/** 按形状生成默认路径：围绕 center（通常是相机注视点），y 为路径高度 */
export function makePath(shape: PathShape, center: Vec3, opts?: { height?: number }): MotionPath {
  const y = opts?.height ?? 1.6
  switch (shape) {
    case 'line':
      return { shape, facePath: true, points: [
        { x: center.x - 4, y, z: center.z + 3 },
        { x: center.x + 4, y, z: center.z - 3 },
      ] }
    case 'ring': {
      // 环绕：半径 5 的 12 边形（facePath=false → 恒对准中心）
      const points: Vec3[] = []
      const r = 5
      for (let i = 0; i < 12; i++) {
        const a = (i / 12) * Math.PI * 2
        points.push({ x: center.x + Math.cos(a) * r, y, z: center.z + Math.sin(a) * r })
      }
      return { shape, facePath: false, points }
    }
    case 'rectangle':
      return { shape, facePath: true, points: [
        { x: center.x - 4, y, z: center.z - 3 },
        { x: center.x + 4, y, z: center.z - 3 },
        { x: center.x + 4, y, z: center.z + 3 },
        { x: center.x - 4, y, z: center.z + 3 },
        { x: center.x - 4, y, z: center.z - 3 },
      ] }
    case 'pencil':
    default:
      return { shape: 'pencil', facePath: true, points: [] }
  }
}

/** 折线总长 */
export function pathLength(points: Vec3[]): number {
  let len = 0
  for (let i = 1; i < points.length; i++) {
    len += dist(points[i - 1], points[i])
  }
  return len
}

function dist(a: Vec3, b: Vec3): number {
  return Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)
}

/** 沿折线按弧长比例取点（t∈[0,1]；空路径返回 null） */
export function pointAt(points: Vec3[], t: number): Vec3 | null {
  if (!points.length) return null
  if (points.length === 1 || t <= 0) return { ...points[0] }
  if (t >= 1) return { ...points[points.length - 1] }
  const total = pathLength(points)
  if (total <= 0) return { ...points[0] }
  let target = total * t
  for (let i = 1; i < points.length; i++) {
    const seg = dist(points[i - 1], points[i])
    if (target <= seg) {
      const p = seg > 0 ? target / seg : 0
      return {
        x: points[i - 1].x + (points[i].x - points[i - 1].x) * p,
        y: points[i - 1].y + (points[i].y - points[i - 1].y) * p,
        z: points[i - 1].z + (points[i].z - points[i - 1].z) * p,
      }
    }
    target -= seg
  }
  return { ...points[points.length - 1] }
}

export interface SamplePathOpts {
  duration: number
  fov: number
  /** facePath=false 时的恒定注视点 */
  lookTarget: Vec3
}

/**
 * 沿路径采样机位关键帧（含首尾，times 均分 duration）。
 * facePath=true → target=行进方向前方 2m 处（水平投影）；
 * false → target 恒为 lookTarget（环绕机位语义）。
 */
export function samplePathFrames(path: MotionPath, sampleCount: number, opts: SamplePathOpts): CameraKeyframe[] {
  const n = Math.max(2, Math.min(24, Math.round(sampleCount)))
  const frames: CameraKeyframe[] = []
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1)
    const pos = pointAt(path.points, t) ?? { x: 0, y: opts.lookTarget.y + 1.6, z: 5 }
    let target: Vec3
    if (path.facePath) {
      const ahead = pointAt(path.points, Math.min(1, t + 0.12))
      if (ahead && dist(ahead, pos) > 0.3) {
        target = { x: ahead.x, y: pos.y, z: ahead.z }
      } else {
        const back = pointAt(path.points, Math.max(0, t - 0.12))
        target = back && dist(back, pos) > 0.3
          ? { x: pos.x * 2 - back.x, y: pos.y, z: pos.z * 2 - back.z }
          : { ...opts.lookTarget }
      }
    } else {
      target = { ...opts.lookTarget }
    }
    frames.push({
      time: Math.round(t * opts.duration * 10) / 10,
      position: { x: round2(pos.x), y: round2(pos.y), z: round2(pos.z) },
      target: { x: round2(target.x), y: round2(target.y), z: round2(target.z) },
      fov: opts.fov,
      easing: 'smooth',
    })
  }
  return frames
}

function round2(n: number): number {
  return Math.round(n * 100) / 100
}
