# 画布节点架构演进整体规划

> 对照 LibTV 的节点形态，规划从"配置节点中间层"到"直出节点 + 覆盖式布局"的演进路线

## 1. 现状与差距（对照 LibTV 实测截图）

| 维度 | 我们（P0 现状） | LibTV |
| --- | --- | --- |
| 脚本派生 | 每镜头派生 1 个 config 节点（提示词/参数）+ 1 个独立结果节点，共 2 个节点/镜头，画布拥挤 | 每镜头 1 个"提示词节点"，prompt 内嵌在节点内，**图就地生成显示在节点里** |
| 视频派生 | 视频在图片右侧新开一列节点 | 视频卡片**覆盖在源图片节点上**，空间占用减半 |
| 模型/参数 | 多数入口硬编码或取默认（配置下放计划 0f8e0d7 解决） | 每个节点对话框底栏可选 |

## 2. 演进路线（三期，Phase A 先行）

```
Phase A 生成配置下放（已有详细设计，先行）
   └─ 所有节点形态的底座：模型/参数在对话框底栏可控
Phase B1 分镜直出重构（消灭 config 中间层）
   └─ 脚本派生直接产出"可生图的图片节点"，一镜头一节点
Phase B2 产物覆盖式布局
   └─ 视频（及后续产物）以卡片覆盖在源图片节点上
Phase C 节点类型路线图（远期，对齐 LibTV 添加节点菜单）
```

## 3. Phase A：生成配置下放（设计已定稿 `2026-08-29-generation-config-downshift-design.md`）

M1 默认值链统一 → M2 Composer 底栏统一（ComposerParamBar 接入 image/video/config 节点）→ M3 剧本链路（分镜聊天模型、向导参数、批量派生参数）。**本期先行，不受 B 期影响**：无论节点形态怎么变，"每处生成都能选模型"都是前置；且 B1 的直出节点就是图片节点，A 期做给 image 节点的底栏直接复用。

## 4. Phase B1：分镜直出重构

**目标形态**：script 派生每镜头直接创建 1 个**可生图的图片节点**——prompt 内嵌节点（Composer 可编辑）、模型/参数在底栏（Phase A 能力）、生成结果就地回填节点自身，不再经过 config 中间层。**实测后视频派生也纳入直出**：批量/单镜头直接创建视频节点（参数/源分镜图/lineage 内嵌，视频地址回填节点自身），不再产生"摄像机控制"config 节点；视频节点按行内列位排在分镜网格右侧专属区（B2 再改覆盖式布局）。

**核心改动**：

1. **图片节点升级为"生成本体"**：content 扩展 `{ prompt, model, size, referenceImages, lineage, status, error }`；CanvasNode 的 image 分支按 status 渲染加载/失败态（现 config→result 两跳的状态展示收敛到节点内）。
2. **就地执行**：canvas-generation.ts 新增 `executeInNodeGeneration(panel, store)`——复用现有 createGenerationTask + pollImageTask + 积分扣费，回填目标从"新建结果节点"改为"更新节点自身"（不新建节点、不加 config 连线）；`executeMergeGeneration` 保留给 config 节点（手动搭建场景仍可用）。
3. **派生链路改写**：`deriveImagesInternal` 每镜头直接 addPanel(type='image', content 含 prompt/参数/lineage) → 就地执行；网格布局、StepGroup、并发池（IMAGE_CONCURRENCY）、批量积分确认全部保留。
4. **lineage 简化**：`ShotLineage` 直接挂图片节点 content，`getShotLineageInfo` 免去 result→config 反查一层；重拍/重跑（HoverToolbar 的 derive-video/reshoot）改读图片节点。
5. **视频派生输入**：`deriveStoryboardVideos` 的"找已成功分镜图"逻辑从"config 的结果节点"改为"lineage 图片节点自身 content"。
6. **兼容策略**：项目未上线，按惯例直接切换、不做旧数据迁移；存量画布里旧的 config 派生节点仍可手动使用（executeMergeGeneration 保留），新派生一律直出。

**验证**：派生 30 镜头 → 画布上只有 30 个图片节点（无 config）；单镜头改词重生成；单镜头重拍视频；批量重跑幂等；StepGroup 与积分确认正常。

## 5. Phase B2：产物覆盖式布局

**目标形态**：视频派生不再向右新开一列，视频节点以紧凑播放卡片**覆盖在源图片节点位置**（右下偏移约 24px + 置顶），像 LibTV；点击展开/全屏，拖开即还原为普通节点。

**核心改动**：

1. `deriveVideoForShot` / `deriveStoryboardVideos` 的布局函数：坐标 = 源图片节点 (x+24, y+24)，加入 panels 时置顶（z 序按数组顺序，append 即置顶）。
2. 图片节点被覆盖时的交互：Hover 工具栏仍可穿透操作源图片（覆盖卡片默认略小，如图片宽的 60%）；框选/多选拖拽时覆盖组整体移动（canvas 已有 StepGroup 思路可参考，此处用"派生对"软关联，不建硬组）。
3. 时间线/导出等下游引用逻辑不受影响（引用的是节点 id）。

**风险与对策**：覆盖导致源图暂不可见——覆盖卡片加"最小化为角标"按钮；缩放很小时重叠严重——zoom < 0.5 时自动还原为偏移布局。

## 6. Phase C：节点类型路线图（远期方向，不展开）

对齐 LibTV 添加节点菜单逐步补齐：音频节点（TTS/配音）、导演台、逐帧拉片、智能剪辑、素材库节点化、"从生成历史选择"导入。每期单独走设计 → 实施。

## 7. 里程碑与顺序

| 阶段 | 依赖 | 交付物 |
| --- | --- | --- |
| A 配置下放（M1→M3） | 无 | 详见 0f8e0d7 设计，3 个独立里程碑 |
| B1 分镜直出 | A（底栏参数能力复用） | 派生直出图片节点 + 就地执行 + lineage 简化 |
| B2 覆盖式布局 | B1 | 视频卡片覆盖源图 + 交互适配 |
| C 节点类型扩展 | 按 | 远期 backlog |

## 8. 决策记录（待用户确认）

| # | 决策点 | 建议 |
| --- | --- | --- |
| 1 | config 节点中间层 | B1 后派生链路不再产生；手动搭建场景保留 executeMergeGeneration 入口 |
| 2 | 存量 config 派生数据 | 不迁移，直接切换（项目未上线惯例） |
| 3 | 实施顺序 | A → B1 → B2，每期独立提交 |
