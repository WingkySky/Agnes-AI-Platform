/* =====================================================
 * Canvas Image Operations — 图像裁剪/分割/旋转/放大工具
 * - 核心能力：统一处理 data URI / blob URL / 本地路径 / 远程 http(s) URL
 * - 远程图片统一通过 /api/proxy/image 走后端代理，绕过浏览器 CORS
 *   以便 canvas 在读取像素（drawImage 后 toDataURL/getImageData）时不报错
 * ===================================================== */

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
 * 将远程 http(s) URL 转换为后端代理 URL，绕过浏览器 CORS 限制
 * - 仅对 http/https 远程 URL 生效
 * - data: URI、blob: URL、同源相对路径（/xxx）原样返回
 * - 代理接口：GET /api/proxy/image?url=<远程 URL>
 */
export function toProxyUrl(source: string): string {
  if (!source) return source
  if (source.startsWith('data:') || source.startsWith('blob:')) return source
  if (source.startsWith('/')) return source
  if (source.startsWith('http://') || source.startsWith('https://')) {
    return `/api/proxy/image?url=${encodeURIComponent(source)}`
  }
  return source
}

/**
 * 将任意图片源（URL / base64 / blob URL）转换为 base64 data URI
 * - 主要用于：① canvas 像素操作（裁剪/放大/蒙版），② 发送给后端 AI 做图生图
 * - 远程 http(s) URL：先通过后端代理 fetch，再转 base64
 * - data: URI：直接返回
 * - blob: URL / 相对路径：fetch 后转 base64
 *
 * 注意：若只是用于 `<img>` 展示或普通 canvas drawImage，
 * 直接用 `toProxyUrl` + `loadImage` 更轻量；本函数会把整图读到内存。
 */
export async function imageToBase64(source: string): Promise<string> {
  if (!source) {
    throw new Error('imageToBase64: source 为空')
  }
  // 已经是 data URI 直接返回
  if (source.startsWith('data:')) return source
  // 远程 http(s) URL：先转代理 URL，再 fetch 读
  // blob URL / 相对路径：直接 fetch
  const fetchUrl = source.startsWith('http://') || source.startsWith('https://')
    ? toProxyUrl(source)
    : source
  try {
    const resp = await fetch(fetchUrl)
    if (!resp.ok) {
      // 代理接口返回 400/502 等错误时，body 是 JSON 错误信息
      // 不要把错误 JSON 当成图片转 base64
      let detail = ''
      try {
        const errBody = await resp.json()
        detail = errBody?.detail || errBody?.message || JSON.stringify(errBody)
      } catch {
        detail = await resp.text().catch(() => '')
      }
      throw new Error(`HTTP ${resp.status}${detail ? `: ${detail}` : ''}`)
    }
    // 检查 content-type 确保是图片（防止代理返回错误页面被当成图片）
    const ct = resp.headers.get('content-type') || ''
    if (ct && !ct.startsWith('image/')) {
      throw new Error(`非图片类型 content-type: ${ct}`)
    }
    const blob = await resp.blob()
    if (blob.size === 0) {
      throw new Error('图片数据为空')
    }
    return await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onloadend = () => resolve(reader.result as string)
      reader.onerror = () => reject(new Error('FileReader 失败'))
      reader.readAsDataURL(blob)
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    throw new Error(`图片转 base64 失败 (${msg})`)
  }
}

/**
 * 与 canvas-generation.ts 中的 toBase64IfNeeded 命名保持一致
 * - 外部代码只需 import { toBase64IfNeeded } from '@/lib/canvas-image-ops' 即可
 */
export async function toBase64IfNeeded(imageUrl: string): Promise<string> {
  return imageToBase64(imageUrl)
}

/**
 * 加载图像（返回 HTMLImageElement）
 * - data URI / blob URL / 相对路径：直接加载
 * - 远程 http(s) URL：通过 toProxyUrl 走后端代理，并设置 crossOrigin
 * - 远程 URL 加载失败时，会先 fetch 探测具体错误原因，给出更明确的错误信息
 */
