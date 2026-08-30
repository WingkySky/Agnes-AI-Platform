/* =====================================================
 * useCopyText — 复制文本到剪贴板并统一提示
 * 多页面复用：预设详情复制、脚本类预设应用等
 * ===================================================== */

import { ElMessage } from 'element-plus'
import { useI18n } from '@/i18n'

export function useCopyText() {
  const { t } = useI18n()

  /** 复制文本，成功返回 true 并提示；失败走降级方案 */
  async function copyText(text: string): Promise<boolean> {
    if (!text) return false
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success(t('presets.plaza.copied'))
      return true
    } catch {
      // clipboard API 不可用时降级为 execCommand
      const ta = document.createElement('textarea')
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(ta)
      if (ok) ElMessage.success(t('presets.plaza.copied'))
      return ok
    }
  }

  return { copyText }
}
