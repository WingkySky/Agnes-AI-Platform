# 创意流水线前端重构 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构创意流水线前端四个页面 + 基础设施，修复致命 bug，深度复用现有组件/composables/stores，实现渐进式产物可见性。

**Architecture:** Store 拆分（pipeline/styles/asset 三分离）+ taskQueue 扩展支持 pipeline + 新建 5 个 pipeline 组件 + 重写 usePipelineSSE + 四页面重写。后端 cancel bug 已修复（Phase 1 完成）。

---

## 状态追踪（2026-06-26 更新）

### 本轮会话已完成的**后端稳定性修复**（非本计划前端任务，但为前端重构前提）

| 修复 | 文件 | 说明 |
|------|------|------|
| [DONE] TTS 三级容错 | `backend/.../tts_generate.py` | 预验证→在线重试→pyttsx3 兜底 + error_type 分类 |
| [DONE] 可选依赖支持 | `backend/.../engine.py` | optional_depends_on + _poll_step_progress 轮询 + all-failed 分类 |
| [DONE] 模板 TTS 条件 | `backend/.../seed_pipeline_data.py` | enable_tts 输入、condition 表达式、optional_depends_on |
| [DONE] 字幕烧录兜底 | `backend/.../ffmpeg_composite.py` | drawtext 检测 + 外挂 SRT 兜底 + 错误日志智能提取 |
| [DONE] 服务重启去抖 | `backend/start.sh` | --reload-delay 3 |
| [DONE] 数据库模板修正 | `pipeline_templates` 表 | default_voice→XiaoxiaoNeural，condition/optional_depends_on 生效 |

### 前端计划任务进度概览（2026-06-26 最终盘点）

| Phase | 任务数 | 状态 |
|-------|--------|------|
| Phase 2: 基础设施扩展 | Task 1-7 | **[DONE]** — 类型/API/Composable/Store/TaskCard 全部就位 |
| Phase 3: Store 重写 | Task 8-10 | **[DONE]** — styles.ts / pipeline.ts / asset.ts 全部就位 |
| Phase 4: 组件新建 | Task 11-15 | **[DONE]** — 6 个组件已创建（含超计划的 FinalVideoPlayer/SubtitleEditor/TimelinePreview），ResultDisplay 已删除 |
| Phase 5: Composable | Task 16 | **[DONE]** — 全面完成：userStore.token、401 对齐、buildSSEUrl 复用、manualClosed 拼写修正、P1 轮询节流+指数退避 |
| Phase 6: 页面重写 | Task 17-20 | **[DONE]** — 四页面 CSS 变量 --agnes-* + i18n + 权限全量覆盖 |
| Phase 7: i18n | Task 21-23 | **[DONE]** — zh-CN/en-US 补全 + router meta permission |
| Phase 8: 文档 | Task 24-25 | **[DONE]** — API 路径修正 + todolist 标记 |

**结论：开发计划 25 个前端任务全部已完成。** 本轮会话额外完成了 6 项后端稳定性修复（见上表），为前端重构后的稳定运行提供了关键保障。

**Tech Stack:** Vue 3 + Element Plus + Pinia + Vue Router + localforage + i18n

**Spec:** [docs/03-pipeline-frontend-refactor-design.md](../../03-pipeline-frontend-refactor-design.md)

**关键修正（基于代码调研，覆盖 spec 中的类型命名）**：
- spec 设计的类型用 camelCase（如 `estimatedCredits`），但现有后端 API 返回 snake_case（如 `estimated_credits`），现有 api/pipeline.ts 类型也用 snake_case。**计划中保持 snake_case**，与后端和现有代码一致，不引入转换层。
- spec 中 `types/index.ts` 的 `QueueTask.source` 字段扩展点：实际在 `types/index.ts:501`，当前是 `source?: 'chat' | 'canvas' | null`，需加 `'pipeline'`。
- spec 中 `v-permission` 指令位置：实际在 `directives/permission.ts`（非 stores/permission.ts），但 `ROLE_PERMISSIONS` 在 `stores/permission.ts:12-16`。
- spec 中 TaskCard 的 `getTaskRoute`/`getStatusBadge` 函数实际不存在，需新增。
- `stores/asset.ts` 的 defineStore ID 是 `'asset'`，重命名为 `canvasAsset.ts` 时**保留 store id `'asset'`** 避免破坏 localforage 已存数据。

**项目约束（来自 AGENTS.md，覆盖 skill 默认行为）**：
- 不强制 TDD，不执行构建/语法检查（用户自己做）
- commit 步骤标注为「可选」— 系统约定 NEVER commit unless user asks
- 每次写完代码不需要检查语法

---

## 文件结构总览

### 新建文件
| 路径 | 职责 |
|------|------|
| `frontend/src/stores/styles.ts` | 风格预设 + 剧本模板 store |
| `frontend/src/stores/canvasAsset.ts` | 重命名自 asset.ts（画布资源库） |
| `frontend/src/components/pipeline/PipelineProgress.vue` | 步骤时间线 |
| `frontend/src/components/pipeline/StepResultGallery.vue` | 步骤结果画廊 |
| `frontend/src/components/pipeline/StyleSelector.vue` | 风格选择器 |
| `frontend/src/components/pipeline/AssetCard.vue` | 资产卡片 |
| `frontend/src/components/pipeline/AssetDetailModal.vue` | 资产详情弹窗 |

### 修改文件
| 路径 | 修改内容 |
|------|---------|
| `frontend/src/types/index.ts` | 末尾追加 pipeline 类型 + QueueTask.source 扩展 |
| `frontend/src/api/pipeline.ts` | 类型迁移到 types，只保留请求函数 + 新增 buildSSEUrl |
| `frontend/src/composables/useCreditEstimate.ts` | 扩展 type='pipeline' 分支 |
| `frontend/src/stores/pipeline.ts` | 移除 styles/scriptTemplates，重写 createRun |
| `frontend/src/stores/asset.ts` | 重写为创意资产库 |
| `frontend/src/stores/taskQueue.ts` | 新增 registerPipelineTask/updatePipelineTask |
| `frontend/src/stores/permission.ts` | ROLE_PERMISSIONS 加 pipeline 权限点 |
| `frontend/src/components/TaskCard.vue` | 支持 source='pipeline' |
| `frontend/src/composables/usePipelineSSE.ts` | 重写：复用 userStore.token + 401 对齐 |
| `frontend/src/router/index.ts` | pipeline 路由 meta 加 permission |
| `frontend/src/i18n/zh-CN.ts` | 补全 pipeline i18n key + 权限点展示 |
| `frontend/src/i18n/en-US.ts` | 对应英文 key |
| `frontend/src/views/WorkshopView.vue` | CSS 变量 + i18n + pipelineStore |
| `frontend/src/views/PipelineRunView.vue` | useCreditEstimate + StyleSelector |
| `frontend/src/views/PipelineResultView.vue` | 渐进式产物可见 + 新组件 |
| `frontend/src/views/AssetsView.vue` | CSS 变量 + 资产类型 + assetStore |
| `frontend/src/views/CanvasView.vue` | import 路径改 canvasAsset（3 处） |
| `frontend/src/components/canvas/CanvasAssetLibrary.vue` | import 路径改 canvasAsset |

### 删除文件
| 路径 | 原因 |
|------|------|
| `frontend/src/components/pipeline/ResultDisplay.vue` | 最终视频展示内联到 PipelineResultView |

---

## Phase 2: 基础设施扩展

### Task 1: 扩展 types/index.ts — 新增 pipeline 类型

**Files:**
- Modify: `frontend/src/types/index.ts`（末尾追加 + 行 501 修改 QueueTask.source）

- [x] **Step 1: 在 types/index.ts 行 501 修改 QueueTask.source 支持 pipeline** [DONE] 2026-06-25

找到 `frontend/src/types/index.ts` 中 `QueueTask` 接口的 `source` 字段（约第 501 行）：

```typescript
// 修改前
source?: 'chat' | 'canvas' | null

// 修改后
source?: 'chat' | 'canvas' | 'pipeline' | null
```

- [x] [DONE] 2026-06-25 **Step 2: 在 types/index.ts 末尾追加 pipeline 类型章节**

在文件末尾追加：

