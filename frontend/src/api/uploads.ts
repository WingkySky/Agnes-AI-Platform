/* =====================================================
 * 通用图片上传 API
 * 预设封面等场景，返回可直接访问的 URL
 * ===================================================== */

import client from './client'

/** 上传图片（jpeg/png/webp，≤5MB），返回 { url } */
export function uploadImage(file: File): Promise<{ url: string }> {
  const formData = new FormData()
  formData.append('file', file)
  return client.post('/api/uploads/image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
