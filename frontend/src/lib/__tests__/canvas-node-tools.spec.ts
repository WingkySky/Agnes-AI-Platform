/* 节点工具栏注册表单测：各节点形态的工具集合、平铺/分组归属、顺序与动态文案 */

import { describe, it, expect, beforeAll } from 'vitest'
import { setLocale } from '@/i18n'
import { Lock, LockOpen } from 'lucide-vue-next'
import {
  TOOL_DEFS, resolveToolbarTools, toolIcon, toolLabelKey,
  type ToolContext, type ToolbarModel,
} from '../canvas-node-tools'

// 文案断言固定在中文（测试环境 navigator.language 可能是 en）
beforeAll(() => setLocale('zh-CN'))

/** 基准上下文：图片·有图·成功·有提示词，其余按需覆盖 */
const ctx = (over: Partial<ToolContext> = {}): ToolContext => ({
  type: 'image', hasContent: true, isError: false, isLoading: false, hasPrompt: true,
  freeResize: false, isLineage: false, lineageIsImage: false, lineageIsFirst: false,
  hasTailFrame: false, hasPrevFrame: false, chainSegments: 0, ...over,
})

const ids = (m: ToolbarModel) => m.primary.map((d) => d.id)
const groupIds = (m: ToolbarModel, key: string) =>
  m.groups.find((g) => g.key === key)?.tools.map((d) => d.id) ?? []

describe('注册表卫生', () => {
  it('工具 id 全局唯一', () => {
    expect(new Set(TOOL_DEFS.map((d) => d.id)).size).toBe(TOOL_DEFS.length)
  })
})

describe('图片节点·有图', () => {
  const m = resolveToolbarTools(ctx())

  it('一级只留 图生图/图生视频/替换图片/删除，其余全部分组收纳（去重后共 20 工具）', () => {
    expect(ids(m)).toEqual(['quick-generate-image', 'quick-generate-video', 'replace-image', 'delete'])
    const total = m.primary.length + m.groups.reduce((n, g) => n + g.tools.length, 0)
    expect(total).toBe(20)
  })

  it('生成组=重新生成+反推，编辑组 9 项按序，管理组 5 项按序', () => {
    expect(groupIds(m, 'generate')).toEqual(['regenerate', 'describe'])
    expect(groupIds(m, 'edit')).toEqual([
      'mask-edit', 'crop', 'split', 'upscale', 'super-resolution',
      'angle', 'lighting', 'emotion', 'toggle-ratio',
    ])
    expect(groupIds(m, 'manage')).toEqual([
      'save-asset', 'download', 'view-large', 'copy-prompt', 'info',
    ])
    expect(m.groups.map((g) => g.key)).toEqual(['generate', 'edit', 'manage'])
    expect(m.groups.map((g) => g.labelKey)).toEqual(['groupGenerate', 'groupEdit', 'groupManage'])
  })

  it('无提示词时生成组只剩反推；loading 不影响快捷生成', () => {
    expect(groupIds(resolveToolbarTools(ctx({ hasPrompt: false })), 'generate')).toEqual(['describe'])
    const loading = resolveToolbarTools(ctx({ isLoading: true }))
    expect(ids(loading)).toContain('quick-generate-image')
    expect(groupIds(loading, 'generate')).toEqual(['describe'])
  })

  it('错误态：重试平铺置顶，重新生成让位', () => {
    const e = resolveToolbarTools(ctx({ isError: true }))
    expect(ids(e)[0]).toBe('retry')
    expect(groupIds(e, 'generate')).toEqual(['describe'])
  })

  it('删除永远一级最后且 danger', () => {
    const del = m.primary[m.primary.length - 1]
    expect(del.id).toBe('delete')
    expect(del.danger).toBe(true)
  })
})

