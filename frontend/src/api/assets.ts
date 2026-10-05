/* =====================================================
 * 统一资产层 API（/api/assets）
 * 全平台媒体唯一身份：assets.id；画布节点/剪辑片段只持有引用
 * ===================================================== */

import client from './client'

/** 统一资产行 */
export interface UnifiedAsset {
  id: number
  type: string
  name: string
  description: string | null
  visual_description: string | null
  reference_images: string[]
  media_type: string
  asset_url: string
  thumb_url: string | null
  storage_key?: string | null
  source: string | null
  work_id: number | null
  is_public: boolean
  moderation_status: string
  use_count: number
  container_type: string | null
  container_id: string | null
  container_name: string | null
  created_at: string | null
  updated_at: string | null
}

/** 画布/上传素材建资产行（画布素材 uid 退役入库通道） */
export function createAsset(data: { url: string; media_type: string; name?: string; work_id?: number }): Promise<UnifiedAsset> {
  return client.post('/api/assets', data)
}

/** 本人资产列表（统一入口：类型/来源/作品/关键词筛选） */
export function listAssets(params: {
  media_type?: string
  source?: string
  work_id?: number
  keyword?: string
  page?: number
  page_size?: number
}): Promise<{ total: number; page: number; page_size: number; items: UnifiedAsset[] }> {
  return client.get('/api/assets', { params })
}

/** 存量补课（管理员）：资产行字段回填 + 历史成功生成批量入库，幂等 */
export function backfillAssets(limit = 500): Promise<{
  rows: { processed: number; migrated: number; remaining: number }
  generations: { processed: number; created: number; remaining: number }
}> {
  return client.post('/api/assets/backfill', null, { params: { limit } })
}
