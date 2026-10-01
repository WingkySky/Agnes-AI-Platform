/* =====================================================
 * canvas-lighting-preview — 打光预览渲染
 * - renderLitImage：把光照参数叠加到图片像素上（方向性明暗/曝光/光色温染）
 * - drawLitSubject：渲染 + 绘制 + 轮廓光晕（背光勾边）
 * - drawLightSphereControl：光源方向球控件（网格/光晕/光源点/带打光模拟的主体）
 * - drawLightingSample：风格预设效果图（灰调球体+地面采样场景 × 预设采样光照）
 * 仅做展示渲染，不读取画布像素（非同源图片 tainted 也不影响显示）
 * ===================================================== */

import type { LightingRenderParams } from './canvas-lighting'

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value))
}

/** 亮度滑杆（0~100，50 不变）→ 曝光叠加透明度 */
function exposureOverlay(brightness: number): { darken: number; lighten: number } {
  if (brightness >= 50) return { darken: 0, lighten: (brightness - 50) / 100 * 0.5 }
  return { darken: (50 - brightness) / 100 * 0.75, lighten: 0 }
}

/**
 * 把光照叠加层画到 ctx 上（假设内容已画好）：
 * 曝光（亮度滑杆）→ 方向性明暗 → 光色温染。
 * 调用方负责把合成模式恢复为 source-over。
 */
function applyLightingOverlay(ctx: CanvasRenderingContext2D, width: number, height: number, params: LightingRenderParams): void {
  const azimuthRad = (params.azimuth * Math.PI) / 180
  const elevationRad = (params.elevation * Math.PI) / 180
  const lightX = Math.sin(azimuthRad)
  const lightY = -Math.sin(elevationRad)
  const facing = Math.cos(azimuthRad)

  ctx.globalCompositeOperation = 'source-atop'

  // 曝光（亮度滑杆）
  const exposure = exposureOverlay(params.brightness)
  if (exposure.darken > 0) {
    ctx.fillStyle = `rgba(0,0,0,${exposure.darken})`
    ctx.fillRect(0, 0, width, height)
  }
  if (exposure.lighten > 0) {
    ctx.fillStyle = `rgba(255,255,255,${exposure.lighten})`
    ctx.fillRect(0, 0, width, height)
  }

  // 方向性明暗：受光侧提亮、背光侧压暗；背光越强整体越暗（剪影感）
  const highlightAlpha = clamp01(0.34 * Math.max(0, facing))
  const shadowAlpha = clamp01(0.55 * Math.max(0.3, 1 - Math.max(0, facing)))
  const span = 0.9
  const gradient = ctx.createLinearGradient(
    width / 2 + lightX * width / 2 * span,
    height / 2 + lightY * height / 2 * span,
    width / 2 - lightX * width / 2 * span,
    height / 2 - lightY * height / 2 * span,
  )
  gradient.addColorStop(0, `rgba(255,252,240,${highlightAlpha})`)
  gradient.addColorStop(0.5, 'rgba(0,0,0,0)')
  gradient.addColorStop(1, `rgba(4,6,14,${shadowAlpha})`)
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, width, height)

  // 光色温染（非白光时）
  if (params.lightColor && params.lightColor.toLowerCase() !== '#ffffff') {
    ctx.globalCompositeOperation = 'soft-light'
    ctx.globalAlpha = 0.45
    ctx.fillStyle = params.lightColor
    ctx.fillRect(0, 0, width, height)
    ctx.globalAlpha = 1
  }

  ctx.globalCompositeOperation = 'source-over'
}

function sourceSize(source: HTMLImageElement | HTMLCanvasElement): { width: number; height: number } {
  if (source instanceof HTMLImageElement) {
    return { width: source.naturalWidth || source.width, height: source.naturalHeight || source.height }
  }
  return { width: source.width, height: source.height }
}

/**
 * 把打光参数渲染到图片上（离屏 canvas，拉伸铺满）。
 * 叠加层用 source-atop 合成，只作用于图片自身像素。
 */
