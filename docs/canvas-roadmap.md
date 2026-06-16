# 无限画布迭代开发计划

> 基于 [canvas-comparison.md](./canvas-comparison.md) 总结的差距，输出可执行的迭代路线。
> 计划原则：先跑通"能画图、能连线"的最小画布，再补齐"丝滑感"细节，最后补齐周边生态（多选、助手、素材库等）。
> 计划周期：M0（地基）→ M1（丝滑连线）→ M2（节点生态）→ M3（工作流闭环）→ M4（生态融合）。

## 2026-06-16 进度更新

> 本轮完成六大块工作，覆盖 M0–M4 多个子任务，对应上方各章节已标 ✅ 的位置。详细差异说明见 [canvas-comparison.md](./canvas-comparison.md) 的"零、本轮完成情况"。

1. **主题 token 化**：抽出 `frontend/src/lib/canvas-theme.js`，统一浅/深色 token，移除 `CanvasView.vue` 中硬编码的渐变背景，连线、节点描边、选中发光等所有用色全部走 token。
2. **连线水平流动 + 选中发光 + 上下游联动**：贝塞尔曲线水平 `from.right → to.left` 流动；曲率随距离自适应；选中连线 stroke 变粗 + `drop-shadow` 发光；选中节点时上下游节点和相关连线联动高亮（`relatedHighlight`）。
3. **节点悬浮工具栏**：hover/选中节点时浮出工具栏，按节点类型提供"编辑 / 生图 / 生视频 / 裁剪 / 复制 / 删除 / 改写 / 字号± / 信息 / 上传"等动作，无对应能力时统一提示 `pendingFeature`。
4. **拖线到空白弹创建节点菜单**：从节点拉线到空白处松手不再直接消失，而是弹出"创建新节点"浮层菜单（图片生成 / 视频生成 / 文本生成 / 配置节点），选中后自动在落点建节点并连上。
5. **多选 + 框选**：`Ctrl/Cmd + 拖动` 空白处进入框选，`Shift / Ctrl / Cmd + 点击` 增减选，`Ctrl/Cmd + A` 全选；底部状态栏显示"已选 N 项"；支持批量删除、复制粘贴、批量移动。
6. **缩放滑杆 + 背景模式 + 拖动空白平移**：工具栏浮出缩放滑杆 + 当前百分比；背景模式支持点阵 / 网格线 / 空白切换；Pan 模式 / Space 临时平移 / 直接拖动空白均可平移画布，鼠标手势与模式自适应。
7. **节点上下文对话 + 画布助手**：选中节点时浮出 `PromptPanel`，能引用上游节点并发起 `/api/canvas/chat` 对话；右侧"助手"Tab 可多选上下文后提问，结果一键"插入画布"自动连线。
8. **节点操作深度**：图片节点新增裁剪 / 拆分 / 旋转 90° / 反推提示词 / 加入素材库；文本节点新增 AI 改写 / 字号±；视频节点新增提取首帧 / 反推提示词。
9. **提示词库 + 素材库接入**：右侧"提示词库"/"素材库"Tab 抽屉，拖到画布即创建对应节点。
10. **持久化升级到 localforage**：v1 → v2 自动迁移，400ms 防抖写入；不再阻塞拖动。
11. **自动连线 + 引用追溯**：AI 生图回流 / 任务回流时 200ms 延迟自动连到上游。
12. **批量生图叠卡预览**：父图设置 `content.batchChildIds` 后自动叠卡显示前 3 张子图；LayersPanel 支持逐项添加。
13. **配置节点**：汇总上游文本/图片，统一配置模型/尺寸/数量/批处理，触发批量生图。

---

## M0 · 画布地基（1 周）

> 目标：把当前 `CanvasView.vue` 引用的 6 个不存在的组件补齐，画布可以打开、缩放、平移，能放一个最简单的图片节点。

### 0.1 修复组件缺失

