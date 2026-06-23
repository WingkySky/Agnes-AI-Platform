/* =====================================================
 * 广场（Plaza）API 封装
 * - 获取广场公开作品列表 / 详情
 * - 点赞 / 取消点赞 / 批量查询点赞状态
 * - 单条 / 批量切换分享状态
 * ===================================================== */

import client from './client'

// ---------- 类型定义 ----------
export interface PlazaWork {
  id: number
  type: 'image' | 'video'
  prompt: string
  model?: string
  params?: Record<string, any>
  mode?: string
  result_url?: string
  likes_count: number
  views_count: number
  author_nickname?: string
  author_avatar_url?: string | null
  created_at?: string
  public_shared_at?: string
  is_mine: boolean
  is_liked: boolean
}

export interface PlazaListResponse {
  total: number
  page: number
  page_size: number
  items: PlazaWork[]
}

export interface LikeActionResponse {
  liked: boolean
  likes_count: number
}

export interface LikeStatusResponse {
  liked_ids: number[]
}

export interface ShareStatusResponse {
  success: boolean
  id: number
  is_public: boolean
  message: string
}

export interface BatchShareResponse {
  success: boolean
  updated_count: number
  failed_ids: number[]
  message: string
}

// ---------- API 函数 ----------

/** 获取广场作品列表 */
export function getPlazaWorks(params: {
  type?: string
  sort?: 'latest' | 'popular'
  page?: number
  page_size?: number
}): Promise<PlazaListResponse> {
  return client.get('/api/plaza/works', { params }) as any
}

/** 获取广场作品详情 */
export function getPlazaWorkDetail(id: number): Promise<PlazaWork> {
  return client.get(`/api/plaza/works/${id}`) as any
}

/** 点赞作品 */
export function likePlazaWork(id: number): Promise<LikeActionResponse> {
  return client.post(`/api/plaza/works/${id}/like`) as any
}

/** 取消点赞 */
export function unlikePlazaWork(id: number): Promise<LikeActionResponse> {
  return client.delete(`/api/plaza/works/${id}/like`) as any
}

/** 批量查询点赞状态 */
export function getLikeStatus(ids: number[]): Promise<LikeStatusResponse> {
  return client.get('/api/plaza/likes/status', {
    params: { ids: ids.join(',') },
  }) as any
}

/** 单条切换分享状态 */
export function updateShareStatus(id: number, isPublic: boolean): Promise<ShareStatusResponse> {
  return client.patch(`/api/history/${id}/share`, { is_public: isPublic }) as any
}

/** 批量设置分享状态 */
export function batchUpdateShareStatus(ids: number[], isPublic: boolean): Promise<BatchShareResponse> {
  return client.patch('/api/history/batch-share', { ids, is_public: isPublic }) as any
}
