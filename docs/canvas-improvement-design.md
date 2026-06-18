# 无限画布改进设计文档

> 版本：v1.0
> 日期：2026-06-18
> 范围：`agnes-platform` 前端画布 UI 组件层补齐 + Config 组合面板生成端到端打通
> 参考项目：`/Users/skywing/Downloads/infinite-canvas-0.4.0`

***

## 一、现状分析

### 1.1 核心问题

当前 `agnes-platform` 的无限画布处于 **"有骨架无皮肤"** 状态：

| 层级            | 状态         | 说明                                                                                                         |
| ------------- | ---------- | ---------------------------------------------------------------------------------------------------------- |
| 后端服务          | ✅ 完整       | 图片/视频异步任务、SSE 聊天、历史管理、视频流代理均已就绪                                                                            |
| 前端 API 层      | ✅ 完整       | `api/images.js`、`api/videos.js`、`api/chat.js` 接口齐全                                                         |
| 前端逻辑层         | ✅ 基本就绪     | `stores/canvas.js`（1752 行）、`lib/canvas-generation.js`（522 行）、`lib/canvas-storage.js`、`lib/canvas-theme.js` |
| **前端 UI 组件层** | ❌ **完全缺失** | `@/components/infinite-canvas/` 目录不存在，CanvasView\.vue 引用的 12 个子组件全部找不到                                     |

### 1.2 "无法通过组合面板生成东西"的根因

经代码核查，存在 **四道独立阻断墙**，任一成立都会导致功能不可用：

1. **第一道墙（致命）**：`CanvasView.vue` 第 92-103 行 import 的 12 个 `@/components/infinite-canvas/` 子组件**全部不存在**，画布页面运行时直接空白，根本无法进入交互流程。

   * 验证：`frontend/src/components/` 下只有 5 个组件（ImageUploader、LanguageSwitcher、PromptTemplates、TaskCard、TaskQueuePanel），`infinite-canvas/` 子目录完全不存在。

2. **第二道墙**：即使画布能打开，`handleMergeGenerate`（CanvasView\.vue:504-541）仅支持 `panel.type === 'config'`，其他类型直接返回提示文案。

3. **第三道墙**：Config 节点需要先建立上游连接才有资源可收集（`buildGenerationContext` 依赖 `getUpstreamNodes`），但当前没有 UI 让用户创建 Config 节点、连接上游资源、编写 `composerContent`。

4. **第四道墙**：`generateVideo` case（CanvasView\.vue:484-486）仅返回提示文案 `t('canvas.editDialog.generateVideoHint')`，**视频生成入口未接入**。

### 1.3 逻辑层已具备的能力（无需重写）

以下逻辑已在 `lib/canvas-generation.js` 中实现，UI 组件只需调用：

* `isResourceNode(panel)` - 判断是否为资源节点（image/text/video/audio）

* `getUpstreamNodes(nodeId, panels, connections)` - 根据连线反查上游资源

* `extractResourceContentForComposer(panel)` - 提取 Composer 需要的 inputs 格式

* `buildGenerationContext(configNode, panels, connections)` - 构建生成上下文（支持 `@[node:xxx]` 引用解析）

* `createGenerationTask(ctx, config)` - 创建图片生成任务

* `pollImageTask(taskId, onProgress)` - 轮询任务状态

* `executeMergeGeneration(configId, store, options)` - 完整端到端流程

### 1.4 Store 已具备的能力（无需重写）

`stores/canvas.js` 已实现：

* 多画布工作区（`workspaces` / `activeWorkspaceId`）

* 视口变换（`viewport: { x, y, zoom }` + `screenToWorld` / `worldToScreen`）

* 面板 CRUD（`addPanel` / `updatePanel` / `deletePanel` / `duplicatePanel`）

* 连线管理（`addConnection` / `deleteConnection` / `endConnecting`）

* 选中状态（`selectedPanelId` / `selectedPanelIds` / `selectedConnectionId`）

* 撤销/重做（`pushSnapshot` / `undo` / `redo`，最多 50 步）

