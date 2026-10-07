/* =====================================================
 * 重命名组合式函数：ElMessageBox.prompt 输入新名（多个列表页复用）
 * 返回 trim 后的新名；取消/空输入返回 null（调用方跳过请求）
 * ===================================================== */

import { ElMessageBox } from 'element-plus'

import { useI18n } from '@/i18n'

export function useRename() {
  const { t } = useI18n()

  async function rename(current: string): Promise<string | null> {
    try {
      const res = await ElMessageBox.prompt(t('common.renamePrompt'), t('common.rename'), {
        inputValue: current,
        inputPattern: /\S/,
        inputErrorMessage: t('common.renamePrompt'),
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
      })
      const name = (res.value || '').trim()
      return name && name !== current ? name : null
    } catch {
      return null // 取消
    }
  }

  return { rename }
}
