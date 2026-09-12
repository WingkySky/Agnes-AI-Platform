# 画布连线生成：多模态输入传递与视频连视频

## 背景与问题

画布上把 文本→图片→视频 节点依次连线后，生成结果之间并没有真正的数据流动：图片生成仍是纯文生图，视频生成仍是纯文生视频。原因是连线只在 config 节点的生成链路生效：

- `executeMergeGeneration` / `executeMergeVideoGeneration` 走 `buildGenerationContext`，按连线收集上游资源（文本拼 prompt、图片进 referenceImages）；
- M3 三节点直出改造后成为主路径的就地生成 `executeInNodeGeneration` / `executeInNodeVideoGeneration` 只读节点自身 `content.prompt` 和 `content.referenceImages`，完全不查 connections；
- UI 层同样割裂：CanvasNode 的输入序号徽章只在连线目标为 config 时显示；节点悬浮输入条（CanvasNodeComposer）不展示接入了哪些上游。

设计结论：

- 其 `buildNodeGenerationContext` 对任意节点收集四类上游资源（text/image/video/audio 分开收集），视频整体作为 referenceVideos 传递，生成时原始视频文件直传（OpenAI 通道 `video[]`、Gemini 通道 inline data），能否视频生视频完全取决于模型；
- 其截帧是独立手动功能：右键菜单提供 截取首帧 / 尾帧 / 当前帧 三选项，离屏 video seek 后按原生分辨率绘制。

模型能力事实：

- Seedance 1.x 仅支持文生视频/图生视频/首尾帧，不接受视频输入；Seedance 2.0 起支持文字、图片、音频、视频四模态输入（多模态参考与编辑），2.5 进一步放宽参考数量；Veo 支持视频延展，Kling 支持视频续写，Wan2.1 不支持。
- 本平台 `/api/videos` schema 已支持 `video2video` 模式与 `reference_videos` 参数（最多 5 个），但模型能力表（`capabilities`）目前没有任何模型声明 `video2video`。

## 设计方案

### 1. 就地生成接入连线收集

`executeInNodeGeneration`（图片）与 `executeInNodeVideoGeneration`（视频）的生成上下文构建改为：节点自身内容 + 上游连线资源合并。

- 上游文本：追加到 prompt 末尾（沿用 config 链路的文本块格式）。
- 上游图片：追加进 referenceImages；与节点自身已有 referenceImages 按 URL 字符串去重（分镜直出节点自身的角色参考图/源图保留在前，上游图片排在后）。
- 上游视频：
  - 目标是视频节点时：若所选模型 `capabilities` 含 `video2video`，上游视频 URL 进 `reference_videos`，模式路由到 `video2video`；否则自动抽取上游视频当前播放位置的帧（未播放过为首帧；复用 `captureVideoFrame`，含代理回退）转为参考图，走 `image2video`。
  - 目标是图片节点时：抽上游视频当前播放位置的帧转为参考图。
  - keyframes 模式不受影响：仍以节点自身 images（首尾帧）为准，不混入上游资源。
- 节点自身 `content.referenceImages` 已有的场景（分镜直出）行为不变，上游资源只做增量合并。

config 节点的合并生成链路保持现状，不动。

### 2. 视频生视频的能力协商

- 判断依据：模型列表接口返回的 `capabilities` 数组（`AiModel.capabilities`），前端读 `capabilities.includes('video2video')`。
- 未声明 `video2video` 的模型一律走当前帧降级（抽上游视频播放头所在帧），不报错；声明后自动启用原生视频参考。
- `createVideoGenerationTask` 扩展 `video2video` 分支：`mode: 'video2video'` + `reference_videos` 透传（后端 schema/agnes_client/aibridge 已支持，最多 5 个）。
- 能力标签由模型管理维护：上游 Agnes API 声明后才给对应模型加 `video2video` 标签；前端不硬编码模型名单。

### 3. 上游输入可视化

连线接入的模块缩略图在输入条上可见。

- CanvasNodeComposer：image / video 节点的输入区上方增加一行输入 chips，数据来自 store 现有 `getInputNodesWithIndex`（与生成序号同源）。图片 chip 显示缩略图，文本 chip 显示「文本N」标签，视频 chip 显示带播放图标的缩略标记。
- CanvasNode 输入序号徽章：放开「连线目标必须是 config」的限制，资源→资源的连线（文本→图片、图片→视频）同样显示序号徽章；config 节点不是资源节点，不会出现在收集结果里，其产出的连线不会误显示徽章。

### 4. 截帧三选项

视频节点截帧从单一「截取当前帧」扩为 首帧 / 当前帧 / 尾帧 三选项：

- 首帧 = 0，尾帧 = `duration − 0.05`（避免 seek 到 duration 失败或黑帧），当前帧 = timeupdate 记录的最近播放位置（现状）。
- 实现：`loadVideoAt` 已支持任意时间戳，仅扩传入来源；新图片节点命名带帧位（「xx 首帧」等），i18n 中英文同步。

## 不做的事

- 不做音频上游参与生成（后端 reference_audios 已预留，待有模型声明能力再接）。
- 不做多图单节点重构、插件系统（维持既有判定）。
- config 节点链路不改。
