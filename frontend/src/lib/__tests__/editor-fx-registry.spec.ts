/* =====================================================
 * 转场/效果器注册表单测：描述符完整性 + 派生类型清单 + 纯函数行为
 * ===================================================== */

import { describe, expect, it } from 'vitest'

import {
  EFFECT_DEFS,
  EFFECT_TYPES,
  TRANSITION_DEFS,
  TRANSITION_TYPES,
  canvasFilterForEffects,
  effectDef,
  transitionDef,
} from '@/lib/editor-fx-registry'
import { isEffectType, isTransitionType } from '@/lib/editor-types'

describe('注册表完整性', () => {
  it('转场描述符：type 守卫认可全部注册项，ffmpegName 非空', () => {
    expect(TRANSITION_DEFS.length).toBeGreaterThanOrEqual(3)
    for (const def of TRANSITION_DEFS) {
      expect(isTransitionType(def.type)).toBe(true)
      expect(def.ffmpegName).toBeTruthy()
      expect(def.labelKey).toContain('editor.transitions.')
      expect(['crossfade', 'fade', 'wipe']).toContain(def.preview)
    }
  })

  it('效果器描述符：type 守卫认可全部注册项，filter 纯函数出值', () => {
    for (const def of EFFECT_DEFS) {
      expect(isEffectType(def.type)).toBe(true)
      expect(def.labelKey).toContain('editor.effects.')
      expect(def.ffmpegFilter(0.4)).toBeTruthy()
      expect(def.canvasFilter(0.4)).toBeTruthy()
      expect(def.previewCss(0.4)).toBeTruthy()
    }
  })

  it('派生类型清单与描述符一致（UI 下拉/卡片数据源）', () => {
    expect(TRANSITION_TYPES).toEqual(TRANSITION_DEFS.map((d) => d.type))
    expect(EFFECT_TYPES).toEqual(EFFECT_DEFS.map((d) => d.type))
  })
})

describe('查表与回退', () => {
  it('transitionDef 未知类型回退 crossfade（与渲染端 xfade 默认一致）', () => {
    expect(transitionDef('crossfade').ffmpegName).toBe('fade')
    expect(transitionDef('boom').type).toBe('crossfade')
  })

  it('effectDef 未知类型返回 null（不施加）', () => {
    expect(effectDef('blur')?.ffmpegFilter(0.4)).toBe('gblur=sigma=8.00')
    expect(effectDef('sepia')).toBeNull()
  })
})

describe('canvasFilterForEffects', () => {
  it('空/undefined 返回 null；多效果器按顺序串联', () => {
    expect(canvasFilterForEffects(undefined)).toBeNull()
    expect(canvasFilterForEffects([])).toBeNull()
    expect(
      canvasFilterForEffects([
        { type: 'grayscale', strength: 1 },
        { type: 'blur', strength: 0.4 },
      ]),
    ).toBe('grayscale(1) blur(8.0px)')
  })

  it('未知类型跳过不污染滤镜串', () => {
    expect(canvasFilterForEffects([{ type: 'sepia', strength: 1 }])).toBeNull()
    expect(canvasFilterForEffects([
      { type: 'sepia', strength: 1 },
      { type: 'grayscale', strength: 1 },
    ])).toBe('grayscale(1)')
  })
})
