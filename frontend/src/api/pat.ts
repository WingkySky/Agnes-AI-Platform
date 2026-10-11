/* =====================================================
 * PAT（个人访问令牌）API 封装
 *
 * 接口：
 *   GET    /api/auth/pat        令牌清单（脱敏）
 *   POST   /api/auth/pat        创建（明文仅此一次返回）
 *   DELETE /api/auth/pat/{id}   吊销（软删，即时生效）
 * ===================================================== */

import client from './client'

export interface PatInfo {
  id: number
  name: string
  permission: 'readonly' | 'full'
  last_used_at: string | null
  revoked_at: string | null
  created_at: string
}

export interface PatCreated extends PatInfo {
  token: string
}

/** 令牌清单（脱敏，无 token 材料） */
export function listPats(): Promise<PatInfo[]> {
  return client.get('/api/auth/pat')
}

/** 创建令牌（明文仅此一次返回，前端引导立即保存） */
export function createPat(name: string, permission: 'readonly' | 'full'): Promise<PatCreated> {
  return client.post('/api/auth/pat', { name, permission })
}

/** 吊销令牌（软删保留记录） */
export function revokePat(id: number): Promise<{ revoked: boolean }> {
  return client.delete(`/api/auth/pat/${id}`)
}
