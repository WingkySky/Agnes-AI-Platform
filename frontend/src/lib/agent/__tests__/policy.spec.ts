/* 策略层直测：三档权限 × 工具组 × 阶段门状态矩阵 */

import { describe, it, expect, beforeAll } from 'vitest'
import { resolveToolCall, gatedKindOf, inferGenerationKind, stageNameOfKind, stageApprovedMessage } from '../policy'
import { setLocale } from '@/i18n'

beforeAll(() => setLocale('zh-CN'))

const base = {
  args: {} as Record<string, unknown>,
  gatedKinds: [] as string[],
  panelType: undefined as string | undefined,
}

describe('resolveToolCall', () => {
  it('只读档：read 组放行，写/生成拒绝且不停止回合', () => {
    expect(resolveToolCall({ ...base, mode: 'readonly', toolName: 'agent_get_state', toolGroup: 'read' }).action).toBe('allow')
    const r = resolveToolCall({ ...base, mode: 'readonly', toolName: 'agent_apply_ops', toolGroup: 'write' })
    expect(r.action).toBe('reject')
    if (r.action === 'reject') {
      expect(r.reason).toContain('只读')
      expect(r.stop).toBe(false)
    }
    const g = resolveToolCall({ ...base, mode: 'readonly', toolName: 'agent_run_generation', toolGroup: 'generation' })
    expect(g.action).toBe('reject')
  })

  it('确认档：阶段汇报转阶段卡审阅', () => {
    const r = resolveToolCall({
      ...base,
      mode: 'confirm',
      toolName: 'agent_stage_review',
      toolGroup: 'write',
      args: { stage: '剧本', summary: '初稿' },
    })
    expect(r.action).toBe('gate')
    if (r.action === 'gate') {
      expect(r.kind).toBe('stage')
      expect(r.stage).toBe('剧本')
      expect(r.onReject).toContain('暂停')
    }
  })

  it('自动档：阶段汇报直通', () => {
    const r = resolveToolCall({
      ...base,
      mode: 'auto',
      toolName: 'agent_stage_review',
      toolGroup: 'write',
      args: { stage: '剧本', summary: '初稿' },
    })
    expect(r.action).toBe('allow')
  })

  it('确认档：生成阶段首次过门，kind 缺省按节点类型推断', () => {
    const r = resolveToolCall({ ...base, mode: 'confirm', toolName: 'agent_run_generation', toolGroup: 'generation', args: { panel_id: 'p1' }, panelType: 'video' })
    expect(r.action).toBe('gate')
    if (r.action === 'gate') expect(r.stage).toBe('分段视频')
  })

  it('确认档：args.kind 显式优先于节点类型', () => {
    const r = resolveToolCall({ ...base, mode: 'confirm', toolName: 'agent_run_generation', toolGroup: 'generation', args: { panel_id: 'p1', kind: 'compose' }, panelType: 'image' })
    expect(r.action).toBe('gate')
    if (r.action === 'gate') expect(r.stage).toBe('成片合成')
  })

  it('确认档：同阶段已过门则放行（同回合不重复拦）', () => {
    const r = resolveToolCall({ ...base, mode: 'confirm', toolName: 'agent_run_generation', toolGroup: 'generation', args: { panel_id: 'p1', kind: 'image' }, gatedKinds: ['image'] })
    expect(r.action).toBe('allow')
  })

  it('自动档：生成不过门', () => {
    const r = resolveToolCall({ ...base, mode: 'auto', toolName: 'agent_run_generation', toolGroup: 'generation', args: { panel_id: 'p1', kind: 'image' } })
    expect(r.action).toBe('allow')
  })

  it('确认档：写工具不过门（随阶段门放行语义）', () => {
    const r = resolveToolCall({ ...base, mode: 'confirm', toolName: 'agent_apply_ops', toolGroup: 'write' })
    expect(r.action).toBe('allow')
  })
})

