/* =====================================================
 * 无限画布 Pinia Store
 * - 管理多画布工作区、视口状态、面板和连线
 * - 支持撤销/重做历史（最多 50 步）
 * - localStorage 持久化
 * ===================================================== */

import { defineStore } from 'pinia'

// ---------- 常量 ----------
const STORAGE_KEY = 'agnes_canvas_v1'
const MAX_HISTORY = 50

// ---------- 工具函数 ----------

/** 生成唯一 ID */
function uid() {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
}

/** 深拷贝快照 */
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

/** 从 localStorage 恢复 */
function restoreFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {
    // ignore
  }
  return null
}

/** 保存到 localStorage */
function saveToStorage(state) {
  try {
    const data = {
      workspaces: state.workspaces,
      activeWorkspaceId: state.activeWorkspaceId,
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  } catch {
    // ignore
  }
}

export const useCanvasStore = defineStore('canvas', {
  state: () => {
    const saved = restoreFromStorage()
    return {
      // 多画布
      workspaces: saved?.workspaces ?? [],
      activeWorkspaceId: saved?.activeWorkspaceId ?? null,

      // 当前画布状态
      viewport: { x: 0, y: 0, zoom: 1 },
      panels: [],
      connections: [],
      selectedPanelId: null,
      selectedConnectionId: null,

      // 历史记录（撤销/重做）
      history: { past: [], future: [] },

      // 拖拽状态（不持久化）
      _dragging: null,
      _resizing: null,

      // 同步状态
      syncing: false,
      lastSyncedAt: null,
    }
  },

  getters: {
    /** 当前激活的工作区 */
    activeWorkspace(state) {
      return state.workspaces.find((w) => w.id === state.activeWorkspaceId) ?? null
    },

    /** 选中的面板 */
    selectedPanel(state) {
      return state.panels.find((p) => p.id === state.selectedPanelId) ?? null
    },

    /** 视口内的可见面板（性能优化） */
    visiblePanels(state) {
      const { x, y, zoom } = state.viewport
      // 假设视口大小为 1920x1080（实际使用时可按需传入）
      const viewWidth = 1920
      const viewHeight = 1080
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

    /** 某面板的所有连线 */
    panelConnections(state) {
      return (panelId) =>
        state.connections.filter(
          (c) => c.source_panel_id === panelId || c.target_panel_id === panelId,
        )
    },
  },

  actions: {
    // ==================== 画布管理 ====================

    /** 创建新画布 */
    createWorkspace(name) {
      const ws = {
        id: uid(),
        name,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        viewport: { x: 0, y: 0, zoom: 1 },
        panels: [],
        connections: [],
      }
      this.workspaces.push(ws)
      this.switchWorkspace(ws.id)
      saveToStorage(this)
      return ws
    },

    /** 切换到指定画布 */
    switchWorkspace(workspaceId) {
      // 先保存当前画布状态到 workspaces 数组
      const current = this.workspaces.find((w) => w.id === this.activeWorkspaceId)
      if (current) {
        current.viewport = { ...this.viewport }
        current.panels = JSON.parse(JSON.stringify(this.panels))
        current.connections = JSON.parse(JSON.stringify(this.connections))
        current.updated_at = new Date().toISOString()
      }

      this.activeWorkspaceId = workspaceId
      const target = this.workspaces.find((w) => w.id === workspaceId)
      if (target) {
        this.viewport = { ...target.viewport }
        this.panels = JSON.parse(JSON.stringify(target.panels))
        this.connections = JSON.parse(JSON.stringify(target.connections))
      } else {
        this.viewport = { x: 0, y: 0, zoom: 1 }
        this.panels = []
        this.connections = []
      }
      this.selectedPanelId = null
      this.selectedConnectionId = null
      this.history = { past: [], future: [] }
      saveToStorage(this)
    },

    /** 删除画布 */
    deleteWorkspace(workspaceId) {
      const idx = this.workspaces.findIndex((w) => w.id === workspaceId)
      if (idx === -1) return

      this.workspaces.splice(idx, 1)

      // 如果删除的是当前激活的，切换到第一个可用的
      if (workspaceId === this.activeWorkspaceId) {
        if (this.workspaces.length > 0) {
          this.switchWorkspace(this.workspaces[0].id)
        } else {
          this.activeWorkspaceId = null
          this.viewport = { x: 0, y: 0, zoom: 1 }
          this.panels = []
          this.connections = []
        }
      }
      saveToStorage(this)
    },

    // ==================== 视口操作 ====================

    /** 平移画布（接收世界坐标系位移） */
    pan(deltaX, deltaY) {
      this.pushSnapshot()
      this.viewport.x += deltaX
      this.viewport.y += deltaY
    },

    /** 平移画布（接收屏幕坐标系像素位移，自动按 zoom 补偿） */
    panByScreenDelta(dx, dy) {
      const zoom = this.viewport.zoom
      this.viewport.x += dx / zoom
      this.viewport.y += dy / zoom
    },

    /** 缩放画布（以指定中心点为准） */
    zoom(factor, center = null) {
      this.pushSnapshot()
      const oldZoom = this.viewport.zoom
      const newZoom = Math.min(3, Math.max(0.1, oldZoom * factor))

      if (center) {
        // 以鼠标位置为中心缩放
        this.viewport.x = center.x - ((center.x - this.viewport.x) / oldZoom) * newZoom
        this.viewport.y = center.y - ((center.y - this.viewport.y) / oldZoom) * newZoom
      }

      this.viewport.zoom = newZoom
    },

    /** 重置视图 */
    resetView() {
      this.pushSnapshot()
      this.viewport = { x: 0, y: 0, zoom: 1 }
    },

    /** 屏幕坐标 → 世界坐标 */
    screenToWorld(screenX, screenY) {
      return {
        x: (screenX - this.viewport.x) / this.viewport.zoom,
        y: (screenY - this.viewport.y) / this.viewport.zoom,
      }
    },

    /** 世界坐标 → 屏幕坐标 */
    worldToScreen(worldX, worldY) {
      return {
        x: worldX * this.viewport.zoom + this.viewport.x,
        y: worldY * this.viewport.zoom + this.viewport.y,
      }
    },

    // ==================== 面板操作 ====================

    /** 添加面板 */
    addPanel(panel) {
      this.pushSnapshot()
      panel.id = uid()
      panel.workspace_id = this.activeWorkspaceId
      panel.created_at = new Date().toISOString()
      panel.updated_at = new Date().toISOString()
      panel.zIndex = this.panels.length + 1
      this.panels.push(panel)
    },

    /** 更新面板 */
    updatePanel(id, changes) {
      this.pushSnapshot()
      const panel = this.panels.find((p) => p.id === id)
      if (panel) {
        Object.assign(panel, changes, { updated_at: new Date().toISOString() })
      }
    },

    /** 删除面板 */
    deletePanel(id) {
      this.pushSnapshot()
      // 同时删除关联的连线
      this.connections = this.connections.filter(
        (c) => c.source_panel_id !== id && c.target_panel_id !== id,
      )
      this.panels = this.panels.filter((p) => p.id !== id)
      if (this.selectedPanelId === id) this.selectedPanelId = null
    },

    /** 复制面板 */
    duplicatePanel(id) {
      const orig = this.panels.find((p) => p.id === id)
      if (!orig) return
      this.addPanel({
        ...orig,
        x: orig.x + 20,
        y: orig.y + 20,
        content: { ...orig.content },
      })
    },

    /** 选中面板 */
    selectPanel(id) {
      this.selectedPanelId = id
      this.selectedConnectionId = null
      // 自动置顶
      const panel = this.panels.find((p) => p.id === id)
      if (panel) {
        panel.zIndex = Math.max(...this.panels.map((p) => p.zIndex || 0), 0) + 1
      }
    },

    /** 将面板提到最前 */
    movePanelToFront(id) {
      const panel = this.panels.find((p) => p.id === id)
      if (panel) {
        panel.zIndex = Math.max(...this.panels.map((p) => p.zIndex || 0), 0) + 1
      }
    },

    // ==================== 连线操作 ====================

    /** 添加连线 */
    addConnection(connection) {
      this.pushSnapshot()
      connection.id = uid()
      connection.workspace_id = this.activeWorkspaceId
      connection.created_at = new Date().toISOString()
      this.connections.push(connection)
    },

    /** 删除连线 */
    deleteConnection(id) {
      this.pushSnapshot()
      this.connections = this.connections.filter((c) => c.id !== id)
      if (this.selectedConnectionId === id) this.selectedConnectionId = null
    },

    /** 自动连线 */
    autoConnect(sourceId, targetId) {
      // 检查是否已存在
      const exists = this.connections.find(
        (c) =>
          c.source_panel_id === sourceId &&
          c.target_panel_id === targetId &&
          c.type === 'auto',
      )
      if (exists) return exists

      this.addConnection({
        source_panel_id: sourceId,
        target_panel_id: targetId,
        type: 'auto',
        source_anchor: 'bottom-right',
        target_anchor: 'top-left',
      })
      return this.connections[this.connections.length - 1]
    },

    // ==================== 撤销/重做 ====================

    /** 压入历史快照 */
    pushSnapshot() {
      const snap = snapshot(this)
      this.history.past.push(snap)
      if (this.history.past.length > MAX_HISTORY) {
        this.history.past.shift()
      }
      this.history.future = [] // 新操作清空重做栈
    },

    /** 撤销 */
    undo() {
      if (this.history.past.length === 0) return
      const currentSnap = snapshot(this)
      this.history.future.push(currentSnap)
      const prevSnap = this.history.past.pop()
      restoreFromSnapshot(this, prevSnap)
    },

    /** 重做 */
    redo() {
      if (this.history.future.length === 0) return
      const currentSnap = snapshot(this)
      this.history.past.push(currentSnap)
      const nextSnap = this.history.future.pop()
      restoreFromSnapshot(this, nextSnap)
    },

    // ==================== 同步 ====================

    /** 开始自动同步（定时器） */
    startAutoSync() {
      // TODO: 后端 API 集成
    },

    /** 停止自动同步 */
    stopAutoSync() {
      // TODO: 清除定时器
    },
  },
})
