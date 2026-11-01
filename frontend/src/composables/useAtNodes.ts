/* =====================================================
 * "@" 画布节点引用（组合式函数）
 *
 * - 桥在线时：草稿末尾的 @token 触发节点弹层（名称/类型子串过滤）
 * - ↑↓ 导航、Enter 选中（@token 替换为「@名称 」）、Esc 关闭
 * - 键盘事件由宿主输入条先转交 handleMenuKeydown，消费返回 true（不再处理 "/" 菜单与发送）
 * - token 文本仅展示用：nodeId 随 canvas_ref 附件走（宿主在 pick 时推待发卡），名称重复/含空格零歧义
 * ===================================================== */

import { computed, ref, watch, type Ref } from 'vue'
import { getCanvasBridge, canvasNodeTypeLabel, type CanvasNodeSummary } from '@/lib/agent/canvas-bridge'

export function useAtNodes(draft: Ref<string>, enabled: () => boolean) {
  const highlight = ref(0)

  /** 末尾 @token：/@[^\s@]*$/ 命中且桥在线 → 弹层（查询=token 去掉 @） */
  const atQuery = computed(() => {
    if (!enabled() || !getCanvasBridge()?.getRefContext()) return null
    const m = /@([^\s@]*)$/.exec(draft.value)
    return m ? m[1] : null
  })

  const atMenuVisible = computed(() => atQuery.value !== null)

  const nodes = computed<CanvasNodeSummary[]>(() => getCanvasBridge()?.getRefContext()?.listNodes() ?? [])

  const filteredNodes = computed(() => {
    const q = (atQuery.value ?? '').toLowerCase()
    const all = nodes.value
    if (!q) return all.slice(0, 20)
    const hit = all.filter((n) =>
      n.name.toLowerCase().includes(q) || n.type.toLowerCase().includes(q) || canvasNodeTypeLabel(n.type).includes(q))
    return hit.slice(0, 20)
  })

  watch(atQuery, () => {
    highlight.value = 0
  })

  /** 选中节点：@token 替换为「@名称 」（引用卡由宿主 pick 回调推待发附件） */
  function pickNode(node: CanvasNodeSummary): void {
    draft.value = draft.value.replace(/@[^\s@]*$/, `@${node.name || node.id} `)
  }

  /** 键盘拦截：返回 true 表示事件已消费 */
  function handleMenuKeydown(e: KeyboardEvent, onPick: (node: CanvasNodeSummary) => void): boolean {
    if (atMenuVisible.value && filteredNodes.value.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        highlight.value = (highlight.value + 1) % filteredNodes.value.length
        return true
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        highlight.value = (highlight.value - 1 + filteredNodes.value.length) % filteredNodes.value.length
        return true
      }
      if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
        e.preventDefault()
        const node = filteredNodes.value[highlight.value]
        if (node) onPick(node)
        return true
      }
    }
    if (atMenuVisible.value && e.key === 'Escape') {
      e.preventDefault()
      draft.value = draft.value.replace(/@[^\s@]*$/, '')
      return true
    }
    return false
  }

  return { atMenuVisible, filteredNodes, highlight, pickNode, handleMenuKeydown }
}
