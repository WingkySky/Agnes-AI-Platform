# 剧本节点「人物/场景信息带入」开发计划

> 分镜资产一体化派生：让剧本→分镜→人物/场景链路全程携带信息

## 1. 背景与问题

P0 主链路（commit 4ce3db1）已实现 script 节点→批量分镜→批量视频，但"分镜→人物/场景"方向完全没有信息带入：

1. **资产卡是空表单**：向导第二步的 `addAsset()`（`ScriptWizardDialog.vue:314`）只 push `{name:'', description:'', imageUrl:''}`，剧本和分镜里已有的角色/场景信息不会预填，全靠手填。
2. **资产参考图与剧情脱节**：`generateAssetImage`（`ScriptWizardDialog.vue:337-339`）的 prompt 只有"名称 + 描述 + 风格"三行，没有剧情概述、没有该资产关联镜头的上下文。
3. **资产对分镜无反向约束**：先建资产卡再生成分镜时，`CanvasNodeComposer.vue:337-342` 只收集上游连线节点，`content.assets` 不回传给 `/api/storyboard`，分镜不会使用已有角色/场景设定。
4. **分镜与资产的关联靠模糊文本**：`deriveImagesInternal`（`canvas-storyboard.ts:285-297`）把全部角色/场景设定无差别注入每条分镜 prompt，全部资产参考图全量并入，A 镜头会带上无关角色的设定与参考图。

## 2. 调研依据

市面漫剧工作流对此问题的成熟解法高度一致（2026-08-29 调研）：

| 来源 | 核心做法 | 本计划的落点 |
| --- | --- | --- |
| GUGU STYLE《AI漫剧剧本生成教程》 | 分镜 JSON 生成时即强制携带 `characters[]` 与 `location` 字段，镜头与资产的关联是结构化的，下游无需再做文本提取 | §4.2 分镜与资产一次 LLM 调用一体化输出 |
| 知漫剧「角色库」 | 角色卡（外貌/服饰/标志性特征）前置 → 剧本导入自动比对段落识别归属 → 人工勾选确认 → 以特征包+立绘为参照生成 | §4.3 自动预填 + 向导人工确认，§4.4 参考图带上下文 |
| 七牛云《AI漫剧工业化制作》 | LLM 拆剧本时强制附加角色特征标签；一致性靠"固定特征 + 参考底图" | §4.5 分镜 prompt 只注入命中资产的设定与参考图 |
| baoyu-comic skill | 角色定义先行 → 角色参考表图 → 每页 prompt 强制引用；引用有降级策略 | §4.4/§4.5 prompt 组装分层与回退 |

共性原则：**资产先于分镜确认（asset-first）、关联在生成分镜那一刻结构化绑定、生成时按关联精确注入、自动预填后保留人工确认**。

## 3. 目标与非目标

**目标**

1. 生成分镜的同时自动产出全剧角色/场景清单，向导第二步自动预填资产卡（保留人工增删改）。
2. 每个分镜记录出场角色与场景，与资产卡结构化关联，可在向导中编辑。
3. 资产参考图 prompt 注入剧情概述 + 关联镜头描述。
4. 已有资产卡回传分镜生成（反向通道），分镜角色沿用已有设定。
5. 分镜图派生按镜头命中注入设定与参考图，无标注时保持现状（全量注入）。

**非目标**

- 不做道具（props）资产卡区块（当前 UI 只有角色/场景两区）。
- 不做 P2 宫格工具包 / LoRA 训练类一致性方案。
- 不动项目制流程（`project/` 下的 wizard 与 character_service 仅作参照）。
- 不做独立的"重新提取资产"按钮（重发剧情概述即可触发，预填按名去重不覆盖已有卡）。

## 4. 方案设计

### 4.1 总体思路

```
剧情概述 + 上游节点 + 已有资产卡
        │
        ▼  POST /api/storyboard（一次 LLM 调用）
{ assets: { characters[], scenes[] },      ← 全剧资产清单 → 预填资产卡
  shots: [{ ..., location, characters[] }] ← 每镜头场景名 + 出场角色名
}
        │
        ├─► 向导② 资产卡预填（按名去重追加，不覆盖手填卡）→ 参考图生成（带剧情+关联镜头上下文）
        └─► 派生分镜图：按 shot.characters/location 命中注入设定文本 + 参考图
```

