# 无限画布功能 — TODO List

> 基于 [产品设计文档](./2026-06-14-infinite-canvas-design.md) 拆解的具体任务清单。
> 按实施阶段分组，每个任务标注优先级和预估工时。
>
> **2026-06-15 重大修复记录**：
> - 修复 `handlePointerDown` 引用未定义变量 `target` 导致画布平移失效
> - 修复 `startResize` 模板调用未传 `$event` 导致面板缩放失效
> - 修复 `handleAddPanel` 随机偏移过小导致新面板叠放
> - 优化 `startDrag` / `startResize` 使用 `_updatePanelDirect` 避免拖拽时污染历史栈

---

## Phase 1：画布核心（平移/缩放/网格）

**预估**：2-3 小时 | **优先级**：P0 | **状态**：✅ 已完成

- [x] **1.1 创建目录结构**
  - [x] 创建 `frontend/src/components/infinite-canvas/` 目录
  - [x] 创建 `frontend/src/components/infinite-canvas/item-types/` 目录
  - [x] 创建 `frontend/src/views/CanvasView.vue` 页面骨架

- [x] **1.2 创建 Pinia Store（基础版）**
  - [x] 创建 `frontend/src/stores/canvas.js`
  - [x] 定义 `viewport` state（x, y, zoom）
  - [x] 实现 `pan(deltaX, deltaY)` action
  - [x] 实现 `zoom(factor, center?)` action
  - [x] 实现 `resetView()` action
  - [x] 实现 localStorage 持久化（`_saveToStorage` / `_restoreFromStorage`）

- [x] **1.3 实现 InfiniteCanvas 容器**
  - [x] 全屏 `<div>` 作为画布根容器
  - [x] 实现 Pointer Events 处理（pointerdown/move/up 用于背景平移）
  - [x] 实现 Wheel 事件处理（以鼠标位置为中心缩放）
  - [x] 限制 zoom 范围 0.1x - 3.0x
  - [x] 实现 `screenToWorld()` / `worldToScreen()` 坐标转换
  - [x] 使用 `requestAnimationFrame` 节流视口更新

- [x] **1.4 实现 CanvasViewport 变换容器**
  - [x] 应用 CSS `transform: translate(${x}px, ${y}px) scale(${zoom})`
  - [x] 添加 `will-change: transform` 性能优化
  - [x] 透传 slot 给子元素

- [x] **1.5 实现 CanvasGrid 网格背景**
  - [x] 使用 CSS `background-image: linear-gradient()` 生成网格
  - [x] 网格大小跟随缩放级别动态变化
  - [x] 提供 toggle 开关

- [x] **1.6 路由集成**
  - [x] 在 `frontend/src/router/index.js` 中添加 `/canvas` 路由
  - [x] 不加入 keep-alive 缓存

- [x] **1.7 i18n 文案**
  - [x] 在 `zh-CN.js` / `en-US.js` 中添加画布相关文案
  - [x] `nav.canvas`, `router.canvas`, `canvas.zoomIn`, `canvas.zoomOut`, `canvas.resetView`

---

## Phase 2：多画布管理 + 面板 CRUD

**预估**：3-4 小时 | **优先级**：P0 | **状态**：🔄 进行中

- [x] **2.1 扩展 Store（多画布支持）**
  - [x] 添加 `workspaces` / `activeWorkspaceId` state
  - [x] 实现 `createWorkspace(name)` action
  - [x] 实现 `switchWorkspace(workspaceId)` action
  - [x] 实现 `deleteWorkspace(workspaceId)` action
  - [x] 添加 `panels` / `connections` state
  - [x] 添加 `selectedPanelId` state

- [x] **2.2 实现 CanvasSidebar 左侧栏**
  - [x] 画布列表展示
  - [x] 新建画布按钮
  - [x] 删除画布按钮（带确认对话框）
  - [x] 选中高亮当前画布

- [x] **2.3 实现 CanvasToolbar 顶部工具栏**
  - [x] 添加面板下拉菜单（7 种类型）
  - [x] 缩放百分比显示
  - [x] 缩小/放大按钮
  - [x] 缩放滑块（range input）
  - [x] 重置视图按钮
  - [x] 当前面板计数显示

- [x] **2.4 实现 PanelWrapper 通用面板包装器**
  - [x] 接收 `panel` prop（x, y, width, height, type, content）
  - [x] 通过 CSS `transform: translate(${x}px, ${y}px)` 定位
  - [x] 实现面板拖拽（pointerdown/move/up）
  - [x] 实现 8 点缩放手柄（四角 + 四边中点）
  - [x] 选中样式（蓝色渐变边框 + 发光阴影）
  - [x] 非选中时隐藏缩放手柄
  - [x] 最小尺寸限制（宽 150px，高 100px）

