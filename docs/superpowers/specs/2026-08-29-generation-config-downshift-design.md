# 生成配置下放重构设计

> 把模型/参数选择能力下放到每个生成入口的对话框底栏（对齐 LibTV Composer 形态），用户在任何模块内生成时都知道并掌控"用什么模型、什么参数"

## 1. 背景与问题

实测剧本创作时的核心抱怨：**生图/生视频模型都没得选，不知道资产是用什么模型生成的**。全量排查后，生成入口的模型/参数可控性如下：

| 生成入口 | 模型 | 参数 | 可控性 |
| --- | --- | --- | --- |
| Composer → config 节点（图/视频） | content.model | 全参数（原生 select） | ✅ 已可选 |
| image 节点 Composer 发送（图生图） | defaultImageModel 硬取 | 1024x1024 硬编码 | ❌ |
| video 节点 Composer 发送（首帧生视频） | defaultVideoModel 硬取 | 16:9、5s 硬编码 | ❌ |
| 文本节点"生成图片" | defaultImageModel | 偏好比例 | ❌ 模型不可选 |
| 剧本向导②资产参考图 | defaultImageModel | 1024x1024 硬编码 | ❌ |
| 剧本批量派生分镜图/视频 | defaultImage/VideoModel | 图：偏好比例；视频：16:9 硬编码 | ❌ |
| Composer → /api/storyboard（分镜 LLM） | 后端取注册表第一个 chat 模型 | — | ❌ 请求体无 model 字段 |
| 快捷生成弹窗（GenerationQuickPanel） | 弹窗内原生 select | 部分 | ⚠️ 可选但简陋 |
| 独立生图/生视频页 | ParamSelector | 全参数 | ✅ 标杆 |

关键发现：**配置能力不必"推倒"重来——config 节点的参数编辑早已在悬浮 Composer 底栏（模式 tabs + 模型/尺寸/视频参数），独立页面也已有完整的 `ParamSelector` 组件（模型带 Provider 分组、图尺寸 tier、视频比例/分辨率/时长/帧率联动）。所谓"下放"，本质是把这两个现成能力复制到其余 6 个失控入口，并统一默认值来源。**

## 2. 目标与非目标

**目标**

1. 每个生成入口都能选模型与关键参数，交互统一为 ParamSelector 底栏形态。
2. 默认值链统一：入口选择 > 用户偏好（preferences.generation.default_model_id，现有字段但全链路无人消费，本次接通）> 模型列表第一个。
3. 分镜 LLM 可选聊天模型（`/api/storyboard` 加可选 model 参数）。
4. 剧本链路（向导资产图、批量派生）生成前可选模型/参数，选择随 script 节点持久化，下次打开仍生效。

**非目标**

- **不拆除 config 节点**：它仍是分镜批量派生的产物与批量编排载体（每个镜头一个可独立重跑的节点，P0 既定架构）；"下放"指交互能力下沉到各入口，交互式生成不再需要手动搭 config 节点。
- 不动独立生图/生视频页（它们已是标杆形态）。
- `camera_params` 消费缺口（节点内持久化但无链路消费）单独立项，不纳入本期。
- GenerationQuickPanel 换 ParamSelector 仅作可选润色项，不在主干。

## 3. 方案设计

### 3.1 配置优先级链（统一默认值）

```
入口级选择（节点 content / 向导内选择，随画布持久化）
  ↓ 未选择时
preferences.generation.default_model_id（偏好页已有此字段，本次接通为全局默认）
  ↓ 仍未命中时
modelsStore 按类型/模式的第一个模型（现状兜底）
```

实现：modelsStore 新增 `getDefaultModel(type: 'image'|'video'|'chat')`——优先返回偏好 id（校验仍存在且类型匹配），否则列表第一个；`defaultImageModel/defaultVideoModel` 改为其封装（现有消费方零改动即获得偏好感知）。

### 3.2 ParamSelector 下放与字段适配

ParamSelector 的 v-model 是驼峰（`size/aspectRatio/seconds/frameRate/model`），画布 content 是蛇形（`aspect_ratio/frame_rate`）。在 canvas-generation.ts 旁新增一个轻量适配组件 `ComposerParamBar.vue`（`components/canvas/`）：

- props：`mode: 'image' | 'video'`，内部直接绑定 `panel.content` 的蛇形字段（经 store.updatePanel 写回），调用方一行接入：`<ComposerParamBar :panel="panel" mode="video" />`
- 内部复用 ParamSelector（经字段映射），不是重写选项逻辑
- 视频模式含：模型 / 分辨率 / 比例 / 帧率 / 时长；图片模式含：模型 / 尺寸
- 布局沿用现 Composer 底栏 flex-wrap，宽 300-520px 可容纳（现状 video 5 个 select 已能换行放下）

