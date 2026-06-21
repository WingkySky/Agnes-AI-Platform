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
