/* =====================================================
 * 作品实体库 API（/api/works/{work_id}/entities、/api/entities）
 * 实体 = 作品级角色/场景/物品事实源；版本内表现图挂统一资产库 asset_id
 * ===================================================== */

import client from './client'

export type EntityKind = 'character' | 'scene' | 'prop'
export type ImageRole = 'design' | 'turnaround' | 'angle'

export interface EntityImage {
  asset_id: number
  role: ImageRole
  url: string | null
}

export interface EntityVersion {
  id: number
  images: EntityImage[]
  is_active: boolean
  created_at: string
}

export interface WorkEntityItem {
  id: number
  work_id: number
  kind: EntityKind
  name: string
  description: string | null
  versions: EntityVersion[]
  active_image_url: string | null
  created_at: string
  updated_at: string
}

export function listWorkEntities(workId: number, kind?: EntityKind): Promise<{ total: number; items: WorkEntityItem[] }> {
  return client.get(`/api/works/${workId}/entities`, { params: kind ? { kind } : {} })
}

export function createWorkEntity(workId: number, data: { kind: EntityKind; name: string; description?: string; asset_id?: number }): Promise<WorkEntityItem> {
  return client.post(`/api/works/${workId}/entities`, data)
}

export function updateWorkEntity(id: number, data: { name?: string; description?: string }): Promise<WorkEntityItem> {
  return client.patch(`/api/entities/${id}`, data)
}

export function deleteWorkEntity(id: number): Promise<null> {
  return client.delete(`/api/entities/${id}`)
}

/** design=新开版本并自动采用；angle/turnaround=追加进当前采用版本 */
export function addEntityVersion(id: number, data: { asset_id: number; role?: ImageRole }): Promise<WorkEntityItem> {
  return client.post(`/api/entities/${id}/versions`, data)
}

export function adoptEntityVersion(id: number, versionId: number): Promise<WorkEntityItem> {
  return client.post(`/api/entities/${id}/adopt`, { version_id: versionId })
}

/** 上传实体表现图原图（复用 /api/uploads/image，jpeg/png/webp ≤5MB）→ { url } */
export function uploadEntityImage(file: File): Promise<{ url: string }> {
  const form = new FormData()
  form.append('file', file)
  return client.post('/api/uploads/image', form)
}