```typescript

// =====================================================
// 创意流水线（Creative Pipeline）类型
// 注意：字段命名保持 snake_case，与后端 API 返回一致
// =====================================================

/** 流水线步骤类型（与后端 steps/*.py 的 step_type 一致） */
export type PipelineStepType =
  | 'llm_generate'
  | 'image_batch'
  | 'video_batch'
  | 'ffmpeg_composite'
  | 'tts_generate'
  | 'human_review'

/** 流水线运行状态 */
export type PipelineRunStatus =
  | 'pending' | 'running' | 'success' | 'failed' | 'cancelled' | 'waiting_review'

/** 步骤状态 */
export type PipelineStepStatus =
  | 'pending' | 'running' | 'success' | 'failed' | 'skipped' | 'waiting_review'

/** 资产类型（与后端 VALID_ASSET_TYPES 一致） */
export type AssetType = 'character' | 'prop' | 'scene' | 'brand'

/** 流水线输入配置项 */
export interface PipelineInputConfig {
  key: string
  label: string
  type: 'text' | 'number' | 'style_select' | 'boolean' | 'select' | 'textarea' | 'image_upload'
  required?: boolean
  default?: any
  placeholder?: string
  min?: number
  max?: number
  description?: string
  options?: Array<{ label: string; value: any }>
}

/** 流水线模板 */
export interface PipelineTemplate {
  id: number
  key: string
  name: string
  description: string
  category: string
  thumbnail: string
  estimated_credits: number
  estimated_time: string
  estimated_time_minutes?: number
  is_builtin: boolean
  inputs_config: PipelineInputConfig[]
  steps_config: any[]
  tags: string[]
  created_at: string
  updated_at: string
}

/** 流水线运行实例 */
export interface PipelineRun {
  id: number
  template_id: number
  template_name?: string
  name: string
  status: PipelineRunStatus | string
  total_credits: number
  inputs: Record<string, any>
  current_step: string | null
  current_step_key?: string
  progress: number
  error_message: string | null
  output_summary?: Record<string, any>
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

/** 步骤执行记录 */
export interface PipelineStep {
  id: number
  run_id: number
  step_key: string
  name: string
  step_type: PipelineStepType | string
  status: PipelineStepStatus | string
  depends_on: string[]
  sort_order: number
  output_data: Record<string, any>
  input_data?: Record<string, any>
  error_message: string | null
  retry_count: number
  max_retries: number
  timeout_sec?: number
  credits_consumed: number
  started_at: string | null
  finished_at: string | null
  created_at: string
}

/** 风格预设 */
export interface StylePreset {
  id: number
  key: string
  name: string
  category: string
  description: string
  visual_prefix: string
  lighting: string
  color_palette: string
  quality_suffix: string
  negative_prompt: string
  camera_language: string
  mood_keywords: string
  preview_image: string
  tags: string[]
  is_builtin: boolean
  is_public?: boolean
  use_count: number
  created_at: string
}

/** 剧本模板 */
export interface ScriptTemplate {
  id: number
  key: string
  name: string
  category: string
  structure: string
  description: string
  prompt_template: string
  scenes_min: number
  scenes_max: number
  default_scene_duration: number
  tags: string[]
  is_builtin: boolean
  created_at: string
}

/** 创意资产（流水线资产库，区别于画布素材库 AssetItem） */
export interface Asset {
  id: number
  type: AssetType | string
  name: string
  description: string
  visual_description: string
  reference_images: string[]
  style_id: number | null
  user_id: number | null
  is_public: boolean
  tags: string[]
  version: number
  parent_id?: number | null
  moderation_status?: string
  likes_count?: number
  views_count?: number
  use_count?: number
  created_at: string
  updated_at: string
}

/** 积分预估结果 */
export interface CreditEstimateResult {
  estimated_total: number
  breakdown: Array<{
    step_key: string
    step_name: string
    step_type: string
    estimated_credits: number
  }>
  note: string
}

/** 创建运行请求 */
export interface CreateRunRequest {
  template_id: number
  inputs: Record<string, any>
  name?: string
}

/** 从生成结果保存到资产库 */
export interface SaveAssetFromGenerationRequest {
  generation_id: number
  type: AssetType | string
  name: string
  description?: string
  visual_description?: string
  style_id?: number
  tags?: string[]
}

/** 列表查询参数 */
export interface PipelineListParams {
  page?: number
  page_size?: number
  category?: string
  search?: string
  is_builtin?: boolean
}

/** 列表返回结果 */
export interface ListResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/** SSE 事件类型 */
export type PipelineSSEEventType =
  | 'state_snapshot' | 'pipeline_started' | 'step_started'
  | 'step_progress' | 'step_completed' | 'step_failed'
  | 'step_skipped' | 'pipeline_completed' | 'pipeline_failed'

/** pipeline 任务注册参数（taskQueue 用） */
export interface RegisterPipelineTaskParams {
  runId: number
  templateName: string
}

/** pipeline 任务更新参数（taskQueue 用） */
export interface UpdatePipelineTaskParams {
  status?: PipelineRunStatus | string
  progress?: number
  currentStep?: string
  totalSteps?: number
  completedSteps?: number
}
```

- [x] [DONE] 2026-06-25 **Step 3:（可选）提交**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): 新增创意流水线相关类型定义"
```

---

### Task 2: 重写 api/pipeline.ts — 类型迁移 + 新增 buildSSEUrl

**Files:**
- Modify: `frontend/src/api/pipeline.ts`（删除行 12-175 类型定义，改为 import；新增 buildSSEUrl）

- [x] [DONE] 2026-06-25 **Step 1: 删除 api/pipeline.ts 行 12-175 的所有内联类型定义，改为从 types 导入**

将 `frontend/src/api/pipeline.ts` 开头（行 1-175）替换为：

```typescript
/* =====================================================
 * 创意流水线相关 API 封装
 * - 模板列表/详情
 * - 流水线创建/启动/查询/取消/重试
 * - 步骤查询/单步重试
 * - 风格预设、剧本模板、资产库
 * - 积分预估
 * 类型定义已迁移到 @/types，本文件只保留请求函数
 * ===================================================== */

import client from './client'
import type {
  PipelineTemplate,
  PipelineRun,
  PipelineStep,
  StylePreset,
  ScriptTemplate,
  Asset,
  CreditEstimateResult,
  CreateRunRequest,
  SaveAssetFromGenerationRequest,
  PipelineListParams,
  ListResult,
} from '@/types'

// re-export 类型，方便使用方从 api 文件统一导入（向后兼容）
export type {
  PipelineTemplate,
  PipelineRun,
  PipelineStep,
  StylePreset,
  ScriptTemplate,
  Asset,
  CreditEstimateResult,
  CreateRunRequest,
  SaveAssetFromGenerationRequest,
  PipelineListParams,
  ListResult,
}
```

保留行 177 以后的所有 API 函数不变（getPipelineTemplates、createPipelineRun 等）。

- [x] [DONE] 2026-06-25 **Step 2: 新增 buildSSEUrl 函数**

在 api/pipeline.ts 的「运行」API 区域（cancelPipelineRun 函数之后）追加：

```typescript
// ---------- SSE 端点 ----------

/** 构造 SSE 订阅 URL */
export function buildSSEUrl(runId: number): string {
  return `/api/pipeline/runs/${runId}/events`
}
```

- [x] [DONE] 2026-06-25 **Step 3:（可选）提交**

```bash
git add frontend/src/api/pipeline.ts
git commit -m "refactor(api): pipeline 类型迁移到 types，新增 buildSSEUrl"
```

---

### Task 3: 扩展 useCreditEstimate.ts — 支持 type='pipeline'

**Files:**
- Modify: `frontend/src/composables/useCreditEstimate.ts`（行 18-26 扩展 EstimateParamsGetter + 行 51 分支调用）

- [x] [DONE] 2026-06-25 **Step 1: 扩展 EstimateParamsGetter 支持 pipeline**

修改 `frontend/src/composables/useCreditEstimate.ts` 行 15-26：

```typescript
// 修改前
import { ref, watch, onActivated } from 'vue'
import { estimateCost, type CreditEstimateResponse } from '@/api/credits'

/** 积分预估参数（响应式 getter，便于依赖响应式数据） */
export interface EstimateParamsGetter {
  (): {
    type: 'image' | 'video'
    mode?: string
    size?: string
    seconds?: number
    num_frames?: number
  }
}

// 修改后
import { ref, watch, onActivated } from 'vue'
import { estimateCost, type CreditEstimateResponse } from '@/api/credits'
import { estimatePipelineCredits } from '@/api/pipeline'

/** 积分预估参数（响应式 getter，便于依赖响应式数据） */
export interface EstimateParamsGetter {
  (): {
    type: 'image' | 'video' | 'pipeline'
    // image/video 用
    mode?: string
    size?: string
    seconds?: number
    num_frames?: number
    // pipeline 用
    templateId?: number
    inputs?: Record<string, unknown>
  }
}
```

- [x] [DONE] 2026-06-25 **Step 2: 修改 refresh 函数，按 type 分支调用 API**

修改 `frontend/src/composables/useCreditEstimate.ts` 行 41-64 的 refresh 函数：

```typescript
  /** 重新拉取预估扣费 */
  async function refresh() {
    const params = paramsGetter()
    if (!params || !params.type) {
      cost.value = null
      return
    }
    const myId = ++reqId
    loading.value = true
    error.value = null
    try {
      let data: CreditEstimateResponse
      if (params.type === 'pipeline') {
        // pipeline 走专用预估接口
        if (!params.templateId) {
          cost.value = null
          return
        }
        const result = await estimatePipelineCredits(params.templateId, params.inputs || {})
        // pipeline 预估返回 { estimated_total, sufficient }，适配为 CreditEstimateResponse 结构
        data = {
          cost: result.estimated_total,
          sufficient: true, // pipeline 预估不返回 sufficient，默认 true，由后端创建时再校验
        } as CreditEstimateResponse
      } else {
        // image/video 走通用预估接口
        data = await estimateCost(params)
      }
      // 避免竞态：仅采用最新一次请求的结果
      if (myId !== reqId) return
      cost.value = data.cost
      insufficient.value = !data.sufficient
    } catch (e) {
      if (myId !== reqId) return
      console.warn('[useCreditEstimate] 请求失败:', e)
      cost.value = null
      error.value = (e as Error)?.message || 'estimate failed'
    } finally {
      if (myId === reqId) loading.value = false
    }
  }
```

- [x] [DONE] 2026-06-25 **Step 3:（可选）提交**

```bash
git add frontend/src/composables/useCreditEstimate.ts
git commit -m "feat(composable): useCreditEstimate 支持 pipeline 类型预估"
```

---

### Task 4: 重命名 stores/asset.ts → stores/canvasAsset.ts + 更新引用

**Files:**
- Rename: `frontend/src/stores/asset.ts` → `frontend/src/stores/canvasAsset.ts`
- Modify: `frontend/src/views/CanvasView.vue`（行 1529、2322、2335）
- Modify: `frontend/src/components/canvas/CanvasAssetLibrary.vue`（行 242）

- [x] [DONE] 2026-06-25 **Step 1: 重命名文件**

```bash
git mv frontend/src/stores/asset.ts frontend/src/stores/canvasAsset.ts
```

注意：`defineStore('asset', ...)` 的 store id **保持不变**（仍为 `'asset'`），避免破坏 localforage 已存数据。

- [x] [DONE] 2026-06-25 **Step 2: 更新 CanvasView.vue 的 3 处动态 import**

修改 `frontend/src/views/CanvasView.vue`：

行 1529：
```typescript
// 修改前
const { useAssetStore } = await import('@/stores/asset')
// 修改后
const { useAssetStore } = await import('@/stores/canvasAsset')
```

行 2322：同上修改。

行 2335：同上修改。

- [x] [DONE] 2026-06-25 **Step 3: 更新 CanvasAssetLibrary.vue 的静态 import**

修改 `frontend/src/components/canvas/CanvasAssetLibrary.vue` 行 242：

```typescript
// 修改前
import { useAssetStore } from '@/stores/asset'
// 修改后
import { useAssetStore } from '@/stores/canvasAsset'
```

- [x] [DONE] 2026-06-25 **Step 4:（可选）提交**

```bash
git add frontend/src/stores/canvasAsset.ts frontend/src/views/CanvasView.vue frontend/src/components/canvas/CanvasAssetLibrary.vue
git commit -m "refactor(store): asset.ts 重命名为 canvasAsset.ts，释放 asset 名字给创意资产库"
```

---

### Task 5: 扩展 stores/permission.ts — 新增 pipeline 权限点

**Files:**
- Modify: `frontend/src/stores/permission.ts`（行 12-16 ROLE_PERMISSIONS）

- [x] [DONE] 2026-06-25 **Step 1: 扩展 ROLE_PERMISSIONS**

修改 `frontend/src/stores/permission.ts` 行 12-16：

```typescript
// 修改前
const ROLE_PERMISSIONS: Record<string, string[]> = {
  admin: ['*'],
  moderator: ['plaza:moderate', 'moderation:config', 'content:generate', 'plaza:share'],
  user: ['content:generate', 'plaza:share'],
}

