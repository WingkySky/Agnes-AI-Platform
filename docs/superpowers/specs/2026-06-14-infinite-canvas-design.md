---
name: infinite-canvas-design
description: 无限画布功能产品设计文档 — 多画布管理、面板拖拽、贝塞尔曲线连线、任务集成
metadata:
  type: project
  created: 2026-06-14
---

# Agnes AI Platform — 无限画布功能产品设计文档

## 1. 产品概述

在 Agnes AI Platform 中新增一个无限画布页面，用户可以创建、拖拽、缩放多种类型的面板，模拟 libtv 和 minimax hub 的交互体验。画布用于同时监控多个生成任务、排列组合生成结果、管理任务流程。

**核心理念**：把画布变成 Agnes 平台的"总控台" — 一个自由的空间，让用户同时看到所有任务的进展、排列创意素材、管理创作流程。

## 2. 需求汇总

### 2.1 核心需求

| 编号 | 需求 | 优先级 | 说明 |
|------|------|--------|------|
| N1 | 无限画布平移/缩放 | P0 | 拖拽背景平移、滚轮缩放（0.1x-3x）、缩放控件、重置视图 |
| N2 | 多画布管理 | P0 | 左侧栏管理多个画布，像 Notion 那样切换 |
| N3 | 面板 CRUD | P0 | 创建、拖拽移动、调整大小、删除、复制面板 |
| N4 | 贝塞尔曲线连线 | P0 | 面板之间手动拖拽锚点连线 + 系统根据任务关系自动连线 |
| N5 | 撤销/重做 | P0 | 支持面板操作和连线操作的撤销/重做（最多 50 步） |
| N6 | 任务状态集成 | P1 | 面板关联任务后自动刷新状态（pending/processing/success/failed） |
| N7 | 后端数据同步 | P1 | 画布数据保存到后端，支持多设备同步 |

### 2.2 面板类型（7 种）

| 类型 | 标识 | 默认尺寸 | 说明 |
|------|------|----------|------|
| 图片预览 | `image` | 400x300 | 展示 Agnes 生成的图片，支持点击放大 |
| 视频预览 | `video` | 560x315 | 展示 Agnes 生成的视频，支持播放控制 |
| 文本笔记 | `text` | 300x200 | 富文本编辑，支持多行文字 |
| URL 链接 | `url` | 400x300 | iframe 嵌入任意网页 |
| 快捷生成 | `quick-generate` | 350x200 | 在画布上直接输入 prompt 触发生成 |
| 文件上传 | `file-upload` | 350x250 | 上传本地图片/视频到面板中 |
| 占位面板 | `placeholder` | 200x150 | 空白面板，用户自定义内容 |

### 2.3 连线规则

| 规则 | 说明 |
|------|------|
| 手动连线 | 用户拖拽面板右下角锚点到另一个面板的左上角锚点 |
| 自动连线 | 系统检测到任务依赖关系时自动创建（如图生视频：图片 → 视频） |
| 连线样式 | 贝塞尔曲线，带方向箭头，颜色区分类型（任务流=蓝色，手动=灰色） |
| 删除连线 | 选中连线按 Delete 键，或点击连线上的删除按钮 |

### 2.4 快捷键

| 快捷键 | 功能 |
|--------|------|
| Delete / Backspace | 删除选中面板/连线 |
| Escape | 取消选中 |
| Ctrl+Z / Cmd+Z | 撤销 |
| Ctrl+Shift+Z / Cmd+Shift+Z | 重做 |
| Ctrl+D / Cmd+D | 复制选中面板 |
| Ctrl+A / Cmd+A | 全选面板 |
| 方向键 | 微调选中面板位置（配合 Shift 步长 10px，否则 1px） |

## 3. 技术方案

### 3.1 技术选型

| 维度 | 选择 | 理由 |
|------|------|------|
| 框架 | Vue 3 Composition API + `<script setup>` | 与项目现有技术栈一致 |
| UI 组件 | Element Plus | 项目已有，深色主题统一 |
| 状态管理 | Pinia | 项目已有，Options-style `defineStore` |
| 画布引擎 | 纯 CSS Transform + Pointer Events | 零依赖、完全可控、与 Vue 天然契合 |
| 连线绘制 | SVG `<path>` + BezierCurveTo | 平滑曲线，性能好 |
| 路由 | vue-router | 项目已有 |
| 后端 | FastAPI | 已有后端，新增画布 API |
| 持久化 | localStorage + 后端同步 | 本地快速恢复 + 多设备同步 |

### 3.2 为什么不选第三方库