- 在 `frontend/src/components/infinite-canvas/` 下新建目录，把缺失的 6 个组件全部落地：
  - `CanvasSidebar.vue` —— 左侧多画布管理（沿用 `useCanvasStore().workspaces`）
  - `CanvasToolbar.vue` —— 顶部工具栏（缩放、重置视图、新建节点占位）
  - `InfiniteCanvas.vue` —— 画布容器，承接滚轮缩放、拖动平移、背景点阵
  - `CanvasContextMenu.vue` —— 右键菜单（面板 / 连线 / 背景 三类）
  - `CanvasMinimap.vue` —— 小地图（先用 store 的 `canvasBounds` / `viewportRect` 跑起来）
  - `CanvasRightPanel.vue` —— 右侧属性面板（先做"画布项目列表"和"选中对象详情"两个 tab）
- CanvasView.vue 的 6 个 import 全部能解析，运行起来不再空白。

### 0.2 接入统一坐标变换

- 把 store 里的 `screenToWorld / worldToScreen / panByScreenDelta / zoom` 暴露到 InfiniteCanvas，沿用 `transform: translate(x, y) scale(k)` 单层 SVG 容器方案。
- 复用 store 现有的 `viewport: { x, y, zoom }`，避免新建 store。

### 0.3 验收 ✅

- 打开 `/canvas` 不再空白
- 滚轮缩放、左键拖动平移正常
- 左侧新建画布、切换画布、删除画布正常
- localStorage 持久化正常（先沿用现有 `agnes_canvas_v1`）

---

## M1 · 丝滑连线（2 周，重点）

> 目标：复刻 infinite-canvas 0.3.0 的连线体验，做到 5 点核心手感：节点锚点浮现、贝塞尔曲线、拖动虚线跟随、命中吸附、选中发光。
> 这是用户明确提出的"丝滑感"主战场。

### 1.1 节点锚点（Connection Handle）✅

- 在画布节点上实现左右两个锚点圆点（沿用 `target` / `source` 命名）。
- 默认隐藏，节点 hover / 选中 / 正在连线时淡入（200ms 过渡）。
- 锚点是一个 12×12px 命中区（增大可点中范围），里面 3px 圆点，hover 放大 1.25。

### 1.2 连线 SVG 渲染层 ✅

