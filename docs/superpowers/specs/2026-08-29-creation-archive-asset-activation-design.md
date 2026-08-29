# 创作内容归档与资产激活设计

> 历史瘦身：画布/项目创作内容自动归档进资产库，历史只留独立生成；资产可分享上广场

## 1. 背景与问题

当前所有生成（图片/视频）统一写入后端 `generations` 表，4 条链路全部汇入（独立生图/生视频页、画布生成、项目制生成），表上无来源字段，无法区分。后果：

1. **历史被创作素材淹没**：剧本创作批量派生的分镜图/视频、资产参考图全部涌进历史页，历史混乱（用户核心痛点）。
2. **资产库未激活**：后端 `assets` 表、`save-from-generation` 接口、`/assets` 页面均已存在，但前端无"从生成存资产"入口，"用于生成"按钮是"功能开发中"占位，`use_count` 无调用方。
3. **广场只收 generations**：`/plaza` + 点赞 + 审核 + 历史页分享开关已完整，但资产和项目成片（`projects.final_video_url`）没有广场入口。

## 2. 目标与非目标

**目标**

1. 画布与项目里的全部生成自动归档进资产库（按创作容器分组），历史默认只显示独立生成。
2. 历史保留可追溯性：记录仍写入 generations 并打来源标记，历史页提供来源筛选。
3. 激活资产库：容器归组视图、分享开关、从历史手动存资产、"用于生成"链路。
4. 广场新增"创作"Tab 收录公开资产与成片，复用现有审核管道。

**非目标**

- 不改项目制内部数据结构（project_* 各表不动）。
- 不做资产版本链自动化（parent_id 机制保留给手动资产）。
- 不做站外分享链接/单作品公开 URL（沿用广场页内浏览）。
- 不迁移旧 generations 数据（项目未上线，改版前记录一律按 independent 处理）。
- 画布本地素材库（canvasAsset store，localforage）维持现状，不与后端资产库合并。

## 3. 决策记录（用户逐条确认）

| # | 决策点 | 结论 |
| --- | --- | --- |
| 1 | 创作内容去向机制 | B：自动归档 + 可追溯（写入打标 + 历史默认过滤 + 来源筛选） |
| 2 | 归档范围 | B：画布 + 项目全部生成；仅生图页/生视频页/聊天的独立生成进历史 |
| 3 | 资产页组织 | A：按创作容器归组（项目 / 画布剧本 / 画布散件），内部按类型分栏 |
| 4 | 广场呈现 | B：分两个 Tab（作品 = 现状 generations / 创作 = 资产 + 成片） |
| 5 | 存储架构 | 方案二：双写（generations 打标 + assets 自动归档记录），否决"纯 generations 视图化"与"本地归档" |
| 6 | "用于生成"链路（M5） | 本期做 |

## 4. 架构：创作上下文透传与双写归档

### 4.1 数据流

归档的前提是 poller 落库时知道生成来历；容器名/资产名等元数据只有调用方（前端/项目服务）完整（画布节点在 localforage，后端不可查）。设计透传链：

```
调用方携带 context = { source, container_type, container_id,
                      container_name, asset_type, asset_name }
  → POST /api/images/tasks、POST /api/videos（schema 加可选 context，随任务内存态）
  → poller 置 success 落库时：
      ├─ generations 写 source / container_type / container_id（历史过滤 + 追溯）
      └─ 有 container → archive_to_asset() 自动建 assets 归档记录
```

各调用方 context 取值：

| 生成场景 | source | container | asset_type | asset_name |
| --- | --- | --- | --- | --- |
| 生图页 / 生视频页 / 聊天 | independent | 不传 | — | — |
| 画布普通图 / 视频节点 | canvas | ('canvas', 'canvas') | material / clip | 节点名 |
| 剧本分镜图 / 分镜视频 | canvas | ('canvas_script', scriptPanelId) | material / clip | `#序号` |
| 剧本角色 / 场景参考图 | canvas | ('canvas_script', scriptPanelId) | character / scene | 资产卡名 |
| 项目制图 / 视频 / 成片 | project | ('project', project_id) | 按产物类型 | 产物名 |

- 前端入口集中在 `createGenerationTask`（canvas-generation.ts）与 `executeMergeGeneration`/`executeMergeVideoGeneration`：执行器从 config 节点 content（lineage、prompt、节点类型）推导 context；`ScriptWizardDialog.generateAssetImage` 直接调 `createGenerationTask` 的路径单独补。
- 项目制不走前端：后端 `submit_image_task/submit_video_task`（services/project/_async_gen.py）调 poller 前注入 project 上下文，产物类型由各调用处（角色参考/场景/分镜帧/镜头视频/成片）传入。
- `container_name` 为**快照冗余**：剧本/项目改名或删除后，归档记录仍正常显示分组名，不做联动。

### 4.2 数据结构变更

**generations 表（3 列）**：`source`（independent/canvas/project，默认 independent）、`container_type`、`container_id`。

**assets 表（6 列）**：`container_type`（project/canvas_script/canvas，null = 传统手动资产）、`container_id`、`container_name`（快照）、`source_generation_id`（FK generations.id，归档去重）、`kind`（image/video）、`asset_url`（单媒体 URL；现有 `reference_images` 保留给传统多图角色卡）。

**assets.type 扩展**：现有 character/prop/scene/brand 之外新增 `material`（素材图，含分镜图）、`clip`（视频片段）、`final`（成片）。

**projects 表不改**：成片在合成完成、`final_video_url` 落库处归档为 `type=final` 的 asset 记录（container=所属项目），分享开关落在 asset 上——广场"创作"Tab 单一数据源即 assets。新表仅 `asset_likes`（见 §7）。

索引：assets 增加 (user_id, container_type, container_id) 组合查询索引。