export function renderLitImage(source: HTMLImageElement | HTMLCanvasElement, width: number, height: number, params: LightingRenderParams): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(width))
  canvas.height = Math.max(1, Math.round(height))
  const ctx = canvas.getContext('2d')
  if (!ctx) return canvas
  ctx.drawImage(source, 0, 0, canvas.width, canvas.height)
  applyLightingOverlay(ctx, canvas.width, canvas.height, params)
  return canvas
}

/** 打光渲染（cover 裁剪铺满：居中裁掉超边，不变形），用于任意比例原图的缩略图 */
export function renderLitImageCover(source: HTMLImageElement | HTMLCanvasElement, width: number, height: number, params: LightingRenderParams): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(width))
  canvas.height = Math.max(1, Math.round(height))
  const ctx = canvas.getContext('2d')
  if (!ctx) return canvas
  const size = sourceSize(source)
  if (size.width > 0 && size.height > 0) {
    const scale = Math.max(canvas.width / size.width, canvas.height / size.height)
    const drawWidth = size.width * scale
    const drawHeight = size.height * scale
    ctx.drawImage(source, (canvas.width - drawWidth) / 2, (canvas.height - drawHeight) / 2, drawWidth, drawHeight)
  }
  applyLightingOverlay(ctx, canvas.width, canvas.height, params)
  return canvas
}

/** 轮廓光颜色：非白光用光色，白光用暖白 */
function rimColor(params: LightingRenderParams): string {
  if (params.lightColor && params.lightColor.toLowerCase() !== '#ffffff') return params.lightColor
  return 'rgba(255,244,222,0.9)'
}

/**
 * 轮廓光晕：把主体图形画到画布外、只让投影落在画布内，
 * 光晕沿背光方向偏移（shadowOffset 不受变换矩阵影响，因此可用大偏移技巧）。
 */
function drawRimHalo(ctx: CanvasRenderingContext2D, lit: HTMLCanvasElement, x: number, y: number, params: LightingRenderParams): void {
  const azimuthRad = (params.azimuth * Math.PI) / 180
  const elevationRad = (params.elevation * Math.PI) / 180
  const offsetX = -Math.sin(azimuthRad) * 6
  const offsetY = Math.sin(elevationRad) * 6
  ctx.save()
  ctx.globalCompositeOperation = 'lighter'
  ctx.shadowColor = rimColor(params)
  ctx.shadowBlur = 12
  ctx.shadowOffsetX = 10000 + offsetX
  ctx.shadowOffsetY = offsetY
  ctx.drawImage(lit, x - 10000, y)
  ctx.restore()
}

/** 主体占位剪影（图片缺失时仍可预览光照方向） */
function drawSubjectPlaceholder(ctx: CanvasRenderingContext2D, x: number, y: number, width: number, height: number): void {
  ctx.save()
  ctx.fillStyle = 'rgba(255,255,255,0.07)'
  ctx.strokeStyle = 'rgba(255,255,255,0.18)'
  ctx.lineWidth = 1
  const cx = x + width / 2
  ctx.beginPath()
  ctx.arc(cx, y + height * 0.28, width * 0.14, 0, Math.PI * 2)
  ctx.fill()
  ctx.stroke()
  ctx.beginPath()
  ctx.moveTo(cx - width * 0.26, y + height * 0.96)
  ctx.quadraticCurveTo(cx, y + height * 0.4, cx + width * 0.26, y + height * 0.96)
  ctx.closePath()
  ctx.fill()
  ctx.stroke()
  ctx.restore()
}

/**
 * 绘制带打光模拟的主体：无图时画占位剪影；有图时离屏渲染光照后贴回，
 * 轮廓光开启时叠加背光光晕后重绘本体（光晕只留在轮廓外圈，不雾化画面）。
 */
export function drawLitSubject(
  ctx: CanvasRenderingContext2D,
  source: HTMLImageElement | HTMLCanvasElement | null,
  x: number, y: number, width: number, height: number,
  params: LightingRenderParams,
  sourceReady = true,
): void {
  if (!source || !sourceReady) {
    drawSubjectPlaceholder(ctx, x, y, width, height)
    return
  }
  const lit = renderLitImage(source, width, height, params)
  ctx.drawImage(lit, x, y)
  if (params.rimLight) {
    drawRimHalo(ctx, lit, x, y, params)
    ctx.drawImage(lit, x, y)
  }
}

