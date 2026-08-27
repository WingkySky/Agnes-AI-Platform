# LibTV 能力复刻 P0：短剧主链路（脚本 → 批量分镜 → 批量视频 → 片段重拍）设计

## 背景与目标

基于 [LibTV 功能调研](../../libtv-feature-research.md)，把 LibTV 的无限画布短剧创作能力复刻到本项目。总体分四期推进，本文档为总体规划 + 首期 P0 的详细设计：

- **P0（本期）**：短剧生成主链路——脚本节点 → 批量分镜图 → 批量图生视频 → 片段重拍
- **P1**：画布交互对齐（双击建节点、节点"+"派生、组整体引用、工作流一键重跑、slash 面板）
- **P2**：角色一致性工具包（角色三视图、多机位九宫格、剧情推演四宫格、25 宫格连贯分镜）
- **P3**：工具补齐（扩图、擦除/抠图、打光、多角度、首尾帧提取）
- **P4**：逐帧拉片、导演台与分镜联动

每期单独走一轮设计 → 实施，不在本期展开。

## 关键决策

| 决策点 | 结论 | 理由 |
| --- | --- | --- |
| 范围 | 总体规划四期，本期只做 P0 生成侧 | 成片合成已有 tts/subtitle/compose 节点手动可用，串联合成为后续增强 |
| 数据存储 | 本地优先：脚本/分镜/lineage 全部存画布 JSON（localforage） | 与现有画布架构一致，零后端表结构变更 |
| 架构 | 方案 A：主画布新增 script 节点 + 批量派生真实节点 | 每个镜头都是节点，天然支持单镜头重拍、分叉引用、接入现有合成链路；派生编排逻辑可被 P1/P2 复用 |
| 成片合成 | 不纳入 P0 | 沿用现有 compose 节点手动连线 |

否决的备选：节点内分镜列表（镜头结果不可被下游引用，偏离画布理念）；建在后端项目制模块（与主画布割裂，与本地优先冲突）。

## 整体架构与数据流

新增节点类型 `script`（脚本节点），作为短剧主链路源头，其余复用现有 config 节点生成体系：

1. **输入**：script 节点内写剧情概述，支持连线引用上游文本节点（世界观/角色设定）与图片节点（角色参考图）。
2. **生成分镜脚本**：前端调 `POST /api/storyboard`，后端用现有 `agnes_client` 的 `/chat/completions` + 结构化 prompt，LLM 输出 JSON 分镜数组回填节点内分镜列表。列表逐条可编辑、可删除、可手动新增。期望镜头数由用户在节点内指定（默认 6–12，上限 30）。
3. **批量生成分镜图**：前端编排器为每个镜头自动创建一个图片 config 节点——prompt 按模板拼装（风格 + 角色设定 + 镜头画面描述 + 景别/机位），角色参考图自动带入 referenceImages；节点按镜头顺序网格布局、自动连线（script → config）、包进一个 StepGroup。生成走现有 `createImageTask` + taskQueue（并发上限、轮询、回填机制全部复用）。
4. **批量图生视频**：分镜图节点一键派生 video config 节点（图生视频模式，prompt 默认携带该镜头运镜描述），走现有 `createVideoTask`。
5. **片段重拍**：派生节点 content 记录 `lineage`（来源脚本节点、镜头号、原始 prompt），修改提示词后重新生成只影响该节点。不引入新机制，本质是"带出处的单节点重生成"。

后端仅新增一个无状态路由，不建表、不存储。

## 组件与数据结构

### 前端

| 位置 | 内容 |
| --- | --- |
| `components/canvas/nodes/ScriptNodeContent.vue`（新） | script 节点主体 UI：剧情输入、分镜列表（序号/景别/机位/画面描述/台词，行内编辑）、"生成分镜脚本"/"批量生成分镜图"/"批量生成视频"操作区。CanvasNode 已 57KB，按节点类型挂子组件，不再堆大 |
| `lib/canvas-storyboard.ts`（新） | 纯逻辑层：分镜 prompt 模板拼装、批量派生节点结构生成、网格自动布局坐标计算、lineage 构造。不依赖 store 单例，保留可测性 |
| `stores/canvas.ts` | 注册 `script` 节点类型；连线校验新增：script 只允许出边到 config；新增 action：按分镜批量创建节点（布局、连线、StepGroup 分组） |
| `CanvasToolbar.vue` | "添加节点"菜单加"脚本" |
| `CanvasNodeHoverToolbar.vue` / `CanvasContextMenu.vue` | 分镜图节点加"派生视频节点"入口 |
| `api/storyboard.ts`（新） | `POST /api/storyboard` 封装 |
| `i18n/zh-CN.ts`、`en-US.ts` | 全部新文案走 `t()`，不硬编 |

### 数据结构（存于画布 JSON，localforage）

