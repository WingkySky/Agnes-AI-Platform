# 无限画布对比分析：infinite-canvas-0.3.0 vs agnes-platform

> 对比日期：2026-06-16
> 对比目的：评估我方平台与社区成熟方案在"无限画布"产品形态上的差异，重点剖析面板之间连接线（connections）的实现差距，并据此给出我方的迭代方向。

## 零、本轮完成情况（2026-06-16 进度更新）

> 本轮对应 M0–M4 多个子任务的实现落地，下列六大块均已完成并接入画布，对应 `canvas-roadmap.md` 各项子任务打勾。详细差距是否已划掉见文末"六、关键差异汇总"。

1. **主题 token 化**：抽出 `frontend/src/lib/canvas-theme.js`，统一浅/深色 token，移除 `CanvasView.vue` 中硬编码的渐变背景，连线、节点描边、选中发光等所有用色全部走 token。
2. **连线水平流动 + 选中发光 + 上下游联动**：贝塞尔曲线水平 `from.right → to.left` 流动；曲率随距离自适应 `curvature = max(dx * 0.5, 50)`；选中连线 stroke 变粗 + `drop-shadow` 发光；选中节点时上下游节点和相关连线联动高亮（`relatedHighlight`）。
3. **节点悬浮工具栏**：hover/选中节点时浮出工具栏，按节点类型提供"编辑 / 生图 / 生视频 / 裁剪 / 复制 / 删除 / 改写 / 字号± / 信息 / 上传"等动作，无对应能力时统一提示 `pendingFeature`。
4. **拖线到空白弹创建节点菜单**：从节点拉线到空白处松手不再直接消失，而是弹出"创建新节点"浮层菜单（图片生成 / 视频生成 / 文本生成 / 配置节点），选中后自动在落点建节点并连上。
5. **多选 + 框选**：`Ctrl/Cmd + 拖动` 空白处进入框选，`Shift / Ctrl / Cmd + 点击` 增减选，`Ctrl/Cmd + A` 全选；底部状态栏显示"已选 N 项"；支持批量删除、复制粘贴、批量移动。
6. **缩放滑杆 + 背景模式 + 拖动空白平移**：工具栏浮出缩放滑杆 + 当前百分比；背景模式支持点阵 / 网格线 / 空白切换；Pan 模式 / Space 临时平移 / 直接拖动空白均可平移画布，鼠标手势与模式自适应。
7. **节点上下文对话 + 画布助手**：节点下方 PromptPanel + 右侧助手 Tab。
8. **节点操作深度**：裁剪 / 拆分 / 旋转 / 反推 / AI 改写。
9. **提示词库 + 素材库**：右侧抽屉可拖入画布。
10. **持久化升级 localforage**：v1→v2 迁移，400ms 防抖。
11. **自动连线 + 引用追溯**：200ms 延迟。
12. **批量生图叠卡**：父图自动叠卡。
13. **配置节点**：批量生图触发。

## 一、项目整体定位对比

| 维度 | infinite-canvas-0.3.0 | agnes-platform（我方） |
|---|---|---|
| 技术栈 | Next.js (App Router) + TypeScript + Ant Design + Tailwind + Zustand，后端 Go + Gin + GORM | Vue 3 + Vite + Element Plus + Pinia，后端 FastAPI + SQLAlchemy |
| 持久化 | 浏览器本地（`localforage` 异步封装）+ Go 后台管理后台 | 浏览器 localStorage（`agnes_canvas_v1`）+ FastAPI 历史持久化 |
| AI 接入 | 本地直连 / 后台代理双通道，OpenAI 兼容 | 单一 BFF 通道，封装 Agnes AI 官方 API |
| 画布节点 | 图片 / 文本 / 配置 / 视频 / 音频 共 5 类 | 暂无可见节点实现（仅 store 层） |
| 已发布版本 | v0.3.0（多轮迭代，画布已成型） | 当前正在搭建画布 UI，CanvasView 引用了若干尚不存在的子组件 |

## 二、画布代码结构对比

### infinite-canvas-0.3.0 的画布目录（成熟形态）

