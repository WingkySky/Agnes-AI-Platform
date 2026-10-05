/* =====================================================
 * 预览解码池测试（mediabunny mock）
 * - probeMediaDuration 三级探测分支（WebCodecs 有无）
 * - Input 池：按 URL 缓存复用、LRU 上限淘汰
 * - 图片位图负缓存
 * ===================================================== */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mb = vi.hoisted(() => {
  const inputs: { url: string; disposed: boolean; duration: number }[] = []
  return { inputs }
})

vi.mock('mediabunny', () => ({
  ALL_FORMATS: [],
  UrlSource: class {
    constructor(public url: string) {}
  },
  CanvasSink: class {},
  AudioBufferSink: class {},
  Input: class {
    url: string
    disposed = false
    duration: number
    constructor(opts: { source: { url: string } }) {
      this.url = opts.source.url
      this.duration = 40 + (this.url.length % 7)
      mb.inputs.push(this)
    }
    async getPrimaryVideoTrack() {
      return null
    }
    async getPrimaryAudioTrack() {
      return null
    }
    async getDurationFromMetadata() {
      if (this.url.includes('broken')) throw new Error('bad container')
      return this.disposed ? 0 : this.duration
    }
    async computeDuration() {
      return this.duration
    }
    dispose() {
      this.disposed = true
    }
  },
}))

import {
  clearMediaPool,
  getMediaTracks,
  getImageBitmap,
  probeDuration,
  probeMediaDuration,
} from '@/lib/editor-media'

beforeEach(() => {
  clearMediaPool()
  mb.inputs.length = 0
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('probeMediaDuration 三级探测', () => {
  it('无 WebCodecs（node 默认）：直接走元素探测', async () => {
    const elementProbe = vi.fn(async () => 12)
    expect(await probeMediaDuration('https://a/x.mp4', elementProbe)).toBe(12)
    expect(elementProbe).toHaveBeenCalledOnce()
  })

  it('有 WebCodecs：mediabunny 元数据时长优先，元素探测不调用', async () => {
    vi.stubGlobal('VideoDecoder', class {})
    vi.stubGlobal('AudioDecoder', class {})
    const elementProbe = vi.fn(async () => 12)
    const duration = await probeMediaDuration('https://a/meta.mp4', elementProbe)
    expect(duration).toBeGreaterThan(0)
    expect(elementProbe).not.toHaveBeenCalled()
  })

  it('有 WebCodecs 但容器探测失败：回退元素探测', async () => {
    vi.stubGlobal('VideoDecoder', class {})
    vi.stubGlobal('AudioDecoder', class {})
    const elementProbe = vi.fn(async () => 7)
    expect(await probeMediaDuration('https://bad/broken.mp4', elementProbe)).toBe(7)
    expect(elementProbe).toHaveBeenCalledOnce()
  })

  it('probeDuration 直连：成功取容器时长，坏容器返回 0', async () => {
    expect(await probeDuration('https://a/ok.mp4')).toBeGreaterThan(0)
    expect(await probeDuration('https://bad/broken.mp4')).toBe(0)
  })
})

describe('Input 池', () => {
  it('同 URL 复用一个 Input', async () => {
    await getMediaTracks('https://a/same.mp4')
    await getMediaTracks('https://a/same.mp4')
    expect(mb.inputs.filter((i) => i.url === 'https://a/same.mp4')).toHaveLength(1)
  })

  it('超出上限 LRU 淘汰最早未用', async () => {
    for (let i = 0; i < 9; i++) await getMediaTracks(`https://a/evict-${i}.mp4`)
    expect(mb.inputs.find((i) => i.url === 'https://a/evict-0.mp4')?.disposed).toBe(true)
    expect(mb.inputs.find((i) => i.url === 'https://a/evict-8.mp4')?.disposed).toBe(false)
  })

  it('淘汰后重新访问会重建', async () => {
    for (let i = 0; i < 9; i++) await getMediaTracks(`https://a/re-${i}.mp4`)
    const countBefore = mb.inputs.length
    await getMediaTracks('https://a/re-0.mp4')
    expect(mb.inputs.length).toBe(countBefore + 1)
  })
})

describe('图片位图缓存', () => {
  it('同 URL 只 fetch 一次（含失败负缓存）', async () => {
    const fetchMock = vi.fn(async () => { throw new Error('404') })
    vi.stubGlobal('fetch', fetchMock)
    await getImageBitmap('https://a/img.png')
    await getImageBitmap('https://a/img.png')
    expect(fetchMock).toHaveBeenCalledOnce()
  })
})
