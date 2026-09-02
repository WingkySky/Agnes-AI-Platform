/* =====================================================
 * 无限画布 Pinia Store（Option API）
 * - 管理多工作区、节点（panels）、连线（connections）、视口
 * - 支持选中 / 历史（撤销/重做，最多 80 步）
 * - 支持搜索定位、对齐参考线、网格吸附、隐藏、锁定、旋转
 * - 支持复制粘贴、图片节点拆分、导入导出 JSON
 * - 持久化由 lib/canvas-storage.js 负责
 * ===================================================== */

import { defineStore } from 'pinia'
import { canvasThemes } from '@/lib/canvas-theme'
import { loadCanvas, saveCanvas, switchCanvasUser, cancelSaveCanvas } from '@/lib/canvas-storage'
import { useThemeStore } from './theme'
import { analyzeFlow } from '@/lib/canvas-flow-analyzer'

// ---------- 连线类型校验（spec 5.4.2） ----------

/**
 * 新增节点类型（tts/subtitle/compose）只接受特定类型的入边。
 * 返回 null 表示校验通过，返回字符串表示错误信息。
 *
 * 规则：
 *   - tts      只接受 text 入边
 *   - subtitle 只接受 text 入边（产出 SRT 文本，不做视频 ASR）
 *   - compose  必须有且仅有一个 video 入边；可选 tts 和 subtitle 入边各最多一个
 *   - text/image/video/audio/config 保持现有行为（不限制）
 */
function validateConnectionTypes(sourceType: string, targetType: string): string | null {
  // script（脚本节点）只允许出边到 config（批量派生生成配置）
  if (sourceType === 'script' && targetType !== 'config') {
    return '脚本节点只能连接到生成配置节点'
  }
  const ALLOWED_INPUTS: Record<string, string[]> = {
    tts: ['text'],
    subtitle: ['text'],
    compose: ['video', 'tts', 'subtitle'],
  }
  const allowed = ALLOWED_INPUTS[targetType]
  if (!allowed) return null // 非新增类型不校验

  if (!allowed.includes(sourceType)) {
    const targetLabel = { tts: '配音', subtitle: '字幕', compose: '成片合成' }[targetType] || targetType
    const sourceLabel = { text: '文本', image: '图片', video: '视频', audio: '音频', config: '配置', tts: '配音', subtitle: '字幕', compose: '合成', script: '脚本' }[sourceType] || sourceType
    return `${targetLabel}节点不接受 ${sourceLabel} 类型输入`
  }
  return null
}

// ---------- 本地类型定义 ----------

/** 画布面板（节点） */
export interface CanvasPanel {
  id: string
  workspace_id?: string | null
  type?: string
  name?: string
  x: number
  y: number
  width: number
  height: number
  zIndex: number
  content: Record<string, unknown>
  meta?: Record<string, unknown>
  is_locked?: boolean
  is_hidden?: boolean
  created_at: string
  updated_at: string
}

/** 画布连线 */
export interface CanvasConnection {
  id: string
  workspace_id?: string | null
  source_panel_id: string
  target_panel_id: string
  type: string
  /** 数据传递配置（可选） */
  data_mapping?: {
    source_field: string
    target_field: string
  }[]
  created_at: string
  [key: string]: unknown
}

/** 画布步骤（流程分组） */
export interface CanvasStep {
  id: string
  name: string
  description?: string
  color?: string
  panel_ids: string[]
  order: number
  depends_on: string[]
  status?: 'pending' | 'running' | 'success' | 'failed'
  created_at: string
  updated_at: string
}

/** 画布流程图 */
interface CanvasFlow {
  id: string
  name: string
  workspace_id: string
  steps: CanvasStep[]
  created_at: string
  updated_at: string
}

/** 画布工作区 */
interface CanvasWorkspace {
  id: string
  name: string
  created_at: string
  updated_at: string
  viewport: Viewport
  panels: CanvasPanel[]
  connections: CanvasConnection[]
}

/** 视口 */
interface Viewport {
  x: number
  y: number
  zoom: number
}

/** 画布容器位置偏移 */
interface CanvasRect {
  left: number
  top: number
}

/** 历史快照 */
interface HistorySnapshot {
  viewport: Viewport
  panels: CanvasPanel[]
  connections: CanvasConnection[]
}

/** 历史（撤销/重做） */
interface History {
  past: HistorySnapshot[]
  future: HistorySnapshot[]
}

/** 拖拽连线状态 */
interface ConnectingState {
  sourcePanelId: string
  sourceAnchorType: string
  startWorld: { x: number; y: number }
  endWorld: { x: number; y: number }
  /** 框选批量接入：随主连线一起预览/接入的其他选中节点 id */
  extraSourceIds?: string[]
}

/** 待创建连线载荷 */
/** 主题 token 类型（对齐 canvas-theme.ts 的 CanvasTheme 结构） */
interface ThemeTokens {
  canvas: { background: string; dot: string; line: string; selectionStroke: string; selectionFill: string }
  node: { label: string; fill: string; panel: string; stroke: string; activeStroke: string; placeholder: string; text: string; muted: string; faint: string }
  toolbar: { panel: string; border: string; item: string; itemHover: string; activeBg: string; activeText: string }
}

// ---------- 常量 ----------
const MAX_HISTORY = 80

// ---------- 工具函数 ----------

/** 生成唯一 ID */
function uid(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
}

/** 深拷贝快照（panels / connections / viewport） */
function snapshot(state: CanvasState): HistorySnapshot {
  return {
    viewport: { ...state.viewport },
    panels: JSON.parse(JSON.stringify(state.panels)),
    connections: JSON.parse(JSON.stringify(state.connections)),
  }
}