## 5. 归档规则

1. **时机**：poller 状态置 success 时归档；失败/取消不归档。成片在项目合成服务写入 `final_video_url` 的函数处调同一归档函数。
2. **容错**：归档整体 try/except，失败仅记日志，绝不阻塞生成主流程（历史有记录，可从历史手动补存）。
3. **去重**：按 `source_generation_id` 查重，已归档跳过（poller 重试安全）。
4. **角色聚合**：同容器同名 type=character 的多条记录，资产页前端聚合展示最新一张、可展开历史；不做版本链。
5. **URL 稳定性**：poller 已有对象存储转存（asset_storage.py），归档直接存 generations.result_url（已是转存后稳定 URL）。
6. **漏传兜底**：未带 context 的调用一律 independent 进历史。M1 将"画布/项目全部生成调用点补 context"列为显式核查项。

## 6. 历史页

- `GET /api/history` 加 `source` 参数，默认 `independent`，可选 all/canvas/project。
- 筛选条加来源 chips：**独立生成（默认）/ 画布创作 / 项目创作 / 全部**。
- 每条记录加"存为资产"按钮：激活现有无调用方的 `POST /pipeline/assets/save-from-generation` 与 store action；手动存的资产 container 为空，归"我的资产"，兼作归档失败的补存兜底。

## 7. 资产页（AssetsView 重构）

一级两区：

1. **创作单元**：container 非空的记录按 (container_type, container_id) 分组为单元卡片（名称快照、类型徽标 项目/剧本/画布、资产数、封面），点进单元详情。
2. **我的资产**：container 为空的传统资产，保持现状。

单元详情：按容器内实际存在的类型分 Tab（角色/场景/分镜图/视频片段/成片/道具）→ 资产卡网格。卡片操作：

- **预览**：图/视频播放。
- **分享到广场**：开关 `is_public`，新端点 `PATCH /api/assets/{id}/share`，复用现有审核管道（敏感词 + AI 预审，作用于 name/description；实施时将 history.py 的预审逻辑下沉 moderation_service 共用），未过审不公开。
- **删除**：仅删归档影子记录，明确提示不影响画布/项目本体。
- **用于生成**（M5）：image kind → 跳转生图页预填 image2image 参考图；video kind → 跳转视频页预填 video2video 参考视频。传值经 stores/asset.ts 的 pendingUse 状态，目标页 onMounted 读取并清除；触发 `increment_use_count`（现有函数，首次接上调用方），替换"功能开发中"占位与 i18n 文案。

路由：`/assets?container=<type>:<id>` query 参数区分顶层与详情，不新增子路由。

## 8. 广场

- 新端点 `GET /plaza/creations`：`assets` where `is_public AND asset_url 非空 AND moderation_status='approved'`，类型筛选 + 最新（public_shared_at）/最热（likes_count）排序 + 分页。
- 新表 `asset_likes`（user_id + asset_id 唯一约束），点赞/取消/批量状态端点与现有 generations 点赞平行；计数写 assets.likes_count。
- 前端 PlazaView 顶部 `el-tabs`：**作品（现状不动）/ 创作**。创作 Tab 卡片带类型标签（角色/场景/分镜图/视频/成片），视频卡封面沿用广场现有视频卡做法；详情弹窗 + 点赞与作品 Tab 交互一致。

## 9. 分期里程碑

| 里程碑 | 内容 |
| --- | --- |
| M1 后端归档链路 | generations 3 列 + assets 6 列 + 索引；images/videos 任务 schema 加 context；画布执行器与全部画布调用点补 context；项目 submit 注入上下文；poller 归档钩子 + archive_to_asset；成片合成处归档 |
| M2 历史页 | source 过滤 + 来源筛选条 + 存为资产按钮（激活 save-from-generation） |
| M3 资产页 | 容器归组重构（创作单元/我的资产/单元详情）+ 分享开关 + 审核 |
| M4 广场 | creations 端点 + asset_likes 表与端点 + 创作 Tab |
| M5 用于生成 | pendingUse 传值 + 生图/视频页预填 + use_count 递增 + 占位文案替换 |

每个里程碑独立可交付；M1 是其余全部的前置。API.md、CHANGELOG.md 随各里程碑同步。

## 10. 验证方式

项目无测试基建，按惯例：`vue-tsc` 类型检查 + 后端 `python -m py_compile` + 手动冒烟（实施计划中细化），关键冒烟项：

1. 生图页生成 → 进历史；画布剧本批量派生 30 镜头 → 历史默认不出现，切"画布创作"筛选可见且扣费记录完整。
2. 剧本分镜图/参考图生成 → 资产页出现"剧本《XX》"单元，分镜图/角色分栏内容正确、名称快照正确。
3. 项目生成 → "项目《XX》"单元归档；合成成片 → final 类型记录出现。
4. 资产分享 → 广场创作 Tab 可见；取消分享即下架；未过审不公开。
5. 资产"用于生成" → 生图页参考图预填、use_count 递增。
6. 归档失败注入（模拟）→ 生成主流程不受影响，历史可手动补存。

## 11. 风险与对策

| 风险 | 对策 |
| --- | --- |
| 画布/项目调用点漏传 context → 误标 independent 涌回历史 | M1 显式核查清单 + 冒烟覆盖每个调用点 |
| 归档拖慢生成主流程 | 归档为落库后异步旁路，try/except 隔离，失败仅日志 |
| 创作素材量大（30 镜头/剧本）→ assets 表膨胀 | 影子记录行小；分组查询走组合索引；无版本链复制 |
| 老记录无 source 全按 independent，创作记录短暂混入历史 | 项目未上线可接受（非目标已声明不迁移） |
| 分享审核绕过 | 分享端点强制走审核管道，与历史分享同一套实现 |