| 库 | 原因 |
|----|------|
| @xyflow/vue | 设计偏向流程图，不适合自由画布，连线风格不够灵活 |
| tldraw | React 实现，与 Vue 3 项目格格不入，体积过大 |
| konva/vue-konva | Canvas 渲染，DOM 交互（iframe、表单）支持差 |
| panzoom | 只做平移缩放，连线/锚点仍需自己实现，不如直接用 CSS transform |

### 3.3 坐标系统

```
世界坐标系（World Coordinates）
- 所有面板位置用世界坐标存储
- 不受缩放/平移影响，数据稳定

屏幕坐标系（Screen Coordinates）
- 渲染时用 CSS transform 转换
- transform: translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})

坐标转换公式：
- 屏幕 → 世界：worldX = (screenX - viewport.x) / viewport.zoom
- 世界 → 屏幕：screenX = worldX * viewport.zoom + viewport.x
```

### 3.4 事件路由策略

```
pointerdown 事件冒泡链：
  CanvasGrid → InfiniteCanvas（背景平移）
  CanvasPanel → InfiniteCanvas（面板拖拽）
  AnchorPoint → InfiniteCanvas（连线拖拽）

判断逻辑：
  event.target.dataset.canvas-target === 'grid'    → 背景平移
  event.target.dataset.canvas-target === 'panel'    → 面板拖拽
  event.target.dataset.canvas-target === 'anchor'   → 连线拖拽
```

## 4. 数据结构

### 4.1 画布数据模型

```typescript
interface CanvasWorkspace {
  id: string
  name: string
  created_at: string
  updated_at: string
  viewport: Viewport
  panels: CanvasPanel[]
  connections: CanvasConnection[]
}

interface Viewport {
  x: number      // 平移 X 偏移量
  y: number      // 平移 Y 偏移量
  zoom: number   // 缩放级别 (0.1 - 3.0)
}

interface CanvasPanel {
  id: string
  type: PanelType                    // 'image' | 'video' | 'text' | 'url' | 'quick-generate' | 'file-upload' | 'placeholder'
  x: number                          // 世界坐标 X
  y: number                          // 世界坐标 Y
  width: number
  height: number
  content: Record<string, any>       // 面板内容（因类型而异）
  zIndex: number                     // 层级（选中时自动置顶）
  workspace_id: string
  task_id?: string                   // 关联的任务 ID（用于状态同步）
  created_at: string
  updated_at: string
}

interface CanvasConnection {
  id: string
  source_panel_id: string
  target_panel_id: string
  type: 'manual' | 'auto'            // 手动连线 or 自动连线
  source_anchor: 'bottom-right'      // 源锚点位置
  target_anchor: 'top-left'          // 目标锚点位置
  workspace_id: string
  created_at: string
}
```

### 4.2 历史快照

```typescript
interface CanvasSnapshot {
  viewport: Viewport
  panels: CanvasPanel[]
  connections: CanvasConnection[]
}
```

## 5. 后端 API 设计

### 5.1 新增路由

```
POST   /api/canvas/workspaces          创建画布
GET    /api/canvas/workspaces          获取用户所有画布
GET    /api/canvas/workspaces/:id      获取单个画布详情
PUT    /api/canvas/workspaces/:id      更新画布名称
DELETE /api/canvas/workspaces/:id      删除画布
PUT    /api/canvas/workspaces/:id      同步画布完整状态（viewport + panels + connections）
GET    /api/canvas/workspaces/:id      获取画布状态
```

### 5.2 同步策略

- 用户离开画布页面时自动同步
- 面板拖拽/连线操作暂停 1 秒后自动保存（防抖）
- 手动点击保存按钮立即同步

## 6. 组件层次结构

```
CanvasView.vue                          # 页面容器
├── CanvasSidebar.vue                   # 左侧栏：多画布管理
├── CanvasToolbar.vue                   # 顶部工具栏
├── InfiniteCanvas.vue                  # 无限画布容器
│   ├── CanvasViewport.vue              # 变换容器（CSS transform）
│   │   ├── CanvasGrid.vue              # 网格背景层
│   │   ├── CanvasConnectionsSvg.vue    # 连线 SVG 层
│   │   ├── CanvasPanels.vue            # 面板容器
│   │   │   ├── PanelWrapper.vue        # 通用面板包装器
│   │   │   │   ├── ImagePanel.vue      # 图片预览面板
│   │   │   │   ├── VideoPanel.vue      # 视频预览面板
│   │   │   │   ├── TextPanel.vue       # 文本笔记面板
│   │   │   │   ├── UrlPanel.vue        # URL/iframe 面板
│   │   │   │   ├── QuickGeneratePanel.vue  # 快捷生成面板
│   │   │   │   ├── FileUploadPanel.vue     # 文件上传面板
│   │   │   │   └── PlaceholderPanel.vue    # 占位面板
│   │   │   └── AnchorPoint.vue         # 连线锚点
│   │   └── Minimap.vue                 # 右下角小地图
│   └── CanvasRightPanel.vue            # 右侧面板：属性编辑
└── CanvasShortcutHandler.vue           # 全局快捷键处理器
```