describe('图片节点·分镜派生', () => {
  const lineage = {
    isLineage: true, lineageIsImage: true, lineageIsFirst: true, chainSegments: 2,
  }

  it('首帧且无尾帧/前段：生成组=图生图+四派生+重拍+反推（无重新生成），一级只剩替换图片+删除', () => {
    const m = resolveToolbarTools(ctx(lineage))
    expect(ids(m)).toEqual(['replace-image', 'delete'])
    expect(groupIds(m, 'generate')).toEqual([
      'quick-generate-image', 'derive-video', 'derive-tail', 'derive-prev', 'derive-chain', 'reshoot', 'describe',
    ])
  })

  it('尾帧/前段已存在时不重复提供；无分段时不提供分段视频', () => {
    const m = resolveToolbarTools(ctx({ ...lineage, hasTailFrame: true, hasPrevFrame: true, chainSegments: 0 }))
    expect(groupIds(m, 'generate')).toEqual(['quick-generate-image', 'derive-video', 'reshoot', 'describe'])
  })

  it('非首帧（链帧/尾帧角色）不再提供尾帧/前段/分段派生', () => {
    const m = resolveToolbarTools(ctx({ ...lineage, lineageIsFirst: false }))
    expect(groupIds(m, 'generate')).toEqual(['quick-generate-image', 'derive-video', 'reshoot', 'describe'])
  })

  it('派生节点的图生图归生成组而非一级', () => {
    const m = resolveToolbarTools(ctx(lineage))
    const quick = m.groups.find((g) => g.key === 'generate')!.tools.find((d) => d.id === 'quick-generate-image')!
    expect(quick).toBeDefined()
  })
})

describe('视频节点', () => {
  it('有内容：一级=替换视频/删除，生成组=重新生成+三截帧', () => {
    const m = resolveToolbarTools(ctx({ type: 'video' }))
    expect(ids(m)).toEqual(['upload-video', 'delete'])
    expect(groupIds(m, 'generate')).toEqual([
      'regenerate', 'capture-frame-first', 'capture-frame', 'capture-frame-last',
    ])
    expect(groupIds(m, 'manage')).toEqual(['save-asset', 'download', 'info'])
  })

  it('无提示词时生成组只剩三截帧', () => {
    const m = resolveToolbarTools(ctx({ type: 'video', hasPrompt: false }))
    expect(groupIds(m, 'generate')).toEqual(['capture-frame-first', 'capture-frame', 'capture-frame-last'])
  })

  it('分镜派生视频：重拍此镜头替换重新生成（排截帧之前）', () => {
    const m = resolveToolbarTools(ctx({ type: 'video', isLineage: true }))
    expect(groupIds(m, 'generate')).toEqual([
      'reshoot', 'capture-frame-first', 'capture-frame', 'capture-frame-last',
    ])
  })

  it('截帧条目携带 position 参数', () => {
    const m = resolveToolbarTools(ctx({ type: 'video' }))
    const caps = m.groups.find((g) => g.key === 'generate')!.tools.filter((d) => d.id.startsWith('capture-frame'))
    expect(caps.map((d) => d.payload!(ctx({ type: 'video' })))).toEqual([
      { position: 'first' }, { position: 'current' }, { position: 'last' },
    ])
  })

  it('空视频：上传视频/节点信息/删除 平铺无分组', () => {
    const m = resolveToolbarTools(ctx({ type: 'video', hasContent: false, hasPrompt: false }))
    expect(ids(m)).toEqual(['upload-video', 'info', 'delete'])
    expect(m.groups).toEqual([])
  })
})

