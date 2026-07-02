/* =====================================================
 * 生成历史记录相关 API 封装
 * ===================================================== */

import client from './client'
import type {
  HistoryListResponse,
  DeleteResponse,
  BatchDeleteResponse,
  ConfigResponse
} from '@/types'

/**
 * 获取历史列表
 * @param params.type   筛选类型：image / video / all（默认）
 * @param params.task_id 按 task_id 精确匹配（用于从积分明细跳转）
 * @param params.page    页码
 * @param params.page_size 每页数量
 */
export function getHistoryList(
  { type = 'all', task_id, page = 1, page_size = 50 }: { type?: string; task_id?: string; page?: number; page_size?: number } = {}
): Promise<HistoryListResponse> {
  return client.get('/api/history', { params: { type, task_id, page, page_size } })
}

/**
 * 删除单条历史记录
 */
export function deleteHistoryRecord(id: number): Promise<DeleteResponse> {
  return client.delete(`/api/history/${id}`)
}

/**
 * 批量删除多条历史记录
 */
export function batchDeleteHistory(ids: number[]): Promise<BatchDeleteResponse> {
  return client.post('/api/history/batch-delete', { ids })
}

/**
 * 获取前端配置（模型列表 / 尺寸选项等）
 */
export function getPlatformConfig(): Promise<ConfigResponse> {
  return client.get('/api/config')
}

// ===== 历史视频后期处理 =====

/** 剪辑操作条目 */
export interface VideoEditOperation {
  type: 'trim' | 'cut'
  start: number
  end: number
}

/** 后期处理请求参数 */
export interface PostProcessParams {
  operation: 'color_grade' | 'video_edit'
  preset?: string
  with_audio_fade?: boolean
  operations?: VideoEditOperation[]
}

/** 后期处理响应 */
export interface PostProcessResponse {
  success: boolean
  source_generation_id: number
  new_generation_id: number
  result_url: string
  operation: string
  credits_consumed: number
}

/**
 * 对单个历史视频做后期处理（调色/剪辑）
 * 复用后端 ColorGradeExecutor / VideoEditExecutor，处理结果作为新记录入库
 */
export function postProcessVideo(
  generationId: number,
  params: PostProcessParams,
): Promise<PostProcessResponse> {
  return client.post(`/api/pipeline/generations/${generationId}/post-process`, params)
}
