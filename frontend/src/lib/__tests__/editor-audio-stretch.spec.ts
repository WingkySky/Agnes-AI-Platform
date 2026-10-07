/* =====================================================
 * 变速预览流式拉伸测试（真实 @soundtouchjs/core，node 可跑）
 * ===================================================== */

import { describe, expect, it } from 'vitest'

import { ClipStretcher } from '@/lib/editor-audio-stretch'

const SR = 44100

function sineBuffer(frames: number, channels = 1): StretcherInputLike {
  const l = new Float32Array(frames)
  for (let i = 0; i < frames; i++) l[i] = Math.sin((2 * Math.PI * 440 * i) / SR)
  const r = channels > 1 ? Float32Array.from(l) : l
  return {
    length: frames,
    numberOfChannels: channels,
    getChannelData: (i: number) => (i === 0 ? l : r),
  }
}

interface StretcherInputLike {
  length: number
  numberOfChannels: number
  getChannelData(channel: number): Float32Array
}

describe('ClipStretcher', () => {
  it('tempo=1 拒绝（直通路径无需管道）', () => {
    expect(() => new ClipStretcher(1, SR, 0)).toThrow()
    expect(() => new ClipStretcher(0, SR, 0)).toThrow()
  })

  it('tempo=2：输出时长≈输入一半，锚点 t0 生效', () => {
    const st = new ClipStretcher(2, SR, 7.5)
    const frames = SR * 2 // 2s 源 → 期望 ~1s 输出
    const chunk = st.push({ buffer: sineBuffer(frames) })
    expect(chunk).not.toBeNull()
    expect(chunk!.t0).toBeCloseTo(7.5)
    const flush = st.flush()
    const total = (chunk!.frames + (flush?.frames ?? 0)) / SR
    expect(total).toBeGreaterThan(0.95)
    expect(total).toBeLessThan(1.15)
  })

  it('tempo=0.5：输出时长≈输入两倍', () => {
    const st = new ClipStretcher(0.5, SR, 0)
    const frames = SR
    const chunk = st.push({ buffer: sineBuffer(frames) })
    const flush = st.flush()
    const total = (chunk!.frames + (flush?.frames ?? 0)) / SR
    expect(total).toBeGreaterThan(1.9)
    expect(total).toBeLessThan(2.4)
  })

  it('多块推进：t0 按累计输出线性推进（时间线域连续）', () => {
    const st = new ClipStretcher(2, SR, 3)
    const blockFrames = Math.floor(SR * 0.5)
    const first = st.push({ buffer: sineBuffer(blockFrames) })
    const second = st.push({ buffer: sineBuffer(blockFrames) })
    expect(first).not.toBeNull()
    expect(second).not.toBeNull()
    const expectedSecondT0 = first!.t0 + first!.frames / SR
    expect(second!.t0).toBeCloseTo(expectedSecondT0, 6)
    // 1s 源内容（2 块 0.5s）→ 拉伸输出合计 ~0.5s
    const flush = st.flush()
    const total = (first!.frames + second!.frames + (flush?.frames ?? 0)) / SR
    expect(total).toBeGreaterThan(0.45)
    expect(total).toBeLessThan(0.65)
  })

  it('单声道复制成双声道输出；flush 只生效一次', () => {
    const st = new ClipStretcher(2, SR, 0)
    const chunk = st.push({ buffer: sineBuffer(SR, 1) })
    expect(chunk).not.toBeNull()
    // 交错数据 L=R（单声道复制）
    let same = true
    for (let i = 0; i < 100; i++) {
      if (chunk!.data[i * 2] !== chunk!.data[i * 2 + 1]) same = false
    }
    expect(same).toBe(true)
    const flush1 = st.flush()
    const flush2 = st.flush()
    expect(flush2).toBeNull()
    // 冲尾块锚点在内容之后
    if (flush1) expect(flush1.t0).toBeCloseTo(chunk!.t0 + chunk!.frames / SR, 6)
  })
})
