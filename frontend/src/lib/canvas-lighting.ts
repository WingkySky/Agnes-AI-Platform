/* =====================================================
 * canvas-lighting — AI 打光纯函数集
 * - 光源方向/亮度/光色/轮廓光/风格预设 → 打光提示词
 * - 一致性约束：只改光照不改实体，禁止把灯具设备画进画面
 * 供 CanvasLightingDialog 与单测使用
 * ===================================================== */

import { t } from '@/i18n'

/** 打光参数 */
export interface LightingOptions {
  /** 主光方位角 0~360（0=正前，90=右，180=正后，270=左） */
  azimuth: number
  /** 仰角 -90~90（正=光从上向下，负=从下向上） */
  elevation: number
  /** 亮度 0~100（50 为不变） */
  brightness: number
  /** 轮廓光 */
  rimLight: boolean
  /** 风格预设 id，'' = 不使用 */
  stylePreset: string
  /** 智能模式：附加自然语言描述 */
  smartMode: boolean
  /** 光色 HEX，#ffffff = 不着色 */
  lightColor: string
}

/** 打光渲染参数（预览/效果图用，LightingOptions 去掉交互字段） */
export type LightingRenderParams = Pick<LightingOptions, 'azimuth' | 'elevation' | 'brightness' | 'rimLight' | 'lightColor'>

export const DEFAULT_LIGHTING_OPTIONS: LightingOptions = {
  azimuth: 0,
  elevation: 0,
  brightness: 50,
  rimLight: false,
  stylePreset: '',
  smartMode: true,
  lightColor: '#ffffff',
}

/** 主光源快捷方位 */
export const LIGHT_POSITIONS: Array<{ labelKey: string; azimuth: number; elevation: number }> = [
  { labelKey: 'canvas.imageOps.lightLeft', azimuth: 270, elevation: 0 },
  { labelKey: 'canvas.imageOps.lightTop', azimuth: 0, elevation: 80 },
  { labelKey: 'canvas.imageOps.lightRight', azimuth: 90, elevation: 0 },
  { labelKey: 'canvas.imageOps.lightFront', azimuth: 0, elevation: 0 },
  { labelKey: 'canvas.imageOps.lightBottom', azimuth: 0, elevation: -80 },
  { labelKey: 'canvas.imageOps.lightBack', azimuth: 180, elevation: 0 },
]

export interface LightingStylePreset {
  id: string
  labelKey: string
  /** 预设氛围底色（效果图背景/氛围叠加） */
  color: string
  /** 英文光照提示词（生图模型对英文光照词更稳） */
  prompt: string
  /** 预设效果图的采样光照参数 */
  sampleLight: LightingRenderParams
}

/** 风格预设 */
export const LIGHTING_STYLE_PRESETS: LightingStylePreset[] = [
  {
    id: 'overexposed', labelKey: 'canvas.imageOps.styleOverexposed', color: '#d4b896',
    prompt: 'overexposed film aesthetic, high-key lighting, washed out highlights, soft diffused light, vintage film look',
    sampleLight: { azimuth: 0, elevation: 20, brightness: 92, rimLight: false, lightColor: '#fff3dd' },
  },
  {
    id: 'blueBacklight', labelKey: 'canvas.imageOps.styleBlueBacklight', color: '#1a3a5c',
    prompt: 'dramatic backlighting, blue rim light, cool color temperature, silhouette with colored edges, ethereal atmosphere',
    sampleLight: { azimuth: 180, elevation: -10, brightness: 30, rimLight: true, lightColor: '#5db4ff' },
  },
  {
    id: 'rembrandt', labelKey: 'canvas.imageOps.styleRembrandt', color: '#5a3a1a',
    prompt: 'Rembrandt lighting, 45-degree angle key light, dramatic chiaroscuro, painterly shadows, classical portraiture',
    sampleLight: { azimuth: 305, elevation: 25, brightness: 42, rimLight: false, lightColor: '#ffd9a6' },
  },
  {
    id: 'cyberpunk', labelKey: 'canvas.imageOps.styleCyberpunk', color: '#2a0a2a',
    prompt: 'cyberpunk neon lighting, synthetic glow, futuristic atmosphere, vibrant cyan and magenta neon',
    sampleLight: { azimuth: 100, elevation: -5, brightness: 40, rimLight: true, lightColor: '#3ae0ff' },
  },
  {
    id: 'sunset', labelKey: 'canvas.imageOps.styleSunset', color: '#7a3010',
    prompt: 'golden hour lighting, warm sunset tones, long shadow, romantic atmosphere, Kodachrome colors',
    sampleLight: { azimuth: 15, elevation: 8, brightness: 55, rimLight: false, lightColor: '#ff9a45' },
  },
  {
    id: 'mysterious', labelKey: 'canvas.imageOps.styleMysterious', color: '#0a0a14',
    prompt: 'low-key noir lighting, deep shadows, mysterious mood, film noir style, high contrast cinematic',
    sampleLight: { azimuth: 270, elevation: 35, brightness: 16, rimLight: false, lightColor: '#9fb0d8' },
  },
  {
    id: 'goldenHour', labelKey: 'canvas.imageOps.styleGoldenHour', color: '#7a5a00',
    prompt: 'golden hour photography, warm soft light, beautiful catchlights, lens flare, magical golden glow',
    sampleLight: { azimuth: 30, elevation: 15, brightness: 68, rimLight: false, lightColor: '#ffcf82' },
  },
  {
    id: 'nolanGrey', labelKey: 'canvas.imageOps.styleNolanGrey', color: '#1a2a2a',
    prompt: 'cinematic cold-tone grading, desaturated teal and grey palette, high-contrast film look',
    sampleLight: { azimuth: 315, elevation: 40, brightness: 45, rimLight: false, lightColor: '#c8d8e8' },
  },
]

