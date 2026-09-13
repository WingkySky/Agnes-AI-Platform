/* 尺寸匹配工具单测：覆盖「自动」模式的档位过滤与偏好比例解析 */

import { describe, it, expect } from 'vitest'
import { matchImageSize, matchSizeByRatio, AUTO_RATIO_VALUE } from '../model-params'

describe('matchImageSize', () => {
  it('按比例匹配最接近的预设（16:10 → 3:2）', () => {
    expect(matchImageSize(1600, 1000)).toBe('1216x832')
  })

  it('传入 tier 时只在对应清晰度档内匹配（精确比例并列取先出现）', () => {
    // 4:3 精确比例在各档都有，不传 tier 时 tie 取 sd；传 hd 锁定 hd 档
    expect(matchImageSize(4000, 3000)).toBe('1152x864')
    expect(matchImageSize(4000, 3000, undefined, 'hd')).toBe('2048x1536')
  })
})

describe('matchSizeByRatio', () => {
  it('在指定清晰度档内取比例精确对应的尺寸', () => {
    expect(matchSizeByRatio('16:9', 'hd')).toBe('2304x1296')
    expect(matchSizeByRatio('1:1', '4k')).toBe('4096x4096')
  })

  it('非标准比例取档内最接近的（21:9 → 16:9）', () => {
    expect(matchSizeByRatio('21:9', 'sd')).toBe('1280x720')
  })

  it('未传档位时在全量预设中匹配', () => {
    expect(matchSizeByRatio('9:16')).toBe('720x1280')
  })
})

describe('AUTO_RATIO_VALUE', () => {
  it('为 auto 字面量（仅前端状态，不得传给后端）', () => {
    expect(AUTO_RATIO_VALUE).toBe('auto')
  })
})
