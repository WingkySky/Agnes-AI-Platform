/* Canvas Image Operations — 图像裁剪/分割/旋转/放大工具 */

/** 裁剪区域 */
interface Rect {
  x: number
  y: number
  width: number
  height: number
}

/** 图像尺寸 */
interface ImageSize {
  width: number
  height: number
}

/**
 * 将远程图片 URL 转为后端代理 URL，绕过浏览器 CORS 限制
 * - 仅对 http/https 远程 URL 生效
 * - data: URI（base64）和 blob: URL 原样返回
 * - 代理接口：GET /api/proxy/image?url=<远程 URL>
 */
function toProxyUrl(source: string): string {
  if (!source) return source
  // data: / blob: URI 无需代理
  if (source.startsWith('data:') || source.startsWith('blob:')) return source
  // 同源 URL（相对路径或 localhost）无需代理
  if (source.startsWith('/')) return source
  // 远程 http/https URL → 走后端代理
  if (source.startsWith('http://') || source.startsWith('https://')) {
    return `/api/proxy/image?url=${encodeURIComponent(source)}`
  }
  return source
}

/**
 * 加载图像
 * @param source - 图像 URL 或 base64 data URL
 * @returns Promise<HTMLImageElement>
 */
export function loadImage(source: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    if (!source) {
      reject(new Error('loadImage: source 为空'))
      return
    }
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('loadImage: 图像加载失败'))
    // 远程 URL 走后端代理，绕过 CORS（canvas 像素操作需要 crossOrigin + CORS 头）
    img.src = toProxyUrl(source)
  })
}

/**
 * 内部辅助：加载图像源（统一入口）
 */
function _loadSource(source: string): Promise<HTMLImageElement> {
  return loadImage(source)
}

/**
 * 内部辅助：将 canvas 转为 base64 PNG 字符串
 */
function _canvasToBase64(canvas: HTMLCanvasElement): string {
  return canvas.toDataURL('image/png')
}

/**
 * 裁剪图像
 * @param source - 图像源
 * @param rect - 裁剪区域
 * @returns base64 PNG
 */
export function cropImage(source: string, { x, y, width, height }: Rect): Promise<string> {
  return _loadSource(source).then((img) => {
    const sx = Math.max(0, Math.floor(x))
    const sy = Math.max(0, Math.floor(y))
    const sw = Math.min(img.width - sx, Math.floor(width))
    const sh = Math.min(img.height - sy, Math.floor(height))
    if (sw <= 0 || sh <= 0) {
      throw new Error('cropImage: 裁剪区域无效')
    }
    const canvas = document.createElement('canvas')
    canvas.width = sw
    canvas.height = sh
    const ctx = canvas.getContext('2d')!
    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh)
    return _canvasToBase64(canvas)
  })
}

/**
 * 将图像等分成 N 份（默认 4 份，2x2 网格）
 * @param source - 图像源
 * @param count - 等分数量（默认 4）
 * @returns base64 PNG 数组
 */
export function splitImage(source: string, count: number = 4): Promise<string[]> {
  return _loadSource(source).then((img) => {
    if (count < 1) {
      throw new Error('splitImage: count 必须 >= 1')
    }
    const n = Math.max(1, Math.round(Math.sqrt(count)))
    const cols = n
    const rows = Math.ceil(count / n)
    const pieceW = Math.floor(img.width / cols)
    const pieceH = Math.floor(img.height / rows)
    const pieces: string[] = []
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const sx = c * pieceW
        const sy = r * pieceH
        const sw = c === cols - 1 ? img.width - sx : pieceW
        const sh = r === rows - 1 ? img.height - sy : pieceH
        const canvas = document.createElement('canvas')
        canvas.width = sw
        canvas.height = sh
        const ctx = canvas.getContext('2d')!
        ctx.drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh)
        pieces.push(_canvasToBase64(canvas))
      }
    }
    return pieces.slice(0, count)
  })
}

/**
 * 旋转图像（只支持 90/180/270 度）
 * @param source - 图像源
 * @param degrees - 90 / 180 / 270
 * @returns base64 PNG
 */
export function rotateImage(source: string, degrees: number = 90): Promise<string> {
  return _loadSource(source).then((img) => {
    const d = ((degrees % 360) + 360) % 360
    if (d !== 90 && d !== 180 && d !== 270 && d !== 0) {
      throw new Error('rotateImage: 只支持 90/180/270 度')
    }
    const canvas = document.createElement('canvas')
    const isVertical = d === 90 || d === 270
    canvas.width = isVertical ? img.height : img.width
    canvas.height = isVertical ? img.width : img.height
    const ctx = canvas.getContext('2d')!
    ctx.save()
    if (d === 90) {
      ctx.translate(canvas.width, 0)
      ctx.rotate(Math.PI / 2)
    } else if (d === 180) {
      ctx.translate(canvas.width, canvas.height)
      ctx.rotate(Math.PI)
    } else if (d === 270) {
      ctx.translate(0, canvas.height)
      ctx.rotate(-Math.PI / 2)
    }
    ctx.drawImage(img, 0, 0)
    ctx.restore()
    return _canvasToBase64(canvas)
  })
}

/**
 * 放大图像（等比）
 * @param source - 图像源
 * @param scale - 放大倍数（1~4）
 * @returns base64 PNG
 */
export function upscaleImage(source: string, scale: number = 2): Promise<string> {
  return _loadSource(source).then((img) => {
    if (scale < 1 || scale > 4) {
      throw new Error('upscaleImage: scale 必须在 1~4 之间')
    }
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(img.width * scale)
    canvas.height = Math.round(img.height * scale)
    const ctx = canvas.getContext('2d')!
    ctx.imageSmoothingEnabled = true
    ctx.imageSmoothingQuality = 'high'
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    return _canvasToBase64(canvas)
  })
}

/**
 * 获取图像尺寸
 * @param source - 图像源
 * @returns 图像宽高
 */
export function getImageSize(source: string): Promise<ImageSize> {
  return _loadSource(source).then((img) => ({
    width: img.width,
    height: img.height,
  }))
}
