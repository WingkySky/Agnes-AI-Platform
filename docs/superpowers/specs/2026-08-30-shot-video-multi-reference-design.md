# 分镜视频多图参考 / 首尾帧 / 跨镜头衔接设计（画布分镜直出链路）

## 一、背景与问题

画布分镜直出链路（script 节点 → 批量分镜图 → 批量图生视频）中，每个镜头的视频生成只由 1 张分镜图控制：`deriveStoryboardVideos`（`frontend/src/lib/canvas-storyboard.ts`）硬编码 `referenceImages: [帧图URL]`。单张图既表达不了动作的结束目标，也带不上角色/场景一致性信息，视频抽卡率受限。

底层能力其实已经具备：

- 后端 `/api/videos`（`backend/app/routes/videos.py`）已支持 `keyframes`（首尾帧，最多 2 张）与 `image2video` 多图参考（`images[]`，Flash 上限 5 张）两种模式；
- 前端 `createVideoGenerationTask`（`frontend/src/lib/canvas-generation.ts`）已按 `use_keyframes` + 参考图数量自动推断模式。

真正的断点有两处：

1. **编排层没有多图的数据位置**：`CanvasShot` 是纯文本结构，分镜图节点的 lineage 没有"首帧/尾帧"角色概念，视频派生只认单张帧图。
2. **直出视频执行器够不着关键帧模式**：`executeInNodeVideoGeneration` 构建 `GenerationConfig` 时没有读节点 content 上的 `use_keyframes`，直出链路永远走 `image2video`（关键帧目前只有 config 节点路径 `executeMergeVideoGeneration` 可达）。

另有一个模型契约约束决定了整体形态：**Agnes Video 2.5 中 keyframe 与 reference 两种 mode 互斥**——keyframe 只有 `first_frame`/`last_frame` 两个槽位，不能附加参考图；reference 的 `images[]` 不区分首尾。因此每个镜头生成视频时在两种模式中二选一。

## 二、目标

1. 每个镜头可选生成"尾帧图"（该镜头动作的结束状态画面）；派生视频时若有尾帧，自动走 keyframes 模式（首帧 = 分镜图，尾帧 = 尾帧图）。
2. 无尾帧的镜头，派生视频时自动并入命中的角色/场景定妆照作为多图参考（reference 模式），提升人物/场景一致性。
3. 跨镜头衔接：镜头可标记"承接上一镜头"，其分镜图（首帧）以上一镜头的尾帧图为底图 image2image 续接生成，使上一镜的结束画面自然过渡为下一镜的开始画面；衔接只发生在生图阶段，视频阶段不感知。
4. 全部改动收在画布分镜直出链路（前端），遵循"数据存画布节点 content（localforage）、后端无状态"原则；后端零改动。

## 三、非目标

- 项目分镜链路（ShotsTab/ShotCard）接入多图 —— 后端 `/api/videos` 已支持两种模式，后续单独一轮接入。
- 视频级衔接（提取上一镜头"生成视频"的实际末帧作为下一镜首帧）—— 依赖视频串行生成，见"四、方案对比"中的取舍，v1 否决。
- 手动逐镜头挑选/上传视频参考图 —— 画布通用 config 节点手动搭建路径已覆盖该需求，直出链路先做自动化部分。

## 四、方案对比（决策记录）

**方案 A（选定基础）：节点角色标注，纯前端编排层改动。** 分镜图节点 lineage 增加 `role: 'first' | 'last'`，尾帧图是同镜头的第二个直出 image 节点；视频派生按"有尾帧 → keyframes，无尾帧 → 帧图 + 定妆照多图参考"自动选模式。改动集中在 `canvas-storyboard.ts`、向导/工具栏 UI、`executeInNodeVideoGeneration` 一处小修复。

**方案 B（否决）：`CanvasShot` 增加视频参考 URL 字段。** 把图片 URL 塞进纯文本分镜数据，与"图即节点"、lineage/重拍体系冲突，且 data URL 会撑爆 script 节点 content。

**方案 C（否决）：镜头视频配置同步后端编排。** 违背画布无状态原则，工作量大，无当前必要。

**衔接实现的取舍（确认范围时补充）：**

- **生图阶段衔接（选定）**：上一镜尾帧图作为底图，image2image 续接生成下一镜首帧。语义天然对齐（上一镜结束态 ≈ 下一镜开始态），批量编排只需"尾帧先于衔接首帧"的池内依赖，视频阶段零改动，重拍粒度仍是单节点。
- **视频级衔接（否决）**：提取上一镜头已生成视频的实际末帧作为下一镜视频首帧。衔接最"真"（动作连续），但视频批量变全串行（几十镜头 × 分钟级墙钟时间）、单点失败阻断整条链、重拍上游镜头导致下游全部失效，成本与脆弱性不可接受。若实测生图衔接效果不足，后续可作为增强单独设计。

## 五、数据结构变更（全部前端节点 content）

1. `ShotLineage`（`canvas-storyboard.ts`）增加 `role?: 'first' | 'last'`：
   - 仅 image lineage 使用；缺省视为 `'first'`，存量节点天然兼容；
   - `readLineage` 透传 role（非法值忽略）。
