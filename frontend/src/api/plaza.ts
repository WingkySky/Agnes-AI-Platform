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
  // 预设来源：作品使用了哪个预设
  preset_id?: number | null
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

// ---------- 广场「创作」Tab（来自 assets 表） ----------
export interface PlazaCreation {
  id: number
  kind: 'image' | 'video'
  asset_type: string                                   // character/scene/material/clip/final/prop/brand
  name: string
  description?: string | null
  asset_url?: string | null
  container_type?: string | null
  container_name?: string | null
  likes_count: number
  views_count: number
  author_nickname?: string
  author_avatar_url?: string | null
  created_at?: string
  public_shared_at?: string
  is_mine: boolean
  is_liked: boolean
}

export interface PlazaCreationListResponse {
  total: number
  page: number
  page_size: number
  items: PlazaCreation[]
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
  preset_id?: number
}): Promise<PlazaListResponse> {
  return client.get('/api/plaza/works', { params })
}

/** 获取广场作品详情 */
export function getPlazaWorkDetail(id: number): Promise<PlazaWork> {
  return client.get(`/api/plaza/works/${id}`)
}

/** 点赞作品 */
export function likePlazaWork(id: number): Promise<LikeActionResponse> {
  return client.post(`/api/plaza/works/${id}/like`)
}

/** 取消点赞 */
export function unlikePlazaWork(id: number): Promise<LikeActionResponse> {
  return client.delete(`/api/plaza/works/${id}/like`)
}

// ---------- 广场「创作」Tab API ----------

/** 获取广场公开创作资产列表 */
export function getPlazaCreations(params: {
  asset_type?: string
  kind?: 'all' | 'image' | 'video'
  sort?: 'latest' | 'popular'
  page?: number
  page_size?: number
}): Promise<PlazaCreationListResponse> {
  return client.get('/api/plaza/creations', { params })
}

/** 获取广场创作资产详情 */
export function getPlazaCreationDetail(id: number): Promise<PlazaCreation> {
  return client.get(`/api/plaza/creations/${id}`)
}

/** 点赞创作 */
export function likePlazaCreation(id: number): Promise<LikeActionResponse> {
  return client.post(`/api/plaza/creations/${id}/like`)
}

/** 取消点赞创作 */
export function unlikePlazaCreation(id: number): Promise<LikeActionResponse> {
  return client.delete(`/api/plaza/creations/${id}/like`)
}

/** 单条切换分享状态 */
export function updateShareStatus(id: number, isPublic: boolean): Promise<ShareStatusResponse> {
  return client.patch(`/api/history/${id}/share`, { is_public: isPublic })
}

/** 批量设置分享状态 */
export function batchUpdateShareStatus(ids: number[], isPublic: boolean): Promise<BatchShareResponse> {
  return client.patch('/api/history/batch-share', { ids, is_public: isPublic })
}
