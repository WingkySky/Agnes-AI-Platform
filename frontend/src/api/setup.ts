/* =====================================================
 * 首启初始化 API 封装
 * 对应后端 /api/setup/* 接口
 * ===================================================== */

import client from './client'
import type { AuthTokenResponse, SetupBootstrapRequest, SetupBootstrapStatus, SetupStatus } from '@/types'

/** 获取首启引导状态（免登录）：实例是否已存在管理员 */
export function getBootstrapStatus(): Promise<SetupBootstrapStatus> {
  return client.get('/api/setup/bootstrap', { silent: true })
}

/** 创建首个管理员（免登录，仅实例无管理员时可用），成功直接返回登录态 */
export function bootstrapAdmin(params: SetupBootstrapRequest): Promise<AuthTokenResponse> {
  return client.post('/api/setup/bootstrap', params)
}

/** 获取首启初始化状态（需登录） */
export function getSetupStatus(): Promise<SetupStatus> {
  return client.get('/api/setup/status')
}

/** 标记首启初始化完成（仅管理员） */
export function completeSetup(): Promise<{ setup_completed: boolean }> {
  return client.post('/api/setup/complete')
}
