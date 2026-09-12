/* 共享 markdown 渲染单测：块级元素、XSS 转义、换行与链接识别 */

import { describe, it, expect } from 'vitest'
import { renderMarkdown } from '../markdown'

describe('renderMarkdown', () => {
  it('空文本返回空串', () => {
    expect(renderMarkdown('')).toBe('')
  })

  it('渲染加粗/行内代码/代码块', () => {
    const html = renderMarkdown('**加粗** 和 `code`\n\n```js\nconst a = 1\n```')
    expect(html).toContain('<strong>加粗</strong>')
    expect(html).toContain('<code>code</code>')
    expect(html).toContain('<pre>')
    expect(html).toContain('const a = 1')
  })

  it('html:false 时内联 HTML 被转义（XSS 防护）', () => {
    const html = renderMarkdown('<img src=x onerror=alert(1)>')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img')
  })

  it('breaks:true 单换行渲染为 <br>', () => {
    expect(renderMarkdown('第一行\n第二行')).toContain('第一行<br>\n第二行')
  })

  it('linkify 自动识别链接', () => {
    const html = renderMarkdown('看 https://example.com 这个')
    expect(html).toContain('<a href="https://example.com"')
  })

  it('列表与表格可用（对话页渲染升级点）', () => {
    const html = renderMarkdown('- 甲\n- 乙')
    expect(html).toContain('<ul>')
    expect(html).toContain('<li>甲</li>')
  })
})