export async function loadImage(source: string): Promise<HTMLImageElement> {
  if (!source) {
    throw new Error('loadImage: source 为空')
  }

  // 远程 http(s) URL：先通过代理 fetch 探测，再加载到 Image
  // 这样可以在失败时给出更明确的错误（如 502 / 400 / 非图片类型）
  if (source.startsWith('http://') || source.startsWith('https://')) {
    const proxyUrl = toProxyUrl(source)
    let probeError: string | null = null
    try {
      const resp = await fetch(proxyUrl)
      if (!resp.ok) {
        let detail = ''
        try {
          const errBody = await resp.json()
          detail = errBody?.detail || errBody?.message || ''
        } catch { /* ignore */ }
        probeError = `HTTP ${resp.status}${detail ? `: ${detail}` : ''}`
      } else {
        const ct = resp.headers.get('content-type') || ''
        if (ct && !ct.startsWith('image/')) {
          probeError = `非图片类型: ${ct}`
        }
      }
    } catch (err) {
      probeError = err instanceof Error ? err.message : String(err)
    }
    if (probeError) {
      throw new Error(`loadImage: ${probeError}`)
    }
    // 探测通过后，用 Image 加载（已确认代理 URL 可用）
    return new Promise((resolve, reject) => {
      const img = new Image()
      img.crossOrigin = 'anonymous'
      img.onload = () => resolve(img)
      img.onerror = () => reject(new Error('loadImage: Image 标签加载失败（代理探测通过但 img 加载失败）'))
      img.src = proxyUrl
    })
  }

  // 同源相对路径 / data: / blob: — 直接用 Image 加载
  return new Promise((resolve, reject) => {
    const img = new Image()
    if (source.startsWith('/')) {
      img.src = source
    } else {
      img.src = source
    }
    img.onload = () => resolve(img)
    img.onerror = () => {
      const sample = source.length > 80 ? source.slice(0, 80) + '...' : source
      reject(new Error(`loadImage: 图片加载失败 (${sample})`))
    }
  })
}

/** 内部辅助：加载图像源（统一入口） */
function _loadSource(source: string): Promise<HTMLImageElement> {
  return loadImage(source)
}

/** 内部辅助：将 canvas 转为 base64 PNG 字符串 */
function _canvasToBase64(canvas: HTMLCanvasElement): string {
  try {
    return canvas.toDataURL('image/png')
  } catch (err) {
    // 如果这里抛 Tainted canvases 之类的错误，往往是因为图片加载时没走代理
    const msg = err instanceof Error ? err.message : String(err)
    throw new Error(`canvas 导出失败（可能是图片跨域未走代理）：${msg}`)
  }
}

/**
 * 裁剪图像
 * @param source - 图像源
 * @param rect - 裁剪区域
 * @returns base64 PNG
 */
export function cropImage(source: string, rect: Rect): Promise<string> {
  return _loadSource(source).then((img) => {
    const sx = Math.max(0, Math.floor(rect.x))
    const sy = Math.max(0, Math.floor(rect.y))
    const sw = Math.min(img.width - sx, Math.floor(rect.width))
    const sh = Math.min(img.height - sy, Math.floor(rect.height))
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
 * 按行列网格拆分图像
 */
export function splitImageByGrid(source: string, rows: number, cols: number): Promise<string[]> {
  return _loadSource(source).then((img) => {
    if (rows < 1 || cols < 1) {
      throw new Error('splitImageByGrid: rows/cols 必须 >= 1')
    }
    const pieceW = Math.floor(img.width / cols)
    const pieceH = Math.floor(img.height / rows)
    if (pieceW < 1 || pieceH < 1) {
      throw new Error('splitImageByGrid: 图像太小，无法拆分')
    }
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
    return pieces
  })
}

/**
 * 按目标长边放大图像（等比，支持算法选择）
 */
export function upscaleToLongEdge(
  source: string,
  targetLongEdge: number,
  algorithm: 'high' | 'bilinear' | 'nearest' = 'high',
): Promise<string> {
  return _loadSource(source).then((img) => {
    const longEdge = Math.max(img.width, img.height)
    if (targetLongEdge <= longEdge) {
      return _canvasToBase64(_drawToCanvas(img, img.width, img.height, algorithm))
    }
    const scale = targetLongEdge / longEdge
    const targetW = Math.round(img.width * scale)
    const targetH = Math.round(img.height * scale)
    return _canvasToBase64(_drawToCanvas(img, targetW, targetH, algorithm))
  })
}

/** 内部辅助：按指定尺寸和算法绘制到 canvas */
function _drawToCanvas(
  img: HTMLImageElement,
  w: number,
  h: number,
  algorithm: 'high' | 'bilinear' | 'nearest',
): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')!
  if (algorithm === 'nearest') {
    ctx.imageSmoothingEnabled = false
  } else {
    ctx.imageSmoothingEnabled = true
    ctx.imageSmoothingQuality = algorithm === 'high' ? 'high' : 'medium'
  }
  ctx.drawImage(img, 0, 0, w, h)
  return canvas
}

/**
 * 获取图像尺寸
 */
export function getImageSize(source: string): Promise<ImageSize> {
  return _loadSource(source).then((img) => ({
    width: img.width,
    height: img.height,
  }))
}
