# 画面时间推演（前/后帧预测）融入分镜直出链路设计

基于 LibTV"画面时间推演"功能的调研结论，把"基于一张关键画面推演前/后 N 秒画面"的能力融入现有画布分镜直出链路（script 节点 → 分镜图 → 视频）。本设计是 [分镜视频多图参考 / 首尾帧 / 跨镜头衔接设计](2026-08-30-shot-video-multi-reference-design.md) 的后续增强，分两期实施：P1 双向画面推演帧（图片层）、P2 画面链长视频（keyframes 分段 + 成片合成）。

## 一、背景与问题

### 1.1 LibTV 功能调研结论

LibTV 于 2026 年 3 月上线"画面时间推演"功能：基于一张关键画面，自动推演生成**前 3 秒 / 后 5 秒的画面延展**，输出的是**画面（图片）**而非视频，用于构建更连贯的叙事链，在故事板预演与长视频分段生产中价值最高。需与"剧情推演四宫格"（推演剧情走向的宫格图）区分：画面时间推演是**时间轴方向**的延展。

### 1.2 本项目现状

多图参考设计已落地，与"画面时间推演"的对照：

| 画面时间推演的组成 | 本项目现状 |
|---|---|
| 后向延展（后 N 秒画面） | **已有**：尾帧图（`ShotLineage.role: 'last'`），prompt 固定为"动作结束瞬间" |
| 前向延展（前 N 秒画面） | **部分已有**：跨镜头衔接 `linkPrev` 只覆盖"镜头间"且必须有上一镜尾帧；第 1 镜、独立分镜图无前延展能力 |
| 延展画面 → 长视频 | **断点**：keyframes 视频与 compose 成片合成均已具备，缺"画面链 → 分段视频 → 拼接成片"编排 |

### 1.3 上游 API 约束（决定整体形态）

Agnes Video 2.5（`backend/app/services/agnes_client.py`）：

- `mode=keyframe`：`first_frame` **必填**、`last_frame` 可选（`images[0]` / `images[-1]`），**不支持"仅尾帧"生成前向视频**；
- keyframe 与 reference 两种 mode **互斥**。

因此"前 N 秒"只能走**图片推演**（image2image 多图参考 + prompt 描述"之前时刻"），这与 LibTV 输出画面而非视频的形态一致；长视频则通过"画面链上相邻两帧互为首尾帧的分段 keyframes 视频 + concat"实现，段间共享帧保证连续。

## 二、目标

1. **P1**：每张分镜图（role=first）可选生成"前段帧"（该镜头动作开始前约 N 秒的画面），与既有尾帧图对称，补齐双向时间推演；
2. **P2**：对单个镜头可发起"画面链长视频"：以分镜图为锚点构建画面链（首帧 → 尾帧 → 后续链帧），相邻链帧两两生成 keyframes 分段视频，全部就绪后自动建 compose 节点合成完整长镜头；
3. 全部改动收在画布分镜直出链路（前端），后端零改动；复用现有 compose 成片能力。

## 三、非目标

- 前向延展的视频级生成（仅尾帧视频上游不支持，见 1.3）；
- 视频级衔接（从已生成视频抽末帧再延展）——多图参考设计中已否决（串行、脆弱），本设计用画面链绕开，维持否决；
- 后向链帧间隔可配置（v1 固定等于视频时长档位 `seconds`）；
- 项目分镜链路（ShotsTab/ShotCard）接入——后续单独一轮。

## 四、方案对比（决策记录）

**方案 A+B（选定）：图片推演 + 画面链串段成片。** P1 补齐前延展帧（对齐 LibTV 本体形态），P2 把链帧两两成段生成 keyframes 视频 + compose 拼接。图片节点天然可并发、重拍粒度是单节点，后端零改动。

**方案 C（维持否决）：视频级延展。** 从已生成视频提取首/末帧再做时间延展。衔接最"真"，但视频批量全串行、单点失败阻断整链、重拍上游导致下游全部失效（多图参考设计中的否决理由仍成立）。

## 五、数据结构变更（全部前端节点 content）

`ShotLineage`（`frontend/src/lib/canvas-storyboard.ts`）：

1. `role` 扩展为 `'first' | 'last' | 'prev' | 'chain'`：
   - `'first'`（缺省）/ `'last'` 语义不变（首帧 / 动作结束尾帧）；
   - `'prev'`：前段帧（动作开始前画面），P1 新增；
   - `'chain'`：后向链帧，配合 `chainSeq` 使用，P2 新增。
