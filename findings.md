# Findings

## 项目事实（调研阶段确认过的）
- 画布自研 DOM/SVG：InfiniteCanvas.vue + stores/canvas.ts（1790 行）+ CanvasView.vue（3114 行）
- 节点 8 类：text/image/video/audio/config/tts/subtitle/compose（CanvasToolbar.vue:125-133）
- 连线类型校验在 stores/canvas.ts:19-45：tts/subtitle 只收 text 入边，compose 恰一 video 入边
- 生成链路：lib/canvas-generation.ts buildGenerationContext → createImageTask()/createVideoTask()（POST /api/images/tasks、/api/videos）→ taskQueue 轮询 → 回填节点自动连线
- taskQueue：localStorage 持久化，并发上限 5，RegisterCanvasTaskParams.panelId 支持画布回填（types/index.ts:557-565）
- 画布持久化：localforage，lib/canvas-storage.ts，key agnes_canvas_v2_{userId}
- 后端 LLM：agnes_client（/chat/completions）；chat_service._get_default_chat_model() 从 model_registry 取 "chat" 类型第一个
- 项目剧本生成范例：services/project/script_service.py regenerate_script → agnes_client POST chat/completions
- i18n：frontend/src/i18n/{zh-CN,en-US}.ts，组件内用 t('canvas.xxx')
- components/canvas/nodes/ 是空目录
- 无测试基建（无 vitest/pytest）；验证靠 vue-tsc + 手动
- StepGroup：CanvasStepGroup.vue + canvas-flow-analyzer.ts（执行顺序分析）
- 积分预估：useCreditEstimate + canvas-credits.ts

## Phase 0 新发现

### 生成执行器（重大复用点）
- `lib/canvas-generation.ts` 已有完整执行器：`executeMergeGeneration(configId, store)` / `executeMergeVideoGeneration(configId, store)` —— 从 config 节点构建上下文 → 自动创建 loading 结果节点（config 正右侧，连线 source_anchor right-middle）→ 创建任务 + 注册 taskQueue → 轮询 → 回填，fire-and-forget。**批量生成 = 创建 N 个带 prompt 的 config 节点 + 逐个调执行器**
- `buildGenerationContext` 只收集 config 的**直接上游**资源节点（image/text/video/audio；config/script 不算资源）。缺口：需加 3 行支持 `configNode.content.referenceImages` 快照合并（设计决策的角色图快照）
- 视频模式推断在 createVideoGenerationTask：有参考图 → image2video
- `pollImageTask` / `pollVideoTask` 已封装轮询

### 集成点
- 节点类型渲染：CanvasNode.vue 模板 v-else-if 分支（:57-345），script 加一个分支挂新组件
- 工具栏：CanvasToolbar.vue buttonGroups 组3（:125-134）加 tool-script → emit add-node payload 'script'
- CanvasView.vue：handleAddNode(:2387) → createNodeAtCenter(:2554)；NODE_DEFAULT_SIZES(:476) 需加 script 尺寸；getNodeName(:489)
- 连线校验：stores/canvas.ts validateConnectionTypes(:28-43) 是按 target 限制入边；script 限制出边需在开头加 source 检查
- StepGroup：store.addStep(:1696) + store.addPanelToStep(:1750)
- store.addPanel(input) 返回 id；updatePanel content 深合并（数组覆盖）
- i18n：zh-CN.ts canvas.toolbar(:1167) 加 toolScript；新增 canvas.script.* 命名空间
- 鉴权：后端用 get_current_user_optional（chat.py 模式）；storyboard 同样
- LLM 调用范例：script_service.py:116-127 → `agnes_client._post(f"{agnes_client.base_url}/chat/completions", body)`；默认聊天模型 `model_registry.get_models_by_type("chat")[0].id`
- 路由注册：main.py:361-386 include_router(prefix="/api")
- schemas 独立文件的先例存在（projects），camera_presets 是路由内联——按设计文档用 schemas/storyboard.py

### M2 待确认
- canvas-credits.ts 的预估函数签名（批量确认弹窗需要总价估算）
- GenerationQuickPanel/ConfigComposer 如何编辑 config 节点 prompt（重拍入口复用）

---

## 验证结论（2026-08-28 接手复核）

上一会话实际已完成 P0 全链路（M1/M2/M3），规划文档严重滞后。逐项核验结果：

### 已实现且接线闭合（痕迹）
- 后端：`backend/app/{routes,schemas,services}/storyboard.py` 三件套齐全；`main.py:388` 已注册 `prefix="/api"` → 路由 `/api/storyboard`；`main.py:67` 已 import。
- 前端新增：`api/storyboard.ts`、`lib/canvas-storyboard.ts`（含 M2 批量图 / M3 批量视频 / 单镜头图生视频）、`components/canvas/nodes/ScriptNodeContent.vue`。
- 接线：CanvasToolbar 已加 `tool-script`（Clapperboard）；CanvasNode.vue 已加 script 渲染分支 + 分镜出处标记；views/CanvasView.vue 已注册 `NODE_DEFAULT_SIZES.script`、`getNodeName.script`、`createNodeAtCenter` 的 script 分支（默认 content 正确）；Hover 工具栏已发 `derive-video`/`reshoot` 事件并由 views/CanvasView 接住（→ `deriveVideoForShot` / 重跑来源 config）。
- 数据正确性：`stores/canvas.ts` 的 `updatePanel` 用 `deepMerge` 深合并 content，编辑 story 不会清掉 shots；`buildGenerationContext` 已支持 `content.referenceImages` 快照合并（角色一致性生效）。

### 类型检查结论
- 脚本相关新文件 `vue-tsc` **零错误**。
- 全量 `vue-tsc -b --noEmit --force` 报 **35 错误**：CanvasView.vue 34 + CanvasNode.vue 1。
- 归因：将 CanvasView.vue / CanvasNode.vue 临时恢复到 HEAD 后错误数仍为 35 → **全部为历史遗留，与脚本功能无关**。
- 根因：大文件 `CanvasView.vue` 同时存在普通 `<script>` 块（396-416 行定义 ImageTaskPollStatus / VideoTaskPollStatus / ImageGenerationRequest / CanvasGenerationStore 等接口）与 `<script setup>` 块（418 行起）；未 `export` 的接口在 `<script setup>` 作用域内不可见，故报"找不到名称"。另有少数 `{}` 类型断言 / `number|undefined` / CustomEvent 转换问题，均属预有 image/video/subtitle 功能。
- 影响：仅阻塞 `npm run build`（其前置 `vue-tsc -b`），**不阻塞 `npm run dev` / `vite build`**（esbuild 不查类型）。团队此前大概率未以 `vue-tsc -b` 作为门禁。

### 后端冒烟
- `.venv/bin/python -c "from app.main import app"` 成功导入并初始化数据库；`/api/storyboard` 已出现在路由表中。

### 待决策
1. 是否修复 35 个历史类型错误以打通 `npm run build`（属构建健康度，超出 P0 脚本范围，且改动大文件有回归风险）。
2. 是否提交当前未提交的 P0 改动（后端 3 文件 + 前端多文件 + 规划文档，均相对 HEAD=1485174 为工作区改动）。
3. 手动冒烟六场景（单/多镜头、含台词、角色图引用、失败重试、30 镜头上限）需在运行环境用真实 LLM 走一遍。

