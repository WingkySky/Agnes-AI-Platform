// =====================================================
// 时间线预览调度 composable
// -------------------------------------------------
// 核心能力:
//   1. 维护主时钟（基于 performance.now() 累积，可暂停/继续）
//   2. requestAnimationFrame 循环按 currentTime 调度视频/音频/字幕片段
//   3. 视频 seek 容差控制（避免频繁 seek 卡顿）
//   4. 暴露 play / pause / seek / stop API 供组件调用
//
// 设计原则:
//   - 视频元素全部 muted（避免与独立 audio 叠加）
//   - 音频走独立 <audio> 元素调度
//   - 字幕文本通过响应式变量暴露，由组件渲染 overlay
//   - 不依赖单个 video.currentTime 作为主时钟（多片段切换误差大）
//   - 调度逻辑与 DOM 解耦：组件负责注册/注销 media 元素引用
// =====================================================

import { ref, computed, onUnmounted, type Ref, type ComputedRef } from 'vue'
import type { TimelineClip, SubtitleStyle } from '@/types/project'

interface UseTimelinePreviewOptions {
  clips: Ref<TimelineClip[]> | ComputedRef<TimelineClip[]>
  subtitleStyle: Ref<SubtitleStyle | null> | ComputedRef<SubtitleStyle | null>
  totalDuration: Ref<number> | ComputedRef<number>
}

// seek 容差：小于此差值不 seek，避免频繁 seek 卡顿
const SEEK_TOLERANCE = 0.1