* 框选（`selectPanelsInRect` / `selectionBox`）

* 拖拽/缩放（`_dragging` / `_resizing` / `_updatePanelDirect`）

* 连线拖拽（`_connecting` / `endConnecting` / `pendingConnectionCreate`）

* Frame 模式（`createFrame` / `syncFrameChildren` / `enteredFrameId`）

* 持久化（`_hydrateFromStorage` + localforage 400ms 防抖）

* 主题（`themeMode` / `backgroundMode`）

* 自动连线延迟队列（`enqueueAutoConnect` / `pendingAutoConnect`）

***

## 二、参考项目核心设计借鉴

### 2.1 Config 节点作为工作流枢纽

`infinite-canvas-0.4.0` 的核心设计：**Config 节点是组合面板的中心**。

```
[文本节点] ──┐
[图片节点] ──┼──→ [Config 节点] ──→ [生成结果节点]
[视频节点] ──┘
```

* 上游资源节点通过连线汇聚到 Config 节点

* Config 节点的 `composerContent` 字段保存组装后的提示词（含 `@[node:xxx]` token）

* 生成时 `buildComposerGenerationContext` 解析 token，文本追加到 prompt 末尾，图片作为 referenceImages

### 2.2 双模式生成上下文

| 模式          | 触发条件                         | 行为                                                                                 |
| ----------- | ---------------------------- | ---------------------------------------------------------------------------------- |
| Composer 模式 | Config 节点有 `composerContent` | 解析 `@[node:xxx]` token，文本追加 `【文本1】\n内容`，图片收集为 referenceImages，prompt 中 token 替换为标签 |
| 简单合并模式      | 无 `composerContent`          | 所有上游文本拼到 prompt 末尾，所有图片作为 referenceImages                                          |

### 2.3 连线的隐式作用

`getConnectedConfigResourceNodes` 实现了智能行为：**当一个资源节点连向 Config 节点时，该节点自身生成时会使用 Config 节点收集的所有其他上游资源**。这是画布"工作流"的核心机制。

### 2.4 节点类型与默认规格

参考 `infinite-canvas-0.4.0/web/src/app/(user)/canvas/constants.ts` 的 `NODE_SPECS`：

| 类型       | 默认尺寸     | 用途               |
| -------- | -------- | ---------------- |
| `image`  | 240×200  | 图片节点（生成结果/上传）    |
| `text`   | 240×120  | 文本节点（提示词/笔记）     |
| `config` | 320×auto | **配置节点（组合面板核心）** |
| `video`  | 320×200  | 视频节点             |
| `audio`  | 240×80   | 音频节点             |

### 2.5 批量生成与结果布局

`addResultNode`（canvas-generation.js:462-499）在 Config 节点右侧按 4 列网格布局创建结果节点：

```
[Config] → [结果1] [结果2] [结果3] [结果4]
           [结果5] [结果6] ...
```

***

## 三、改进目标

### 3.1 核心目标

**让用户能够通过 Config 组合面板端到端生成图片/视频**：

1. 用户能打开画布页面（不再空白）
2. 用户能从工具栏添加 Text/Image/Config 节点
3. 用户能拖拽连线建立 Text → Config、Image → Config 的关系
4. 用户能双击 Config 节点打开 Composer，用 `@[node:xxx]` 组装提示词
5. 用户能点击"开始生成"按钮，触发 `executeMergeGeneration`
6. 生成结果自动回填到 Config 节点右侧的新 image 节点
7. 视频生成入口接入（Config 节点支持 `generationMode: 'video'`）

### 3.2 非目标（本次不做）

* 不实现 MCP server / 本地 Agent（`canvas-agent/`）

* 不实现 AI 助手面板的 ReAct 工具循环

* 不实现图片高级处理（蒙版编辑、3D 角度变换、超分等）

* 不实现批量生成的堆叠展开动画（BatchFrame）

* 不重写已就绪的逻辑层和后端

***

## 四、架构设计

### 4.1 组件分层

