/* =====================================================
 * 存储配额 API —— 用户自查用量 / 管理员概览
 * ===================================================== */

import client from './client'

export interface StorageUsage {
  total_used: number      // 字节
  total_quota: number | null  // null = 不限制
  daily_used: number
  daily_quota: number | null
}

export interface AdminStorageOverview {
  total_used: number
  default_quota: number | null
  top_users: Array<{ user_id: number; used: number; files: number }>
}

export function getStorageUsage(): Promise<StorageUsage> {
  return client.get('/api/storage/usage')
}

export function getAdminStorageOverview(limit = 10): Promise<AdminStorageOverview> {
  return client.get('/api/admin/storage/overview', { params: { limit } })
}

/** 字节 → 人性化 MB/GB 文案（展示用） */
export function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${Math.max(0, Math.round(bytes / 1024))} KB`
}