```ts
// script 节点 content
{
  story: string,            // 剧情概述（含从上游文本节点汇总的内容）
  shots: Array<{
    id: string,             // 镜头唯一 id，派生节点通过它回溯
    no: number,             // 镜头序号
    shotSize: string,       // 景别（远景/全景/中景/近景/特写）
    camera: string,         // 机位/运镜
    description: string,    // 画面描述（生图 prompt 的主体）
    dialogue: string,       // 台词（可空，后续接配音）
  }>,
}

// 派生的 config 节点 content 追加
{
  lineage: {
    scriptPanelId: string,  // 来源脚本节点
    shotId: string,         // 镜头 id
    shotNo: number,         // 镜头序号（排序用）
    originPrompt: string,   // 生成时的原始 prompt（重拍参照）
  },
}
```

连线沿用现有 `GenerationConnection`。**角色参考图以快照方式落地**：批量派生分镜图节点时，把 script 节点收集到的角色图 URL 直接写入该 config 节点的 `referenceImages`，不依赖运行时沿链路上溯——分镜图的重拍结果不随后续上游改动漂移。

### 后端（无表、无存储）

- `routes/storyboard.py`：`POST /api/storyboard`
- `services/storyboard_service.py`：拼结构化 prompt → `agnes_client` chat → 剥离 markdown 代码栅栏 → JSON 解析 → Pydantic 校验
- `schemas/storyboard.py`：请求/响应模型

**接口定义：**

```
POST /api/storyboard
Request {
  story: string                    // 剧情概述
  characters: [{                   // 角色设定（来自上游文本/图片节点）
    name: string
    description: string
    ref_image_url: string | null   // 角色参考图
  }]
  shot_count_min: int              // 期望镜头数下限
  shot_count_max: int              // 期望镜头数上限（≤30）
  style: string                    // 画面风格（可空）
}
Response { status, message, data: { shots: [<与前端 shots 同构的数组>] } }

错误：400 未配置聊天模型 / 参数校验失败；502 LLM 输出解析失败（重试一次后仍失败）；504 上游超时
```

## 错误处理

- **LLM 输出非法 JSON**：剥离代码栅栏后解析，失败重试一次，仍失败返回 502，前端 toast"分镜脚本生成失败，请重试"。不做自动修复。
- **无 chat 模型**：`model_registry` 查不到 chat 类型时 400 明确报错。
- **分镜数量上限 30**：前端批量创建前限制 + 后端 `shot_count_max ≤ 30` 校验，防止积分失控；批量生成前复用现有积分预估逻辑出确认弹窗（汇总全部镜头费用）。
- **批量任务部分失败**：每个镜头是独立队列任务，失败节点独立标记，可单条重试（现有机制）。
- 派生节点数量大：localforage 写入已有 400ms 防抖，无额外处理。

## 验证方式

项目无测试基建，按项目惯例以类型检查 + 手动冒烟为主：

- 前端 `vue-tsc` 类型检查；后端语法/类型检查。
- 手动冒烟六个场景：单镜头、多镜头、含台词、角色图引用、失败重试、30 镜头上限。
- `canvas-storyboard.ts` 为纯函数层（不依赖 store 单例），后续补测试基建时可直接测。

## P0 里程碑

1. **M1**：script 节点 + 后端 `/api/storyboard` + 分镜列表编辑（单节点闭环）
2. **M2**：批量派生分镜图（编排器 + 自动布局 + StepGroup + 积分确认）
3. **M3**：批量图生视频 + lineage + 片段重拍

## 后续路线概要（每期单独设计）

- **P1 画布交互**：双击空白建节点；节点"+"派生下游（泛化 M2/M3 的派生编排）；组整体引用（组"+"派生）；工作流保存/一键重跑（基于 `canvas-flow-analyzer.ts`）；slash 指令面板（扩展 GenerationQuickPanel）。
- **P2 角色一致性工具包**：统一实现模式 = prompt 模板注册表 + 并发生成 + 宫格切分成独立节点（复用 `canvas-image-ops.ts` 已有分割）。含角色三视图、多机位九宫格、剧情推演四宫格、25 宫格连贯分镜、画面推演（±秒）。
- **P3 工具补齐**：扩图、擦除/抠图、打光（光位模板）、多角度（机位模板）、首尾帧提取再生成、帧率提升（视上游 API 能力）。
- **P4**：逐帧拉片（上传参考视频抽帧 + 多模态分析 → 镜头参考卡）；导演台与分镜联动（3D 场景输出机位图作为分镜首帧）。

## 参考

- 功能调研：`docs/libtv-feature-research.md`
- 现有画布底座：`frontend/src/components/canvas/InfiniteCanvas.vue`、`stores/canvas.ts`、`lib/canvas-generation.ts`、`stores/taskQueue.ts`、`lib/canvas-storage.ts`
- 后端生成体系：`backend/app/routes/images.py`、`routes/videos.py`、`services/chat_service.py`、`services/agnes_client.py`