```
CanvasView.vue（页面壳，已存在）
├── CanvasSidebar.vue              ← 左侧多画布管理
├── CanvasToolbar.vue              ← 顶部工具栏（节点创建 + 搜索 + 导入导出）
├── InfiniteCanvas.vue             ← 画布主体（视口变换 + 节点/连线渲染 + 拖拽交互）
│   ├── CanvasConnectionsSvg.vue   ← 连线 SVG 层（贝塞尔曲线 + 锚点 + 拖线）
│   └── CanvasNode.vue             ← 单个节点渲染（按类型分发）
│       ├── ImageNodeContent       ← 图片节点内容
│       ├── TextNodeContent        ← 文本节点内容
│       ├── ConfigNodeContent      ← Config 节点内容（内嵌 CanvasConfigNodePanel）
│       ├── VideoNodeContent       ← 视频节点内容
│       └── AudioNodeContent       ← 音频节点内容
├── CanvasConfigNodePanel.vue      ← Config 节点面板（模式切换 + 模型 + 生成按钮）
├── CanvasConfigComposer.vue       ← Config 组合器（@[node:xxx] 富文本 + mention 菜单）
├── CanvasMinimap.vue              ← 小地图
├── CanvasQuickToolbar.vue         ← 底部浮动快捷工具栏
├── CanvasZoomControls.vue         ← 左下角缩放控制
├── CanvasNodeHoverToolbar.vue     ← 节点悬浮工具栏
├── CanvasRightPanel.vue           ← 右侧属性面板
├── CanvasContextMenu.vue          ← 右键菜单
├── ConnectionCreateMenu.vue       ← 拖线到空白弹出的创建菜单
├── PanelEditDialog.vue            ← 节点编辑弹窗
└── ImageCropDialog.vue            ← 图片裁剪弹窗
```

### 4.2 数据流

```
用户操作 → CanvasView.vue → store (canvas.js) → 持久化 (canvas-storage.js)
                ↓
         InfiniteCanvas.vue 渲染（响应 store 变化）
                ↓
         CanvasNode.vue / CanvasConnectionsSvg.vue
                ↓
用户点击生成 → CanvasConfigNodePanel → emit('generate', nodeId)
                ↓
         CanvasView.handleMergeGenerate → executeMergeGeneration (canvas-generation.js)
                ↓
         createImageTask → 后端 /api/images/tasks → Agnes AI
                ↓
         pollImageTask → 轮询 /api/images/tasks/{taskId}
                ↓
         addResultNode → store.addPanel + store.addConnection
                ↓
         InfiniteCanvas 响应式渲染新节点
```

### 4.3 视口变换数学

世界坐标 → 屏幕坐标的变换（已在 store 中实现）：

```
screenX = worldX * zoom + viewport.x
screenY = worldY * zoom + viewport.y
```

InfiniteCanvas.vue 的画布容器使用 CSS transform：

```css
.canvas-world {
  transform: translate(var(--vx)px, var(--vy)px) scale(var(--zoom));
  transform-origin: 0 0;
}
```

其中 `--vx` / `--vy` / `--zoom` 由 store.viewport 响应式驱动。

***

## 五、组件清单与职责

### 5.1 核心组件（必须实现，优先级 high）

#### 5.1.1 `InfiniteCanvas.vue` - 画布主体

**职责**：

* 渲染画布背景（点阵/网格/空白，根据 `store.backgroundMode`）

* 应用视口 transform（响应 `store.viewport`）

* 渲染所有可见面板（`store.visiblePanels`）

* 渲染连线 SVG 层（`CanvasConnectionsSvg`）

* 处理画布级鼠标事件：平移（Space/中键拖动）、框选、滚轮缩放

* 处理节点级事件：拖拽移动、四角缩放、锚点连线

* emit `panel-edit` / `panel-action` 给父组件

**Props**：无（直接读 store）
**Events**：`panel-edit(panel)` / `panel-action({ type, panel })`

**关键交互**：

* 鼠标按下空白 → 开始框选

* 鼠标按下节点 → 开始拖拽（记录起始位置）

* 鼠标按下锚点 → 开始连线（`store._connecting`）