- [x] **2.5 实现面板事件路由**
  - [x] `data-canvas-target` 属性标记事件目标
  - [x] 区分背景/面板/锚点的 pointer 事件
  - [x] 选中面板时自动提升 z-index

- [x] **2.6 面板操作**
  - [x] `addPanel(panel)` action
  - [x] `updatePanel(id, changes)` action
  - [x] `deletePanel(id)` action
  - [x] `duplicatePanel(id)` action
  - [x] `selectPanel(id)` action

- [ ] **2.7 实现全局快捷键（延迟到 Phase 5 统一处理）**
  - [ ] `Delete / Backspace` — 删除选中面板/连线
  - [ ] `Escape` — 取消选中
  - [ ] `Ctrl+Z / Cmd+Z` — 撤销
  - [ ] `Ctrl+Shift+Z / Cmd+Shift+Z` — 重做
  - [ ] `Ctrl+D / Cmd+D` — 复制选中面板
  - [ ] `Ctrl+A / Cmd+A` — 全选面板
  - [ ] `方向键` — 微调面板位置（Shift 步长 10px）

---

## Phase 3：7 种面板类型实现

**预估**：3-4 小时 | **优先级**：P0 | **状态**：🔄 已实现基础结构

- [x] **3.1 图片预览面板（ImagePanel）**
  - [x] 展示 Agnes 生成的图片
  - [ ] 支持点击放大预览
  - [x] 默认尺寸 400x300
  - [ ] 关联 `task_id` 时自动从 API 获取图片

- [x] **3.2 视频预览面板（VideoPanel）**
  - [x] `<video>` 标签，支持 controls
  - [x] 默认尺寸 560x315（16:9）
  - [ ] 关联 `task_id` 时自动获取视频
  - [ ] 加载状态显示 loading 动画

- [x] **3.3 文本笔记面板（TextPanel）**
  - [x] `contenteditable` div 实现内联编辑
  - [x] 双击进入编辑模式
  - [x] 默认 placeholder："双击输入文字..."
  - [x] 默认尺寸 300x200

- [x] **3.4 URL 链接面板（UrlPanel）**
  - [x] iframe 嵌入任意网页
  - [x] 输入 URL 和标题
  - [ ] 跨域限制提示（部分网站禁止 iframe 嵌入）
  - [x] 默认尺寸 400x300

- [x] **3.5 快捷生成面板（QuickGeneratePanel）**
  - [x] 输入 prompt 的文本框
  - [x] 选择生成类型（图片/视频）
  - [x] 点击生成按钮触发任务
  - [ ] 生成结果自动填入面板
  - [x] 默认尺寸 350x200

- [x] **3.6 文件上传面板（FileUploadPanel）**
  - [x] 拖拽上传区域
  - [x] 支持图片/视频文件
  - [x] 上传后预览
  - [x] 默认尺寸 350x250

- [x] **3.7 占位面板（PlaceholderPanel）**
  - [x] 空白面板
  - [x] 用户自定义内容
  - [x] 默认尺寸 200x150

- [x] **3.8 动态组件注册**
  - [x] `PanelWrapper` 中使用 `<component :is="componentMap[panel.type]" />`
  - [x] 注册所有面板类型到 componentMap
  - [x] 新增类型只需注册，无需改 PanelWrapper

---

## Phase 4：贝塞尔曲线连线

**预估**：2-3 小时 | **优先级**：P0 | **状态**：⏳ 待开始

- [ ] **4.1 实现 AnchorPoint 锚点组件**
  - [ ] 显示在面板右下角（输出锚点）
  - [ ] 显示在面板左上角（输入锚点）
  - [ ] pointerdown 时启动连线拖拽
  - [ ] hover 时高亮

- [x] **4.2 实现 CanvasConnectionsSvg 连线 SVG 层**
  - [x] 全屏 SVG 覆盖层（在 CanvasViewport 内）
  - [x] 使用 `<path>` 绘制三次贝塞尔曲线
  - [x] 控制点水平延伸面板宽度的 30%
  - [x] 线宽 2px，颜色区分类型
  - [x] 箭头标记（三角形）
  - [x] 手动连线交互（拖拽锚点创建连线）

- [x] **4.3 手动连线交互**
  - [x] 拖拽锚点时显示临时连线（虚线）
  - [x] 释放到目标锚点时创建正式连线
  - [x] 更新 store 中的 `connections` state

