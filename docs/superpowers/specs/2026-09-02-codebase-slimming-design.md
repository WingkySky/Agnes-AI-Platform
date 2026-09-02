# 全局代码优化精简设计

## 背景

2026-09-02 完成全库（约 12.3 万行）四路简化审查（后端 services、后端 routes/schemas/models、前端 views、前端 stores/lib/components）。结论：预计可精简 5,000–6,000 行（≈4–5%），其中约七成是经 grep 全库验证零调用的纯死代码；另发现 4 个真实 Bug。病根是功能演进后旧实现未拆和图片/视频双版本成对复制，而非抽象过度。

审查完整发现清单以 2026-09-02 会话审查报告为准（下文只收录已确认纳入范围的条目）。

## 已确认的决策

| 决策点 | 结论 |
|---|---|
| 范围 | 全量推进：Bug 修复 + 死代码删除 + 重复收敛 + 规范修正 + 响应结构统一 |
| 存量未提交改动 | 先由本轮按功能整理提交，作为检查点，之后优化每阶段单独提交 |
| pipeline 风格元素组件族 | 确认删除（预设广场已用新画廊组件落地） |
| routes/logs.py | 保留（运维手工排查用） |
| rebuild-covers 两个路由 | 保留 |
| 响应结构 | 彻底统一为 status/message/data，前后端同步 |
| 执行策略 | 方案 A：六阶段串行，每阶段独立 commit，验证全绿才进下一阶段 |

## 阶段划分

| 阶段 | 内容 | 预计净减 |
|---|---|---|
| Phase 0 | 提交存量改动作检查点 | — |
| Phase 1 | 修 4 个真 Bug | — |
| Phase 2 | 删全部死代码 | ~3,500 行 |
| Phase 3 | 重复逻辑收敛 | ~1,500 行 |
| Phase 4 | 规范修正 | ~150 行 |
| Phase 5 | 响应结构彻底统一 | 小幅 |

## Phase 1 — Bug 修复

1. **WatermarkConfigView.vue 鉴权修复**：`localStorage.getItem('access_token')` 读取了不存在的 key（真实 key 为 `agnes.platform.auth.token`，stores/user.ts:25），上传水印 Logo 鉴权必然失败；且 `uploadHeaders` 为 setup 时一次性求值常量，重新登录后携带旧 token。修复：删除 `uploadHeaders`，上传请求改走统一 axios client（拦截器自动注入最新 token）。
2. **auth.py 重复路由删除**：`PUT /users/{user_id}/watermark` 与 `PUT /users/{user_id}/content-safety` 各注册两次（606/715、630/740 行），后注册者永不可达。删除 711–758 行死定义。
3. **chat.py media-callback 鉴权**：该回调当前完全无鉴权。实现时先确认调用方；默认方案为共享密钥校验（`.env` 配置 `AGNES_CALLBACK_KEY`，校验请求 header），若调用方无法携带密钥则降级为校验任务归属。这是本阶段唯一实现期决策点。
4. **chat_service.py 流式模型不一致**：流式第二轮请求（753 行）调 `_get_default_chat_model()` 漏传 `user_id`，用户有偏好模型时同一会话两轮会用不同模型。补传即可。

## Phase 2 — 死代码删除

所有条目均已经 grep 全库验证零调用。删除后如发现误删，从对应 commit 的 git 历史恢复。

### 后端（~1,150 行）

- `chat_service.py`：非流式 `chat()`（778–952 行，内部引用签名中不存在的变量，从未跑通）+ 仅被它调用的 `_download_image_as_base64`
- `style_service.py`：只保留 `get_style_by_id`，删除其余 7 个零调用函数
- `script_template_service.py`：只保留 pipeline.py 在用的函数
- `asset_library.py`：只保留 `get_asset_by_id` / `save_asset_from_generation` / `delete_asset` / `increment_use_count`
- `model_registry.py`：删除 24–117 行与 provider_registry.py 逐行重复的兼容层（含零调用的 `build_model_info`）
- 零散死函数：`agnes_client.create_tts_task`/`_aspect_ratio`；`provider_registry.find_provider_for_model`/`get_default_client`/`list_provider_ids`；`project/_generation_history.finalize_video_success/failure`；`style_element_service.increment_element_use_count`/`build_video_prompt_with_elements`；`credits_service.get_image_cost`/`get_video_cost`（同步兼容版）；`moderation_service.apply_moderation_result`；`upload_service.save_image_upload/save_video_upload`；`captcha_service.cleanup_expired_email_codes`；`system_config_service.get_all_configs`；`core/database.py` 同步 `SessionLocal`/`get_db`；`core/logging.py get_logger`/`log_with_context`；`chat_service._default_chat_model` 死赋值
- schemas 死类：`WizardStepEvent`、`HealthResponse`、`SubtitleClip`（连同 routes/projects.py 的死 import）
- `models/menu_item.py` 整文件（菜单实际存 system_configs 表，该表无读写）+ `models/__init__.py` 对应 import

