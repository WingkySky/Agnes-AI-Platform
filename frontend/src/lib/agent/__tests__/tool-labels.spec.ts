/* 工具标签注册表：完整性（全工具必有条目）+ mcp 兜底 + 未注册兜底 + 带参富文案 */

import { describe, it, expect, beforeAll } from 'vitest'
import { AGENT_TOOLS } from '../tools'
import { CHAT_TOOLS } from '../chat-tools'
import { TOOL_LABELS, toolStepLabel, mcpShortName, toolRouteLabel, stepSummaryOf } from '../tool-labels'
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

describe('toolRouteLabel（批次 3 执行来源）', () => {
  it('三态路由文案；未回填返回 undefined', () => {
    expect(toolRouteLabel('local')).toBe('本页执行')
    expect(toolRouteLabel('bridge')).toBe('页面实时执行')
    expect(toolRouteLabel('server')).toBe('服务端执行')
    expect(toolRouteLabel(undefined)).toBeUndefined()
  })
})

describe('stepSummaryOf（批次 3 完成回执摘要）', () => {
  it('取 data 内 message + 白名单产物 URL', () => {
    const r = stepSummaryOf(JSON.stringify({
      ok: true,
      data: { audio_url: 'https://cdn/a.mp3', asset_id: 3, message: '配音已生成并入素材库' },
    }))
    expect(r).toEqual({ text: '配音已生成并入素材库', url: 'https://cdn/a.mp3' })
  })

  it('顶层 message（落画布占位步骤无 ok/data 包装）', () => {
    expect(stepSummaryOf(JSON.stringify({ message: '已放到「对话画布」', panel_id: 'p1' })))
      .toEqual({ text: '已放到「对话画布」' })
  })

  it('ok:false / 非 JSON / 空结果返回 undefined', () => {
    expect(stepSummaryOf(JSON.stringify({ ok: false, error: 'x' }))).toBeUndefined()
    expect(stepSummaryOf('普通错误文本')).toBeUndefined()
    expect(stepSummaryOf(null)).toBeUndefined()
    expect(stepSummaryOf(JSON.stringify({ ok: true, data: {} }))).toBeUndefined()
  })

  it('URL 只认白名单字段与 http(s) 协议', () => {
    expect(stepSummaryOf(JSON.stringify({ ok: true, data: { url: 'javascript:alert(1)', message: 'm' } }))?.url).toBeUndefined()
    expect(stepSummaryOf(JSON.stringify({ ok: true, data: { final_url: 'https://cdn/f.mp4' } })))
      .toEqual({ text: '', url: 'https://cdn/f.mp4' })
  })

  it('message 缺失时按结构化字段合成建卡/连线/失败摘要（桥上原生 apply_ops 回执）', () => {
    const r = stepSummaryOf(JSON.stringify({
      results: [
        { index: 0, op: 'add_panel', ok: true, panel_id: 'p1' },
        { index: 1, op: 'add_panel', ok: true, panel_id: 'p2' },
        { index: 2, op: 'add_connection', ok: true, connection_id: 'c1' },
        { index: 3, op: 'delete_panel', ok: false, error: 'x' },
      ],
      new_panel_ids: ['p1', 'p2'],
    }))
    expect(r?.text).toBe('已新建 2 个节点、新建 1 条连线、1 条失败')
  })
})
