/* =====================================================
 * 转场/效果器注册表（可扩展的唯一事实源）
 *
 * 参考注册表描述符模式（OpenCut params/registry 的 DefinitionRegistry 极简版）：
 * 新增一种转场/效果器 = 本文件加一条描述符 + 后端 lowering 映射表加一行 + i18n，
 * UI 库卡片、预览绘制、渲染端滤镜全部由描述符驱动，无散落硬编码。
 * - 转场：ffmpegName（渲染端 xfade transition 名）+ preview（预览混合绘制族）
 * - 效果器：ffmpegFilter / canvasFilter / previewCss 三个纯函数按 strength 出值
 * ===================================================== */

import type { EffectType, TransitionType } from './editor-types'

// ---------- 转场 ----------

export interface TransitionDef {
  type: TransitionType
  labelKey: string
  /** 渲染端：ffmpeg xfade transition 名 */
  ffmpegName: string
  /** 预览端混合绘制族：crossfade=alpha 叠化 / fade=黑场插值 / wipe=擦除显现 */
  preview: 'crossfade' | 'fade' | 'wipe'
}

export const TRANSITION_DEFS: TransitionDef[] = [
  { type: 'crossfade', labelKey: 'editor.transitions.crossfade', ffmpegName: 'fade', preview: 'crossfade' },
  { type: 'fade', labelKey: 'editor.transitions.fade', ffmpegName: 'fadeblack', preview: 'fade' },
  { type: 'wipe', labelKey: 'editor.transitions.wipe', ffmpegName: 'wipeleft', preview: 'wipe' },
]

export const TRANSITION_TYPES: TransitionType[] = TRANSITION_DEFS.map((d) => d.type)

/** 未知类型回退 crossfade（渲染端 xfade 默认同名语义） */
export function transitionDef(type: string): TransitionDef {
  return TRANSITION_DEFS.find((d) => d.type === type) ?? TRANSITION_DEFS[0]!
}

// ---------- 效果器 ----------

export interface EffectDef {
  type: EffectType
  labelKey: string
  /** 渲染端：归一化 vf 滤镜片段（strength 0~1）；null = 不施加 */
  ffmpegFilter: (strength: number) => string | null
  /** 预览端：canvas ctx.filter 值；null = 不施加 */
  canvasFilter: (strength: number) => string | null
  /** 库卡片/属性区示意：CSS filter 值（作用于示例缩略图） */
  previewCss: (strength: number) => string | null
  /** 是否展示强度调节（grayscale 恒定黑白不可调） */
  adjustable: boolean
}

export const EFFECT_DEFS: EffectDef[] = [
  {
    type: 'grayscale',
    labelKey: 'editor.effects.grayscale',
    ffmpegFilter: () => 'hue=s=0',
    canvasFilter: () => 'grayscale(1)',
    previewCss: () => 'grayscale(1)',
    adjustable: false,
  },
  {
    type: 'blur',
    labelKey: 'editor.effects.blur',
    ffmpegFilter: (s) => `gblur=sigma=${(s * 20).toFixed(2)}`,
    canvasFilter: (s) => `blur(${(s * 20).toFixed(1)}px)`,
    previewCss: (s) => `blur(${(s * 20).toFixed(1)}px)`,
    adjustable: true,
  },
]

export const EFFECT_TYPES: EffectType[] = EFFECT_DEFS.map((d) => d.type)

/** 未知类型返回 null（不施加） */
export function effectDef(type: string): EffectDef | null {
  return EFFECT_DEFS.find((d) => d.type === type) ?? null
}

/** 片段效果器 → 预览 ctx.filter 组合串（空返回 null；按 effects 顺序串联） */
export function canvasFilterForEffects(effects: Array<{ type: string; strength: number }> | undefined | null): string | null {
  if (!effects || effects.length === 0) return null
  const parts = effects
    .map((e) => effectDef(e.type)?.canvasFilter(e.strength))
    .filter((v): v is string => !!v)
  return parts.length > 0 ? parts.join(' ') : null
}
