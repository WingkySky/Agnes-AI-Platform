/* 工具标签注册表：完整性（全工具必有条目）+ mcp 兜底 + 未注册兜底 + 带参富文案 */

import { describe, it, expect, beforeAll } from 'vitest'
import { AGENT_TOOLS } from '../tools'
import { CHAT_TOOLS } from '../chat-tools'
import { TOOL_LABELS, toolStepLabel, mcpShortName } from '../tool-labels'
import { setLocale } from '@/i18n'

beforeAll(() => setLocale('zh-CN'))

describe('TOOL_LABELS 完整性', () => {
  it('内核与宿主全部工具都有标签条目', () => {
    const names = new Set([...AGENT_TOOLS, ...CHAT_TOOLS].map((tool) => tool.name))
    for (const name of names) expect(TOOL_LABELS[name], name).toBeDefined()
  })
})

describe('toolStepLabel', () => {
  it('mcp 工具走兜底模板并取末段短名', () => {
    expect(toolStepLabel('mcp__3__generate_image')).toBe('外部工具 · generate_image')
    expect(mcpShortName('mcp__12__list_dir')).toBe('list_dir')
  })

  it('未注册工具兜底返回原始名', () => {
    expect(toolStepLabel('future_tool')).toBe('future_tool')
  })

  it('带参富文案：技能名 / 生成类型 / 操作计数 / 节点名回调注入', () => {
    expect(toolStepLabel('agent_load_skill', { name: '分镜大师' })).toBe('加载技能：分镜大师')
    expect(toolStepLabel('agent_load_skill')).toBe('加载技能')
    expect(toolStepLabel('agent_run_generation', { kind: 'video' })).toBe('生成视频')
    expect(toolStepLabel('agent_run_generation', { kind: 'image', panel_id: 'p1' }, { nodeNameOf: () => '开场镜头' })).toBe('生成图片：开场镜头')
    expect(toolStepLabel('agent_apply_ops', { ops: [{ op: 'add_panel' }, { op: 'add_panel' }, { op: 'add_connection' }] })).toBe('画布操作：新建节点 ×2、连线 ×1')
    expect(toolStepLabel('agent_select', { panel_id: 'p1' }, { nodeNameOf: () => '开场镜头' })).toBe('选中节点：开场镜头')
  })

  it('无 nodeNameOf 时节点引用原样回落', () => {
    expect(toolStepLabel('agent_select', { panel_id: 'p1' })).toBe('选中节点：p1')
  })
})