* 滚轮 → 缩放（以鼠标位置为中心）

* Space 按下 → 平移模式

#### 5.1.2 `CanvasNode.vue` - 节点渲染

**职责**：

* 根据 `panel.type` 分发到对应内容组件

* 渲染节点外框、选中态、悬浮态

* 渲染左右锚点（Config 节点无右侧锚点）

* 渲染四角缩放 handle（图片节点保持比例）

* 处理节点级鼠标事件（拖拽/缩放/双击）

**Props**：`panel: Panel`
**Events**：`edit(panel)` / `action({ type, panel })` / `connect-start({ panelId, anchor })`

**节点类型分发**：

* `image` → 显示图片（`panel.content.imageUrl`），loading 态显示骨架，error 态显示重试

* `text` → 显示文本（`panel.content.text`），支持双击编辑

* `config` → 内嵌 `CanvasConfigNodePanel`

* `video` → 显示视频缩略图 + 播放按钮

* `audio` → 显示音频波形 + 播放按钮

#### 5.1.3 `CanvasConnectionsSvg.vue` - 连线渲染

**职责**：

* 渲染所有连线为贝塞尔曲线

* 渲染正在拖拽的临时连线（`store._connecting`）

* 渲染锚点圆点（hover 高亮）

* 处理连线点击选中、锚点拖拽开始

**路径公式**（参考 infinite-canvas-0.4.0）：

```
M startX startY
C startX+curvature startY, endX-curvature endY, endX endY
```

其中 `curvature = Math.max(dx * 0.5, 50)`，`dx = endX - startX`。

#### 5.1.4 `CanvasConfigNodePanel.vue` - Config 节点面板

**职责**：

* 模式切换（图片/视频/音频/文本，Segmented 组件）

* 输入统计 chip（显示上游资源数量）

* 模型选择器（根据模式显示不同模型列表）

* 设置弹窗按钮（图片尺寸/视频时长/音频音色等）

* "开始生成"按钮（调用 `emit('generate', nodeId)`）

* 双击展开 `CanvasConfigComposer`

**Props**：`panel: Panel`（Config 节点）
**Events**：`generate(nodeId)` / `update-content(changes)`

**生成按钮禁用条件**：无 `composerContent` 且无上游输入

#### 5.1.5 `CanvasConfigComposer.vue` - Config 组合器

**职责**：

* contentEditable 富文本编辑器

* 输入 `@` 触发 mention 菜单（列出上游资源节点）

* 插入引用 chip（图片显示缩略图，文本显示文字）

* 序列化为 `composerContent`（含 `@[node:xxx]` token）

* 反序列化渲染已有 token 为 chip

**Props**：`modelValue: string`（composerContent）/ `inputs: NodeInput[]`（上游资源）
**Events**：`update:modelValue(content)`

**Mention 菜单触发**：正则 `/(^|\s)@([^\s@]*)$/` 检测光标前是否有 `@query`

### 5.2 辅助组件（必须实现，优先级 medium）

#### 5.2.1 `CanvasToolbar.vue`

* 顶部工具栏

* 节点创建按钮（Text/Image/Config/Video/Audio）

* 搜索框（`/` 快捷键聚焦）

* 类型筛选

* 导入/导出 JSON 按钮

* 主题切换

* emit `export-json` / `import-json`

#### 5.2.2 `CanvasSidebar.vue`

* 左侧多画布管理

* 画布列表（创建/切换/重命名/删除）

* 当前画布高亮

#### 5.2.3 `CanvasZoomControls.vue`

* 左下角缩放控制

* 缩放滑杆（10% \~ 300%）

* 缩小/放大/重置按钮

* 小地图开关（`is-minimap-open` prop + `toggle-minimap` event）

#### 5.2.4 `CanvasMinimap.vue`

* 右下角小地图

* 显示所有节点的缩略色块

* 当前视口矩形

* 点击/拖动跳转视口

#### 5.2.5 `CanvasQuickToolbar.vue`

* 底部浮动快捷工具栏

* 撤销/重做

* 快速添加节点

* 主题切换