### 前端（~2,300 行）

- camera 死链路：`stores/camera.ts`、`types/camera.ts`、`api/cameraPresets.ts` 的 4 个 CRUD 函数
- pipeline 风格元素组件族（已确认删除）：`components/WatermarkOverlay.vue`、`pipeline/HistoryImagePicker.vue`、`pipeline/StyleElementEditor.vue`、`pipeline/StyleElementPicker.vue`、`pipeline/StyleSelector.vue`，连带 `api/styleElement.ts` 死函数
- `stores/canvas.ts` 约 410 行死 action/getter（锁定、剪贴板、待创建连线、网格/对齐、隐藏/搜索定位、执行顺序等，均被组件内实现替代）+ 连带 `lib/canvas-flow-analyzer.ts` 死导出
- `lib/type-helpers_20260705_180610_340.ts` 备份文件；`type-helpers.ts` 收敛为只剩在用的 `getErrorMessage`
- api 层死函数：`images.createImage/getImageRecord`、`plaza` 点赞状态 2 个 + 5 个死响应类型、`projects.getScript/listFrameImages/listVideos`、`pipeline.getScriptTemplateDetail/getStylePresetDetail`、`presets.exportPresets/importPresets`、`admin.getPermissions` + 3 个死类型、`providers.listProviderModels`、`scenes.getScene`
- `types/index.ts`：重复定义的 `VideoStatusResponse`（删 237–247 行）+ `HealthResponse`/`BatchDeleteRequest`/`CreateSessionRequest`/`UpdateSessionRequest`/`TaskCreationResponse` 死类型
- stores 死 action：`project.ts` 的 `fetchMergeStatus`/`fetchSubtitleClips`/`fetchSubtitleStyle`/`fetchTimelineClips`；`canvasAsset.ts` 的 `updateAsset`/`importFromPipeline`；`styles.ts` 死 getter 与 `loadScriptTemplates`；`chat.ts` 的 `stopAllMediaPolls`
- lib 死导出：`canvas-image-ops.splitImage/rotateImage/upscaleImage`（`imageToBase64` 收为内部）、`canvas-storyboard.hasDerivedConfigs`（`buildAssetContexts` 收为内部）、`canvas-templates.onTemplateUserSwitch`、`canvas-storage.isStorageReady/currentCanvasUserKey`
- views 死项：`VideoView` 的 VIDEO_MODELS/DURATION_OPTIONS/FRAME_RATE_OPTIONS、`ImageView` 的 IMAGE_MODELS、`HistoryView` 的 `onDetailImageLoad`
- i18n：删除随死代码产生的孤儿 key（如 `lockPanel`/`toggleGrid`/`gridSize`），逐一 grep 确认无引用后再删，en-US/zh-CN 同步

## Phase 3 — 重复逻辑收敛

### 后端

- `routes/projects.py`：新增 `get_owned_project` FastAPI 依赖（查项目 + 404 + 归属校验 403），替换全文件 96 处两行样板
- `routes/videos.py` + `routes/history.py`：抽 `proxy_video_stream(video_url, range_header)` 合并两处逐字相同的 Range 代理
- `routes/history.py`：`_scope_user(stmt, user)` helper 收敛 10 处用户隔离过滤；下载代理抽 `_proxy_attachment`；`_async_ai_moderate` 与分享状态机下沉 `moderation_service`；`get_history` 改用 schema `model_validate` 并删除旧数据兼容回退
- `routes/chat.py`：`send_message` 瘦身——附件校验、历史构建、SSE 编排下沉 `chat_service`，会话隔离改 `Depends(get_owned_session)`
- `routes/projects.py`：帧图/视频/音频三组版本管理路由仿照现有 `_build_entity_routes` 工厂注册
- `project/character_service.py`、`scene_service.py`、`prop_service.py`：三个 `extract_X_from_script` 合一为 `extract_entities_from_script`（差异点：ORM 模型、prompt 模板、字段映射）
- `agnes_client.py`：抽 `_request_with_retry` 合并 `_post`/`_get` 重复重试循环
- 新增 `agnes_client.chat_text()`，替换 8 处复制粘贴的 LLM 取文本三行模板
- `moderation_service.py`：`moderate_image_with_ai`/`moderate_video_with_ai` 合并为公共 `_moderate_frame_with_ai`
- `image_poller.py`/`video_poller.py`：抽共享 `_persist_generation` 等公共逻辑
- `routes/admin_review.py`：改用 `core/security.py` 现成的 `require_permission` 依赖；抽 `load_authors_map` helper；删恒真常量 `WORK_REVIEW_ONLY_PUBLIC` 及死分支
- `schemas/project.py`：Character/Scene/Prop 三组 Create/Update/Response 合并为 EntityCreate/EntityUpdate/EntityResponse（字段并集全 Optional；service 用 `model_dump(exclude_unset=True)` 消费，无需改动逻辑）
- `merge_service.py`：三份时长计算收敛为 `_timeline_total_duration`

