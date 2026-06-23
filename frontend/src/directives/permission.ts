/* =====================================================
 * v-permission 自定义指令
 * - 无权限时隐藏元素（移除 DOM）
 * - 用法：v-permission="'plaza:moderate'"
 * ===================================================== */

import type { Directive, DirectiveBinding } from 'vue'
import { usePermissionStore } from '@/stores/permission'

/**
 * 更新元素显示状态
 */
function updateEl(el: HTMLElement, binding: DirectiveBinding<string>) {
  const permStore = usePermissionStore()
  const perm = binding.value
  if (!perm) return

  const hasPerm = permStore.hasPermission(perm)
  if (hasPerm) {
    el.style.display = ''
  } else {
    el.style.display = 'none'
  }
}

const permissionDirective: Directive = {
  mounted(el: HTMLElement, binding) {
    updateEl(el, binding as DirectiveBinding<string>)
  },
  updated(el: HTMLElement, binding) {
    updateEl(el, binding as DirectiveBinding<string>)
  },
}

export default permissionDirective
