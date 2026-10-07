/* =====================================================
 * 运镜注册表纯函数测试（端点/中点数值 + 裁剪窗钳制）
 * ===================================================== */

import { describe, expect, it } from 'vitest'

import { cameraRectAt, isCameraType } from '@/lib/editor-camera-registry'

describe('isCameraType', () => {
  it('枚举内 true，其余 false', () => {
    expect(isCameraType('zoomIn')).toBe(true)
    expect(isCameraType('rotate')).toBe(false)
    expect(isCameraType(null)).toBe(false)
  })
})

describe('cameraRectAt', () => {
  it('无运镜 / 非法 type → null', () => {
    expect(cameraRectAt(null, 0.5)).toBeNull()
    expect(cameraRectAt({ type: 'nope', strength: 1 }, 0.5)).toBeNull()
  })

  it('推进：p=0 全画面，p=1 zoom=1+0.6×strength（居中）', () => {
    const cam = { type: 'zoomIn', strength: 1 }
    const p0 = cameraRectAt(cam, 0)!
    expect(p0.zoom).toBe(1)
    expect(p0.x).toBeCloseTo(0)
    const p1 = cameraRectAt(cam, 1)!
    expect(p1.zoom).toBeCloseTo(1.6)
    expect(p1.x).toBeCloseTo((1 - 1 / 1.6) / 2)
    expect(p1.y).toBeCloseTo(p1.x)
    // 中点对称
    const mid = cameraRectAt(cam, 0.5)!
    expect(mid.zoom).toBeCloseTo(1.3)
  })

  it('拉远：p=1 回到全画面', () => {
    const cam = { type: 'zoomOut', strength: 1 }
    expect(cameraRectAt(cam, 0)!.zoom).toBeCloseTo(1.6)
    expect(cameraRectAt(cam, 1)!.zoom).toBe(1)
  })

  it('右移：zoom 恒 1.3，窗口 x 从左缘滑到右缘（贴边），y 居中', () => {
    const cam = { type: 'panRight', strength: 1 }
    const p0 = cameraRectAt(cam, 0)!
    const p1 = cameraRectAt(cam, 1)!
    const span = 1 - 1 / 1.3
    expect(p0.zoom).toBeCloseTo(1.3)
    expect(p1.zoom).toBeCloseTo(1.3)
    expect(p0.x).toBeCloseTo(0)
    expect(p1.x).toBeCloseTo(span)
    expect(p0.y).toBeCloseTo(span / 2)
    // x 始终不越界
    const mid = cameraRectAt(cam, 0.5)!
    expect(mid.x).toBeGreaterThan(0)
    expect(mid.x).toBeLessThan(span)
  })

  it('下移：窗口 y 从上缘滑到下缘，x 居中', () => {
    const cam = { type: 'panDown', strength: 1 }
    const p0 = cameraRectAt(cam, 0)!
    const p1 = cameraRectAt(cam, 1)!
    const span = 1 - 1 / 1.3
    expect(p0.y).toBeCloseTo(0)
    expect(p1.y).toBeCloseTo(span)
    expect(p0.x).toBeCloseTo(span / 2)
  })

  it('progress/strength 越界钳制到 0~1', () => {
    const cam = { type: 'zoomIn', strength: 2 }
    expect(cameraRectAt(cam, 3)!.zoom).toBeCloseTo(1.6)
    expect(cameraRectAt({ type: 'zoomIn', strength: -1 }, 0.5)!.zoom).toBe(1)
  })
})
