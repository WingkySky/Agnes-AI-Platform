/* =====================================================
 * useChatComposer — 聊天输入组合式（多聊天面共享）
 *
 * 消费方：对话页 ChatView / 全局宿主 AgentHostPanel。
 * 收口发送链路共有的输入状态与副作用：待发附件（粘贴识别/上传/URL 提取）、
 * 发送、"/" 技能快速清单（useSlashSkills）。
 * enabled 守卫用于多聊天面共存时互斥收集全局粘贴（抽屉开着只收抽屉的）。
 * ===================================================== */

import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import type { MessageAttachment } from '@/types'
import { useI18n } from '@/i18n'
import { useChatStore } from '@/stores/chat'
import { useSlashSkills } from '@/composables/useSlashSkills'
import { isImageFile, isSupportedFile, extractFileText } from '@/lib/agent/attachments'

export interface UseChatComposerOptions {
  /** 全局粘贴监听生效条件（false 时事件直接放行）；多面共存时用于互斥 */
  enabled?: () => boolean
}

export function useChatComposer(options: UseChatComposerOptions = {}) {
  const { t } = useI18n()
  const chatStore = useChatStore()

  // 输入框文本
  const inputText = ref('')
  // 待发送附件列表（粘贴/上传后加入，发送时清空）
  const pendingAttachments = ref<MessageAttachment[]>([])

  // "/" 技能快速清单（共享组合式；菜单渲染用共享 ChatSkillMenu）
  const { skillMenuVisible, filteredSkills, skillHighlight, pickSkill, handleMenuKeydown } = useSlashSkills(inputText, () => !chatStore.busy)

  /** 键盘事件转交技能菜单（ChatInputBar keydown 先过这里） */
  function onDraftKeydown(e: KeyboardEvent): void {
    handleMenuKeydown(e)
  }

  /** 发送消息（使用 pendingAttachments：粘贴/上传的附件，叠加文本中的 URL 识别） */
  async function handleSend() {
    const content = inputText.value.trim()
    const attachments = [...pendingAttachments.value]
    // 从文本中自动识别 URL 作为附件（与粘贴识别互补）
    attachments.push(...extractUrlsAsAttachments(content))

    if (!content && attachments.length === 0) return
    if (chatStore.busy) return

    inputText.value = ''
    pendingAttachments.value = []
    try {
      await chatStore.send(content, attachments)
    } catch (e: unknown) {
      ElMessage.error((e instanceof Error ? e.message : '') || t('chat.sendFailed'))
    }
  }

  /** 处理全局 Ctrl+V 粘贴事件：自动识别图片（二进制）/ 图片 URL */
  function handleGlobalPaste(e: ClipboardEvent) {
    if (options.enabled && !options.enabled()) return
    if (chatStore.busy) return

    const items = e.clipboardData?.items
    let handled = false

    // 1) 优先识别二进制图片（截图、图片文件复制）
    if (items) {
      for (const item of items) {
        if (item.type.indexOf('image') !== -1) {
          const file = item.getAsFile()
          if (file) {
            fileToBase64(file).then(base64 => {
              pendingAttachments.value.push({
                name: file.name || 'pasted-image.png',
                base64,
                url: undefined,
                size: file.size,
                mime_type: file.type || 'image/png',
              })
            })
            handled = true
            break
          }
        }
      }
    }

    // 2) 如果没有图片，检查纯文本是否是图片 URL
    if (!handled) {
      const text = e.clipboardData?.getData('text')
      if (text && isImageUrl(text.trim())) {
        const url = text.trim()
        pendingAttachments.value.push({
          name: url.split('/').pop() || 'image',
          base64: undefined,
          url,
          size: 0,
          mime_type: 'image/url',
          source: 'url',
        })
        handled = true
      }
    }

    if (handled) {
      e.preventDefault() // 阻止默认粘贴行为（否则输入框会出现文本）
    }
  }

  onMounted(() => window.addEventListener('paste', handleGlobalPaste))
  onBeforeUnmount(() => window.removeEventListener('paste', handleGlobalPaste))

  /** 附件按钮选择本地文件（共享输入条 pick-files 事件）：
   *  图片收 base64 附件；文本类文档（md/pdf/docx 等）解析为文本拼进输入框 */
  function onFilesPicked(files: File[]) {
    for (const file of files) {
      if (isImageFile(file)) {
        fileToBase64(file).then(base64 => {
          pendingAttachments.value.push({
            name: file.name,
            base64,
            url: undefined,
            size: file.size,
            mime_type: file.type,
          })
        })
      } else if (isSupportedFile(file)) {
        extractFileText(file)
          .then(({ name, text }) => {
            inputText.value = (inputText.value ? inputText.value + '\n\n' : '') + `【文件：${name}】\n${text}`
          })
          .catch(() => ElMessage.warning(t('agent.unsupportedType')))
      }
    }
  }

  /** 删除待发送附件 */
  function removePendingAttachment(index: number) {
    pendingAttachments.value.splice(index, 1)
  }

  return {
    inputText,
    pendingAttachments,
    handleSend,
    onFilesPicked,
    removePendingAttachment,
    onDraftKeydown,
    skillMenuVisible,
    filteredSkills,
    skillHighlight,
    pickSkill,
  }
}

