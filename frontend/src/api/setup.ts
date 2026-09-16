/* =====================================================
 * 首启初始化 API 封装
 * 对应后端 /api/setup/* 接口
 * ===================================================== */

import client from './client'
import type { SetupStatus } from '@/types'

/** 获取首启初始化状态 */
export function getSetupStatus(): Promise<SetupStatus> {
  return client.get('/api/setup/status')
}

/** 标记首启初始化完成（仅管理员） */
export function completeSetup(): Promise<{ setup_completed: boolean }> {
  return client.post('/api/setup/complete')
}