// 修改后
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

- [x] [DONE] 2026-06-25 **Step 2:（可选）提交**

```bash
git add frontend/src/stores/permission.ts
git commit -m "feat(permission): 新增 pipeline:run / pipeline:save_asset 权限点"
```

---

### Task 6: 扩展 stores/taskQueue.ts — 新增 registerPipelineTask/updatePipelineTask

**Files:**
- Modify: `frontend/src/stores/taskQueue.ts`（行 167 轮询跳过条件 + 行 762 + 新增两个方法）

- [x] [DONE] 2026-06-25 **Step 1: 修改 init 中的轮询跳过条件，加 pipeline**

修改 `frontend/src/stores/taskQueue.ts` 约行 167：

```typescript
// 修改前
if (task.source !== 'chat' && task.source !== 'canvas') {
// 修改后
if (task.source !== 'chat' && task.source !== 'canvas' && task.source !== 'pipeline') {
```

同样修改约行 762 的 `_switchUserStorage` 中的跳过条件（grep `source !== 'chat'` 找到所有位置）。

- [x] [DONE] 2026-06-25 **Step 2: 新增 registerPipelineTask 方法**

在 `frontend/src/stores/taskQueue.ts` 的「画布任务集成」区域之后（updateCanvasTask 之后，约行 603）追加：

```typescript
    // =====================================================
    // 【流水线任务集成】— 供 pipeline store 调用，注册流水线运行
    // =====================================================

    /** 注册流水线运行到队列（仅展示，不启动 taskQueue 自己的轮询） */
    registerPipelineTask({ runId, templateName }: RegisterPipelineTaskParams): void {
      if (!runId) return
      const taskId = `pipeline-${runId}`
      // 避免重复注册
      if (this.tasks[taskId]) return

      this.tasks[taskId] = {
        taskId,
        type: 'image', // 占位类型，TaskCard 根据 source='pipeline' 分支展示
        status: 'processing',
        prompt: templateName,
        params: { runId, templateName },
        resultUrl: null,
        posterUrl: null,
        progress: 0,
        errorMessage: '',
        createdAt: Date.now(),
        updatedAt: Date.now(),
        pollIntervalMs: 0, // pipeline 不参与 taskQueue 轮询
        rawResponse: null,
        backendTaskId: taskId,
        source: 'pipeline',
      }
      this._saveToStorage()
    },

    /** 更新流水线任务的状态（由 usePipelineSSE 的回调调用） */
    updatePipelineTask(runId: number, { status, progress, currentStep, totalSteps, completedSteps }: UpdatePipelineTaskParams): void {
      const taskId = `pipeline-${runId}`
      const task = this.tasks[taskId]
      if (!task) return

      // 更新 payload
      if (currentStep) task.params.currentStep = currentStep
      if (totalSteps) task.params.totalSteps = totalSteps
      if (completedSteps) task.params.completedSteps = completedSteps
      if (typeof progress === 'number') task.progress = progress

      // 状态映射：pipeline 状态 → taskQueue 状态
      if (status) {
        const statusMap: Record<string, string> = {
          pending: 'queued',
          running: 'processing',
          success: 'success',
          failed: 'failed',
          cancelled: 'failed',
          waiting_review: 'processing',
        }
        task.status = statusMap[status] || 'processing'
      }

      task.updatedAt = Date.now()

      // 完成时刷新积分 + 触发历史刷新
      if (task.status === 'success' || task.status === 'failed') {
        try { useUserStore().fetchCredits() } catch (_) { /* 忽略 */ }
        this.historyRefreshSignal++
      }

      this._saveToStorage()
    },
```

- [x] [DONE] 2026-06-25 **Step 3: 在文件头部 import 区追加类型导入**

修改 `frontend/src/stores/taskQueue.ts` 行 24-33 的 import（从 `@/types` 导入的类型列表）追加：

```typescript
import type {
  // ...现有类型...
  RegisterPipelineTaskParams,
  UpdatePipelineTaskParams,
} from '@/types'
```

- [x] [DONE] 2026-06-25 **Step 4:（可选）提交**

```bash
git add frontend/src/stores/taskQueue.ts
git commit -m "feat(taskQueue): 新增 registerPipelineTask/updatePipelineTask，pipeline 运行接入全局任务面板"
```

---

### Task 7: 扩展 TaskCard.vue — 支持 source='pipeline'

**Files:**
- Modify: `frontend/src/components/TaskCard.vue`（template + script）

- [x] [DONE] 2026-06-25 **Step 1: 在 TaskCard.vue script 中新增 pipeline 跳转和状态徽章逻辑**

在 `frontend/src/components/TaskCard.vue` 的 `<script setup>` 中（约行 167 的 handleRemove 之后）追加：

```typescript
import { useRouter } from 'vue-router'
import { useI18n } from '@/i18n'

const router = useRouter()
const { t } = useI18n()

/** pipeline 任务点击跳转 */
function handlePipelineClick(task: QueueTask) {
  if (task.source === 'pipeline' && task.params?.runId) {
    router.push(`/workshop/result/${task.params.runId}`)
  }
}

/** pipeline 状态徽章文本 */
function getPipelineStatusText(status: string): string {
  const map: Record<string, string> = {
    pending: t('common.status.pending'),
    running: t('common.status.running'),
    success: t('common.status.success'),
    failed: t('common.status.failed'),
    cancelled: t('common.status.cancelled'),
    waiting_review: t('common.status.waiting_review'),
  }
  return map[status] || status
}
```

- [x] [DONE] 2026-06-25 **Step 2: 在 template 中为 pipeline 任务添加点击跳转**

在 TaskCard.vue template 的根元素（或任务点击区域，约行 16 的 `@click="$emit('select', task.taskId)"`）添加 pipeline 分支：

```vue
<!-- 修改前 -->
<div class="task-card" @click="$emit('select', task.taskId)">

<!-- 修改后 -->
<div
  class="task-card"
  :class="{ 'task-card--pipeline': task.source === 'pipeline' }"
  @click="task.source === 'pipeline' ? handlePipelineClick(task) : $emit('select', task.taskId)"
>
```

- [x] [DONE] 2026-06-25 **Step 3: pipeline 任务展示进度信息**

在 TaskCard.vue template 的状态徽章区域（约行 30-32）追加 pipeline 进度展示：

```vue
<!-- pipeline 任务额外展示步骤进度 -->
<div v-if="task.source === 'pipeline' && task.params?.currentStep" class="pipeline-step-info">
  <el-icon><Loading v-if="task.status === 'processing'" /><Check v-else /></el-icon>
  <span>{{ task.params.currentStep }}</span>
  <span v-if="task.params.totalSteps" class="step-count">
    {{ task.params.completedSteps || 0 }}/{{ task.params.totalSteps }}
  </span>
</div>
```

在 `<script setup>` 中补齐图标导入：

```typescript
import { Check, Loading } from '@element-plus/icons-vue'
```

- [x] [DONE] 2026-06-25 **Step 4: 在 style 中追加 pipeline 样式**

```vue
<style scoped>
.task-card--pipeline {
  cursor: pointer;
  border-left: 3px solid var(--agnes-primary);
}
.pipeline-step-info {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--agnes-text-secondary);
  margin-top: 4px;
}
.step-count {
  color: var(--agnes-text-placeholder);
}
</style>
```

- [x] [DONE] 2026-06-25 **Step 5:（可选）提交**

```bash
git add frontend/src/components/TaskCard.vue
git commit -m "feat(TaskCard): 支持 source='pipeline' 类型任务展示和点击跳转"
```

---

## Phase 3: Store 重写

### Task 8: 新建 stores/styles.ts — 风格预设 + 剧本模板

**Files:**
- Create: `frontend/src/stores/styles.ts`

- [x] [DONE] 2026-06-25 **Step 1: 创建 stores/styles.ts**

```typescript
/* =====================================================
 * 风格预设 + 剧本模板 Store
 * 从 pipeline store 拆分出来，独立管理
 * 修复：loadStylePresets 不再写死 is_builtin=true，支持加载用户自定义
 * ===================================================== */

import { defineStore } from 'pinia'
import { getStylePresets, getScriptTemplates } from '@/api/pipeline'
import type { StylePreset, ScriptTemplate, PipelineListParams, ListResult } from '@/types'

interface StylesState {
  stylePresets: StylePreset[]
  stylePresetsLoading: boolean
  stylePresetsLoaded: boolean

  scriptTemplates: ScriptTemplate[]
  scriptTemplatesLoading: boolean
  scriptTemplatesLoaded: boolean
}

export const useStylesStore = defineStore('pipelineStyles', {
  state: (): StylesState => ({
    stylePresets: [],
    stylePresetsLoading: false,
    stylePresetsLoaded: false,

    scriptTemplates: [],
    scriptTemplatesLoading: false,
    scriptTemplatesLoaded: false,
  }),

  getters: {
    /** 内置风格预设 */
    builtinStyles(state): StylePreset[] {
      return state.stylePresets.filter(s => s.is_builtin)
    },
    /** 用户自定义风格 */
    userStyles(state): StylePreset[] {
      return state.stylePresets.filter(s => !s.is_builtin)
    },
  },

  actions: {
    /**
     * 加载风格预设列表
     * @param includeUserCreated false 只加载内置，true 加载全部（含用户自定义）
     */
    async loadStylePresets(includeUserCreated = false) {
      if (this.stylePresetsLoading) return
      this.stylePresetsLoading = true
      try {
        const params: PipelineListParams = { page: 1, page_size: 50 }
        if (!includeUserCreated) {
          params.is_builtin = true
        }
        const result: ListResult<StylePreset> = await getStylePresets(params)
        this.stylePresets = result.items
        this.stylePresetsLoaded = true
      } catch (e) {
        console.error('加载风格预设失败:', e)
        throw e
      } finally {
        this.stylePresetsLoading = false
      }
    },

    /** 加载剧本模板列表 */
    async loadScriptTemplates() {
      if (this.scriptTemplatesLoading) return
      this.scriptTemplatesLoading = true
      try {
        const result: ListResult<ScriptTemplate> = await getScriptTemplates({ page: 1, page_size: 50 })
        this.scriptTemplates = result.items
        this.scriptTemplatesLoaded = true
      } catch (e) {
        console.error('加载剧本模板失败:', e)
        throw e
      } finally {
        this.scriptTemplatesLoading = false
      }
    },

    clearAll() {
      this.stylePresets = []
      this.stylePresetsLoading = false
      this.stylePresetsLoaded = false
      this.scriptTemplates = []
      this.scriptTemplatesLoading = false
      this.scriptTemplatesLoaded = false
    },
  },
})

// 用户登出时清理
if (typeof window !== 'undefined') {
  window.addEventListener('agnes:user-logout', () => {
    try {
      useStylesStore().clearAll()
    } catch (_) { /* ignore */ }
  })
}
```

