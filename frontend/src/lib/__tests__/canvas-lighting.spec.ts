/* 打光纯函数单测：方位映射、亮度五档、空段过滤、智能模式、命名摘要 */

import { describe, it, expect, beforeAll } from 'vitest'
import { setLocale } from '@/i18n'
import {
  DEFAULT_LIGHTING_OPTIONS,
  LIGHT_POSITIONS,
  LIGHTING_STYLE_PRESETS,
  buildLightDirectionPrompt,
  buildLightingPrompt,
  buildLightingLabel,
  hexToColorName,
} from '../canvas-lighting'

// 文案断言固定在中文（测试环境 navigator.language 可能是 en）
beforeAll(() => setLocale('zh-CN'))

describe('buildLightDirectionPrompt 方位映射', () => {
  it('8 方位段', () => {
    expect(buildLightDirectionPrompt(0, 0)).toContain('from the front')
    expect(buildLightDirectionPrompt(45, 0)).toContain('front-right')
    expect(buildLightDirectionPrompt(90, 0)).toContain('right side')
    expect(buildLightDirectionPrompt(135, 0)).toContain('back-right')
    expect(buildLightDirectionPrompt(180, 0)).toContain('behind the subject')
    expect(buildLightDirectionPrompt(225, 0)).toContain('back-left')
    expect(buildLightDirectionPrompt(270, 0)).toContain('left side')
    expect(buildLightDirectionPrompt(315, 0)).toContain('front-left')
  })

  it('方位角环绕归一（-90 与 270 等价，365 与 5 等价）', () => {
    expect(buildLightDirectionPrompt(-90, 0)).toBe(buildLightDirectionPrompt(270, 0))
    expect(buildLightDirectionPrompt(365, 0)).toBe(buildLightDirectionPrompt(5, 0))
  })

  it('俯仰极值直接给顶光/底光，中段带修饰', () => {
    expect(buildLightDirectionPrompt(90, 60)).toBe('strong top-down key light from directly above')
    expect(buildLightDirectionPrompt(90, -60)).toBe('strong upward uplight from directly below the subject')
    expect(buildLightDirectionPrompt(90, 40)).toContain('tilted downward from above')
    expect(buildLightDirectionPrompt(90, -40)).toContain('tilted upward from below')
    expect(buildLightDirectionPrompt(90, 0)).not.toContain('tilted')
  })
})

describe('buildLightingPrompt', () => {
  it('默认参数：空段过滤，无相邻逗号，含一致性约束与 meta 标记', () => {
    const prompt = buildLightingPrompt({ ...DEFAULT_LIGHTING_OPTIONS }, '')
    expect(prompt).toContain('lighting-only edit')
    expect(prompt).toContain('do not add any lamp')
    expect(prompt).toContain('[lighting azimuth:0° elevation:0° brightness:50%]')
    expect(prompt).not.toContain(', ,')
    expect(prompt).not.toContain('toward')
  })

  it('预设、智能描述、轮廓光、光色按段拼接', () => {
    const prompt = buildLightingPrompt(
      { ...DEFAULT_LIGHTING_OPTIONS, stylePreset: 'rembrandt', rimLight: true, lightColor: '#ffb066', brightness: 20 },
      '黄昏窗边氛围',
    )
    expect(prompt).toContain('Rembrandt lighting')
    expect(prompt).toContain('黄昏窗边氛围')
    expect(prompt).toContain('rim light and edge highlight')
    expect(prompt).toContain('toward orange (#ffb066)')
    expect(prompt).toContain('low-key, dim and moody')
    expect(prompt).toContain('rim:on')
  })

  it('智能模式关闭时描述不进提示词', () => {
    const prompt = buildLightingPrompt({ ...DEFAULT_LIGHTING_OPTIONS, smartMode: false }, '黄昏窗边氛围')
    expect(prompt).not.toContain('黄昏窗边氛围')
  })

  it('描述前后空白被修剪', () => {
    const prompt = buildLightingPrompt({ ...DEFAULT_LIGHTING_OPTIONS }, '  soft window light  ')
    expect(prompt).toContain('soft window light')
    expect(prompt).not.toContain('  soft')
  })

  it('亮度五档', () => {
    const high = buildLightingPrompt({ ...DEFAULT_LIGHTING_OPTIONS, brightness: 80 }, '')
    expect(high).toContain('high-key')
    const low = buildLightingPrompt({ ...DEFAULT_LIGHTING_OPTIONS, brightness: 20 }, '')
    expect(low).toContain('low-key')
    const mid = buildLightingPrompt({ ...DEFAULT_LIGHTING_OPTIONS, brightness: 60 }, '')
    expect(mid).toContain('slightly brighter')
    const midLow = buildLightingPrompt({ ...DEFAULT_LIGHTING_OPTIONS, brightness: 40 }, '')
    expect(midLow).toContain('slightly darker')
    const neutral = buildLightingPrompt({ ...DEFAULT_LIGHTING_OPTIONS, brightness: 50 }, '')
    expect(neutral).not.toContain('exposure')
  })

  it('全部 8 个风格预设都有可用英文提示词', () => {
    for (const preset of LIGHTING_STYLE_PRESETS) {
      const prompt = buildLightingPrompt({ ...DEFAULT_LIGHTING_OPTIONS, stylePreset: preset.id }, '')
      expect(prompt).toContain(preset.prompt)
    }
  })

  it('光色进提示词时带英文名（模型对颜色词比色值敏感）', () => {
    const prompt = buildLightingPrompt({ ...DEFAULT_LIGHTING_OPTIONS, lightColor: '#5db4ff' }, '')
    expect(prompt).toContain('tinted toward blue (#5db4ff)')
  })

  it('白光不进光色段', () => {
    const prompt = buildLightingPrompt({ ...DEFAULT_LIGHTING_OPTIONS, lightColor: '#ffffff' }, '')
    expect(prompt).not.toContain('tinted toward')
  })
})