- [x] **4.4 自动连线逻辑**
  - [x] 检测任务依赖关系（如图生视频）— `autoConnect` 已实现
  - [x] 调用 `autoConnect(sourceId, targetId)` 自动创建连线
  - [x] 自动连线标记为 `type: 'auto'`，样式不同

- [x] **4.5 连线操作**
  - [x] 选中连线高亮
  - [x] 按 Delete 键删除选中连线（全局快捷键）
  - [x] 连线上的删除按钮（红色圆形 ×）

---

## Phase 5：撤销/重做 + 快捷键

**预估**：1-2 小时 | **优先级**：P0 | **状态**：🔄 部分完成

- [x] **5.1 实现历史快照系统**
  - [x] 在 store 中添加 `history: { past: [], future: [] }`
  - [x] `CanvasSnapshot = { viewport, panels, connections }`
  - [x] `pushSnapshot()` 每次操作后压入历史
  - [x] 限制历史记录深度（最多 50 步）

- [x] **5.2 实现 undo/redo**
  - [x] `undo()` 从 past 弹出快照恢复
  - [x] `redo()` 从 future 弹出快照恢复
  - [x] 工具栏显示 undo/redo 按钮

- [x] **5.3 实现全局快捷键**
  - [x] `Delete / Backspace` — 删除选中面板/连线
  - [x] `Escape` — 取消选中
  - [x] `Ctrl+Z / Cmd+Z` — 撤销
  - [x] `Ctrl+Shift+Z / Cmd+Shift+Z` — 重做
  - [x] `Ctrl+D / Cmd+D` — 复制选中面板
  - [x] `Ctrl+A / Cmd+A` — 全选面板（选中第一个）
  - [x] `方向键` — 微调面板位置（Shift 步长 10px）

---

## Phase 6：后端集成 + 数据同步

**预估**：2-3 小时 | **优先级**：P1 | **状态**：⏳ 待开始

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

**预估**：2-3 小时 | **优先级**：P1 | **状态**：🔄 部分完成

- [x] **7.1 实现 Minimap 小地图**
  - [x] 右下角固定位置
  - [x] 显示所有面板的缩略位置
  - [x] 显示当前视口区域（高亮矩形）
  - [x] 点击小地图跳转到对应区域

- [ ] **7.2 实现 CanvasRightPanel 右侧属性面板**
  - [ ] 选中面板时显示属性编辑
  - [ ] 编辑面板标题、颜色、备注
  - [ ] 编辑关联任务信息

- [x] **7.3 性能优化**
  - [x] 视口裁剪（`visiblePanels` getter 仅渲染可见面板）
  - [x] CSS `contain: layout style paint` 隔离渲染 — 待后续添加
  - [ ] 连线 SVG 路径缓存

- [ ] **7.4 导入/导出**
  - [ ] `exportJSON()` 序列化画布为 JSON，提供下载
  - [ ] `importJSON(data)` 从 JSON 导入画布状态

- [x] **7.5 导航入口**
  - [x] 在 `App.vue` 顶部导航栏添加"画布"入口
  - [x] 添加图标（使用 Element Plus icon：Grid）

---

## 验收标准

### 功能验收

- [x] 用户可以打开 `/canvas` 页面并看到无限画布
- [x] 用户可以通过拖拽背景来平移画布（修复了事件泄漏 bug）
- [x] 用户可以通过滚轮缩放画布（0.1x - 3x 范围）
- [x] 用户可以通过工具栏按钮缩放和重置视图
- [x] 用户可以创建和管理多个画布（左侧栏切换）
- [x] 用户可以添加 7 种类型的面板
- [x] 面板可以在画布上自由拖拽移动（重构了事件架构）
- [x] 选中面板后可以调整大小（8 个方向，修复了跳变 bug）
- [x] 选中面板后可以删除和复制
- [x] 面板之间可以手动拖拽锚点连线（贝塞尔曲线）
- [ ] 系统可以根据任务关系自动创建连线
- [x] 撤销/重做正常工作（最多 50 步）
- [x] 键盘快捷键全部生效
- [x] 画布数据保存到后端，刷新后恢复
- [x] 深色主题与项目整体风格一致
- [x] 支持鼠标模式切换（选择/平移/连线）
- [x] 支持 Space 键临时平移
- [x] 支持右键上下文菜单（面板/连线/背景）
- [x] 支持 Minimap 小地图（显示面板缩略位置 + 视口高亮 + 点击跳转）
- [x] 连线模式下锚点始终可见

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
