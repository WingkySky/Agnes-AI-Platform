# LibTV 优点提炼与差距补强计划

本文对照 LibTV（liblib.tv）的产品优点，逐项核实本仓库代码现状后整理而成，用于指导后续功能补强。LibTV 的功能调研背景见 [libtv-feature-research.md](libtv-feature-research.md)；该文的差距表成文于分镜直出动工之前，现状以本文为准。

## 一、LibTV 的优点提炼

LibTV 的产品优势不是单点功能，而是四条互相咬合的"效率飞轮"：

### 1. 全流程一站式闭环

剧本 → 分镜 → 图 → 视频 → 后期剪辑在一个界面完成，不切换工具。官方教程从输入故事到产出全部片段都在画布内完成，仅最后的拼接剪辑交给剪映等外部工具。

### 2. 智能引用，操作成本极低

- 点击节点"+"自动派生下游节点并自动连线，上游内容自动作为生成输入；
- 上游文本连到生成器后自动并入提示词，用户几乎不管理连线；
- 双击画布空白直接建节点，本地图片/视频/音频可直接拖入画布成节点。

### 3. 分镜表是"批量生产核心"

脚本节点把剧情一键转成结构化分镜表，再一键"批量转分镜图 → 批量转视频片段"，每条结果可单独调整重新生成（片段重拍）。这直接命中短剧"几十个镜头、大量抽卡"的生产模式。

### 4. 资产体系保证角色一致性

角色/场景/道具三类资产统一管理，配合角色三视图锁定形象，保证跨分镜不崩脸。这是连续叙事短剧的命门，也是 LibTV 生态最强的一环。

### 配套能力

- 20+ 模型自由切换（Seedance、Wan、Kling、MiniMax、Midjourney 等）；
- 宫格探索工具：多机位九宫格、剧情推演四宫格、角色三视图、连贯分镜（Slash 指令调出）；
- 图像/视频工具箱：扩图、擦除、抠图、打光、多角度、高清放大、帧率提升、首尾帧提取；
- 导演台（3D 虚拟场景布景调度）、逐帧拉片（参考视频逐帧分析）；
- 工作流打组保存、一键重复执行；画布分享与社区。

### 用户痛点信号（公开评论区）

用户两大核心抱怨是**成本**（"一部剧上千块"、"无限充值"）和**抽卡率**（分镜→视频成功率低）。本项目"本地优先 + 自带 API Key + 生成前积分预估"的形态正好切中成本痛点，应作为差异化方向持续强化。

## 二、本项目已对齐的能力

以下能力经代码核实已具备，无需重复建设：

- **分镜直出主链路**：script 节点 → 分镜向导（分镜表可编辑、AI 提取角色/场景资产、参考图按名注入）→ 批量生成分镜图（幂等跳过、并发池、积分预估确认、自动挂组）→ 批量图生视频。核心逻辑在 `frontend/src/lib/canvas-storyboard.ts`，向导在 `frontend/src/components/canvas/nodes/ScriptWizardDialog.vue`。
- **模型聚合**：双 Provider（Agnes AI + 火山 Seedance），图片含 agnes-image-2.1-flash 与 Seedream 全家族，视频含 agnes-video-2.5、Seedance 全家族与 Wan2.1 系列，按请求切换、支持自定义模型（`backend/app/services/provider_registry.py`）。评论区公认效果主力是 Seedance，已接入。
- **节点派生与自动连线**：悬停工具栏支持文生图/图生图/图生视频、分镜图派生视频、视频首帧再生（`CanvasNodeHoverToolbar.vue` + `CanvasView.vue`）。
- **成片合成（领先项）**：项目级 `backend/app/services/project/merge_service.py` 支持 concat + xfade 转场 + 画中画 + 字幕烧录，而 LibTV 内置剪辑仍在完善、官方推荐导出剪映。
- **任务队列与成本控制**：生成前积分预估、预扣、失败退款（`routes/images.py`、`routes/videos.py`）。
- **3D 导演台底座**：three.js 场景编辑（`SceneEditorView.vue` + `Scene3DEditor.vue`）。
- **视频模式**：文生/图生/首尾帧（keyframes）/视频生视频（2.5 非 Flash）均已支持。

## 三、缺陷清单与补强建议

### A. 主链路断点（最高优先）

**A1. 单镜头重拍对直出节点失效（bug）—— 已修复**
`CanvasView.vue` 的 `handleHoverReshoot` 原先只认 `content.sourceFrom` 回溯 config 节点重跑，分镜直出节点（lineage 在自身 content）点"重拍"静默无效。已修复：直出节点重拍/重试统一走 `executeInNodeGeneration` / `executeInNodeVideoGeneration` 就地执行，保留节点上的模型/参数/参考图/源图。

**A2. TTS 为空壳，配音链路断裂**
`backend/app/services/project/audio_service.py` 的 `_call_tts_provider` 直接抛 `NotImplementedError`，`agnes_client.create_tts_task` 同为 stub；画布 tts/subtitle/compose 节点只有设置 UI、无后端执行链路。短剧没有配音+字幕+合成的成片闭环，产出到"一堆片段"即止。`requirements.txt` 已含 `aibridge-sdk[edge-tts]`、音色预设已定义 8 个，缺的只是接线。

