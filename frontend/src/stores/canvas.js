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
import { loadCanvas, saveCanvas } from '@/lib/canvas-storage'

// ---------- 常量 ----------
const MAX_HISTORY = 80

// ---------- 工具函数 ----------

/** 生成唯一 ID */
function uid() {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
}

/** 深拷贝快照（panels / connections / viewport） */
function snapshot(state) {
  return {
    viewport: { ...state.viewport },
    panels: JSON.parse(JSON.stringify(state.panels)),
    connections: JSON.parse(JSON.stringify(state.connections)),
  }
}

/** 从快照恢复状态 */
function restoreFromSnapshot(state, snap) {
  state.viewport = { ...snap.viewport }
  state.panels = JSON.parse(JSON.stringify(snap.panels))
  state.connections = JSON.parse(JSON.stringify(snap.connections))
}

/**
 * 深合并（仅合并普通对象；数组与基本类型用右侧值覆盖）
 * - 供 updatePanel 的 content 深度合并使用
 */
function deepMerge(target, source) {
  if (!source || typeof source !== 'object') return target ?? source
  if (Array.isArray(source)) return source
  if (!target || typeof target !== 'object' || Array.isArray(target)) {
    return JSON.parse(JSON.stringify(source))
  }
  const out = JSON.parse(JSON.stringify(target))
  for (const key of Object.keys(source)) {
    const sv = source[key]
    if (sv && typeof sv === 'object' && !Array.isArray(sv)) {
      out[key] = deepMerge(out[key], sv)
    } else {
      out[key] = sv
    }
  }
  return out
}