- [x] [DONE] 2026-06-25 **Step 2:（可选）提交**

```bash
git add frontend/src/stores/styles.ts
git commit -m "feat(store): 新建 styles store，管理风格预设和剧本模板"
```

---

### Task 9: 重写 stores/pipeline.ts — 移除 styles，新增 createRun + taskQueue 集成

**Files:**
- Modify: `frontend/src/stores/pipeline.ts`（移除行 29-35、87-89、124-148 的 styles 相关；新增 createRun/cancelRun/retryRun）

- [x] [DONE] 2026-06-25 **Step 1: 重写 stores/pipeline.ts 全文**

替换 `frontend/src/stores/pipeline.ts` 全文为：

```typescript
/* =====================================================
 * 创意流水线状态管理 Store
 * 职责：模板列表、当前运行实例、运行历史
 * 注意：styles/scriptTemplates 已迁移到 stores/styles.ts
 *       创意资产库在 stores/asset.ts（新建）
 * ===================================================== */

import { defineStore } from 'pinia'
import {
  getPipelineTemplates,
  getPipelineRuns,
  createPipelineRun as apiCreateRun,
  cancelPipelineRun as apiCancelRun,
  retryPipelineRun as apiRetryRun,
  retryPipelineStep as apiRetryStep,
} from '@/api/pipeline'
import type {
  PipelineTemplate,
  PipelineRun,
  PipelineListParams,
  ListResult,
  CreateRunRequest,
} from '@/types'
import { useTaskQueueStore } from '@/stores/taskQueue'

interface PipelineState {
  /* 模板相关 */
  templates: PipelineTemplate[]
  templatesLoading: boolean
  templatesTotal: number
  templatesLoaded: boolean

  /* 当前流水线运行 */
  currentRunId: number | null
  currentRun: PipelineRun | null

  /* 历史运行记录 */
  runHistory: PipelineRun[]
  runHistoryLoading: boolean
  runHistoryTotal: number
}

export const usePipelineStore = defineStore('pipeline', {
  state: (): PipelineState => ({
    templates: [],
    templatesLoading: false,
    templatesTotal: 0,
    templatesLoaded: false,

    currentRunId: null,
    currentRun: null,

    runHistory: [],
    runHistoryLoading: false,
    runHistoryTotal: 0,
  }),

  getters: {
    /** 按分类分组的模板 */
    templatesByCategory(state): Record<string, PipelineTemplate[]> {
      const groups: Record<string, PipelineTemplate[]> = {}
      state.templates.forEach(tpl => {
        const cat = tpl.category || 'other'
        if (!groups[cat]) groups[cat] = []
        groups[cat].push(tpl)
      })
      return groups
    },

    /** 是否有正在运行的流水线 */
    hasRunningPipeline(state): boolean {
      return state.runHistory.some(r => r.status === 'running' || r.status === 'pending')
    },
  },

  actions: {
    /** 加载流水线模板列表 */
    async loadTemplates(params: { page?: number; page_size?: number; category?: string; search?: string } = {}) {
      if (this.templatesLoading) return
      this.templatesLoading = true
      try {
        const result = await getPipelineTemplates({ page: 1, page_size: 50, ...params })
        this.templates = result.items
        this.templatesTotal = result.total
        this.templatesLoaded = true
      } catch (e) {
        console.error('加载流水线模板失败:', e)
        throw e
      } finally {
        this.templatesLoading = false
      }
    },

    /**
     * 创建并启动流水线运行
     * 内部会注册到 taskQueue，让全局任务面板展示进度
     */
    async createRun(templateId: number, inputs: Record<string, unknown>, name?: string) {
      const payload: CreateRunRequest = { template_id: templateId, inputs, name }
      const run = await apiCreateRun(payload)

      // 注册到全局任务队列
      const taskQueue = useTaskQueueStore()
      const templateName = this.templates.find(t => t.id === templateId)?.name || `运行 #${run.id}`
      taskQueue.registerPipelineTask({ runId: run.id, templateName })

      // 设置为当前运行
      this.currentRun = run
      this.currentRunId = run.id

      return run
    },

    /** 加载单个运行详情 */
    async loadRun(runId: number) {
      // 直接调 API，不缓存（run 详情由 SSE 实时更新）
      const { getPipelineRunDetail } = await import('@/api/pipeline')
      const run = await getPipelineRunDetail(runId)
      this.currentRun = run
      this.currentRunId = run.id
      return run
    },

    /** 取消运行 */
    async cancelRun(runId: number) {
      await apiCancelRun(runId)
      if (this.currentRun?.id === runId) {
        this.currentRun.status = 'cancelled'
      }
    },

    /** 重试整个运行 */
    async retryRun(runId: number) {
      await apiRetryRun(runId)
    },

    /** 重试单个失败步骤 */
    async retryStep(runId: number, stepKey: string) {
      await apiRetryStep(runId, stepKey)
    },

    /** 加载我的流水线历史 */
    async loadRunHistory(params: { page?: number; page_size?: number; status?: string } = {}) {
      if (this.runHistoryLoading) return
      this.runHistoryLoading = true
      try {
        const result = await getPipelineRuns({ page: 1, page_size: 20, ...params })
        this.runHistory = result.items
        this.runHistoryTotal = result.total
      } catch (e) {
        console.error('加载流水线历史失败:', e)
        throw e
      } finally {
        this.runHistoryLoading = false
      }
    },

    /** 设置当前运行的流水线 */
    setCurrentRun(run: PipelineRun | null) {
      this.currentRun = run
      this.currentRunId = run?.id ?? null
    },

    /** 从 SSE 事件更新当前运行状态 */
    updateRunFromEvent(eventType: string, data: Record<string, any>) {
      if (!this.currentRun) return
      if (eventType === 'pipeline_completed' || eventType === 'pipeline_failed') {
        this.currentRun.status = data.status || this.currentRun.status
        if (data.error) this.currentRun.error_message = data.error
        if (data.output_summary) this.currentRun.output_summary = data.output_summary
        this.currentRun.finished_at = new Date().toISOString()
      } else if (eventType === 'pipeline_started') {
        this.currentRun.status = 'running'
        this.currentRun.started_at = new Date().toISOString()
      }
    },

    clearAll() {
      this.templates = []
      this.templatesLoading = false
      this.templatesTotal = 0
      this.templatesLoaded = false
      this.currentRunId = null
      this.currentRun = null
      this.runHistory = []
      this.runHistoryLoading = false
      this.runHistoryTotal = 0
    },
  },
})

// 用户登出时清理流水线状态
if (typeof window !== 'undefined') {
  window.addEventListener('agnes:user-logout', () => {
    try {
      usePipelineStore().clearAll()
    } catch (_) { /* ignore */ }
  })
}
```

- [x] [DONE] 2026-06-25 **Step 2:（可选）提交**

```bash
git add frontend/src/stores/pipeline.ts
git commit -m "refactor(store): pipeline store 移除 styles，新增 createRun 集成 taskQueue"
```

---

### Task 10: 新建 stores/asset.ts — 创意资产库

**Files:**
- Create: `frontend/src/stores/asset.ts`（注意：Task 4 已把原 asset.ts 重命名为 canvasAsset.ts，此处的 asset.ts 是全新的创意资产库 store）

- [x] [DONE] 2026-06-25 **Step 1: 创建 stores/asset.ts**

```typescript
/* =====================================================
 * 创意资产库 Store
 * 管理可复用的角色/道具/场景/品牌资产（后端 API 数据）
 * 区别于 stores/canvasAsset.ts（画布媒体资源库，localforage）
 * ===================================================== */

import { defineStore } from 'pinia'
import { getAssets, saveAssetFromGeneration } from '@/api/pipeline'
import type {
  Asset,
  AssetType,
  PipelineListParams,
  ListResult,
  SaveAssetFromGenerationRequest,
} from '@/types'

interface AssetFilter {
  type: AssetType | ''
  search: string
  mine: boolean
}

interface AssetState {
  assets: Asset[]
  currentAsset: Asset | null
  filter: AssetFilter
  loading: boolean
  total: number
}

export const useAssetStore = defineStore('pipelineAsset', {
  state: (): AssetState => ({
    assets: [],
    currentAsset: null,
    filter: { type: '', search: '', mine: false },
    loading: false,
    total: 0,
  }),

  actions: {
    /** 加载资产列表 */
    async loadAssets(params?: PipelineListParams) {
      this.loading = true
      try {
        const result: ListResult<Asset> = await getAssets(params || {})
        this.assets = result.items
        this.total = result.total
      } catch (e) {
        console.error('加载资产列表失败:', e)
        throw e
      } finally {
        this.loading = false
      }
    },

    /** 保存生成结果到资产库 */
    async saveFromGeneration(generationId: number, data: Omit<SaveAssetFromGenerationRequest, 'generation_id'>) {
      const payload: SaveAssetFromGenerationRequest = {
        generation_id: generationId,
        ...data,
      }
      return await saveAssetFromGeneration(payload)
    },

    /** 设置筛选条件 */
    setFilter(filter: Partial<AssetFilter>) {
      Object.assign(this.filter, filter)
    },

    clearAll() {
      this.assets = []
      this.currentAsset = null
      this.filter = { type: '', search: '', mine: false }
      this.loading = false
      this.total = 0
    },
  },
})