### 4.2 后端：`/api/storyboard` 一体化输出分镜 + 资产

**`backend/app/schemas/storyboard.py`**

- `StoryboardShot` 增加 `characters: List[str]`（出场角色名）、`location: str`（场景名）。
- `StoryboardRequest` 增加 `scenes: List[StoryboardCharacter]`（已有场景卡回传，反向通道）。
- 新增 `StoryboardAsset(name, description)` 与结果模型 `StoryboardResult(shots, assets: {characters: List[StoryboardAsset], scenes: List[StoryboardAsset]})`。

**`backend/app/services/storyboard_service.py`**

`_PROMPT_TEMPLATE` 改为输出 JSON 对象（任务从"生成分镜"扩展为"提取资产 + 生成分镜"两件事）：

```
你是专业短剧分镜师。请根据剧情概述和角色/场景设定，完成两件事：
1. 提取全剧资产清单；2. 生成结构化分镜脚本。

## 要求
- 镜头数量：{shot_min} 到 {shot_max} 个
- 资产清单：从剧情中提取角色与场景。角色 description 写外貌/服饰/气质等可直接用于生成
  角色设定图的内容；场景 description 写环境/时间/氛围。若下方已给定角色/场景设定，
  必须沿用其 name 与描述，不得改写
- 每个镜头包含：no（序号）、shot_size（景别：远景/全景/中景/近景/特写）、camera（机位/运镜）、
  location（场景名，必须取自场景清单）、characters（出场角色名数组，必须取自角色清单）、
  description（画面描述）、dialogue（台词，没有则为空字符串）
- description 必须是可直接用于 AI 生图的具体画面描述，包含场景、人物动作、表情、光线；
  人物以角色名指代，与 characters 字段一致
- 台词短句化，符合短剧节奏
- 严格输出 JSON 对象，不要输出任何其他内容
{style_line}
## 剧情概述
{story}

## 已有角色设定
{characters}

## 已有场景设定
{scenes}

## 输出格式
{"assets": {"characters": [{"name": "...", "description": "..."}],
            "scenes": [{"name": "...", "description": "..."}]},
 "shots": [{"no": 1, "shot_size": "中景", "camera": "缓推", "location": "...",
            "characters": ["..."], "description": "...", "dialogue": "..."}]}
```

- `_build_prompt` 增加 scenes 段（沿用 characters 的拼装方式）。
- 解析改为对象格式：沿用现有栅栏容错 + `_MAX_ATTEMPTS=2` 重试；LLM 仍输出数组时降级为 `{shots: 数组, assets: 空}`，不整单失败。
- `generate_storyboard` 返回 `StoryboardResult`。

**`backend/app/routes/storyboard.py`**

- `data` 改为 `{"shots": [...], "assets": {...}}`，同步更新 `StoryboardResponse.data` 的描述注释。

### 4.3 前端：类型扩展、资产预填与反向通道

**`frontend/src/api/storyboard.ts`**：`StoryboardShot` 增加 `characters: string[]`、`location: string`；新增资产类型；响应 `data` 类型补 `assets`。

**`frontend/src/lib/canvas-storyboard.ts`**

- `CanvasShot` 增加 `characters: string[]`、`location: string`（注释说明：与资产卡按 name 关联）。
- `readShots` 类型守卫补默认值：`characters` 非字符串数组时给 `[]`，`location` 给 `''` —— 旧节点无新字段也能读。
- 新增导出 `mergeExtractedAssets(current: ScriptAssets, extracted?): ScriptAssets | null`：把 LLM 提取的资产按 name（trim 后）去重追加到已有卡，全部重复时返回 `null`（调用方跳过写入）。
- 新增导出 `buildShotContexts(shot, assets, extraCharacters: string[])`：按镜头命中过滤资产设定文本——
  - `shot.characters` 非空 → 角色设定只取名字命中的卡；`shot.location` 非空 → 场景设定只取同名卡；某一维未标注 → 该维取全量；
  - 过滤结果为空但全量非空 → 回退全量（角色名对不上时不丢信息）；
  - `extraCharacters`（上游文本节点设定）始终全量并入 characters。

