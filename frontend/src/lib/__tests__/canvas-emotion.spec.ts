/* 表情控制纯函数单测：预设网格、blendshapes、提示词组装、几何裁切、羽化混合 */

import { describe, it, expect, beforeAll } from 'vitest'
import { setLocale } from '@/i18n'
import {
  EMOTION_PRESETS, NEUTRAL_EMOTION_PRESET,
  findEmotionPreset, clampAxis, emotionBlendshapes, buildEmotionPrompt,
  clampFaceBox, resolveEmotionEditRegion, emotionGenerationSize, emotionFeatherAlpha,
  emotionPresetLabel, emotionDriftScore,
} from '../canvas-emotion'

// 文案断言固定在中文（测试环境 navigator.language 可能是 en）
beforeAll(() => setLocale('zh-CN'))

describe('EMOTION_PRESETS 5×5 预设网格', () => {
  it('共 25 格，id 与坐标唯一', () => {
    expect(EMOTION_PRESETS).toHaveLength(25)
    expect(new Set(EMOTION_PRESETS.map(p => p.id)).size).toBe(25)
    expect(new Set(EMOTION_PRESETS.map(p => p.labelKey)).size).toBe(25)
  })

  it('行=唤醒度（上激动下平静），列=亲近度（左亲近右疏离）', () => {
    expect(EMOTION_PRESETS[0]).toMatchObject({ intimacy: 2, arousal: 2 })
    expect(EMOTION_PRESETS[4]).toMatchObject({ intimacy: -2, arousal: 2 })
    expect(EMOTION_PRESETS[20]).toMatchObject({ intimacy: 2, arousal: -2 })
    expect(EMOTION_PRESETS[24]).toMatchObject({ intimacy: -2, arousal: -2 })
  })

  it('中性格位于 (0,0)，每格都有英文提示词', () => {
    expect(NEUTRAL_EMOTION_PRESET.intimacy).toBe(0)
    expect(NEUTRAL_EMOTION_PRESET.arousal).toBe(0)
    for (const preset of EMOTION_PRESETS) {
      expect(preset.prompt.trim()).not.toBe('')
    }
  })
})

describe('findEmotionPreset / clampAxis', () => {
  it('越界值收敛到 [-2,2]', () => {
    expect(clampAxis(5)).toBe(2)
    expect(clampAxis(-9)).toBe(-2)
    expect(clampAxis(1.4)).toBe(1)
  })

  it('按坐标查预设，越界收敛到边界格', () => {
    expect(findEmotionPreset(-2, 2).intimacy).toBe(-2)
    // 5×5 全网格任意收敛坐标都命中对应预设（不会回退中性）
    expect(findEmotionPreset(99, -99)).toMatchObject({ intimacy: 2, arousal: -2 })
  })

  it('预设中文名走 i18n', () => {
    expect(emotionPresetLabel(NEUTRAL_EMOTION_PRESET)).toBe('中性克制')
  })
})

describe('emotionBlendshapes 情绪 → 面部权重', () => {
  it('中性返回空对象', () => {
    expect(emotionBlendshapes(NEUTRAL_EMOTION_PRESET)).toEqual({})
  })

  it('喜悦带 smile，悲伤带 frown，激动带 eyeWide（L/R 成对）', () => {
    const joy = emotionBlendshapes(findEmotionPreset(2, 2))
    expect(joy.mouthSmile_L).toBeGreaterThan(0)
    expect(joy.mouthSmile_L).toBe(joy.mouthSmile_R)
    const sad = emotionBlendshapes(findEmotionPreset(-2, -2))
    expect(sad.mouthFrown_L).toBeGreaterThan(0)
    expect(emotionBlendshapes(findEmotionPreset(0, 2)).eyeWide_L).toBeGreaterThan(0)
  })

  it('权重全部在 (0,1] 区间', () => {
    for (const preset of EMOTION_PRESETS) {
      for (const value of Object.values(emotionBlendshapes(preset))) {
        expect(value).toBeGreaterThan(0)
        expect(value).toBeLessThanOrEqual(1)
      }
    }
  })
})