export type LightViewMode = 'perspective' | 'front'

export interface LightSphereState {
  options: LightingRenderParams
  viewMode: LightViewMode
  image: HTMLImageElement | HTMLCanvasElement | null
  imageReady: boolean
}

/** 光源方向球控件：暗底球体 + 经纬网格 + 打光模拟主体 + 光源光晕点 */
export function drawLightSphereControl(ctx: CanvasRenderingContext2D, size: number, state: LightSphereState): void {
  const { options, viewMode, image, imageReady } = state
  const cx = size / 2
  const cy = size / 2
  const radius = size / 2 - 4

  ctx.clearRect(0, 0, size, size)
  ctx.beginPath()
  ctx.arc(cx, cy, radius, 0, Math.PI * 2)
  ctx.fillStyle = '#111'
  ctx.fill()
  ctx.strokeStyle = 'rgba(255,255,255,0.2)'
  ctx.lineWidth = 1
  ctx.stroke()

  ctx.save()
  ctx.beginPath()
  ctx.arc(cx, cy, radius, 0, Math.PI * 2)
  ctx.clip()

  const azimuthRad = (options.azimuth * Math.PI) / 180
  const elevationRad = (options.elevation * Math.PI) / 180
  const lightX = viewMode === 'front'
    ? cx + radius * Math.sin(azimuthRad) * 0.85
    : cx + radius * Math.sin(azimuthRad) * Math.cos(elevationRad)
  const lightY = viewMode === 'front'
    ? cy - radius * Math.sin(elevationRad) * 0.85
    : cy - radius * Math.sin(elevationRad)

  // 光源环境光晕
  const glow = ctx.createRadialGradient(lightX, lightY, 0, lightX, lightY, radius * 1.4)
  glow.addColorStop(0, 'rgba(255,255,240,0.55)')
  glow.addColorStop(0.35, 'rgba(255,230,180,0.18)')
  glow.addColorStop(0.7, 'rgba(255,200,100,0.05)')
  glow.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.fillStyle = glow
  ctx.fillRect(0, 0, size, size)

  // 经纬网格：正面为直线网格，透视为经纬椭圆
  ctx.strokeStyle = 'rgba(255,255,255,0.07)'
  ctx.lineWidth = 0.7
  if (viewMode === 'front') {
    for (let index = -2; index <= 2; index++) {
      const offset = index * (radius / 3)
      ctx.beginPath()
      ctx.moveTo(cx + offset, cy - radius)
      ctx.lineTo(cx + offset, cy + radius)
      ctx.stroke()
      ctx.beginPath()
      ctx.moveTo(cx - radius, cy + offset)
      ctx.lineTo(cx + radius, cy + offset)
      ctx.stroke()
    }
  } else {
    for (let latitude = -75; latitude <= 75; latitude += 15) {
      const latRad = (latitude * Math.PI) / 180
      const ringRadius = radius * Math.cos(latRad)
      ctx.beginPath()
      ctx.ellipse(cx, cy - radius * Math.sin(latRad), ringRadius, ringRadius * 0.22, 0, 0, Math.PI * 2)
      ctx.stroke()
    }
    for (let index = 0; index < 8; index++) {
      const angle = (index * Math.PI) / 4
      ctx.beginPath()
      ctx.ellipse(cx, cy, radius * Math.abs(Math.cos(angle)), radius, 0, 0, Math.PI * 2)
      ctx.stroke()
    }
  }

  // 主体：带打光模拟的原图（或占位剪影）
  const maxWidth = radius * 0.92
  const maxHeight = radius * 0.96
  if (image && imageReady) {
    const naturalWidth = image instanceof HTMLImageElement ? (image.naturalWidth || image.width) : image.width
    const naturalHeight = image instanceof HTMLImageElement ? (image.naturalHeight || image.height) : image.height
    const aspectRatio = naturalWidth > 0 && naturalHeight > 0 ? naturalWidth / naturalHeight : 2 / 3
    const drawWidth = Math.min(maxWidth, maxHeight * aspectRatio)
    const drawHeight = Math.min(maxHeight, maxWidth / aspectRatio)
    drawLitSubject(ctx, image, cx - drawWidth / 2, cy - drawHeight / 2, drawWidth, drawHeight, options, true)
  } else {
    drawSubjectPlaceholder(ctx, cx - maxWidth / 2, cy - maxHeight / 2, maxWidth, maxHeight)
  }

  ctx.restore()

  // 光源点
  const dot = ctx.createRadialGradient(lightX, lightY, 0, lightX, lightY, 14)
  dot.addColorStop(0, 'rgba(255,245,200,0.95)')
  dot.addColorStop(0.4, 'rgba(255,220,120,0.5)')
  dot.addColorStop(1, 'rgba(255,200,50,0)')
  ctx.beginPath()
  ctx.fillStyle = dot
  ctx.arc(lightX, lightY, 14, 0, Math.PI * 2)
  ctx.fill()
  ctx.beginPath()
  ctx.arc(lightX, lightY, 5, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(255,255,255,0.95)'
  ctx.fill()
}

/** 采样底图缓存（同尺寸复用） */
const sampleBaseCache = new Map<string, HTMLCanvasElement>()

/** 灰调采样场景：背景墙 + 地面 + 主体球 + 接触阴影（供预设效果图打光） */
function getSampleBase(width: number, height: number): HTMLCanvasElement {
  const key = `${width}x${height}`
  const cached = sampleBaseCache.get(key)
  if (cached) return cached

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) return canvas

  const wall = ctx.createLinearGradient(0, 0, 0, height)
  wall.addColorStop(0, '#262a33')
  wall.addColorStop(1, '#101218')
  ctx.fillStyle = wall
  ctx.fillRect(0, 0, width, height)

  const groundY = height * 0.74
  const ground = ctx.createLinearGradient(0, groundY, 0, height)
  ground.addColorStop(0, '#3c4048')
  ground.addColorStop(1, '#17191f')
  ctx.fillStyle = ground
  ctx.fillRect(0, groundY, width, height - groundY)

  const radius = Math.min(width, height) * 0.3
  const cx = width / 2
  const cy = groundY - radius * 0.85
  const ball = ctx.createRadialGradient(cx - radius * 0.35, cy - radius * 0.35, radius * 0.1, cx, cy, radius)
  ball.addColorStop(0, '#c7ccd6')
  ball.addColorStop(0.55, '#7d838f')
  ball.addColorStop(1, '#3f444e')
  ctx.fillStyle = ball
  ctx.beginPath()
  ctx.arc(cx, cy, radius, 0, Math.PI * 2)
  ctx.fill()

  ctx.fillStyle = 'rgba(0,0,0,0.35)'
  ctx.beginPath()
  ctx.ellipse(cx, groundY + (height - groundY) * 0.18, radius * 0.9, radius * 0.16, 0, 0, Math.PI * 2)
  ctx.fill()

  sampleBaseCache.set(key, canvas)
  return canvas
}

/** 风格预设效果图：优先用当前原图（cover 裁剪 × 预设采样光照），无图时用灰调采样场景兜底；最后叠预设氛围色 */
export function drawLightingSample(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  preset: { color: string; sampleLight: LightingRenderParams },
  source: HTMLImageElement | HTMLCanvasElement | null = null,
  sourceReady = false,
): void {
  ctx.clearRect(0, 0, width, height)
  if (source && sourceReady) {
    const lit = renderLitImageCover(source, width, height, preset.sampleLight)
    ctx.drawImage(lit, 0, 0)
  } else {
    const base = getSampleBase(Math.round(width), Math.round(height))
    drawLitSubject(ctx, base, 0, 0, width, height, preset.sampleLight, true)
  }

  ctx.save()
  ctx.globalCompositeOperation = 'soft-light'
  ctx.globalAlpha = 0.4
  ctx.fillStyle = preset.color
  ctx.fillRect(0, 0, width, height)
  ctx.restore()
}
