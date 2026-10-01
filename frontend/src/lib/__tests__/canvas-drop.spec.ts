/* planDropLayout 单测：落点居中、行排列、换行与混合尺寸 */

import { describe, it, expect } from 'vitest'
import { planDropLayout } from '../canvas-drop'

const IMG = { width: 340, height: 240 }
const VIDEO = { width: 420, height: 236 }

describe('planDropLayout', () => {
  it('空入参返回空数组', () => {
    expect(planDropLayout([], 100, 200)).toEqual([])
  })

  it('单个节点以落点为中心', () => {
    expect(planDropLayout([IMG], 100, 200)).toEqual([{ x: 100 - 170, y: 200 - 120 }])
  })

  it('多节点横向排列，间距 gap', () => {
    const pos = planDropLayout([IMG, IMG, IMG], 500, 300, 4, 16)
    expect(pos[0]).toEqual({ x: 500 - 170, y: 300 - 120 })
    expect(pos[1]).toEqual({ x: pos[0].x + 340 + 16, y: pos[0].y })
    expect(pos[2]).toEqual({ x: pos[1].x + 340 + 16, y: pos[0].y })
  })

  it('超过每行上限换行，行高取行内最大', () => {
    const pos = planDropLayout([VIDEO, IMG, VIDEO, IMG, IMG], 0, 0, 3, 10)
    // 第一行 [video, img, video]，行高 = max(236, 240, 236) = 240
    expect(pos[1].y).toBe(0 - 120)
    expect(pos[2].y).toBe(0 - 118)
    // 第二行整体下移一行（240 + gap），x 重新从落点锚点起排
    expect(pos[3].y).toBe(0 - 120 + 240 + 10)
    expect(pos[3].x).toBe(0 - 170)
    expect(pos[4].x).toBe(pos[3].x + 340 + 10)
  })

  it('混合尺寸同行时列偏移按前序节点实际宽度累加', () => {
    const pos = planDropLayout([VIDEO, IMG], 1000, 1000, 4, 16)
    expect(pos[1].x).toBe(1000 - 170 + 420 + 16)
  })
})