```
web/src/app/(user)/canvas/
├── components/
│   ├── infinite-canvas.tsx           # 画布容器：滚轮缩放 / 拖动平移 / 背景点阵
│   ├── canvas-connections.tsx        # 静态连线 + 拖动中的活动连线
│   ├── canvas-node.tsx               # 节点壳，含左右连接点
│   ├── canvas-node-prompt-panel.tsx  # 节点下方的提示词面板
│   ├── canvas-node-hover-toolbar.tsx # 节点悬停工具栏
│   ├── canvas-config-composer.tsx    # 配置节点
│   ├── canvas-assistant-panel.tsx    # 画布助手
│   ├── canvas-local-agent-panel.tsx  # 本地 Agent 面板
│   ├── canvas-mini-map.tsx           # 小地图
│   ├── canvas-toolbar.tsx            # 顶部工具栏
│   ├── canvas-zoom-controls.tsx      # 缩放控件
│   └── ...（30+ 组件）
├── stores/
│   ├── use-canvas-store.ts           # 项目维度持久化
│   ├── use-canvas-ui-store.ts        # UI 状态
│   └── use-canvas-agent-store.ts     # 本地 Agent 状态
├── utils/
│   ├── canvas-node-size.ts           # 等比缩放算法
│   ├── canvas-image-data.ts          # 图像处理
│   └── canvas-resource-references.ts # 引用与提示词拼接
├── types.ts                          # 节点/连线/视口/选择框/事件类型
└── constants.ts                      # 节点默认尺寸、状态常量
```

### agnes-platform 的画布目录（仅数据层）

```
frontend/src/
├── stores/
│   └── canvas.js                     # Pinia store：多画布、视口、面板、连线、撤销/重做
└── views/
    └── CanvasView.vue                # 页面壳，引用下列不存在的组件：
        ├── @/components/infinite-canvas/CanvasSidebar.vue    # 不存在
        ├── @/components/infinite-canvas/CanvasToolbar.vue    # 不存在
        ├── @/components/infinite-canvas/InfiniteCanvas.vue   # 不存在
        ├── @/components/infinite-canvas/CanvasContextMenu.vue# 不存在
        ├── @/components/infinite-canvas/CanvasMinimap.vue    # 不存在
        └── @/components/infinite-canvas/CanvasRightPanel.vue # 不存在
```

> 结论：我方画布目前只有"数据骨架"，还没有真正可交互的画布。CanvasView.vue 中引用的 6 个核心组件全部缺失，运行时会直接空白。

## 三、连接线（Connection）实现差异 —— 核心差距

这是用户最关心的"丝滑感"的来源。下面对比两边的实现细节。

### 1. 连线渲染

| 维度 | infinite-canvas-0.3.0 | agnes-platform |
|---|---|---|
| 渲染方式 | React + SVG `<path>`，曲线 + 透明粗 hit area | 无渲染（仅 store 数据） |
| 路径形态 | 三次贝塞尔曲线 `M startX startY C startX+curvature startY, endX-curvature endY, endX endY` | 无 |
| 曲率自适应 | `curvature = max(dx * 0.5, 50)` 距离越远越舒展 | 无 |
| 连线方向 | 始终 `from.right → to.left`，水平流动，视觉整齐 | 无（store 记录 source/target 但无锚点渲染） |
| 活动连线预览 | 拖动时用虚线 `5,5` 实时跟随鼠标 | store 记录 `worldX/worldY` 但页面无任何 SVG |
| 选中态 | 选中时 stroke 变粗 + `drop-shadow` 发光 | 仅高亮 `selectedConnectionId`，无渲染 |