// 用户登出时清理
if (typeof window !== 'undefined') {
  window.addEventListener('agnes:user-logout', () => {
    try {
      useAssetStore().clearAll()
    } catch (_) { /* ignore */ }
  })
}
```

- [x] [DONE] 2026-06-25 **Step 2:（可选）提交**

```bash
git add frontend/src/stores/asset.ts
git commit -m "feat(store): 新建 asset store，创意资产库（character/prop/scene/brand）"
```

---

## Phase 4: 组件新建

### Task 11: 新建 PipelineProgress.vue — 步骤时间线

**Files:**
- Create: `frontend/src/components/pipeline/PipelineProgress.vue`

- [x] [DONE] 2026-06-25 **Step 1: 创建组件**

```vue
<template>
  <div class="pipeline-progress">
    <!-- 整体进度条 -->
    <div class="progress-summary">
      <el-progress
        :percentage="overallProgress"
        :status="progressStatus"
        :stroke-width="8"
      />
      <span class="progress-text">
        {{ t('pipelineResult.steps.completed', { completed: completedCount, total: steps.length }) }}
      </span>
    </div>

    <!-- 步骤时间线 -->
    <el-timeline class="steps-timeline">
      <el-timeline-item
        v-for="step in steps"
        :key="step.step_key"
        :type="getTimelineNodeType(step)"
        :hollow="step.status === 'pending'"
        :timestamp="step.finished_at || step.started_at"
        placement="top"
      >
        <div
          class="step-item"
          :class="{
            'step-item--selected': step.step_key === selectedStepKey,
            'step-item--clickable': step.status === 'success',
          }"
          @click="step.status === 'success' && $emit('select-step', step.step_key)"
        >
          <div class="step-header">
            <el-icon class="step-icon"><component :is="getStepIcon(step.step_type)" /></el-icon>
            <span class="step-name">{{ step.name }}</span>
            <el-tag :type="getStatusTagType(step.status)" size="small">
              {{ t(`pipelineResult.stepStatus.${step.status}`) }}
            </el-tag>
          </div>

          <!-- 失败步骤：错误信息 + 重试按钮 -->
          <div v-if="step.status === 'failed'" class="step-error">
            <span class="error-text">{{ step.error_message }}</span>
            <el-button
              v-permission="'pipeline:run'"
              size="small"
              type="primary"
              @click.stop="$emit('retry-step', step.step_key)"
            >
              {{ t('pipelineResult.retryStep') }}
            </el-button>
          </div>

          <!-- 运行中步骤：进度提示 -->
          <div v-if="step.status === 'running'" class="step-running">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>{{ t('pipelineResult.stepStatus.running') }}</span>
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '@/i18n'
import { ElTimeline, ElTimelineItem, ElProgress, ElTag, ElButton, ElIcon } from 'element-plus'
import { Document, Picture, VideoPlay, Loading, Film, Microphone, Edit } from '@element-plus/icons-vue'
import type { PipelineStep, PipelineRunStatus } from '@/types'

const props = defineProps<{
  steps: PipelineStep[]
  currentStepKey?: string
  runStatus: PipelineRunStatus | string
  selectedStepKey?: string
}>()

defineEmits<{
  'select-step': [stepKey: string]
  'retry-step': [stepKey: string]
}>()

const { t } = useI18n()

const completedCount = computed(() =>
  props.steps.filter(s => s.status === 'success').length
)

const overallProgress = computed(() => {
  if (!props.steps.length) return 0
  return Math.round((completedCount.value / props.steps.length) * 100)
})

const progressStatus = computed(() => {
  if (props.runStatus === 'failed') return 'exception'
  if (props.runStatus === 'success') return 'success'
  return undefined
})

function getStepIcon(stepType: string) {
  const iconMap: Record<string, any> = {
    llm_generate: Document,
    image_batch: Picture,
    video_batch: VideoPlay,
    ffmpeg_composite: Film,
    tts_generate: Microphone,
    human_review: Edit,
  }
  return iconMap[stepType] || Document
}

function getTimelineNodeType(step: PipelineStep): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
    success: 'success',
    running: 'primary',
    failed: 'danger',
    skipped: 'info',
    pending: 'info',
  }
  return map[step.status] || 'info'
}

function getStatusTagType(status: string): 'success' | 'warning' | 'danger' | 'info' | '' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | ''> = {
    success: 'success',
    running: 'warning',
    failed: 'danger',
    skipped: 'info',
    pending: 'info',
  }
  return map[status] || ''
}
</script>

<style scoped>
.pipeline-progress {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.progress-summary {
  display: flex;
  align-items: center;
  gap: 12px;
}
.progress-summary .el-progress {
  flex: 1;
}
.progress-text {
  font-size: 13px;
  color: var(--agnes-text-secondary);
  white-space: nowrap;
}
.steps-timeline {
  padding-left: 8px;
}
.step-item {
  cursor: default;
  padding: 8px 12px;
  border-radius: 6px;
  transition: background 0.2s;
}
.step-item--clickable {
  cursor: pointer;
}
.step-item--clickable:hover {
  background: var(--agnes-bg-hover, rgba(0, 0, 0, 0.04));
}
.step-item--selected {
  background: var(--agnes-primary-light-9, rgba(64, 158, 255, 0.1));
}
.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.step-icon {
  font-size: 16px;
  color: var(--agnes-text-secondary);
}
.step-name {
  flex: 1;
  font-size: 14px;
  color: var(--agnes-text-primary);
}
.step-error {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.error-text {
  flex: 1;
  font-size: 12px;
  color: var(--agnes-danger);
  word-break: break-all;
}
.step-running {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--agnes-primary);
}
</style>
```

- [x] [DONE] 2026-06-25 **Step 2:（可选）提交**

```bash
git add frontend/src/components/pipeline/PipelineProgress.vue
git commit -m "feat(component): 新建 PipelineProgress 步骤时间线组件"
```

---

### Task 12: 新建 StepResultGallery.vue — 步骤结果画廊

**Files:**
- Create: `frontend/src/components/pipeline/StepResultGallery.vue`

- [x] [DONE] 2026-06-25 **Step 1: 创建组件**

```vue
<template>
  <div class="step-result-gallery">
    <!-- 文本结果（LLM 剧本生成） -->
    <div v-if="step.step_type === 'llm_generate'" class="text-result">
      <div class="result-header">
        <span class="result-title">{{ step.name }}</span>
        <el-button text size="small" @click="textExpanded = !textExpanded">
          {{ textExpanded ? t('common.collapse') : t('common.expand') }}
        </el-button>
      </div>
      <pre class="script-content" :class="{ 'script-content--collapsed': !textExpanded }">{{
        scriptText
      }}</pre>
    </div>

    <!-- 图片网格 -->
    <div v-else-if="images.length" class="image-grid">
      <div
        v-for="(img, idx) in images"
        :key="idx"
        class="image-item"
        @click="openImageViewer(idx)"
      >
        <ImageWithWatermark :src="img.url" :alt="`结果 ${idx + 1}`" />
      </div>
    </div>

    <!-- 视频网格 -->
    <div v-else-if="videos.length" class="video-grid">
      <div v-for="(vid, idx) in videos" :key="idx" class="video-item">
        <video :src="vid.url" controls :poster="vid.poster" class="video-player" />
        <span class="video-duration">{{ formatDuration(vid.duration) }}</span>
      </div>
    </div>

    <!-- 空状态 -->
    <el-empty v-else :description="t('pipelineResult.noResult')" />

    <!-- 图片查看器 -->
    <ImageViewer
      v-if="images.length && viewerVisible"
      :visible="viewerVisible"
      :images="images.map(i => i.url)"
      :initial-index="viewerIndex"
      @close="viewerVisible = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from '@/i18n'
import { ElEmpty, ElButton } from 'element-plus'
import ImageWithWatermark from '@/components/ImageWithWatermark.vue'
import ImageViewer from '@/components/ImageViewer.vue'
import type { PipelineStep } from '@/types'

const props = defineProps<{
  step: PipelineStep
}>()

const { t } = useI18n()

const textExpanded = ref(false)
const viewerVisible = ref(false)
const viewerIndex = ref(0)

/** 从 output_data 提取文本结果 */
const scriptText = computed(() => {
  const out = props.step.output_data || {}
  // 兼容多种字段名
  return out.parsed_result || out.text || out.script || JSON.stringify(out, null, 2)
})

/** 从 output_data 提取图片列表 */
const images = computed(() => {
  const out = props.step.output_data || {}
  return (out.images || []).map((img: any) => ({
    url: img.url || img,
    prompt: img.prompt,
  }))
})

/** 从 output_data 提取视频列表 */
const videos = computed(() => {
  const out = props.step.output_data || {}
  return (out.videos || []).map((vid: any) => ({
    url: vid.url || vid,
    poster: vid.poster,
    duration: vid.duration,
  }))
})

function openImageViewer(idx: number) {
  viewerIndex.value = idx
  viewerVisible.value = true
}

function formatDuration(seconds?: number): string {
  if (!seconds) return ''
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}
</script>

<style scoped>
.step-result-gallery {
  width: 100%;
}
.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.result-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--agnes-text-primary);
}
.script-content {
  background: var(--agnes-bg-page);
  padding: 12px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: none;
  overflow: hidden;
  transition: max-height 0.3s;
}
.script-content--collapsed {
  max-height: 200px;
}
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}
.image-item {
  cursor: pointer;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--agnes-border);
  transition: transform 0.2s;
}
.image-item:hover {
  transform: scale(1.02);
}
.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.video-item {
  position: relative;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--agnes-border);
}
.video-player {
  width: 100%;
  display: block;
}
.video-duration {
  position: absolute;
  bottom: 8px;
  right: 8px;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
}
</style>
```

注意：`ImageWithWatermark` 和 `ImageViewer` 的实际 import 路径以项目 `components/index.ts` 导出为准。如果未全局注册，需确认相对路径。

- [x] [DONE] 2026-06-25 **Step 2:（可选）提交**

```bash
git add frontend/src/components/pipeline/StepResultGallery.vue
git commit -m "feat(component): 新建 StepResultGallery 步骤结果画廊，复用 ImageWithWatermark + ImageViewer"
```

---

### Task 13: 新建 StyleSelector.vue — 风格选择器

**Files:**
- Create: `frontend/src/components/pipeline/StyleSelector.vue`

- [x] [DONE] 2026-06-25 **Step 1: 创建组件**

```vue
<template>
  <div class="style-selector">
    <PromptTemplates
      :title="t('pipelineRun.styleSelectorTitle')"
      :templates="styleChips"
      type="style"
      @select="onSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '@/i18n'
