/* =====================================================
 * 无限画布三节点 API（tts / subtitle / compose）
 * 对应后端 /api/canvas/*（无状态，按节点 content 传参，不建表）
 * ===================================================== */

import client from './client'

/** 字幕片段（与后端 CanvasSubtitleSegment 对齐） */
export interface CanvasSubtitleSegment {
  start_time: number
  duration: number
  text: string
}

export interface CanvasTtsResult {
  audio_url: string
  duration_ms?: number | null
}

export interface CanvasSubtitleResult {
  srt: string
  segments: CanvasSubtitleSegment[]
  total_duration: number
}

export interface CanvasComposeResult {
  video_url: string
  duration_ms?: number | null
}

/** 画布文本 → TTS 配音 */
export function generateCanvasTts(data: { text: string; voice?: string; speed?: number }): Promise<CanvasTtsResult> {
  return client.post('/api/canvas/tts', data)
}

/** TTS 音色库（内置音色清单） */
export interface CanvasVoice {
  voice_id: string
  name: string
  gender: string
  suitable_for: string
}

export interface CanvasBgm {
  id: string
  name: string
  mood: string
  duration: number
  available: boolean
}

/** 音色库 / BGM 曲库原始拉取 */
function getCanvasVoices(): Promise<{ voices: CanvasVoice[] }> {
  return client.get('/api/canvas/voices')
}

function getCanvasBgms(): Promise<{ bgms: CanvasBgm[]; moods: string[] }> {
  return client.get('/api/canvas/bgms')
}

let _voicesCache: Promise<{ voices: CanvasVoice[] }> | null = null
/** 音色库（模块级缓存，节点间共享一次拉取） */
export function getCanvasVoicesCached(): Promise<{ voices: CanvasVoice[] }> {
  _voicesCache ??= getCanvasVoices().catch((e: unknown) => { _voicesCache = null; throw e })
  return _voicesCache
}

let _bgmsCache: Promise<{ bgms: CanvasBgm[]; moods: string[] }> | null = null
/** BGM 曲库（模块级缓存，节点间共享一次拉取） */
export function getCanvasBgmsCached(): Promise<{ bgms: CanvasBgm[]; moods: string[] }> {
  _bgmsCache ??= getCanvasBgms().catch((e: unknown) => { _bgmsCache = null; throw e })
  return _bgmsCache
}

/** 画布文案 → SRT 字幕（audio_url 提供时服务端 whisper 转写真实时间戳，失败回退 LLM 拆分） */
export function generateCanvasSubtitles(data: { text: string; max_chars?: number; prompt?: string; audio_url?: string }): Promise<CanvasSubtitleResult> {
  return client.post('/api/canvas/subtitle', data)
}

/** 多段视频（+可选多段配音/字幕/BGM/转场）→ 一条成片 */
export function composeCanvasVideos(data: {
  video_urls: string[]
  audios?: string[] | null
  subtitles?: CanvasSubtitleSegment[] | null
  with_subtitle?: boolean
  bgm_id?: string | null
  aspect_ratio?: string
  transition?: string
}): Promise<CanvasComposeResult> {
  return client.post('/api/canvas/compose', data)
}
