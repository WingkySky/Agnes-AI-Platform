# 创意流水线系统 — 开发任务清单

> 版本：v1.1（前端重构后）
> 基于文档：[01-creative-pipeline-overview.md](./01-creative-pipeline-overview.md)、[03-pipeline-frontend-refactor-design.md](./03-pipeline-frontend-refactor-design.md)

---

## 完成状态说明

| 状态 | 标记 | 说明 |
|------|------|------|
| ✅ 已完成 | `[x]` | 代码已实现并可用 |
| ⚠️ 待修复/完善 | `[~]` | 基础框架已有，但需要修复bug或补全功能 |
| ❌ 未开始 | `[ ]` | 尚未实现 |
| 🚫 暂缓 | `[-]` | 后续Phase实现，当前不做 |

---

## 前端重构里程碑（2026-06 完成）

完成创意流水线前端四页面 + 基础设施重构，关键改动：

- **Store 拆分**：pipeline / styles / asset 三分离；新增 canvasAsset.ts 专门承载画布素材库（保留 store id='asset' 避免 localforage 数据失效）
- **新组件**：PipelineProgress / StepResultGallery / StyleSelector / AssetCard / AssetDetailModal
- **渐进式产物可见性**：PipelineResultView 步骤完成即展示产出，不等最终结果；底部最终结果区仅在有最终视频时显示
- **深度复用**：PipelineRunView 复用 useCreditEstimate + StyleSelector；TaskCard 复用并扩展 pipeline 分支
- **规范统一**：CSS 变量统一 `--agnes-*` 前缀，文案全部走 i18n（零硬编码中文），pipeline 类型集中在 types/index.ts
- **集成打通**：pipeline 运行注册到全局 TaskQueuePanel；SSE 收到 step_completed 后触发 historyRefreshSignal；usePipelineSSE 复用 userStore.token，401 处理对齐 client.ts

详见实施计划：[docs/superpowers/plans/2026-06-25-pipeline-frontend-refactor.md](./superpowers/plans/2026-06-25-pipeline-frontend-refactor.md)

---

## Phase 1：基础骨架（MVP）— 目标：跑通完整漫剧流水线

### 1.1 后端：数据库 & 模型层

