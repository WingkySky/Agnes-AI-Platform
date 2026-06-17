/* =====================================================
 * 无限画布 Pinia Store
 * - 管理多画布工作区、视口状态、面板和连线
 * - 支持撤销/重做历史（最多 50 步）
 * - 支持背景模式切换（点阵 / 网格 / 空白，不持久化）
 * - 持久化由 lib/canvas-storage.js 负责（localforage + 400ms 防抖）
 * ===================================================== */

import { defineStore } from 'pinia'
import { canvasThemes } from '@/lib/canvas-theme'
import { loadCanvas, saveCanvas, migrateFromV1, isStorageReady } from '@/lib/canvas-storage'

// ---------- 常量 ----------
const V1_STORAGE_KEY = 'agnes_canvas_v1'
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

/** 从 localStorage 同步恢复 v1 数据（仅作为 state() 的 fallback，异步 hydrate 会覆盖）
 *  - 当前 v1 schema 只持久化 workspaces / activeWorkspaceId / themeMode
 */
function restoreFromStorageSync() {
  try {
    const raw = localStorage.getItem(V1_STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {
    // ignore
  }
  return null
}

/**
 * 异步从 localforage 拉取完整画布数据（v2 schema：含 panels / connections / viewport）
 * 供 _hydrateFromStorage() 在 onMounted 阶段调用，覆盖 v1 fallback
 */
async function restoreFromStorage() {
  return await loadCanvas()
}

/** 保存到 localforage（由 lib/canvas-storage.js 内部做 400ms 防抖）
 *  - 保留函数签名兼容旧调用，行为已切换到 localforage
 */
function saveToStorage(state) {
  saveCanvas(state)
}

export const useCanvasStore = defineStore('canvas', {
  state: () => {
    // 同步 v1 fallback：仅恢复 workspaces / activeWorkspaceId / themeMode
    // 完整状态（panels / connections / viewport）由 onMounted 阶段的 _hydrateFromStorage() 异步覆盖
    const saved = restoreFromStorageSync()
    return {
      // 多画布
      workspaces: saved?.workspaces ?? [],
      activeWorkspaceId: saved?.activeWorkspaceId ?? null,

      // 画布主题模式：'dark' | 'light'
      themeMode: saved?.themeMode ?? 'dark',

      // 当前画布状态
      viewport: { x: 0, y: 0, zoom: 1 },
      panels: [],
      connections: [],
      // 选中状态：selectedPanelId 兼容旧 API（始终等于 selectedPanelIds[0]）
      // 新增 selectedPanelIds 作为多选数据源；两者在所有 action 中同步维护
      selectedPanelId: null,
      selectedPanelIds: [],
      selectedConnectionId: null,
      // 框选矩形（世界坐标），用于 Ctrl/Cmd + 拖动框选可视化
      selectionBox: null,
      // 画布背景模式：'dot' | 'grid' | 'blank'（不持久化，刷新后回默认）
      backgroundMode: 'dot',

      // 历史记录（撤销/重做）
      history: { past: [], future: [] },

      // 拖拽状态（不持久化）
      _dragging: null,        // { type: 'panel' | 'resize', ... }
      _resizing: null,
      _connecting: null,       // { sourcePanelId, anchorType: 'input'|'output', worldX, worldY }

      // 待创建连线状态：从节点锚点拖线到空白松手后弹出创建菜单
      // { sourcePanelId, anchorType: 'source' | 'target', worldX, worldY }
      pendingConnectionCreate: null,

      // 交互护栏：拖动面板期间，画布绝对不能平移
      _isDraggingPanel: false,
      // 空格键按下状态：临时进入平移模式
      _isSpacePressed: false,

      // 同步状态
      syncing: false,
      lastSyncedAt: null,

      // ===== Task 2: 画布成熟化扩展 state（均不持久化） =====

      // 任务 3 搜索与筛选
      searchQuery: '',                // 当前搜索关键字
      filterTypes: [],                // 选中的类型集合；空数组表示全部显示
      searchMatchedIds: [],           // 当前匹配的 panel id 列表（计算后）
      searchHighlightUntil: 0,        // 搜索高亮到期时间戳（Date.now() + 1500）

      // 任务 7 网格
      showGrid: true,                 // 是否启用网格吸附
      gridSize: 24,                   // 网格大小（限幅 4~128）

      // 任务 6 对齐参考线
      alignmentGuides: { vertical: [], horizontal: [] }, // 当前拖动中的对齐参考线（世界坐标）

      // 任务 4 隐藏
      hiddenIds: [],                  // 被隐藏的 panel id 集合（用数组实现 Set 行为）

      // Frame 模式
      enteredFrameId: null,           // 当前进入的 Frame id；null 表示不在 Frame 内部

      // ===== Task 5: 持久化状态 =====
      _storageReady: false,           // localforage 是否就绪，由 _hydrateFromStorage() 翻转

      // ===== Task 6/7/8: 自动连线 / 批量子节点预览 =====
      // pendingAutoConnect: { sourcePanelId, targetPanelId, timer }
      // - 用于"拖线悬停/松手"等场景的延迟自动连线；
      // - 同一时刻只允许一个待执行任务，新的 enqueue 会替换旧的。
      pendingAutoConnect: null,

      // batchExpanded: { [parentId]: true | false }
      // - 记录每个 config / batch 父节点的展开/折叠状态
      // - 不持久化，刷新后回默认（折叠）
      batchExpanded: {},

      // 右键菜单剪贴板：存放复制的 panel 深拷贝数组（不持久化）
      // - copyToClipboard 时写入；pastePanel 时读取并基于屏幕坐标创建副本
      clipboard: [],
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

    /** 多选时的面板对象列表（按 selectedPanelIds 顺序） */
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
      // 使用实际视口尺寸（从 window 获取）
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

    /** 某面板的所有连线 */
    panelConnections(state) {
      return (panelId) =>
        state.connections.filter(
          (c) => c.source_panel_id === panelId || c.target_panel_id === panelId,
        )
    },

    /** 所有面板的边界矩形（用于 Minimap） */
    canvasBounds(state) {
      // 修复：bounds 合并所有面板 + 当前视口的可见范围，
      // 这样无论视口移到哪，视口框始终在 minimap 内可见
      let minX = -Infinity, minY = -Infinity
      let maxX = Infinity, maxY = Infinity

      // 面板边界
      if (state.panels.length > 0) {
        minX = Infinity; minY = Infinity
        maxX = -Infinity; maxY = -Infinity
        for (const p of state.panels) {
          minX = Math.min(minX, p.x)
          minY = Math.min(minY, p.y)
          maxX = Math.max(maxX, p.x + p.width)
          maxY = Math.max(maxY, p.y + p.height)
        }
      }

      // 视口在世界坐标中的范围
      const { x, y, zoom } = state.viewport
      const viewWidth = window.innerWidth
      const viewHeight = window.innerHeight
      const vpLeft = -x / zoom
      const vpTop = -y / zoom
      const vpRight = vpLeft + viewWidth / zoom
      const vpBottom = vpTop + viewHeight / zoom

      minX = Math.min(minX, vpLeft)
      minY = Math.min(minY, vpTop)
      maxX = Math.max(maxX, vpRight)
      maxY = Math.max(maxY, vpBottom)

      // 防止 NaN/Infinity
      if (!isFinite(minX)) {
        return { left: -500, top: -500, width: 1000, height: 1000 }
      }

      // 扩展 200px 边距，让空白区域也有意义
      const padding = 200
      return {
        left: minX - padding,
        top: minY - padding,
        width: (maxX - minX) + padding * 2,
        height: (maxY - minY) + padding * 2,
      }
    },

    /** 当前视口在画布中的矩形（用于 Minimap 高亮） */
    viewportRect(state) {
      const { x, y, zoom } = state.viewport
      const viewWidth = window.innerWidth
      const viewHeight = window.innerHeight
      return {
        x: -x / zoom,
        y: -y / zoom,
        width: viewWidth / zoom,
        height: viewHeight / zoom,
      }
    },

    /** 当前画布主题 token 对象（来自 canvasThemes） */
    canvasTheme(state) {
      return canvasThemes[state.themeMode] ?? canvasThemes.dark
    },

    /**
     * 联动高亮：根据选中面板 id 返回其上下游相关节点与连线
     * - 节点集合 = 选中面板 + 与之相连的所有邻居面板
     * - 连线集合 = 选中面板参与的所有连线
     * 用于画布上的"选中一个节点 → 上下游高亮"效果
     */
    relatedHighlight: (state) => (panelId) => {
      const empty = { nodes: new Set(), connections: new Set() }
      if (!panelId) return empty
      const exists = state.panels.some((p) => p.id === panelId)
      if (!exists) return empty

      const nodes = new Set([panelId])
      const connections = new Set()
      for (const c of state.connections) {
        if (c.source_panel_id === panelId || c.target_panel_id === panelId) {
          connections.add(c.id)
          const otherId = c.source_panel_id === panelId ? c.target_panel_id : c.source_panel_id
          if (otherId) nodes.add(otherId)
        }
      }
      return { nodes, connections }
    },

    // ===== Task 2: 画布成熟化扩展 getters =====

    /** 检查指定 panel 是否处于隐藏状态 */
    isPanelHidden: (state) => (id) => {
      return state.hiddenIds.includes(id)
    },

    /**
     * 在 visiblePanels 基础上再过滤 hiddenIds 和 filterTypes
     * - filterTypes 为空数组时不过滤类型
     * - 隐藏的 panel 永远不显示
     */
    visiblePanelsFiltered(state) {
      const { x, y, zoom } = state.viewport
      const viewWidth = window.innerWidth
      const viewHeight = window.innerHeight
      const left = -x / zoom
      const top = -y / zoom
      const right = left + viewWidth / zoom
      const bottom = top + viewHeight / zoom

      const hiddenSet = new Set(state.hiddenIds)
      const typeFilter = state.filterTypes.length > 0
        ? new Set(state.filterTypes)
        : null

      return state.panels.filter((p) => {
        if (hiddenSet.has(p.id)) return false
        if (typeFilter && !typeFilter.has(p.type)) return false
        const pRight = p.x + p.width
        const pBottom = p.y + p.height
        return !(pRight < left || p.x > right || pBottom < top || p.y > bottom)
      })
    },

    /**
     * 按 searchQuery 匹配面板列表
     * - 匹配字段：name / content.text / panel.type
     * - 空 query 返回空数组（搜索由组件显式触发）
     */
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

    /** 返回指定 frame 的 children id 列表（若 frame 不存在返回空数组） */
    frameChildren: (state) => (frameId) => {
      if (!frameId) return []
      const frame = state.panels.find((p) => p.id === frameId)
      if (!frame) return []
      return Array.isArray(frame.content?.children) ? frame.content.children : []
    },

    /**
     * 对齐参考线计算
     * - targetBounds: { x, y, width, height }
     * - otherIds: 参与对齐的其他 panel id 列表（不含 target 自身）
     * - threshold: 对齐阈值（默认 4）
     * - 返回 { x, y, guides: { vertical, horizontal } }
     *   修正后的 x/y 是应用了吸附的目标位置
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

        // x 方向：target 的 left/center/right vs other 的 left/center/right
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

        // y 方向同上
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

    // ===== Task 6/7/8: 自动连线 / 批量生成 getter =====

    /** 通过 panelId 查找面板；找不到返回 null */
    getPanel: (state) => (id) => state.panels.find((p) => p.id === id) ?? null,

    /**
     * 返回引用此 panel 的下游 panel id 集合
     * - 解析规则：遍历所有 connections，命中 source_panel_id === panelId 的连线的 target_panel_id
     * - 用于"删除前确认"或"反向高亮"等场景
     */
    references: (state) => (panelId) => {
      const result = new Set()
      if (!panelId) return result
      for (const c of state.connections) {
        if (c.source_panel_id === panelId && c.target_panel_id) {
          result.add(c.target_panel_id)
        }
      }
      return result
    },

    /**
     * 返回指定父节点的批量子节点列表
     * - 父节点的 content.batchChildIds 必须存在
     * - 子节点不存在时按 id 过滤
     */
    batchChildPanels: (state) => (parentId) => {
      if (!parentId) return []
      const parent = state.panels.find((p) => p.id === parentId)
      const ids = Array.isArray(parent?.content?.batchChildIds) ? parent.content.batchChildIds : []
      if (ids.length === 0) return []
      const map = new Map(state.panels.map((p) => [p.id, p]))
      const out = []
      for (const id of ids) {
        const p = map.get(id)
        if (p) out.push(p)
      }
      return out
    },
  },

  actions: {
    // ==================== 画布管理 ====================

    /** 切换画布主题模式：'dark' | 'light' */
    setThemeMode(mode) {
      if (mode === 'dark' || mode === 'light') {
        this.themeMode = mode
        saveToStorage(this)
      }
    },

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
      } else if (this.activeWorkspaceId === null && this.panels.length > 0) {
        // 兼容历史孤儿面板：当前没有激活画布但顶层存在面板（旧版本残留），
        // 把这些面板迁移到目标画布，避免切换时丢失
        const target = this.workspaces.find((w) => w.id === workspaceId)
        if (target) {
          const orphanPanels = JSON.parse(JSON.stringify(this.panels)).map((p) => ({
            ...p,
            workspace_id: target.id,
          }))
          const orphanConns = JSON.parse(JSON.stringify(this.connections))
          target.panels = [...target.panels, ...orphanPanels]
          target.connections = [...target.connections, ...orphanConns]
          target.viewport = { ...this.viewport }
          target.updated_at = new Date().toISOString()
        }
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
      this.selectedPanelIds = []
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
          // 最后一个画布被删除：彻底清空所有运行时状态，
          // 避免选中/历史/连线交互残留指向已不存在的面板
          this.activeWorkspaceId = null
          this.viewport = { x: 0, y: 0, zoom: 1 }
          this.panels = []
          this.connections = []
          this.selectedPanelId = null
          this.selectedPanelIds = []
          this.selectedConnectionId = null
          this.selectionBox = null
          this.history = { past: [], future: [] }
          this._connecting = null
          this.pendingConnectionCreate = null
          this.enteredFrameId = null
          this.hiddenIds = []
        }
      }
      saveToStorage(this)
    },

    /** 重命名画布 */
    renameWorkspace(workspaceId, name) {
      const ws = this.workspaces.find((w) => w.id === workspaceId)
      if (!ws) return
      const trimmed = (name ?? '').trim()
      if (!trimmed) return
      ws.name = trimmed
      ws.updated_at = new Date().toISOString()
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

    /**
     * 直接设置缩放比例（不压栈）
     * - 用于滑杆拖动期间的连续更新，避免污染撤销/重做历史
     * - 限幅 0.1 ~ 3.0
     * - 传入屏幕坐标 center 时，以 center 为缩放中心调整视口 x/y
     */
    setZoom(zoom, center = null) {
      const oldZoom = this.viewport.zoom
      const newZoom = Math.min(3, Math.max(0.1, Number(zoom) || oldZoom))
      if (newZoom === oldZoom) return

      if (center) {
        this.viewport.x = center.x - ((center.x - this.viewport.x) / oldZoom) * newZoom
        this.viewport.y = center.y - ((center.y - this.viewport.y) / oldZoom) * newZoom
      }

      this.viewport.zoom = newZoom
    },

    /**
     * 设置画布背景模式
     * - mode 取值：'dot' | 'grid' | 'blank'
     * - 不持久化，刷新后回到默认 'dot'
     */
    setBackgroundMode(mode) {
      if (['dot', 'grid', 'blank'].includes(mode)) {
        this.backgroundMode = mode
      }
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

    /** 添加面板
     *  Task 6 任务回流自动连线：
     *  - 若入参 panel.content 携带 upstreamPanelId（上游节点 id），
     *    则在新面板添加完成后入队一条自动连线（延迟 200ms 由
     *    CanvasConnectionsSvg 的 watcher 触发 store.autoConnect）
     *  - 触发源是助手"插入画布"等任务回流路径，由调用方负责写入 upstreamPanelId
     *  - 注意：enqueueAutoConnect 内部不压历史快照，
     *    因此不会污染 undo/redo 栈
     */
    addPanel(panel) {
      // 顺序保护：若当前没有激活画布，先自动创建一个默认画布，
      // 避免面板成为不属于任何画布的"孤儿面板"（切换/刷新后丢失）
      if (!this.activeWorkspaceId) {
        this.createWorkspace(`画布 1`)
      }
      this.pushSnapshot()
      panel.id = uid()
      panel.workspace_id = this.activeWorkspaceId
      panel.created_at = new Date().toISOString()
      panel.updated_at = new Date().toISOString()
      panel.zIndex = this.panels.length + 1
      this.panels.push(panel)
      saveCanvas(this)
      // 任务回流：上游 → 当前新节点的自动连线
      const upstreamId = panel.content?.upstreamPanelId
      if (upstreamId && upstreamId !== panel.id) {
        this.enqueueAutoConnect({
          sourcePanelId: upstreamId,
          targetPanelId: panel.id,
          delay: 200,
        })
      }
    },

    /** 更新面板 */
    updatePanel(id, changes) {
      this.pushSnapshot()
      const panel = this.panels.find((p) => p.id === id)
      if (panel) {
        Object.assign(panel, changes, { updated_at: new Date().toISOString() })
        saveCanvas(this)
      }
    },

    /**
     * 直接更新面板（不压入历史快照）
     * 用于拖拽/缩放过程中的高频更新，由调用方在操作开始时压入一次快照
     */
    _updatePanelDirect(id, changes) {
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
      // 同步多选数组
      this.selectedPanelIds = this.selectedPanelIds.filter((pid) => pid !== id)
      if (this.selectedPanelId === id) this.selectedPanelId = null
      saveCanvas(this)
    },

    /** 一次性清空所有面板（只压一次快照） */
    clearAllPanels() {
      if (this.panels.length === 0) return
      this.pushSnapshot()
      this.connections = []
      this.panels = []
      this.selectedPanelIds = []
      this.selectedPanelId = null
      this.selectedConnectionId = null
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
      // addPanel 内部已 saveCanvas
    },

    /**
     * 复制面板到剪贴板（不立即创建新面板）
     * - 支持单选（传 id）或多选（不传 id 时用 selectedPanelIds）
     * - 深拷贝存入 state.clipboard，paste 时基于鼠标位置创建副本
     */
    copyToClipboard(id) {
      const ids = id ? [id] : [...this.selectedPanelIds]
      if (ids.length === 0) return
      const copies = this.panels
        .filter((p) => ids.includes(p.id))
        .map((p) => JSON.parse(JSON.stringify(p)))
      this.clipboard = copies
    },

    /**
     * 粘贴剪贴板内容到指定屏幕坐标
     * @param {number} screenX - 右键位置的屏幕 x
     * @param {number} screenY - 右键位置的屏幕 y
     * - 以剪贴板中第一个面板的左上角为锚点，对齐到屏幕坐标对应的世界坐标
     * - 其余面板按相对偏移放置
     * - 一次性 pushSnapshot，避免多次粘贴污染历史栈
     */
    pastePanel(screenX, screenY) {
      if (!Array.isArray(this.clipboard) || this.clipboard.length === 0) return
      // 屏幕坐标 → 世界坐标（扣除画布容器偏移由调用方在 world 转换中处理）
      const world = this.screenToWorld(screenX, screenY)
      // 以第一个面板为锚点计算偏移
      const anchor = this.clipboard[0]
      const offsetX = world.x - (anchor.x || 0)
      const offsetY = world.y - (anchor.y || 0)
      this.pushSnapshot()
      const newIds = []
      for (const item of this.clipboard) {
        const newId = uid()
        newIds.push(newId)
        const copy = {
          ...JSON.parse(JSON.stringify(item)),
          id: newId,
          x: (item.x || 0) + offsetX,
          y: (item.y || 0) + offsetY,
          workspace_id: this.activeWorkspaceId,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          zIndex: this.panels.length + 1,
        }
        this.panels.push(copy)
      }
      // 选中粘贴出来的新面板
      this.selectedPanelIds = newIds
      this.selectedPanelId = newIds[0] ?? null
      this.selectedConnectionId = null
      saveCanvas(this)
    },

    /** 选中面板
     *  - append=false（默认）：清空已有选中，单选此 id
     *  - append=true：toggle（已选则移除，未选则追加；用于 Shift/Ctrl/Cmd + 点击）
     */
    selectPanel(id, { append = false } = {}) {
      if (append) {
        // toggle 模式：保留其他选中，只切换当前 id
        const idx = this.selectedPanelIds.indexOf(id)
        if (idx >= 0) {
          this.selectedPanelIds.splice(idx, 1)
        } else if (id) {
          this.selectedPanelIds.push(id)
        }
      } else {
        // 单选：清空再加入单个 id
        this.selectedPanelIds = id ? [id] : []
      }
      // 同步单选便捷字段，保持旧 API 可用
      this.selectedPanelId = this.selectedPanelIds[0] ?? null
      this.selectedConnectionId = null
      // 自动置顶：仅在单选时调整（多选时不主动改变 z 顺序）
      if (!append && id) {
        const panel = this.panels.find((p) => p.id === id)
        if (panel) {
          panel.zIndex = Math.max(...this.panels.map((p) => p.zIndex || 0), 0) + 1
        }
      }
    },

    /** 清空所有选中（面板 + 连线） */
    clearSelection() {
      this.selectedPanelIds = []
      this.selectedPanelId = null
      this.selectedConnectionId = null
    },

    /** 框选：选中所有中心点落在 rect 内的面板
     *  - rect = { startWorld: {x,y}, endWorld: {x,y} }
     *  - append=true：与已有选中叠加；否则替换
     */
    selectPanelsInRect(rect, { append = false } = {}) {
      const { startWorld, endWorld } = rect
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
      this.selectedConnectionId = null
    },

    /** 设置框选矩形（世界坐标），用于 SelectionBox 组件可视化 */
    setSelectionBox(box) {
      this.selectionBox = box
    },

    /** 清除框选矩形 */
    clearSelectionBox() {
      this.selectionBox = null
    },

    /** 批量删除当前选中的所有面板（只压一次快照） */
    deleteSelectedPanels() {
      if (this.selectedPanelIds.length === 0) return
      this.pushSnapshot()
      const ids = new Set(this.selectedPanelIds)
      // 同时删除与选中面板关联的连线
      this.connections = this.connections.filter(
        (c) => !ids.has(c.source_panel_id) && !ids.has(c.target_panel_id),
      )
      this.panels = this.panels.filter((p) => !ids.has(p.id))
      this.selectedPanelIds = []
      this.selectedPanelId = null
    },

    /** 批量复制当前选中的所有面板（只压一次快照，复制体自动选中） */
    duplicateSelectedPanels() {
      if (this.selectedPanelIds.length === 0) return
      this.pushSnapshot()
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
      this.selectedConnectionId = null
    },

    /** 选中连线 */
    selectConnection(id) {
      this.selectedConnectionId = id
      this.selectedPanelIds = []
      this.selectedPanelId = null
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
      saveCanvas(this)
    },

    /** 删除连线 */
    deleteConnection(id) {
      this.pushSnapshot()
      this.connections = this.connections.filter((c) => c.id !== id)
      if (this.selectedConnectionId === id) this.selectedConnectionId = null
      saveCanvas(this)
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

    /**
     * 任务 9：流程落地 —— 把上游面板的产出回填到直接相连的下游面板
     * - 当前仅处理 source = quick-generate / image，target = image 的情况
     * - 回填字段：target.content.imageUrl = payload.imageUrl
     * - 多个下游 ImagePanel 都会被回填（单条连线场景下通常只有一个）
     * - 不压栈（这是产出回填，不是用户主动编辑；如需可回滚由调用方在生成前压栈）
     * @param {string} sourcePanelId - 产出方 panel id
     * @param {{ imageUrl: string }} payload - 产出内容
     */
    propagateResultToDownstream(sourcePanelId, payload) {
      if (!sourcePanelId || !payload) return
      // 找到所有 source → target 的连线
      const downstreamConns = this.connections.filter(
        (c) => c.source_panel_id === sourcePanelId,
      )
      if (downstreamConns.length === 0) return
      for (const conn of downstreamConns) {
        const target = this.panels.find((p) => p.id === conn.target_panel_id)
        if (!target) continue
        // 图片产出 → 回填 image / quick-generate 面板
        if (payload.imageUrl) {
          if (target.type !== 'image' && target.type !== 'quick-generate') continue
          this._updatePanelDirect(target.id, {
            content: {
              ...(target.content || {}),
              imageUrl: payload.imageUrl,
              sourceFrom: sourcePanelId,
            },
          })
        }
        // 视频产出 → 回填 video 面板
        if (payload.videoUrl) {
          if (target.type !== 'video') continue
          this._updatePanelDirect(target.id, {
            content: {
              ...(target.content || {}),
              videoUrl: payload.videoUrl,
              taskStatus: 'success',
              sourceFrom: sourcePanelId,
            },
          })
        }
      }
    },

    /**
     * 任务 9：流程落地 —— 收集指定面板的所有上游输入
     * - 扫描 connections 中 target_panel_id === panelId 的所有连线
     * - 按上游面板类型收集：
     *   · image / quick-generate → 取 content.imageUrl（图生图/图生视频的参考图）
     *   · video                  → 取 content.videoUrl（理论上可作为关键帧，当前仅收集不强制使用）
     *   · text                   → 取 content.text（拼接到下游 prompt）
     * - 返回 { images: string[], texts: string[] }
     *   images: 上游图片 URL 数组（已过滤空值）
     *   texts:  上游文本数组（已过滤空值）
     * - 调用方（QuickGeneratePanel / VideoPanel）在用户点"生成"时实时调用，
     *   不做缓存，保证连线变化后立即生效
     */
    collectUpstreamInputs(panelId) {
      const result = { images: [], texts: [] }
      if (!panelId) return result
      const upstreamConns = this.connections.filter(
        (c) => c.target_panel_id === panelId,
      )
      if (upstreamConns.length === 0) return result
      for (const conn of upstreamConns) {
        const src = this.panels.find((p) => p.id === conn.source_panel_id)
        if (!src) continue
        const content = src.content || {}
        if (src.type === 'image' || src.type === 'quick-generate') {
          if (content.imageUrl) result.images.push(content.imageUrl)
        } else if (src.type === 'video') {
          if (content.videoUrl) result.images.push(content.videoUrl)
        } else if (src.type === 'text') {
          const text = (content.text || '').trim()
          if (text) result.texts.push(text)
        }
      }
      return result
    },

    // ==================== 导入/导出 ====================

    /** 导出当前画布为 JSON 字符串（包含当前激活 workspace 的完整状态） */
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

    /** 从 JSON 导入画布（会替换当前画布的 panels/connections/viewport） */
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
      this.pushSnapshot()
      this.viewport = { ...(ws.viewport || { x: 0, y: 0, zoom: 1 }) }
      this.panels = JSON.parse(JSON.stringify(ws.panels))
      this.connections = JSON.parse(JSON.stringify(ws.connections))
      this.selectedPanelId = null
      this.selectedPanelIds = []
      this.selectedConnectionId = null
      return {
        panels: this.panels.length,
        connections: this.connections.length,
      }
    },

    // ==================== 连线交互 ====================

    /** 开始连线拖拽 */
    startConnecting(panelId, anchorType) {
      this._connecting = {
        sourcePanelId: panelId,
        anchorType,
        worldX: 0,
        worldY: 0,
      }
    },

    /** 更新连线拖拽目标位置（屏幕坐标 → 世界坐标） */
    updateConnecting(screenX, screenY) {
      if (!this._connecting) return
      const world = this.screenToWorld(screenX, screenY)
      this._connecting.worldX = world.x
      this._connecting.worldY = world.y
    },

    /** 结束连线拖拽，如果命中目标锚点则创建连线 */
    endConnecting(targetPanelId, targetAnchorType) {
      if (!this._connecting) return null
      const { sourcePanelId, anchorType } = this._connecting

      // 不能连接到自身
      if (targetPanelId === sourcePanelId) {
        this._connecting = null
        return null
      }

      // 起点是 source → 终点必须是 target；起点是 target → 终点必须是 source
      // 即"从 source 一端拉出，连到 target 一端"
      const connectingTargetAnchor = anchorType === 'source' ? 'target' : 'source'

      // 如果命中了目标锚点，检查方向是否正确
      if (targetAnchorType === 'source' || targetAnchorType === 'target') {
        if (targetAnchorType !== connectingTargetAnchor) {
          this._connecting = null
          return null
        }
      }

      // 决定 source/target 方向：source 锚点一侧是连线起点
      let sourceId, targetId
      if (anchorType === 'source') {
        sourceId = sourcePanelId
        targetId = targetPanelId
      } else {
        sourceId = targetPanelId
        targetId = sourcePanelId
      }

      // 检查是否已存在
      const exists = this.connections.find(
        (c) =>
          c.source_panel_id === sourceId &&
          c.target_panel_id === targetId,
      )
      if (exists) {
        this._connecting = null
        return null
      }

      this.addConnection({
        source_panel_id: sourceId,
        target_panel_id: targetId,
        type: 'manual',
        source_anchor: 'right-middle',
        target_anchor: 'left-middle',
      })

      const conn = this.connections[this.connections.length - 1]
      this._connecting = null
      return conn
    },

    /** 取消连线拖拽 */
    cancelConnecting() {
      this._connecting = null
    },

    // ==================== 拖线到空白：创建新节点菜单 ====================

    /** 设置待创建连线的状态（拖线到空白处松手时调用） */
    setPendingConnectionCreate(payload) {
      if (payload) {
        this.pendingConnectionCreate = payload
      }
    },

    /** 清除待创建连线状态（菜单关闭时调用） */
    clearPendingConnectionCreate() {
      this.pendingConnectionCreate = null
    },

    /**
     * 在落点位置创建指定类型的新节点，并自动与原 source 节点连上
     * - type ∈ ['image', 'video', 'text', 'quick-generate'] 时才执行
     * - 只压一次历史快照（顶部 pushSnapshot），然后绕过 addPanel/addConnection
     *   直接 push 新对象，避免历史栈被多压两次
     * - 新节点 zIndex 为 max + 1，确保盖在 source 之上
     */
    createConnectedNode(type, pending) {
      const allowed = ['image', 'video', 'text', 'quick-generate']
      if (!allowed.includes(type)) return null
      if (!pending || !pending.sourcePanelId) return null

      // 找到原 source 面板
      const sourcePanel = this.panels.find((p) => p.id === pending.sourcePanelId)
      if (!sourcePanel) return null

      // 默认尺寸按 type 取
      const sizeMap = {
        image: { width: 400, height: 300 },
        video: { width: 560, height: 315 },
        text: { width: 300, height: 200 },
        'quick-generate': { width: 350, height: 200 },
      }
      const { width, height } = sizeMap[type]

      // 落点对齐新节点中心
      const x = pending.worldX - width / 2
      const y = pending.worldY - height / 2

      // 只压一次快照
      this.pushSnapshot()

      // 计算新 zIndex = max + 1
      const maxZ = this.panels.reduce(
        (m, p) => Math.max(m, p.zIndex || 0),
        0,
      )

      const now = new Date().toISOString()
      const newPanel = {
        id: uid(),
        type,
        x,
        y,
        width,
        height,
        content: {},
        workspace_id: this.activeWorkspaceId,
        zIndex: maxZ + 1,
        created_at: now,
        updated_at: now,
      }
      this.panels.push(newPanel)

      // 决定连线方向
      let sourceId, targetId
      if (pending.anchorType === 'source') {
        sourceId = pending.sourcePanelId
        targetId = newPanel.id
      } else {
        sourceId = newPanel.id
        targetId = pending.sourcePanelId
      }

      const newConn = {
        id: uid(),
        workspace_id: this.activeWorkspaceId,
        source_panel_id: sourceId,
        target_panel_id: targetId,
        type: 'manual',
        source_anchor: 'right-middle',
        target_anchor: 'left-middle',
        created_at: now,
      }
      this.connections.push(newConn)

      // 清空 pending
      this.pendingConnectionCreate = null

      return newPanel.id
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

    // ===== Task 2.1: 搜索与筛选 =====

    /**
     * 设置搜索关键字
     * - 空字符串时清空 searchMatchedIds 和 searchHighlightUntil
     * - 非空时不自动计算匹配（计算由 searchAndLocate 触发，避免每次输入都全量扫描）
     */
    setSearchQuery(q) {
      this.searchQuery = typeof q === 'string' ? q : ''
      if (!this.searchQuery) {
        this.searchMatchedIds = []
        this.searchHighlightUntil = 0
      }
    },

    /** 设置类型筛选集合（数组） */
    setFilterTypes(types) {
      this.filterTypes = Array.isArray(types) ? types : []
    },

    /** 清空搜索状态 */
    clearSearch() {
      this.searchQuery = ''
      this.searchMatchedIds = []
      this.searchHighlightUntil = 0
    },

    /**
     * 执行搜索并定位首个匹配项
     * - 计算 matchedPanels，把 id 列表写入 searchMatchedIds
     * - 第一个匹配 panel 调 centerOnPanel
     * - 设置 searchHighlightUntil = Date.now() + 1500
     */
    searchAndLocate(q) {
      this.setSearchQuery(q)
      const matched = this.matchedPanels
      this.searchMatchedIds = matched.map((p) => p.id)
      if (matched.length > 0) {
        this.centerOnPanel(matched[0].id)
      }
      this.searchHighlightUntil = Date.now() + 1500
    },

    /**
     * 把指定 panel 的中心居中到视口（仅平移，不缩放）
     * - 使用当前窗口尺寸作为视口基准
     */
    centerOnPanel(panelId) {
      const panel = this.panels.find((p) => p.id === panelId)
      if (!panel) return
      const { zoom } = this.viewport
      const cx = panel.x + panel.width / 2
      const cy = panel.y + panel.height / 2
      const viewWidth = window.innerWidth
      const viewHeight = window.innerHeight
      this.viewport.x = viewWidth / 2 - cx * zoom
      this.viewport.y = viewHeight / 2 - cy * zoom
    },

    // ===== Task 2.2: 网格 =====

    /** 切换是否启用网格吸附 */
    toggleGrid() {
      this.showGrid = !this.showGrid
    },

    /**
     * 设置网格大小（限幅 4~128）
     * - 非数字输入会忽略
     */
    setGridSize(size) {
      const n = Number(size)
      if (!isFinite(n) || n <= 0) return
      this.gridSize = Math.min(128, Math.max(4, n))
    },

    /**
     * 网格吸附
     * - 关闭网格时直接返回原坐标
     * - 打开时按 gridSize 圆整
     */
    snapToGrid(x, y) {
      if (!this.showGrid) return { x, y }
      const g = this.gridSize
      return {
        x: Math.round(x / g) * g,
        y: Math.round(y / g) * g,
      }
    },

    // ===== Task 2.3: 对齐参考线 =====

    /** 设置当前的对齐参考线（世界坐标） */
    setAlignmentGuides(guides) {
      this.alignmentGuides = guides ?? { vertical: [], horizontal: [] }
    },

    /** 清空对齐参考线 */
    clearAlignmentGuides() {
      this.alignmentGuides = { vertical: [], horizontal: [] }
    },

    // ===== Task 2.4: 面板锁定 =====

    /**
     * 锁定面板
     * - 写 panel.content.locked = true
     * - 不压栈（锁定是 UI 状态且可频繁切换；如需可回滚由调用方自行压栈）
     */
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

    /** 切换面板的锁定状态 */
    toggleLock(id) {
      const panel = this.panels.find((p) => p.id === id)
      if (!panel) return
      const current = !!panel.content?.locked
      this._updatePanelDirect(id, {
        content: { ...(panel.content ?? {}), locked: !current },
      })
    },

    // ===== Task 2.5: 备注 =====

    /**
     * 更新面板备注
     * - 直接写入 panel.content.note
     * - 不压栈（备注是高频输入；如需可回滚由调用方在编辑开始时压栈）
     */
    updateNote(panelId, text) {
      const panel = this.panels.find((p) => p.id === panelId)
      if (!panel) return
      this._updatePanelDirect(panelId, {
        content: { ...(panel.content ?? {}), note: text ?? '' },
      })
    },

    // ===== Task 2.6: 隐藏 =====

    /**
     * 设置面板的隐藏状态
     * - 维护 hiddenIds 数组（push / splice）
     * - 不压栈（隐藏是 UI 状态，不是数据变更）
     */
    setPanelHidden(id, hidden) {
      if (!id) return
      const idx = this.hiddenIds.indexOf(id)
      if (hidden) {
        if (idx === -1) this.hiddenIds.push(id)
      } else {
        if (idx >= 0) this.hiddenIds.splice(idx, 1)
      }
    },

    // ===== Task 2.7: Frame 模式 =====

    /**
     * 创建一个 Frame 面板
     * - rect = { x, y, width, height }
     * - 创建 type='frame' 的 panel，content.children 收集中心点落在 rect 内的非 frame 节点 id
     * - 默认颜色交由组件层处理，这里只存 children 与尺寸
     * - 走 addPanel 自动压一次快照
     */
    createFrame(rect) {
      if (!rect) return null
      const { x, y, width, height } = rect
      const children = this.panels
        .filter((p) => {
          if (p.type === 'frame') return false
          const cx = p.x + p.width / 2
          const cy = p.y + p.height / 2
          return cx >= x && cx <= x + width && cy >= y && cy <= y + height
        })
        .map((p) => p.id)

      this.addPanel({
        type: 'frame',
        x,
        y,
        width,
        height,
        content: { children },
      })
      return this.panels[this.panels.length - 1] ?? null
    },

    /** 把 childId 加入 frame.content.children（去重） */
    addChildToFrame(frameId, childId) {
      if (!frameId || !childId) return
      const frame = this.panels.find((p) => p.id === frameId)
      if (!frame) return
      const children = Array.isArray(frame.content?.children) ? frame.content.children : []
      if (children.includes(childId)) return
      this._updatePanelDirect(frameId, {
        content: { ...(frame.content ?? {}), children: [...children, childId] },
      })
    },

    /** 从 frame.content.children 移除 childId */
    removeChildFromFrame(frameId, childId) {
      if (!frameId || !childId) return
      const frame = this.panels.find((p) => p.id === frameId)
      if (!frame) return
      const children = Array.isArray(frame.content?.children) ? frame.content.children : []
      if (!children.includes(childId)) return
      this._updatePanelDirect(frameId, {
        content: {
          ...(frame.content ?? {}),
          children: children.filter((cid) => cid !== childId),
        },
      })
    },

    /** 进入 Frame 模式（仅记录 id，不做视口切换，组件层负责视觉表现） */
    enterFrame(frameId) {
      this.enteredFrameId = frameId ?? null
    },

    /** 退出 Frame 模式 */
    exitFrame() {
      this.enteredFrameId = null
    },

    /**
     * 同步 Frame 子节点（任务 5：Frame 联动）
     * - 在 BaseNode onUp 拖动 / 缩放结束时调用，把 Frame 的 (x, y, w, h) 变化应用到子节点
     * - 用 prev/now 差量计算：上次同步时的 Frame 尺寸 → 当前尺寸
     *   · 拖动：所有子节点 x += dx, y += dy（保持相对偏移）
     *   · 缩放：以 Frame 左上角为锚点，等比调整子节点 x / y / width / height
     * - 使用 _updatePanelDirect 不压栈（BaseNode 已经在 onUp 开始时压过一次快照）
     * - 每次同步后写回 frameSync 基准，避免连续拖动 / 缩放叠加误差
     */
    syncFrameChildren(frameId) {
      const frame = this.panels.find((p) => p.id === frameId)
      if (!frame) return
      const childIds = Array.isArray(frame.content?.children) ? frame.content.children : []
      if (childIds.length === 0) return

      // 读取"上次同步时"的 Frame 尺寸；首次同步时用当前值初始化基准
      const prev = frame.content?.frameSync ?? {
        x: frame.x, y: frame.y, width: frame.width, height: frame.height,
      }
      const dx = frame.x - prev.x
      const dy = frame.y - prev.y
      // 缩放比例（用 w / h 都算，逻辑上假定等比；任意一边为 0 时按 1 处理）
      const scaleX = prev.width === 0 ? 1 : frame.width / prev.width
      const scaleY = prev.height === 0 ? 1 : frame.height / prev.height

      for (const childId of childIds) {
        const child = this.panels.find((p) => p.id === childId)
        if (!child) continue
        // 缩放：以 Frame 左上角为锚点（先回到 Frame 坐标系 → 缩放 → 回到世界坐标 → 叠加拖动偏移）
        const newX = prev.x + (child.x - prev.x) * scaleX + dx
        const newY = prev.y + (child.y - prev.y) * scaleY + dy
        const newW = child.width * scaleX
        const newH = child.height * scaleY
        this._updatePanelDirect(childId, { x: newX, y: newY, width: newW, height: newH })
      }

      // 写回当前 Frame 尺寸作为下次同步的基准
      this._updatePanelDirect(frameId, {
        content: {
          ...(frame.content ?? {}),
          frameSync: { x: frame.x, y: frame.y, width: frame.width, height: frame.height },
        },
      })
    },

    // ===== Task 5: 持久化 hydrate =====

    /**
     * 异步从 localforage 拉取 v2 数据并合并到 state
     * - 仅恢复持久化字段：panels / connections / viewport / workspaces / activeWorkspaceId / themeMode
     * - 由 CanvasView 的 onMounted 触发一次；不重复执行（idempotent）
     * - 如果有 v1 数据（localStorage 'agnes_canvas_v1'），先尝试迁移到 localforage
     */
    async _hydrateFromStorage() {
      if (this._storageReady) return

      // 1) 尝试 v1 → v2 一次性迁移（仅当 v2 为空时）
      try {
        const current = await loadCanvas()
        if (!current) {
          const migrated = await migrateFromV1()
          if (!migrated) {
            // 没有 v1 也没有 v2：保持当前 state 不变
            this._storageReady = isStorageReady()
            return
          }
        }
      } catch {
        // 迁移失败：继续走 loadCanvas
      }

      // 2) 加载 v2
      const data = await restoreFromStorage()
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
      this._storageReady = isStorageReady()
    },

    // ===== Task 6: 自动连线（延迟触发） =====

    /**
     * 把一条自动连线加入 pending 队列，delay ms 后执行
     * - 同一时刻只允许一个 pending；新调用会替换旧的（旧的 timer 被清掉）
     * - 实际连线由 autoConnect() 创建（已存在则不重复创建）
     */
    enqueueAutoConnect({ sourcePanelId, targetPanelId, delay = 200 }) {
      // 取消上一个
      this.cancelPendingAutoConnect()
      if (!sourcePanelId || !targetPanelId || sourcePanelId === targetPanelId) return
      const timer = setTimeout(() => {
        this.pendingAutoConnect = null
        this.autoConnect(sourcePanelId, targetPanelId)
      }, delay)
      this.pendingAutoConnect = { sourcePanelId, targetPanelId, timer }
    },

    /** 取消挂起的自动连线 */
    cancelPendingAutoConnect() {
      if (this.pendingAutoConnect?.timer) {
        clearTimeout(this.pendingAutoConnect.timer)
      }
      this.pendingAutoConnect = null
    },

    // ===== Task 7: 批量生成 / 子节点管理 =====

    /**
     * 在 parent 下挂载一个批量子节点
     * 1) 把 childPanel.id 写入 parent.content.batchChildIds（去重）
     * 2) push childPanel 到 panels
     * 3) 压一次历史快照，便于整体回滚
     *
     * 注：childPanel 仍然走 addPanel 的入参约定（无 id），由本方法在 push 前补 id
     */
    addBatchChild(parentId, childPanel) {
      const parent = this.panels.find((p) => p.id === parentId)
      if (!parent || !childPanel) return null
      this.pushSnapshot()
      // 1) 分配 id 并写入 panels
      if (!childPanel.id) childPanel.id = uid()
      childPanel.workspace_id = this.activeWorkspaceId
      childPanel.created_at = childPanel.created_at ?? new Date().toISOString()
      childPanel.updated_at = new Date().toISOString()
      childPanel.zIndex = this.panels.length + 1
      this.panels.push(childPanel)
      // 2) 维护 parent.content.batchChildIds
      const existing = Array.isArray(parent.content?.batchChildIds)
        ? parent.content.batchChildIds
        : []
      if (!existing.includes(childPanel.id)) {
        this._updatePanelDirect(parentId, {
          content: { ...(parent.content ?? {}), batchChildIds: [...existing, childPanel.id] },
        })
      }
      return childPanel.id
    },

    /** 展开指定父节点的批量预览 */
    expandBatch(parentId) {
      if (!parentId) return
      this.batchExpanded = { ...this.batchExpanded, [parentId]: true }
    },

    /** 折叠指定父节点的批量预览 */
    collapseBatch(parentId) {
      if (!parentId) return
      this.batchExpanded = { ...this.batchExpanded, [parentId]: false }
    },

    // ===== Task 8: 配置节点（驱动批量生图） =====

    /**
     * 在指定位置创建一个 type='config' 的配置节点
     * - content.model / size / count 缺省值：'sdxl' / '1:1' / 4
     * - content.batchMode 缺省 true（与 ConfigPanel 默认开关保持一致）
     */
    addConfigNode({ x, y }) {
      const panel = {
        type: 'config',
        x: Number(x) || 0,
        y: Number(y) || 0,
        width: 240,
        height: 180,
        content: {
          model: 'sdxl',
          size: '1:1',
          count: 4,
          batchMode: true,
          batchChildIds: [],
        },
      }
      this.addPanel(panel)
      return this.panels[this.panels.length - 1]?.id ?? null
    },

    /**
     * 应用 config 节点：对它的所有上游 image 节点，分别复制 count 个 image 占位节点
     * - 上游关系：connection.target_panel_id === configId 的 source_panel_id
     * - 每个上游 image 复制出的子节点会挂在 config.content.batchChildIds 下
     * - 占位：内容为 { sourceFrom: sourcePanelId, status: 'pending' }
     * - 返回创建的子节点数量，便于 BaseNode 弹出"已生成 N 个子图"提示
     */
    applyConfig(configId) {
      const config = this.panels.find((p) => p.id === configId)
      if (!config || config.type !== 'config') return 0
      const count = Math.max(1, Number(config.content?.count) || 4)
      const upstreamIds = this.connections
        .filter((c) => c.target_panel_id === configId)
        .map((c) => c.source_panel_id)
        .filter(Boolean)
      let created = 0
      for (const sourceId of upstreamIds) {
        const source = this.panels.find((p) => p.id === sourceId)
        if (!source) continue
        for (let i = 0; i < count; i++) {
          this.addBatchChild(configId, {
            type: 'image',
            x: (config.x ?? 0) + 280 + (i % 4) * 220,
            y: (config.y ?? 0) + Math.floor(i / 4) * 240,
            width: 200,
            height: 200,
            content: {
              sourceFrom: source.id,
              status: 'pending',
              rotation: 0,
            },
          })
          created++
        }
      }
      return created
    },

    /**
     * 设置面板旋转角度（0 / 90 / 180 / 270）
     * - 写入 panel.content.rotation
     * - 不压栈（高频切换，由调用方按需压栈）
     */
    setPanelRotation(id, rotation) {
      const allowed = [0, 90, 180, 270]
      const r = Number(rotation)
      if (!allowed.includes(r)) return
      const panel = this.panels.find((p) => p.id === id)
      if (!panel) return
      this._updatePanelDirect(id, {
        content: { ...(panel.content ?? {}), rotation: r },
      })
    },

    /**
     * 把一个 image 面板复制 N 份，新节点 zIndex 递增
     * - 默认 count = 4
     * - 复制节点会向右下偏移，避免与原节点重叠
     */
    splitImagePanel(id, count = 4) {
      const orig = this.panels.find((p) => p.id === id)
      if (!orig) return []
      const n = Math.max(1, Number(count) || 4)
      this.pushSnapshot()
      const maxZ = Math.max(...this.panels.map((p) => p.zIndex || 0), 0)
      const newIds = []
      for (let i = 0; i < n; i++) {
        const newPanel = {
          ...orig,
          id: uid(),
          x: orig.x + 30 + i * 20,
          y: orig.y + 30 + i * 20,
          zIndex: maxZ + i + 1,
          content: JSON.parse(JSON.stringify(orig.content ?? {})),
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }
        this.panels.push(newPanel)
        newIds.push(newPanel.id)
      }
      return newIds
    },
  },
})