**A3. BGM 内置库无音频文件**
`services/project/bgm_library.py` 定义了 5 条按情绪分类的曲目元数据，但 `backend/assets/bgm/` 目录为空。与 A2 一并补齐。

### B. 角色一致性（LibTV 最强项）

**B1. 资产库与画布两套体系不通**
独立资产库（角色/道具/场景，`AssetsView.vue`）不能拖入画布；画布素材面板（`CanvasAssetLibrary.vue`）只有历史素材与本地素材两个 tab。script 向导内的资产卡是孤立副本，资产库中维护的角色形象做分镜时用不上。建议：资产库加入画布素材面板可拖出；向导资产卡支持"从资产库选择"。

**B2. 无三视图生成工作流**
资产卡的"角色三视图"只是一句提示词文案（`canvas-storyboard.ts` 的 `buildAssetImagePrompt`），不是工作流。LibTV 的三视图是"生成宫格 → 切分 → 挑图入库"。项目已有宫格切分能力（`canvas-image-ops.ts`），缺"三视图模板 + 并发生成 + 切分回写资产卡"的编排。

**B3. 逐镜头提示词裸拼**
`buildShotImagePrompt` 是字段直接拼接，无润色环节。LibTV 有独立"合成提示词"环节且教程强调"优化提示词、提高抽卡率"。建议批量生图前加可选的 LLM 逐镜头提示词润色（复用 `/api/storyboard` 的 LLM 链路），这是提升出图质量性价比最高的一招。

### C. 抽卡与探索工具（高频、实现成本低）

**C1. 宫格工具族缺失**
多机位九宫格、剧情推演四宫格、连贯分镜均无。实现模式统一：prompt 模板 → 并发生成 → 宫格切分成独立节点；模板、并发、切分三项底层能力均已具备，纯前端编排即可。

**C2. Slash 指令入口**
`GenerationQuickPanel.vue` 目前只是生成参数弹窗，可扩展为指令面板，宫格工具族从这里进入。

### D. 画布交互对齐（成本低）

- 双击空白建节点未实现（`InfiniteCanvas.vue` 无 dblclick 处理）；
- 本地文件不能直接拖入画布成节点（`handleDrop` 只解析素材面板的 `application/x-asset`），需支持 `dataTransfer.files` 直落节点；
- 旋转已实现（`canvas-image-ops.ts` 的 `rotateImage`）但未接入工具栏，属死代码；
- 组（StepGroup）只有可视化与管理，无"整组重跑/整体引用派生"。

### E. 图像/视频工具补齐（依赖后端端点）

- 画布的放大/超分是前端本地插值算法，非 AI 超分，对 AI 出图意义有限；
- 后端无扩图、擦除、抠图、打光端点；打光可先用光位 prompt 模板方案（多角度已按此实现）；
- 视频侧缺：帧率提升、视频分镜解析（视频 → 分镜脚本，用于拆解对标片）、对口型/音生视频（取决于上游模型契约，Seedance 2.5 若支持音视频直出可优先接）。

### F. 远期项

- 逐帧拉片（上传参考视频抽帧分析 → 镜头参考卡）；
- 导演台输出首帧/机位图到画布（3D 编辑器目前无截图导出能力，与画布无数据通道）；
- 每日配额与生成前 AI 审核（当前仅严格模式敏感词预检，AI 审核发生在分享到广场之后）；
- 项目制与画布 script 双体系的进一步融合（现有 `asset_archive`/`asset_bridge` 桥接方向正确，不建议合并）；
- 画布分享、社区、Agent 入口（对辅助短剧创作非核心，暂不做）。

## 四、建议补强顺序

1. ~~修复 A1 reshoot bug~~ —— 已修复（直出节点重拍/重试走就地执行）；
2. **打通 A2/A3 成片闭环**（TTS 接线 + 画布 compose/subtitle 节点接 merge 链路 + BGM 文件）—— 完成后用户才能从一句话走到成片，对标 LibTV 的全流程闭环；
3. **B 组一致性三件套**：资产库互通 → 三视图 → 提示词润色；
4. **C 组宫格工具 + Slash 面板** —— 低成本高感知；
5. **D/E 组**按"交互优先、工具次之"滚动补齐。

另有一项工程健康度问题曾存在：全量 `vue-tsc -b` 的 35 个历史遗留类型错误阻塞 `npm run build`——已在生成配置下放实施期间清理完毕，当前全量类型检查为零错误。

## 五、关联文档

- [libtv-feature-research.md](libtv-feature-research.md) —— LibTV 功能调研与复刻方案（背景）
- [competitive-analysis-and-improvement-plan.md](competitive-analysis-and-improvement-plan.md) —— 开源竞品对比与工程化精进路线
- [optimization-plan.md](optimization-plan.md) —— 平台优化计划