/** 一致性约束段：只改光照，禁止实体灯具入画 */
const CONSISTENCY_PROMPT = [
  'this is a lighting-only edit of the reference image: same scene, same people, same action, same clothing, same background, only the lighting changes',
  'the following instructions describe how light falls on the subject, they are not new objects to add to the scene',
  'do not add any lamp, spotlight, light fixture, reflector, softbox, torch, candle, or photography equipment into the image',
  'preserve identity, face, outfit, hairstyle, body pose, and the background layout from the input image',
  'if multiple people are present, preserve the same number of people and their spatial relationship',
  'only change lighting direction, light color, brightness, shadows, contrast, and mood',
].join(', ')

/**
 * 方位角+仰角 → 模型稳定的自然语言描述。
 * 只描述光照落向，不描述实体灯具，避免模型把摄影设备画进画面。
 */
export function buildLightDirectionPrompt(azimuth: number, elevation: number): string {
  const deg = ((azimuth % 360) + 360) % 360
  if (elevation >= 60) return 'strong top-down key light from directly above'
  if (elevation <= -60) return 'strong upward uplight from directly below the subject'
  let azimuthName: string
  if (deg >= 345 || deg <= 15) azimuthName = 'coming from the front'
  else if (deg < 75) azimuthName = 'coming from the front-right at 45 degrees'
  else if (deg <= 105) azimuthName = 'coming from the right side, pure side-light'
  else if (deg < 165) azimuthName = 'coming from the back-right, creating rim and edge light'
  else if (deg <= 195) azimuthName = 'coming from directly behind the subject, strong backlight and silhouette'
  else if (deg < 255) azimuthName = 'coming from the back-left, creating rim and edge light'
  else if (deg <= 285) azimuthName = 'coming from the left side, pure side-light'
  else azimuthName = 'coming from the front-left at 45 degrees'
  const elevationName = elevation >= 30
    ? ', tilted downward from above'
    : elevation <= -30
      ? ', tilted upward from below'
      : ''
  return `main key light ${azimuthName}${elevationName}`
}

/** 亮度 → 描述（50 为不变，输出空段） */
function buildBrightnessPrompt(brightness: number): string {
  if (brightness >= 75) return 'high-key, bright and well-lit scene, lifted exposure'
  if (brightness <= 25) return 'low-key, dim and moody scene, deep shadows, reduced exposure'
  if (brightness === 50) return ''
  return brightness > 50 ? 'slightly brighter exposure' : 'slightly darker exposure'
}