#### 5.2.6 `CanvasContextMenu.vue`

* 右键菜单

* 三种场景：背景右键 / 节点右键 / 连线右键

* 节点级动作：edit/crop/split/rotate/inferPrompt/addToAssets/rewrite/extractFirstFrame/fontUp/fontDown/generate/generateVideo/info/upload

* 通过 `ref.show(e, { target, data })` 调用，emit `panel-action`

#### 5.2.7 `CanvasNodeHoverToolbar.vue`

* 节点悬浮工具栏

* 根据节点类型显示不同工具

* Props: `panel` / `visible`

* Events: `action({ type, panel })` / `enter` / `leave`

#### 5.2.8 `CanvasRightPanel.vue`

* 右侧属性面板

* 选中节点时显示属性编辑（位置/尺寸/内容字段）

* 选中连线时显示连线属性

* 空白时显示画布属性（背景模式/网格大小）

#### 5.2.9 `ConnectionCreateMenu.vue`

* 拖线到空白时弹出的创建菜单

* 显示可创建的节点类型

* 选中后创建节点并自动连线

* 读取 `store.pendingConnectionCreate`

#### 5.2.10 `PanelEditDialog.vue`

* 节点编辑弹窗

* 按节点类型渲染不同表单

* Props: `modelValue`（visible）/ `panel`

* Events: `confirm({ panel, changes })`

#### 5.2.11 `ImageCropDialog.vue`

* 图片裁剪弹窗

* Props: `modelValue`（visible）/ `imageSrc`

* Events: `confirm({ width, height, base64 })`

***

## 六、实施计划

### 阶段 1：核心画布渲染（让画布能打开）

**目标**：访问 `/canvas` 路由不再空白，能看到节点和连线。

**任务**：

1. 创建 `frontend/src/components/infinite-canvas/` 目录
2. 实现 `InfiniteCanvas.vue`（画布主体 + 视口变换 + 背景渲染）
3. 实现 `CanvasNode.vue`（按类型渲染节点内容）
4. 实现 `CanvasConnectionsSvg.vue`（连线渲染 + 锚点）
5. 实现 `CanvasToolbar.vue`（基础工具栏，能添加节点）
6. 实现 `CanvasSidebar.vue`（多画布管理）
7. 实现 `CanvasZoomControls.vue`（缩放控制）

**验收**：能添加 Text/Image/Config 节点，能拖拽移动，能连线，能缩放平移。

### 阶段 2：Config 组合面板生成（核心目标）

**目标**：能通过 Config 节点端到端生成图片。

**任务**：

1. 实现 `CanvasConfigNodePanel.vue`（模式切换 + 模型选择 + 生成按钮）
2. 实现 `CanvasConfigComposer.vue`（@\[node:xxx] 富文本 + mention 菜单）
3. 在 `CanvasNode.vue` 中集成 Config 节点面板
4. 验证 `executeMergeGeneration` 端到端流程
5. 验证结果节点回填

**验收**：

* 添加 Text 节点输入"一只猫"

* 添加 Config 节点

* 连线 Text → Config

* 双击 Config 打开 Composer

* 输入"画一只 @\[文本1]"

* 点击生成

* 结果图片出现在 Config 右侧

### 阶段 3：交互完善

**目标**：补齐右键菜单、悬浮工具栏、属性面板等交互组件。

**任务**：

1. 实现 `CanvasContextMenu.vue`
2. 实现 `CanvasNodeHoverToolbar.vue`
3. 实现 `CanvasRightPanel.vue`
4. 实现 `ConnectionCreateMenu.vue`
5. 实现 `CanvasMinimap.vue`
6. 实现 `CanvasQuickToolbar.vue`
7. 实现 `PanelEditDialog.vue`
8. 实现 `ImageCropDialog.vue`

### 阶段 4：视频生成接入

**目标**：Config 节点支持视频生成模式。

**任务**：

1. 在 `CanvasConfigNodePanel.vue` 支持模式切换到 `video`
2. 在 `canvas-generation.js` 新增 `executeMergeVideoGeneration`（参考图片流程）
3. 在 `CanvasView.vue` 的 `generateVideo` case 调用视频生成
4. 视频结果节点回填

