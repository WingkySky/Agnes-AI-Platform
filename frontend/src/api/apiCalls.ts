/* =====================================================
 * 上游调用记账 API 封装（管理员，/api/admin/api-calls）
 * ===================================================== */

import client from './client'

export interface ApiCallRecord {
  id: number
  user_id: number | null
  provider_id: number | null
  provider_name: string | null
  model: string | null
  call_type: string | null
  endpoint: string | null
  status: string | null
  error_category: string | null
  error_message: string | null
  request_id: string | null
  latency_ms: number | null
  tokens_in: number | null
  tokens_out: number | null
  estimated_credits: number | null
  created_at: string | null
}

export interface ApiCallListParams {
  page?: number
  page_size?: number
  provider_id?: number
  model?: string
  call_type?: string
  status?: string
  error_category?: string
  since?: string
  before?: string
}

export interface ApiCallListResponse {
  total: number
  page: number
  page_size: number
  calls: ApiCallRecord[]
}

export interface ApiCallSummary {
  days: number
  total: number
  failed: number
  failure_rate: number
  daily: Array<{ date: string; status: string; count: number }>
  by_category: Array<{ category: string; count: number }>
  by_provider: Record<string, { success: number; failed: number }>
  by_model: Record<string, { success: number; failed: number }>
}

/** 查询上游调用日志（分页筛选） */
export function listApiCalls(params: ApiCallListParams): Promise<ApiCallListResponse> {
  return client.get('/api/admin/api-calls', { params })
}

/** 聚合摘要（近 N 天，按日×类目×渠道） */
export function getApiCallsSummary(days = 7): Promise<ApiCallSummary> {
  return client.get('/api/admin/api-calls/summary', { params: { days } })
}
