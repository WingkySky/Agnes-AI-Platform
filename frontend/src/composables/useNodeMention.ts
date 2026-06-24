/* =====================================================
 * useNodeMention 组合式函数
 * - 处理 textarea 中的 @ 提及节点功能
 * - 输入 @ 时弹出已接入节点的下拉选择列表
 * - 支持键盘导航（上下箭头选择，Enter 确认，Esc 关闭）
 * - 选择后插入可读标签格式（@图片1、@文本2），用户看到什么就是什么
 * - 弹窗使用 fixed 定位，通过 Teleport 传送到 body，避免被父容器裁剪
 * ===================================================== */

import { ref, computed, nextTick } from 'vue'
import { useCanvasStore } from '@/stores/canvas'

export interface MentionPanel {
  id: string
  name: string
  type: string
  index: number
  label: string
  preview?: string
}

/** 节点类型中文名映射 */
const TYPE_LABELS: Record<string, string> = {
  text: '文本',
  image: '图片',
  video: '视频',
  audio: '音频',
}

/**
 * 计算 textarea 中光标位置的像素坐标（用于定位 mention 弹窗）
 * 使用镜像 div 技术精确测量
 */
function getCaretCoordinates(textarea: HTMLTextAreaElement, position: number): { top: number; left: number } {
  const div = document.createElement('div')
  const style = window.getComputedStyle(textarea)

  // 复制影响文本布局的样式
  const props = [
    'boxSizing', 'width', 'height',
    'overflowX', 'overflowY',
    'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth',
    'borderStyle',
    'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
    'fontStyle', 'fontVariant', 'fontWeight', 'fontStretch', 'fontSize',
    'fontSizeAdjust', 'lineHeight', 'fontFamily',
    'textAlign', 'textTransform', 'textIndent', 'textDecoration',
    'letterSpacing', 'wordSpacing', 'tabSize',
    'whiteSpace', 'wordWrap', 'wordBreak',
  ] as const

  for (const p of props) {
    (div.style as any)[p] = (style as any)[p]
  }

  div.style.position = 'absolute'
  div.style.visibility = 'hidden'
  div.style.whiteSpace = 'pre-wrap'
  div.style.wordWrap = 'break-word'
  div.style.top = '0'
  div.style.left = '0'

  const textBefore = textarea.value.substring(0, position)
  const textAfter = textarea.value.substring(position)

  // 光标前文本
  div.textContent = textBefore
  // 光标位置用 span 标记
  const caretSpan = document.createElement('span')
  caretSpan.textContent = textAfter || '.'
  div.appendChild(caretSpan)

  document.body.appendChild(div)

  const rect = textarea.getBoundingClientRect()
  const divRect = div.getBoundingClientRect()

  // 计算光标相对于 textarea 左上角的坐标
  const caretTop = divRect.height - parseInt(style.paddingTop, 10) - parseInt(style.borderTopWidth, 10)
  const caretLeft = caretSpan.offsetLeft - divRect.left + div.offsetLeft - parseInt(style.paddingLeft, 10)

  document.body.removeChild(div)

  // 转换为视口坐标（fixed 定位）
  return {
    top: rect.top + caretTop + parseInt(style.lineHeight, 10) + 4,
    left: rect.left + caretLeft,
  }
}

