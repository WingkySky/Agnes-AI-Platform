/* =====================================================
 * 积分明细 API 封装
 * - estimateCost          : 预估本次生成任务需要消耗的积分
 * - listMyTransactions   : 查询当前用户的积分变动明细
 * - listAllTransactions  : [管理员] 查询所有用户的积分变动明细
 * ===================================================== */

import client from './client'

/** 积分预估响应 */
export interface CreditEstimateResponse {
  type: 'image' | 'video'
  mode?: string | null
  cost: number
  balance: number
  sufficient: boolean
}

/** 预估本次生成任务需要消耗的积分 */
export function estimateCost(params: {
  type: 'image' | 'video'
  mode?: string
  size?: string
  seconds?: number
  num_frames?: number
}): Promise<CreditEstimateResponse> {
  return client.get('/api/credits/estimate', { params })
}

/** 积分变动明细项 */
export interface CreditTransactionItem {
  id: number
  user_id: number
  username?: string  // 仅管理员视图返回
  type: 'recharge' | 'consume' | 'refund' | 'adjust'
  amount: number
  balance_after: number
  status: 'pending' | 'confirmed' | 'refunded'
  ref_type?: string | null
  ref_id?: string | null
  description: string
  operator_id?: number | null
  created_at: string
}

/** 积分明细列表响应 */
export interface CreditTransactionListResponse {
  items: CreditTransactionItem[]
  total: number
  page: number
  page_size: number
}

/** 查询当前用户的积分变动明细 */
export function listMyTransactions(params: {
  page?: number
  page_size?: number
  type?: string
}): Promise<CreditTransactionListResponse> {
  return client.get('/api/credits/transactions', { params })
}

/** [管理员] 查询所有用户的积分变动明细 */
export function listAllTransactions(params: {
  page?: number
  page_size?: number
  type?: string
  user_id?: number
}): Promise<CreditTransactionListResponse> {
  return client.get('/api/credits/transactions/all', { params })
}
