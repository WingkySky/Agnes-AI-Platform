/* =====================================================
 * 片段素材条数据层测试
 * - 纯函数：桶数/步长钳制、网格索引、峰值重采样
 * - 音波峰值：解码分桶、按 URL 缓存复用、失败负缓存、LRU 淘汰
 * - 缩略图帧：按网格取帧缓存、失败负缓存
 * ===================================================== */

import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../editor-media', () => ({
  createAudioSink: vi.fn(),
  createThumbSink: vi.fn(),
  probeDuration: vi.fn(),
  getImageBitmap: vi.fn(),
  hasWebCodecs: vi.fn(() => true),
}))

import type { AudioBufferSink, CanvasSink } from 'mediabunny'
import {
  bucketCountFor,
  clearStripCaches,
  ensureThumbs,
  getWaveformPeaks,
  gridIndices,
  resamplePeaks,
  thumbKey,
  thumbStep,
  type WavePeaks,
} from '../editor-strips'
import { createAudioSink, createThumbSink, probeDuration } from '../editor-media'
import type { EditorClip } from '../editor-types'

const mockedProbe = vi.mocked(probeDuration)
const mockedAudioSink = vi.mocked(createAudioSink)
const mockedThumbSink = vi.mocked(createThumbSink)

function makeClip(duration: number, trimStart = 0): EditorClip {
  return { id: 'c1', trackId: 't1', assetId: 1, start: 0, duration, trimStart, props: {} }
}

function fakeAudioBuffer(seconds: number, value: number, rate = 1000): AudioBuffer {
  const data = new Float32Array(Math.round(seconds * rate)).fill(value)
  return { duration: seconds, sampleRate: rate, getChannelData: () => data } as unknown as AudioBuffer
}

function fakeAudioSink(chunks: { t: number; seconds: number; value: number }[]): AudioBufferSink {
  return {
    buffers: async function* () {
      for (const c of chunks) {
        yield { timestamp: c.t, duration: c.seconds, buffer: fakeAudioBuffer(c.seconds, c.value) }
      }
    },
  } as unknown as AudioBufferSink
}

function makePeaks(mins: number[], maxs: number[], bucketSec = 1): WavePeaks {
  return { mins: Float32Array.from(mins), maxs: Float32Array.from(maxs), bucketSec }
}

beforeEach(() => {
  vi.clearAllMocks()
  clearStripCaches()
})

describe('纯函数', () => {
  it('bucketCountFor 钳制 256~4096', () => {
    expect(bucketCountFor(0.5)).toBe(256)
    expect(bucketCountFor(10)).toBe(500)
    expect(bucketCountFor(100)).toBe(4096)
  })

  it('thumbStep 每源约 24 帧，0.5~4s 钳制', () => {
    expect(thumbStep(0)).toBe(1)
    expect(thumbStep(12)).toBe(0.5)
    expect(thumbStep(48)).toBe(2)
    expect(thumbStep(120)).toBe(4)
  })

  it('gridIndices 覆盖源跨度（tile 半开区间 [t,t+step) 与跨度相交）', () => {
    expect(gridIndices(0, 10, 2)).toEqual([0, 2, 4, 6, 8])
    expect(gridIndices(2.3, 7.1, 2)).toEqual([2, 4, 6])
    expect(gridIndices(5.5, 5.8, 2)).toEqual([4])
    expect(gridIndices(-1, 1, 1)).toEqual([0])
    expect(gridIndices(1, 1, 1)).toEqual([])
  })

  it('resamplePeaks 列聚合取峰值，空桶计 0', () => {
    const peaks = makePeaks([-1, -0.5, 0, 1], [0.5, 0.25, 0, -1])
    const amps = resamplePeaks(peaks, 0, 4, 4)
    expect([...amps]).toEqual([1, 0.5, 0, 0])
  })

  it('resamplePeaks 子跨度映射与列数无关性', () => {
    const peaks = makePeaks([-1, -0.5, 0, 0], [0.5, 0.25, 0, 0])
    const two = resamplePeaks(peaks, 1, 3, 2)
    expect([...two]).toEqual([0.5, 0])
    const eight = resamplePeaks(peaks, 0, 4, 8)
    expect(eight[0]).toBeCloseTo(1)
    expect(eight[1]).toBeCloseTo(1)
    expect(resamplePeaks(peaks, 3, 1, 4).every((v) => v === 0)).toBe(true)
  })
})