2. 新增 `chainSeq?: number`：链上时间序号。锚点首帧视为 seq 0，尾帧视为 seq 1，链帧 seq = 2, 3, …；`'prev'` 视为 seq -1。`readLineage` 透传并校验（非法值忽略）。
3. 画面链的帧间隔 = script 节点视频参数 `seconds`（时长档位）；尾帧时刻近似视为"1 个档位之后"，与既有"尾帧 = 动作结束瞬间"语义兼容。

视频直出节点 content 沿用 `use_keyframes: true` 标记，链段视频同样写入（执行器既有路由零改动）。

## 六、P1：前段帧生成

**入口（两处，共用同一实现 `derivePrevFrameForShot`）：**

1. 分镜图节点（role=first 且尚无前段帧）悬浮工具栏"推演前段画面"（`CanvasNodeHoverToolbar.vue`，紧挨现有"生成尾帧图"）；
2. 向导第 3 步镜头行内：在尾帧槽旁新增前段帧槽位 + "生成前段帧 / 重拍前段帧"按钮（`ScriptWizardDialog.vue`）。

**生成规格：**

- 模式：image2image 多图参考，`referenceImages = [锚点分镜图, ...按镜头命中的资产图]`（锚点排首位，最大化其对构图影响）；
- prompt：`buildShotImagePrompt(...)` 结果追加前段帧附加行（常量，与尾帧附加行并排定义）：`此画面为该镜头动作开始前约{N}秒的瞬间：与主画面同场景、同人物、同机位，动作处于尚未开始的起始前状态`（N 取该镜头 `duration`；提示词中文硬编码与尾帧附加行现状一致，UI 标签一律走 i18n）；
- 节点命名 `#{no} 前段帧`（后缀走 i18n，参照 `tailSuffix`），lineage 写 `role: 'prev'`，进入与首帧/尾帧相同的 StepGroup，布局排在首帧同列、尾帧行带的上方独立行带；
- 幂等：同镜头已有前段帧节点（含 pending/loading）则跳过，与尾帧幂等语义一致。

**P1 不动视频派生**：前段帧 v1 只作为画面推演预览（时间轴向前延展的对齐项），不参与 P2 画面链与视频派生；是否将前段帧纳入画面链长视频（作为链头段）留作后续增强，避免 P1 动视频链路。

## 七、P2：画面链长视频

**入口：** script 节点视频参数区新增"长镜头分段数"（`shot_video_params.chainSegments?: number`，默认 0 = 不启用；取值 1–4）。启用后，向导第 3 步镜头行内出现"生成分段视频"动作；分镜图节点悬浮工具栏对 role=first 节点同样出现该动作。

**编排（`deriveChainVideosForShot`）：**

1. **画面链构建**：`[seq0=首帧, seq1=尾帧, seq2..(1+n)=链帧]`，n = chainSegments。链上缺帧（尾帧或链帧未生成/未成功）时**自动补齐**入队（补齐沿用尾帧/前段帧的派生实现模式：image2image 多图参考、锚点排首位；链帧 lineage 写 `role: 'chain'` + `chainSeq`，prompt 追加链帧附加行：`此画面为该镜头动作结束后第{k}个时段的画面：同场景、同人物、同机位，动作从上一时刻状态自然继续推进`，k = chainSeq - 1，每段时长 = 视频档位 `seconds`），补齐数量计入积分预估确认总数；
2. **积分预估**：动作入口一次性确认"补齐帧数 + 分段视频数"两笔消耗（复用现有积分预估确认流程）；
3. **分段视频**：链帧全部 success 后，相邻帧 `[seq i-1, seq i]`（i = 1..1+n）两两生成 1 个视频直出节点：`use_keyframes: true`、`referenceImages = [帧i-1, 帧i]`、`seconds = params.seconds`、prompt 用 `buildShotVideoPrompt(shot)` + 段序标注行（"本段为该动作的第{i}/(1+n)段，从起始帧动作状态自然延续到结束帧动作状态"）。段间共享帧保证 concat 后画面连续；
4. **成片合成**：全部分段视频 success 后，自动创建 compose 节点（复用现有"生成成片"能力），按段序连线各段视频节点并执行，产出长镜头成片；任一段失败则不建 compose，计入汇总提示；
5. **并发与依赖**：帧补齐任务进现有图片并发池（池内无相互依赖）；段视频在帧就绪后进视频并发池（段间无依赖，沿用 `VIDEO_CONCURRENCY`）；compose 依赖全部段成功。

**失败语义（与现有批量模式一致，不静默降级）：**

- 链帧生成失败：对应帧节点 error 态，依赖它的分段跳过并计入批量结束汇总 warning；
- 用户显式启用链式长视频后，缺帧补齐失败不会降级为"只出部分段 + compose"：compose 不建，明确提示缺哪段；
- 单镜头入口在前置帧未就绪且补齐失败时给出具体提示（参照衔接镜头"先生成上一镜头尾帧"的提示模式）。

