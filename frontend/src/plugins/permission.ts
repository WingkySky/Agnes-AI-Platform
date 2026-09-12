/* =====================================================
 * 权限插件
 * - 注册全局 v-permission 指令
 * - 注册全局方法 $hasPerm
 * ===================================================== */

import type { App } from 'vue'
import permissionDirective from '@/directives/permission'
import { usePermissionStore } from '@/stores/permission'

export default {
  install(app: App) {
    // 注册全局指令
    app.directive('permission', permissionDirective)

    // 注册全局方法 $hasPerm
    app.config.globalProperties.$hasPerm = (perm: string): boolean => {
      const permStore = usePermissionStore()
      return permStore.hasPermission(perm)
    }
  },
}