**`frontend/src/components/canvas/CanvasNodeComposer.vue`（`sendScript`）**

1. 请求参数：`characters` 在上游节点之外并入 `content.assets.characters` 中已有非空卡，`scenes` 传入已有场景卡（反向通道）。
2. 响应映射：shots 增加 `characters: s.characters || []`、`location: s.location || ''`。
3. 写回：`updateContent({ shots })` 后调 `mergeExtractedAssets(readAssets(panel), resp.data?.assets)`，有新增才 `updateContent({ assets })`，再唤起向导。

**`frontend/src/components/canvas/nodes/ScriptWizardDialog.vue`**

- 步骤①表格增加两列：`场景`（文本输入）与 `出场角色`（文本输入，逗号分隔，`v-model` 经 computed 或 input 事件 split/join 成数组），随 `persistShots` 持久化。
- `addShot()` 默认值补 `characters: [], location: ''`。
- 步骤②资产卡描述下方加一行 muted 小字"出现镜头：#1、#3"（新增 helper `shotNosForAsset(shots, kind, name)` 反查，无关联则不显示）——对应知漫剧"自动识别 + 人工确认"。

**i18n（`frontend/src/i18n/zh-CN.ts` / `en-US.ts`，约 :1922 的 canvas.script.wizard 命名空间）**

新增：`colCharacters`（出场角色）、`colScene`（场景）、`charactersPlaceholder`（多个角色用逗号分隔）、`scenePlaceholder`、`assocShots`（出现镜头）。

### 4.4 资产参考图：纯设定图 prompt

`canvas-storyboard.ts` 导出 `buildAssetImagePrompt(panel, asset, kind, label)`（替换 `ScriptWizardDialog.vue` 的内联三行拼装）：

```
{角色设定图|场景设定图}：{name}
{description}
{纯粹性约束：角色=同一角色三视图设定图（正面/侧面/背面全身立绘并排，发型服装一致）；场景=空场景环境全景/无人物}
画面风格：{style}
```

**不注入剧情**（相关镜头描述、剧情概述一律不进参考图 prompt）。实测教训：把镜头描述注入参考图 prompt 会导致提示词污染——角色图混入其他角色与战斗背景、场景图混入人物。参考图必须是纯设定图（角色三视图 / 场景空镜），三视图能在后续 image2image 分镜派生中同时锚定正/侧/背面（对齐知漫剧"标准立绘"、七牛云"三视图参照底图"的行业做法，也是 P2 宫格工具包的前置形态）；剧情上下文只通过 §4.5 的分镜图 prompt 注入。资产与镜头的关联（`shotNosForAsset`）仅用于向导"出现镜头"提示，不进生图 prompt。

### 4.5 分镜图派生：按镜头命中注入设定与参考图

**`canvas-storyboard.ts` `deriveImagesInternal`**（`canvas-storyboard.ts:279`）由"批级统一"改为"逐镜头"：

- 每镜头 `contexts = buildShotContexts(shot, assets, upstreamTexts)` → `buildShotImagePrompt`（签名不变）。
- 每镜头 `referenceImages = 上游图片节点 + 命中角色卡 imageUrl + 命中场景卡 imageUrl`（命中规则与 4.4 一致，未命中不并入）。
- `mode` 逐镜头判定（有参考图 → `image2image`）；积分预估 `confirmBatchCost` 的 mode 按"任一 pending 镜头有参考图即 image2image"估算（可能轻微高估，可接受）。
- config 节点创建、连线、StepGroup、并发池、lineage 均不变。

**`ScriptWizardDialog.vue` 步骤③预览**：`shotPrompts` 从"全量 contexts"改为逐镜头 `buildShotContexts`，预览与实际派生一致。

### 4.6 数据结构变更汇总

| 位置 | 变更 |
| --- | --- |
| `/api/storyboard` 请求 | `+ scenes: [{name, description}]` |
| `/api/storyboard` 响应 | `data` 由 `{shots}` 变 `{shots, assets}`；shot `+ characters[]、location` |
| script 节点 `content.shots[]` | `+ characters: string[]、location: string`（localforage，无迁移需求，守卫给默认值） |
| script 节点 `content.assets` | 结构不变，仅内容由预填产生 |

## 5. 里程碑