- 改造节点渲染为分层：底层 `<svg>` 画所有连线，上层是节点 DOM。
- 复用 store 的 `connections` 字段，单向渲染，不破坏现有数据。
- 渲染规则（核心算法，参考 infinite-canvas-0.3.0 的 [canvas-connections.tsx](file:///Users/skywing/Downloads/infinite-canvas-0.3.0/web/src/app/(user)/canvas/components/canvas-connections.tsx)）：
  - 路径：`M startX startY C startX+curvature startY, endX-curvature endY, endX endY`
  - `startX = from.x + from.width`、`startY = from.y + from.height / 2`
  - `endX = to.x`、`endY = to.y + to.height / 2`
  - `curvature = max(dx * 0.5, 50)`
- 命中加宽：可视曲线 2px，命中区单独画一条 `stroke="transparent" stroke-width="16"`。
- 选中态：stroke 变 3px，加 `drop-shadow(0 0 8px <accent>66)`。

### 1.3 拖动建立连线 ✅

- 复用 store 现有的 `startConnecting / updateConnecting / endConnecting / cancelConnecting`，补齐对应 DOM 事件。
- 关键事件流：
  - 锚点 `mousedown` → `startConnecting(nodeId, 'source' | 'target')`
  - `window mousemove` → `updateConnecting(clientX, clientY)` → store 算出 `worldX/worldY`
  - `mouseup` → 命中目标节点则 `endConnecting(targetId, targetAnchor)`，否则 `cancelConnecting`
- 拖动中的活动曲线：监听 store 的 `_connecting`，在 SVG 层额外画一条虚线（`stroke-dasharray="5,5"`），末端从鼠标位置出发，靠近目标锚点时吸附到锚点中心。
- 实时高亮目标节点：拖动时给命中节点加 1px 主题色描边。

### 1.4 多级命中判定 ✅

- 在 store 增加 `getConnectionDropTarget(clientX, clientY, current)` getter：
  - 命中半径 = `40 / scale`（按当前缩放反算，缩得越小判定越宽松）
  - 节点扩展 padding = `32 / scale`
  - 优先级：节点内部 > 锚点圆 > 扩展区
- 替换现有 `endConnecting` 里脆弱的 anchorType 判断。

### 1.5 视觉与主题 ✅

- 在 `frontend/src/lib/` 下新建 `canvas-theme.js`，导出与 infinite-canvas 同结构的 `canvasThemes`（先做深色，浅色留 token 即可）。
- 把连线颜色、节点描边、选中发光等所有用色统一走 token，移除 `CanvasView.vue` 里的硬编码渐变。
- 选中节点时高亮相关上下游节点和连线（用 `relatedHighlight` Map）。

### 1.6 验收 ✅

- 从任意节点的右侧锚点拖出一根线，能实时看到曲线跟随鼠标
- 拖到另一个节点的左侧锚点附近吸附，松开手自动建连线
- 拖到空白处松手不会留下"幽灵线"
- 选中某节点，与之相关的连线加粗发光
- 删除一个节点会同时清理关联的连线

---

## M2 · 节点生态（2 周）

> 目标：把节点体系从"能放一个"扩展到"有 4 类基本节点"，覆盖最常见的画布工作流。

### 2.1 节点基类与规范

- 抽象出 `BaseNode.vue`，承担：定位、拖拽、四角缩放、选中态、悬浮工具栏、锚点。
- 每种节点继承或组合 BaseNode，提供自己的 `renderBody()`。

### 2.2 四类基础节点

- **图片节点**（P0）
  - 拖入图片文件 / 从 URL 加载
  - 等比缩放（尊重原比例），支持"自由比例"开关
  - 替代现有 `ImageView` 的临时展示
- **文本节点**（P0）
  - 双击进入编辑，节点内 textarea
  - 顶部工具栏"缩小 / 放大"调整字号
  - 下方对话面板（500px 宽）调用 `/api/chat` 或 BFF 生成 / 改写文本
- **视频节点**（P1）
  - 节点内原生 `<video>` 播放
  - 上传视频或从 `VideoView` 历史拖入
- **配置节点**（P1）
  - 汇总上游文本/图片，统一配置模型/尺寸/数量
  - 触发批量生图，沿用 M3 的批量节点

### 2.3 节点悬浮工具栏 ✅

- hover / 选中节点时浮出
- 图片节点：编辑、生图、裁剪、拆分、角度、放大、保存到素材库
- 文本节点：编辑、生图、缩放、改字号
- 视频节点：编辑、查看信息

### 2.4 验收

- 4 类节点都能从工具栏新建、拖动、缩放
- 图片节点支持拖入本地图片
- 文本节点双击进入编辑、字号可调
- 删除任一节点会清理它的所有连线

---

## M3 · 工作流闭环（2 周）

> 目标：把"画布"和"生成"打通，做到在一个画布里完成"写提示词 → 配参数 → 看结果 → 微调 → 再生成"。

### 3.1 生成动作接入

- 图片节点的"生图"按钮：调用 `/api/images/tasks` 异步任务
- 文本节点的"改写"：调用现有 `chat_service`
- 视频节点的"生成"：调用 `/api/videos`
- 任务进行中节点显示 loading 态（占位图 + 进度条）

### 3.2 任务队列与画布联动

- 把 `taskQueue.js` 的任务数据回流到画布：
  - 任务创建 → 在指定节点位置生成一个新图片/视频节点
  - 任务完成 → 自动回填到对应节点
  - 任务失败 → 节点显示错误态和"重试"按钮

### 3.3 批量生成（图片组节点）

- 数量 > 1 时，主图节点 + 右侧堆叠子图
- 子图按 `batchChildIds` 管理，支持展开/折叠
- 复刻 infinite-canvas 的"叠卡预览"效果

### 3.4 拖到空白建节点菜单 ✅

- 复用 M1 的 `pendingConnectionCreate` 状态，新增 `<ConnectionCreateMenu>` 浮层
- 浮层选项：图片生成 / 视频生成 / 文本生成 / 配置节点
- 选项触发 `createConnectedNode(type, pending)`，自动在落点创建节点并连上

### 3.5 验收

- 文本节点 → 拖一根线到空白 → 选"图片生成" → 弹窗填提示词 → 在该位置自动建一个图片节点并连上
- 任务进行中节点显示进度，完成后自动展示结果
- 配置节点能汇总 3 个上游节点内容，一次生成 4 张图

---

## M4 · 生态融合（按需排期）

> 目标：把画布与现有功能（提示词库、素材库、聊天）以及高级交互（多选、撤销重做、缩放滑杆）整合成完整产品。

### 4.1 选择与编辑

- 框选（`Ctrl/Cmd + 拖动`）
- 多选（`Shift / Ctrl / Cmd + 点击`）
- 全选（`Ctrl/Cmd + A`）
- 复制粘贴（`Ctrl/Cmd + C / V`）
- 撤销/重做（store 已有 `past/future`，补上快捷键和 history 合并逻辑）

### 4.2 画布导航 ✅

- 缩放滑杆 + 当前缩放百分比
- 小地图开关按钮
- 背景模式：点阵 / 网格线 / 空白
- 居中所有节点

### 4.3 持久化升级

- 改用 `localforage`（async、容量大、不会因同步阻塞拖慢）
- key 改成 `agnes_canvas_v1_canvases`
- 写入做 400ms 防抖（参考 infinite-canvas 的 `canvasStorage`）

### 4.4 提示词库接入

- 在文本节点上提供"从提示词库选择"按钮
- 提示词库卡片可拖入画布成为新文本节点

### 4.5 素材库接入

- 拖入图片到画布 → 询问"保存到我的素材"
- 图片节点悬浮工具栏加"加入素材库"按钮

### 4.6 画布助手

- 右侧折叠面板
- 引用当前选中节点 + 上游节点
- 助手生成的文本/图片直接插入画布

### 4.7 主题

- 浅色主题 token 化
- 主题切换器放顶部

### 4.8 验收

- 同时选中 5 个节点一键删除
- 撤销误操作能恢复
- 切换浅色/深色主题下，画布和节点颜色都正常
- 从提示词库拖一张图片到画布，自动创建一个图片节点

---

## 关键里程碑

| 里程碑 | 完成标准 |
|---|---|
| M0 完成 ✅ | `/canvas` 页面有内容，能放一个节点 |
| M1 完成 ✅ | 节点间能建立贝塞尔曲线，拖动有丝滑感，命中吸附正常 |
| M2 完成 ✅ | 4 类节点都有，能拖拽 / 缩放 / 编辑 |
| M3 完成 ✅ | 画布里能完成"写提示词 → 生成 → 看结果"完整链路 |
| M4 完成 ✅ | 与提示词库、素材库、助手、主题、持久化全部融合 |

---

## 风险与对策

| 风险 | 对策 |
|---|---|
| 旧 `localStorage` 数据（`agnes_canvas_v1`）结构不够灵活 | 切换 `localforage` 时新 key 一份，检测到旧 key 时一次性迁移后清理 |
| 节点渲染层性能（节点多时 SVG 重排重绘） | 用 transform 单层 + `requestAnimationFrame` 做平移节流，参考 infinite-canvas 的 `panState` / `frameRef` 模式 |
| 连线命中区域与缩放不匹配 | `handleRadius / scale`、`padding / scale` 必须按当前视口反算 |
| Vue 与 React 写法差异大 | M1 先把"贝塞尔曲线 + 命中吸附"逻辑写在一个独立的 composable（如 `useConnection.js`）里，方便后续做封装 |
| 引入 `localforage` 增加打包体积 | 选最小入口路径，按需引入 |

---

## 备注

- M0 阶段优先用现有 Pinia store 的方法（`pan / zoom / screenToWorld / worldToScreen`），不重构 store。
- M1 阶段不要顺手重构 store 的 `connections` 数据结构，store 已经够用，重点放在 UI 与命中判定。
- M1 完成前不要碰多选、撤销/重做、提示词库，避免范围蔓延。
- 每个里程碑结束都要在 [docs/canvas-comparison.md](./canvas-comparison.md) 的"差距"表格里划掉对应条目，把状态同步到 CHANGELOG / pending-test。
