/* =====================================================
 * 首启初始化 Store
 * 职责：
 *   - 免登录引导判定：拉取 GET /api/setup/bootstrap 并缓存 admin_exists，
 *     实例无管理员时（bootstrapPending）守卫将所有路由强制送入向导
 *   - 登录后拉取一次 /api/setup/status 并缓存（路由守卫用）
 *   - 提供 shouldIntercept 判定：管理员待配 Provider 且未完成向导
 *   - 向导完成 / 配置 Provider 后本地同步状态
 *
 * 用法（router 守卫）：
 *   if (!userStore.isAuthenticated && await setupStore.isBootstrapPending()) next({ name: 'setup' })
 *   if (userStore.isAuthenticated && await setupStore.shouldIntercept()) next({ name: 'setup' })
 * ===================================================== */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getBootstrapStatus,
  getSetupStatus,
  completeSetup as apiCompleteSetup,
} from '@/api/setup'
import type { SetupStatus } from '@/types'

export const useSetupStore = defineStore('setup', () => {
  // ================ state ================
  const status = ref<SetupStatus | null>(null)
  /** null=未拉取；true/false=实例是否已有管理员 */
  const adminExists = ref<boolean | null>(null)

  // ================ actions ================

  /** 拉取初始化状态（已加载过则跳过；force 用于重新同步） */
  async function fetchStatus(force = false): Promise<void> {
    if (status.value && !force) return
    status.value = await getSetupStatus()
  }

  /**
   * 免登录引导判定：实例尚无管理员时所有路由强制进向导。
   * 每会话只拉取一次并缓存；拉取失败不拦截（避免网络异常锁死在向导外）
   */
  async function isBootstrapPending(): Promise<boolean> {
    if (adminExists.value === null) {
      try {
        adminExists.value = (await getBootstrapStatus()).admin_exists
      } catch {
        return false
      }
    }
    return adminExists.value === false
  }

  /**
   * 守卫判定（登录态）：是否应拦截到 /setup。
   * - provider_pending && !setup_completed：管理员未配 Provider 且未完成向导
   * 拉取失败（网络异常等）不拦截，避免把用户锁死在向导外
   */
  async function shouldIntercept(): Promise<boolean> {
    try {
      await fetchStatus()
    } catch {
      return false
    }
    const s = status.value
    if (!s) return false
    return s.provider_pending && !s.setup_completed
  }

  /** 创建 Provider 成功后同步本地状态 */
  function markProviderConfigured() {
    if (status.value) status.value.provider_pending = false
  }

  /** 向导完成：写实例级标记并同步本地状态 */
  async function complete() {
    await apiCompleteSetup()
    if (status.value) status.value.setup_completed = true
  }

  /** 登出 / 创建管理员后重置（adminExists 一并清空，下次导航重新拉取） */
  function reset() {
    status.value = null
    adminExists.value = null
  }

  return { status, adminExists, fetchStatus, isBootstrapPending, shouldIntercept, markProviderConfigured, complete, reset }
})