/** 色相区间 → 英文颜色名 */
const COLOR_HUE_NAMES: Array<{ max: number; name: string }> = [
  { max: 15, name: 'red' },
  { max: 45, name: 'orange' },
  { max: 70, name: 'yellow' },
  { max: 160, name: 'green' },
  { max: 200, name: 'cyan' },
  { max: 255, name: 'blue' },
  { max: 290, name: 'purple' },
  { max: 330, name: 'pink' },
  { max: 361, name: 'red' },
]

/**
 * HEX → 英文颜色名（生图模型对颜色词远比色值敏感）。
 * 按 HSL 色相映射，并按明度补 pale/deep 修饰；低饱和归 grey，极亮/极暗归 white/black。
 */
export function hexToColorName(hex: string): string {
  const groups = hex.trim().match(/^#?([0-9a-fA-F]{6})$/)
  if (!groups) return ''
  const value = parseInt(groups[1], 16)
  const red = ((value >> 16) & 255) / 255
  const green = ((value >> 8) & 255) / 255
  const blue = (value & 255) / 255
  const max = Math.max(red, green, blue)
  const min = Math.min(red, green, blue)
  const lightness = (max + min) / 2
  const delta = max - min
  if (delta === 0) {
    if (lightness > 0.85) return 'white'
    if (lightness < 0.15) return 'black'
    return 'grey'
  }
  const saturation = delta / (1 - Math.abs(2 * lightness - 1))
  if (saturation < 0.08) return 'grey'
  let hue: number
  if (max === red) hue = ((green - blue) / delta) % 6
  else if (max === green) hue = (blue - red) / delta + 2
  else hue = (red - green) / delta + 4
  hue = (hue * 60 + 360) % 360
  const base = COLOR_HUE_NAMES.find(item => hue < item.max)?.name ?? 'red'
  if (lightness > 0.82) return `pale ${base}`
  if (lightness < 0.25) return `deep ${base}`
  return base
}

/** 组装打光提示词：分段逗号拼接，空段过滤 */
export function buildLightingPrompt(options: LightingOptions, smartDesc: string): string {
  const presetPrompt = options.stylePreset
    ? LIGHTING_STYLE_PRESETS.find(p => p.id === options.stylePreset)?.prompt ?? ''
    : ''
  let colorPrompt = ''
  if (options.lightColor && options.lightColor.toLowerCase() !== '#ffffff') {
    const colorName = hexToColorName(options.lightColor)
    colorPrompt = colorName
      ? `key light color temperature tinted toward ${colorName} (${options.lightColor})`
      : `key light color temperature tinted toward ${options.lightColor}`
  }
  const segments = [
    CONSISTENCY_PROMPT,
    presetPrompt,
    options.smartMode ? smartDesc.trim() : '',
    buildLightDirectionPrompt(options.azimuth, options.elevation),
    buildBrightnessPrompt(options.brightness),
    options.rimLight ? 'add clear rim light and edge highlight along the silhouette' : '',
    colorPrompt,
    `[lighting azimuth:${options.azimuth}° elevation:${options.elevation}° brightness:${options.brightness}%${options.rimLight ? ' rim:on' : ''}]`,
  ]
  return segments.map(s => s.trim()).filter(Boolean).join(', ')
}

/** 子节点命名摘要，如"AI 打光：伦勃朗光，亮度 30%，轮廓光" */
export function buildLightingLabel(options: LightingOptions): string {
  const preset = LIGHTING_STYLE_PRESETS.find(p => p.id === options.stylePreset)
  const position = LIGHT_POSITIONS.find(p => p.azimuth === options.azimuth && p.elevation === options.elevation)
  const parts: string[] = []
  if (preset) parts.push(t(preset.labelKey))
  else if (position) parts.push(t('canvas.imageOps.lightKeyLabel', { dir: t(position.labelKey) }))
  else parts.push(t('canvas.imageOps.lightKeyDegrees', { azimuth: options.azimuth, elevation: options.elevation }))
  if (options.brightness !== 50) parts.push(t('canvas.imageOps.lightBrightnessLabel', { value: options.brightness }))
  if (options.rimLight) parts.push(t('canvas.imageOps.lightRimLabel'))
  if (options.lightColor && options.lightColor.toLowerCase() !== '#ffffff') parts.push(t('canvas.imageOps.lightColorLabel', { color: options.lightColor }))
  return t('canvas.imageOps.lightingLabel', { summary: parts.join('，') })
}
