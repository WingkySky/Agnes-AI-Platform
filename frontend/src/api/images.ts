/* =====================================================
 * 图片生成相关 API 封装
 * - 支持异步任务模式（类似视频生成）
 * - createImageTask      : 创建异步任务，返回 task_id
 * - getImageTaskStatus   : 轮询任务状态
 * - cancelImageTask      : 取消任务
 * - 兼容旧的 createImage / getImageRecord 接口（同步模式，保留兼容）
 * ===================================================== */

import client from './client'
import type {
  ImageGenerationRequest,
  ImageTaskCreatedResponse,
  ImageTaskStatusResponse,
  ImageTaskCancelResponse,
  ImageGenerationResponse,
  ImageRecordResponse
} from '@/types'

/**
 * 创建图片异步生成任务（推荐使用）
 */
export function createImageTask(params: ImageGenerationRequest): Promise<ImageTaskCreatedResponse> {
  return client.post('/api/images/tasks', params, { silent: true })
}

/**
 * 查询图片任务状态（轮询用）
 */
export function getImageTaskStatus(taskId: string): Promise<ImageTaskStatusResponse> {
  return client.get(`/api/images/tasks/${taskId}`, { silent: true })
}

/**
 * 取消图片生成任务
 */
export function cancelImageTask(taskId: string): Promise<ImageTaskCancelResponse> {
  return client.delete(`/api/images/tasks/${taskId}`)
}

/* ============ 以下为兼容旧代码的接口（同步模式） ============ */

/**
 * 同步生成图片（阻塞式，不推荐新代码使用）
 */
export function createImage(params: ImageGenerationRequest): Promise<ImageGenerationResponse> {
  return client.post('/api/images/generations', params)
}

/**
 * 获取单张图片生成记录
 */
export function getImageRecord(id: number): Promise<ImageRecordResponse> {
  return client.get(`/api/images/${id}`)
}
