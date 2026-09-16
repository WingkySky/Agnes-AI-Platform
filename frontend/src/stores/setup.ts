/* =====================================================
 * 首启初始化 Store
 * 职责：
 *   - 登录后拉取一次 /api/setup/status 并缓存（路由守卫用）
 *   - 提供 shouldIntercept 判定：待改密 或 （管理员待配 Provider 且未完成向导）
 *   - 向导完成 / 改密成功 / 配置 Provider 后本地同步状态
 *
 * 用法（router 守卫）：
 *   if (await setupStore.shouldIntercept()) next({ name: 'setup' })
 * ===================================================== */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getSetupStatus, completeSetup as apiCompleteSetup } from '@/api/setup'
import type { SetupStatus } from '@/types'

export const useSetupStore = defineStore('setup', () => {
  // ================ state ================
  const status = ref<SetupStatus | null>(null)

  // ================ actions ================

  /** 拉取初始化状态（已加载过则跳过；force 用于重新同步） */
  async function fetchStatus(force = false): Promise<void> {
    if (status.value && !force) return
    status.value = await getSetupStatus()
  }

  /**
   * 守卫判定：是否应拦截到 /setup。
   * - password_pending：后端安全语义，改密前始终拦截
   * - provider_pending && !setup_completed：管理员未配 Provider 且未完成过向导
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
    return s.password_pending || (s.provider_pending && !s.setup_completed)
  }

  /** 改密成功后同步本地状态 */
  function markPasswordChanged() {
    if (status.value) status.value.password_pending = false
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

  /** 登出时重置 */
  function reset() {
    status.value = null
  }

  return { status, fetchStatus, shouldIntercept, markPasswordChanged, markProviderConfigured, complete, reset }
})
