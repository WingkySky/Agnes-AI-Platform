/* =====================================================
 * 预览音频引擎（全音频统一调度）
 * - 纯函数：audibleSpans（哪些片段出声+窗口裁剪）、sourceTimeAt/timelineTimeAt
 *   （变速时间映射）、gainBreakpoints（线性包络断点）——vitest 锁死行为
 * - AudioEngine 薄执行层：音频时钟主控（t0 锚定），lookahead 窗口内把
 *   mediabunny 解出的 PCM buffer 依次挂 AudioBufferSourceNode（playbackRate=变速）
 *   + GainNode（setValueAtTime/linearRampToValueAtTime 样本级 fade）
 * - 已知取舍：变速走 varispeed（音高随速度偏移），渲染端 atempo 保音高；
 *   预览与成片在变速片段存在音高差异，待后续批次引入时域拉伸
 * ===================================================== */

import { clipEnd, type EditorClip, type EditorDocument } from './editor-types'
import { clipGainAt } from './editor-audio'
import type { AudioBufferSink, WrappedAudioBuffer } from 'mediabunny'

/** 调度前视窗口（秒） */
export const AUDIO_LOOKAHEAD_S = 2

/** 参与预览声音的片段窗口（音频轨 + 未静音视频自带音频；音画分离源片段已 muted 自动跳过）。
 * 独奏是预览监听态：存在独奏轨时只出独奏轨的声音（成片渲染不读 solo）。 */
export interface AudibleSpan {
  clip: EditorClip
  /** 与窗口相交后的时间线域范围 */
  from: number
  to: number
}

export function audibleSpans(doc: EditorDocument, from: number, to: number): AudibleSpan[] {
  const byId = new Map(doc.tracks.map((tr) => [tr.id, tr]))
  const anySolo = doc.tracks.some((tr) => tr.flags.solo)
  const out: AudibleSpan[] = []
  for (const clip of doc.clips) {
    const track = byId.get(clip.trackId)
    if (!track || track.kind === 'subtitle') continue
    if (track.flags.muted || (anySolo && !track.flags.solo) || clip.props.muted === true) continue
    if (clip.assetId == null) continue
    const spanFrom = Math.max(clip.start, from)
    const spanTo = Math.min(clipEnd(clip), to)
    if (spanTo <= spanFrom) continue
    out.push({ clip, from: spanFrom, to: spanTo })
  }
  return out
}

/** 时间线时刻 → 源内时刻（变速：源内跨度 = 时间线跨度 × speed） */
export function sourceTimeAt(clip: EditorClip, t: number): number {
  return clip.trimStart + (t - clip.start) * (clip.props.speed ?? 1)
}

/** 源内时刻 → 时间线时刻 */
export function timelineTimeAt(clip: EditorClip, srcT: number): number {
  return clip.start + (srcT - clip.trimStart) / (clip.props.speed ?? 1)
}

/** [from,to] 内的增益分段点（含端点）：clipGainAt 分段线性，段内插值精确 */
export function gainBreakpoints(clip: EditorClip, from: number, to: number): { t: number; v: number }[] {
  const times = [from]
  const { fadeIn = 0, fadeOut = 0 } = clip.props
  if (fadeIn > 0) {
    const p = clip.start + fadeIn
    if (p > from && p < to) times.push(p)
  }
  if (fadeOut > 0) {
    const p = clipEnd(clip) - fadeOut
    if (p > from && p < to) times.push(p)
  }
  times.push(to)
  return times.map((t) => ({ t, v: clipGainAt(clip, t) }))
}

// ---------- 执行层 ----------

interface ActiveAudio {
  clip: EditorClip
  gain: GainNode
  sink: AudioBufferSink | null
  iter: AsyncGenerator<WrappedAudioBuffer, void, unknown> | null
  /** 已取到但落在窗口外的 buffer，下轮优先消费 */
  pending: WrappedAudioBuffer | null
  sources: AudioBufferSourceNode[]
  pumping: boolean
  stopping: boolean
}

export class AudioEngine {
  private ctx: AudioContext
  private t0 = 0
  private actives = new Map<string, ActiveAudio>()

  constructor(ctx: AudioContext) {
    this.ctx = ctx
  }

  /** 播放/续播锚定：音频时钟与时间线对齐（seek 后必须重锚） */
  anchor(playhead: number): void {
    this.t0 = this.ctx.currentTime - playhead
  }

  /** 音频时钟投影出的时间线时刻 */
  now(): number {
    return this.ctx.currentTime - this.t0
  }