/** File → base64（异步） */
function fileToBase64(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

/** 判断字符串是否为图片 URL（http/https 开头，且路径后缀或域名像图片） */
function isImageUrl(text: string) {
  if (!text) return false
  if (!/^https?:\/\//i.test(text)) return false
  // 检查是否是常见的图片扩展名
  const lower = text.toLowerCase().split('?')[0]
  return /\.(png|jpe?g|gif|webp|bmp|svg|avif)$/i.test(lower)
}

// 匹配 http(s):// 开头的独立链接（不包含中文标点、空白、括号、引号）
const URL_REGEX = /\bhttps?:\/\/[^\s，。！？、<>（）()[\]{}"'`]+/gi

/** 根据文件扩展名快速判断链接类型（无需网络请求，即时响应） */
function guessUrlTypeByExt(url: string) {
  if (!url) return 'unknown'
  const u = url.toLowerCase().split('?')[0]
  if (/\.(jpg|jpeg|png|gif|webp|bmp|svg|tiff?|avif)$/.test(u)) return 'image'
  if (/\.(mp4|webm|mov|m4v|avi|mkv|flv)$/.test(u)) return 'video'
  if (/\.(pdf|doc|docx|txt|md|csv|xls|xlsx|ppt|pptx|rtf|odt)$/.test(u)) return 'document'
  return 'unknown'
}

/** 从 URL 中提取文件名（作为附件名称） */
function extractUrlName(url: string) {
  try {
    const u = new URL(url)
    const parts = u.pathname.split('/')
    return parts[parts.length - 1] || u.hostname
  } catch {
    return url.split('/').pop() || 'link'
  }
}

/** 从文本中识别 URL，返回附件对象数组（仅包含 image / video / document，webpage 不加入附件） */
function extractUrlsAsAttachments(text: string) {
  if (!text) return []
  const matches = text.match(URL_REGEX) || []
  const atts: MessageAttachment[] = []
  const seen = new Set()
  for (const rawUrl of matches) {
    // 去重
    if (seen.has(rawUrl)) continue
    seen.add(rawUrl)
    const linkType = guessUrlTypeByExt(rawUrl)
    if (linkType === 'unknown') {
      // 未知扩展名 → 不加入附件，仅保留在文本中
      continue
    }
    atts.push({
      name: extractUrlName(rawUrl),
      url: rawUrl,
      size: 0,
      mime_type: linkType === 'image' ? 'image/url' : (linkType === 'video' ? 'video/url' : 'application/url'),
      source: 'url',
      _link_type: linkType,
    })
  }
  return atts
}

/** URL 截断显示（缩略图旁边的 URL 文案） */
export function truncateUrl(url: string) {
  if (!url) return ''
  if (url.length <= 50) return url
  return url.slice(0, 47) + '...'
}