export const useCanvasStore = defineStore('canvas', {
  state: () => ({
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

    // ---------- 背景 ----------
    backgroundMode: 'dots',

    // ---------- 显示图片信息 ----------
    showImageInfo: false,

    // ---------- 历史 ----------
    history: { past: [], future: [] },

    // ---------- 交互状态 ----------
    _isSpacePressed: false,
    _isDraggingPanel: false,

    // ---------- 待创建连线 ----------
    pendingConnectionCreate: null,

    // ---------- 连线拖拽（临时连线状态）----------
    connecting: null,

    // ---------- 搜索与筛选 ----------
    searchQuery: '',
    searchMatchedIds: [],

    // ---------- 网格 ----------
    showGrid: true,
    gridSize: 24,

    // ---------- 对齐参考线 ----------
    alignmentGuides: { vertical: [], horizontal: [] },

    // ---------- 隐藏 ----------
    hiddenIds: [],

    // ---------- 剪贴板 ----------
    clipboard: [],

    // ---------- 持久化标记 ----------
    _storageReady: false,
  }),

  getters: {
    /** 当前激活的工作区 */
    activeWorkspace(state) {
      return state.workspaces.find((w) => w.id === state.activeWorkspaceId) ?? null
    },

    /** 当前画布主题 token 对象（来自 canvasThemes） */
    canvasTheme(state) {
      return canvasThemes[state.themeMode] ?? canvasThemes.dark
    },

    /** 当前选中的面板对象列表（按 selectedPanelIds 顺序） */
    selectedPanels(state) {
      if (state.selectedPanelIds.length === 0) return []
      const map = new Map(state.panels.map((p) => [p.id, p]))
      const result = []
      for (const id of state.selectedPanelIds) {
        const p = map.get(id)
        if (p) result.push(p)
      }
      return result
    },

    /** 视口内的可见面板（性能优化） */
    visiblePanels(state) {
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

    /** 按 searchQuery 匹配面板列表（匹配 name / content.text / type） */
    matchedPanels(state) {
      const q = (state.searchQuery || '').trim().toLowerCase()
      if (!q) return []
      return state.panels.filter((p) => {
        if ((p.name || '').toLowerCase().includes(q)) return true
        if (p.type && p.type.toLowerCase().includes(q)) return true
        const text = p.content?.text
        if (typeof text === 'string' && text.toLowerCase().includes(q)) return true
        return false
      })
    },

    /**
     * 对齐参考线计算
     * - targetBounds: { x, y, width, height }
     * - otherIds: 参与对齐的其他 panel id 列表
     * - threshold: 对齐阈值（默认 4 像素）
     * - 返回 { x, y, guides: { vertical, horizontal } }
     */
    computeAlignment: (state) => (targetBounds, otherIds, threshold = 4) => {
      const { x, y, width, height } = targetBounds
      const tx = [x, x + width / 2, x + width]
      const ty = [y, y + height / 2, y + height]
      let dx = 0
      let dy = 0
      const vertical = []
      const horizontal = []
      const otherSet = new Set(otherIds)

      for (const other of state.panels) {
        if (!otherSet.has(other.id)) continue
        const ox = [other.x, other.x + other.width / 2, other.x + other.width]
        const oy = [other.y, other.y + other.height / 2, other.y + other.height]

        let snappedX = false
        for (let i = 0; i < 3 && !snappedX; i++) {
          for (let j = 0; j < 3; j++) {
            const diff = ox[j] - tx[i]
            if (Math.abs(diff) <= threshold) {
              dx = diff
              vertical.push(ox[j])
              snappedX = true
              break
            }
          }
        }

        let snappedY = false
        for (let i = 0; i < 3 && !snappedY; i++) {
          for (let j = 0; j < 3; j++) {
            const diff = oy[j] - ty[i]
            if (Math.abs(diff) <= threshold) {
              dy = diff
              horizontal.push(oy[j])
              snappedY = true
              break
            }
          }
        }
      }

      return {
        x: x + dx,
        y: y + dy,
        guides: {
          vertical: [...new Set(vertical)],
          horizontal: [...new Set(horizontal)],
        },
      }
    },

    /**
     * 返回上游节点的 output 数组
     * - 规则：source_panel_id → target_panel_id 即"上游 → 下游"
     * - 每项：{ panel, output }
     */
    getUpstreamOutput: (state) => (panelId) => {
      const upstreamIds = state.connections
        .filter((c) => c.target_panel_id === panelId)
        .map((c) => c.source_panel_id)
        .filter(Boolean)

      return upstreamIds
        .map((pid) => {
          const panel = state.panels.find((p) => p.id === pid)
          if (!panel) return null
          const content = panel.content ?? {}
          let output
          switch (panel.type) {
            case 'image':
              output = {
                resultUrl: content.resultUrl,
                prompt: content.prompt,
                model: content.model,
                size: content.size,
                imageUrl: content.imageUrl,
              }
              break
            case 'video':
              output = {
                resultUrl: content.resultUrl,
                prompt: content.prompt,
                imageUrl: content.imageUrl,
              }
              break
            case 'audio':
              output = {
                resultUrl: content.resultUrl,
                prompt: content.prompt,
              }
              break
            case 'text':
              output = { text: content.text, prompt: content.prompt }
              break
            case 'chat':
              output = {
                lastReply: content.lastReply,
                messages: content.messages ?? [],
              }
              break
            case 'config':
              output = {
                model: content.model,
                size: content.size,
                count: content.count,
                composerContent: content.composerContent,
              }
              break
            default:
              output = { ...content }
          }
          return { panel, output }
        })
        .filter(Boolean)
    },

    /**
     * 把上游节点的核心字段合并成一个 { prompt, model, size, imageUrl, resultUrl } 对象
     */
    resolveInputs: (state) => (panelId) => {
      const panel = state.panels.find((p) => p.id === panelId)
      if (!panel) return null
      const upstreamIds = state.connections
        .filter((c) => c.target_panel_id === panelId)
        .map((c) => c.source_panel_id)
        .filter(Boolean)

      const merged = JSON.parse(JSON.stringify(panel.content ?? {}))
      for (const pid of upstreamIds) {
        const up = state.panels.find((p) => p.id === pid)
        if (!up) continue
        const content = up.content ?? {}
        const output = {}
        if (content.resultUrl !== undefined) output.resultUrl = content.resultUrl
        if (content.imageUrl !== undefined) output.imageUrl = content.imageUrl
        if (content.prompt !== undefined) output.prompt = content.prompt
        if (content.model !== undefined) output.model = content.model
        if (content.size !== undefined) output.size = content.size
        if (content.text !== undefined) output.text = content.text
        if (content.lastReply !== undefined) output.lastReply = content.lastReply
        if (content.count !== undefined) output.count = content.count
        Object.assign(merged, output)
      }
      return merged
    },
  },

  actions: {
    // ==================== 主题 ====================

    /** 切换主题模式：'dark' | 'light' */
    setThemeMode(mode) {
      if (mode === 'dark' || mode === 'light') {
        this.themeMode = mode
        saveCanvas(this)
      }
    },

    /** 切换背景模式：'dots' | 'lines' | 'blank'（对齐参考项目 dots/lines/blank） */
    setBackgroundMode(mode) {
      if (['dots', 'lines', 'blank'].includes(mode)) {
        this.backgroundMode = mode
        saveCanvas(this)
      }
    },

    /** 切换图片信息显示开关 */
    toggleImageInfo() {
      this.showImageInfo = !this.showImageInfo
      saveCanvas(this)
    },

    // ==================== 工作区 ====================

    /** 创建并切换到新工作区 */
    createWorkspace(name) {
      const ws = {
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
      saveCanvas(this)
      return ws
    },

    /** 切换到指定工作区（保存当前、加载目标） */
    switchWorkspace(id) {
      const current = this.workspaces.find((w) => w.id === this.activeWorkspaceId)
      if (current) {
        current.viewport = { ...this.viewport }
        current.panels = JSON.parse(JSON.stringify(this.panels))
        current.connections = JSON.parse(JSON.stringify(this.connections))
        current.updated_at = new Date().toISOString()
      }

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
      saveCanvas(this)
    },

    /** 删除工作区 */
    deleteWorkspace(id) {
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
      saveCanvas(this)
    },

    /** 重命名工作区 */
    renameWorkspace(id, name) {
      const ws = this.workspaces.find((w) => w.id === id)
      if (!ws) return
      const trimmed = (name ?? '').trim()
      if (!trimmed) return
      ws.name = trimmed
      ws.updated_at = new Date().toISOString()
      saveCanvas(this)
    },

    // ==================== 视口 ====================

    /** 平移画布（世界坐标增量） */
    pan(dx, dy) {
      this.viewport.x += Number(dx) || 0
      this.viewport.y += Number(dy) || 0
    },

    /** 设置缩放（可选以中心点为缩放中心；范围 5%-500%，对齐参考项目） */
    setZoom(zoom, center = null) {
      const oldZoom = this.viewport.zoom
      const newZoom = Math.min(5, Math.max(0.05, Number(zoom) || oldZoom))
      if (center) {
        this.viewport.x = center.x - ((center.x - this.viewport.x) / oldZoom) * newZoom
        this.viewport.y = center.y - ((center.y - this.viewport.y) / oldZoom) * newZoom
      }
      this.viewport.zoom = newZoom
    },

    /** 重置视口 */
    resetView() {
      this.viewport = { x: 0, y: 0, zoom: 1 }
    },

    /** 屏幕坐标 → 世界坐标 */
    /** 屏幕坐标(clientX/clientY) → 世界坐标，自动减去画布容器偏移 */
    screenToWorld(sx, sy) {
      const lx = sx - this.canvasRect.left
      const ly = sy - this.canvasRect.top
      return {
        x: (lx - this.viewport.x) / this.viewport.zoom,
        y: (ly - this.viewport.y) / this.viewport.zoom,
      }
    },

    /** 世界坐标 → 屏幕坐标(clientX/clientY)，自动加上画布容器偏移 */
    worldToScreen(wx, wy) {
      return {
        x: wx * this.viewport.zoom + this.viewport.x + this.canvasRect.left,
        y: wy * this.viewport.zoom + this.viewport.y + this.canvasRect.top,
      }
    },

    /** 更新画布容器在屏幕中的位置偏移（由 InfiniteCanvas 组件调用） */
    setCanvasRect(rect) {
      this.canvasRect = { left: rect.left, top: rect.top }
    },

    // ==================== 节点操作 ====================

    /** 添加面板（自动生成 id / workspace_id / zIndex / 时间戳） */
    addPanel(panel) {
      if (!this.activeWorkspaceId) {
        this.createWorkspace('画布 1')
      }
      panel.id = uid()
      panel.workspace_id = this.activeWorkspaceId
      panel.zIndex = this.panels.length + 1
      panel.created_at = new Date().toISOString()
      panel.updated_at = new Date().toISOString()
      if (!panel.content || typeof panel.content !== 'object') {
        panel.content = {}
      }
      this.panels.push(panel)
      saveCanvas(this)
      return panel.id
    },

    /** 更新面板（顶层浅合并；content 深合并） */
    updatePanel(id, changes) {
      const panel = this.panels.find((p) => p.id === id)
      if (!panel || !changes) return
      if (changes.content && typeof changes.content === 'object') {
        changes = {
          ...changes,
          content: deepMerge(panel.content ?? {}, changes.content),
        }
      }
      Object.assign(panel, changes, { updated_at: new Date().toISOString() })
      saveCanvas(this)
    },

    /** 直接写回（不压历史快照）：拖动/缩放等高频操作 */
    _updatePanelDirect(id, changes) {
      const panel = this.panels.find((p) => p.id === id)
      if (!panel) return
      Object.assign(panel, changes, { updated_at: new Date().toISOString() })
    },

    /** 删除面板（同时清理相关连线） */
    deletePanel(id) {
      this.connections = this.connections.filter(
        (c) => c.source_panel_id !== id && c.target_panel_id !== id,
      )
      this.panels = this.panels.filter((p) => p.id !== id)
      this.selectedPanelIds = this.selectedPanelIds.filter((pid) => pid !== id)
      if (this.selectedPanelId === id) this.selectedPanelId = null
      saveCanvas(this)
    },

    /** 清空所有面板 */
    clearAllPanels() {
      if (this.panels.length === 0) return
      this.connections = []
      this.panels = []
      this.selectedPanelIds = []
      this.selectedPanelId = null
    },

    /** 复制单个面板（向右下偏移 20 像素） */
    duplicatePanel(id) {
      const orig = this.panels.find((p) => p.id === id)
      if (!orig) return
      return this.addPanel({
        ...orig,
        x: orig.x + 20,
        y: orig.y + 20,
        content: JSON.parse(JSON.stringify(orig.content ?? {})),
      })
    },

    /** 复制所有选中面板（向右下偏移，整体选中） */
    duplicateSelectedPanels() {
      if (this.selectedPanelIds.length === 0) return []
      const idSet = new Set(this.selectedPanelIds)
      const origs = this.panels.filter((p) => idSet.has(p.id))
      const maxZ = Math.max(...this.panels.map((p) => p.zIndex || 0), 0)
      const now = new Date().toISOString()
      const newIds = []
      for (let i = 0; i < origs.length; i++) {
        const orig = origs[i]
        const newPanel = {
          ...orig,
          id: uid(),
          workspace_id: this.activeWorkspaceId,
          x: orig.x + 20,
          y: orig.y + 20,
          zIndex: maxZ + i + 1,
          content: JSON.parse(JSON.stringify(orig.content ?? {})),
          created_at: now,
          updated_at: now,
        }
        this.panels.push(newPanel)
        newIds.push(newPanel.id)
      }
      this.selectedPanelIds = newIds
      this.selectedPanelId = newIds[0] ?? null
      saveCanvas(this)
      return newIds
    },

    // ==================== 选中 ====================

    /** 选中面板（append=true 时与已有选中叠加） */
    selectPanel(id, { append = false } = {}) {
      if (append) {
        const idx = this.selectedPanelIds.indexOf(id)
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
    clearSelection() {
      this.selectedPanelIds = []
      this.selectedPanelId = null
    },

    /** 框选：所有中心点落在 rect 内的面板 */
    selectPanelsInRect({ startWorld, endWorld }, { append = false } = {}) {
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

    /** 将面板置顶 */
    movePanelToFront(id) {
      const panel = this.panels.find((p) => p.id === id)
      if (!panel) return
      panel.zIndex = Math.max(...this.panels.map((p) => p.zIndex || 0), 0) + 1
    },

    // ==================== 连线 ====================

    /** 添加连线 */
    addConnection({ source_panel_id, target_panel_id, type = 'manual', ...rest }) {
      if (!source_panel_id || !target_panel_id) return null
      const conn = {
        id: uid(),
        workspace_id: this.activeWorkspaceId,
        source_panel_id,
        target_panel_id,
        type,
        ...rest,
        created_at: new Date().toISOString(),
      }
      this.connections.push(conn)
      saveCanvas(this)
      return conn
    },

    /** 删除连线 */
    deleteConnection(id) {
      this.connections = this.connections.filter((c) => c.id !== id)
      saveCanvas(this)
    },

    /** 开始拖拽连线：记录源节点和锚点类型 */
    startConnecting(sourcePanelId, anchorType) {
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
      }
    },

    /** 更新拖拽连线的终点坐标 */
    updateConnecting(worldX, worldY) {
      if (!this.connecting) return
      this.connecting.endWorld = { x: worldX, y: worldY }
    },

    /** 完成连线：在源节点和目标节点之间创建一条连接 */
    endConnecting(targetPanelId, targetAnchorType) {
      if (!this.connecting) return
      const sourceId = this.connecting.sourcePanelId
      const sourceAnchor = this.connecting.sourceAnchorType
      this.connecting = null
      if (!targetPanelId || targetPanelId === sourceId) return
      // 确定真正的 source/target：source 锚点代表输出，target 锚点代表输入
      let realSource, realTarget
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
      this.addConnection({
        source_panel_id: realSource,
        target_panel_id: realTarget,
        type: 'flow',
      })
    },

    /** 取消当前拖拽连线 */
    cancelConnecting() {
      this.connecting = null
    },

    // ==================== 待创建连线 ====================

    /** 设置待创建连线状态 */
    setPendingConnectionCreate(payload) {
      this.pendingConnectionCreate = payload ?? null
    },

    /** 清空待创建连线状态 */
    clearPendingConnectionCreate() {
      this.pendingConnectionCreate = null
    },

    /** 从待创建连线状态生成一个新节点，并建立连线 */
    createConnectedNode(type, pending) {
      if (!pending) return
      const { sourceId, worldX, worldY } = pending
      const width = 260
      const height = type === 'image' ? 260 : 220
      const panel = {
        id: uid(),
        workspace_id: this.activeWorkspaceId,
        type,
        name: `新${type === 'image' ? '图片' : type === 'text' ? '文本' : '笔记'}节点`,
        x: worldX - width / 2,
        y: worldY - height / 2,
        width,
        height,
        zIndex: (this.panels.reduce((m, p) => Math.max(m, p.zIndex || 0), 0)) + 1,
        content: {},
        meta: {},
        is_locked: false,
        is_hidden: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
      this.panels.push(panel)
      if (sourceId) {
        this.addConnection({
          source_panel_id: sourceId,
          target_panel_id: panel.id,
          type: 'flow',
        })
      }
      this.selectedPanelIds = [panel.id]
      this.selectedPanelId = panel.id
      this.pendingConnectionCreate = null
      this.pushSnapshot()
      saveCanvas(this)
      return panel
    },

    // ==================== 历史（撤销/重做） ====================

    /** 压入历史快照（最多 80 条；清空 future） */
    pushSnapshot() {
      const snap = snapshot(this)
      this.history.past.push(snap)
      if (this.history.past.length > MAX_HISTORY) {
        this.history.past.shift()
      }
      this.history.future = []
    },

    /** 撤销 */
    undo() {
      if (this.history.past.length === 0) return
      const currentSnap = snapshot(this)
      this.history.future.push(currentSnap)
      const prevSnap = this.history.past.pop()
      restoreFromSnapshot(this, prevSnap)
      saveCanvas(this)
    },

    /** 重做 */
    redo() {
      if (this.history.future.length === 0) return
      const currentSnap = snapshot(this)
      this.history.past.push(currentSnap)
      const nextSnap = this.history.future.pop()
      restoreFromSnapshot(this, nextSnap)
      saveCanvas(this)
    },

    // ==================== 搜索与定位 ====================

    /** 设置搜索关键字 */
    setSearchQuery(q) {
      this.searchQuery = typeof q === 'string' ? q : ''
      if (!this.searchQuery) {
        this.searchMatchedIds = []
      }
    },

    /** 执行搜索并定位首个匹配项 */
    searchAndLocate(q) {
      this.setSearchQuery(q)
      const matched = this.matchedPanels
      this.searchMatchedIds = matched.map((p) => p.id)
      if (matched.length > 0) {
        this.centerOnPanel(matched[0].id)
      }
    },

    /** 将指定面板置于视口中心（不缩放） */
    centerOnPanel(id) {
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

    /** 设置面板隐藏状态 */
    setPanelHidden(id, hidden) {
      if (!id) return
      const idx = this.hiddenIds.indexOf(id)
      if (hidden) {
        if (idx === -1) this.hiddenIds.push(id)
      } else {
        if (idx >= 0) this.hiddenIds.splice(idx, 1)
      }
    },

    // ==================== 网格 ====================

    /** 切换是否启用网格 */
    toggleGrid() {
      this.showGrid = !this.showGrid
    },

    /** 设置网格大小（限幅 4~128） */
    setGridSize(size) {
      const n = Number(size)
      if (!isFinite(n) || n <= 0) return
      this.gridSize = Math.min(128, Math.max(4, n))
    },

    /** 网格吸附（返回吸附后的坐标） */
    snapToGrid(x, y) {
      if (!this.showGrid) return { x, y }
      const g = this.gridSize
      return {
        x: Math.round(x / g) * g,
        y: Math.round(y / g) * g,
      }
    },

    // ==================== 对齐参考线 ====================

    /** 设置当前对齐参考线 */
    setAlignmentGuides(guides) {
      this.alignmentGuides = guides ?? { vertical: [], horizontal: [] }
    },

    /** 清空对齐参考线 */
    clearAlignmentGuides() {
      this.alignmentGuides = { vertical: [], horizontal: [] }
    },

    // ==================== 锁定 ====================

    /** 切换锁定状态 */
    toggleLock(id) {
      const panel = this.panels.find((p) => p.id === id)
      if (!panel) return
      const current = !!panel.content?.locked
      this._updatePanelDirect(id, {
        content: { ...(panel.content ?? {}), locked: !current },
      })
    },

    /** 锁定面板 */
    lockPanel(id) {
      const panel = this.panels.find((p) => p.id === id)
      if (!panel) return
      this._updatePanelDirect(id, {
        content: { ...(panel.content ?? {}), locked: true },
      })
    },

    /** 解锁面板 */
    unlockPanel(id) {
      const panel = this.panels.find((p) => p.id === id)
      if (!panel) return
      this._updatePanelDirect(id, {
        content: { ...(panel.content ?? {}), locked: false },
      })
    },

    // ==================== 图片节点拆分 ====================

    /** 将图片节点分割成 n 个小节点（位置错开） */
    splitImagePanel(id, n = 4) {
      const orig = this.panels.find((p) => p.id === id)
      if (!orig) return []
      const count = Math.max(1, Number(n) || 4)
      const maxZ = Math.max(...this.panels.map((p) => p.zIndex || 0), 0)
      const now = new Date().toISOString()
      const newIds = []
      for (let i = 0; i < count; i++) {
        const newPanel = {
          ...orig,
          id: uid(),
          x: orig.x + 30 + i * 20,
          y: orig.y + 30 + i * 20,
          zIndex: maxZ + i + 1,
          content: JSON.parse(JSON.stringify(orig.content ?? {})),
          created_at: now,
          updated_at: now,
        }
        this.panels.push(newPanel)
        newIds.push(newPanel.id)
      }
      saveCanvas(this)
      return newIds
    },

    // ==================== 旋转 ====================

    /** 设置面板旋转角度（0/90/180/270） */
    setPanelRotation(id, degrees) {
      const allowed = [0, 90, 180, 270]
      const r = Number(degrees)
      if (!allowed.includes(r)) return
      const panel = this.panels.find((p) => p.id === id)
      if (!panel) return
      this._updatePanelDirect(id, {
        content: { ...(panel.content ?? {}), rotation: r },
      })
    },

    // ==================== 复制粘贴 ====================

    /** 复制面板到剪贴板（不传 id 则复制选中） */
    copyToClipboard(id) {
      const ids = id ? [id] : [...this.selectedPanelIds]
      if (ids.length === 0) return
      this.clipboard = this.panels
        .filter((p) => ids.includes(p.id))
        .map((p) => JSON.parse(JSON.stringify(p)))
    },

    /** 粘贴剪贴板到指定屏幕坐标（以首个面板左上角为锚点） */
    pastePanel(screenX, screenY) {
      if (!Array.isArray(this.clipboard) || this.clipboard.length === 0) return
      const world = this.screenToWorld(screenX, screenY)
      const anchor = this.clipboard[0]
      const offsetX = world.x - (anchor.x || 0)
      const offsetY = world.y - (anchor.y || 0)
      const maxZ = Math.max(...this.panels.map((p) => p.zIndex || 0), 0)
      const now = new Date().toISOString()
      const newIds = []
      for (let i = 0; i < this.clipboard.length; i++) {
        const item = this.clipboard[i]
        const copy = {
          ...JSON.parse(JSON.stringify(item)),
          id: uid(),
          x: (item.x || 0) + offsetX,
          y: (item.y || 0) + offsetY,
          workspace_id: this.activeWorkspaceId,
          zIndex: maxZ + i + 1,
          created_at: now,
          updated_at: now,
        }
        this.panels.push(copy)
        newIds.push(copy.id)
      }
      this.selectedPanelIds = newIds
      this.selectedPanelId = newIds[0] ?? null
      saveCanvas(this)
    },

    // ==================== 导入导出 ====================

    /** 导出当前画布为 JSON 字符串 */
    exportJSON() {
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
    importJSON(jsonStr) {
      let data
      try {
        data = JSON.parse(jsonStr)
      } catch (e) {
        throw new Error('JSON 解析失败: ' + e.message)
      }
      const ws = data?.workspace
      if (!ws || !Array.isArray(ws.panels) || !Array.isArray(ws.connections)) {
        throw new Error('JSON 结构不合法（缺少 workspace.panels 或 workspace.connections）')
      }
      if (ws.viewport && typeof ws.viewport === 'object') {
        this.viewport = { ...this.viewport, ...ws.viewport }
      }
      this.panels = JSON.parse(JSON.stringify(ws.panels))
      this.connections = JSON.parse(JSON.stringify(ws.connections))
      this.selectedPanelIds = []
      this.selectedPanelId = null
      saveCanvas(this)
      return {
        panels: this.panels.length,
        connections: this.connections.length,
      }
    },

    // ==================== 持久化 hydrate ====================

    /** 从存储加载数据填充 state（幂等，_storageReady 标记避免重复加载） */
    async _hydrateFromStorage() {
      if (this._storageReady) return
      try {
        const data = await loadCanvas()
        if (data && typeof data === 'object') {
          if (Array.isArray(data.workspaces)) this.workspaces = data.workspaces
          if ('activeWorkspaceId' in data) this.activeWorkspaceId = data.activeWorkspaceId
          if (data.themeMode === 'dark' || data.themeMode === 'light') {
            this.themeMode = data.themeMode
          }
          if (data.viewport && typeof data.viewport === 'object') {
            this.viewport = { ...this.viewport, ...data.viewport }
          }
          if (Array.isArray(data.panels)) this.panels = data.panels
          if (Array.isArray(data.connections)) this.connections = data.connections
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn('[canvas] 持久化加载失败', err)
      }
      this._storageReady = true
    },
  },
})