  private ctxTime(t: number): number {
    return this.t0 + t
  }

  /** 每 rAF 调一次：对齐活跃片段集合并推进 lookahead 调度 */
  tick(
    doc: EditorDocument,
    playhead: number,
    sinkFor: (clip: EditorClip) => Promise<AudioBufferSink | null>,
  ): void {
    const windowEnd = playhead + AUDIO_LOOKAHEAD_S
    const spans = audibleSpans(doc, playhead, windowEnd)
    const keep = new Set(spans.map((s) => s.clip.id))
    for (const [id, a] of this.actives) {
      if (!keep.has(id)) {
        this.disposeActive(a)
        this.actives.delete(id)
      }
    }
    for (const span of spans) {
      let a = this.actives.get(span.clip.id)
      if (a && a.clip !== span.clip) {
        // 文档被编辑过（对象引用变了）：按新片段重建
        this.disposeActive(a)
        this.actives.delete(span.clip.id)
        a = undefined
      }
      if (!a) {
        a = {
          clip: span.clip,
          gain: this.ctx.createGain(),
          sink: null,
          iter: null,
          pending: null,
          sources: [],
          pumping: false,
          stopping: false,
        }
        a.gain.connect(this.ctx.destination)
        this.actives.set(span.clip.id, a)
        void this.initActive(span, a, sinkFor)
      }
    }
    for (const span of spans) {
      const a = this.actives.get(span.clip.id)
      if (a && a.iter && !a.pumping && !a.stopping) void this.pump(span, a, playhead, windowEnd)
    }
  }

  private async initActive(
    span: AudibleSpan,
    a: ActiveAudio,
    sinkFor: (clip: EditorClip) => Promise<AudioBufferSink | null>,
  ): Promise<void> {
    const sink = await sinkFor(span.clip)
    if (a.stopping) return
    if (!sink) return // 无音频轨：静默
    a.iter = sink.buffers(sourceTimeAt(span.clip, span.from))
  }

  private async pump(span: AudibleSpan, a: ActiveAudio, playhead: number, windowEnd: number): Promise<void> {
    if (!a.iter || a.stopping) return
    a.pumping = true
    try {
      while (!a.stopping) {
        const wb = a.pending ?? (await a.iter.next()).value
        a.pending = null
        if (!wb) break // 源耗尽
        const speed = a.clip.props.speed ?? 1
        const ta = timelineTimeAt(a.clip, wb.timestamp)
        const tb = ta + wb.duration / speed
        if (ta >= windowEnd) {
          a.pending = wb
          break
        }
        if (tb > playhead) this.schedule(a, wb, ta, tb, playhead, speed)
        if (tb >= windowEnd) break
      }
    } catch {
      a.stopping = true // 解码失败：静默停该片段（预览层不弹窗）
    } finally {
      a.pumping = false
    }
  }

  private schedule(a: ActiveAudio, wb: WrappedAudioBuffer, ta: number, tb: number, playhead: number, speed: number): void {
    const src = this.ctx.createBufferSource()
    src.buffer = wb.buffer
    src.playbackRate.value = speed
    src.connect(a.gain)
    // 首个 buffer 可能含片段起点之前的样本（包对齐），起播时刻钳到片段起点
    const startT = Math.max(ta, playhead, a.clip.start)
    for (const [i, p] of gainBreakpoints(a.clip, startT, tb).entries()) {
      const at = this.ctxTime(p.t)
      if (i === 0) a.gain.gain.setValueAtTime(p.v, at)
      else a.gain.gain.linearRampToValueAtTime(p.v, at)
    }
    const offset = startT > ta
      ? Math.max(0, Math.min(wb.buffer.duration, sourceTimeAt(a.clip, startT) - wb.timestamp))
      : 0
    src.start(this.ctxTime(startT), offset)
    a.sources.push(src)
    src.onended = () => {
      a.sources = a.sources.filter((s) => s !== src)
      src.disconnect()
    }
  }

  private disposeActive(a: ActiveAudio): void {
    a.stopping = true
    a.pending = null
    for (const s of a.sources) {
      try { s.stop() } catch { /* 未开始时忽略 */ }
      s.disconnect()
    }
    a.sources = []
    if (a.iter) void a.iter.return(undefined)
    a.gain.disconnect()
  }

  /** 暂停/seek/停止：全部 source 停掉，下一次 tick 按新位置重建 */
  stopAll(): void {
    for (const a of this.actives.values()) this.disposeActive(a)
    this.actives.clear()
  }
}