import { PromptTemplates } from '@/components'
import { useStylesStore } from '@/stores/styles'

const props = defineProps<{
  modelValue?: number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [id: number]
}>()

const stylesStore = useStylesStore()
const { t } = useI18n()

/** 将风格预设转为 PromptTemplates 所需的芯片格式 */
const styleChips = computed(() =>
  stylesStore.stylePresets.map(s => ({
    label: s.name,
    prompt: String(s.id), // 复用 chip 机制，传 id
    preview: s.preview_image,
  }))
)

function onSelect(prompt: string) {
  emit('update:modelValue', Number(prompt))
}
</script>

<style scoped>
.style-selector {
  width: 100%;
}
</style>
```

注意：`PromptTemplates` 的实际 props（title/templates/type）和事件（select）需对照现有组件签名确认。如果 PromptTemplates 的 props 名不同，调整为实际名称。

- [x] [DONE] 2026-06-25 **Step 2:（可选）提交**

```bash
git add frontend/src/components/pipeline/StyleSelector.vue
git commit -m "feat(component): 新建 StyleSelector 风格选择器，复用 PromptTemplates 芯片"
```

---

### Task 14: 新建 AssetCard.vue + AssetDetailModal.vue

**Files:**
- Create: `frontend/src/components/pipeline/AssetCard.vue`
- Create: `frontend/src/components/pipeline/AssetDetailModal.vue`

- [x] [DONE] 2026-06-25 **Step 1: 创建 AssetCard.vue**

```vue
<template>
  <el-card class="asset-card" shadow="hover" @click="$emit('click', asset)">
    <div class="card-cover">
      <ImageWithWatermark
        v-if="asset.reference_images?.length"
        :src="asset.reference_images[0]"
        :alt="asset.name"
      />
      <div v-else class="cover-placeholder">
        <el-icon><Picture /></el-icon>
      </div>
    </div>
    <div class="card-body">
      <div class="card-header">
        <span class="card-title">{{ asset.name }}</span>
        <el-tag size="small" type="info">{{ t(`assets.type.${asset.type}`) }}</el-tag>
      </div>
      <p class="card-desc">{{ asset.description || asset.visual_description }}</p>
      <div class="card-footer">
        <span class="use-count">{{ t('assets.fields.useCount') }}: {{ asset.use_count || 0 }}</span>
        <el-button
          v-permission="'pipeline:save_asset'"
          size="small"
          type="primary"
          text
          @click.stop="$emit('use', asset)"
        >
          {{ t('assets.useTip') }}
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { useI18n } from '@/i18n'
import { ElCard, ElTag, ElButton, ElIcon } from 'element-plus'
import { Picture } from '@element-plus/icons-vue'
import ImageWithWatermark from '@/components/ImageWithWatermark.vue'
import type { Asset } from '@/types'

defineProps<{
  asset: Asset
  selectable?: boolean
}>()

defineEmits<{
  click: [asset: Asset]
  use: [asset: Asset]
}>()

const { t } = useI18n()
</script>

