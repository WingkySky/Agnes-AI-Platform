# 创意流水线前端重构设计文档

> 版本：v1.0
> 日期：2026-06-25
> 状态：已确认，待实施
> 基于：[01-creative-pipeline-overview.md](./01-creative-pipeline-overview.md)、[02-creative-pipeline-todolist.md](./02-creative-pipeline-todolist.md)

---

## 目录

1. [背景与问题](#1-背景与问题)
2. [重构目标与原则](#2-重构目标与原则)
3. [架构变更概览](#3-架构变更概览)
4. [Store 拆分与 taskQueue 扩展](#4-store-拆分与-taskqueue-扩展)
5. [API 路径决策与类型集中](#5-api-路径决策与类型集中)
6. [组件复用与新建方案](#6-组件复用与新建方案)
7. [页面重写方案](#7-页面重写方案)
8. [权限点设计](#8-权限点设计)
9. [i18n 命名空间设计](#9-i18n-命名空间设计)
10. [SSE 重写与数据流](#10-sse-重写与数据流)
11. [渐进式产物可见性](#11-渐进式产物可见性)
12. [后端修复](#12-后端修复)
13. [实施顺序](#13-实施顺序)
14. [验收标准](#14-验收标准)

---

## 1. 背景与问题

### 1.1 现状评估

创意流水线（Creative Pipeline）前端代码已实现，但存在大量内部不一致和重复造轮子问题，导致页面不可用。

**技术栈对齐**（无偏离）：
- Vue 3 + Element Plus + Pinia + Vue Router + localforage（正确）
- 未引入 Tailwind / Ant Design / Naive UI 等额外 UI 库（正确）
- 全部使用 `@element-plus/icons-vue` 图标（正确）

**实质性问题**（导致页面不可用）：

| # | 严重度 | 问题 | 影响 |
|---|--------|------|------|
| 1 | 致命 | `WorkshopView.vue`、`AssetsView.vue` 用 `var(--text-primary)` 等 CSS 变量，但项目实际是 `--agnes-text-primary` | 样式全部失效 |
| 2 | 致命 | `PipelineResultView.vue` 的 `goBack()` 跳 `/pipeline/runs`（路由不存在） | 返回按钮失效，跳首页 |
| 3 | 致命 | `PipelineResultView.vue` 步骤类型枚举（`script_gen/image_generate/video_merge`）与后端/设计（`llm_generate/image_batch/video_batch`）完全不一致 | 步骤类型标签全部 fallback |
| 4 | 严重 | `stores/asset.ts` 实际是画布媒体资源库（localforage），并非设计文档的「创意资产库 store」 | AssetsView 只能直连 API，绕过 store |
| 5 | 严重 | `AssetsView.vue` 资产类型 tab 是 `character/scene/style/object`，后端校验的是 `character/prop/scene/brand` | 类型筛选会 400 |
| 6 | 严重 | `PipelineResultView.vue`、`ResultDisplay.vue`、`usePipelineSSE.ts` 全程硬编码中文 | 违反 AGENTS.md i18n 规则 |
| 7 | 中等 | `stores/pipeline.ts` 把 styles/scriptTemplates 混进 pipeline store，设计要求独立 `styles.ts` store；`loadStylePresets` 写死 `is_builtin: true` | 用户自定义风格无法加载 |
| 8 | 中等 | 前端大量重复造轮子（未复用 taskQueue、useCreditEstimate、ImageWithWatermark、ImageViewer、PromptTemplates、client.ts token 处理等） | 代码冗余，体验割裂 |
| 9 | 低 | `usePipelineSSE.ts` 拼写错误 `manuallClosed`（6 处）、`ResultDisplay.handleSaveToAsset` 未实现 | 代码质量问题 |

**后端问题**（已修复，见第 12 节）：
- `engine.py` 的 `cancel()` 方法三处致命 bug（`STATUS_WAITING_APPROVAL` 未定义、`run.precharged_credits` 字段不存在、`refund_credits` 调用签名错误）

### 1.2 重复造轮子清单

| # | 现有基础设施 | pipeline 重复实现 | 重构动作 |
|---|------------|-----------------|---------|
| 1 | `taskQueue.ts` 的 `registerXxxTask` 扩展模式 | pipeline 自建运行进度管理 | 扩展 taskQueue 支持 pipeline |
| 2 | `TaskCard.vue` + `TaskQueuePanel.vue` 全局任务面板 | pipeline 运行不在全局面板出现 | 扩展 TaskCard 支持 `source='pipeline'` |
| 3 | `ImageWithWatermark.vue` + `ImageViewer.vue` | ResultDisplay 裸用 `<el-image>`，无水印无放大 | 复用 ImageWithWatermark + ImageViewer |
| 4 | `useCreditEstimate.ts` | PipelineRunView 内联 `estimateCredits()` | 扩展 hook 支持 `type='pipeline'` |
| 5 | `PromptTemplates.vue` 芯片样式 | style_select 用 `el-select` 下拉 | 复用 PromptTemplates 芯片 |
| 6 | `client.ts` token + 401 处理 | usePipelineSSE 自己读 localStorage | 复用 userStore.token |
| 7 | `types/index.ts` 类型集中 | pipeline 类型塞在 api 文件内 | 迁移到 types/index.ts |
| 8 | `permission.ts` RBAC | pipeline 无权限点 | 补全权限点 |

---

## 2. 重构目标与原则

### 2.1 目标

1. **页面立即可用**：修复所有致命 bug，页面可正常访问和操作
2. **深度复用**：最大化复用现有组件/composables/stores，不重复造轮子
3. **符合规范**：严格遵循 AGENTS.md（i18n、CSS 变量、类型集中、权限控制）
4. **渐进式产物可见**：每个步骤完成后即时展示产出，不等最终结果
5. **不破坏现有功能**：image/video/canvas/plaza/chat 功能不受影响

### 2.2 核心原则

1. **优先扩展而非新建**：能用现有 hook/store/组件扩展的，绝不新建
2. **类型集中**：所有 TypeScript 类型放 `types/index.ts`，API 文件只导出请求函数
3. **CSS 变量统一**：全部使用 `--agnes-*` 系列前缀
4. **i18n 全覆盖**：所有用户可见文案走 `t()`，包括状态枚举
5. **权限点显式**：路由 meta + `v-permission` 指令双重控制
6. **不新建转发组件**：所有新组件都有实际逻辑，不做 `<slot />` 透传

### 2.3 范围边界

- **前端整体重写**：WorkshopView、PipelineRunView、PipelineResultView、AssetsView 四个页面全部重写
- **后端只修 cancel bug**：API 路径保留现状（更新设计文档反映实际实现）
- **不动画布模块**：`stores/asset.ts` 重命名为 `canvasAsset.ts`，但画布逻辑不变

---

## 3. 架构变更概览

### 3.1 目录结构变更

```
frontend/src/
├── api/
│   └── pipeline.ts                    # 重写：只保留请求函数，类型迁移到 types/
├── components/
│   ├── pipeline/                      # 新建目录
│   │   ├── PipelineProgress.vue       # 新建：步骤时间线（DAG 多步进度）
│   │   ├── StepResultGallery.vue      # 新建：步骤结果画廊（图片+视频混合）
│   │   ├── StyleSelector.vue          # 新建：风格选择器（复用 PromptTemplates 芯片）
│   │   ├── AssetCard.vue              # 新建：创意资产卡片
│   │   └── AssetDetailModal.vue       # 新建：资产详情弹窗（含版本历史）
│   ├── TaskCard.vue                   # 扩展：支持 source='pipeline' 类型
│   └── ...                            # 其他组件不变
├── composables/
│   ├── useCreditEstimate.ts           # 扩展：新增 type='pipeline' 分支
│   ├── usePipelineSSE.ts              # 重写：复用 userStore.token + client.ts 401 处理
│   └── ...
├── stores/
│   ├── pipeline.ts                    # 重写：只管 templates + currentRun + runHistory
│   ├── styles.ts                      # 新建：风格预设 + 剧本模板缓存
│   ├── asset.ts                       # 重写：创意资产库（character/prop/scene/brand）
│   ├── canvasAsset.ts                 # 重命名自原 asset.ts：画布媒体资源库
│   ├── taskQueue.ts                   # 扩展：新增 registerPipelineTask/updatePipelineTask
│   └── ...
├── types/
│   └── index.ts                       # 扩展：新增 pipeline 相关所有类型
├── views/
│   ├── WorkshopView.vue               # 重写：修复 CSS 变量 + i18n + 使用 pipelineStore
│   ├── PipelineRunView.vue            # 重写：复用 useCreditEstimate + StyleSelector
│   ├── PipelineResultView.vue         # 重写：渐进式产物可见 + 复用新组件
│   └── AssetsView.vue                 # 重写：修复 CSS 变量 + 资产类型 + 复用 AssetCard
└── ...
```

### 3.2 删除/重命名清单

| 操作 | 文件 | 原因 |
|------|------|------|
| 重命名 | `stores/asset.ts` → `stores/canvasAsset.ts` | 释放 asset.ts 名字给创意资产库；明确职责 |
| 重写 | `stores/asset.ts`（新建） | 创意资产库（character/prop/scene/brand） |
| 删除 | `components/pipeline/ResultDisplay.vue`（旧版） | 最终视频展示内联在 PipelineResultView，不再需要独立组件 |
| 修改 | 引用 `stores/asset.ts` 的所有画布文件 | 改为引用 `stores/canvasAsset.ts` |

---

## 4. Store 拆分与 taskQueue 扩展

### 4.1 Store 拆分方案

| Store | 职责 | 数据来源 |
|-------|------|---------|
| `stores/pipeline.ts` | 模板列表、当前运行实例、运行历史 | 后端 API |
| `stores/styles.ts`（新建） | 风格预设列表、剧本模板列表 | 后端 API |
| `stores/asset.ts`（重写） | 创意资产库（character/prop/scene/brand） | 后端 API |
| `stores/canvasAsset.ts`（重命名自原 asset.ts） | 画布媒体资源库（image/video blob） | localforage |

### 4.2 `stores/pipeline.ts`（重写）核心 API

```typescript
export const usePipelineStore = defineStore('pipeline', {
  state: () => ({
    templates: [] as PipelineTemplate[],
    currentRun: null as PipelineRun | null,
    runHistory: [] as PipelineRun[],
    loading: false,
  }),
  actions: {
    async loadTemplates(category?: string),
    async createRun(templateId: number, inputs: Record<string, unknown>),
    async loadRun(runId: number),
    async cancelRun(runId: number),
    async retryRun(runId: number),
    clearAll(),
  }
})
```

**关键约束**：
- `createRun` 内部调用 `taskQueue.registerPipelineTask()` 注册到全局队列
- 不再混入 styles/scriptTemplates（移到 `stores/styles.ts`）

### 4.3 `stores/styles.ts`（新建）核心 API

```typescript
export const useStylesStore = defineStore('styles', {
  state: () => ({
    stylePresets: [] as StylePreset[],
    scriptTemplates: [] as ScriptTemplate[],
    loading: false,
  }),
  actions: {
    // includeUserCreated: false 只加载内置，true 加载用户自定义（修复写死 is_builtin: true 的问题）
    async loadStylePresets(includeUserCreated?: boolean),
    async loadScriptTemplates(),
    clearAll(),
  }
})
```

### 4.4 `stores/asset.ts`（重写）核心 API

```typescript
export const useAssetStore = defineStore('asset', {
  state: () => ({
    assets: [] as Asset[],
    currentAsset: null as Asset | null,
    filter: { type: '', search: '', mine: false } as AssetFilter,
    loading: false,
  }),
  actions: {
    async loadAssets(filter?: AssetListParams),
    async createAsset(data: CreateAssetRequest),
    async saveFromGeneration(generationId: number, data: SaveAssetFromGenerationRequest),
    clearAll(),
  }
})
```

### 4.5 taskQueue 扩展方案

**现状**：`taskQueue.ts` 已有 `registerChatTask`/`updateChatTask`/`registerCanvasTask`/`updateCanvasTask` 的外部任务接入模式。

**扩展**：新增 `registerPipelineTask` + `updatePipelineTask`。

```typescript
// stores/taskQueue.ts 新增
type TaskSource = 'chat' | 'canvas' | 'pipeline' | null

interface PipelineTaskPayload {
  runId: number
  templateName: string
  status: PipelineRunStatus
  progress: number          // 0-1
  currentStep?: string
  totalSteps?: number
  completedSteps?: number
}

function registerPipelineTask(runId: number, templateName: string): void
function updatePipelineTask(runId: number, payload: Partial<PipelineTaskPayload>): void
```

**约束**：
- pipeline 任务不参与 image/video 的并发上限（5 个/类型），pipeline 有自己的并发限制（后端控制）
- pipeline 任务的历史清理复用现有逻辑（5 个 / 20 分钟）
- 不破坏现有 image/video/chat/canvas 任务的展示逻辑

---

## 5. API 路径决策与类型集中

### 5.1 API 路径决策

**决策**：**保留后端现状，更新设计文档反映实际实现**。

理由：
1. 后端骨架已扎实，路径已与前端配套
2. 独立顶级路径（`/api/assets`、`/api/styles`）只是组织美观，无功能价值
3. 用户要求"前端整体重写"，不动后端 API

**需要更新 `01-creative-pipeline-overview.md` 第 8 章的位置**：
- `/api/styles` → `/api/pipeline/styles`
- `/api/assets` → `/api/pipeline/assets`
- `/api/script-templates` → `/api/pipeline/script-templates`
- SSE `/stream` → `/events`
- 模板详情按 `{key}` → 按 `{id}`（保留 `get_template_by_key` 服务方法供内部使用）
- 预估积分 `/estimate` → `/estimate-credits`

### 5.2 `api/pipeline.ts` 重写方案

**现状问题**：9 个类型内联在 api 文件中（违反项目约定）。

**重写后结构**：只导出请求函数，类型从 `types/index.ts` 导入。

```typescript
// frontend/src/api/pipeline.ts（重写）
import { client } from './client'
import type { ... } from '@/types'

// ---------- 模板 ----------
export async function getPipelineTemplates(params?: PipelineTemplateListParams)
export async function getPipelineTemplateDetail(id: number)
export async function estimatePipelineCredits(templateId: number, inputs: Record<string, unknown>)

// ---------- 运行 ----------
export async function createPipelineRun(data: CreateRunRequest)
export async function getPipelineRunDetail(runId: number)
export async function getPipelineRunSteps(runId: number)
export async function retryPipelineRun(runId: number)
export async function retryPipelineStep(runId: number, stepKey: string)
export async function cancelPipelineRun(runId: number)

// ---------- SSE 端点 ----------
export function buildSSEUrl(runId: number): string
// 返回 /api/pipeline/runs/{runId}/events

// ---------- 风格 ----------
export async function getStylePresets()
export async function getStylePresetDetail(id: number)

// ---------- 剧本模板 ----------
export async function getScriptTemplates()
export async function getScriptTemplateDetail(id: number)

// ---------- 资产 ----------
export async function getAssets(params?: AssetListParams)
export async function getAssetDetail(id: number)
export async function saveAssetFromGeneration(data: SaveAssetFromGenerationRequest)
```

### 5.3 `types/index.ts` 类型扩展

所有 pipeline 相关类型追加到 `types/index.ts` 末尾，包括：

- `PipelineStepType`（与后端 step_type 一致：`llm_generate` / `image_batch` / `video_batch` / `ffmpeg_composite` / `tts_generate` / `human_review`）
- `PipelineRunStatus`（`pending` / `running` / `success` / `failed` / `cancelled` / `waiting_review`）
- `PipelineStepStatus`（`pending` / `running` / `success` / `failed` / `skipped` / `waiting_review`）
- `AssetType`（`character` / `prop` / `scene` / `brand`，与后端 `VALID_ASSET_TYPES` 一致）
- `StylePresetCategory`、`PipelineTemplateCategory`、`TemplateInputType`
- `TemplateInput`、`PipelineStepDefinition`、`PipelineTemplate`、`PipelineRun`、`PipelineStep`
- `StylePreset`、`ScriptTemplate`、`Asset`
- 请求参数类型：`CreateRunRequest`、`SaveAssetFromGenerationRequest`、`PipelineTemplateListParams`、`PipelineRunListParams`、`AssetListParams`、`CreditEstimateResult`
- SSE 事件类型：`PipelineSSEEventType`、`PipelineSSEEvent`

### 5.4 useCreditEstimate 扩展

**现状**：`useCreditEstimate.ts`（78 行）只支持 `type: 'image' | 'video'`，调用 `/api/credits/estimate`。

**扩展方案**：

```typescript
type EstimateType = 'image' | 'video' | 'pipeline'

interface EstimateParams {
  type: EstimateType
  request?: Record<string, unknown>   // image/video 用
  templateId?: number                  // pipeline 用
  inputs?: Record<string, unknown>    // pipeline 用
}

export function useCreditEstimate(paramsGetter: () => EstimateParams) {
  // 根据 type 选择 API：
  //   image/video → /api/credits/estimate
  //   pipeline    → /api/pipeline/templates/{templateId}/estimate-credits
  // 其余逻辑（loading/error/refresh/watch/onActivated）全部复用
}
```

**PipelineRunView 改动**：删除内联的 `estimateCredits()`，改用 `useCreditEstimate({ type: 'pipeline', templateId, inputs })`。

---

## 6. 组件复用与新建方案

### 6.1 现有组件复用清单

| 现有组件 | 在 pipeline 中的复用场景 | 改动 |
|---------|------------------------|------|
| `ImageWithWatermark.vue` | StepResultGallery、AssetCard 的图片展示 | 直接使用，零改动 |
| `ImageViewer.vue` | StepResultGallery 点击图片放大查看 | 直接使用，零改动 |
| `ImageUploader.vue` | AssetDetailModal 上传参考图 | 直接使用，零改动 |
| `PromptTemplates.vue` | StyleSelector 风格选择芯片 | 直接使用，零改动 |
| `TaskQueuePanel.vue` | 全局展示 pipeline 运行进度 | 零改动（taskQueue 扩展后自动支持） |
| `TaskCard.vue` | pipeline 任务卡片 | 扩展：支持 `source='pipeline'` 类型 |
| `useDownload.ts` | 下载视频 | 直接使用，零改动 |
| `useCreditEstimate.ts` | 积分预估 | 扩展：新增 `type='pipeline'` 分支 |

### 6.2 新建组件清单

| 组件 | 职责 | 依赖 |
|------|------|------|
| `PipelineProgress.vue` | 步骤时间线（DAG 多步进度展示） | pipelineStore、usePipelineSSE |
| `StepResultGallery.vue` | 步骤结果画廊（图片+视频混合） | ImageWithWatermark、ImageViewer |
| `StyleSelector.vue` | 风格选择器（复用 PromptTemplates 芯片） | PromptTemplates、stylesStore |
| `AssetCard.vue` | 创意资产卡片 | ImageWithWatermark |
| `AssetDetailModal.vue` | 资产详情弹窗（含版本历史） | ImageUploader、assetStore |

**删除**：`components/pipeline/ResultDisplay.vue`（最终视频展示内联在 PipelineResultView，不再需要独立组件）。

### 6.3 组件设计细节

#### 6.3.1 `TaskCard.vue` 扩展

```typescript
function getTaskRoute(task: QueueTask): string {
  if (task.source === 'pipeline') {
    return `/workshop/result/${task.payload.runId}`
  }
  return task.type === 'image' ? '/images' : '/videos'
}

function getStatusBadge(task: QueueTask): { type: string; text: string } {
  if (task.source === 'pipeline') {
    return getPipelineStatusBadge(task.payload.status)
  }
  return getDefaultStatusBadge(task.status)
}
```

#### 6.3.2 `PipelineProgress.vue`（新建）

**Props**：
```typescript
interface Props {
  steps: PipelineStep[]
  currentStepKey?: string
  runStatus: PipelineRunStatus
  selectedStepKey?: string
}
```

**Events**：`select-step(stepKey: string)`、`retry-step(stepKey: string)`

**UI 结构**：
- `el-timeline` 展示每个步骤
- 节点图标按 step_type 显示对应图标（llm_generate→Document，image_batch→Picture，video_batch→VideoPlay）
- 当前运行步骤：动画 loading 图标
- 失败步骤：红色高亮 + 错误信息 + 重试按钮
- 已完成步骤：可点击高亮（selectedStepKey），emit `select-step`

#### 6.3.3 `StepResultGallery.vue`（新建）

**Props**：
```typescript
interface Props {
  step: PipelineStep
}
```

**UI 结构**：
- 根据 `step.step_type` 和 `step.output_data` 智能渲染：
  - `llm_generate`：展示文本结果（剧本内容，支持折叠/展开）
  - `image_batch`：图片网格，复用 `ImageWithWatermark`，点击打开 `ImageViewer`
  - `video_batch`：视频网格，带缩略图 + hover 预览 + 播放按钮
- 空状态：`el-empty`

#### 6.3.4 `StyleSelector.vue`（新建）

```vue
<template>
  <PromptTemplates
    :title="t('pipelineRun.styleSelectorTitle')"
    :templates="styleChips"
    type="style"
    @select="onSelect"
  />
</template>
```

**约束**：不内联实现下拉框，直接复用 PromptTemplates 的芯片 UI。

#### 6.3.5 `AssetCard.vue`（新建）

**Props**：
```typescript
interface Props {
  asset: Asset
  selectable?: boolean
}
```

**Events**：`click(asset)`、`use(asset)`

**UI 结构**：卡片封面（`ImageWithWatermark` 取 `reference_images[0]`）+ 名称 + 类型标签 + 描述 + 操作按钮。

#### 6.3.6 `AssetDetailModal.vue`（新建）

**Props**：
```typescript
interface Props {
  modelValue: boolean
  assetId: number
}
```

**UI 结构**：基本信息 + 视觉描述（可编辑）+ 参考图（`ImageUploader` 上传 + `ImageWithWatermark` 展示）+ 版本历史 + 操作按钮（保存创建新版本、删除）。

### 6.4 组件依赖关系图

```
WorkshopView
  └── TemplateCard（内联在 WorkshopView，简单卡片无需独立组件）

PipelineRunView
  ├── StyleSelector → PromptTemplates（复用）
  └── useCreditEstimate（扩展）

PipelineResultView
  ├── PipelineProgress（新建）
  │   └── 可点击步骤节点 → 切换右侧展示
  ├── StepResultGallery（新建）
  │   ├── ImageWithWatermark（复用）
  │   └── ImageViewer（复用）
  └── usePipelineSSE（重写）

AssetsView
  ├── AssetCard（新建）
  │   └── ImageWithWatermark（复用）
  └── AssetDetailModal（新建）
      ├── ImageUploader（复用）
      └── ImageWithWatermark（复用）
```

### 6.5 关键约束

1. **不新建转发组件**：所有新组件都有实际逻辑
2. **图片展示统一走 ImageWithWatermark**：StepResultGallery、AssetCard 全部复用
3. **图片放大统一走 ImageViewer**：与 HistoryView 体验一致
4. **风格选择复用 PromptTemplates**：不内联 `el-select` 下拉
5. **TaskCard 扩展不破坏现有逻辑**：新增 `source='pipeline'` 分支
6. **新组件全部 scoped CSS + `--agnes-*` 变量**：杜绝 `--text-primary` 等非标准变量

---

## 7. 页面重写方案

### 7.1 `WorkshopView.vue`（重写）

**重写要点**：
1. CSS 变量全部改 `--agnes-*`（`--text-primary` → `--agnes-text-primary` 等）
2. i18n 全覆盖：`categoryLabels` → `t('workshop.category.*')`，`getStatusText` → `t('common.status.*')`
3. 使用 pipelineStore 加载模板列表
4. 权限控制：「使用此模板」按钮加 `v-permission="'pipeline:run'"`

**UI 结构保持**：分类侧边栏 + 搜索框 + 模板卡片网格（现有结构合理，不重构布局）。

### 7.2 `PipelineRunView.vue`（重写）

**重写要点**：
1. 复用 `useCreditEstimate`：删除内联 `estimateCredits()`，改用扩展后的 hook
2. 复用 `StyleSelector`：`style_select` 字段改用 `<StyleSelector v-model="form[field.key]" />`
3. 删除大量 `:deep()` 覆盖（评估是否真的需要，多数情况下 Element Plus 默认样式已够用；必要的覆盖移到全局 CSS）
4. 删除未使用的 `Operation` 图标导入
5. i18n 全覆盖：`getStepTypeLabel` → `t('pipelineRun.stepType.*')`
6. 使用 pipelineStore
7. 权限控制：「启动流水线」按钮加 `v-permission="'pipeline:run'"`

### 7.3 `PipelineResultView.vue`（重写）

**重写要点**：
1. 修复路由 bug：`goBack()` 改为 `router.push('/workshop')`（或 `router.back()`）
2. 统一步骤类型枚举：与后端 `step_type` 完全对齐（`llm_generate/image_batch/video_batch` 等）
3. 拆分组件：步骤时间线抽到 `PipelineProgress.vue`，结果展示抽到 `StepResultGallery.vue`。页面本身只做数据加载、SSE 连接、组件编排
4. i18n 全覆盖：所有硬编码中文 → `t('pipelineResult.*')`
5. 复用 usePipelineSSE（重写后）
6. taskQueue 集成：SSE 收到事件后同步 `taskQueue.updatePipelineTask()`
7. 权限控制：「重试失败步骤」「取消」按钮加 `v-permission="'pipeline:run'"`
8. **渐进式产物可见**：见第 11 节

### 7.4 `AssetsView.vue`（重写）

**重写要点**：
1. 修复资产类型 tab：改为 `all/character/prop/scene/brand`，与后端 `VALID_ASSET_TYPES` 一致
2. CSS 变量全部改 `--agnes-*`
3. 使用 assetStore：不再直接调 `getAssets()`
4. 复用 AssetCard + AssetDetailModal
5. i18n 全覆盖：`getTypeLabel` → `t('assets.type.*')`
6. 权限控制：「创建资产」「编辑资产」按钮加 `v-permission="'pipeline:save_asset'"`（编辑需额外检查 `asset.user_id === currentUser.id`）

---

## 8. 权限点设计

### 8.1 权限点清单

| 权限点 | 说明 | admin | moderator | user |
|--------|------|-------|-----------|------|
| `pipeline:run` | 运行流水线、取消、重试 | ✓ | ✓ | ✓ |
| `pipeline:save_asset` | 保存到自己的资产库、创建/编辑/删除自己的资产 | ✓ | ✓ | ✓ |
| `pipeline:manage_templates` | 创建/编辑/删除模板（内置和自定义） | ✓ | ✗ | ✗ |
| `pipeline:manage_styles` | 创建/编辑/删除风格预设和剧本模板 | ✓ | ✗ | ✗ |

### 8.2 实现位置

**`stores/permission.ts`** 扩展 `ROLE_PERMISSIONS`：

```typescript
const ROLE_PERMISSIONS: Record<string, string[]> = {
  admin: ['*'],
  moderator: [
    'plaza:moderate', 'moderation:config', 'content:generate', 'plaza:share',
    'pipeline:run', 'pipeline:save_asset',
  ],
  user: [
    'content:generate', 'plaza:share',
    'pipeline:run', 'pipeline:save_asset',
  ],
}
```

**`router/index.ts`** 路由 meta 加 `permission`：

```typescript
{ path: '/workshop', meta: { requiresAuth: true, permission: 'pipeline:run' } },
{ path: '/workshop/run/:templateId', meta: { requiresAuth: true, permission: 'pipeline:run' } },
{ path: '/workshop/result/:runId', meta: { requiresAuth: true, permission: 'pipeline:run' } },
{ path: '/assets', meta: { requiresAuth: true, permission: 'pipeline:save_asset' } },
```

**组件内**用 `v-permission` 指令控制按钮显示。资源所有权操作需额外检查 `asset.user_id === currentUser.id`。

---

## 9. i18n 命名空间设计

### 9.1 命名空间结构

```typescript
// frontend/src/i18n/zh-CN.ts 补全

common: {
  status: {
    pending: '等待中',
    running: '运行中',
    success: '已完成',
    failed: '失败',
    cancelled: '已取消',
    waiting_review: '待审核',
    skipped: '已跳过',
  },
  actions: {
    confirm: '确认', cancel: '取消', retry: '重试',
    save: '保存', delete: '删除', download: '下载',
    copyLink: '复制链接', preview: '预览', detail: '详情',
  },
},

workshop: {
  title: '创意工坊',
  subtitle: '选择模板，一键生成完整作品',
  searchPlaceholder: '搜索模板...',
  category: { all: '全部', drama: '剧情类', ad: '广告类', education: '科普类', art: '艺术类', comic: '漫画类', commercial: '商业类' },
  template: {
    useCount: '已使用 {count} 次',
    steps: '{count} 个步骤',
    estimateCredits: '约 {credits} 积分',
    estimateTime: '约 {minutes} 分钟',
    use: '使用此模板',
  },
  recentRuns: { title: '最近运行', empty: '暂无运行记录' },
},

pipelineRun: {
  title: '配置并运行',
  back: '返回',
  templateInfo: '模板信息',
  parameters: '参数配置',
  estimate: {
    title: '积分预估',
    total: '预计消耗 {credits} 积分',
    insufficient: '积分不足，当前剩余 {credits} 积分',
    loading: '预估中...',
  },
  styleSelectorTitle: '选择视觉风格',
  start: '启动流水线',
  confirmStart: '确认启动？预计消耗 {credits} 积分',
  stepType: {
    llm_generate: 'LLM 剧本生成',
    image_batch: '图片批量生成',
    video_batch: '视频批量生成',
    ffmpeg_composite: '视频合成',
    tts_generate: '配音生成',
    human_review: '人工审核',
  },
},

pipelineResult: {
  title: '运行详情',
  back: '返回工坊',
  runInfo: '运行 #{id} · 创建于 {time}',
  retryStep: '重试失败步骤',
  retryConfirm: '确认重试失败步骤吗？',
  retrySuccess: '已重新开始执行',
  retryStepSuccess: '已重试步骤: {step}',
  retryStepFailed: '重试步骤失败: {error}',
  loadFailed: '加载流水线状态失败',
  resultTitle: '生成结果',
  saveToAsset: '保存到资产库',
  noResult: '暂无结果数据',
  duration: '时长 {seconds} 秒',
  steps: {
    total: '共 {total} 步',
    completed: '已完成 {completed}/{total}',
    allCompleted: '所有步骤已完成，共耗时 {duration}',
    error: '执行过程中遇到错误',
    running: '流水线正在执行中',
    preparing: '正在准备执行环境',
  },
  sse: {
    connecting: '连接中',
    connected: '实时连接',
    reconnecting: '重连中',
    polling: '轮询中',
  },
  stepStatus: {
    pending: '等待中',
    running: '正在生成',
    success: '生成完成',
    failed: '生成失败',
    cancelled: '已取消',
    skipped: '已跳过',
    processing: '处理中',
  },
},

assets: {
  title: '我的资产库',
  subtitle: '管理可复用的角色、场景、风格',
  type: { all: '全部', character: '角色', prop: '道具', scene: '场景', brand: '品牌' },
  searchPlaceholder: '搜索资产...',
  empty: '暂无资产',
  createAsset: '创建资产',
  editAsset: '编辑资产',
  deleteConfirm: '确认删除此资产吗？',
  saveFromGeneration: '保存到资产库',
  fields: {
    name: '名称', type: '类型', description: '描述',
    visualDescription: '视觉描述', referenceImages: '参考图',
    tags: '标签', version: '版本', useCount: '使用次数',
  },
  useTip: '在生成中使用',
},
```

**英文版 `en-US.ts` 同步补全对应 key**。

### 9.2 关键约束

1. **状态枚举复用**：`common.status.*` 命名空间跨页面共用
2. **步骤类型枚举统一**：前后端对齐 `llm_generate/image_batch/video_batch/ffmpeg_composite/tts_generate/human_review`
3. **零硬编码中文**：所有用户可见文案走 `t()`

---

## 10. SSE 重写与数据流

### 10.1 usePipelineSSE 重写方案

**现状问题**（418 行）：
1. 拼写错误 `manuallClosed`（6 处）
2. 硬编码 token key `localStorage.getItem('agnes.platform.auth.token')`
3. 401 处理与 client.ts 不一致
4. 错误提示硬编码中文
5. SSE URL 构造内联

**重写要点**：

1. **token 复用 userStore**：
```typescript
import { useUserStore } from '@/stores/user'
const userStore = useUserStore()
const token = computed(() => userStore.token)
```

2. **401 处理对齐 client.ts**：SSE 收到 401 时，调用 `userStore.logout()` + `router.push('/login')` + `dispatch('agnes:user-logout')`。

3. **SSE URL 复用 api 函数**：
```typescript
import { buildSSEUrl } from '@/api/pipeline'
const url = buildSSEUrl(runId)
```

4. **修复拼写错误**：`manuallClosed` → `manualClosed`

5. **i18n 全覆盖**：错误提示走 `t('pipelineResult.sse.*')`

6. **保留核心逻辑**：SSE 事件解析 + 指数退避重连（最多 20 次）+ 10 秒轮询兜底 + 页面卸载清理

### 10.2 历史回流方案

**现状**：pipeline 生成的图片/视频写入 generations 表（后端 `integration.save_batch_generations` 已实现），但前端 HistoryView 看不到。

**前端改动**：SSE 收到 `step_completed` 事件后，触发历史刷新信号：

```typescript
import { useTaskQueueStore } from '@/stores/taskQueue'
const taskQueue = useTaskQueueStore()

function handleStepCompleted(event) {
  // 更新 pipelineStore.currentRun
  // 同步 taskQueue.updatePipelineTask
  // 触发历史刷新信号，让 HistoryView 能看到新生成的图片/视频
  taskQueue.triggerHistoryRefresh()
}
```

**后端依赖**：已实现，前端无需额外改动。HistoryView 通过现有 `getHistoryList()` API 自动看到 pipeline 产出。

### 10.3 TaskQueue 协作流程

```
用户点击「启动流水线」
    ↓
PipelineRunView.createRun()
    ↓
pipelineStore.createRun(templateId, inputs)
    ↓ POST /api/pipeline/runs → 后端创建 run + 步骤 + 启动执行引擎 → 返回 run_id
    ↓
pipelineStore.currentRun = run
taskQueue.registerPipelineTask(run.id, templateName)  ← 注册到全局队列
    ↓ 跳转 /workshop/result/{runId}
    ↓
PipelineResultView 挂载 → usePipelineSSE.start() → 建立 SSE 连接
    ↓
后端推送事件
    ↓
usePipelineSSE.handleEvent(event)
    ├→ pipelineStore.updateRunFromEvent(event)   ← 更新 currentRun
    ├→ taskQueue.updatePipelineTask(runId, ...)   ← 同步全局队列
    └→ if step_completed: taskQueue.triggerHistoryRefresh()  ← 触发历史刷新
    ↓
全局 TaskQueuePanel 自动响应 → 显示 pipeline 任务进度（点击跳转 /workshop/result/{runId}）
    ↓
HistoryView 自动响应 → watch historyRefreshSignal → 刷新列表 → 显示 pipeline 产出的图片/视频
```

---

## 11. 渐进式产物可见性

### 11.1 核心原则

**流程的每个阶段的产品都是可见的，不要让用户最后才见到产物。**

每个步骤完成后立即展示该步骤的产出，用户不需要等到全流程结束才看到结果。

### 11.2 UI 布局（PipelineResultView）

```
┌─────────────────────────────────────────────────────┐
│  顶部：运行信息 + 状态徽章 + 进度条 + SSE 连接状态    │
├──────────────────┬──────────────────────────────────┤
│ 左侧：步骤时间线   │ 右侧：当前选中步骤的产出展示      │
│                   │                                  │
│ ● 剧本生成 ✓      │  ┌────────────────────────────┐  │
│   (点击查看)       │  │  StepResultGallery        │  │
│ ● 角色设计 ✓      │  │  - 文本结果（剧本内容）    │  │
│   (点击查看)       │  │  - 图片网格（角色图）      │  │
│ ● 分镜绘制 🔄      │  │  - 视频网格（分镜视频）    │  │
│   (运行中)         │  │                            │  │
│ ○ 视频生成 ⏳      │  └────────────────────────────┘  │
│   (等待中)         │                                  │
├──────────────────┴──────────────────────────────────┤
│ 底部：最终结果区（仅当最终合成步骤完成后显示）        │
└─────────────────────────────────────────────────────┘
```

### 11.3 关键交互逻辑

1. **步骤时间线可点击**：每个已完成步骤点击后在右侧展示 `StepResultGallery`
2. **自动切换焦点**：SSE 收到 `step_completed` 事件后，自动切换右侧展示该步骤产出（高亮该步骤节点）
3. **运行中步骤展示进度**：当前运行中的步骤在右侧展示进度条 + "正在生成 3/5" 等状态
4. **底部最终结果区**：仅当存在最终视频（ffmpeg_composite 步骤完成，或 output_summary 含 video_url）时显示
5. **未启动状态**：流水线刚启动时，右侧展示"正在准备执行环境"占位

### 11.4 代码实现

```typescript
// PipelineResultView.vue
const selectedStepKey = ref<string>('')

// SSE 收到 step_completed 后自动切换
function handleStepCompleted(event) {
  selectedStepKey.value = event.step_key
  taskQueue.triggerHistoryRefresh()
}

// 点击时间线节点切换
function handleStepClick(stepKey: string) {
  selectedStepKey.value = stepKey
}

const selectedStep = computed(() =>
  steps.value.find(s => s.step_key === selectedStepKey.value)
)
```

### 11.5 删除 ResultDisplay 组件

**决策**：删除 `components/pipeline/ResultDisplay.vue`。

理由：
1. 最终视频展示逻辑简单（video + 下载 + 保存到资产），内联在 PipelineResultView 即可
2. 中间步骤结果由 `StepResultGallery` 负责
3. 减少一层不必要的组件抽象

---

## 12. 后端修复

### 12.1 cancel() 方法 bug 修复（已完成）

**问题**：`engine.py` 的 `cancel()` 方法三处致命 bug：
1. `STATUS_WAITING_APPROVAL` 未定义（应为 `STATUS_WAITING_REVIEW`）
2. `run.precharged_credits` 字段不存在（`PipelineRun` 模型无此列）
3. `refund_credits` 调用签名错误（多传了 `amount` 位置参数，且 `reason` 同时以位置和关键字传递）

**修复方案**（已实施）：
- 使用已定义的 `STATUS_WAITING_REVIEW` 常量
- 删除对 `run.precharged_credits` 的引用
- 直接调用 `refund_credits(db, user_id, ref_id, reason="流水线取消退款")`，对齐实际签名

### 12.2 更新设计文档

更新 `docs/01-creative-pipeline-overview.md` 第 8 章 API 路径，反映后端实际实现：
- `/api/styles` → `/api/pipeline/styles`
- `/api/assets` → `/api/pipeline/assets`
- `/api/script-templates` → `/api/pipeline/script-templates`
- SSE `/stream` → `/events`
- 模板详情按 `{key}` → 按 `{id}`
- 预估积分 `/estimate` → `/estimate-credits`

---

## 13. 实施顺序

### Phase 1：后端修复（已完成）
- [x] 修复 `engine.py` 的 `cancel()` 方法三处 bug

### Phase 2：基础设施扩展
1. 扩展 `types/index.ts`：新增 pipeline 相关所有类型
2. 重写 `api/pipeline.ts`：类型迁移到 types，只保留请求函数
3. 扩展 `useCreditEstimate.ts`：新增 `type='pipeline'` 分支
4. 重命名 `stores/asset.ts` → `stores/canvasAsset.ts`，更新所有引用
5. 扩展 `stores/permission.ts`：新增 pipeline 权限点
6. 扩展 `stores/taskQueue.ts`：新增 `registerPipelineTask`/`updatePipelineTask`
7. 扩展 `TaskCard.vue`：支持 `source='pipeline'` 类型

### Phase 3：Store 重写
1. 重写 `stores/pipeline.ts`：只管 templates + currentRun + runHistory
2. 新建 `stores/styles.ts`：风格预设 + 剧本模板
3. 重写 `stores/asset.ts`：创意资产库（character/prop/scene/brand）

### Phase 4：组件新建
1. 新建 `components/pipeline/PipelineProgress.vue`
2. 新建 `components/pipeline/StepResultGallery.vue`
3. 新建 `components/pipeline/StyleSelector.vue`
4. 新建 `components/pipeline/AssetCard.vue`
5. 新建 `components/pipeline/AssetDetailModal.vue`
6. 删除 `components/pipeline/ResultDisplay.vue`（旧版）

### Phase 5：composable 重写
1. 重写 `composables/usePipelineSSE.ts`：复用 userStore.token + client.ts 401 处理 + i18n + 修复拼写

### Phase 6：页面重写
1. 重写 `views/WorkshopView.vue`：CSS 变量 + i18n + pipelineStore
2. 重写 `views/PipelineRunView.vue`：useCreditEstimate + StyleSelector + 删除 :deep 覆盖
3. 重写 `views/PipelineResultView.vue`：渐进式产物可见 + PipelineProgress + StepResultGallery
4. 重写 `views/AssetsView.vue`：CSS 变量 + 资产类型 + assetStore + AssetCard

### Phase 7：i18n 与权限补全
1. 补全 `i18n/zh-CN.ts`：common.status.* + workshop + pipelineRun + pipelineResult + assets
2. 补全 `i18n/en-US.ts`：对应英文 key
3. 路由 meta 加 `permission` 字段

### Phase 8：设计文档更新
1. 更新 `docs/01-creative-pipeline-overview.md` 第 8 章 API 路径
2. 更新 `docs/02-creative-pipeline-todolist.md` 标记完成状态

---

## 14. 验收标准

### 14.1 功能验收
- [ ] WorkshopView 页面样式正常显示（CSS 变量生效）
- [ ] WorkshopView 模板卡片「使用」按钮可点击跳转
- [ ] PipelineRunView 积分预估复用 useCreditEstimate
- [ ] PipelineRunView 风格选择复用 StyleSelector（PromptTemplates 芯片）
- [ ] PipelineResultView 返回按钮正常跳转 /workshop
- [ ] PipelineResultView 步骤类型标签正确显示（llm_generate/image_batch/video_batch）
- [ ] PipelineResultView 每个步骤完成后即时展示产出（渐进式可见）
- [ ] PipelineResultView 底部最终结果区仅在有最终视频时显示
- [ ] AssetsView 资产类型 tab 为 all/character/prop/scene/brand
- [ ] AssetsView 使用 assetStore 加载数据
- [ ] AssetsView 卡片图片有水印（复用 ImageWithWatermark）

### 14.2 集成验收
- [ ] pipeline 运行注册到全局 TaskQueuePanel
- [ ] TaskCard 显示 pipeline 任务进度，点击跳转 /workshop/result/{runId}
- [ ] SSE 收到 step_completed 后触发 historyRefreshSignal
- [ ] HistoryView 能看到 pipeline 生成的图片/视频
- [ ] usePipelineSSE 复用 userStore.token，401 处理对齐 client.ts

### 14.3 规范验收
- [ ] 所有页面 CSS 变量使用 `--agnes-*` 前缀
- [ ] 所有页面文案走 i18n（零硬编码中文）
- [ ] 所有 pipeline 类型在 `types/index.ts`
- [ ] api/pipeline.ts 只导出请求函数，不内联类型
- [ ] 路由 meta 含 `permission` 字段
- [ ] 组件内用 `v-permission` 指令控制按钮显示
- [ ] 新组件全部 scoped CSS
- [ ] `manuallClosed` 拼写错误已修复

### 14.4 不破坏现有功能
- [ ] 画布模块功能正常（canvasAsset 重命名后）
- [ ] image/video 生成功能正常
- [ ] chat 功能正常
- [ ] plaza 广场功能正常
- [ ] TaskQueue 现有 image/video/chat/canvas 任务展示正常

---

*文档结束*
