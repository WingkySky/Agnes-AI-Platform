/* 附件工具层单测：类型分流、错误归一、文件提取（FileReader stub）、画布图拉取（fetch stub） */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  isImageFile, isSupportedFile, attachmentErrorKey, extractFileText,
  fetchPanelImageBase64, FILE_TEXT_MAX_CHARS,
} from '../attachments'

const stubs = vi.hoisted(() => {
  const state = { textContent: '' }
  class FakeFileReader {
    result: string | null = null
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    readAsDataURL(): void {
      this.result = 'data:image/png;base64,QUJD'
      this.onload?.()
    }
    readAsText(): void {
      this.result = state.textContent
      this.onload?.()
    }
  }
  return { state, FakeFileReader }
})

beforeEach(() => {
  stubs.state.textContent = ''
  vi.stubGlobal('FileReader', stubs.FakeFileReader)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('类型分流', () => {
  it('图片按 MIME 判定，文件按扩展名/类型分流', () => {
    expect(isImageFile(new File([new Uint8Array(1)], 'a.png', { type: 'image/png' }))).toBe(true)
    expect(isImageFile(new File([new Uint8Array(1)], 'a.bin', { type: 'application/octet-stream' }))).toBe(false)
    expect(isSupportedFile(new File([new Uint8Array(1)], 'a.txt', { type: 'text/plain' }))).toBe(true)
    expect(isSupportedFile(new File([new Uint8Array(1)], 'notes.md'))).toBe(true)
    expect(isSupportedFile(new File([new Uint8Array(1)], 'doc.pdf', { type: 'application/pdf' }))).toBe(true)
    expect(isSupportedFile(new File([new Uint8Array(1)], 'doc.docx'))).toBe(true)
    expect(isSupportedFile(new File([new Uint8Array(1)], 'virus.exe'))).toBe(false)
  })
})

describe('attachmentErrorKey', () => {
  it('已知 i18n key 原样返回，未知错误归为 parseFailed', () => {
    expect(attachmentErrorKey(new Error('pdfNoText'))).toBe('pdfNoText')
    expect(attachmentErrorKey(new Error('fileTooLarge'))).toBe('fileTooLarge')
    expect(attachmentErrorKey(new Error('随便什么'))).toBe('parseFailed')
    expect(attachmentErrorKey('字符串错误')).toBe('parseFailed')
  })
})

describe('extractFileText', () => {
  it('txt 直读文本', async () => {
    stubs.state.textContent = '剧本第一幕'
    const r = await extractFileText(new File([new Uint8Array(1)], '剧本.txt', { type: 'text/plain' }))
    expect(r.name).toBe('剧本.txt')
    expect(r.text).toBe('剧本第一幕')
  })

  it('超长文本截断', async () => {
    stubs.state.textContent = 'x'.repeat(FILE_TEXT_MAX_CHARS + 100)
    const r = await extractFileText(new File([new Uint8Array(1)], 'long.md'))
    expect(r.text.length).toBe(FILE_TEXT_MAX_CHARS + 7)
    expect(r.text.endsWith('…（已截断）')).toBe(true)
  })

  it('超大文本文件拒绝', async () => {
    const big = new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'big.txt', { type: 'text/plain' })
    await expect(extractFileText(big)).rejects.toMatchObject({ message: 'fileTooLarge' })
  })

  it('不支持的类型抛 unsupportedType', async () => {
    await expect(extractFileText(new File([new Uint8Array(1)], 'x.exe'))).rejects.toMatchObject({ message: 'unsupportedType' })
  })
})

describe('fetchPanelImageBase64', () => {
  it('外域 URL 走后端代理并把 blob 转 base64 附件', async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL) => new Response(new Blob(['abc'], { type: 'image/png' }), { status: 200, headers: { 'content-type': 'image/png' } }))
    vi.stubGlobal('fetch', fetchMock)
    const att = await fetchPanelImageBase64('https://cdn.example.com/a.png')
    expect(att).toEqual({ data: 'QUJD', mimeType: 'image/png' })
    const calledUrl = fetchMock.mock.calls[0]?.[0]
    expect(typeof calledUrl).toBe('string')
    expect(calledUrl).toContain('/api/proxy/image?url=')
    expect(calledUrl).toContain(encodeURIComponent('https://cdn.example.com/a.png'))
  })

  it('非 200 响应抛错归为 parseFailed', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('no', { status: 502 })))
    await expect(fetchPanelImageBase64('https://cdn.example.com/a.png')).rejects.toMatchObject({ message: 'parseFailed' })
  })
})
