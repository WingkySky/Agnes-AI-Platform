/* =====================================================
 * 视频生成相关 API 封装
 * ===================================================== */

import client from './client'
import type {
  VideoGenerationRequest,
  VideoTaskCreatedResponse,
  VideoStatusResponse
} from '@/types'

/**
 * 创建视频生成任务
 */
export function createVideoTask(params: VideoGenerationRequest): Promise<VideoTaskCreatedResponse> {
  return client.post('/api/videos', params, { silent: true })
}

/**
 * 查询视频任务状态（轮询用）
 */
export function getVideoStatus(taskId: string): Promise<VideoStatusResponse> {
  return client.get(`/api/videos/${taskId}`, { silent: true }) // 轮询失败不弹错误提示
}

/**
 * 中止视频任务
 */
export function cancelVideoTask(taskId: string): Promise<{ success: boolean; task_id: string; status: string; message: string }> {
  return client.delete(`/api/videos/${taskId}`)
}
