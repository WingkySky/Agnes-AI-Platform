/**
 * 视频生成相关 API
 * - 创建异步视频任务
 * - 查询任务状态
 * - 取消任务
 * - 视频流代理
 */

import { get, post, del } from './client'

/**
 * 视频生成请求参数
 */
export interface VideoGenerationRequest {
  prompt: string
  model: string
  mode?: string
  aspect_ratio?: string
  seconds?: number
  num_frames?: number
  frame_rate?: number
  width?: number
  height?: number
  negative_prompt?: string
  image?: string
  images?: string[]
  image_mime_type?: string
  image_mime_types?: string[]
  seed?: number
}

/**
 * 视频任务创建响应
 */
export interface VideoTaskCreatedResponse {
  task_id: string
  video_id: string
  status: string
  prompt: string
  model: string
  num_frames?: number
  frame_rate?: number
  width?: number
  height?: number
  aspect_ratio?: string
  seconds?: number
  mode: string
  credits_consumed: number
  remaining_credits: number
  message?: string
}

/**
 * 视频任务状态响应
 */
export interface VideoStatusResponse {
  task_id: string
  video_id?: string
  status: 'pending' | 'processing' | 'success' | 'failed' | 'unknown'
  progress: number
  video_url?: string
  message?: string
  elapsed_sec?: number
}

/**
 * 创建视频生成任务
 */
export function createVideoTask(params: VideoGenerationRequest): Promise<VideoTaskCreatedResponse> {
  return post<VideoTaskCreatedResponse>('/api/videos', params)
}

/**
 * 查询视频任务状态
 */
export function getVideoStatus(taskId: string): Promise<VideoStatusResponse> {
  return get<VideoStatusResponse>(`/api/videos/${taskId}`)
}

/**
 * 取消视频任务
 */
export function cancelVideoTask(taskId: string): Promise<{ success: boolean; message?: string }> {
  return del<{ success: boolean; message?: string }>(`/api/videos/${taskId}`)
}

export default {
  createVideoTask,
  getVideoStatus,
  cancelVideoTask,
}
