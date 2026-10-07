/* =====================================================
 * 变速预览流式拉伸（WSOLA，@soundtouchjs/core，MPL-2.0）
 * - 与渲染端 atempo 语义对齐：tempo 时域拉伸保音高（替代 varispeed 变调）
 * - 每个活跃变速片段一个 ClipStretcher：源块（源域）进 → 拉伸块（时间线域）出；
 *   输出流锚定首块的时间线时刻 t0，之后按累计输出帧数线性推进（rate=1 可直接调度）
 * - 交错双声道处理：单声道复制成双声道，>2 声道取前两声道（预览近似）
 * - 源耗尽后灌零冲出 WSOLA 尾窗；多余静音落在片段内容之外，无害
 * ===================================================== */

import { Stretch } from '@soundtouchjs/core'

/** 最小结构化输入（真实 AudioBuffer / 测试桩都满足） */
export interface StretcherInputBuffer {
  readonly length: number
  readonly numberOfChannels: number
  getChannelData(channel: number): Float32Array
}

export interface StretcherInput {
  buffer: StretcherInputBuffer
}

/** 拉伸输出块（时间线域） */
export interface StretchedChunk {
  /** 交错双声道样本 */
  data: Float32Array
  /** 帧数（data.length / 2） */
  frames: number
  /** 块起点的时间线时刻（秒） */
  t0: number
  /** 采样率 */
  sampleRate: number
}

const FEED_CHUNK = 8192
/** 冲尾静音时长（秒）——覆盖 WSOLA 序列窗（50~125ms）留余量 */
const FLUSH_SEC = 0.3
const FLUSH_IDLE_LIMIT = 8

export class ClipStretcher {
  private readonly stretch: Stretch
  private readonly sampleRate: number
  private readonly t0: number
  /** 已消费输出帧数（拉伸域累计） */
  private outFrames = 0
  private flushed = false
  private pending: Float32Array[] = []
  private pendingFrames = 0

  /**
   * @param tempo 变速倍率（≠1）
   * @param sampleRate 源采样率
   * @param t0 首个输入块起点的时间线时刻（秒）
   */
  constructor(tempo: number, sampleRate: number, t0: number) {
    if (!(tempo > 0) || tempo === 1) throw new Error('ClipStretcher 需要 ≠1 的正变速')
    this.sampleRate = sampleRate
    this.t0 = t0
    this.stretch = new Stretch({ sampleRate, createBuffers: true })
    this.stretch.tempo = tempo
  }

  /** 喂入一个源块 → 本块产出的拉伸输出（WSOLA 内部缓冲未满时可能为 null） */
  push(input: StretcherInput): StretchedChunk | null {
    const buf = input.buffer
    const frames = buf.length
    const inter = new Float32Array(frames * 2)
    const l = buf.getChannelData(0)
    const r = buf.numberOfChannels > 1 ? buf.getChannelData(1) : l
    for (let i = 0; i < frames; i++) {
      inter[i * 2] = l[i]!
      inter[i * 2 + 1] = r[i]!
    }
    let inPos = 0
    while (inPos < frames) {
      const n = Math.min(FEED_CHUNK, frames - inPos)
      this.stretch.inputBuffer!.putSamples(inter, inPos, n)
      this.stretch.process()
      inPos += n
      this.drain()
    }
    return this.emit()
  }

  /** 源耗尽后灌零冲出尾窗（一次性；之后返回 null） */
  flush(): StretchedChunk | null {
    if (this.flushed) return null
    this.flushed = true
    const zeroFrames = Math.ceil(this.sampleRate * FLUSH_SEC)
    const zero = new Float32Array(zeroFrames * 2)
    let zPos = 0
    let idle = 0
    while (zPos < zeroFrames || idle < FLUSH_IDLE_LIMIT) {
      if (zPos < zeroFrames) {
        const n = Math.min(FEED_CHUNK, zeroFrames - zPos)
        this.stretch.inputBuffer!.putSamples(zero, zPos, n)
        zPos += n
      }
      this.stretch.process()
      idle = this.drain() === 0 ? idle + 1 : 0
    }
    return this.emit()
  }

  private drain(): number {
    let n = 0
    while (this.stretch.outputBuffer!.frameCount > 0) {
      const a = this.stretch.outputBuffer!.frameCount
      const out = new Float32Array(a * 2)
      this.stretch.outputBuffer!.extract(out, 0, a)
      this.stretch.outputBuffer!.receive(a)
      this.pending.push(out)
      this.pendingFrames += a
      n += a
    }
    return n
  }

  private emit(): StretchedChunk | null {
    if (!this.pendingFrames) return null
    const data = new Float32Array(this.pendingFrames * 2)
    let pos = 0
    for (const part of this.pending) {
      data.set(part, pos)
      pos += part.length
    }
    const chunk: StretchedChunk = {
      data,
      frames: this.pendingFrames,
      t0: this.t0 + this.outFrames / this.sampleRate,
      sampleRate: this.sampleRate,
    }
    this.outFrames += this.pendingFrames
    this.pending = []
    this.pendingFrames = 0
    return chunk
  }
}