### 前端

- `lib/canvas-generation.ts`：新增 `runGenerationFlow` 统一 4 个 execute 函数（复用既有 `runMediaTask` 流程）；删 `extractResourceContentForComposer` 与死 import
- `stores/taskQueue.ts`：submitImage/submitVideo 与各自 background 函数按类型字段合并为 2 个；`registerCanvasTask`/`registerChatTask`、`updateCanvasTask`/`updateChatTask` 按 source 合并；删除整套重写轮询的 `_startProjectPolling`（项目任务走 `_startPolling`）；修复 `isRetryableError` 内外都 return false 的死逻辑；抽 `isMediaSuccess`/`isMediaFailed` 收敛 6 处重复状态数组
- 上游节点"排序编号"逻辑三处实现收敛为 `lib/canvas-generation.ts` 唯一实现，store getter 一行委托
- `composables/useCopyText.ts` 增加可选 `successMsg` 参数，替换 6 处复制粘贴的剪贴板逻辑（含 HistoryView 未走降级的 `copyRecordId`）
- `formatTime` 收敛到 `lib/`（11 个 view 替换）
- blob 下载 `fetchBlobAsUrl` 收敛到 lib（3 处）
- 新增 `useConfirm` composable（默认注入确认/取消文案与 warning 类型），替换 23 处 `ElMessageBox.confirm` 样板
- `ImageView`/`VideoView` 提示词长度分阶提示抽 `usePromptLength`
- `UnifiedReview.vue`：删 `handleReject` 纯转发壳，4 处审核动作抽局部 `reviewAction` helper
- `App.vue` + `MenuAdminView`：抽 `lib/icons.ts getIconByName` 共用，删 17 项冗余 iconMap
- `LoginView`：`loadLoginCaptcha`/`loadRegisterCaptcha` 合并为 `loadCaptcha(target)`

## Phase 4 — 规范修正

- 删除 `main.py` `_auto_migrate_missing_columns`（75 行手写迁移与 alembic 双轨维护，违反"未上线不兼容旧数据"；保留 `create_all`）
- `stores/taskQueue.ts` 持久化从 localStorage 换 localforage（对齐 canvas-storage 封装，消除 5MB 配额写失败被空 catch 静默吞掉的隐患；删手写字段白名单序列化与 `_switchUserStorage` 手工分 key）
- 剩余函数体内 import 上移文件顶部（约 35 处，仅处理无循环依赖的）
- 裸 dict 入参换 Pydantic schema：`set_cover_api` 的 `data: dict`、auth.py watermark/content-safety 的 `req: dict`
- 零散小项：`video_poller._get_interval/_get_timeout` 的假 try/except 顶层 import；`core/security.py` 永假的 `isinstance(token, bytes)` 分支；`credits_service` 死变量与同构 try/except 收敛

## Phase 5 — 响应结构统一

目标结构遵循 AGENTS.md：

- 成功：`{"status": "success", "message": "", "data": ...}`
- 错误：一律 `HTTPException`（FastAPI 标准 `{"detail": ...}`，前端拦截器已读取 detail/message）

实施顺序（保证中间态系统始终可运行）：

1. 后端新增 `core/response.py` 的 `ok(data, message="")` helper
2. 前端 `client.ts` 响应拦截器加透明解包：识别 envelope（`status === 'success'` 且含 `data` 字段）则返回 `data.data`；旧形状端点继续透传——兼容期两形状并存
3. 后端逐模块切换到 `ok()`：auth/admin → projects → history/videos/images → chat → 其余模块；每切换一个模块，同步修正对应前端 api 消费点并验证
4. 收尾验证：grep 后端不再有 `{"success": ...}`/`{"status": "ok"}` 裸写；grep 前端不再消费 `res.success`/`res.ok` 字段；删除拦截器兼容注释

## 验证与回滚

- 每阶段 gate：
  - 前端：`npm run type-check`；Phase 3/5 追加 `npm run build`
  - 后端：`pytest backend/tests/` + `python -m compileall app`
  - Phase 5 每切一个模块，手工冒烟对应前端流程（登录、生图、对话等）
- 每个 Phase 一个独立 commit（规范格式如 `refactor: Phase 2 删除全库死代码`），出问题 `git revert` 单个 commit
- 死代码如误删，从对应 commit 历史恢复

## 不做的事

- 不改 logs.py 与 rebuild-covers 路由（保留）
- 不动 `provider_registry` 主体逻辑（组织良好，仅删 3 个死方法）
- 不重构 `CanvasView.vue` 等大体量但无成块重复的文件（本轮只删其中死代码）
- 不引入新的状态管理方案或新抽象层；所有收敛都优先复用项目已有手法（路由工厂、依赖注入、composables）