export function useNodeMention(textareaRef: { value: HTMLTextAreaElement | null }) {
  const store = useCanvasStore()

  // ---------- 状态 ----------
  /** @ 提及弹窗是否可见 */
  const mentionPopupVisible = ref(false)
  /** 当前输入 @ 后搜索的关键字 */
  const mentionSearchText = ref('')
  /** 当前选中的候选项索引 */
  const mentionActiveIndex = ref(0)
  /** 当前 @ 符号在文本中的起始位置 */
  const mentionStartPos = ref(-1)
  /** 当前编辑的面板 ID（即 config 节点自己的 ID） */
  const currentPanelId = ref<string | null>(null)
  /** 弹窗位置（fixed 定位，相对于视口） */
  const mentionPopupPosition = ref({ top: 0, left: 0 })

  // ---------- 计算属性：候选项列表 ----------
  const mentionCandidates = computed<MentionPanel[]>(() => {
    if (!currentPanelId.value) return []
    // 获取当前 config 节点的所有上游输入节点（带序号）
    const inputs = store.getInputNodesWithIndex(currentPanelId.value)
    const search = mentionSearchText.value.trim()

    return inputs
      .map(({ panel, index }) => {
        const typeLabel = TYPE_LABELS[panel.type] || '节点'
        const label = `${typeLabel}${index}`
        let name = ''
        let preview = ''
        switch (panel.type) {
          case 'text':
            name = '文本节点'
            preview = String(panel.content?.content || '').slice(0, 30)
            break
          case 'image':
            name = '图片'
            preview = panel.content?.prompt ? String(panel.content.prompt).slice(0, 30) : ''
            break
          case 'video':
            name = '视频'
            preview = panel.content?.prompt ? String(panel.content.prompt).slice(0, 30) : ''
            break
          case 'audio':
            name = '音频'
            break
          default:
            name = panel.name || panel.type || '节点'
        }
        return {
          id: panel.id,
          name,
          type: panel.type || '',
          index,
          label,
          preview,
        }
      })
      .filter(item => {
        if (!search) return true
        const searchLower = search.toLowerCase()
        return (
          item.name.includes(search) ||
          item.label.includes(search) ||
          String(item.index).includes(search) ||
          (item.preview && item.preview.toLowerCase().includes(searchLower))
        )
      })
  })

  // ---------- 工具函数：获取节点类型图标 ----------
  function getTypeIcon(type: string): string {
    const icons: Record<string, string> = {
      text: '📝',
      image: '🖼️',
      video: '🎬',
      audio: '🎵',
      config: '⚙️',
    }
    return icons[type] || '📦'
  }

  // ---------- 更新弹窗位置（fixed 定位，基于光标像素坐标） ----------
  function updatePopupPosition() {
    const textarea = textareaRef.value
    if (!textarea) return
    const pos = getCaretCoordinates(textarea, textarea.selectionStart)
    mentionPopupPosition.value = pos
  }

  // ---------- 输入处理：检测 @ 符号 ----------
  function handleInput() {
    const textarea = textareaRef.value
    if (!textarea) return

    const cursorPos = textarea.selectionStart
    const text = textarea.value
    const textBeforeCursor = text.substring(0, cursorPos)

    // 查找最近的 @ 符号：匹配 @ 后面跟非空格非@字符（支持中文标签搜索）
    const atMatch = textBeforeCursor.match(/(^|\s)@([^\s@]*)$/)
    if (atMatch) {
      const atIndex = textBeforeCursor.lastIndexOf('@')
      mentionStartPos.value = atIndex
      mentionSearchText.value = atMatch[2] || ''
      mentionPopupVisible.value = true
      mentionActiveIndex.value = 0
      nextTick(updatePopupPosition)
    } else {
      closeMentionPopup()
    }
  }

  // ---------- 关闭弹窗 ----------
  function closeMentionPopup() {
    mentionPopupVisible.value = false
    mentionSearchText.value = ''
    mentionStartPos.value = -1
    mentionActiveIndex.value = 0
  }

  // ---------- 选择候选项并插入可读标签（@图片1、@文本2） ----------
  function selectMention(panel: MentionPanel) {
    const textarea = textareaRef.value
    if (!textarea || mentionStartPos.value < 0) {
      closeMentionPopup()
      return
    }

    const text = textarea.value
    const cursorPos = textarea.selectionStart
    // 插入可读格式：@图片1 （用户看到什么就是什么，自然语言）
    const insertText = `@${panel.label}`
    const before = text.substring(0, mentionStartPos.value)
    const after = text.substring(cursorPos)
    const newValue = before + insertText + ' ' + after

    // 触发 input 事件
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set
    if (nativeInputValueSetter) {
      nativeInputValueSetter.call(textarea, newValue)
    } else {
      textarea.value = newValue
    }
    textarea.dispatchEvent(new Event('input', { bubbles: true }))

    // 移动光标到插入文本末尾 + 1 个空格
    const newCursorPos = mentionStartPos.value + insertText.length + 1
    nextTick(() => {
      textarea.focus()
      textarea.setSelectionRange(newCursorPos, newCursorPos)
    })

    closeMentionPopup()
  }

  // ---------- 键盘导航 ----------
  function handleKeyDown(event: KeyboardEvent) {
    if (!mentionPopupVisible.value) return

    const candidates = mentionCandidates.value
    if (candidates.length === 0) {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeMentionPopup()
      }
      return
    }

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault()
        mentionActiveIndex.value = (mentionActiveIndex.value + 1) % candidates.length
        break
      case 'ArrowUp':
        event.preventDefault()
        mentionActiveIndex.value = (mentionActiveIndex.value - 1 + candidates.length) % candidates.length
        break
      case 'Enter':
        event.preventDefault()
        selectMention(candidates[mentionActiveIndex.value])
        break
      case 'Escape':
        event.preventDefault()
        closeMentionPopup()
        break
    }
  }

  // ---------- 点击候选项时阻止blur（mousedown时先阻止默认，避免textarea失焦） ----------
  function handlePopupMouseDown(event: MouseEvent) {
    event.preventDefault()
  }

  // ---------- 失去焦点时关闭（延迟，留给点击候选项的时间） ----------
  function handleBlur() {
    setTimeout(closeMentionPopup, 200)
  }

  // ---------- 设置当前面板 ID ----------
  function setCurrentPanel(panelId: string | null) {
    currentPanelId.value = panelId
  }

  return {
    mentionPopupVisible,
    mentionSearchText,
    mentionActiveIndex,
    mentionCandidates,
    mentionPopupPosition,
    handleInput,
    handleKeyDown,
    handleBlur,
    handlePopupMouseDown,
    selectMention,
    closeMentionPopup,
    setCurrentPanel,
    getTypeIcon,
  }
}