## 7. 状态管理（Pinia Store）

### 7.1 Store 结构

```javascript
useCanvasStore = defineStore('canvas', {
  state: () => ({
    // 多画布
    workspaces: [],
    activeWorkspaceId: null,
    // 当前画布状态
    viewport: { x: 0, y: 0, zoom: 1 },
    panels: [],
    connections: [],
    selectedPanelId: null,
    selectedConnectionId: null,
    // 历史记录
    history: { past: [], future: [] },
    // 拖拽状态（不持久化）
    _dragging: null,    // { type: 'pan'|'panel'|'connection', ... }
    _resizing: null,
    // 同步状态
    syncing: false,
    lastSyncedAt: null,
  }),

  getters: {
    activeWorkspace,
    selectedPanel,
    visiblePanels,       // 视口内的面板（性能优化）
    panelConnections,    // 某面板的所有连线
  },

  actions: {
    // 画布管理
    createWorkspace(name),
    switchWorkspace(workspaceId),
    deleteWorkspace(workspaceId),
    syncWorkspace(),
    // 视口操作
    pan(deltaX, deltaY),
    zoom(factor, center?),
    resetView(),
    // 面板操作
    addPanel(panel),
    updatePanel(id, changes),
    deletePanel(id),
    duplicatePanel(id),
    selectPanel(id),
    movePanelToFront(id),
    // 连线操作
    addConnection(connection),
    deleteConnection(id),
    autoConnect(sourceId, targetId),
    // 历史
    pushSnapshot(),
    undo(),
    redo(),
    // 同步
    startAutoSync(),
    stopAutoSync(),
  },
})
```

## 8. 视觉设计要点

### 8.1 深色主题

复用项目现有 CSS 变量：
- 背景：`linear-gradient(135deg, #0b0f1a 0%, #101827 50%, #0b0f1a 100%)`
- 面板背景：`rgba(20, 30, 50, 0.85)` + `backdrop-filter: blur(12px)`
- 选中边框：`--agnes-primary`（蓝色渐变）
- 网格线：`rgba(100, 150, 220, 0.06)`
- 连线：`rgba(100, 150, 255, 0.4)`（任务流）/ `rgba(150, 150, 180, 0.3)`（手动）

### 8.2 面板样式

- 圆角：12px
- 阴影：`0 4px 24px rgba(0, 0, 0, 0.3)`
- Hover：阴影加深 + 边框高亮
- 选中：2px 蓝色渐变边框 + 发光阴影

### 8.3 连线样式

- 曲线：三次贝塞尔曲线，控制点水平延伸面板宽度的 30%
- 线宽：2px
- 箭头：三角形，填充 `rgba(100, 150, 255, 0.6)`
- Hover：线宽加到 3px，颜色变亮

## 9. 实施阶段

| 阶段 | 内容 | 预估工时 | 可独立交付 |
|------|------|----------|-----------|
| Phase 1 | 画布核心（平移/缩放/网格） | 2-3h | 可平移缩放的空画布 |
| Phase 2 | 多画布管理 + 面板 CRUD | 3-4h | 可创建/拖拽/删除的面板 |
| Phase 3 | 7 种面板类型实现 | 3-4h | 所有面板类型可用 |
| Phase 4 | 贝塞尔曲线连线 | 2-3h | 手动连线 + 自动连线 |
| Phase 5 | 撤销/重做 + 快捷键 | 1-2h | 完整交互体验 |
| Phase 6 | 后端集成 + 数据同步 | 2-3h | 多设备同步 |
| Phase 7 | UX 完善（小地图/属性面板/性能优化） | 2-3h | 生产就绪 |

**总计预估**：15-22 小时

## 10. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 拖拽与缩放事件冲突 | 高 | 严格通过 `data-canvas-target` 区分事件目标 |
| 缩放时面板位置跳跃 | 中 | 以鼠标位置为中心点缩放，精确坐标转换 |
| 大量面板时性能下降 | 中 | 视口裁剪（仅渲染可见面板）、CSS `contain` 优化 |
| iframe 面板跨域问题 | 中 | 部分网站禁止 iframe 嵌入，显示占位提示 |
| 连线计算复杂度高 | 低 | 面板数量 <100 时贝塞尔曲线计算无压力 |