describe('getWaveformPeaks', () => {
  it('解码分桶并按 URL 缓存复用', async () => {
    mockedProbe.mockResolvedValue(4)
    mockedAudioSink.mockResolvedValue(
      fakeAudioSink([
        { t: 0, seconds: 2, value: 0.5 },
        { t: 2, seconds: 2, value: -0.25 },
      ]),
    )
    const peaks = await getWaveformPeaks('u1')
    expect(peaks).not.toBeNull()
    expect(peaks!.mins.length).toBe(bucketCountFor(4))
    expect(peaks!.bucketSec).toBeCloseTo(4 / bucketCountFor(4))
    const amps = resamplePeaks(peaks!, 0, 4, 2)
    expect(amps[0]).toBeCloseTo(0.5)
    expect(amps[1]).toBeCloseTo(0.25)
    await getWaveformPeaks('u1')
    expect(mockedAudioSink).toHaveBeenCalledTimes(1)
  })

  it('失败负缓存不重试', async () => {
    mockedProbe.mockResolvedValue(4)
    mockedAudioSink.mockResolvedValue(null) // 真实 createAudioSink 失败返回 null
    expect(await getWaveformPeaks('u2')).toBeNull()
    await getWaveformPeaks('u2')
    expect(mockedProbe).toHaveBeenCalledTimes(1)
    expect(mockedAudioSink).toHaveBeenCalledTimes(1)
  })

  it('LRU 上限 40 源，淘汰最久未用后按需重算', async () => {
    mockedProbe.mockResolvedValue(1)
    mockedAudioSink.mockImplementation(async () =>
      fakeAudioSink([{ t: 0, seconds: 1, value: 0.1 }]),
    )
    for (let i = 0; i < 40; i++) await getWaveformPeaks(`u${i}`)
    await getWaveformPeaks('u0') // touch → u0 变为最新
    await getWaveformPeaks('new') // 挤出最久未用的 u1
    const calls = mockedAudioSink.mock.calls.length
    await getWaveformPeaks('u1') // 被挤出 → 重算
    expect(mockedAudioSink.mock.calls.length).toBe(calls + 1)
    await getWaveformPeaks('u0') // 未被挤出 → 命中缓存
    expect(mockedAudioSink.mock.calls.length).toBe(calls + 1)
  })
})

describe('ensureThumbs', () => {
  function stubImageBitmap(): void {
    vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 160, height: 90, close() {} }) as unknown as ImageBitmap))
  }

  it('时长未探测完返回 null，就绪后按网格取帧缓存', async () => {
    stubImageBitmap()
    const sink = { getCanvas: vi.fn(async (t: number) => ({ canvas: { width: 160, height: 90 }, timestamp: t, duration: 0.04 })) }
    mockedProbe.mockResolvedValue(8) // step = 0.5
    mockedThumbSink.mockResolvedValue(sink as unknown as CanvasSink)
    const clip = makeClip(2)
    let ready = 0
    expect(ensureThumbs('v1', clip, () => { ready++ })).toBeNull()
    await vi.waitFor(() => expect(ready).toBeGreaterThan(0))
    const handle = ensureThumbs('v1', clip, () => { ready++ })
    expect(handle?.step).toBe(0.5)
    await vi.waitFor(() => expect(handle!.frames.size).toBe(4)) // 网格 [0, 0.5, 1, 1.5]
    expect(handle!.frames.get(thumbKey(0))).not.toBeNull()
    const calls = sink.getCanvas.mock.calls.length
    ensureThumbs('v1', clip, () => undefined) // 全部命中缓存，不再取帧
    expect(sink.getCanvas.mock.calls.length).toBe(calls)
    vi.unstubAllGlobals()
  })

  it('取帧失败负缓存为 null', async () => {
    stubImageBitmap()
    const sink = { getCanvas: vi.fn(async () => { throw new Error('boom') }) }
    mockedProbe.mockResolvedValue(2)
    mockedThumbSink.mockResolvedValue(sink as unknown as CanvasSink)
    const clip = makeClip(1)
    let handle: ReturnType<typeof ensureThumbs> = null
    await vi.waitFor(() => {
      handle = ensureThumbs('v2', clip, () => undefined)
      expect(handle).not.toBeNull()
    })
    await vi.waitFor(() => expect(handle!.frames.size).toBe(2)) // 网格 [0, 0.5]
    expect(handle!.frames.get(thumbKey(0))).toBeNull()
    vi.unstubAllGlobals()
  })
})
