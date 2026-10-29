// 运镜/走位路径纯函数测试（b3）
import { describe, expect, it } from 'vitest'

import { makePath, pathLength, pointAt, samplePathFrames } from '../path'

const v = (x: number, y: number, z: number) => ({ x, y, z })

describe('makePath', () => {
  it('线=2 点、矩形=闭合 5 点、环绕=12 点且 facePath=false', () => {
    const c = v(0, 0, 0)
    expect(makePath('line', c).points).toHaveLength(2)
    expect(makePath('line', c).facePath).toBe(true)
    const rect = makePath('rectangle', c)
    expect(rect.points).toHaveLength(5)
    expect(rect.points[0]).toEqual(rect.points[4])
    const ring = makePath('ring', c)
    expect(ring.points).toHaveLength(12)
    expect(ring.facePath).toBe(false)
  })

  it('铅笔=空点串（等绘制）', () => {
    expect(makePath('pencil', v(0, 0, 0)).points).toEqual([])
  })
})

describe('pointAt / pathLength', () => {
  const line = [v(0, 1.6, 0), v(10, 1.6, 0)]

  it('按弧长比例取点', () => {
    expect(pathLength(line)).toBe(10)
    expect(pointAt(line, 0)).toEqual(v(0, 1.6, 0))
    expect(pointAt(line, 0.5)).toEqual(v(5, 1.6, 0))
    expect(pointAt(line, 1)).toEqual(v(10, 1.6, 0))
  })

  it('空路径返回 null、单点路径恒返回该点', () => {
    expect(pointAt([], 0.5)).toBeNull()
    expect(pointAt([v(1, 2, 3)], 0.7)).toEqual(v(1, 2, 3))
  })

  it('折线跨段取点', () => {
    const poly = [v(0, 0, 0), v(4, 0, 0), v(4, 0, 4)]
    // 总长 8，t=0.75 → 走 6 → 第二段走 2
    expect(pointAt(poly, 0.75)).toEqual(v(4, 0, 2))
  })
})

describe('samplePathFrames', () => {
  it('采样 n 帧含首尾、times 均分 duration', () => {
    const path = { shape: 'line' as const, facePath: true, points: [v(0, 1.6, 0), v(8, 1.6, 0)] }
    const frames = samplePathFrames(path, 5, { duration: 8, fov: 50, lookTarget: v(0, 1, 0) })
    expect(frames).toHaveLength(5)
    expect(frames[0].time).toBe(0)
    expect(frames[4].time).toBe(8)
    expect(frames.map(f => f.position.x)).toEqual([0, 2, 4, 6, 8])
    expect(frames.every(f => f.easing === 'smooth')).toBe(true)
  })

  it('facePath=true 时 target 朝行进前方（y 取机位高度）', () => {
    const path = { shape: 'line' as const, facePath: true, points: [v(0, 1.6, 0), v(8, 1.6, 0)] }
    const frames = samplePathFrames(path, 3, { duration: 6, fov: 50, lookTarget: v(0, 0, 0) })
    // 首帧在前半程，target 在更前方（x 更大）
    expect(frames[0].target.x).toBeGreaterThan(frames[0].position.x)
    expect(frames[0].target.y).toBe(1.6)
  })

  it('facePath=false（环绕）时 target 恒为 lookTarget', () => {
    const path = { shape: 'ring' as const, facePath: false, points: [v(5, 1.6, 0), v(0, 1.6, 5), v(-5, 1.6, 0)] }
    const frames = samplePathFrames(path, 3, { duration: 6, fov: 50, lookTarget: v(0, 1.2, 0) })
    for (const f of frames) {
      expect(f.target).toEqual(v(0, 1.2, 0))
    }
  })

  it('空点串回退中性机位（不炸）', () => {
    const path = { shape: 'pencil' as const, facePath: true, points: [] }
    const frames = samplePathFrames(path, 2, { duration: 4, fov: 50, lookTarget: v(0, 0, 0) })
    expect(frames).toHaveLength(2)
    expect(frames[0].position.z).toBe(5)
  })

  it('采样数钳制 2~24', () => {
    const path = { shape: 'line' as const, facePath: true, points: [v(0, 1.6, 0), v(4, 1.6, 0)] }
    expect(samplePathFrames(path, 1, { duration: 4, fov: 50, lookTarget: v(0, 0, 0) })).toHaveLength(2)
    expect(samplePathFrames(path, 99, { duration: 4, fov: 50, lookTarget: v(0, 0, 0) })).toHaveLength(24)
  })
})
