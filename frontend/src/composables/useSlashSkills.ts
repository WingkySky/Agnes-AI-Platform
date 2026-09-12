/* =====================================================
 * "/" 技能快速清单（组合式函数，两宿主复用：画布面板 + 对话页）
 *
 * - 草稿以 / 开头触发菜单；名称/描述/短标识子串过滤（相关度排序）
 * - ↑↓ 导航、Enter 选中（替换 / 令牌为「【使用技能：名称】」标记行，不自动发送）、Esc 关闭
 * - 键盘事件由宿主输入条先转交 handleMenuKeydown，消费返回 true（输入条不再处理发送）
 * ===================================================== */

import { computed, ref, watch, type Ref } from 'vue'
import { filterSkills, listAgentSkills, type AgentSkill } from '@/lib/agent/skills'

export function useSlashSkills(draft: Ref<string>, enabled: () => boolean) {
  const skillList = ref<AgentSkill[]>([])
  const skillHighlight = ref(0)

  void listAgentSkills().then((s) => { skillList.value = s }).catch(() => {})

  const slashQuery = computed(() => {
    if (!enabled() || !draft.value.startsWith('/')) return null
    return draft.value.slice(1).split('\n')[0]
  })

  const skillMenuVisible = computed(() => slashQuery.value !== null)
  const filteredSkills = computed(() => filterSkills(skillList.value, slashQuery.value ?? ''))

  watch(slashQuery, () => {
    skillHighlight.value = 0
  })

  /** 组装标记行草稿：替换 / 令牌为「【使用技能：名称】」，不自动发送（用户补完诉求再发） */
  function pickSkill(skill: AgentSkill): void {
    const rest = draft.value.split('\n').slice(1).join('\n')
    draft.value = `【使用技能：${skill.name}】${rest ? '\n' + rest : ''}`
  }

  /** 键盘拦截：返回 true 表示事件已消费（宿主输入条跳过默认发送） */
  function handleMenuKeydown(e: KeyboardEvent): boolean {
    if (skillMenuVisible.value && filteredSkills.value.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        skillHighlight.value = (skillHighlight.value + 1) % filteredSkills.value.length
        return true
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        skillHighlight.value = (skillHighlight.value - 1 + filteredSkills.value.length) % filteredSkills.value.length
        return true
      }
      if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
        e.preventDefault()
        pickSkill(filteredSkills.value[skillHighlight.value])
        return true
      }
    }
    if (skillMenuVisible.value && e.key === 'Escape') {
      e.preventDefault()
      // 关闭菜单：清掉 / 令牌让菜单消失（令牌在开头，直接清空第一行）
      draft.value = draft.value.split('\n').slice(1).join('\n')
      return true
    }
    return false
  }

  return { skillMenuVisible, filteredSkills, skillHighlight, pickSkill, handleMenuKeydown }
}
