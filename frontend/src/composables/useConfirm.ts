/* =====================================================
 * useConfirm — 统一确认弹窗（ElMessageBox.confirm 封装）
 * 用法（需在组件 setup 组合式上下文中调用，内部使用 useI18n）：
 *   const { confirm } = useConfirm()
 *   await confirm('确定删除？')          // 取消时静默，后续代码不执行
 *   doDelete()
 * 缺省注入 confirmButtonText: t('common.confirm')、
 * cancelButtonText: t('common.cancel')、type: 'warning'，
 * 需要自定义时通过 options 覆盖。
 * 注意：用户取消时返回的 Promise 保持挂起（静默吞掉 reject），
 * 因此「await confirm(...) 之后的代码」只在确认后执行。
 * ===================================================== */

import { ElMessageBox } from 'element-plus'
import { useI18n } from '@/i18n'

export interface ConfirmOptions {
  type?: 'success' | 'warning' | 'info' | 'error'
  confirmButtonText?: string
  cancelButtonText?: string
}

export function useConfirm() {
  const { t } = useI18n()

  /** 确认弹窗：确认后正常返回；取消时静默（Promise 保持挂起） */
  async function confirm(message: string, title?: string, options: ConfirmOptions = {}): Promise<void> {
    try {
      await ElMessageBox.confirm(message, title, {
        type: 'warning',
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        ...options,
      })
    } catch {
      // 用户取消：静默吞掉 reject，保持挂起让调用方 await 之后的代码不再执行
      await new Promise<void>(() => {})
    }
  }

  return { confirm }
}