***

## 七、关键技术点

### 7.1 视口变换与坐标转换

所有节点位置存储为**世界坐标**，渲染时通过 CSS transform 转换为屏幕坐标：

```vue
<div class="canvas-world" :style="worldStyle">
  <CanvasNode v-for="panel in visiblePanels" :key="panel.id" :panel="panel" />
  <CanvasConnectionsSvg />
</div>
```

```js
const worldStyle = computed(() => ({
  transform: `translate(${store.viewport.x}px, ${store.viewport.y}px) scale(${store.viewport.zoom})`,
  transformOrigin: '0 0',
}))
```

鼠标事件坐标转换：

```js
function getWorldCoord(e) {
  return store.screenToWorld(e.clientX, e.clientY)
}
```

### 7.2 连线锚点位置计算

锚点使用语义化位置（`left-middle` / `right-middle`）：

```js
function getAnchorPos(panel, anchor) {
  switch (anchor) {
    case 'left-middle':   return { x: panel.x, y: panel.y + panel.height / 2 }
    case 'right-middle':  return { x: panel.x + panel.width, y: panel.y + panel.height / 2 }
    case 'top-middle':    return { x: panel.x + panel.width / 2, y: panel.y }
    case 'bottom-middle': return { x: panel.x + panel.width / 2, y: panel.y + panel.height }
  }
}
```

### 7.3 Composer 的 contentEditable 序列化

**序列化**（DOM → composerContent）：

* 遍历编辑器子节点

* 文本节点 → 原样输出

* chip 元素 → 输出 `@[node:nodeId]`（从 `data-node-id` 属性读取）

**反序列化**（composerContent → DOM）：

* 正则 `@\[node:([^\]]+)\]/g` 匹配 token

* 替换为 chip 元素（图片 chip 显示缩略图，文本 chip 显示文字）

### 7.4 Config 节点生成流程

```
1. 用户点击"开始生成"
2. CanvasConfigNodePanel emit('generate', nodeId)
3. CanvasView.handleMergeGenerate(panel)
4. executeMergeGeneration(panel.id, store, { count, onProgress })
5.   buildGenerationContext(panel, store.panels, store.connections)
6.   → { prompt, referenceImages, inputSummary }
7.   createGenerationTask(ctx, config) → POST /api/images/tasks
8.   pollImageTask(taskId, onProgress) → GET /api/images/tasks/{taskId}
9.   addResultNode(store, panel, resultUrl, i)
10.    store.addPanel(newImagePanel) → 返回 newId
11.    store.addConnection({ source: panel.id, target: newId })
12. InfiniteCanvas 响应式渲染新节点
```

### 7.5 主题系统

使用 CSS 变量 + `data-theme` 属性（已在 CanvasView\.vue 中定义）：

```css
.canvas-view[data-theme="dark"] {
  --canvas-bg: ...;
  --canvas-node-border: ...;
  --canvas-connection-active: ...;
}
```

组件内**不硬编码颜色**，全部使用 `var(--canvas-xxx)`。

### 7.6 性能优化

* `visiblePanels` getter 只渲染视口内节点

* 节点使用 `v-memo` 或 `shallowRef` 避免不必要重渲染

* 拖拽/缩放期间使用 `_updatePanelDirect`（不压栈、不持久化），松手时一次性 `saveCanvas`

* 连线 SVG 使用单一 `<svg>` 容器，所有 path 集中渲染

***

## 八、与参考项目的差异说明

### 8.1 技术栈差异

| 维度   | infinite-canvas-0.4.0 | agnes-platform     |
| ---- | --------------------- | ------------------ |
| 框架   | Next.js + React       | Vue 3 + Vite       |
| 状态   | Zustand               | Pinia              |
| UI 库 | Ant Design + Tailwind | Element Plus       |
| 持久化  | localforage           | localforage（已就绪）   |
| 后端   | 无（前端直连 OpenAI）        | FastAPI + Agnes AI |

### 8.2 实现策略

