/* =====================================================
 * 作品（轻容器）API（/api/works）
 * 作品 = 创作顶层容器：聚合集画布（canvas_workspaces.work_id）、剪辑工程与实体库
 * ===================================================== */

import client from './client'

export interface WorkItem {
  id: number
  title: string
  cover_url: string | null
  description: string | null
  created_at: string
  updated_at: string
}

export function listWorks(): Promise<{ total: number; items: WorkItem[] }> {
  return client.get('/api/works')
}

export function getWork(id: number): Promise<WorkItem> {
  return client.get(`/api/works/${id}`)
}

export function createWork(data: { title: string; description?: string; cover_url?: string }): Promise<WorkItem> {
  return client.post('/api/works', data)
}

export function updateWork(id: number, data: { title?: string; description?: string; cover_url?: string }): Promise<WorkItem> {
  return client.patch(`/api/works/${id}`, data)
}

/** 上传作品封面图片（复用 /api/uploads/image，jpeg/png/webp ≤5MB）→ { url } */
export function uploadWorkCover(file: File): Promise<{ url: string }> {
  const form = new FormData()
  form.append('file', file)
  return client.post('/api/uploads/image', form)
}

export function deleteWork(id: number): Promise<null> {
  return client.delete(`/api/works/${id}`)
}
