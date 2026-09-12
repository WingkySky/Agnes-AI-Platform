/* =====================================================
 * Agent 附件工具层（UI 无关，纯函数为主）
 *
 * - 图片：超阈值 canvas 重编码 JPEG（白底），小图原样 base64 保透明
 * - 文件：txt/md 等文本直读；PDF（pdfjs-dist 逐页）/ DOCX（mammoth 浏览器构建）提取文本
 * - 画布图片节点 URL → base64（外域走后端 /api/proxy/image 绕 CORS）
 * - 错误以 i18n key 抛出（fileTooLarge/unsupportedType/pdfNoText），面板侧翻译
 * ===================================================== */

// pdfjs worker 以独立资源引入（Vite ?url 打包为静态资源地址；不设 workerSrc 运行时 fake worker 会加载失败）
import pdfWorkerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

/** 附件图片（裸 base64，无 data: 前缀；与内核 ImageContent 类型同形，内核负责映射） */
export interface AgentImageAttachment {
  data: string
  mimeType: string
}

/** 原图直传阈值：≤1MB 且长边 ≤2048 不重编码（保 PNG 透明） */
const SMALL_IMAGE_BYTES = 1024 * 1024
export const IMAGE_MAX_EDGE = 2048
/** 重编码后仍超限则拒绝 */
export const IMAGE_MAX_BYTES = 4 * 1024 * 1024
const TEXT_FILE_MAX_BYTES = 2 * 1024 * 1024
const DOC_FILE_MAX_BYTES = 20 * 1024 * 1024
/** 文件提取文本的最大长度（超出截断） */
export const FILE_TEXT_MAX_CHARS = 20000
/** 单条消息图片附件上限 */
export const MAX_IMAGES_PER_MESSAGE = 4

const TEXT_EXTENSIONS = /\.(txt|md|markdown|json|csv|log|ts|tsx|js|mjs|py|html|css|xml|yml|yaml)$/i
const PDF_EXTENSIONS = /\.pdf$/i
const DOCX_EXTENSIONS = /\.docx$/i

export function isImageFile(file: File): boolean {
  return file.type.startsWith('image/')
}

export function isSupportedFile(file: File): boolean {
  return isTextFile(file) || PDF_EXTENSIONS.test(file.name) || DOCX_EXTENSIONS.test(file.name)
}

/** 附件错误的 i18n key（未知错误统一归为 parseFailed） */
export type AttachmentErrorKey = 'fileTooLarge' | 'unsupportedType' | 'pdfNoText' | 'parseFailed'

export function attachmentErrorKey(e: unknown): AttachmentErrorKey {
  const msg = e instanceof Error ? e.message : String(e)
  if (msg === 'fileTooLarge' || msg === 'unsupportedType' || msg === 'pdfNoText') return msg
  return 'parseFailed'
}

/** dataURL/裸 base64 归一为附件（FileReader 读出带 data: 前缀，机制层要裸 base64） */
function blobToAttachment(blob: Blob, mimeType: string): Promise<AgentImageAttachment> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : ''
      const idx = result.indexOf(',')
      if (idx < 0) {
        reject(new Error('parseFailed'))
        return
      }
      resolve({ data: result.slice(idx + 1), mimeType })
    }
    reader.onerror = () => reject(new Error('parseFailed'))
    reader.readAsDataURL(blob)
  })
}

/** 面板上传/粘贴图片 → 附件：小图原样，超阈值重编码 JPEG q0.85（白底） */
export async function prepareImageFile(file: File): Promise<AgentImageAttachment> {
  let bmp: ImageBitmap
  try {
    bmp = await createImageBitmap(file)
  } catch {
    throw new Error('parseFailed')
  }
  try {
    const longEdge = Math.max(bmp.width, bmp.height)
    if (file.size <= SMALL_IMAGE_BYTES && longEdge <= IMAGE_MAX_EDGE) {
      return await blobToAttachment(file, file.type || 'image/png')
    }
    const scale = longEdge > IMAGE_MAX_EDGE ? IMAGE_MAX_EDGE / longEdge : 1
    const w = Math.max(1, Math.round(bmp.width * scale))
    const h = Math.max(1, Math.round(bmp.height * scale))
    const canvas = document.createElement('canvas')
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('parseFailed')
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, w, h)
    ctx.drawImage(bmp, 0, 0, w, h)
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85))
    if (!blob) throw new Error('parseFailed')
    const att = await blobToAttachment(blob, 'image/jpeg')
    // base64 长度 ≈ 原始字节 4/3，按原始字节比较上限
    if (att.data.length * 0.75 > IMAGE_MAX_BYTES) throw new Error('fileTooLarge')
    return att
  } finally {
    bmp.close()
  }
}