### 3.3 各入口改造清单

| 入口 | 改造 |
| --- | --- |
| image 节点 Composer | 底栏加 ComposerParamBar(mode=image)；选择存 image 节点 content（image_model/image_size），sendImage 透传给 executeImageReferenceGeneration（新增可选参数，替换硬编码） |
| video 节点 Composer | 同上（video_model/aspect_ratio/seconds…），sendVideo 透传给 executeVideoFromFrameGeneration |
| config 节点 Composer | 现有原生 select 整体替换为 ComposerParamBar（同一交互形态；content 字段名不变，executeMerge* 零改动） |
| script 节点 Composer | 底栏加分镜聊天模型选择（chat 模型列表，存 content.chat_model） |
| 剧本向导②资产参考图 | 向导②顶部加一行 ComposerParamBar(mode=image)，选择存 script 节点 content（wizard_image_model/image_size），generateAssetImage 消费 |
| 剧本批量派生（步骤③） | 步骤③批量按钮旁加参数区（mode=image/video 各自的模型+关键参数），写入派生 config 节点 content（派生后仍可逐镜头在 Composer 单改） |
| 文本节点"生成图片" | 沿用 M1 后的偏好默认模型，不加 UI（低频路径） |

### 3.4 后端：/api/storyboard 加可选 model

- `StoryboardRequest` 加 `model: Optional[str]`；`storyboard_service.generate_storyboard` 有 model 时校验其在 chat 注册表中，否则回退第一个 chat 模型（与 images/videos 的 model 可选回退模式一致）。
- Composer sendScript 透传 `content.chat_model`。

### 3.5 数据持久化位置

| 选择 | 存储位置 | 理由 |
| --- | --- | --- |
| image/video/config 节点的模型参数 | 各节点 content（现有模式） | 节点即配置，重试/重跑自然继承 |
| script 节点的 chat_model / 向导模型参数 | script 节点 content | 一个剧本一份配置，重开向导不丢 |
| 全局默认 | preferences.generation.default_model_id | 偏好页已有 UI，接通即生效 |

## 4. 里程碑

| 里程碑 | 内容 |
| --- | --- |
| M1 默认值链统一 | modelsStore.getDefaultModel 接通偏好 default_model_id；defaultImage/VideoModel 改封装 |
| M2 Composer 底栏统一 | ComposerParamBar 适配组件；image/video/config 三类节点 Composer 接入；script 加聊天模型选择 |
| M3 剧本链路 | 后端 /api/storyboard 加 model；向导②参数栏；步骤③批量参数区；sendScript/derive 链路透传 |
| 收尾 | CHANGELOG/API.md；冒烟（重点：每个入口选非默认模型生成，产物元数据中模型正确） |

每个里程碑独立可交付，M2 依赖 M1（默认值），M3 依赖 M1。

## 5. 验证方式

vue-tsc + py_compile + 手动冒烟：

1. 偏好页设默认生图模型 → 新 image 节点直接发送 → 产物模型 = 偏好值。
2. image/video 节点 Composer 底栏选模型与参数 → 发送 → 产物按选择生成；重选节点再打开 → 选择保留。
3. config 节点 Composer 换 ParamSelector 后：模式切换、参数修改、生成、重试全链路与改造前一致。
4. script 节点选 GVLM 类 chat 模型 → 生成分镜 → 后端日志/产物确认用了所选模型。
5. 向导②选非默认生图模型 + 尺寸 → 生成资产参考图按选择；重开向导选择保留。
6. 步骤③设置批量参数 → 批量派生 30 镜头全部按所选模型/参数；单镜头重拍继承所选。

## 6. 风险与对策

| 风险 | 对策 |
| --- | --- |
| ParamSelector 在 300px 窄 Composer 溢出 | 沿用 flex-wrap 换行；Popover 内部自带滚动（现有组件已处理） |
| 偏好 default_model_id 指向已删除/下架模型 | getDefaultModel 校验存在性，未命中回退列表第一个 |
| config 节点换组件引入回归 | content 字段名与读写路径不变，仅替换控件；冒烟项 3 覆盖全链路 |
| 批量派生参数与逐节点修改冲突 | 步骤③参数仅作为派生时写入 config 的初值，派生后以节点 content 为准（现有重跑语义不变） |
