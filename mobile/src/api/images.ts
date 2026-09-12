/**
 * 图片生成相关 API
 * - 创建异步图片任务
 * - 查询任务状态
 * - 取消任务
 */

import { get, post, del } from './client'

/**
 * 图片生成请求参数
 */
export interface ImageGenerationRequest {
  prompt: string
  model: string
  size?: string
  aspect_ratio?: string
  response_format?: string
  is_image_to_image?: boolean
  all_reference_images?: string[]
  mask?: string
}

/**
 * 图片任务创建响应
 */
export interface ImageTaskCreatedResponse {
  task_id: string
  id: string
  status: string
  prompt: string
  model: string
  size: string
  credits_consumed: number
  remaining_credits: number
  created_at: string
  message?: string
}

/**
 * 图片任务状态响应
 */
export interface ImageTaskStatusResponse {
  task_id: string
  status: 'pending' | 'processing' | 'success' | 'failed' | 'unknown'
  progress: number
  result_url?: string
  url?: string
  credits_consumed?: number
  elapsed_sec?: number
  message?: string
}

/**
 * 图片任务取消响应
 */
export interface ImageTaskCancelResponse {
  success: boolean
  task_id: string
  status: string
  message?: string
}

/**
 * 创建图片异步生成任务（推荐使用）
 */
export function createImageTask(params: ImageGenerationRequest): Promise<ImageTaskCreatedResponse> {
  return post<ImageTaskCreatedResponse>('/api/images/tasks', params)
}

/**
 * 查询图片任务状态（轮询用）
 */
export function getImageTaskStatus(taskId: string): Promise<ImageTaskStatusResponse> {
  return get<ImageTaskStatusResponse>(`/api/images/tasks/${taskId}`)
}

/**
 * 取消图片生成任务
 */
export function cancelImageTask(taskId: string): Promise<ImageTaskCancelResponse> {
  return del<ImageTaskCancelResponse>(`/api/images/tasks/${taskId}`)
}

export default {
  createImageTask,
  getImageTaskStatus,
  cancelImageTask,
}