describe('辅助函数', () => {
  it('inferGenerationKind：显式 kind 优先，缺省按节点类型', () => {
    expect(inferGenerationKind('', 'video')).toBe('video')
    expect(inferGenerationKind('', 'compose')).toBe('compose')
    expect(inferGenerationKind('', 'text')).toBe('image')
    expect(inferGenerationKind('compose', 'image')).toBe('compose')
  })

  it('stageNameOfKind 映射', () => {
    expect(stageNameOfKind('asset')).toBe('实体设定')
    expect(stageNameOfKind('image')).toBe('分镜图')
    expect(stageNameOfKind('video')).toBe('分段视频')
    expect(stageNameOfKind('compose')).toBe('成片合成')
  })

  it('gatedKindOf：仅生成类工具记录过门', () => {
    expect(gatedKindOf('agent_apply_ops', {}, undefined)).toBeNull()
    expect(gatedKindOf('agent_run_generation', { kind: 'video' }, undefined)).toBe('video')
    expect(gatedKindOf('agent_run_generation', {}, 'compose')).toBe('compose')
  })

  it('确认档：asset（实体设定）独立过门，与 image 互不影响', () => {
    const gate = resolveToolCall({ ...base, mode: 'confirm', toolName: 'agent_run_generation', toolGroup: 'generation', args: { kind: 'asset' } })
    expect(gate.action).toBe('gate')
    if (gate.action === 'gate') {
      expect(gate.stage).toBe('实体设定')
      expect(gate.summary).toContain('实体设定')
    }
    // asset 已过门时再次 asset 放行；但 image 仍要过自己的门
    expect(resolveToolCall({ ...base, mode: 'confirm', toolName: 'agent_run_generation', toolGroup: 'generation', args: { kind: 'asset' }, gatedKinds: ['asset'] }).action).toBe('allow')
    const imageGate = resolveToolCall({ ...base, mode: 'confirm', toolName: 'agent_run_generation', toolGroup: 'generation', args: { kind: 'image' }, gatedKinds: ['asset'] })
    expect(imageGate.action).toBe('gate')
    if (imageGate.action === 'gate') expect(imageGate.stage).toBe('分镜图')
  })

  it('mcp 组：确认档每工具首次过门（kind=tool），已过门直通；只读拒、自动直通', () => {
    const gate = resolveToolCall({ ...base, mode: 'confirm', toolName: 'mcp__1__read_file', toolGroup: 'mcp' })
    expect(gate.action).toBe('gate')
    if (gate.action === 'gate') {
      expect(gate.kind).toBe('tool')
      expect(gate.stage).toBe('mcp__1__read_file')
      expect(gate.summary).toContain('MCP')
    }
    // 同工具已过门 → 直通；不同工具 → 仍要过门
    expect(resolveToolCall({ ...base, mode: 'confirm', toolName: 'mcp__1__read_file', toolGroup: 'mcp', gatedKinds: ['mcp__1__read_file'] }).action).toBe('allow')
    expect(resolveToolCall({ ...base, mode: 'confirm', toolName: 'mcp__2__list_dir', toolGroup: 'mcp', gatedKinds: ['mcp__1__read_file'] }).action).toBe('gate')
    // 自动档直通；只读档拒绝
    expect(resolveToolCall({ ...base, mode: 'auto', toolName: 'mcp__1__read_file', toolGroup: 'mcp' }).action).toBe('allow')
    const ro = resolveToolCall({ ...base, mode: 'readonly', toolName: 'mcp__1__read_file', toolGroup: 'mcp' })
    expect(ro.action).toBe('reject')
  })

  it('gatedKindOf：mcp 工具记工具名本身，非生成类返回 null', () => {
    expect(gatedKindOf('mcp__1__read_file', {}, undefined)).toBe('mcp__1__read_file')
    expect(gatedKindOf('agent_create_text_node', {}, undefined)).toBeNull()
  })

  it('阶段通过指引：实体设定指向分镜提示词', () => {
    expect(stageApprovedMessage('实体设定')).toContain('分镜提示词')
    expect(stageApprovedMessage('剧本')).toContain('实体设定')
  })
})