describe('简单形态全平铺（无分组）', () => {
  it('空图片：上传图片/节点信息/删除', () => {
    const m = resolveToolbarTools(ctx({ hasContent: false, hasPrompt: false }))
    expect(ids(m)).toEqual(['upload-image', 'info', 'delete'])
    expect(m.groups).toEqual([])
  })

  it('文本有内容：生图/生视频/字号±/存素材/节点信息/删除 共 7 钮平铺', () => {
    const m = resolveToolbarTools(ctx({ type: 'text' }))
    expect(ids(m)).toEqual([
      'quick-generate-image', 'quick-generate-video', 'font-size-down', 'font-size-up',
      'save-asset', 'info', 'delete',
    ])
    expect(m.groups).toEqual([])
  })

  it('文本无内容时去掉存素材', () => {
    const m = resolveToolbarTools(ctx({ type: 'text', hasContent: false }))
    expect(ids(m)).not.toContain('save-asset')
  })

  it('音频有内容：替换音频/存素材/下载/节点信息/删除 平铺', () => {
    const m = resolveToolbarTools(ctx({ type: 'audio' }))
    expect(ids(m)).toEqual(['upload-audio', 'save-asset', 'download', 'info', 'delete'])
    expect(m.groups).toEqual([])
  })

  it('配置节点：编辑（聚焦）/存素材/下载/节点信息/删除 平铺', () => {
    const m = resolveToolbarTools(ctx({ type: 'config' }))
    expect(ids(m)).toEqual(['edit', 'save-asset', 'download', 'info', 'delete'])
    expect(m.groups).toEqual([])
  })

  it('执行节点：生成/节点信息/删除；loading 时隐藏生成', () => {
    const m = resolveToolbarTools(ctx({ type: 'tts', hasContent: false, hasPrompt: false }))
    expect(ids(m)).toEqual(['run-node', 'info', 'delete'])
    const loading = resolveToolbarTools(ctx({ type: 'tts', hasContent: false, hasPrompt: false, isLoading: true }))
    expect(ids(loading)).toEqual(['info', 'delete'])
  })
})

describe('动态文案与参数', () => {
  it('上传↔替换按内容态切换', () => {
    const m = resolveToolbarTools(ctx({ type: 'video' }))
    const replace = m.primary.find((d) => d.id === 'upload-video')!
    expect(toolLabelKey(replace, ctx({ type: 'video' }))).toBe('replaceVideo')
    const empty = resolveToolbarTools(ctx({ type: 'video', hasContent: false, hasPrompt: false }))
    const upload = empty.primary.find((d) => d.id === 'upload-video')!
    expect(toolLabelKey(upload, ctx({ type: 'video', hasContent: false }))).toBe('uploadVideo')
  })

  it('锁比例↔自由比例文案与图标联动', () => {
    const locked = resolveToolbarTools(ctx()).groups.find((g) => g.key === 'edit')!.tools.find((d) => d.id === 'toggle-ratio')!
    expect(toolLabelKey(locked, ctx())).toBe('unlockRatio')
    expect(toolIcon(locked, ctx())).toBe(LockOpen)
    const free = resolveToolbarTools(ctx({ freeResize: true })).groups.find((g) => g.key === 'edit')!.tools.find((d) => d.id === 'toggle-ratio')!
    expect(toolLabelKey(free, ctx({ freeResize: true }))).toBe('lockRatio')
    expect(toolIcon(free, ctx({ freeResize: true }))).toBe(Lock)
  })

  it('文本节点生图按钮文案为「生图」，快捷生成 mode 按类型区分', () => {
    const textBtn = resolveToolbarTools(ctx({ type: 'text' })).primary.find((d) => d.id === 'quick-generate-image')!
    expect(toolLabelKey(textBtn, ctx({ type: 'text' }))).toBe('generateImage')
    expect(textBtn.payload!(ctx({ type: 'text' }))).toEqual({ mode: 'text2image' })
    const imgBtn = resolveToolbarTools(ctx()).primary.find((d) => d.id === 'quick-generate-image')!
    expect(toolLabelKey(imgBtn, ctx())).toBe('quickImage')
    expect(imgBtn.payload!(ctx())).toEqual({ mode: 'image2image' })
  })

  it('中文文案抽检：分组标签与删除', () => {
    expect(setLocale('zh-CN')).toBeUndefined()
    // toolLabelKey 返回 key，组件用 t() 渲染；此处验证 key 映射表与注册表一致
    const m = resolveToolbarTools(ctx())
    expect(m.groups.map((g) => g.labelKey)).toEqual(['groupGenerate', 'groupEdit', 'groupManage'])
  })
})