核心代码（infinite-canvas-0.3.0 的 [canvas-connections.tsx:7-60](file:///Users/skywing/Downloads/infinite-canvas-0.3.0/web/src/app/(user)/canvas/components/canvas-connections.tsx#L7-L60)）：

```tsx
// 三次贝塞尔曲线，曲率随水平距离自动调整
const startX = from.position.x + from.width;
const startY = from.position.y + from.height / 2;
const endX = to.position.x;
const endY = to.position.y + to.height / 2;
const dx = Math.abs(endX - startX);
const curvature = Math.max(dx * 0.5, 50);
const pathD = `M ${startX} ${startY} C ${startX + curvature} ${startY}, ${endX - curvature} ${endY}, ${endX} ${endY}`;

return (
    <g>
        {/* 透明加粗 hit area：16px 宽，鼠标更容易点中 */}
        <path d={pathD} stroke="transparent" strokeWidth="16" pointerEvents="stroke" onClick={onSelect} />
        {/* 可见曲线：选中态变粗 + 发光 */}
        <path d={pathD} stroke={active ? theme.node.activeStroke : theme.node.muted}
              strokeWidth={active ? 3 : 2} strokeOpacity={active ? 1 : 0.82}
              style={{ filter: active ? `drop-shadow(0 0 8px ${theme.node.activeStroke}66)` : undefined }} />
    </g>
);
```

### 2. 连线锚点（Handle）

| 维度 | infinite-canvas-0.3.0 | agnes-platform |
|---|---|---|
| 节点上的锚点 | 左侧 `target` + 右侧 `source` 两个圆点，仅在 hover/选中/连线时显示 | store 记录 `input/output` 但无 UI |
| 视觉 | 12×12px 命中区 + 3px 实心点，hover 放大 1.25 | 无 |
| 出现条件 | `visible={hovered || isSelected || isConnecting}` 平滑淡入淡出 | 无 |
| 锚点位置 | 永远在节点左/右中点 | store 写死 `bottom-right → top-left`（与渲染无关） |

核心代码（infinite-canvas-0.3.0 的 [canvas-node.tsx:666-678](file:///Users/skywing/Downloads/infinite-canvas-0.3.0/web/src/app/(user)/canvas/components/canvas-node.tsx#L666-L678)）：

```tsx
function ConnectionHandleDot({ side, visible, onMouseDown }) {
    return (
        <div className={`absolute top-1/2 z-30 flex size-12 -translate-y-1/2 cursor-crosshair
                         ${side === "left" ? "-left-6" : "-right-6"}
                         ${visible ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0"}
                         transition-opacity duration-150`}
             onMouseDown={onMouseDown}>
            <div className="size-3 rounded-full border-2 transition-all hover:scale-125"
                 style={{ background: theme.node.panel, borderColor: theme.node.muted }} />
        </div>
    );
}
```

### 3. 拖动建立连线的命中判定

| 维度 | infinite-canvas-0.3.0 | agnes-platform |
|---|---|---|
| 命中半径 | `CONNECTION_HANDLE_HIT_RADIUS = 40 / scale`（按缩放反算） | 无 |
| 扩展 padding | `CONNECTION_NODE_HIT_PADDING = 32 / scale` | 无 |
| 命中优先级 | 节点内部 (0) > 锚点圆 (1) > 扩展区 (2)，按优先级取最优 | 仅判断 `closest('[data-canvas-target]')` |
| 拖动中实时高亮 | `connectionTargetNodeId` 状态实时更新目标节点描边 | 无 |
| 释放判定 | 命中节点即连；未命中且远离节点取消；未命中但靠近节点也取消（避免误连） | `endConnecting` 时若提供 `targetPanelId/anchorType` 则建连线 |

核心代码（infinite-canvas-0.3.0 的 [canvas-client-page.tsx:542-577](file:///Users/skywing/Downloads/infinite-canvas-0.3.0/web/src/app/(user)/canvas/[id]/canvas-client-page.tsx#L542-L577)）：

```ts
const getConnectionDropTarget = (clientX, clientY, current) => {
    const world = screenToCanvas(clientX, clientY);
    const scale = Math.max(viewportRef.current.k, 0.05);
    const padding = CONNECTION_NODE_HIT_PADDING / scale;
    const handleRadius = CONNECTION_HANDLE_HIT_RADIUS / scale;
    let bestNodeId = null, bestPriority = Infinity;

    for (const node of [...nodesRef.current].reverse()) {
        const anchor = getConnectionTargetAnchor(node, current);
        const dx = world.x - anchor.x, dy = world.y - anchor.y;
        const hitsHandle = dx*dx + dy*dy <= handleRadius*handleRadius;
        const hitsInside = world.x >= node.position.x && world.x <= node.position.x + node.width && ...;
        const hitsExpanded = world.x >= node.position.x - padding && ...;

        if (!hitsHandle && !hitsInside && !hitsExpanded) continue;
        if (node.id === current.nodeId || !normalizeConnection(...)) continue;

        const priority = hitsInside ? 0 : hitsHandle ? 1 : 2;
        if (priority < bestPriority) { bestNodeId = node.id; bestPriority = priority; }
    }
    return { nodeId: bestNodeId, isNearNode: bestNodeId !== null || ... };
};
```

### 4. 拖动中预览曲线

| 维度 | infinite-canvas-0.3.0 | agnes-platform |
|---|---|---|
| 实时跟随 | `setMouseWorld(screenToCanvas(...))` 每帧更新 | store 记录 `worldX/worldY`，但页面无 SVG |
| 末端吸附 | 接近目标锚点时曲线末端会"吸"到锚点中心 | 无 |
| 视觉差异 | 拖动中虚线（`strokeDasharray="5,5"`），与正式连线区分 | 无 |
| 拖出画布 | 释放时若不在任何节点上则自动取消 | store 直接置 null |

### 5. 拖到空白处的"创建节点"菜单（杀手级细节）

> 这是 infinite-canvas 最亮眼的一处体验：用户从一个节点拉出一根线，在空白处松开手，不会直接消失，而是弹出一个浮层菜单"引用该节点生成"（图片/视频/文本/音频/配置节点）。选哪个就在那里建一个对应节点并自动连上。

| 维度 | infinite-canvas-0.3.0 | agnes-platform |
|---|---|---|
| 实现 | `pendingConnectionCreate` state + `<ConnectionCreateMenu>` 浮层 + `createConnectedNode` 动作 | 无 |
| 触发条件 | 拖到空白处且不是误触临近节点 | 无 |
| 创建效果 | 立即在落点生成新节点并自动连线 | 无 |

### 6. 视觉与主题

| 维度 | infinite-canvas-0.3.0 | agnes-platform |
|---|---|---|
| 主题系统 | 浅色/深色双主题（`canvasThemes` + `useThemeStore`），所有节点/连线颜色全部走 token | 单一深色硬编码 |
| 选中态 | stroke 变粗 + 发光 + 上下游联动高亮（`relatedHighlight`） | 仅记录 ID |
| 暗色适配 | 全 token 化，浅深一致 | CanvasView 用了 `linear-gradient(135deg, #0b0f1a ...)` 写死 |

## 四、连接线之外的差距

| 模块 | infinite-canvas-0.3.0 | agnes-platform |
|---|---|---|
| 节点类型 | 图片 / 文本 / 配置 / 视频 / 音频，共 5 类 | 未实现 |
| 拖拽框选 | `Ctrl/Cmd + 拖动` + `Shift` 追加选中 | 无 |
| 多选操作 | 复制粘贴、批量删除、批量移动 | 无 |
| 撤销/重做 | 节点/连线/视口/背景/助手会话全支持 | store 已有 `past/future` 但 CanvasView 缺组件 |
| 持久化 | `localforage`（异步、大对象友好） | `localStorage`（同步、5MB 上限、存大图易爆） |
| 助手面板 | 内嵌右侧 chat，支持引用当前节点 | store 已有 chat 数据，无 UI 集成 |
| 提示词库 | 完整前后端，可拖入画布 | 无 |
| 素材库 | 我的素材 + 服务器素材库 | 无 |
| 节点下方对话面板 ✅ | 文本节点下方 500px 宽生成面板 | 无 |
| 节点悬浮工具栏 ✅ | 选中时浮出"编辑/生图/裁剪/拆分/角度"等动作 | 无 |
| 缩放滑杆 | 独立 `<CanvasZoomControls>` + 滑杆 | store 已实现 `zoom()` |
| 小地图 | 完整 `<Minimap>` | CanvasView 引用了缺失的 `<CanvasMinimap>` |
| 背景模式 | 点阵 / 网格线 / 空白 | store 中无对应字段 |
| 帧动画批生成 ✅ | 批量生图叠卡预览、展开/折叠 | 无 |
| 图片操作 ✅ | 裁剪 / 拆分 / 局部重绘 / 角度变换 / 放大 / 反推提示词 | 无 |
| 视频操作 | 节点内原生播放器，参考视频/音频上下文 | 仅 `VideoView` 独立页面 |
| 导入导出 | JSON 导入导出单个项目 | 已有 exportJSON / importJSON |

## 五、用户视角的体验差距

把上述差异落到用户能感知的"丝滑感"上，可以拆成 5 个具体维度：

1. **从节点拉线的手感**：对方每个节点都自带左右两个发光圆点，hover 浮现，光标变成十字；我方连圆点都没有。
2. **连线的视觉**：对方用贝塞尔曲线且曲率自动适配距离，水平流动整齐；我方若简单画线会是折线。
3. **拖动中反馈**：对方实时跟随一根虚线，靠近目标节点会有明显描边变化；我方完全没有。
4. **松手即建**：对方拖到空白会弹"创建新节点"菜单，是画布扩展工作流的关键路径；我方直接丢失。
5. **选中与上下文**：对方选中节点自动高亮上下游，相关连线发光；我方只切换 ID。

这 5 条就是我方画布要复刻"丝滑感"时必须先解决的体验。

## 六、关键差异汇总（按优先级）

| 优先级 | 差距 | 用户感知 |
|---|---|---|
| P0 ✅ | 画布 UI 整体缺失（6 个核心组件不存在） | 打开 `/canvas` 空白 |
| P0 ✅ | 连线无任何渲染 | 无法看到上下游关系 |
| P1 ✅ | 节点锚点缺失 | 无法触发连线 |
| P1 ✅ | 拖动中无预览线 | 不知道连到了哪里 |
| P1 ✅ | 命中判定粗糙（已用多级命中，但还可优化） | 连线时频繁失误 |
| P2 ✅ | 选中态无视觉反馈 | 分不清当前操作对象 |
| P2 ✅ | 主题 token 不统一 | 深色不一致，浅色不可用 |
| P2 | 持久化用 localStorage | 后续接图片/大对象会爆 |
| P3 | 拖到空白建节点菜单 | 扩展工作流的高频动作 |
| P3 | 框选/多选 | 批量操作基础 |
| P3 | 缩放滑杆、小地图背景模式 | 画布导航基础 |
