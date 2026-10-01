/* 多角度纯函数单测：预设匹配、景别档位边界、提示词构建 */

import { describe, it, expect, beforeAll } from 'vitest'
import { setLocale } from '@/i18n'
import {
  ANGLE_LIMITS,
  clamp,
  normalizeAngle,
  findAnglePreset,
  distanceTier,
  buildAnglePrompt,
} from '../canvas-angle'

// 文案断言固定在中文（测试环境 navigator.language 可能是 en）
beforeAll(() => setLocale('zh-CN'))

describe('normalizeAngle / clamp', () => {
  it('归一化到 [-180, 180)', () => {
    expect(normalizeAngle(0)).toBe(0)
    expect(normalizeAngle(185)).toBe(-175)
    expect(normalizeAngle(-185)).toBe(175)
    expect(normalizeAngle(360)).toBe(0)
  })

  it('clamp 限位', () => {
    expect(clamp(200, ANGLE_LIMITS.tiltMin, ANGLE_LIMITS.tiltMax)).toBe(60)
    expect(clamp(-100, ANGLE_LIMITS.tiltMin, ANGLE_LIMITS.tiltMax)).toBe(-60)
    expect(clamp(45, ANGLE_LIMITS.tiltMin, ANGLE_LIMITS.tiltMax)).toBe(45)
  })
})

describe('findAnglePreset', () => {
  it('水平+俯仰双向匹配', () => {
    expect(findAnglePreset(180, 0)?.id).toBe('back')
    expect(findAnglePreset(0, -60)?.id).toBe('bottom')
    expect(findAnglePreset(0, 60)?.id).toBe('top')
  })

  it('非预设组合返回 undefined', () => {
    expect(findAnglePreset(45, 0)).toBeUndefined()
    expect(findAnglePreset(0, 59)).toBeUndefined()
  })
})

describe('distanceTier 档位边界', () => {
  it('≤3 近景，≥7 全景，其余中景', () => {
    expect(distanceTier(1)).toBe('near')
    expect(distanceTier(3)).toBe('near')
    expect(distanceTier(4.8)).toBe('medium')
    expect(distanceTier(7)).toBe('far')
    expect(distanceTier(10)).toBe('far')
  })
})

describe('buildAnglePrompt', () => {
  it('包含一致性约束、角度描述、距离档位与镜头类型', () => {
    const prompt = buildAnglePrompt({ horizontalAngle: 45, pitchAngle: 30, cameraDistance: 4.8, wideAngle: false })
    expect(prompt).toContain('不要只做透视变形')
    expect(prompt).toContain('向右 45°')
    expect(prompt).toContain('俯视 30°')
    expect(prompt).toContain('4.8')
    expect(prompt).toContain('中景')
    expect(prompt).toContain('标准镜头')
  })

  it('正面平视 + 广角', () => {
    const prompt = buildAnglePrompt({ horizontalAngle: 0, pitchAngle: 0, cameraDistance: 8, wideAngle: true })
    expect(prompt).toContain('正面')
    expect(prompt).toContain('平视')
    expect(prompt).toContain('全景')
    expect(prompt).toContain('广角镜头')
  })

  it('负角度描述为向左/仰视', () => {
    const prompt = buildAnglePrompt({ horizontalAngle: -90, pitchAngle: -30, cameraDistance: 2, wideAngle: false })
    expect(prompt).toContain('向左 90°')
    expect(prompt).toContain('仰视 30°')
    expect(prompt).toContain('近景')
  })
})