2. 视频直出节点 content 在有尾帧时写入 `use_keyframes: true`；无尾帧不写（与现状一致）。
3. `CanvasShot` 增加 `linkPrev?: boolean`（缺省 false）：该镜头承接上一镜头。衔接是导演意图（与景别/运镜同类），故放在分镜数据上；图片本体仍以节点存在，`CanvasShot` 不存任何图片 URL。第 1 个镜头的 linkPrev 无效。
4. script 节点 `shot_video_params` 增加 `refAssets?: boolean`（默认 true）：无尾帧镜头是否把命中定妆照并入视频参考图。

## 六、尾帧图生成

尾帧图既是本镜头 keyframes 模式的结束帧，也是跨镜头衔接的衔接点（下一镜头首帧的底图）。

**入口（三处，共用同一实现）：**

1. 向导第 3 步逐镜头行内"生成尾帧"按钮（该镜头首帧已派生时可用）；
2. 向导第 3 步头部"批量补尾帧"（只处理"首帧已成功且尚无尾帧"的镜头）；
3. 分镜图节点悬浮工具栏"生成尾帧图"（`CanvasView.vue`，紧挨现有"派生视频"动作，仅对 role=first 且尚无尾帧的分镜图节点显示）。

**实现：** `deriveImagesInternal(scriptPanel, pending, role: 'first' | 'last' = 'first')` 扩展一个 role 参数：

- 幂等：同镜头已有尾帧节点（含 pending/loading）则跳过，与首帧派生的幂等语义一致；
- prompt：`buildShotImagePrompt(...)` 结果追加一行尾帧要求（"此图为该镜头动作的结束瞬间：与首帧同场景、同人物、同机位，人物动作处于收尾状态"。提示词中文硬编码与 `buildAssetImagePrompt` 现状一致，UI 标签文案一律走 i18n）；
- `referenceImages` 收集逻辑与首帧完全一致（上游图片节点 + 按镜头命中的角色/场景资产图），保障人物/场景一致；
- 节点命名 `#{no} 尾帧`（后缀走 i18n，参照 `videoSuffix`），lineage 写 `role: 'last'`，进入与首帧相同的 StepGroup。

v1 不做"从本镜头首帧 image2image 派生尾帧"的链式生成（依赖首帧完成，编排复杂）；首尾帧并列独立生成，见"风险"。

## 七、跨镜头衔接（生图阶段）

**开关：** 分镜表编辑步骤（向导步骤 1）每镜头行新增"衔接上一镜"开关，写回 `CanvasShot.linkPrev`；第 1 个镜头开关禁用。

**语义：** 开启后，该镜头的首帧图不再从文本直接生成，而是以上一镜头尾帧图为首张参考图的 image2image 续接生成：

- `referenceImages = [上一镜头尾帧图, ...按镜头命中的资产图]`（尾帧排第一，最大化其对构图的影响）；
- prompt = `buildShotImagePrompt(...)` 结果末尾追加承接行："画面承接首张参考图的场景、人物与状态，为本镜头的开始瞬间"；
- 节点仍是 role=first 的普通分镜图节点，后续视频派生、重拍、定位等行为与其他首帧完全一致。

**批量编排（`deriveStoryboardImages`）：**

- 任务按镜头序号组织：无依赖任务（所有尾帧 + 未衔接首帧）直接进并发池；衔接首帧的任务在池内 await 上一镜头尾帧任务完成后再执行；
- 同批次自动补齐缺失的上一镜尾帧（衔接镜头的上一镜尚无尾帧时，先入队尾帧生成），补齐数量计入批量积分预估确认的总数；
- 上一镜头尾帧已存在且 success → 直接以其为底图，不重复生成；
- 上一镜头尾帧生成失败 → 该衔接首帧跳过并计入批量汇总提示，**不静默降级**为纯文本生成；
- 已有首帧的镜头仍按幂等规则跳过，衔接只影响本次新生成的首帧。

**单镜头入口（`deriveImageForShot` / 悬浮工具栏）：** 衔接镜头在上一镜尾帧未就绪时提示"请先生成上一镜头尾帧"，不静默降级。

**视频阶段不感知衔接：** 衔接只改变首帧图的来源；首帧图落地后，视频派生按下一节规则照常执行。

## 八、视频派生模式解析

`deriveStoryboardVideos` 与 `deriveVideoForShot` 统一按以下规则取图：

```
tail = 该镜头 role='last' 的直出 image 节点
if tail 存在且未 success   → 计入 notReady，跳过该镜头（不静默降级为单图）
else if tail 存在且 success → referenceImages = [首帧URL, 尾帧URL]；content.use_keyframes = true
else                        → referenceImages = [首帧URL]
                              if refAssets 开启：追加命中的角色/场景资产图（按 shotId 去重，整体 slice(0, 5)）
```