export function useTimelinePreview(options: UseTimelinePreviewOptions) {
  const { clips, subtitleStyle, totalDuration } = options

  // ---------- 响应式状态 ----------
  const isPlaying = ref(false)
  const currentTime = ref(0)
  const activeVideoClipId = ref<number | null>(null)
  const activeAudioClipId = ref<number | null>(null)
  const activeSubtitleText = ref('')
  const activeSubtitleClipId = ref<number | null>(null)

  // ---------- 内部状态 ----------
  // 视频元素池：clipId -> HTMLVideoElement（显示用，由组件注册）
  const videoEls = new Map<number, HTMLVideoElement>()
  // 音频元素池：clipId -> HTMLAudioElement（由组件注册）
  const audioEls = new Map<number, HTMLAudioElement>()

  let rafId: number | null = null
  let startTimeRef = 0 // performance.now() 时间戳，主时钟基准

  // ---------- 计算 ----------
  const videoClips = computed(() =>
    clips.value.filter((c) => c.track_type === 'video' && c.track_index === 0),
  )

  const audioClips = computed(() =>
    clips.value.filter((c) => c.track_type === 'audio' && c.track_index === 0),
  )

  const subtitleClips = computed(() =>
    clips.value.filter((c) => c.track_type === 'subtitle'),
  )

  // ---------- 元素注册 ----------
  function registerVideoEl(clipId: number, el: HTMLVideoElement | null) {
    if (el) {
      videoEls.set(clipId, el)
    } else {
      videoEls.delete(clipId)
    }
  }

  function registerAudioEl(clipId: number, el: HTMLAudioElement | null) {
    if (el) {
      audioEls.set(clipId, el)
    } else {
      audioEls.delete(clipId)
    }
  }

  // ---------- 主时钟调度 ----------
  function tick() {
    if (!isPlaying.value) return

    const now = performance.now()
    currentTime.value = (now - startTimeRef) / 1000

    // 播放结束判定
    const total = totalDuration.value
    if (total > 0 && currentTime.value >= total) {
      currentTime.value = total
      pause()
      return
    }

    // 1. 视频调度
    const activeVideo = findActiveClip(videoClips.value, currentTime.value)
    activeVideoClipId.value = activeVideo?.id ?? null

    videoEls.forEach((el, clipId) => {
      const clip = videoClips.value.find((c) => c.id === clipId)
      if (!clip) return

      if (activeVideo && clipId === activeVideo.id) {
        // 激活当前片段
        el.style.display = ''
        const targetTime = (clip.trim_start || 0) + (currentTime.value - clip.start_time)
        // seek 容差控制
        if (Math.abs(el.currentTime - targetTime) > SEEK_TOLERANCE) {
          try {
            el.currentTime = targetTime
          } catch {
            // seek 失败（如未加载到该位置），忽略
          }
        }
        if (el.paused) {
          el.play().catch(() => {
            // 自动播放策略拦截，忽略（用户手势触发应正常）
          })
        }
      } else {
        // 非激活片段暂停隐藏
        if (!el.paused) el.pause()
        el.style.display = 'none'
      }
    })

    // 2. 音频调度
    const activeAudio = findActiveClip(audioClips.value, currentTime.value)
    activeAudioClipId.value = activeAudio?.id ?? null

    audioEls.forEach((el, clipId) => {
      const clip = audioClips.value.find((c) => c.id === clipId)
      if (!clip) return

      if (activeAudio && clipId === activeAudio.id) {
        const targetTime = (clip.trim_start || 0) + (currentTime.value - clip.start_time)
        if (Math.abs(el.currentTime - targetTime) > SEEK_TOLERANCE) {
          try {
            el.currentTime = targetTime
          } catch {
            // ignore
          }
        }
        if (el.paused) {
          el.play().catch(() => {
            // ignore
          })
        }
      } else {
        if (!el.paused) el.pause()
      }
    })

    // 3. 字幕调度
    const activeSub = findActiveClip(subtitleClips.value, currentTime.value)
    activeSubtitleClipId.value = activeSub?.id ?? null
    activeSubtitleText.value = activeSub?.subtitle_text || ''

    rafId = requestAnimationFrame(tick)
  }

  function findActiveClip(clipsList: TimelineClip[], t: number): TimelineClip | null {
    for (const c of clipsList) {
      if (t >= c.start_time && t < c.start_time + c.duration) {
        return c
      }
    }
    return null
  }

  // ---------- 控制 API ----------
  async function play(): Promise<void> {
    if (isPlaying.value) return
    const total = totalDuration.value
    // 已到结尾时重新从 0 开始
    if (total > 0 && currentTime.value >= total) {
      currentTime.value = 0
    }
    isPlaying.value = true
    startTimeRef = performance.now() - currentTime.value * 1000
    rafId = requestAnimationFrame(tick)
  }

  function pause(): void {
    if (!isPlaying.value) return
    isPlaying.value = false
    if (rafId !== null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
    // 暂停所有 media 元素
    videoEls.forEach((el) => {
      if (!el.paused) el.pause()
    })
    audioEls.forEach((el) => {
      if (!el.paused) el.pause()
    })
  }

  function seek(t: number): void {
    const total = totalDuration.value
    const target = Math.max(0, Math.min(t, total || t))
    currentTime.value = target
    if (isPlaying.value) {
      // 播放中 seek：重置主时钟基准
      startTimeRef = performance.now() - target * 1000
    }
    // 立即调度一次（更新激活状态）
    scheduleOnce()
  }

  function stop(): void {
    pause()
    currentTime.value = 0
    activeVideoClipId.value = null
    activeAudioClipId.value = null
    activeSubtitleText.value = ''
    activeSubtitleClipId.value = null
  }

  function togglePlayPause(): void {
    if (isPlaying.value) {
      pause()
    } else {
      void play()
    }
  }

  // 立即调度一次（用于 seek 后立即更新激活状态，不启动 RAF 循环）
  function scheduleOnce() {
    const wasPlaying = isPlaying.value
    isPlaying.value = true
    tick()
    if (!wasPlaying) {
      isPlaying.value = false
      if (rafId !== null) {
        cancelAnimationFrame(rafId)
        rafId = null
      }
    }
  }

  // ---------- 字幕样式 CSS ----------
  const subtitleStyleCss = computed<Record<string, string>>(() => {
    const s = subtitleStyle.value
    if (!s) {
      return {
        fontFamily: 'Microsoft YaHei',
        fontSize: '24px',
        color: '#FFFFFF',
        textShadow: '0 0 2px #000000, 0 0 2px #000000',
        marginBottom: '40px',
      }
    }
    // text-shadow 模拟 outline（多层投影让描边更清晰）
    const ow = s.outline_width || 2
    const oc = s.outline_color || '#000000'
    const shadow = [
      `0 0 ${ow}px ${oc}`,
      `0 0 ${ow}px ${oc}`,
      `${ow}px 0 ${ow}px ${oc}`,
      `-${ow}px 0 ${ow}px ${oc}`,
      `0 ${ow}px ${ow}px ${oc}`,
      `0 -${ow}px ${ow}px ${oc}`,
    ].join(', ')
    return {
      fontFamily: s.font_family || 'Microsoft YaHei',
      fontSize: `${s.font_size}px`,
      color: s.font_color || '#FFFFFF',
      textShadow: shadow,
      marginBottom: `${s.margin_vertical || 40}px`,
    }
  })

  // ---------- 清理 ----------
  onUnmounted(() => {
    stop()
    videoEls.clear()
    audioEls.clear()
  })

  return {
    // 响应式状态
    isPlaying,
    currentTime,
    activeVideoClipId,
    activeAudioClipId,
    activeSubtitleClipId,
    activeSubtitleText,
    subtitleStyleCss,
    // 元素注册
    registerVideoEl,
    registerAudioEl,
    // 控制 API
    play,
    pause,
    seek,
    stop,
    togglePlayPause,
  }
}