### M1 后端一体化输出
1. `schemas/storyboard.py`：Shot/Request 扩展 + StoryboardAsset/StoryboardResult。
2. `services/storyboard_service.py`：新 prompt 模板 + 对象解析（含数组降级）+ scenes 段。
3. `routes/storyboard.py`：响应 data 补 assets。
4. `API.md` 同步 `/api/storyboard` 段落。

### M2 前端链路打通（预填 + 编辑 + 反向通道）
1. `api/storyboard.ts` 类型扩展。
2. `canvas-storyboard.ts`：`CanvasShot`/`readShots` 扩展、`mergeExtractedAssets`、`buildShotContexts`、`shotNosForAsset`。
3. `CanvasNodeComposer.vue` `sendScript`：资产回传 + shots 映射 + 预填写回。
4. `ScriptWizardDialog.vue`：步骤①两列 + `addShot` 默认值 + 步骤②关联镜头小字。
5. i18n 中英文案。

### M3 生成质量（上下文注入）
1. `buildAssetImagePrompt` + `generateAssetImage` 接入。
2. `deriveImagesInternal` 逐镜头 contexts/参考图/mode + 步骤③预览对齐。
3. `CHANGELOG.md` Unreleased 补记录。

## 6. 改动文件清单

| 文件 | 改动 |
| --- | --- |
| `backend/app/schemas/storyboard.py` | Shot/Request 扩展、新增资产与结果模型 |
| `backend/app/services/storyboard_service.py` | prompt 模板重写、对象解析、scenes 段 |
| `backend/app/routes/storyboard.py` | 响应 data 补 assets |
| `docs/API.md` | `/api/storyboard` 文档更新 |
| `frontend/src/api/storyboard.ts` | 请求/响应类型扩展 |
| `frontend/src/lib/canvas-storyboard.ts` | 类型/守卫、mergeExtractedAssets、buildShotContexts、shotNosForAsset、buildAssetImagePrompt、逐镜头派生 |
| `frontend/src/components/canvas/CanvasNodeComposer.vue` | sendScript 资产回传与预填 |
| `frontend/src/components/canvas/nodes/ScriptWizardDialog.vue` | 步骤①两列、关联镜头小字、资产图 prompt、预览对齐 |
| `frontend/src/i18n/zh-CN.ts` / `en-US.ts` | 新增文案 key |
| `CHANGELOG.md` | Unreleased 记录 |

## 7. 验证方式

项目无测试基建，按惯例：`vue-tsc` 类型检查 + 后端 `python -m py_compile` 语法检查 + 手动冒烟：

1. 新 script 节点输入剧情生成分镜 → shots 带出场角色/场景；向导①可编辑两列；向导②自动出现预填的角色/场景卡（含描述），卡片显示"出现镜头"。
2. 预填后手动改某卡描述/删卡，重发剧情重新生成分镜 → 已有同名卡不被覆盖，仅追加新角色。
3. 先手填角色/场景卡再生成分镜 → 分镜描述沿用已有设定（反向通道生效）。
4. 资产卡"生成图像" → prompt 含相关剧情与剧情概述（可在派生前通过步骤③或临时日志确认）。
5. 批量派生分镜图 → 步骤③预览中每条 prompt 只含命中镜头的设定；命中角色的参考图带入（config 节点 referenceImages）；无标注的旧节点行为与现状一致（全量注入）。
6. 中文界面切换英文 → 新增文案无硬编码。

## 8. 风险与对策

| 风险 | 对策 |
| --- | --- |
| LLM 输出对象格式不稳定 | 保留 2 次重试；解析出数组时降级为仅 shots、assets 为空，不整单失败 |
| 分镜中角色名与资产清单不一致 | prompt 强约束"characters/location 必须取自清单、人物以角色名指代"；前端命中为空时回退全量注入 |
| 旧画布节点无新字段 | `readShots` 守卫默认 `[]`/`''`，派生按"未标注"回退全量，行为与现状一致 |
| 同批镜头混合 mode（部分有参考图） | mode 逐镜头判定；积分预估按任一命中即 image2image，可能轻微高估 |
| 剧情概述过长撑爆资产图 prompt | 拼入前截断 200 字，关联镜头描述最多 3 条 |