- "尾帧未成功即跳过"是刻意设计：用户显式要求了尾帧，静默降级单图会按错误预期烧积分。
- 5 张上限对应 Flash 参考图上限，帧图始终排第一；后端 `routes/videos.py` 校验仍是最终防线。
- 积分预估：keyframes 组与 image2video 组分别调用 `estimateCanvasCost` 后求和（批量内可能两种模式混合）。
- 所选模型不支持对应能力（如无 keyframes）时，由后端校验报错 → 节点 error 态显示原因；用户换模型后用现有"重拍/重试"就地重跑，前端不做模型能力白名单。

## 九、执行层修复（canvas-generation.ts）

`executeInNodeVideoGeneration`（直出视频节点执行器）补齐：

- 读取 `panel.content.use_keyframes`；为 true 时校验 `referenceImages.length <= 2`（超出抛错），并把 `use_keyframes` 传入 `GenerationConfig`，使 `createVideoGenerationTask` 路由到 keyframes 模式；
- 重拍/重试复用同一执行器且保留节点 content，行为自动一致，无需额外处理。

## 十、UI 变更

1. `ScriptWizardDialog.vue` 向导步骤 1（分镜表编辑）每镜头行新增"衔接上一镜"开关（第 1 镜头禁用，写回 `linkPrev`）。
2. `ScriptWizardDialog.vue` 第 3 步 `genRows` 改为 role 感知：
   - 主缩略图取 role=first 节点（现状逻辑需过滤掉尾帧节点，否则首帧槽位会被尾帧抢占）；
   - 每行新增尾帧缩略图槽（loading/error 样式与首帧一致）+ "生成尾帧 / 重拍尾帧"按钮 + 定位跳转；
   - 开启衔接的镜头显示衔接标记（提示该首帧由上一镜尾帧续接）；
   - 步骤头新增"批量补尾帧"按钮；
   - 视频参数栏新增"并入角色/场景参考图"开关（写入 `shot_video_params.refAssets`）。
3. `CanvasNodeHoverToolbar` / `CanvasView.vue`：分镜图节点（role=first 且尚无尾帧）悬浮工具栏增加"生成尾帧图"动作。
4. 新增 UI 文案全部走 i18n，zh/en 同步补充。

## 十一、错误处理

- 尾帧生成失败：节点 error 态 + 批量结束汇总 warning（沿用既有批量模式）。
- 衔接首帧因上一镜尾帧未就绪/失败而跳过：计入批量汇总提示；单镜头入口直接提示先补尾帧。不静默降级。
- 批量派生视频遇尾帧未就绪：计入 notReady 并 info 提示（沿用"分镜图未就绪"既有模式），不静默降级。
- 后端能力校验失败（模型不支持 keyframes / 参考图超限）：错误信息写入节点 error 态展示。

## 十二、测试与验收

项目无前端测试基建，验收 = `vue-tsc -b` 全量类型检查零错误 + 手动冒烟（沿用 specs 目录 smoke checklist 惯例）：

1. 三个入口生成尾帧均可用；向导行内尾帧缩略图/重拍/定位正确；
2. 有尾帧镜头派生视频：网络面板确认请求 `mode=keyframes`、首尾帧图正确、张数 = 2；
3. 无尾帧 + refAssets 开启：`images[]` = [帧图, ...命中资产图] 且 ≤ 5；关闭 refAssets 后仅帧图；
4. 尾帧 pending 时批量派生视频：该镜头被跳过且有 notReady 提示；
5. 存量分镜节点（lineage 无 role）回归：单图派生行为与改动前一致；
6. `refAssets` 开关与"衔接上一镜"开关状态在向导重开后保持；
7. 衔接镜头批量生成：先出尾帧后出首帧，衔接首帧请求的 `referenceImages[0]` = 上一镜尾帧图，prompt 含承接行；
8. 衔接镜头的上一镜尾帧缺失时批量自动补齐（积分确认数量包含补齐尾帧）；上一镜尾帧失败时衔接首帧跳过且有提示；单镜头入口给出"先生成上一镜头尾帧"提示；
9. 第 1 个镜头的衔接开关禁用。

## 十三、风险

- 定妆照（角色三视图并排图）作为视频参考图可能引入干扰 —— 与首帧生图使用同一类参考、同一风险面；若实测效果差，后续增加 per-shot 参考图开关。
- 首尾帧独立生成，构图一致性靠提示词 + 资产参考图保障，可能出现场景漂移 —— 后续可增强为"从本镜头首帧 image2image 派生尾帧"。
- 衔接还原度取决于生图模型对首张参考图的权重，若"承接上一镜"效果弱，后续增强为视频级末帧提取衔接（见方案对比）。
- 重拍上游尾帧后，下游衔接首帧不会自动级联重生成，需手动重拍（v1 如此，避免隐性批量烧积分）。

## 十四、关联文档

- [libtv-gap-analysis.md](../../libtv-gap-analysis.md) —— 差距补强计划（本设计对应"分镜→视频准确性"补强）
- [2026-08-29-script-node-asset-derivation-design.md](2026-08-29-script-node-asset-derivation-design.md) —— 分镜直出与资产按名注入（本设计的上游链路）