/** 从快照恢复状态 */
function restoreFromSnapshot(state: CanvasState, snap: HistorySnapshot): void {
  state.viewport = { ...snap.viewport }
  state.panels = JSON.parse(JSON.stringify(snap.panels))
  state.connections = JSON.parse(JSON.stringify(snap.connections))
}

/**
 * 深合并（仅合并普通对象；数组与基本类型用右侧值覆盖）
 * - 供 updatePanel 的 content 深度合并使用
 */

/** 类型谓词：判断值是否为普通对象（非数组、非null） */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** 类型谓词：背景模式值 */
function isBackgroundMode(value: unknown): value is 'dots' | 'lines' | 'blank' {
  return typeof value === 'string' && (['dots', 'lines', 'blank'] as readonly string[]).includes(value)
}

function deepMerge(target: Record<string, unknown> | null | undefined, source: Record<string, unknown> | null | undefined): Record<string, unknown> {
  if (!source || typeof source !== 'object') return target ?? source ?? {}
  if (Array.isArray(source)) {
    const arrResult: Record<string, unknown> = {}
    for (let i = 0; i < source.length; i++) {
      arrResult[String(i)] = source[i]
    }
    return arrResult
  }
  if (!target || typeof target !== 'object' || Array.isArray(target)) {
    return JSON.parse(JSON.stringify(source))
  }
  const out: Record<string, unknown> = JSON.parse(JSON.stringify(target))
  for (const key of Object.keys(source)) {
    const sv = source[key]
    if (isPlainObject(sv)) {
      out[key] = deepMerge(isPlainObject(out[key]) ? out[key] : {}, sv)
    } else {
      out[key] = sv
    }
  }
  return out
}

// ---------- State 接口 ----------
interface CanvasState {
  // ---------- 工作区 ----------
  workspaces: CanvasWorkspace[]
  activeWorkspaceId: string | null

  // ---------- 主题 ----------
  themeMode: 'dark' | 'light'

  // ---------- 节点与连线 ----------
  panels: CanvasPanel[]
  connections: CanvasConnection[]

  // ---------- 视口 ----------
  viewport: Viewport

  // ---------- 画布容器在屏幕中的位置偏移（用于坐标转换） ----------
  canvasRect: CanvasRect

  // ---------- 选中 ----------
  selectedPanelIds: string[]
  selectedPanelId: string | null
  selectedConnectionId: string | null

  // ---------- 文本编辑（外部触发节点进入编辑模式） ----------
  // 当值等于某 panel.id 时，对应 CanvasNode 自动进入文本编辑态
  editingPanelId: string | null

  // ---------- 分镜向导（外部触发脚本节点打开向导） ----------
  // 当值等于某 script panel.id 时，对应 ScriptNodeContent 自动打开分镜向导，消费后置空
  openScriptWizardId: string | null

  // ---------- 背景 ----------
  backgroundMode: 'dots' | 'lines' | 'blank'

  // ---------- 显示图片信息 ----------
  showImageInfo: boolean

  // ---------- 历史 ----------
  history: History

  // ---------- 交互状态 ----------
  _isSpacePressed: boolean
  _isDraggingPanel: boolean

  // ---------- 连线拖拽（临时连线状态）----------
  connecting: ConnectingState | null

  // 连线类型校验失败时的错误信息（供调用方读取显示提示）
  lastConnectionError: string | null

  // ---------- 搜索与筛选 ----------
  searchQuery: string

  // ---------- 流程模式 ----------
  isFlowMode: boolean
  steps: CanvasStep[]
  flows: CanvasFlow[]

  // ---------- 持久化标记 ----------
  _storageReady: boolean

  // ---------- 防递归标记 ----------
  _isSaving: boolean
}

