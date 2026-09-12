/* =====================================================
 * usePromptLength — 提示词长度分阶提示
 * 0 ~ goodMax 适中，goodMax ~ longMax 较长，超过 longMax 过长
 * 用法（组件 setup 中）：
 *   const { levelClass, text } = usePromptLength(prompt, 3000, 8000)
 * ===================================================== */

import { computed, type Ref } from 'vue'
import { useI18n } from '@/i18n'

export type PromptLengthLevel = 'good' | 'long' | 'too_long'

const levelTextKeys: Record<PromptLengthLevel, string> = {
  good: 'params.promptLengthGood',
  long: 'params.promptLengthLong',
  too_long: 'params.promptLengthTooLong',
}

export function usePromptLength(prompt: Ref<string>, goodMax: number, longMax: number) {
  const { t } = useI18n()

  /** 分阶结果：good / long / too_long */
  const level = computed<PromptLengthLevel>(() => {
    const len = prompt.value.length
    if (len <= goodMax) return 'good'
    if (len <= longMax) return 'long'
    return 'too_long'
  })

  /** 模板 hint 用的 CSS 类名：level-good / level-long / level-too-long */
  const levelClass = computed(() => `level-${level.value.replace('_', '-')}`)

  /** 提示文案：空提示词返回空字符串 */
  const text = computed(() => (prompt.value.length === 0 ? '' : t(levelTextKeys[level.value])))

  return { level, levelClass, text }
}
