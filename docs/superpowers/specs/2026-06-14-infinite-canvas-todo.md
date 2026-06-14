# 无限画布功能 — TODO List

> 基于 [产品设计文档](./2026-06-14-infinite-canvas-design.md) 拆解的具体任务清单。
> 按实施阶段分组，每个任务标注优先级和预估工时。

---

## Phase 1：画布核心（平移/缩放/网格）

**预估**：2-3 小时 | **优先级**：P0

- [ ] **1.1 创建目录结构**
  - [ ] 创建 `frontend/src/components/infinite-canvas/` 目录
  - [ ] 创建 `frontend/src/components/infinite-canvas/item-types/` 目录
  - [ ] 创建 `frontend/src/views/CanvasView.vue` 页面骨架

- [ ] **1.2 创建 Pinia Store（基础版）**
  - [ ] 创建 `frontend/src/stores/canvas.js`
  - [ ] 定义 `viewport` state（x, y, zoom）
  - [ ] 实现 `pan(deltaX, deltaY)` action
  - [ ] 实现 `zoom(factor, center?)` action
  - [ ] 实现 `resetView()` action
  - [ ] 实现 localStorage 持久化（`_saveToStorage` / `_restoreFromStorage`）

- [ ] **1.3 实现 InfiniteCanvas 容器**
  - [ ] 全屏 `<div>` 作为画布根容器
  - [ ] 实现 Pointer Events 处理（pointerdown/move/up 用于背景平移）
  - [ ] 实现 Wheel 事件处理（以鼠标位置为中心缩放）
  - [ ] 限制 zoom 范围 0.1x - 3.0x
  - [ ] 实现 `screenToWorld()` / `worldToScreen()` 坐标转换
  - [ ] 使用 `requestAnimationFrame` 节流视口更新

- [ ] **1.4 实现 CanvasViewport 变换容器**
  - [ ] 应用 CSS `transform: translate(${x}px, ${y}px) scale(${zoom})`
  - [ ] 添加 `will-change: transform` 性能优化
  - [ ] 透传 slot 给子元素

- [ ] **1.5 实现 CanvasGrid 网格背景**
  - [ ] 使用 CSS `background-image: linear-gradient()` 生成网格
  - [ ] 网格大小跟随缩放级别动态变化
  - [ ] 提供 toggle 开关

- [ ] **1.6 路由集成**
  - [ ] 在 `frontend/src/router/index.js` 中添加 `/canvas` 路由
  - [ ] 不加入 keep-alive 缓存

- [ ] **1.7 i18n 文案**
  - [ ] 在 `zh-CN.js` / `en-US.js` 中添加画布相关文案
  - [ ] `nav.canvas`, `router.canvas`, `canvas.zoomIn`, `canvas.zoomOut`, `canvas.resetView`

---

## Phase 2：多画布管理 + 面板 CRUD

**预估**：3-4 小时 | **优先级**：P0

- [ ] **2.1 扩展 Store（多画布支持）**
  - [ ] 添加 `workspaces` / `activeWorkspaceId` state
  - [ ] 实现 `createWorkspace(name)` action
  - [ ] 实现 `switchWorkspace(workspaceId)` action
  - [ ] 实现 `deleteWorkspace(workspaceId)` action
  - [ ] 添加 `panels` / `connections` state
  - [ ] 添加 `selectedPanelId` state

- [ ] **2.2 实现 CanvasSidebar 左侧栏**
  - [ ] 画布列表展示
  - [ ] 新建画布按钮
  - [ ] 删除画布按钮（带确认对话框）
  - [ ] 选中高亮当前画布

- [ ] **2.3 实现 CanvasToolbar 顶部工具栏**
  - [ ] 添加面板下拉菜单（7 种类型）
  - [ ] 缩放百分比显示
  - [ ] 缩小/放大按钮
  - [ ] 缩放滑块（range input）
  - [ ] 重置视图按钮
  - [ ] 当前面板计数显示

- [ ] **2.4 实现 PanelWrapper 通用面板包装器**
  - [ ] 接收 `panel` prop（x, y, width, height, type, content）
  - [ ] 通过 CSS `transform: translate(${x}px, ${y}px)` 定位
  - [ ] 实现面板拖拽（pointerdown/move/up）
  - [ ] 实现 8 点缩放手柄（四角 + 四边中点）
  - [ ] 选中样式（蓝色渐变边框 + 发光阴影）
  - [ ] 非选中时隐藏缩放手柄
  - [ ] 最小尺寸限制（宽 150px，高 100px）

- [ ] **2.5 实现面板事件路由**
  - [ ] `data-canvas-target` 属性标记事件目标
  - [ ] 区分背景/面板/锚点的 pointer 事件
  - [ ] 选中面板时自动提升 z-index

