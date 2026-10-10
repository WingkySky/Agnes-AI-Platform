/* 画布视频悬停预览单例：新预览停旧、stopPreview 仅对当前预览生效、stopActivePreview 清场 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { startPreview, stopPreview, stopActivePreview } from '@/lib/canvas-video-preview'

/** 最小 HTMLVideoElement 桩：只实现模块触达的成员 */
function fakeVideo(): HTMLVideoElement {
  const el = {
    muted: false,
    currentTime: 5,
    paused: true,
    play: vi.fn(async () => {}),
    pause: vi.fn(),
  }
  return el as unknown as HTMLVideoElement
}

beforeEach(() => {
  stopActivePreview()
})

describe('canvas-video-preview 单例互斥', () => {
  it('startPreview：静音+归零+播放；切到新元素时旧元素暂停复位', () => {
    const a = fakeVideo()
    const b = fakeVideo()
    expect(startPreview(a)).toBe(true)
    expect(a.muted).toBe(true)
    expect(a.currentTime).toBe(0)
    expect(a.play).toHaveBeenCalled()

    startPreview(b)
    expect(a.pause).toHaveBeenCalled()
    expect(a.currentTime).toBe(0)
    expect(b.play).toHaveBeenCalled()
  })

  it('stopPreview：仅当前预览元素生效，非当前元素不动', () => {
    const a = fakeVideo()
    const b = fakeVideo()
    startPreview(a)

    stopPreview(b)
    expect(b.pause).not.toHaveBeenCalled()

    stopPreview(a)
    expect(a.pause).toHaveBeenCalled()
    expect(a.currentTime).toBe(0)
    // 预览接管前的 muted 原值被恢复（避免预览后用户点原生播放键变静音）
    expect(a.muted).toBe(false)

    // 已停后重复 stop 不再动它
    a.currentTime = 3
    stopPreview(a)
    expect(a.currentTime).toBe(3)
  })

  it('startPreview 恢复原静音态：元素原本 muted 时 stop 后仍保持 muted=true', () => {
    const a = fakeVideo()
    a.muted = true
    startPreview(a)
    stopPreview(a)
    expect(a.muted).toBe(true)
  })

  it('stopActivePreview：清场当前预览；无预览时安全', () => {
    const a = fakeVideo()
    startPreview(a)
    stopActivePreview()
    expect(a.pause).toHaveBeenCalled()
    expect(() => stopActivePreview()).not.toThrow()
  })

  it('play() 被浏览器策略拒绝：静默回停（不抛出）', async () => {
    const a = fakeVideo()
    a.play = vi.fn(async () => Promise.reject(new Error('NotAllowed')))
    expect(() => startPreview(a)).not.toThrow()
    await new Promise((r) => setTimeout(r, 0))
    expect(a.pause).toHaveBeenCalled()
  })
})
