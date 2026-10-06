/* formatTimecode 单测：HH:MM:SS.mmm 格式、进位、负值截断 */

import { describe, it, expect } from 'vitest'
import { formatTimecode } from '../editor-timecode'

describe('formatTimecode', () => {
  it('基础格式（时:分:秒.毫秒 3 位）', () => {
    expect(formatTimecode(0)).toBe('00:00:00.000')
    expect(formatTimecode(3.24)).toBe('00:00:03.240')
    expect(formatTimecode(61.5)).toBe('00:01:01.500')
    expect(formatTimecode(3661.5)).toBe('01:01:01.500')
  })

  it('毫秒四舍五入并正确进位', () => {
    expect(formatTimecode(0.9999)).toBe('00:00:01.000')
    expect(formatTimecode(59.9999)).toBe('00:01:00.000')
    expect(formatTimecode(7225.1234)).toBe('02:00:25.123')
  })

  it('负值截断为 0', () => {
    expect(formatTimecode(-0.5)).toBe('00:00:00.000')
  })
})