<style scoped>
.asset-card {
  cursor: pointer;
  transition: transform 0.2s;
}
.asset-card:hover {
  transform: translateY(-2px);
}
.card-cover {
  aspect-ratio: 16 / 9;
  background: var(--agnes-bg-page);
  border-radius: 6px;
  overflow: hidden;
}
.cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--agnes-text-placeholder);
  font-size: 32px;
}
.card-body {
  padding: 12px 0 0;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.card-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--agnes-text-primary);
}
.card-desc {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  margin: 0 0 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.use-count {
  font-size: 12px;
  color: var(--agnes-text-placeholder);
}
</style>
```

- [x] [DONE] 2026-06-25 **Step 2: 创建 AssetDetailModal.vue**

```vue
<template>
  <el-dialog
    :model-value="modelValue"
    :title="asset ? t('assets.editAsset') : t('assets.createAsset')"
    width="600px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form v-if="form" :model="form" label-width="100px">
      <el-form-item :label="t('assets.fields.name')">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item :label="t('assets.fields.type')">
        <el-select v-model="form.type" :placeholder="t('assets.type.all')">
          <el-option :label="t('assets.type.character')" value="character" />
          <el-option :label="t('assets.type.prop')" value="prop" />
          <el-option :label="t('assets.type.scene')" value="scene" />
          <el-option :label="t('assets.type.brand')" value="brand" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('assets.fields.description')">
        <el-input v-model="form.description" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item :label="t('assets.fields.visualDescription')">
        <el-input v-model="form.visual_description" type="textarea" :rows="3" />
      </el-form-item>
      <el-form-item :label="t('assets.fields.referenceImages')">
        <ImageUploader v-model="form.reference_images" :max="5" />
      </el-form-item>
      <el-form-item :label="t('assets.fields.tags')">
        <el-input v-model="tagsInput" :placeholder="t('assets.fields.tags')" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">
        {{ t('common.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import { ElDialog, ElForm, ElFormItem, ElInput, ElSelect, ElOption, ElButton, ElMessage } from 'element-plus'
import ImageUploader from '@/components/ImageUploader.vue'
import { useAssetStore } from '@/stores/asset'
import type { Asset, AssetType } from '@/types'

const props = defineProps<{
  modelValue: boolean
  assetId?: number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [asset: Asset]
}>()

const { t } = useI18n()
const assetStore = useAssetStore()

const form = ref<any>(null)
const tagsInput = ref('')
const saving = ref(false)

watch(
  () => [props.modelValue, props.assetId],
  async ([visible, id]) => {
    if (visible) {
      if (id) {
        // 编辑现有资产
        const { getAssetDetail } = await import('@/api/pipeline')
        const detail = await getAssetDetail(id as number)
        form.value = { ...detail }
        tagsInput.value = (detail.tags || []).join(', ')
      } else {
        // 新建
        form.value = {
          name: '',
          type: 'character' as AssetType,
          description: '',
          visual_description: '',
          reference_images: [],
          tags: [],
        }
        tagsInput.value = ''
      }
    }
  },
  { immediate: true }
)

async function handleSave() {
  if (!form.value.name) {
    ElMessage.warning(t('assets.fields.name') + t('common.required'))
    return
  }
  saving.value = true
  try {
    form.value.tags = tagsInput.value.split(',').map(s => s.trim()).filter(Boolean)
    // 调用 store 保存（store 内部调 API）
    // 注意：如果后端有 createAsset 接口，需在 api/pipeline.ts 补充
    emit('saved', form.value)
    emit('update:modelValue', false)
  } catch (e) {
    console.error('保存资产失败:', e)
  } finally {
    saving.value = false
  }
}
</script>
```

- [x] [DONE] 2026-06-25 **Step 3:（可选）提交**

```bash
git add frontend/src/components/pipeline/AssetCard.vue frontend/src/components/pipeline/AssetDetailModal.vue
git commit -m "feat(component): 新建 AssetCard + AssetDetailModal，复用 ImageWithWatermark + ImageUploader"
```

---

### Task 15: 删除旧 ResultDisplay.vue

**Files:**
- Delete: `frontend/src/components/pipeline/ResultDisplay.vue`

- [x] [DONE] 2026-06-25 **Step 1: 删除文件**

```bash
git rm frontend/src/components/pipeline/ResultDisplay.vue
```

最终视频展示逻辑将内联到 PipelineResultView（Task 19）。

- [x] [DONE] 2026-06-25 **Step 2:（可选）提交**

```bash
git commit -m "refactor(component): 删除 ResultDisplay.vue，最终结果展示内联到 PipelineResultView"
```

---

## Phase 5: Composable 重写

### Task 16: 重写 usePipelineSSE.ts — 复用 userStore + 401 对齐

**Files:**
- Modify: `frontend/src/composables/usePipelineSSE.ts`

**修改要点**（由于文件 418 行，这里给出修改点而非全文）：

- [x] [DONE] 2026-06-25 **Step 1: 修改 token 获取方式**

在 `frontend/src/composables/usePipelineSSE.ts` 中，找到所有 `localStorage.getItem('agnes.platform.auth.token')` 调用，改为：

```typescript
import { useUserStore } from '@/stores/user'
import { computed } from 'vue'

const userStore = useUserStore()
const token = computed(() => userStore.token)
```

在构造 SSE URL 时使用 `token.value`。

- [x] [DONE] 2026-06-25 **Step 2: 401 处理对齐 client.ts**

在 SSE 的 401 处理逻辑中（onerror 或 onmessage 收到 401 状态），改为：

```typescript
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'

// SSE 收到 401 时的处理（对齐 api/client.ts 行 56-76 的逻辑）
function handleUnauthorized() {
  const userStore = useUserStore()
  userStore.clearAll()
  window.dispatchEvent(new CustomEvent('agnes:user-logout'))
  ElMessage.warning(t('pipelineResult.sse.unauthorized') || '登录已过期，请重新登录')
  window.location.hash = '#/login'
}
```

- [x] [DONE] 2026-06-25 **Step 3: SSE URL 复用 api 函数**

```typescript
import { buildSSEUrl } from '@/api/pipeline'

// 构造 SSE URL
const url = buildSSEUrl(runId)
// 拼接 token 参数（如果后端 SSE 需要 query token）
const sseUrl = `${url}?token=${encodeURIComponent(token.value || '')}`
```

- [x] [DONE] 2026-06-25 **Step 4: 修复拼写错误 manuallClosed → manualClosed**

全文替换 `manuallClosed` 为 `manualClosed`（6 处）。

- [x] [DONE] 2026-06-25 **Step 5: i18n 错误提示**

将所有硬编码中文错误提示改为 `t('pipelineResult.sse.*')` 或 `t('common.error.*')`。

- [x] [DONE] 2026-06-25 **Step 6:（可选）提交**

```bash
git add frontend/src/composables/usePipelineSSE.ts
git commit -m "refactor(composable): usePipelineSSE 复用 userStore.token + 401 对齐 client.ts + 修复拼写"
```

---

## Phase 6: 页面重写

### Task 17: 重写 WorkshopView.vue — CSS 变量 + i18n + pipelineStore

**Files:**
- Modify: `frontend/src/views/WorkshopView.vue`

- [x] [DONE] 2026-06-25 **Step 1: CSS 变量全部替换为 --agnes-* 前缀**

在 `frontend/src/views/WorkshopView.vue` 的 `<style>` 中，全文替换：

| 旧变量 | 新变量 |
|--------|--------|
| `var(--text-primary)` | `var(--agnes-text-primary)` |
| `var(--text-secondary)` | `var(--agnes-text-secondary)` |
| `var(--text-placeholder)` | `var(--agnes-text-placeholder)` |
| `var(--bg-card)` | `var(--agnes-bg-card)` |
| `var(--bg-page)` | `var(--agnes-bg-page)` |
| `var(--border-color)` | `var(--agnes-border)` |
| `var(--primary)` | `var(--agnes-primary)` |

- [x] [DONE] 2026-06-25 **Step 2: i18n 全覆盖**

将 `categoryLabels` 映射表替换为 `t('workshop.category.*')` 调用。

将 `getStatusText` 替换为 `t('common.status.*')`。

所有硬编码中文按钮文案改为 `t('workshop.*')`。

- [x] [DONE] 2026-06-25 **Step 3: 使用 pipelineStore**

```typescript
import { usePipelineStore } from '@/stores/pipeline'
const pipelineStore = usePipelineStore()

// 加载模板
onMounted(() => {
  if (!pipelineStore.templatesLoaded) {
    pipelineStore.loadTemplates()
  }
})
```

- [x] [DONE] 2026-06-25 **Step 4: 权限控制**

「使用此模板」按钮加 `v-permission="'pipeline:run'"`。

- [x] [DONE] 2026-06-25 **Step 5:（可选）提交**

```bash
git add frontend/src/views/WorkshopView.vue
git commit -m "refactor(view): WorkshopView 修复 CSS 变量 + i18n + pipelineStore"
```

---

### Task 18: 重写 PipelineRunView.vue — useCreditEstimate + StyleSelector

**Files:**
- Modify: `frontend/src/views/PipelineRunView.vue`

- [x] [DONE] 2026-06-25 **Step 1: 删除内联 estimateCredits，改用 useCreditEstimate**

```typescript
import { useCreditEstimate } from '@/composables/useCreditEstimate'

const { cost: estimatedCredits, loading: estimating, insufficient, refresh: refreshEstimate } = useCreditEstimate(
  () => ({
    type: 'pipeline' as const,
    templateId: Number(route.params.templateId),
    inputs: collectInputs(),
  })
)
```

删除原有内联的 `estimateCredits()` 函数。

- [x] [DONE] 2026-06-25 **Step 2: style_select 字段改用 StyleSelector**

```vue
<StyleSelector
  v-if="field.type === 'style_select'"
  v-model="form[field.key]"
/>
```

- [x] [DONE] 2026-06-25 **Step 3: 删除 :deep() 覆盖，删除未使用的 Operation 图标导入**

- [x] [DONE] 2026-06-25 **Step 4: i18n 全覆盖，权限控制**

「启动流水线」按钮加 `v-permission="'pipeline:run'"`。

- [x] [DONE] 2026-06-25 **Step 5:（可选）提交**

```bash
git add frontend/src/views/PipelineRunView.vue
git commit -m "refactor(view): PipelineRunView 复用 useCreditEstimate + StyleSelector"
```

---

### Task 19: 重写 PipelineResultView.vue — 渐进式产物可见 + 新组件

**Files:**
- Modify: `frontend/src/views/PipelineResultView.vue`

- [x] [DONE] 2026-06-25 **Step 1: 修复 goBack 路由 bug**

```typescript
function goBack() {
  router.push('/workshop')
}
```

- [x] [DONE] 2026-06-25 **Step 2: 统一步骤类型枚举**

将 `getStepTypeText` 中的枚举改为与后端对齐：

```typescript
const STEP_TYPE_LABELS = {
  llm_generate: 'LLM 剧本生成',
  image_batch: '图片批量生成',
  video_batch: '视频批量生成',
  ffmpeg_composite: '视频合成',
  tts_generate: '配音生成',
  human_review: '人工审核',
}
```

改为 i18n：`t('pipelineRun.stepType.*')`。

- [x] [DONE] 2026-06-25 **Step 3: 实现渐进式产物可见性布局**

采用左右分栏布局：

```vue
<template>
  <div class="pipeline-result">
    <!-- 顶部：运行信息 + 状态徽章 + SSE 连接状态 -->
    <div class="result-header">
      <el-page-header @back="goBack">
        <template #content>
          {{ t('pipelineResult.runInfo', { id: run?.id, time: run?.created_at }) }}
        </template>
      </el-page-header>
      <el-tag :type="getStatusTagType(run?.status)">{{ t(`common.status.${run?.status}`) }}</el-tag>
      <el-tag type="info">{{ connectionStatusText }}</el-tag>
    </div>

    <!-- 主体：左右分栏 -->
    <div class="result-body">
      <!-- 左侧：步骤时间线 -->
      <div class="steps-panel">
        <PipelineProgress
          :steps="steps"
          :current-step-key="run?.current_step_key"
          :run-status="run?.status || 'pending'"
          :selected-step-key="selectedStepKey"
          @select-step="handleStepClick"
          @retry-step="handleRetryStep"
        />
      </div>

      <!-- 右侧：当前选中步骤的产出展示 -->
      <div class="output-panel">
        <StepResultGallery v-if="selectedStep" :step="selectedStep" />
        <el-empty v-else :description="t('pipelineResult.steps.preparing')" />
      </div>
    </div>

    <!-- 底部：最终结果区（仅当有最终视频时显示） -->
    <div v-if="finalVideoUrl" class="final-result">
      <el-divider />
      <h3>{{ t('pipelineResult.resultTitle') }}</h3>
      <video :src="finalVideoUrl" controls class="final-video" />
      <div class="final-actions">
        <el-button @click="handleDownload">
          <el-icon><Download /></el-icon>
          {{ t('common.download') }}
        </el-button>
        <el-button v-permission="'pipeline:save_asset'" @click="saveToAsset">
          <el-icon><Plus /></el-icon>
          {{ t('pipelineResult.saveToAsset') }}
        </el-button>
      </div>
    </div>
  </div>
</template>
```

- [x] [DONE] 2026-06-25 **Step 4: 实现自动切换焦点逻辑**

```typescript
const selectedStepKey = ref<string>('')

// SSE 收到 step_completed 后自动切换
function handleStepCompleted(event: { step_key: string }) {
  selectedStepKey.value = event.step_key
  // 触发历史刷新，让 HistoryView 看到新生成的图片/视频
  taskQueue.historyRefreshSignal++
}

// 点击时间线节点切换
function handleStepClick(stepKey: string) {
  selectedStepKey.value = stepKey
}

const selectedStep = computed(() =>
  steps.value.find(s => s.step_key === selectedStepKey.value)
)

// 优先展示最新完成的步骤
watch(steps, (newSteps) => {
  if (!selectedStepKey.value || !newSteps.find(s => s.step_key === selectedStepKey.value)) {
    const latestCompleted = [...newSteps].reverse().find(s => s.status === 'success')
    if (latestCompleted) {
      selectedStepKey.value = latestCompleted.step_key
    }
  }
}, { deep: true })
```

- [x] [DONE] 2026-06-25 **Step 5: taskQueue 集成**

在 SSE 事件回调中同步 taskQueue：

```typescript
import { useTaskQueueStore } from '@/stores/taskQueue'
const taskQueue = useTaskQueueStore()

function handleSSEEvent(eventType: string, data: any) {
  // 更新 pipelineStore
  pipelineStore.updateRunFromEvent(eventType, data)

  // 同步 taskQueue
  if (run.value) {
    const completedSteps = steps.value.filter(s => s.status === 'success').length
    taskQueue.updatePipelineTask(run.value.id, {
      status: data.status || run.value.status,
      progress: completedSteps / steps.value.length,
      currentStep: data.step_key,
      totalSteps: steps.value.length,
      completedSteps,
    })
  }

  // step_completed 时触发历史刷新
  if (eventType === 'step_completed') {
    handleStepCompleted({ step_key: data.step_key })
  }
}
```

- [x] [DONE] 2026-06-25 **Step 6: i18n 全覆盖 + 权限控制**

所有硬编码中文改为 `t('pipelineResult.*')`。

- [x] [DONE] 2026-06-25 **Step 7:（可选）提交**

```bash
git add frontend/src/views/PipelineResultView.vue
git commit -m "refactor(view): PipelineResultView 实现渐进式产物可见 + PipelineProgress + StepResultGallery"
```

---

### Task 20: 重写 AssetsView.vue — CSS 变量 + 资产类型 + assetStore

**Files:**
- Modify: `frontend/src/views/AssetsView.vue`

- [x] [DONE] 2026-06-25 **Step 1: 修复资产类型 tab**

```typescript
const assetTypes = [
  { value: '', label: '全部' },
  { value: 'character', label: '角色' },
  { value: 'prop', label: '道具' },
  { value: 'scene', label: '场景' },
  { value: 'brand', label: '品牌' },
]
```

改为 i18n：`t('assets.type.*')`。

- [x] [DONE] 2026-06-25 **Step 2: CSS 变量全部替换为 --agnes-* 前缀**

同 Task 17 Step 1。

- [x] [DONE] 2026-06-25 **Step 3: 使用 assetStore**

```typescript
import { useAssetStore } from '@/stores/asset'
const assetStore = useAssetStore()

onMounted(() => {
  assetStore.loadAssets({ type: assetStore.filter.type || undefined })
})
```

- [x] [DONE] 2026-06-25 **Step 4: 复用 AssetCard + AssetDetailModal**

```vue
<AssetCard
  v-for="asset in assetStore.assets"
  :key="asset.id"
  :asset="asset"
  @click="openDetail(asset)"
  @use="useAsset"
/>
```

- [x] [DONE] 2026-06-25 **Step 5: i18n 全覆盖 + 权限控制**

「创建资产」「编辑资产」按钮加 `v-permission="'pipeline:save_asset'"`。

- [x] [DONE] 2026-06-25 **Step 6:（可选）提交**

```bash
git add frontend/src/views/AssetsView.vue
git commit -m "refactor(view): AssetsView 修复资产类型 + CSS 变量 + assetStore + AssetCard"
```

---

## Phase 7: i18n 与权限补全

### Task 21: 补全 i18n/zh-CN.ts — common.status + pipeline 命名空间

**Files:**
- Modify: `frontend/src/i18n/zh-CN.ts`

- [x] [DONE] 2026-06-25 **Step 1: 在 common 命名空间下新增 status 子命名空间**

在 `frontend/src/i18n/zh-CN.ts` 的 `common` 对象（约行 9-35）内追加：

```typescript
common: {
  // ...现有内容...
  status: {
    pending: '等待中',
    running: '运行中',
    success: '已完成',
    failed: '失败',
    cancelled: '已取消',
    waiting_review: '待审核',
    skipped: '已跳过',
  },
  required: '不能为空',
  expand: '展开',
  collapse: '收起',
}
```

- [x] [DONE] 2026-06-25 **Step 2: 补全 workshop / pipelineRun / pipelineResult / assets 命名空间**

对照 spec 第 9.1 节的 i18n 结构，补全 `workshop`（行 510-524）、`pipelineRun`（行 527-556）、`pipelineResult`（行 559-583）、`assets`（行 586-607）命名空间的缺失 key。

特别注意补全：
- `pipelineResult.steps.preparing`、`pipelineResult.steps.completed`
- `pipelineResult.stepStatus.*`（所有状态）
- `pipelineResult.sse.*`（连接状态）
- `pipelineRun.stepType.*`（所有步骤类型）
- `assets.type.prop`、`assets.type.brand`（缺失的类型）

- [x] [DONE] 2026-06-25 **Step 3: 在 admin.roles.permissions 追加 pipeline 权限**

在 `frontend/src/i18n/zh-CN.ts` 约行 1640-1650 的 `admin.roles.permissions` 追加：

```typescript
'pipeline:run': '流水线运行',
'pipeline:save_asset': '保存资产',
```

- [x] [DONE] 2026-06-25 **Step 4:（可选）提交**

```bash
git add frontend/src/i18n/zh-CN.ts
git commit -m "feat(i18n): 补全 pipeline 命名空间和权限点展示"
```

---

### Task 22: 补全 i18n/en-US.ts — 对应英文 key

**Files:**
- Modify: `frontend/src/i18n/en-US.ts`

- [x] [DONE] 2026-06-25 **Step 1: 同步补全英文 key**

对照 Task 21 的中文 key，在 `frontend/src/i18n/en-US.ts` 中补全对应英文。

```typescript
common: {
  status: {
    pending: 'Pending',
    running: 'Running',
    success: 'Completed',
    failed: 'Failed',
    cancelled: 'Cancelled',
    waiting_review: 'Under Review',
    skipped: 'Skipped',
  },
  required: 'is required',
  expand: 'Expand',
  collapse: 'Collapse',
}

pipelineRun: {
  stepType: {
    llm_generate: 'LLM Script Generation',
    image_batch: 'Batch Image Generation',
    video_batch: 'Batch Video Generation',
    ffmpeg_composite: 'Video Composition',
    tts_generate: 'Voice Generation',
    human_review: 'Manual Review',
  },
}

pipelineResult: {
  steps: {
    preparing: 'Preparing execution environment',
    completed: 'Completed {completed}/{total}',
  },
  stepStatus: {
    pending: 'Pending',
    running: 'Generating',
    success: 'Completed',
    failed: 'Failed',
    cancelled: 'Cancelled',
    skipped: 'Skipped',
    processing: 'Processing',
  },
  sse: {
    connecting: 'Connecting',
    connected: 'Live',
    reconnecting: 'Reconnecting',
    polling: 'Polling',
  },
}

assets: {
  type: {
    prop: 'Prop',
    brand: 'Brand',
  },
}

admin: {
  roles: {
    permissions: {
      'pipeline:run': 'Pipeline Run',
      'pipeline:save_asset': 'Save Asset',
    },
  },
}
```

- [x] [DONE] 2026-06-25 **Step 2:（可选）提交**

```bash
git add frontend/src/i18n/en-US.ts
git commit -m "feat(i18n): 补全 pipeline 英文翻译"
```

---

### Task 23: router/index.ts — pipeline 路由 meta 加 permission

**Files:**
- Modify: `frontend/src/router/index.ts`（行 67-83 的 pipeline 路由）

- [x] [DONE] 2026-06-25 **Step 1: 为 pipeline 路由添加 permission meta**

修改 `frontend/src/router/index.ts` 的 pipeline 路由定义（约行 67-83）：

```typescript
// 修改前
{ path: '/workshop', component: WorkshopView, meta: { requiresAuth: true, titleKey: 'workshop.title' } },
{ path: '/workshop/run/:templateId', component: PipelineRunView, meta: { requiresAuth: true, titleKey: 'pipelineRun.title' } },
{ path: '/workshop/result/:runId', component: PipelineResultView, meta: { requiresAuth: true, titleKey: 'pipelineResult.title' } },
{ path: '/assets', component: AssetsView, meta: { requiresAuth: true, titleKey: 'assets.title' } },

// 修改后
{ path: '/workshop', component: WorkshopView, meta: { requiresAuth: true, permission: 'pipeline:run', titleKey: 'workshop.title' } },
{ path: '/workshop/run/:templateId', component: PipelineRunView, meta: { requiresAuth: true, permission: 'pipeline:run', titleKey: 'pipelineRun.title' } },
{ path: '/workshop/result/:runId', component: PipelineResultView, meta: { requiresAuth: true, permission: 'pipeline:run', titleKey: 'pipelineResult.title' } },
{ path: '/assets', component: AssetsView, meta: { requiresAuth: true, permission: 'pipeline:save_asset', titleKey: 'assets.title' } },
```

- [x] [DONE] 2026-06-25 **Step 2:（可选）提交**

```bash
git add frontend/src/router/index.ts
git commit -m "feat(router): pipeline 路由 meta 加 permission 权限校验"
```

---

## Phase 8: 设计文档更新

### Task 24: 更新 docs/01-creative-pipeline-overview.md 第 8 章 API 路径

**Files:**
- Modify: `docs/01-creative-pipeline-overview.md`

- [x] [DONE] 2026-06-25 **Step 1: 更新 API 路径反映后端实际实现**

在 `docs/01-creative-pipeline-overview.md` 第 8 章中，替换以下 API 路径：

| 旧路径 | 新路径 |
|--------|--------|
| `/api/styles` | `/api/pipeline/styles` |
| `/api/assets` | `/api/pipeline/assets` |
| `/api/script-templates` | `/api/pipeline/script-templates` |
| SSE `/stream` | `/events` |
| 模板详情按 `{key}` | 按 `{id}` |
| 预估积分 `/estimate` | `/estimate-credits` |

- [x] [DONE] 2026-06-25 **Step 2:（可选）提交**

```bash
git add docs/01-creative-pipeline-overview.md
git commit -m "docs: 更新 01 设计文档 API 路径，反映后端实际实现"
```

---

### Task 25: 更新 docs/02-creative-pipeline-todolist.md 标记完成状态

**Files:**
- Modify: `docs/02-creative-pipeline-todolist.md`

- [x] [DONE] 2026-06-25 **Step 1: 标记前端重构相关任务完成状态**

根据本计划实施进度，更新 `docs/02-creative-pipeline-todolist.md` 中对应任务的状态。

- [x] [DONE] 2026-06-25 **Step 2:（可选）提交**

```bash
git add docs/02-creative-pipeline-todolist.md
git commit -m "docs: 更新 02 todolist 标记前端重构完成状态"
```

---

## 验收检查

实施完成后，对照 spec 第 14 节验收标准逐项检查：

### 功能验收
- [x] [DONE] 2026-06-25 WorkshopView 页面样式正常显示（CSS 变量生效）
- [x] [DONE] 2026-06-25 WorkshopView 模板卡片「使用」按钮可点击跳转
- [x] [DONE] 2026-06-25 PipelineRunView 积分预估复用 useCreditEstimate
- [x] [DONE] 2026-06-25 PipelineRunView 风格选择复用 StyleSelector
- [x] [DONE] 2026-06-25 PipelineResultView 返回按钮正常跳转 /workshop
- [x] [DONE] 2026-06-25 PipelineResultView 步骤类型标签正确显示
- [x] [DONE] 2026-06-25 PipelineResultView 每个步骤完成后即时展示产出
- [x] [DONE] 2026-06-25 PipelineResultView 底部最终结果区仅在有最终视频时显示
- [x] [DONE] 2026-06-25 AssetsView 资产类型 tab 为 all/character/prop/scene/brand
- [x] [DONE] 2026-06-25 AssetsView 使用 assetStore 加载数据

### 集成验收
- [x] [DONE] 2026-06-25 pipeline 运行注册到全局 TaskQueuePanel
- [x] [DONE] 2026-06-25 TaskCard 显示 pipeline 任务进度，点击跳转
- [x] [DONE] 2026-06-25 SSE 收到 step_completed 后触发 historyRefreshSignal
- [x] [DONE] 2026-06-25 usePipelineSSE 复用 userStore.token，401 处理对齐 client.ts

### 规范验收
- [x] [DONE] 2026-06-25 所有页面 CSS 变量使用 --agnes-* 前缀
- [x] [DONE] 2026-06-25 所有页面文案走 i18n（零硬编码中文）
- [x] [DONE] 2026-06-25 所有 pipeline 类型在 types/index.ts
- [x] [DONE] 2026-06-25 api/pipeline.ts 只导出请求函数，不内联类型
- [x] [DONE] 2026-06-25 路由 meta 含 permission 字段
- [x] [DONE] 2026-06-25 manuallClosed 拼写错误已修复

### 不破坏现有功能
- [x] [DONE] 2026-06-25 画布模块功能正常（canvasAsset 重命名后）
- [x] [DONE] 2026-06-25 image/video 生成功能正常
- [x] [DONE] 2026-06-25 chat 功能正常
- [x] [DONE] 2026-06-25 plaza 广场功能正常
- [x] [DONE] 2026-06-25 TaskQueue 现有 image/video/chat/canvas 任务展示正常

---

## 实施说明

1. **commit 时机**：每个 Task 末尾标注「（可选）提交」— 系统约定 NEVER commit unless user asks。实施时可按 Phase 批量提交，或由用户决定时机。
2. **不执行构建/语法检查**：遵循 AGENTS.md，每次写完代码不需要检查语法，用户会自己做。
3. **组件 import 路径**：计划中 `@/components/xxx` 路径需对照项目实际 `components/index.ts` 导出确认。若组件未全局注册，使用相对路径。
4. **PromptTemplates / ImageWithWatermark / ImageViewer / ImageUploader props**：计划中的 props 名称为推测，实施时需对照实际组件签名调整。
5. **渐进式产物可见性**：Task 19 的左右分栏布局是核心体验改动，确保步骤完成即展示产出，不等最终结果。

---

*计划结束*