export const useCanvasStore = defineStore('canvas', {
  state: (): CanvasState => ({
    // ---------- 工作区 ----------
    workspaces: [],
    activeWorkspaceId: null,

    // ---------- 主题 ----------
    themeMode: 'dark',

    // ---------- 节点与连线 ----------
    panels: [],
    connections: [],

    // ---------- 视口 ----------
    viewport: { x: 0, y: 0, zoom: 1 },

    // ---------- 画布容器在屏幕中的位置偏移（用于坐标转换） ----------
    canvasRect: { left: 0, top: 0 },

    // ---------- 选中 ----------
    selectedPanelIds: [],
    selectedPanelId: null,
    selectedConnectionId: null,

    // ---------- 文本编辑（外部触发节点进入编辑模式） ----------
    // 当值等于某 panel.id 时，对应 CanvasNode 自动进入文本编辑态
    editingPanelId: null,

    // ---------- 分镜向导（外部触发脚本节点打开向导） ----------
    // 当值等于某 script panel.id 时，对应 ScriptNodeContent 自动打开分镜向导，消费后置空
    openScriptWizardId: null,

    // ---------- 背景 ----------
    backgroundMode: 'dots',

    // ---------- 显示图片信息 ----------
    showImageInfo: false,

    // ---------- 历史 ----------
    history: { past: [], future: [] },

    // ---------- 交互状态 ----------
    _isSpacePressed: false,
    _isDraggingPanel: false,

    // ---------- 连线拖拽（临时连线状态）----------
    connecting: null,

    // 连线类型校验错误信息
    lastConnectionError: null,

    // ---------- 搜索与筛选 ----------
    searchQuery: '',

    // ---------- 流程模式 ----------
    isFlowMode: false,
    steps: new Array<CanvasStep>(),
    flows: new Array<CanvasFlow>(),

    // ---------- 持久化标记 ----------
    _storageReady: false,

    // ---------- 防递归标记 ----------
    _isSaving: false,
  }),

  getters: {
    /** 当前激活的工作区 */
    activeWorkspace(state): CanvasWorkspace | null {
      return state.workspaces.find((w) => w.id === state.activeWorkspaceId) ?? null
    },

    /** 当前画布主题 token 对象（来自 canvasThemes） */
    canvasTheme(state): ThemeTokens {
      return canvasThemes[state.themeMode] ?? canvasThemes.dark
    },

    /** 当前选中的面板对象列表（按 selectedPanelIds 顺序） */
    selectedPanels(state): CanvasPanel[] {
      if (state.selectedPanelIds.length === 0) return []
      const map = new Map(state.panels.map((p) => [p.id, p]))
      const result: CanvasPanel[] = []
      for (const id of state.selectedPanelIds) {
        const p = map.get(id)
        if (p) result.push(p)
      }
      return result
    },

    /** 视口内的可见面板（性能优化） */
    visiblePanels(state): CanvasPanel[] {
      const { x, y, zoom } = state.viewport
      const viewWidth = window.innerWidth
      const viewHeight = window.innerHeight
      const left = -x / zoom
      const top = -y / zoom
      const right = left + viewWidth / zoom
      const bottom = top + viewHeight / zoom
      return state.panels.filter((p) => {
        const pRight = p.x + p.width
        const pBottom = p.y + p.height
        return !(pRight < left || p.x > right || pBottom < top || p.y > bottom)
      })
    },

    /**
     * 获取接入某个目标节点的源节点列表（带序号，按连接创建顺序排序）
     * 返回 Map：sourcePanelId -> index (1-based)
     */
    getInputNodeIndices: (state) => (targetPanelId: string): Map<string, number> => {
      const result = new Map<string, number>()
      const incomingConns = state.connections
        .filter(c => c.target_panel_id === targetPanelId)
        .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
      let idx = 1
      for (const conn of incomingConns) {
        if (!result.has(conn.source_panel_id)) {
          result.set(conn.source_panel_id, idx++)
        }
      }
      return result
    },

    /**
     * 获取接入某个目标节点的源节点数组（按序号排序，含序号信息）
     */
    getInputNodesWithIndex: (state) => (targetPanelId: string): Array<{ panel: CanvasPanel; index: number }> => {
      const indexMap = new Map<string, number>()
      const incomingConns = state.connections
        .filter(c => c.target_panel_id === targetPanelId)
        .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
      let idx = 1
      const orderedIds: string[] = []
      for (const conn of incomingConns) {
        if (!indexMap.has(conn.source_panel_id)) {
          indexMap.set(conn.source_panel_id, idx++)
          orderedIds.push(conn.source_panel_id)
        }
      }
      const result: Array<{ panel: CanvasPanel; index: number }> = []
      for (const sourceId of orderedIds) {
        const panel = state.panels.find(p => p.id === sourceId)
        const index = indexMap.get(sourceId)
        if (panel && index) {
          result.push({ panel, index })
        }
      }
      return result
    },

    // ==================== 流程模式 ====================

    /**
     * 获取分析后的步骤列表（按执行顺序排序）
     * - 自动分析节点连线，识别执行顺序
     * - 返回 CanvasStep[] 数组
     */
    analyzedSteps(state): CanvasStep[] {
      if (!state.isFlowMode || state.panels.length === 0) return []
      
      // 使用静态导入的函数
      return analyzeFlow(state.panels, state.connections)
    },
  },

  actions: {
    // ==================== 主题 ====================

    /** 切换主题模式：'dark' | 'light'（同步联动全局主题，保证标题栏/页脚一起切换） */
    setThemeMode(mode: 'dark' | 'light'): void {
      if (mode === 'dark' || mode === 'light') {
        this.themeMode = mode
        this._save()
        // 联动全局主题 store：同步切换 <html> class 和 Element Plus 主题
        // 这样标题栏、页脚、Element Plus 组件都会跟着画布一起变深/变浅
        useThemeStore().setMode(mode)
      }
    },

    /** 从全局主题同步到画布（仅更新画布内部状态，不反向调用 theme store，避免循环） */
    syncFromGlobalTheme(mode: 'dark' | 'light'): void {
      if ((mode === 'dark' || mode === 'light') && this.themeMode !== mode) {
        this.themeMode = mode
        this._save()
      }
    },

    /** 切换背景模式：'dots' | 'lines' | 'blank'（对齐参考项目 dots/lines/blank） */
    setBackgroundMode(mode: 'dots' | 'lines' | 'blank'): void {
      if (['dots', 'lines', 'blank'].includes(mode)) {
        this.backgroundMode = mode
        this._save()
      }
    },

    /** 切换图片信息显示开关 */
    toggleImageInfo(): void {
      this.showImageInfo = !this.showImageInfo
      this._save()
    },

    // ==================== 工作区 ====================

    /** 创建并切换到新工作区 */
    createWorkspace(name?: string): CanvasWorkspace {
      const ws: CanvasWorkspace = {
        id: uid(),
        name: name ?? '未命名工作区',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        viewport: { x: 0, y: 0, zoom: 1 },
        panels: [],
        connections: [],
      }
      this.workspaces.push(ws)
      this.activeWorkspaceId = ws.id
      this.viewport = { ...ws.viewport }
      this.panels = []
      this.connections = []
      this.selectedPanelIds = []
      this.selectedPanelId = null
      this.history = { past: [], future: [] }
      this._save()
      return ws
    },

    /** 切换到指定工作区（保存当前、加载目标） */
    switchWorkspace(id: string): void {
      // 先保存当前工作区的数据到 workspaces
      this._syncCurrentWorkspace()

      this.activeWorkspaceId = id
      const target = this.workspaces.find((w) => w.id === id)
      if (target) {
        this.viewport = { ...target.viewport }
        this.panels = JSON.parse(JSON.stringify(target.panels))
        this.connections = JSON.parse(JSON.stringify(target.connections))
      } else {
        this.viewport = { x: 0, y: 0, zoom: 1 }
        this.panels = []
        this.connections = []
      }
      this.selectedPanelIds = []
      this.selectedPanelId = null
      this.history = { past: [], future: [] }
      this._save()
    },

    /** 删除工作区 */
    deleteWorkspace(id: string): void {
      const idx = this.workspaces.findIndex((w) => w.id === id)
      if (idx === -1) return
      this.workspaces.splice(idx, 1)
      if (id === this.activeWorkspaceId) {
        if (this.workspaces.length > 0) {
          this.switchWorkspace(this.workspaces[0].id)
        } else {
          this.activeWorkspaceId = null
          this.viewport = { x: 0, y: 0, zoom: 1 }
          this.panels = []
          this.connections = []
          this.selectedPanelIds = []
          this.selectedPanelId = null
          this.history = { past: [], future: [] }
        }
      }
      this._save()
    },

    /** 重命名工作区 */
    renameWorkspace(id: string, name: string): void {
      const ws = this.workspaces.find((w) => w.id === id)
      if (!ws) return
      const trimmed = (name ?? '').trim()
      if (!trimmed) return
      ws.name = trimmed
      ws.updated_at = new Date().toISOString()
      this._save()
    },

    /**
     * 复制工作区（深拷贝当前画布的所有 panels/connections/viewport）
     * - 重新生成所有 panel id 和 connection id，避免 id 冲突
     * - 同步更新 connections 中的 source_panel_id / target_panel_id 引用
     * - 同步更新 config 节点 composerContent / prompt 中的 @[node:xxx] 引用
     * - 新画布追加到列表末尾并切换过去
     * @param name 新画布名称（由调用方拼好后缀，避免 store 依赖 i18n）
     */
    duplicateWorkspace(id: string, name?: string): string | null {
      const ws = this.workspaces.find((w) => w.id === id)
      if (!ws) return null

      // 先保存当前画布状态（避免复制的是旧数据）
      this._syncCurrentWorkspace()

      // 重新生成 panel id 和 connection id
      const idMap = new Map<string, string>()
      const newPanels: CanvasPanel[] = JSON.parse(JSON.stringify(ws.panels))
      newPanels.forEach(p => {
        const oldId = p.id
        const newId = uid()
        idMap.set(oldId, newId)
        p.id = newId
      })
      const newConnections: CanvasConnection[] = JSON.parse(JSON.stringify(ws.connections))
      newConnections.forEach(c => {
        c.id = uid()
        c.source_panel_id = idMap.get(c.source_panel_id) || c.source_panel_id
        c.target_panel_id = idMap.get(c.target_panel_id) || c.target_panel_id
      })
      // 更新 config 节点中的 @[node:xxx] 引用
      const nodeRefPattern = /@\[node:([^\]]+)\]/g
      newPanels.forEach(panel => {
        if (panel.type === 'config' && panel.content) {
          const updateRef = (text: string): string => {
            if (!text) return text
            return text.replace(nodeRefPattern, (match, oldNodeId: string) => {
              const newNodeId = idMap.get(oldNodeId)
              return newNodeId ? `@[node:${newNodeId}]` : match
            })
          }
          const cc = panel.content.composerContent
          if (typeof cc === 'string') panel.content.composerContent = updateRef(cc)
          const pp = panel.content.prompt
          if (typeof pp === 'string') panel.content.prompt = updateRef(pp)
        }
      })

      const newWs: CanvasWorkspace = {
        id: uid(),
        name: name || ws.name,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        viewport: { ...ws.viewport },
        panels: newPanels,
        connections: newConnections,
      }
      this.workspaces.push(newWs)
      this.switchWorkspace(newWs.id)
      return newWs.id
    },

    /**
     * 导出指定工作区为 JSON 字符串（不影响当前画布状态）
     * - 不要求该工作区是当前激活的
     */
    exportWorkspaceById(id: string): string | null {
      const ws = this.workspaces.find((w) => w.id === id)
      if (!ws) return null
      const data = {
        version: 1,
        exportedAt: new Date().toISOString(),
        workspace: {
          id: ws.id,
          name: ws.name,
          viewport: { ...ws.viewport },
          panels: JSON.parse(JSON.stringify(ws.panels)),
          connections: JSON.parse(JSON.stringify(ws.connections)),
        },
      }
      return JSON.stringify(data, null, 2)
    },

    /** 批量删除工作区（不切换当前激活的画布除非被删） */
    deleteWorkspaces(ids: string[]): void {
      const idSet = new Set(ids)
      const wasActiveDeleted = idSet.has(this.activeWorkspaceId || '')
      this.workspaces = this.workspaces.filter(w => !idSet.has(w.id))
      if (wasActiveDeleted) {
        if (this.workspaces.length > 0) {
          this.switchWorkspace(this.workspaces[0].id)
        } else {
          this.activeWorkspaceId = null
          this.viewport = { x: 0, y: 0, zoom: 1 }
          this.panels = []
          this.connections = []
          this.selectedPanelIds = []
          this.selectedPanelId = null
          this.history = { past: [], future: [] }
        }
      }
      this._save()
    },

    // ==================== 视口 ====================

    /** 平移画布（世界坐标增量） */
    pan(dx: number, dy: number): void {
      this.viewport.x += Number(dx) || 0
      this.viewport.y += Number(dy) || 0
    },

    /** 设置缩放（可选以中心点为缩放中心；范围 5%-500%，对齐参考项目） */
    setZoom(zoom: number, center: { x: number; y: number } | null = null): void {
      const oldZoom = this.viewport.zoom
      const newZoom = Math.min(5, Math.max(0.05, Number(zoom) || oldZoom))
      if (center) {
        this.viewport.x = center.x - ((center.x - this.viewport.x) / oldZoom) * newZoom
        this.viewport.y = center.y - ((center.y - this.viewport.y) / oldZoom) * newZoom
      }
      this.viewport.zoom = newZoom
    },

    /** 重置视口 */
    resetView(): void {
      this.viewport = { x: 0, y: 0, zoom: 1 }
    },

    /** 屏幕坐标 → 世界坐标 */
    /** 屏幕坐标(clientX/clientY) → 世界坐标，自动减去画布容器偏移 */
    screenToWorld(sx: number, sy: number): { x: number; y: number } {
      const lx = sx - this.canvasRect.left
      const ly = sy - this.canvasRect.top
      return {
        x: (lx - this.viewport.x) / this.viewport.zoom,
        y: (ly - this.viewport.y) / this.viewport.zoom,
      }
    },

    /** 世界坐标 → 屏幕坐标(clientX/clientY)，自动加上画布容器偏移 */
    worldToScreen(wx: number, wy: number): { x: number; y: number } {
      return {
        x: wx * this.viewport.zoom + this.viewport.x + this.canvasRect.left,
        y: wy * this.viewport.zoom + this.viewport.y + this.canvasRect.top,
      }
    },

    /** 更新画布容器在屏幕中的位置偏移（由 InfiniteCanvas 组件调用） */
    setCanvasRect(rect: { left: number; top: number }): void {
      this.canvasRect = { left: rect.left, top: rect.top }
    },

    // ==================== 节点操作 ====================

    /** 添加面板（自动生成 id / workspace_id / zIndex / 时间戳） */
    addPanel(input: Partial<CanvasPanel> & { x: number; y: number; width: number; height: number }): string {
      if (!this.activeWorkspaceId) {
        this.createWorkspace('画布 1')
      }
      const panel: CanvasPanel = {
        id: uid(),
        workspace_id: this.activeWorkspaceId!,
        zIndex: this.panels.length + 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        content: {},
        x: input.x,
        y: input.y,
        width: input.width,
        height: input.height,
        type: input.type,
        name: input.name,
        meta: input.meta,
        is_locked: input.is_locked,
        is_hidden: input.is_hidden,
      }
      if (input.content && typeof input.content === 'object') {
        panel.content = input.content
      }
      this.panels.push(panel)
      this._save()
      return panel.id
    },

    /** 更新面板（顶层浅合并；content 深合并） */
    updatePanel(id: string, changes: Partial<CanvasPanel>): void {
      const panel = this.panels.find((p) => p.id === id)
      if (!panel || !changes) return
      let mergedChanges = changes
      if (changes.content && typeof changes.content === 'object') {
        mergedChanges = {
          ...changes,
          content: deepMerge(panel.content ?? {}, changes.content),
        }
      }
      Object.assign(panel, mergedChanges, { updated_at: new Date().toISOString() })
      this._save()
    },

    /** 直接写回（不压历史快照）：拖动/缩放等高频操作 */
    _updatePanelDirect(id: string, changes: Partial<CanvasPanel>): void {
      const panel = this.panels.find((p) => p.id === id)
      if (!panel) return
      Object.assign(panel, changes, { updated_at: new Date().toISOString() })
    },

    /** 删除面板（同时清理相关连线） */
    deletePanel(id: string): void {
      this.connections = this.connections.filter(
        (c) => c.source_panel_id !== id && c.target_panel_id !== id,
      )
      this.panels = this.panels.filter((p) => p.id !== id)
      this.selectedPanelIds = this.selectedPanelIds.filter((pid) => pid !== id)
      if (this.selectedPanelId === id) this.selectedPanelId = null
      this._save()
    },

    /** 清空所有面板 */
    clearAllPanels(): void {
      if (this.panels.length === 0) return
      this.connections = []
      this.panels = []
      this.selectedPanelIds = []
      this.selectedPanelId = null
    },

    /** 复制单个面板（向右下偏移 20 像素；副本不带 lineage，避免同一 shotId 出现两个节点） */
    duplicatePanel(id: string): string | undefined {
      const orig = this.panels.find((p) => p.id === id)
      if (!orig) return
      const content: Record<string, unknown> = JSON.parse(JSON.stringify(orig.content ?? {}))
      delete content.lineage
      return this.addPanel({
        ...orig,
        x: orig.x + 20,
        y: orig.y + 20,
        content,
      })
    },

    /** 复制所有选中面板（向右下偏移，整体选中） */
    duplicateSelectedPanels(): string[] {
      if (this.selectedPanelIds.length === 0) return []
      const idSet = new Set(this.selectedPanelIds)
      const origs = this.panels.filter((p) => idSet.has(p.id))
      const maxZ = Math.max(...this.panels.map((p) => p.zIndex || 0), 0)
      const now = new Date().toISOString()
      const newIds: string[] = []
      for (let i = 0; i < origs.length; i++) {
        const orig = origs[i]
        // 副本不带 lineage，避免同一 shotId 在画布上出现两个节点
        const content: Record<string, unknown> = JSON.parse(JSON.stringify(orig.content ?? {}))
        delete content.lineage
        const newPanel: CanvasPanel = {
          ...orig,
          id: uid(),
          workspace_id: this.activeWorkspaceId!,
          x: orig.x + 20,
          y: orig.y + 20,
          zIndex: maxZ + i + 1,
          content,
          created_at: now,
          updated_at: now,
        }
        this.panels.push(newPanel)
        newIds.push(newPanel.id)
      }
      this.selectedPanelIds = newIds
      this.selectedPanelId = newIds[0] ?? null
      this._save()
      return newIds
    },

    // ==================== 选中 ====================

    /** 选中面板（append=true 时与已有选中叠加） */
    selectPanel(id: string | null, { append = false }: { append?: boolean } = {}): void {
      if (append) {
        const idx = this.selectedPanelIds.indexOf(id!)
        if (idx >= 0) {
          this.selectedPanelIds.splice(idx, 1)
        } else if (id) {
          this.selectedPanelIds.push(id)
        }
      } else {
        this.selectedPanelIds = id ? [id] : []
      }
      this.selectedPanelId = this.selectedPanelIds[0] ?? null
      if (!append && id) {
        const panel = this.panels.find((p) => p.id === id)
        if (panel) {
          panel.zIndex = Math.max(...this.panels.map((p) => p.zIndex || 0), 0) + 1
        }
      }
    },

    /** 清空所有选中 */
    clearSelection(): void {
      this.selectedPanelIds = []
      this.selectedPanelId = null
    },

    /** 框选：所有中心点落在 rect 内的面板 */
    selectPanelsInRect({ startWorld, endWorld }: { startWorld: { x: number; y: number }; endWorld: { x: number; y: number } }, { append = false }: { append?: boolean } = {}): void {
      const left = Math.min(startWorld.x, endWorld.x)
      const right = Math.max(startWorld.x, endWorld.x)
      const top = Math.min(startWorld.y, endWorld.y)
      const bottom = Math.max(startWorld.y, endWorld.y)

      const matched = this.panels
        .filter((p) => {
          const cx = p.x + p.width / 2
          const cy = p.y + p.height / 2
          return cx >= left && cx <= right && cy >= top && cy <= bottom
        })
        .map((p) => p.id)

      if (append) {
        const set = new Set(this.selectedPanelIds)
        for (const id of matched) set.add(id)
        this.selectedPanelIds = [...set]
      } else {
        this.selectedPanelIds = matched
      }
      this.selectedPanelId = this.selectedPanelIds[0] ?? null
    },

    // ==================== 连线 ====================

    /** 添加连线 */
    addConnection({ source_panel_id, target_panel_id, type = 'manual', ...rest }: { source_panel_id: string; target_panel_id: string; type?: string; [key: string]: unknown }): CanvasConnection | null {
      if (!source_panel_id || !target_panel_id) return null

      // 连线类型校验（spec 5.4.2）
      // 新增的 tts/subtitle/compose 节点只接受特定类型的入边
      const sourcePanel = this.panels.find((p) => p.id === source_panel_id)
      const targetPanel = this.panels.find((p) => p.id === target_panel_id)
      if (sourcePanel && targetPanel) {
        const sourceType = sourcePanel.type || 'text'
        const targetType = targetPanel.type || 'text'
        const validationError = validateConnectionTypes(sourceType, targetType)
        if (validationError) {
          // 校验失败：返回 null，调用方可读取 lastConnectionError 显示提示
          this.lastConnectionError = validationError
          return null
        }
      }

      const conn: CanvasConnection = {
        id: uid(),
        workspace_id: this.activeWorkspaceId,
        source_panel_id,
        target_panel_id,
        type,
        ...rest,
        created_at: new Date().toISOString(),
      }
      this.connections.push(conn)
      this._save()
      return conn
    },

    /** 删除连线 */
    deleteConnection(id: string): void {
      this.connections = this.connections.filter((c) => c.id !== id)
      this._save()
    },

    /** 开始拖拽连线：记录源节点和锚点类型；extraSourceIds 为框选批量接入的其他选中节点 */
    startConnecting(sourcePanelId: string, anchorType: string, extraSourceIds: string[] = []): void {
      const source = this.panels.find((p) => p.id === sourcePanelId)
      if (!source) return
      // 源节点锚点的世界坐标（中心左/右）
      const x = anchorType === 'source'
        ? source.x + source.width
        : source.x
      const y = source.y + source.height / 2
      this.connecting = {
        sourcePanelId,
        sourceAnchorType: anchorType,
        startWorld: { x, y },
        endWorld: { x, y },
        extraSourceIds: extraSourceIds.filter((id) => id !== sourcePanelId),
      }
    },

    /** 更新拖拽连线的终点坐标 */
    updateConnecting(worldX: number, worldY: number): void {
      if (!this.connecting) return
      this.connecting.endWorld = { x: worldX, y: worldY }
    },

    /** 完成连线：在源节点和目标节点之间创建一条连接 */
    endConnecting(targetPanelId: string, targetAnchorType: string): void {
      if (!this.connecting) return
      const sourceId = this.connecting.sourcePanelId
      const sourceAnchor = this.connecting.sourceAnchorType
      this.connecting = null
      if (!targetPanelId || targetPanelId === sourceId) return
      // 确定真正的 source/target：source 锚点代表输出，target 锚点代表输入
      let realSource: string, realTarget: string
      if (sourceAnchor === 'source') {
        realSource = sourceId
        realTarget = targetPanelId
      } else {
        realSource = targetPanelId
        realTarget = sourceId
      }
      // 防止重复
      const exists = this.connections.some(
        (c) => c.source_panel_id === realSource && c.target_panel_id === realTarget,
      )
      if (exists) return
      const conn = this.addConnection({
        source_panel_id: realSource,
        target_panel_id: realTarget,
        type: 'flow',
      })
      // 连线类型校验失败时，endConnecting 不抛错（addConnection 已设 lastConnectionError）
      // 调用方（CanvasView）应在调 endConnecting 后检查 store.lastConnectionError 显示提示
      if (!conn && this.lastConnectionError) {
        // 错误信息保留在 state 里供调用方读取，这里不清理
        return
      }
    },

    /** 取消当前拖拽连线 */
    cancelConnecting(): void {
      this.connecting = null
    },

    // ==================== 待创建连线 ====================

    // ==================== 历史（撤销/重做） ====================

    /** 压入历史快照（最多 80 条；清空 future） */
    pushSnapshot(): void {
      const snap = snapshot(this)
      this.history.past.push(snap)
      if (this.history.past.length > MAX_HISTORY) {
        this.history.past.shift()
      }
      this.history.future = []
    },

    /** 撤销 */
    undo(): void {
      if (this.history.past.length === 0) return
      const currentSnap = snapshot(this)
      this.history.future.push(currentSnap)
      const prevSnap = this.history.past.pop()!
      restoreFromSnapshot(this, prevSnap)
      this._save()
    },

    /** 重做 */
    redo(): void {
      if (this.history.future.length === 0) return
      const currentSnap = snapshot(this)
      this.history.past.push(currentSnap)
      const nextSnap = this.history.future.pop()!
      restoreFromSnapshot(this, nextSnap)
      this._save()
    },

    // ==================== 搜索与定位 ====================

    /** 设置搜索关键字 */
    setSearchQuery(q: string): void {
      this.searchQuery = typeof q === 'string' ? q : ''
    },

    /** 将指定面板置于视口中心（不缩放） */
    centerOnPanel(id: string): void {
      const panel = this.panels.find((p) => p.id === id)
      if (!panel) return
      const { zoom } = this.viewport
      const cx = panel.x + panel.width / 2
      const cy = panel.y + panel.height / 2
      const viewWidth = window.innerWidth
      const viewHeight = window.innerHeight
      this.viewport.x = viewWidth / 2 - cx * zoom
      this.viewport.y = viewHeight / 2 - cy * zoom
    },

    // ==================== 隐藏 ====================

    // ==================== 网格 ====================

    // ==================== 对齐参考线 ====================

    // ==================== 锁定 ====================

    // ==================== 图片节点拆分 ====================

    // ==================== 旋转 ====================

    // ==================== 复制粘贴 ====================

    // ==================== 导入导出 ====================

    /** 导出当前画布为 JSON 字符串 */
    exportJSON(): string {
      const data = {
        version: 1,
        exportedAt: new Date().toISOString(),
        workspace: {
          id: this.activeWorkspaceId,
          name: this.activeWorkspace?.name ?? 'untitled',
          viewport: { ...this.viewport },
          panels: JSON.parse(JSON.stringify(this.panels)),
          connections: JSON.parse(JSON.stringify(this.connections)),
        },
      }
      return JSON.stringify(data, null, 2)
    },

    /** 从 JSON 字符串导入画布（替换当前 panels/connections/viewport） */
    importJSON(jsonStr: string): { panels: number; connections: number } {
      let data: Record<string, unknown>
      try {
        data = JSON.parse(jsonStr)
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : String(e)
        throw new Error('JSON 解析失败: ' + message)
      }
      const ws = data.workspace
      if (!ws || typeof ws !== 'object' || Array.isArray(ws) || !('panels' in ws) || !('connections' in ws)) {
        throw new Error('JSON 结构不合法（缺少 workspace 或 workspace.panels / workspace.connections）')
      }
      const wsObj = ws as Record<string, unknown>
      if (wsObj.viewport && typeof wsObj.viewport === 'object') {
        this.viewport = { ...this.viewport, ...(wsObj.viewport as Viewport) }
      }
      this.panels = JSON.parse(JSON.stringify(wsObj.panels))
      this.connections = JSON.parse(JSON.stringify(wsObj.connections))
      this.selectedPanelIds = []
      this.selectedPanelId = null
      this._save()
      return {
        panels: this.panels.length,
        connections: this.connections.length,
      }
    },

    // ==================== 持久化 hydrate ====================

    /** 从存储加载数据填充 state（幂等，_storageReady 标记避免重复加载） */
    async _hydrateFromStorage(): Promise<void> {
      if (this._storageReady) return
      try {
        const rawData = await loadCanvas()
        if (rawData && typeof rawData === 'object') {
          const data = rawData as unknown as Record<string, unknown>
          if (Array.isArray(data.workspaces)) this.workspaces = data.workspaces as CanvasWorkspace[]
          if ('activeWorkspaceId' in rawData) {
            const id = rawData.activeWorkspaceId
            this.activeWorkspaceId = typeof id === 'string' || typeof id === 'number' ? String(id) : null
          }
          // themeMode 不从 localforage 恢复：全局主题 store（localStorage）是唯一真相源，
          // 由 App.vue 的 watch(immediate) 同步过来，避免 localforage 旧值覆盖全局主题
          const bgMode = rawData.backgroundMode
          if (isBackgroundMode(bgMode)) {
            this.backgroundMode = bgMode
          }
          if (typeof rawData.showImageInfo === 'boolean') {
            this.showImageInfo = rawData.showImageInfo
          }
          if (rawData.viewport && typeof rawData.viewport === 'object') {
            this.viewport = { ...this.viewport, ...(rawData.viewport as Viewport) }
          }
          if (Array.isArray(rawData.panels)) this.panels = rawData.panels as CanvasPanel[]
          if (Array.isArray(rawData.connections)) this.connections = rawData.connections as CanvasConnection[]
          // 加载完成后同步一次：确保 workspaces 中当前工作区数据与顶层一致
          // 避免旧版本数据中 workspaces 与顶层不同步，导致切换工作区时丢失数据
          this._syncCurrentWorkspace()
        }
      } catch (err: unknown) {
        // eslint-disable-next-line no-console
        console.warn('[canvas] 持久化加载失败', err)
      }
      this._storageReady = true
    },

    /**
     * 将顶层的 panels/connections/viewport 同步到 workspaces 中的当前工作区
     * - 日常操作只修改顶层数据，保存前调用此函数确保 workspaces 数据同步
     * - 避免切换工作区时丢失数据
     */
    _syncCurrentWorkspace(): void {
      const current = this.workspaces.find((w) => w.id === this.activeWorkspaceId)
      if (!current) return
      current.viewport = { ...this.viewport }
      current.panels = JSON.parse(JSON.stringify(this.panels))
      current.connections = JSON.parse(JSON.stringify(this.connections))
      current.updated_at = new Date().toISOString()
    },

    /** 统一保存入口：先同步当前工作区数据，再防抖写入存储 */
    _save(): void {
      // 防递归保护：避免 _syncCurrentWorkspace 中响应式更新意外触发新的 _save 调用
      if (this._isSaving) return
      this._isSaving = true
      try {
        this._syncCurrentWorkspace()
        saveCanvas(this)
      } finally {
        this._isSaving = false
      }
    },

    /**
     * 用户切换时切换画布数据空间
     * - 切换 localforage 中的 user key
     * - 重置 _storageReady 并重新 hydrate
     */
    async _switchUserStorage(userId: number | string | null): Promise<void> {
      // 先取消待执行的保存，避免清空数据过程中误写入空状态
      cancelSaveCanvas()
      switchCanvasUser(userId)
      // 清空当前 state（避免看到上一个用户的数据）
      this.workspaces = []
      this.activeWorkspaceId = null
      this.panels = []
      this.connections = []
      this.selectedPanelId = null
      this.history.past = []
      this.history.future = []
      // 重新 hydrate 新用户数据
      this._storageReady = false
      await this._hydrateFromStorage()
    },

    // ==================== 流程模式 ====================

    /**
     * 切换流程模式
     */
    toggleFlowMode(): void {
      this.isFlowMode = !this.isFlowMode
      if (this.isFlowMode) {
        // 进入流程模式时，自动分析流程
        this.analyzeCurrentFlow()
      }
      this._save()
    },

    /**
     * 分析当前画布的流程，自动生成步骤分组
     */
    analyzeCurrentFlow(): void {
      if (!this.isFlowMode) return

      const steps = analyzeFlow(this.panels, this.connections)
      
      // 保留现有步骤的状态（如自定义名称、颜色等）
      const existingStepMap = new Map(this.steps.map(s => [s.id, s]))
      
      this.steps = steps.map(newStep => {
        const existing = existingStepMap.get(newStep.id)
        if (existing) {
          // 保留用户自定义的信息
          return {
            ...newStep,
            name: existing.name || newStep.name,
            description: existing.description || newStep.description,
            color: existing.color || newStep.color,
            status: existing.status || newStep.status,
          }
        }
        return newStep
      })

      this._save()
    },

    /**
     * 添加步骤
     */
    addStep(step: Partial<CanvasStep>): string {
      const id = step.id || `step_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
      const newStep: CanvasStep = {
        id,
        name: step.name || `步骤 ${this.steps.length + 1}`,
        description: step.description,
        color: step.color || '#409eff',
        panel_ids: step.panel_ids || [],
        order: step.order ?? this.steps.length,
        depends_on: step.depends_on || [],
        status: step.status,
        created_at: step.created_at || new Date().toISOString(),
        updated_at: step.updated_at || new Date().toISOString(),
      }
      
      this.steps.push(newStep)
      this._save()
      return id
    },

    /**
     * 更新步骤
     */
    updateStep(stepId: string, updates: Partial<CanvasStep>): void {
      const index = this.steps.findIndex(s => s.id === stepId)
      if (index === -1) return

      const step = this.steps[index]
      if (updates.name !== undefined) step.name = updates.name
      if (updates.description !== undefined) step.description = updates.description
      if (updates.color !== undefined) step.color = updates.color
      if (updates.panel_ids !== undefined) step.panel_ids = updates.panel_ids
      if (updates.order !== undefined) step.order = updates.order
      if (updates.depends_on !== undefined) step.depends_on = updates.depends_on
      if (updates.status !== undefined) step.status = updates.status
      step.updated_at = new Date().toISOString()

      this._save()
    },

    /**
     * 删除步骤
     */
    removeStep(stepId: string): void {
      const index = this.steps.findIndex(s => s.id === stepId)
      if (index === -1) return

      this.steps.splice(index, 1)
      this._save()
    },

    /**
     * 添加节点到步骤
     */
    addPanelToStep(stepId: string, panelId: string): void {
      const step = this.steps.find(s => s.id === stepId)
      if (!step) return

      if (!step.panel_ids.includes(panelId)) {
        step.panel_ids.push(panelId)
        step.updated_at = new Date().toISOString()
        this._save()
      }
    },
  },
})
