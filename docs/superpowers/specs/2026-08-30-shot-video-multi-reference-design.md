# 分镜视频多图参考 / 首尾帧支持设计（画布分镜直出链路）

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
3. 全部改动收在画布分镜直出链路（前端），遵循"数据存画布节点 content（localforage）、后端无状态"原则；后端零改动。

## 三、非目标

- 项目分镜链路（ShotsTab/ShotCard）接入多图 —— 后端 `/api/videos` 已支持两种模式，后续单独一轮接入。
- 跨镜头自动衔接（上一镜头尾帧作下一镜头首帧）—— 引入串行依赖，打破批量并行生成，成本与复杂度不成比例。
- 手动逐镜头挑选/上传视频参考图 —— 画布通用 config 节点手动搭建路径已覆盖该需求，直出链路先做自动化部分。

## 四、方案对比（决策记录）

**方案 A（选定）：节点角色标注，纯前端编排层改动。** 分镜图节点 lineage 增加 `role: 'first' | 'last'`，尾帧图是同镜头的第二个直出 image 节点；视频派生按"有尾帧 → keyframes，无尾帧 → 帧图 + 定妆照多图参考"自动选模式。改动集中在 `canvas-storyboard.ts`、向导/工具栏 UI、`executeInNodeVideoGeneration` 一处小修复。

**方案 B（否决）：`CanvasShot` 增加视频参考 URL 字段。** 把图片 URL 塞进纯文本分镜数据，与"图即节点"、lineage/重拍体系冲突，且 data URL 会撑爆 script 节点 content。

**方案 C（否决）：镜头视频配置同步后端编排。** 违背画布无状态原则，工作量大，无当前必要。

## 五、数据结构变更（全部前端节点 content）

1. `ShotLineage`（`canvas-storyboard.ts`）增加 `role?: 'first' | 'last'`：
   - 仅 image lineage 使用；缺省视为 `'first'`，存量节点天然兼容；
   - `readLineage` 透传 role（非法值忽略）。
2. 视频直出节点 content 在有尾帧时写入 `use_keyframes: true`；无尾帧不写（与现状一致）。
3. `CanvasShot` 不变 —— 分镜保持纯文本数据，图片一律以节点存在。
4. script 节点 `shot_video_params` 增加 `refAssets?: boolean`（默认 true）：无尾帧镜头是否把命中定妆照并入视频参考图。

## 六、尾帧图生成

**入口（三处，共用同一实现）：**

1. 向导第 3 步逐镜头行内"生成尾帧"按钮（该镜头首帧已派生时可用）；
2. 向导第 3 步头部"批量补尾帧"（只处理"首帧已成功且尚无尾帧"的镜头）；
3. 分镜图节点悬浮工具栏"生成尾帧图"（`CanvasView.vue`，紧挨现有"派生视频"动作，仅对 role=first 且尚无尾帧的分镜图节点显示）。

**实现：** `deriveImagesInternal(scriptPanel, pending, role: 'first' | 'last' = 'first')` 扩展一个 role 参数：

- 幂等：同镜头已有尾帧节点（含 pending/loading）则跳过，与首帧派生的幂等语义一致；
- prompt：`buildShotImagePrompt(...)` 结果追加一行尾帧要求（"此图为该镜头动作的结束瞬间：与首帧同场景、同人物、同机位，人物动作处于收尾状态"。提示词中文硬编码与 `buildAssetImagePrompt` 现状一致，UI 标签文案一律走 i18n）；
- `referenceImages` 收集逻辑与首帧完全一致（上游图片节点 + 按镜头命中的角色/场景资产图），保障人物/场景一致；
- 节点命名 `#{no} 尾帧`（后缀走 i18n，参照 `videoSuffix`），lineage 写 `role: 'last'`，进入与首帧相同的 StepGroup。

v1 不做"从首帧结果 image2image 派生尾帧"的链式生成（依赖首帧完成，编排复杂）；首尾帧并列独立生成，见"风险"。

## 七、视频派生模式解析

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

## 八、执行层修复（canvas-generation.ts）

`executeInNodeVideoGeneration`（直出视频节点执行器）补齐：

- 读取 `panel.content.use_keyframes`；为 true 时校验 `referenceImages.length <= 2`（超出抛错），并把 `use_keyframes` 传入 `GenerationConfig`，使 `createVideoGenerationTask` 路由到 keyframes 模式；
- 重拍/重试复用同一执行器且保留节点 content，行为自动一致，无需额外处理。

## 九、UI 变更

1. `ScriptWizardDialog.vue` 第 3 步 `genRows` 改为 role 感知：
   - 主缩略图取 role=first 节点（现状逻辑需过滤掉尾帧节点，否则首帧槽位会被尾帧抢占）；
   - 每行新增尾帧缩略图槽（loading/error 样式与首帧一致）+ "生成尾帧 / 重拍尾帧"按钮 + 定位跳转；
   - 步骤头新增"批量补尾帧"按钮；
   - 视频参数栏新增"并入角色/场景参考图"开关（写入 `shot_video_params.refAssets`）。
2. `CanvasNodeHoverToolbar` / `CanvasView.vue`：分镜图节点（role=first 且尚无尾帧）悬浮工具栏增加"生成尾帧图"动作。
3. 新增 UI 文案全部走 i18n，zh/en 同步补充。

## 十、错误处理

- 尾帧生成失败：节点 error 态 + 批量结束汇总 warning（沿用既有批量模式）。
- 批量派生视频遇尾帧未就绪：计入 notReady 并 info 提示（沿用"分镜图未就绪"既有模式），不静默降级。
- 后端能力校验失败（模型不支持 keyframes / 参考图超限）：错误信息写入节点 error 态展示。

## 十一、测试与验收

项目无前端测试基建，验收 = `vue-tsc -b` 全量类型检查零错误 + 手动冒烟（沿用 specs 目录 smoke checklist 惯例）：

1. 三个入口生成尾帧均可用；向导行内尾帧缩略图/重拍/定位正确；
2. 有尾帧镜头派生视频：网络面板确认请求 `mode=keyframes`、首尾帧图正确、张数 = 2；
3. 无尾帧 + refAssets 开启：`images[]` = [帧图, ...命中资产图] 且 ≤ 5；关闭 refAssets 后仅帧图；
4. 尾帧 pending 时批量派生视频：该镜头被跳过且有 notReady 提示；
5. 存量分镜节点（lineage 无 role）回归：单图派生行为与改动前一致；
6. `refAssets` 开关与"并入参考图"状态在向导重开后保持。

## 十二、风险

- 定妆照（角色三视图并排图）作为视频参考图可能引入干扰 —— 与首帧生图使用同一类参考、同一风险面；若实测效果差，后续增加 per-shot 参考图开关。
- 首尾帧独立生成，构图一致性靠提示词 + 资产参考图保障，可能出现场景漂移 —— 后续可增强为"从首帧 image2image 派生尾帧"。

## 十三、关联文档

- [libtv-gap-analysis.md](../../libtv-gap-analysis.md) —— 差距补强计划（本设计对应"分镜→视频准确性"补强）
- [2026-08-29-script-node-asset-derivation-design.md](2026-08-29-script-node-asset-derivation-design.md) —— 分镜直出与资产按名注入（本设计的上游链路）