* **不移植 React 代码**，而是参考设计思路用 Vue 3 Composition API 重写

* **复用已有逻辑层**：`canvas.js` / `canvas-generation.js` / `canvas-storage.js` / `canvas-theme.js` 不重写

* **复用已有 API 层**：`api/images.js` / `api/videos.js` 不重写

* **Element Plus 替代 Ant Design**：使用 `ElButton` / `ElInput` / `ElDialog` / `ElMessage` 等

### 8.3 字段命名对齐

agnes-platform 的 Panel 结构与 infinite-canvas 的 Node 结构字段映射：

| agnes-platform (Panel)          | infinite-canvas (Node)                | 说明                                |
| ------------------------------- | ------------------------------------- | --------------------------------- |
| `panel.id`                      | `node.id`                             | ID                                |
| `panel.type`                    | `node.type`                           | 类型（image/text/config/video/audio） |
| `panel.x` / `panel.y`           | `node.position.x` / `node.position.y` | 位置                                |
| `panel.width` / `panel.height`  | `node.width` / `node.height`          | 尺寸                                |
| `panel.content`                 | `node.metadata`                       | 内容/元数据                            |
| `panel.content.composerContent` | `node.metadata.composerContent`       | Config 组合提示词                      |
| `panel.content.prompt`          | `node.metadata.prompt`                | 提示词                               |
| `panel.content.model`           | `node.metadata.model`                 | 模型                                |
| `panel.content.size`            | `node.metadata.size`                  | 尺寸                                |
| `panel.content.count`           | `node.metadata.count`                 | 批量数量                              |
| `panel.content.status`          | `node.metadata.status`                | 状态（idle/loading/success/error）    |
| `panel.content.imageUrl`        | `node.metadata.content`               | 图片 URL/base64                     |
| `panel.content.text`            | `node.metadata.content`               | 文本内容                              |
| `panel.content.videoUrl`        | `node.metadata.content`               | 视频 URL                            |
| `connection.source_panel_id`    | `connection.fromNodeId`               | 连线起点                              |
| `connection.target_panel_id`    | `connection.toNodeId`                 | 连线终点                              |

***

## 九、风险与缓解

### 9.1 风险：组件实现工作量大

**12 个组件 + 视口变换 + 拖拽交互**，工作量较大。

**缓解**：

* 分阶段实施，阶段 1（核心渲染）完成后即可验收画布能打开

* 复用已有逻辑层，UI 组件只做渲染和事件转发

* 优先实现最小可用版本，高级特性（蒙版编辑、3D 变换等）不做

### 9.2 风险：视口变换与坐标转换 bug

**缓解**：

* 严格使用 `store.screenToWorld` / `store.worldToScreen`，不手算

* 拖拽时记录起始世界坐标，移动时用 delta 更新

* 连线锚点位置实时从 panel 坐标计算

### 9.3 风险：contentEditable 浏览器兼容性

**缓解**：

* 序列化/反序列化使用明确的 DOM 遍历规则，不依赖 innerHTML

* chip 元素使用 `data-node-id` 属性存储 ID

* mention 菜单使用绝对定位浮层，不依赖 contentEditable 原生下拉

### 9.4 风险：生成任务超时

**缓解**：

* `pollImageTask` 已有 5 分钟超时

* `onProgress` 回调实时更新 UI

* 失败时 `ElMessage.error` 提示，不阻塞画布

***

## 十、验收标准

### 10.1 阶段 1 验收

* [ ] 访问 `/canvas` 路由不再空白

* [ ] 能从工具栏添加 Text/Image/Config/Video/Audio 节点

* [ ] 节点能拖拽移动

* [ ] 节点能四角缩放

* [ ] 能从节点右侧锚点拖线到另一节点左侧锚点建立连线

* [ ] 滚轮能缩放画布（以鼠标位置为中心）

* [ ] Space 按住能平移画布

* [ ] Ctrl+Z / Ctrl+Y 能撤销/重做

* [ ] Delete 能删除选中节点

### 10.2 阶段 2 验收（核心目标）

