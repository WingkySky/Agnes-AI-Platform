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

/** 画布文案 → LLM 拆分 SRT 字幕 */
export function generateCanvasSubtitles(data: { text: string; max_chars?: number }): Promise<CanvasSubtitleResult> {
  return client.post('/api/canvas/subtitle', data)
}

/** 多段视频（+可选配音/字幕）→ 一条成片 */
export function composeCanvasVideos(data: {
  video_urls: string[]
  audio_url?: string | null
  subtitles?: CanvasSubtitleSegment[] | null
  with_subtitle?: boolean
  bgm_id?: string | null
  aspect_ratio?: string
}): Promise<CanvasComposeResult> {
  return client.post('/api/canvas/compose', data)
}