- [ ] **2.6 面板操作**
  - [ ] `addPanel(panel)` action
  - [ ] `updatePanel(id, changes)` action
  - [ ] `deletePanel(id)` action
  - [ ] `duplicatePanel(id)` action
  - [ ] `selectPanel(id)` action

---

## Phase 3：7 种面板类型实现

**预估**：3-4 小时 | **优先级**：P0

- [ ] **3.1 图片预览面板（ImagePanel）**
  - [ ] 展示 Agnes 生成的图片
  - [ ] 支持点击放大预览
  - [ ] 默认尺寸 400x300
  - [ ] 关联 `task_id` 时自动从 API 获取图片

- [ ] **3.2 视频预览面板（VideoPanel）**
  - [ ] `<video>` 标签，支持 controls
  - [ ] 默认尺寸 560x315（16:9）
  - [ ] 关联 `task_id` 时自动获取视频
  - [ ] 加载状态显示 loading 动画

- [ ] **3.3 文本笔记面板（TextPanel）**
  - [ ] `contenteditable` div 实现内联编辑
  - [ ] 双击进入编辑模式
  - [ ] 默认 placeholder："双击输入文字..."
  - [ ] 默认尺寸 300x200

- [ ] **3.4 URL 链接面板（UrlPanel）**
  - [ ] iframe 嵌入任意网页
  - [ ] 输入 URL 和标题
  - [ ] 跨域限制提示（部分网站禁止 iframe 嵌入）
  - [ ] 默认尺寸 400x300

- [ ] **3.5 快捷生成面板（QuickGeneratePanel）**
  - [ ] 输入 prompt 的文本框
  - [ ] 选择生成类型（图片/视频）
  - [ ] 点击生成按钮触发任务
  - [ ] 生成结果自动填入面板
  - [ ] 默认尺寸 350x200

- [ ] **3.6 文件上传面板（FileUploadPanel）**
  - [ ] 拖拽上传区域
  - [ ] 支持图片/视频文件
  - [ ] 上传后预览
  - [ ] 默认尺寸 350x250

- [ ] **3.7 占位面板（PlaceholderPanel）**
  - [ ] 空白面板
  - [ ] 用户自定义内容
  - [ ] 默认尺寸 200x150

- [ ] **3.8 动态组件注册**
  - [ ] `PanelWrapper` 中使用 `<component :is="componentMap[panel.type]" />`
  - [ ] 注册所有面板类型到 componentMap
  - [ ] 新增类型只需注册，无需改 PanelWrapper

---

## Phase 4：贝塞尔曲线连线

**预估**：2-3 小时 | **优先级**：P0

- [ ] **4.1 实现 AnchorPoint 锚点组件**
  - [ ] 显示在面板右下角（输出锚点）
  - [ ] 显示在面板左上角（输入锚点）
  - [ ] pointerdown 时启动连线拖拽
  - [ ] hover 时高亮

- [ ] **4.2 实现 CanvasConnectionsSvg 连线 SVG 层**
  - [ ] 全屏 SVG 覆盖层（在 CanvasViewport 内）
  - [ ] 使用 `<path>` 绘制三次贝塞尔曲线
  - [ ] 控制点水平延伸面板宽度的 30%
  - [ ] 线宽 2px，颜色区分类型
  - [ ] 箭头标记（三角形）

- [ ] **4.3 手动连线交互**
  - [ ] 拖拽锚点时显示临时连线（虚线）
  - [ ] 释放到目标锚点时创建正式连线
  - [ ] 更新 store 中的 `connections` state

- [ ] **4.4 自动连线逻辑**
  - [ ] 检测任务依赖关系（如图生视频）
  - [ ] 调用 `autoConnect(sourceId, targetId)` 自动创建连线
  - [ ] 自动连线标记为 `type: 'auto'`，样式不同

- [ ] **4.5 连线操作**
  - [ ] 选中连线高亮
  - [ ] 按 Delete 键删除选中连线
  - [ ] 连线上的删除按钮

---

## Phase 5：撤销/重做 + 快捷键

**预估**：1-2 小时 | **优先级**：P0

- [ ] **5.1 实现历史快照系统**
  - [ ] 在 store 中添加 `history: { past: [], future: [] }`
  - [ ] `CanvasSnapshot = { viewport, panels, connections }`
  - [ ] `pushSnapshot()` 每次操作后压入历史
  - [ ] 限制历史记录深度（最多 50 步）

- [ ] **5.2 实现 undo/redo**
  - [ ] `undo()` 从 past 弹出快照恢复
  - [ ] `redo()` 从 future 弹出快照恢复
  - [ ] 工具栏显示 undo/redo 按钮