function truncateText(text: string): string {
  return text.length > FILE_TEXT_MAX_CHARS ? text.slice(0, FILE_TEXT_MAX_CHARS) + '\n…（已截断）' : text
}

async function readAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : '')
    reader.onerror = () => reject(new Error('parseFailed'))
    reader.readAsText(file)
  })
}

async function readPdfText(file: File): Promise<string> {
  const pdfjs = await import('pdfjs-dist')
  pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerSrc
  const buf = await file.arrayBuffer()
  const loadingTask = pdfjs.getDocument({ data: buf })
  const doc = await loadingTask.promise
  try {
    const pages: string[] = []
    for (let i = 1; i <= doc.numPages; i++) {
      const page = await doc.getPage(i)
      const content = await page.getTextContent()
      pages.push(content.items.map((it) => ('str' in it && typeof it.str === 'string' ? it.str : '')).join(' '))
    }
    const text = pages.join('\n\n')
    if (!text.trim()) throw new Error('pdfNoText')
    return text
  } finally {
    await loadingTask.destroy()
  }
}

async function readDocxText(file: File): Promise<string> {
  const mammoth = await import('mammoth/mammoth.browser')
  const buf = await file.arrayBuffer()
  const result = await mammoth.extractRawText({ arrayBuffer: buf })
  return result.value
}

/** 面板上传/拖拽文件 → 提取文本（类型分流；错误消息为 i18n key） */
export async function extractFileText(file: File): Promise<{ name: string; text: string }> {
  if (isTextFile(file)) {
    if (file.size > TEXT_FILE_MAX_BYTES) throw new Error('fileTooLarge')
    return { name: file.name, text: truncateText(await readAsText(file)) }
  }
  if (PDF_EXTENSIONS.test(file.name) || file.type === 'application/pdf') {
    if (file.size > DOC_FILE_MAX_BYTES) throw new Error('fileTooLarge')
    return { name: file.name, text: truncateText(await readPdfText(file)) }
  }
  if (DOCX_EXTENSIONS.test(file.name) || file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') {
    if (file.size > DOC_FILE_MAX_BYTES) throw new Error('fileTooLarge')
    return { name: file.name, text: truncateText(await readDocxText(file)) }
  }
  throw new Error('unsupportedType')
}

function isTextFile(file: File): boolean {
  return file.type.startsWith('text/') || TEXT_EXTENSIONS.test(file.name)
}

function isSameOriginUrl(url: string): boolean {
  try {
    return new URL(url, window.location.origin).origin === window.location.origin
  } catch {
    return false
  }
}

/** 画布图片节点 URL → 附件：同域直拉，外域走后端图片代理绕 CORS */
export async function fetchPanelImageBase64(url: string): Promise<AgentImageAttachment> {
  if (!isSameOriginUrl(url)) {
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const origin = typeof window !== 'undefined' ? window.location.origin : ''
    const proxied = `${origin}${base}/api/proxy/image?url=${encodeURIComponent(url)}`
    return fetchAsAttachment(proxied)
  }
  return fetchAsAttachment(url)
}

async function fetchAsAttachment(fetchUrl: string): Promise<AgentImageAttachment> {
  let resp: Response
  try {
    resp = await fetch(fetchUrl)
  } catch {
    throw new Error('parseFailed')
  }
  if (!resp.ok) throw new Error('parseFailed')
  const blob = await resp.blob()
  const mimeType = blob.type.startsWith('image/') ? blob.type : 'image/png'
  return blobToAttachment(blob, mimeType)
}