## 八、改动清单（预估）

| 层 | 文件 | 改动 |
|---|---|---|
| 编排 | `frontend/src/lib/canvas-storyboard.ts` | `ShotLineage` role/chainSeq 扩展、`derivePrevFrameForShot`、`deriveChainVideosForShot`、前段帧/链帧 prompt 附加行、节点布局行带；参考图截断改按模型生效（仅 2.5 Flash，见第九节） |
| 入口 | `frontend/src/components/canvas/CanvasNodeHoverToolbar.vue` | "推演前段画面"、"生成分段视频"动作 |
| 入口 | `frontend/src/components/canvas/nodes/ScriptWizardDialog.vue` | 行内前段帧槽位、链式动作与分段数参数 |
| 入口 | `frontend/src/views/CanvasView.vue` | 对应 handler 接线 |
| 参数 | script 节点视频参数区 | `chainSegments` 参数项 |
| i18n | `frontend/src/i18n/zh-CN.ts` / `en-US.ts` | 前段帧/链帧/分段视频/汇总提示文案 |
| 后端 | 无 | 零改动（keyframes 与 compose 能力均已具备） |

## 九、风险

- 前段帧/链帧与锚点帧的构图一致性靠提示词 + 资产参考图保障，可能出现场景漂移——与既有尾帧同级风险，后续可增强为"从锚点帧 image2image 强约束派生"；
- keyframe 与 reference 互斥：分段视频不带资产参考图，资产一致性由链帧生成阶段保障；
- 模型契约差异备注：2.5 的 keyframe 仅收 `first_frame`/`last_frame` 两个定长字段（1–2 张），多图素材归 reference（无时间锚点顺序语义），故画面链在 2.5 上只能相邻帧两两分段；2.0 契约的 `extra_body.image` 数组 + `extra_body.mode: "keyframes"` 支持多关键帧一链一段（受 `num_frames ≤ 441`，约 18 秒 @24fps 约束）。链节点模型（`role: 'chain'` + `chainSeq`）与编排层（`deriveChainVideosForShot`）已隔离此差异——若后续 2.5 放开 keyframe 多帧字段，或指定镜头回退走 2.0，仅需调整分段策略即可切换"一链一段"单请求生成，不改节点与 lineage 模型；
- 参考图张数上限是模型级差异：`images ≤5` 仅是 agnes-video-2.5-flash 的独立限制，2.5 非 Flash 与 2.0 契约均无此硬限制。前端仅在取图所选视频模型为 2.5 Flash 时把多图参考截断到 5 张（在前端拦截，避免把超限请求发往后端再回传错误信息），其余模型不截断；后端 Flash 前置校验保留作兜底，上游对非 Flash 若有隐含约束由其错误自然暴露。现状修正点：`collectShotVideoRefs` 目前对多图参考无条件 `slice(0, VIDEO_REF_MAX)`，需改为按模型判断；图片侧（image2image 派生）前端本就未做张数截断，维持现状；
- 链越长积分消耗越多：`chainSegments` 上限 4，且必须经积分预估确认；
- 首帧若为衔接帧（`linkPrev` 开头、以上一镜尾帧续接），链式长视频仍以其为链锚点正常工作，不影响跨镜头衔接语义。

## 十、验收标准

1. P1：任一分镜图可通过悬浮工具栏/向导生成前段帧；重复触发幂等跳过；前段帧节点 lineage `role: 'prev'`、命名与布局正确；
2. P1：前段帧请求为 image2image 多图参考，`referenceImages[0]` = 锚点分镜图，prompt 含前段附加行与时长；
3. P2：设置 `chainSegments = n` 后发起分段生成：自动补齐缺失尾帧/链帧，积分确认数量 = 补齐帧数 + (1+n) 段视频；
4. P2：每段视频请求 `mode=keyframes`、首尾帧为相邻链帧、张数 = 2、seconds = 档位值；
5. P2：全部段成功后自动出现 compose 节点并连线全部段视频，成片可播放且段间过渡连贯；任一段失败时不建 compose 且有汇总提示；
6. 回归：不启用 `chainSegments` 时，现有"派生视频 / 生成尾帧 / 跨镜头衔接"行为完全不变。

## 参考

- [LibTV 功能调研与复刻方案](../../libtv-feature-research.md)
- [LibTV 优点提炼与差距补强计划](../../libtv-gap-analysis.md)
- [分镜视频多图参考 / 首尾帧 / 跨镜头衔接设计](2026-08-30-shot-video-multi-reference-design.md)
- LibTV"画面时间推演（前3秒/后5秒画面延展）"调研来源：AIProductHub LibTV 词条
