/* =====================================================
 * canvas-angle — AI 多角度纯函数集
 * - 角度预设 / 限位 / 景别档位判定
 * - 提示词构建（一致性约束 + 角度描述 + 档位词）
 * 供 CanvasImageAngleDialog 与单测使用
 * ===================================================== */

import { t } from '@/i18n'

/** 多角度参数 */
export interface AngleParams {
  /** 水平环绕角 -180~180（0=正面，负=向左，正=向右，±180=背面） */
  horizontalAngle: number
  /** 垂直俯仰角 -60~60（正=俯视，负=仰视） */
  pitchAngle: number
  /** 镜头距离 1~10 */
  cameraDistance: number
  /** 广角镜头 */
  wideAngle: boolean
}

export type AnglePresetId = 'front' | 'left' | 'right' | 'back' | 'top' | 'bottom'

export interface AnglePreset {
  id: AnglePresetId
  labelKey: string
  horizontalAngle: number
  pitchAngle: number
}

/** 快捷视角预设 */
export const ANGLE_PRESETS: AnglePreset[] = [
  { id: 'front', labelKey: 'canvas.imageOps.presetFront', horizontalAngle: 0, pitchAngle: 0 },
  { id: 'left', labelKey: 'canvas.imageOps.presetLeft', horizontalAngle: -90, pitchAngle: 0 },
  { id: 'right', labelKey: 'canvas.imageOps.presetRight', horizontalAngle: 90, pitchAngle: 0 },
  { id: 'back', labelKey: 'canvas.imageOps.presetBack', horizontalAngle: 180, pitchAngle: 0 },
  { id: 'top', labelKey: 'canvas.imageOps.presetTop', horizontalAngle: 0, pitchAngle: 60 },
  { id: 'bottom', labelKey: 'canvas.imageOps.presetBottom', horizontalAngle: 0, pitchAngle: -60 },
]

/** 角度限位（水平支持绕到背面） */
export const ANGLE_LIMITS = {
  rotateMin: -180,
  rotateMax: 180,
  tiltMin: -60,
  tiltMax: 60,
  distanceMin: 1,
  distanceMax: 10,
} as const

/** 方向箭头步进（度） */
export const ANGLE_STEP = 5

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

/** 归一化到 [-180, 180) */
export function normalizeAngle(value: number): number {
  return (((value + 180) % 360) + 360) % 360 - 180
}

/** 按水平+俯仰双向匹配预设；不匹配返回 undefined（展示"自定义"） */
export function findAnglePreset(horizontalAngle: number, pitchAngle: number): AnglePreset | undefined {
  return ANGLE_PRESETS.find(p => p.horizontalAngle === horizontalAngle && p.pitchAngle === pitchAngle)
}

/** 景别档位：≤3 近景 / ≥7 全景 / 其余中景 */
export function distanceTier(distance: number): 'near' | 'medium' | 'far' {
  if (distance <= 3) return 'near'
  if (distance >= 7) return 'far'
  return 'medium'
}

const TIER_KEYS: Record<'near' | 'medium' | 'far', string> = {
  near: 'canvas.imageOps.tierNear',
  medium: 'canvas.imageOps.tierMedium',
  far: 'canvas.imageOps.tierFar',
}

/** 镜头距离对应的档位 i18n key */
export function distanceTierKey(distance: number): string {
  return TIER_KEYS[distanceTier(distance)]
}

/** 构建多角度提示词：一致性约束 + 角度/距离档位/镜头描述 */
export function buildAnglePrompt(params: AngleParams): string {
  const horizontal = params.horizontalAngle > 0
    ? t('canvas.imageOps.dirRight', { angle: params.horizontalAngle })
    : params.horizontalAngle < 0
      ? t('canvas.imageOps.dirLeft', { angle: Math.abs(params.horizontalAngle) })
      : t('canvas.imageOps.dirFront')
  const pitch = params.pitchAngle > 0
    ? t('canvas.imageOps.dirDown', { angle: params.pitchAngle })
    : params.pitchAngle < 0
      ? t('canvas.imageOps.dirUp', { angle: Math.abs(params.pitchAngle) })
      : t('canvas.imageOps.dirLevel')
  const lens = params.wideAngle ? t('canvas.imageOps.wideAngleLens') : t('canvas.imageOps.standardLens')
  return t('canvas.imageOps.anglePromptTemplate', {
    horizontal,
    pitch,
    distance: params.cameraDistance.toFixed(1),
    tier: t(TIER_KEYS[distanceTier(params.cameraDistance)]),
    lens,
  })
}