describe('buildEmotionPrompt 提示词组装', () => {
  const box = { id: 'f1', x: 100, y: 50, width: 60, height: 80, source: 'detected' as const }
  const region = { x: 0, y: 0, width: 300, height: 300 }
  // 在测试内构建（describe 收集期早于 beforeAll 的 setLocale，文案断言会错语言）
  const makePrompt = (...chars: Array<{ name: string; preset: ReturnType<typeof findEmotionPreset> }>) =>
    buildEmotionPrompt(chars.map(c => ({ ...c, faceBox: box })), region)

  it('单角色：包含角色名、目标情绪与人脸框像素坐标', () => {
    const prompt = makePrompt({ name: '小婉', preset: NEUTRAL_EMOTION_PRESET })
    expect(prompt).toContain('小婉')
    expect(prompt).toContain('中性克制')
    expect(prompt).toContain('x=100px')
    expect(prompt).toContain('width=60px')
    // 人脸中心 (130, 90) 在 300×300 中约 43%/30%
    expect(prompt).toContain('43% 横向、30% 纵向')
  })

  it('单角色：包含身份锁定与禁改约束', () => {
    const prompt = makePrompt({ name: '小婉', preset: NEUTRAL_EMOTION_PRESET })
    expect(prompt).toContain('仅修改第一张输入图')
    expect(prompt).toContain('第二张输入图仅用于核对同一人物身份')
    expect(prompt).toContain('严格保持人物身份')
    expect(prompt).toContain('构图完全对齐')
    // 蒙版措辞不得出现"白色"字样（会被模型字面化画成白圈），并明令禁止覆盖层
    expect(prompt).toContain('编辑范围蒙版')
    expect(prompt).not.toContain('白色为唯一可编辑')
    expect(prompt).toContain('不要添加白色雾感')
  })

  it('多角色：逐角色列人脸框与情绪，声明参考图与角色顺序一一对应', () => {
    const prompt = makePrompt(
      { name: '小婉', preset: findEmotionPreset(2, 2) },
      { name: '阿玲', preset: NEUTRAL_EMOTION_PRESET },
    )
    expect(prompt).toContain('以下 2 个角色')
    expect(prompt).toContain('角色1「小婉」')
    expect(prompt).toContain('角色2「阿玲」')
    expect(prompt).toContain('欣喜若狂')
    expect(prompt).toContain('中性克制')
    expect(prompt).toContain('顺序一一对应')
    expect(prompt).toContain('严格保持每个人物身份')
  })
})

describe('几何：人脸框与编辑区', () => {
  it('clampFaceBox 收敛回图像范围', () => {
    expect(clampFaceBox({ id: 'a', x: -10, y: -20, width: 60, height: 80, source: 'manual' }, 100, 100))
      .toMatchObject({ x: 0, y: 0, width: 60, height: 80 })
    expect(clampFaceBox({ id: 'b', x: 90, y: 90, width: 50, height: 50, source: 'manual' }, 100, 100))
      .toMatchObject({ x: 90, y: 90, width: 10, height: 10 })
  })

  it('resolveEmotionEditRegion 四周留余量并裁回图像', () => {
    // 居中框：left=400-170, top=300-150, right=400+370, bottom=300+400
    expect(resolveEmotionEditRegion({ id: 'a', x: 400, y: 300, width: 200, height: 200, source: 'detected' }, 1000, 1000))
      .toEqual({ x: 230, y: 150, width: 540, height: 550 })
    // 贴边框不越界
    expect(resolveEmotionEditRegion({ id: 'b', x: 0, y: 0, width: 100, height: 100, source: 'detected' }, 500, 500))
      .toEqual({ x: 0, y: 0, width: 185, height: 200 })
  })

  it('emotionGenerationSize 按宽高比选尺寸', () => {
    expect(emotionGenerationSize({ x: 0, y: 0, width: 1200, height: 800 })).toBe('1536x1024')
    expect(emotionGenerationSize({ x: 0, y: 0, width: 800, height: 1200 })).toBe('1024x1536')
    expect(emotionGenerationSize({ x: 0, y: 0, width: 540, height: 550 })).toBe('1024x1024')
  })
})

describe('emotionFeatherAlpha 羽化曲线', () => {
  it('椭圆内全取，椭圆外全弃，0.65~1 宽过渡带平滑衰减', () => {
    expect(emotionFeatherAlpha(0)).toBe(1)
    expect(emotionFeatherAlpha(0.65)).toBe(1)
    expect(emotionFeatherAlpha(1)).toBe(0)
    expect(emotionFeatherAlpha(1.5)).toBe(0)
    const mid = emotionFeatherAlpha(0.825)
    expect(mid).toBeGreaterThan(0)
    expect(mid).toBeLessThan(1)
    expect(mid).toBeCloseTo(0.5, 1)
  })
})

describe('emotionDriftScore 几何漂移评分', () => {
  const region = { x: 0, y: 0, width: 500, height: 520 }
  const face = (eyes: Array<{ x: number; y: number }>, over = {}) =>
    ({ id: 'f', x: 150, y: 150, width: 200, height: 200, source: 'detected' as const, keypoints: eyes, ...over })

  it('构图完全一致时评分为 0', () => {
    const eyes = [{ x: 210, y: 230 }, { x: 290, y: 230 }]
    // 生成图 1024² 中脸框与源图按覆盖缩放等比对应（脸/眼相对位置逐一对齐）
    const score = emotionDriftScore(
      { faceBox: face(eyes), generatedFaceBox: face([{ x: 432, y: 452 }, { x: 592, y: 452 }], { width: 400, height: 400, x: 312, y: 292 }) },
      region, 1024, 1024,
    )
    expect(score).toBeLessThan(0.02)
  })

  it('生成图人脸放大 20% 时评分显著升高', () => {
    const eyes = [{ x: 210, y: 230 }, { x: 290, y: 230 }]
    const score = emotionDriftScore(
      { faceBox: face(eyes), generatedFaceBox: face([{ x: 416, y: 444 }, { x: 608, y: 444 }], { width: 480, height: 480, x: 272, y: 252 }) },
      region, 1024, 1024,
    )
    expect(score).toBeGreaterThan(0.1)
  })

  it('缺少生成图人脸框时返回 0（无信息不判罚）', () => {
    expect(emotionDriftScore({ faceBox: face([]) }, region, 1024, 1024)).toBe(0)
  })
})