| 状态 | 任务 | 文件/位置 | 备注 |
|------|------|-----------|------|
| ✅ | 创建 pipeline_templates 表 | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/models/pipeline.py#L13-L59) | 流水线模板表 |
| ✅ | 创建 script_templates 表 | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/models/pipeline.py#L61-L106) | 剧本模板表 |
| ✅ | 创建 style_presets 表 | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/models/pipeline.py#L108-L158) | 风格预设表 |
| ✅ | 创建 assets 表 | [asset.py](file:///Users/skywing/agnes-platform/backend/app/models/asset.py#L13-L64) | 资产库表 |
| ✅ | 创建 pipeline_runs 表 | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/models/pipeline.py#L160-L208) | 流水线执行实例表 |
| ✅ | 创建 pipeline_steps 表 | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/models/pipeline.py#L210-L268) | 步骤执行记录表 |
| ✅ | generations 表添加 pipeline 关联字段 | [generation.py](file:///Users/skywing/agnes-platform/backend/app/models/generation.py#L64-L68) | 已添加 pipeline_run_id 和 pipeline_step_key |
| ✅ | Pydantic Schema - 流水线相关 | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/schemas/pipeline.py) | |
| ✅ | Pydantic Schema - 资产相关 | [assets.py](file:///Users/skywing/agnes-platform/backend/app/schemas/assets.py) | |
| ✅ | 修复种子数据与模型字段不匹配问题 | [seed_pipeline_data.py](file:///Users/skywing/agnes-platform/backend/seed_pipeline_data.py) | 风格预设12个（含新增6个），剧本模板3个（添加 structure/output_schema 等字段） |

---

### 1.2 后端：资产库基础服务

| 状态 | 任务 | 文件/位置 | 备注 |
|------|------|-----------|------|
| ✅ | StylePreset CRUD 服务 | [style_service.py](file:///Users/skywing/agnes-platform/backend/app/services/style_service.py) | |
| ✅ | ScriptTemplate CRUD 服务 | [script_template_service.py](file:///Users/skywing/agnes-platform/backend/app/services/script_template_service.py) | 包含 Jinja2 模板渲染 |
| ✅ | Asset CRUD 服务 | [asset_library.py](file:///Users/skywing/agnes-platform/backend/app/services/asset_library.py) | |
| ⚠️ | 风格预设提示词构建方法完善 | [style_service.py](file:///Users/skywing/agnes-platform/backend/app/services/style_service.py) | build_prompt_with_style 需要正确拼接各字段 |
| ✅ | 资产从生成记录保存功能 | [asset_library.py](file:///Users/skywing/agnes-platform/backend/app/services/asset_library.py#L146-L186) | 已实现 save_asset_from_generation；路由已暴露 POST /pipeline/assets/save-from-generation |

---

### 1.3 后端：流水线执行引擎

| 状态 | 任务 | 文件/位置 | 备注 |
|------|------|-----------|------|
| ✅ | DAG 依赖解析 + 就绪步骤判断 | [engine.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/engine.py#L283-L302) | _get_ready_steps() |
| ✅ | 步骤执行器注册机制 | [steps/__init__.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/steps/__init__.py) | register_step_executor + create_step_executor |
| ✅ | BaseStepExecutor 抽象基类 | [base.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/steps/base.py#L51-L133) | validate/execute/estimate_credits/cleanup |
| ✅ | StepExecutionContext 上下文类 | [base.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/steps/base.py#L13-L50) | |
| ✅ | 状态机管理（pipeline + step） | [engine.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/engine.py#L403-L500) | pending/running/success/failed/cancelled |
| ✅ | 并发步骤调度执行 | [engine.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/engine.py#L233-L282) | asyncio.gather 并发执行就绪步骤 |
| ✅ | 失败自动重试 | [engine.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/engine.py#L356-L373) | retry_count 控制 |
| ✅ | 断点续跑机制 | [engine.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/engine.py#L166-L179) | resume() 从数据库恢复状态继续 |
| ✅ | llm_generate 步骤执行器 | [llm_generate.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/steps/llm_generate.py) | LLM剧本生成，多层JSON解析容错 |
| ✅ | image_batch 步骤执行器 | [image_batch.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/steps/image_batch.py) | 批量图片生成，并发控制，风格应用 |
| ✅ | video_batch 步骤执行器 | [video_batch.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/steps/video_batch.py) | 批量视频生成，创建+轮询两阶段 |
| ⚠️ | 积分实际逐步扣减 | [engine.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/engine.py#L427-L469) | 已添加 _precharge_credits/_confirm_step_credits/_refund_step_credits/_refund_remaining_credits 方法 |
| ⚠️ | 生成结果保存到 generations 表 | [integration.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/integration.py) | 已在 image_batch.py 和 video_batch.py 中调用 save_batch_generations |
| ⚠️ | 风格预设正确应用到提示词 | [image_batch.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/steps/image_batch.py#L197-L200) | 需要确认 style_service.build_prompt_with_style 实现正确 |
| ✅ | 视频生成正确使用 width/height/num_frames | [video_batch.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/steps/video_batch.py#L255-L267) | 已修正 mode 为 image2video，Agnes客户端自动转换参数 |
| ✅ | 条件步骤执行（condition 字段） | [engine.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/engine.py#L311-L318) | 已添加 _evaluate_condition 和 _get_nested_value 方法 |
| ✅ | same-user 并发流水线限制（最多2个） | [run_service.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/run_service.py#L288-L308) | 已实现 _check_concurrency_limit，限制 MAX_PARALLEL_RUNS_PER_USER=2 |
| ✅ | 流水线运行时积分不足检查 | [run_service.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/run_service.py#L159-L220) | 已在 create_and_start_run 中同步预扣积分，不足立即抛 402；retry_run/retry_step 也有重试前积分检查 |

---

### 1.4 后端：SSE 进度推送

| 状态 | 任务 | 文件/位置 | 备注 |
|------|------|-----------|------|
| ✅ | SSE Manager 实现 | [sse_manager.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/sse_manager.py) | 订阅/取消订阅/广播/回调工厂 |
| ✅ | SSE 路由端点 | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L385-L437) | /pipeline/runs/{id}/events，心跳保活 |
| ✅ | 进度事件类型 | 路由中已有注释 | step_started/step_progress/step_completed/step_failed/pipeline_completed |
| ⚠️ | step_progress 事件推送 | [engine.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/engine.py) | 长步骤（如批量生成）需要推送中间进度 |

---

### 1.5 后端：API 路由

| 状态 | 任务 | 文件/位置 | 备注 |
|------|------|-----------|------|
| ✅ | GET /pipeline/templates | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L70-L94) | 模板列表（分类筛选、搜索、分页） |
| ✅ | GET /pipeline/templates/{id} | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L97-L108) | 模板详情 |
| ✅ | POST /pipeline/templates/{id}/estimate-credits | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L111-L120) | 积分预估 |
| ✅ | POST /pipeline/runs | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L127-L148) | 创建并启动流水线 |
| ✅ | GET /pipeline/runs | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L151-L177) | 我的流水线列表 |
| ✅ | GET /pipeline/runs/{id} | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L180-L197) | 运行详情 |
| ✅ | GET /pipeline/runs/{id}/steps | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L200-L216) | 步骤列表 |
| ✅ | POST /pipeline/runs/{id}/retry | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L219-L230) | 重试失败流水线 |
| ✅ | POST /pipeline/runs/{id}/cancel | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L233-L241) | 取消流水线 |
| ✅ | GET /pipeline/styles | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L248-L272) | 风格预设列表 |
| ✅ | GET /pipeline/styles/{id} | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L275-L286) | 风格详情 |
| ✅ | GET /pipeline/script-templates | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L293-L317) | 剧本模板列表 |
| ✅ | GET /pipeline/script-templates/{id} | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L320-L331) | 剧本模板详情 |
| ✅ | GET /pipeline/assets | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L338-L364) | 资产库列表 |
| ✅ | GET /pipeline/assets/{id} | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L367-L378) | 资产详情 |
| ✅ | GET /pipeline/runs/{id}/events | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L385-L437) | SSE 进度流 |
| ✅ | POST /pipeline/runs/{id}/steps/{key}/retry | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L233-L246) | 单步重试（已添加） |
| ❌ | POST /pipeline/templates | 新增路由 | 用户创建自定义模板 |
| ❌ | PUT /pipeline/templates/{id} | 新增路由 | 更新模板 |
| ❌ | DELETE /pipeline/templates/{id} | 新增路由 | 删除模板 |
| ❌ | POST /pipeline/templates/{id}/duplicate | 新增路由 | 复制模板 |
| ❌ | POST /pipeline/assets | 新增路由 | 创建资产 |
| ❌ | PUT /pipeline/assets/{id} | 新增路由 | 更新资产（创建新版本） |
| ❌ | DELETE /pipeline/assets/{id} | 新增路由 | 删除资产 |
| ✅ | POST /pipeline/assets/save-from-generation | [pipeline.py](file:///Users/skywing/agnes-platform/backend/app/routes/pipeline.py#L479) | 从生成记录保存为资产（已实现） |
| ❌ | POST /pipeline/styles | 新增路由 | 创建自定义风格 |
| ❌ | PUT /pipeline/styles/{id} | 新增路由 | 更新风格 |
| ❌ | DELETE /pipeline/styles/{id} | 新增路由 | 删除风格 |

---

### 1.6 后端：内置模板 & 种子数据

| 状态 | 任务 | 文件/位置 | 备注 |
|------|------|-----------|------|
| ⚠️ | 修复风格预设种子数据 | [seed_pipeline_data.py](file:///Users/skywing/agnes-platform/backend/seed_pipeline_data.py#L44-L153) | 字段名需匹配模型（visual_prefix/lighting/color_palette 等） |
| ✅ | 3个剧本模板 | [seed_pipeline_data.py](file:///Users/skywing/agnes-platform/backend/seed_pipeline_data.py#L160-L332) | 短篇漫剧/产品广告/情感短剧 |
| ⚠️ | 标准漫剧流水线模板修复 | [seed_pipeline_data.py](file:///Users/skywing/agnes-platform/backend/seed_pipeline_data.py#L340-L455) | steps_config 需与执行器兼容，视频参数需修正 |
| ⚠️ | 产品广告流水线模板修复 | [seed_pipeline_data.py](file:///Users/skywing/agnes-platform/backend/seed_pipeline_data.py#L456-L546) | 同上 |
| ❌ | 种子数据幂等性完善 | seed_pipeline_data.py | 目前只判断key，字段更新需要支持 |

---

### 1.7 后端：与现有系统集成

| 状态 | 任务 | 文件/位置 | 备注 |
|------|------|-----------|------|
| ⚠️ | 积分实际逐步扣减 | credits_service + engine | 已添加 _precharge_credits/_confirm_step_credits/_refund_step_credits/_refund_remaining_credits 方法；预扣移至 create_and_start_run 同步执行 |
| ❌ | 内容审核集成（仅推广场） | moderation_service | 创意工坊产出默认 is_public=False，不需审核；仅当用户主动分享到广场时才走审核流程 |
| ❌ | TaskQueue 集成（后端部分） | 与现有 poller 协调 | 流水线任务状态同步 |
| ✅ | 流水线运行时积分不足检查 | [run_service.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/run_service.py#L159-L220) | 已在 create_and_start_run 中同步预扣，不足立即抛 402；retry_run/retry_step 重试前也检查积分 |

---

### 1.8 前端：API 层

| 状态 | 任务 | 文件/位置 | 备注 |
|------|------|-----------|------|
| ✅ | 创建 pipeline API 封装 | [pipeline.ts](file:///Users/skywing/agnes-platform/frontend/src/api/pipeline.ts) | 所有流水线相关API调用；类型已迁移到 types/index.ts，本文件只保留请求函数 + re-export 类型 |
| ✅ | 新增 buildSSEUrl 构造 SSE 订阅 URL | [pipeline.ts](file:///Users/skywing/agnes-platform/frontend/src/api/pipeline.ts) | 供 usePipelineSSE 使用，统一 URL 拼装 |
| ✅ | SSE 客户端封装（composable） | [usePipelineSSE.ts](file:///Users/skywing/agnes-platform/frontend/src/composables/usePipelineSSE.ts) | 连接SSE、解析事件、自动重连；复用 userStore.token，401 处理对齐 client.ts |
| ✅ | 扩展 useCreditEstimate 支持 type='pipeline' | [useCreditEstimate.ts](file:///Users/skywing/agnes-platform/frontend/src/composables/useCreditEstimate.ts) | PipelineRunView 积分预估复用此 composable |

---

### 1.9 前端：状态管理（Stores）

| 状态 | 任务 | 文件/位置 | 备注 |
|------|------|-----------|------|
| ✅ | pipeline store | [pipeline.ts](file:///Users/skywing/agnes-platform/frontend/src/stores/pipeline.ts) | 当前运行实例、步骤状态、SSE连接管理；已移除 styles/scriptTemplates（拆分到 styles store），重写 createRun |
| ✅ | styles store（风格预设 + 剧本模板） | [styles.ts](file:///Users/skywing/agnes-platform/frontend/src/stores/styles.ts) | 从 pipeline store 拆分，专门管理风格预设列表和剧本模板 |
| ✅ | assets store（创意资产库） | [asset.ts](file:///Users/skywing/agnes-platform/frontend/src/stores/asset.ts) | 已重写为创意流水线资产库（与画布素材库分离） |
| ✅ | canvasAsset store（画布素材库） | [canvasAsset.ts](file:///Users/skywing/agnes-platform/frontend/src/stores/canvasAsset.ts) | 从原 asset.ts 重命名而来，保留 store id='asset' 避免 localforage 数据失效 |
| ✅ | taskQueue store 扩展 pipeline 支持 | [taskQueue.ts](file:///Users/skywing/agnes-platform/frontend/src/stores/taskQueue.ts) | 新增 registerPipelineTask / updatePipelineTask；source='pipeline' 不参与轮询 |
| ✅ | permission store 新增 pipeline 权限点 | [permission.ts](file:///Users/skywing/agnes-platform/frontend/src/stores/permission.ts) | ROLE_PERMISSIONS 加入 pipeline:run、pipeline:save_asset |

---

### 1.10 前端：页面 & 路由

| 状态 | 任务 | 文件/位置 | 备注 |
|------|------|-----------|------|
| ✅ | 创意工坊入口页面（模板市场） | [WorkshopView.vue](file:///Users/skywing/agnes-platform/frontend/src/views/WorkshopView.vue) | 分类侧边栏 + 搜索 + 模板卡片网格；CSS 变量统一 `--agnes-*` 前缀，文案走 i18n，复用 pipelineStore |
| ✅ | 模板配置 & 运行页 | [PipelineRunView.vue](file:///Users/skywing/agnes-platform/frontend/src/views/PipelineRunView.vue) | 左侧参数配置表单 + 右侧实时进度；复用 useCreditEstimate + StyleSelector |
| ✅ | 流水线结果详情页 | [PipelineResultView.vue](file:///Users/skywing/agnes-platform/frontend/src/views/PipelineResultView.vue) | 结果展示 + 步骤详情Tab + 操作按钮；渐进式产物可见性（步骤完成即展示产出，不等最终结果）；底部最终结果区仅在有最终视频时显示 |
| ✅ | 我的资产库页 | [AssetsView.vue](file:///Users/skywing/agnes-platform/frontend/src/views/AssetsView.vue) | Tab 切换（all/character/prop/scene/brand）+ 网格视图；使用 assetStore 加载数据 |
| ✅ | 前端路由配置 | [router/index.ts](file:///Users/skywing/agnes-platform/frontend/src/router/index.ts) | 已添加 /workshop、/workshop/run/:templateId、/workshop/result/:runId、/assets 路由，meta 含 permission 字段 |
| ✅ | 菜单配置 | [menus.ts](file:///Users/skywing/agnes-platform/frontend/src/config/menus.ts) | 已添加「创意工坊」「我的资产」菜单项 |

---

### 1.11 前端：核心组件

| 状态 | 任务 | 文件/位置 | 备注 |
|------|------|-----------|------|
| ✅ | 模板卡片 | [WorkshopView.vue](file:///Users/skywing/agnes-platform/frontend/src/views/WorkshopView.vue) | 模板卡片（缩略图+名称+分类+使用次数）已内联到 WorkshopView，未单独抽 TemplateCard.vue |
| ✅ | PipelineProgress.vue | [PipelineProgress.vue](file:///Users/skywing/agnes-platform/frontend/src/components/pipeline/PipelineProgress.vue) | 步骤列表+当前步骤状态+进度条 |
| ✅ | StepResultGallery.vue | [StepResultGallery.vue](file:///Users/skywing/agnes-platform/frontend/src/components/pipeline/StepResultGallery.vue) | 步骤结果图片/视频画廊；用于渐进式产物可见性 |
| ✅ | StyleSelector.vue | [StyleSelector.vue](file:///Users/skywing/agnes-platform/frontend/src/components/pipeline/StyleSelector.vue) | 风格选择器（网格+预览）；PipelineRunView 复用 |
| ✅ | AssetCard.vue | [AssetCard.vue](file:///Users/skywing/agnes-platform/frontend/src/components/pipeline/AssetCard.vue) | 资产卡片（位于 pipeline/ 目录下） |
| ✅ | AssetDetailModal.vue | [AssetDetailModal.vue](file:///Users/skywing/agnes-platform/frontend/src/components/pipeline/AssetDetailModal.vue) | 资产详情弹窗（位于 pipeline/ 目录下） |
| ✅ | TaskCard.vue 扩展 pipeline 分支 | [TaskCard.vue](file:///Users/skywing/agnes-platform/frontend/src/components/TaskCard.vue) | 支持 source='pipeline'，展示步骤进度，点击跳转 pipeline-result |

---

### 1.12 前端：与现有模块集成

| 状态 | 任务 | 文件/位置 | 备注 |
|------|------|-----------|------|
| ✅ | TaskQueue 展示流水线任务 | [taskQueue.ts](file:///Users/skywing/agnes-platform/frontend/src/stores/taskQueue.ts) | 新增 source='pipeline' 分支，TaskQueuePanel 全局注册 pipeline 任务，TaskCard 点击跳转结果页 |
| ✅ | i18n 文案补充 | [zh-CN.ts](file:///Users/skywing/agnes-platform/frontend/src/i18n/zh-CN.ts) / [en-US.ts](file:///Users/skywing/agnes-platform/frontend/src/i18n/en-US.ts) | 流水线相关所有文案 + 权限点展示（pipeline:run、pipeline:save_asset） |
| ✅ | 权限指令适配 | [permission.ts](file:///Users/skywing/agnes-platform/frontend/src/stores/permission.ts) | ROLE_PERMISSIONS 加入 pipeline 权限点，路由 meta 含 permission 字段 |
| ✅ | CanvasView 引用路径迁移 | [CanvasView.vue](file:///Users/skywing/agnes-platform/frontend/src/views/CanvasView.vue) | import 路径从 asset.ts 改为 canvasAsset（保留 store id='asset'） |
| ✅ | CanvasAssetLibrary 引用路径迁移 | [CanvasAssetLibrary.vue](file:///Users/skywing/agnes-platform/frontend/src/components/canvas/CanvasAssetLibrary.vue) | import 路径从 asset.ts 改为 canvasAsset |

---

### 1.13 Phase 1 验收标准

- [ ] 后端服务启动正常，种子数据可成功写入
- [ ] 选择「标准漫剧」模板，输入主题，一键启动流水线
- [ ] SSE实时推送每一步进度（剧本→角色图→分镜图→视频）
- [ ] 每步结果可在结果页查看
- [ ] 失败可重试，取消可停止
- [x] 前端页面可正常访问和使用（前端重构已完成，详见 1.8~1.12 章节）
- [ ] 生成的图片/视频在历史记录中可追溯到流水线来源

> 备注：前端重构（2026-06）已完成 1.8~1.12 全部任务，剩余验收项依赖后端种子数据与执行引擎的端到端联调。

---

## Phase 2：成片合成 & 配音 — 目标：输出完整带字幕配音视频

| 状态 | 任务 | 说明 |
|------|------|------|
| ✅ | ffmpeg_composite 步骤执行器 | [ffmpeg_composite.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/steps/ffmpeg_composite.py) 视频拼接（concat demuxer + copy/reencode fallback）、字幕烧录（drawtext）、BGM混合（amix）、配音替换 |
| 🚫 | SRT字幕生成 | 从剧本对白生成SRT格式字幕文件（当前用 drawtext 直接烧录，未生成独立 SRT） |
| ⚠️ | 字幕样式配置 | 当前固定样式（白字+黑底框），字体、大小、颜色、位置等可配置项后续迭代 |
| ✅ | tts_generate 步骤执行器 | [tts_generate.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/steps/tts_generate.py) 使用 edge-tts，角色声音分配（按性别），说话者解析 |
| ✅ | 音频混音 | ffmpeg_composite 中实现：配音替换原音轨 + BGM amix 混合 |
| ⚠️ | 时间轴对齐 | 当前按分镜 index 顺序拼接，未按 duration 精确对齐（简单 concat） |
| 🚫 | TimelinePreview 组件 | 可视化时间轴（分镜+字幕+配音），后续迭代 |
| 🚫 | 字幕编辑器 | 生成后可手动修改字幕文本和时间，后续迭代 |
| ⚠️ | 成片播放器 | 当前用原生 `<video>` 标签，字幕切换/倍速播放等后续迭代 |
| ✅ | 新增内置模板 | [seed_pipeline_data.py](file:///Users/skywing/agnes-platform/backend/seed_pipeline_data.py) 新增"科普短片"模板；现有"标准漫剧"和"产品广告"模板已追加 tts_generate + ffmpeg_composite 步骤 |
| 🚫 | 下载带水印成片 | 集成 watermark_service，后续迭代 |

---

## Phase 3：画布深度融合 — 目标：双向打通流水线与无限画布

| 状态 | 任务 | 说明 |
|------|------|------|
| 🚫 | 导出到画布API | /pipeline/runs/{id}/export-canvas 返回nodes+edges+positions |
| 🚫 | 画布导入功能 | CanvasView检测URL参数?import=pipeline:{id}，自动加载节点 |
| 🚫 | 自动布局算法 | 按流程排列节点（剧本→角色→分镜→视频） |
| 🚫 | 画布右键菜单 | 「用选中资产启动流水线」 |
| 🚫 | 智能参数填充 | 选中图片→角色/风格，选中文本→主题，预填到配置页 |
| 🚫 | 节点元数据标记 | 导出的节点带pipeline_run_id/step_key元数据 |
| 🚫 | 画布内选择性重跑 | 右键某节点→「重新生成此步」，只重跑该步及下游 |
| 🚫 | 可视化流水线编辑器 | 拖拽式编辑模板（类似画布节点），步骤节点+连线定义依赖 |
| 🚫 | 自定义模板保存 | 可视化编辑后保存为用户自定义模板 |

---

## Phase 4：资产生态 & 社区 — 目标：UGC内容闭环

| 状态 | 任务 | 说明 |
|------|------|------|
| 🚫 | 资产发布到广场 | 资产审核流程（复用现有moderation） |
| 🚫 | 广场新增「资产」分类 | 浏览、搜索、筛选公开资产 |
| 🚫 | 收藏到我的资产库 | 一键收藏别人分享的资产 |
| 🚫 | 资产评分&评论 | 五星评分+文字评论 |
| 🚫 | 模板市场广场 | 用户分享模板，分类、搜索、推荐 |
| 🚫 | 「使用此模板」一键创建 | 从广场作品/模板直接进入配置页 |
| 🚫 | 广场作品提取资产 | 详情页「提取角色」「提取风格」按钮 |
| 🚫 | 资产版本管理完善 | 版本对比diff、版本回滚、分支版本 |
| 🚫 | 资产点赞/使用量统计 | 反范式缓存，热门排序 |
| 🚫 | 模板收藏功能 | template_favorites表 |

---

## 优先级排序建议（Phase 1 执行顺序）

### 第一优先级（后端修复 & 核心功能打通）
1. 修复种子数据字段不匹配问题
2. 修复视频生成参数（width/height/num_frames）
3. 完善积分实际扣减逻辑
4. 完善生成结果写入generations表
5. 补充单步重试API
6. 添加条件步骤执行支持
7. 后端端到端测试（跑通标准漫剧模板）

### 第二优先级（前端基础框架）— ✅ 已完成
1. ✅ 创建pipeline API封装
2. ✅ 创建SSE composable
3. ✅ 创建pipeline store（含 styles / asset 拆分）
4. ✅ 配置路由和菜单
5. ✅ 模板市场页面（WorkshopView）
6. ✅ i18n文案

### 第三优先级（前端核心页面）— ✅ 已完成
1. ✅ 模板配置&运行页（PipelineRunView）
2. ✅ PipelineProgress进度组件
3. ✅ SSE实时进度展示
4. ✅ 结果详情页（PipelineResultView，渐进式产物可见性）
5. ✅ StepResultGallery结果画廊组件

### 第四优先级（资产库 & 完善）
1. ✅ 资产库页面（AssetsView）
2. ❌ 自定义风格/模板CRUD
3. ✅ TaskQueue集成
4. ❌ 内容审核集成
5. ❌ 整体测试和bug修复

---

## 关键注意事项

1. **视频参数问题**：根据项目记忆，视频生成必须使用 `width/height/num_frames/frame_rate`，不能用 `aspect_ratio/duration/fps`；width和height必须是8的倍数；num_frames必须是8n+1格式。
2. **base64上传**：单图ti2vid使用纯base64（不带data:image前缀）直接上传，不经过中间URL转换，性能更好。
3. **i18n**：所有前端文案必须走国际化，不要硬编码中文。
4. **代码注释**：按照用户规则，功能模块需要备注信息，调整代码时检查不要删掉原有备注。
5. **不破坏现有功能**：所有改动增量添加，现有图片/视频/画布/广场功能不受影响。
6. **异步一致性**：后端全程使用async/await，不要混入同步阻塞调用。
7. **代码风格**：后端沿用现有FastAPI分层（routes/services/models/schemas），前端沿用Vue3+Element Plus+Pinia结构。

---

*文档结束*
