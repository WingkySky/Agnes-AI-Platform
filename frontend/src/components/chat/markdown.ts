/* =====================================================
 * 共享 markdown 渲染单例（components/chat）
 *
 * - html:false 关闭内联 HTML 注入（XSS 防护）
 * - breaks:true 对齐聊天场景的换行习惯
 * - linkify:true 自动识别链接
 * ===================================================== */

import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: false, breaks: true, linkify: true })

/** markdown → HTML（空文本直接返回空串） */
export function renderMarkdown(text: string): string {
  if (!text) return ''
  return md.render(text)
}
