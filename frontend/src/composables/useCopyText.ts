/* =====================================================
 * useCopyText — 复制文本到剪贴板并统一提示
 * 多页面复用：预设详情复制、脚本类预设应用等
 * ===================================================== */

import { ElMessage } from 'element-plus'
import { useI18n } from '@/i18n'

export function useCopyText() {
  const { t } = useI18n()

  /** 复制文本，成功返回 true 并提示（successMsg 缺省用广场预设文案）；失败走降级方案，由调用方根据返回值处理 */
  async function copyText(text: string, successMsg?: string): Promise<boolean> {
    if (!text) return false
    const msg = successMsg ?? t('presets.plaza.copied')
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success(msg)
      return true
    } catch {
      // clipboard API 不可用时降级为 execCommand
      const ta = document.createElement('textarea')
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(ta)
      if (ok) ElMessage.success(msg)
      return ok
    }
  }

  return { copyText }
}
