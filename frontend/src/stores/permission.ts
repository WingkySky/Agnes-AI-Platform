/* =====================================================
 * 权限 Store
 * - 管理当前用户的权限列表
 * - 提供权限检查方法
 * - 内置角色权限映射（简化版本）
 * ===================================================== */

import { defineStore } from 'pinia'
import { ref } from 'vue'

/** 内置角色权限映射 */
const ROLE_PERMISSIONS: Record<string, string[]> = {
  admin: ['*'],
  moderator: ['plaza:moderate', 'moderation:config', 'content:generate', 'plaza:share'],
  user: ['content:generate', 'plaza:share'],
}

export const usePermissionStore = defineStore('permission', () => {
  // ================ state ================
  const permissions = ref<string[]>([])
  const currentRole = ref<string>('')

  // ================ actions ================

  /**
   * 根据用户角色加载权限
   * 简化版本：从内置角色权限映射获取
   * 后续可改为从后端 API 获取
   */
  function loadPermissions(role: string) {
    currentRole.value = role || 'user'
    const perms = ROLE_PERMISSIONS[role] || ROLE_PERMISSIONS.user || []
    permissions.value = [...perms]
  }

  /**
   * 检查是否拥有某权限
   * admin 角色直接返回 true
   */
  function hasPermission(perm: string): boolean {
    if (currentRole.value === 'admin') {
      return true
    }
    if (permissions.value.includes('*')) {
      return true
    }
    return permissions.value.includes(perm)
  }

  /** 登出时清空权限 */
  function reset() {
    permissions.value = []
    currentRole.value = ''
  }

  return {
    permissions,
    currentRole,
    loadPermissions,
    hasPermission,
    reset,
  }
})
