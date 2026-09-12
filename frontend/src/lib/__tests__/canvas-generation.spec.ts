/* buildGenerationContext 上游合并策略单测：重点防"节点已有提示词时被上游文本污染"
 * （分镜图连剧本节点仅作派生溯源，剧本全文混入会把单帧提示词变成叙事多格构图） */

import { describe, it, expect } from 'vitest'
import { buildGenerationContext } from '../canvas-generation'

function panel(id: string, type: string, content: Record<string, unknown>, name?: string) {
  return { id, type, name: name ?? type, x: 0, y: 0, width: 100, height: 80, zIndex: 0, content, created_at: '', updated_at: '' }
}

function conn(id: string, source: string, target: string) {
  return { id, source_panel_id: source, target_panel_id: target, type: 'manual', created_at: '' }
}

describe('buildGenerationContext 上游合并策略', () => {
  const scriptPanel = panel('script', 'text', { content: '《西游记》剧本：场景一……场景五……' })

  it('节点自身有提示词：上游文本不拼接（防剧本全文污染单帧提示词）', () => {
    const image = panel('img1', 'image', { prompt: 'Single frame: a woman kneels, cinematic still' })
    const ctx = buildGenerationContext(image, [scriptPanel, image], [conn('c1', 'script', 'img1')])
    expect(ctx?.prompt).toBe('Single frame: a woman kneels, cinematic still')
    expect(ctx?.prompt).not.toContain('场景一')
  })

  it('节点无提示词：上游文本充当提示词来源（保持原语义）', () => {
    const image = panel('img1', 'image', {})
    const ctx = buildGenerationContext(image, [scriptPanel, image], [conn('c1', 'script', 'img1')])
    expect(ctx?.prompt).toContain('场景一')
  })

  it('节点有提示词时上游图片仍收集为参考图', () => {
    const ref = panel('ref', 'image', { content: 'http://example.com/ref.png' })
    const image = panel('img1', 'image', { prompt: 'single frame prompt' })
    const ctx = buildGenerationContext(image, [ref, image], [conn('c1', 'ref', 'img1')])
    expect(ctx?.referenceImages).toContain('http://example.com/ref.png')
    expect(ctx?.prompt).toBe('single frame prompt')
  })

  it('显式 @文本1 引用：上游文本仍进入提示词（引用解析路径不受影响）', () => {
    const image = panel('img1', 'image', { prompt: 'single frame prompt，画面设定见 @文本1' })
    const ctx = buildGenerationContext(image, [scriptPanel, image], [conn('c1', 'script', 'img1')])
    expect(ctx?.prompt).toContain('场景一')
    expect(ctx?.prompt).toContain('【文本1】')
  })
})