* [ ] 能添加 Text 节点并输入文本

* [ ] 能添加 Config 节点

* [ ] 能连线 Text → Config

* [ ] 双击 Config 节点能打开 Composer

* [ ] 在 Composer 输入 `@` 能弹出 mention 菜单

* [ ] 选择 mention 项能插入 chip

* [ ] 点击"开始生成"能触发图片生成

* [ ] 生成过程中显示进度提示

* [ ] 生成完成后结果图片出现在 Config 节点右侧

* [ ] 结果节点与 Config 节点有连线

### 10.3 阶段 3 验收

* [ ] 右键节点能弹出上下文菜单

* [ ] 右键菜单的"编辑"能打开 PanelEditDialog

* [ ] 右键菜单的"裁剪"能打开 ImageCropDialog

* [ ] 节点悬浮能显示工具栏

* [ ] 右侧属性面板能编辑选中节点属性

* [ ] 拖线到空白能弹出创建菜单

* [ ] 小地图能显示缩略并跳转视口

### 10.4 阶段 4 验收

* [ ] Config 节点能切换到视频模式

* [ ] 视频模式能选择模型和参数

* [ ] 点击生成能触发视频任务

* [ ] 视频结果节点能播放

***

## 附录 A：关键文件路径索引

### A.1 已就绪文件（无需修改）

**前端逻辑层**：

* `frontend/src/stores/canvas.js` - Pinia store（1752 行）

* `frontend/src/lib/canvas-generation.js` - 合并生成逻辑（522 行）

* `frontend/src/lib/canvas-storage.js` - localforage 持久化

* `frontend/src/lib/canvas-theme.js` - 主题 token

**前端 API 层**：

* `frontend/src/api/images.js` - 图片任务 API

* `frontend/src/api/videos.js` - 视频任务 API

* `frontend/src/api/chat.js` - 聊天 API

* `frontend/src/api/client.js` - axios 实例

**后端**：

* `backend/app/routes/images.py` - 图片任务路由

* `backend/app/routes/videos.py` - 视频任务路由

* `backend/app/services/agnes_client.py` - Agnes AI 客户端

* `backend/app/services/image_poller.py` - 图片任务轮询

* `backend/app/services/video_poller.py` - 视频任务轮询

### A.2 需创建文件

```
frontend/src/components/infinite-canvas/
├── InfiniteCanvas.vue
├── CanvasNode.vue
├── CanvasConnectionsSvg.vue
├── CanvasConfigNodePanel.vue
├── CanvasConfigComposer.vue
├── CanvasToolbar.vue
├── CanvasSidebar.vue
├── CanvasZoomControls.vue
├── CanvasMinimap.vue
├── CanvasQuickToolbar.vue
├── CanvasContextMenu.vue
├── CanvasNodeHoverToolbar.vue
├── CanvasRightPanel.vue
├── ConnectionCreateMenu.vue
├── PanelEditDialog.vue
└── ImageCropDialog.vue
```

### A.3 需修改文件

* `frontend/src/views/CanvasView.vue` - 接入视频生成（`generateVideo` case）

* `frontend/src/lib/canvas-generation.js` - 新增 `executeMergeVideoGeneration`（可选）

### A.4 参考文件

* `/Users/skywing/Downloads/infinite-canvas-0.4.0/web/src/app/(user)/canvas/components/` - 30+ 成熟组件

* `/Users/skywing/Downloads/infinite-canvas-0.4.0/web/src/app/(user)/canvas/[id]/canvas-client-page.tsx` - 画布主页面（核心生成逻辑）

* `/Users/skywing/Downloads/infinite-canvas-0.4.0/web/src/app/(user)/canvas/components/canvas-config-composer.tsx` - Config 组合器

* `/Users/skywing/Downloads/infinite-canvas-0.4.0/web/src/app/(user)/canvas/components/canvas-config-node-panel.tsx` - Config 节点面板

* `/Users/skywing/Downloads/infinite-canvas-0.4.0/web/src/app/(user)/canvas/utils/canvas-resource-references.ts` - 资源引用工具