describe('hexToColorName 颜色名映射', () => {
  it('常见色相', () => {
    expect(hexToColorName('#ff0000')).toBe('red')
    expect(hexToColorName('#ff8800')).toBe('orange')
    expect(hexToColorName('#3ae0ff')).toBe('cyan')
    expect(hexToColorName('#5db4ff')).toBe('blue')
    expect(hexToColorName('#22aa44')).toBe('green')
  })

  it('明度修饰与灰阶', () => {
    expect(hexToColorName('#0a0a14')).toBe('deep blue')
    expect(hexToColorName('#ffd9a6')).toBe('pale orange')
    expect(hexToColorName('#ffffff')).toBe('white')
    expect(hexToColorName('#050505')).toBe('black')
    expect(hexToColorName('#8c8c8c')).toBe('grey')
  })

  it('非法输入返回空串', () => {
    expect(hexToColorName('not-a-color')).toBe('')
    expect(hexToColorName('')).toBe('')
  })

  it('每个预设都带合法的采样光照参数（供效果图渲染）', () => {
    for (const preset of LIGHTING_STYLE_PRESETS) {
      const sample = preset.sampleLight
      expect(sample.azimuth).toBeGreaterThanOrEqual(0)
      expect(sample.azimuth).toBeLessThanOrEqual(360)
      expect(sample.elevation).toBeGreaterThanOrEqual(-90)
      expect(sample.elevation).toBeLessThanOrEqual(90)
      expect(sample.brightness).toBeGreaterThanOrEqual(0)
      expect(sample.brightness).toBeLessThanOrEqual(100)
      expect(sample.lightColor).toMatch(/^#[0-9a-fA-F]{6}$/)
    }
  })
})

describe('buildLightingLabel 命名摘要', () => {
  it('命中预设：预设名 + 亮度 + 轮廓光 + 光色', () => {
    const label = buildLightingLabel({ ...DEFAULT_LIGHTING_OPTIONS, stylePreset: 'rembrandt', brightness: 30, rimLight: true, lightColor: '#ffb066' })
    expect(label).toContain('伦勃朗光')
    expect(label).toContain('亮度 30%')
    expect(label).toContain('轮廓光')
    expect(label).toContain('光色 #ffb066')
    expect(label.startsWith('AI 打光：')).toBe(true)
  })

  it('命中快捷方位', () => {
    for (const position of LIGHT_POSITIONS) {
      const label = buildLightingLabel({ ...DEFAULT_LIGHTING_OPTIONS, azimuth: position.azimuth, elevation: position.elevation })
      expect(label).toContain('主光')
    }
  })

  it('自由角度回退到度数描述', () => {
    const label = buildLightingLabel({ ...DEFAULT_LIGHTING_OPTIONS, azimuth: 123, elevation: 20 })
    expect(label).toContain('主光 123°/20°')
  })

  it('默认参数只含方位描述', () => {
    const label = buildLightingLabel({ ...DEFAULT_LIGHTING_OPTIONS })
    expect(label).toBe('AI 打光：主光前方')
  })
})