- [ ] **5.3 实现全局快捷键**
  - [ ] `Delete / Backspace` — 删除选中面板/连线
  - [ ] `Escape` — 取消选中
  - [ ] `Ctrl+Z / Cmd+Z` — 撤销
  - [ ] `Ctrl+Shift+Z / Cmd+Shift+Z` — 重做
  - [ ] `Ctrl+D / Cmd+D` — 复制选中面板
  - [ ] `Ctrl+A / Cmd+A` — 全选面板
  - [ ] `方向键` — 微调面板位置（Shift 步长 10px）

---

## Phase 6：后端集成 + 数据同步

**预估**：2-3 小时 | **优先级**：P1

- [ ] **6.1 后端 API（FastAPI）**
  - [ ] 创建 `app/routes/canvas.py` 路由模块
  - [ ] 创建 `app/models/canvas.py` 数据模型
  - [ ] 创建 `app/schemas/canvas.py` Pydantic schema
  - [ ] 实现 CRUD 接口（见设计文档 §5.1）

- [ ] **6.2 前端 API 客户端**
  - [ ] 创建 `frontend/src/api/canvas.js`
  - [ ] 封装所有画布 API 调用

- [ ] **6.3 数据同步**
  - [ ] 离开画布页面时自动同步
  - [ ] 操作后防抖 1 秒自动保存
  - [ ] 手动保存按钮
  - [ ] 加载画布时从后端拉取最新数据

- [ ] **6.4 与现有系统集成**
  - [ ] 面板关联 `task_id` 后从任务队列获取状态
  - [ ] 任务状态变化时自动更新面板
  - [ ] 从历史记录拖入面板

---

## Phase 7：UX 完善

**预估**：2-3 小时 | **优先级**：P1

- [ ] **7.1 实现 Minimap 小地图**
  - [ ] 右下角固定位置
  - [ ] 显示所有面板的缩略位置
  - [ ] 显示当前视口区域（高亮矩形）
  - [ ] 点击小地图跳转到对应区域

- [ ] **7.2 实现 CanvasRightPanel 右侧属性面板**
  - [ ] 选中面板时显示属性编辑
  - [ ] 编辑面板标题、颜色、备注
  - [ ] 编辑关联任务信息

- [ ] **7.3 性能优化**
  - [ ] 视口裁剪（`visiblePanels` getter 仅渲染可见面板）
  - [ ] CSS `contain: layout style paint` 隔离渲染
  - [ ] 连线 SVG 路径缓存

- [ ] **7.4 导入/导出**
  - [ ] `exportJSON()` 序列化画布为 JSON，提供下载
  - [ ] `importJSON(data)` 从 JSON 导入画布状态

- [ ] **7.5 导航入口**
  - [ ] 在 `App.vue` 顶部导航栏添加"画布"入口
  - [ ] 添加图标（使用 Element Plus icon）

---

## 验收标准

### 功能验收

- [ ] 用户可以打开 `/canvas` 页面并看到无限画布
- [ ] 用户可以通过拖拽背景来平移画布
- [ ] 用户可以通过滚轮缩放画布（0.1x - 3x 范围）
- [ ] 用户可以通过工具栏按钮缩放和重置视图
- [ ] 用户可以创建和管理多个画布（左侧栏切换）
- [ ] 用户可以添加 7 种类型的面板
- [ ] 面板可以在画布上自由拖拽移动
- [ ] 选中面板后可以调整大小（8 个方向）
- [ ] 选中面板后可以删除和复制
- [ ] 面板之间可以手动拖拽锚点连线（贝塞尔曲线）
- [ ] 系统可以根据任务关系自动创建连线
- [ ] 撤销/重做正常工作（最多 50 步）
- [ ] 键盘快捷键全部生效
- [ ] 画布数据保存到后端，刷新后恢复
- [ ] 深色主题与项目整体风格一致

### 性能验收

- [ ] 100 个面板时平移/缩放保持 60fps
- [ ] 50 条连线时渲染无卡顿
- [ ] 画布加载时间 < 2 秒

---

## 测试计划

### 单元测试
- [ ] `canvas-store.spec.js` — store 的 pan/zoom/CRUD 逻辑
- [ ] `coordinate-transform.spec.js` — 坐标转换函数
- [ ] `bezier-curve.spec.js` — 贝塞尔曲线计算

### 集成测试
- [ ] 创建 → 拖拽 → 连线 → 删除完整流程
- [ ] 缩放 → 拖拽 → 面板位置保持正确
- [ ] 撤销/重做后状态恢复正确
- [ ] localStorage 持久化恢复

### E2E 测试（Playwright）
- [ ] 打开画布页面，验证空白画布加载
- [ ] 滚轮缩放，验证 zoom level 变化
- [ ] 拖拽背景，验证画面移动
- [ ] 添加面板，验证面板出现在画布上
- [ ] 拖拽面板，验证位置变化
- [ ] 连线操作，验证连线创建和删除
- [ ] 键盘快捷键（Delete、Ctrl+Z）
- [ ] 多画布切换，验证状态隔离
