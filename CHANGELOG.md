# Changelog

本文件记录 Agnes AI Platform 的所有版本变更。格式参考 [Keep a Changelog](https://keepachangelog.com/)。

## [Unreleased]

### 功能
- 图片参考图按模型差异化截断：仅对上游契约确有限制的模型生效（`agnes-image-2.1-flash` 上游最多 6 张，超出会被 400 拒绝），前端 `IMAGE_MODEL_REF_LIMITS`（`createGenerationTask` 请求构建处，保留前 N 张，锚点/底图 > 角色 > 场景优先级）+ 后端 `_IMAGE_REF_LIMITS`（`agnes_client.create_image` 兜底截断）双层防护，其余模型原样透传不截断；修复画布分镜图批量生成因参考图 7-8 张全量被上游拒绝的问题
- Seedream 生图按模型/Provider 差异化优化（`AGNSDKClientWrapper.create_image`，无像素级预处理）：①「AI生成」显式标识水印按方舟官方 `watermark` 参数关闭——覆盖 volcengine_cv Provider 全量与 openai 协议兼容端点（火山 agent plan）的 seedream 系模型，经 aibridge `image_generate(**kwargs)` → `extra` → 请求体顶层透传；②分辨率归一化——把 volcengine_cv 适配器的 Seedream 尺寸规范移植到封装层（合法总像素 ∈ [2K 档, 4K 档]，不合法按最接近宽高比映射官方 2K 推荐档，合法原样透传），修复 openai 兼容端点 size 原样透传导致前端默认 1024x1024 低于 Seedream 最小档的问题（已实测 plan 端点 1024→2048 归一化生效且无水印）；发布内容时按平台规则声明 AI 生成的义务由使用方承担
- 统一预设广场重构：预设中心改造为对标风格/特效广场的卡片画廊（广场/我的收藏/最近使用三 tab + 类型/分类导航 + 搜索 + 排序），生图页"风格库"、生视频页"特效库"弹窗即选即用
- 预设挂载式应用：风格/特效/运镜卡片一键"使用"即挂载到生成模块（标签可移除，风格与运镜单选、特效可叠加），提交生成时系统自动拼接提示词片段与负面词，提示词输入框保持纯用户内容；脚本类复制到剪贴板、提示词类追加输入框
- 官方封面维护：管理员可在预设详情一键 AI 生成封面（`POST /api/presets/{id}/generate-cover`），effect/camera 类型自动走视频 API 生成 4s 动态封面（`cover_video`，卡片悬停循环播放），其余生成静态图（`cover_image`）；或运行 `backend/generate_plaza_covers.py` 批量补齐；用户自建卡支持上传图片或从生成记录选图
- 画风不再硬编码：生图/生视频页 13 个硬编码风格与 style_presets 12 个内置风格收编为官方种子（`backend/seed_plaza_presets.py`，共 37 条官方卡），新增 12 个视频特效模板
- 预设五类统一（style/effect/camera/prompt/script）：`prompt_presets` 新增 `cover_image` / `cover_video` / `prompt_config` / `is_official` 字段，camera 类型不再分流 camera_presets 表
- 新增收藏与最近使用（`preset_favorites` / `preset_recent_uses` 表，favorite toggle + use 上报接口）、通用图片上传接口（`POST /api/uploads/image`）
- `/presets` 管理页重构：画廊 + 我的预设管理（编辑/删除/投稿/导入导出），投稿审核沿用现有 admin_review 流

### 安全
- 移除 `jwt_secret` 不安全默认值，启动时强制校验非空、非默认占位值、长度≥32 字节
- 移除 `encryption_key` 默认空兜底，启动时强制校验非空；`security._derive_key` 不再使用内置默认密钥
- 补全 `.env.example` 缺失变量（JWT_SECRET / SMTP_* / CAPTCHA_* / EMAIL_CODE_* / BACKEND_PORT / LOG_* / NEW_USER_DEFAULT_CREDITS）
- 默认 admin 账号与首位注册管理员 `must_change_password=True`，登录响应与 `/auth/me` 返回该标志；新增 `POST /auth/change-password` 接口（旧密码+新密码），修改成功后清除标志；邮箱重置密码后自动清除标志
- S5（/uploads 鉴权代理）经审查后跳过：avatars 目录受广场匿名浏览硬约束必须公开，watermarked 目录因水印下载接口动态处理未被使用，当前无真正需要鉴权的上传文件

### 性能
- 修复 `system_config_service.get_config_value` 缓存永不过期 bug（增加 60 秒 TTL 检查）
- `moderation_service.check_sensitive_text` 添加进程内 60 秒 TTL 缓存，敏感词增删改后自动清除
- `credits_service._get_rule_value` 添加进程内 60 秒 TTL 缓存，积分规则修改/重置后自动清除

### 可观测性
- `admin_review` 统一审核接口的 9 处静默 `except: pass` 改为 `logger.exception`，保留默认 0 值不破坏前端逻辑

### 工程化
- 建立 `VERSION` 文件（0.0.1）与 `CHANGELOG.md`
- 从 `.gitignore` 移除 `docs/`，设计文档纳入版本控制

### 新增（功能）
- 剧本节点分镜资产一体化（设计文档 `docs/superpowers/specs/2026-08-29-script-node-asset-derivation-design.md`）：`POST /api/storyboard` 一次 LLM 调用同时输出全剧角色/场景清单与分镜数组，镜头携带 `characters`/`location` 与资产按名关联；请求新增 `scenes` 反向通道（已有资产卡回传，分镜沿用已有设定）；向导步骤①新增场景/出场角色列、步骤②资产卡按名去重自动预填（卡片显示"出现镜头"）、资产参考图为纯设定图 prompt（角色三视图立绘：正面/侧面/背面并排；场景空镜无人物，不注入剧情避免提示词污染）；分镜图派生按镜头命中注入设定文本与参考图（未标注镜头保持全量注入，与旧行为一致）
- 创作内容归档与资产激活（设计文档 `docs/superpowers/specs/2026-08-29-creation-archive-asset-activation-design.md`）
  - 生成记录新增来源标记（`source` / `container_type` / `container_id`），历史默认只显示独立生成，提供来源筛选（独立生成 / 画布创作 / 项目创作 / 全部）
  - 画布与项目生成自动归档进资产库（按创作容器分组），新增归档服务 `asset_archive.archive_to_asset` 与成片归档 `archive_final_video`
  - 资产表新增容器归组字段（`container_type` / `container_id` / `container_name` / `source_generation_id`）与 `kind` / `asset_url`；`type` 扩展 `material` / `clip` / `final`
  - 资产页重构为「创作单元 + 我的资产」两区：创作单元按容器分组、支持单元详情（按类型分栏）、预览、分享到广场（复用审核管道）、删除归档影子记录
  - 新增端点：`GET /api/pipeline/assets/containers`、`GET /api/pipeline/assets/container/{type}/{id}`、`PATCH /api/pipeline/assets/{id}/share`、`DELETE /api/pipeline/assets/{id}`；`GET /api/pipeline/assets` 新增 `scope=my` 仅返回当前用户资产
  - 审核逻辑下沉至 `moderation_service.run_async_asset_moderation` 共用（资产分享与历史分享统一走敏感词 + AI 预审管道）
  - 广场新增「创作」Tab（M4）：`GET /api/plaza/creations` 返回已公开且审核通过的资产，支持 `asset_type` / `kind` / `sort(latest|popular)` 筛选与分页；复用 `asset_likes` 表新增 `POST/DELETE /api/plaza/creations/{id}/like` 点赞/取消与 `GET /api/plaza/creations/likes/status` 批量状态查询；`GET /api/plaza/creations/{id}` 详情浏览量自增；前端 `PlazaView` 增加作品/创作双 Tab、类型标签、点赞按钮与创作详情弹窗
  - 资产「用于生成」闭环（M5）：`POST /api/pipeline/assets/{id}/use` 记录使用并递增 `use_count`；资产卡「用于生成」写入 Pinia `pendingUse`，跳转生图/视频页在 `onMounted` 预填参考图/视频并调用 use 接口；替换「功能开发中」占位文案并补充 i18n（zh-CN / en-US）
  - 生成配置下放 Phase A（设计文档 `docs/superpowers/specs/2026-08-29-generation-config-downshift-design.md`）：模型与参数选择从硬编码/默认值下沉到每个生成入口
    - 默认值链统一：`modelsStore.getDefaultModel(type)` 优先级为偏好默认模型（校验存在且类型匹配）> 该类型列表第一个；`defaultImageModel` / `defaultVideoModel` 改为其封装，全链路消费方零改动即获得偏好感知；偏好字段拆分为 `default_image_model_id` / `default_video_model_id`，偏好页新增"默认生图/生视频模型"两个下拉（原 `default_model_id` 从未有 UI 入口）
    - 新增 `ComposerParamBar`：复用 `ParamSelector` 的选项逻辑，只做驼峰↔蛇形字段适配与 content 持久化（支持 `contentKey` 分区）；image / video / config 三类节点 Composer 接入，config 节点原生 select 整体替换后字段名与读写路径不变，`executeMerge*` 零改动
    - script 节点新增分镜聊天模型选择（存 `content.chat_model`）；`POST /api/storyboard` 新增可选 `model`，命中 chat 模型注册表时使用指定模型，未传或未命中回退第一个 chat 模型
    - 剧本向导步骤② 新增资产图参数栏、步骤③ 新增分镜图/分镜视频批量参数区，按 `asset_image_params` / `shot_image_params` / `shot_video_params` 分区持久化到 script 节点；批量派生与单镜头重拍改为同源读取，视频时长优先级为参数栏显式选择 > 镜头表格时长，视频 `aspect_ratio` / `resolution` / `frame_rate` 不再硬编码
- 分镜直出 B1 地基与派生切换（设计文档 `docs/superpowers/specs/2026-08-29-canvas-node-evolution-roadmap.md`）：脚本批量派生分镜图不再产生 config 中间节点，每镜头直接创建 1 个可生图的图片节点（prompt/模型/参考图/lineage 内嵌节点，结果就地回填 `content.content`）；**视频派生同样直出**：批量/单镜头直接创建视频节点（参数/源分镜图/lineage 内嵌，视频地址回填节点自身），不再产生"摄像机控制"config 节点，视频节点按行内列位排在分镜网格右侧专属区（B2 改覆盖式布局）；`findDerivedPanels` 同时识别直出节点与存量 config 派生（幂等不重复派生）；`getShotLineageInfo` 兼容直出节点（镜头徽章与派生/重拍按钮可用）；直出节点重试走就地执行（保留模型/参数/参考图/源图）；批量失败汇总提示（补 `batchImagesFailed` / `batchVideosFailed` 文案）
    - 手工验证清单见 `docs/superpowers/specs/2026-08-29-phase-a-smoke-checklist.md`
- Provider 协议兼容接入与模型手动停用（配置管理页）：新增 Provider 表单的 Adapter 类型改为分组下拉——「协议兼容接入」组提供 OpenAI 接口协议兼容 / Anthropic 接口协议兼容（自定义端点，走 aibridge `openai` / `anthropic` adapter + 自定义 base_url，已用 mock 服务验证 list_models / image_generate 链路），原厂商列表归入「厂商适配器」组；模型列表新增手动停用/启用（`model_definitions` 新增 `is_disabled` 列，启动自动迁移加列）：停用模型不出现在生成页模型列表（`refresh_models_cache` 过滤 `is_disabled`），模型同步永不修改 `is_disabled`（修复原同步会把手动停用的模型自动重新激活的问题），模型表格状态列三态（已激活/已停用/已下线）、行内停用/启用按钮、默认隐藏已停用模型（「显示已停用」开关控制），编辑弹窗"激活"开关改为"启用模型"（对应 `is_disabled`），`PUT /api/models/{model_id}` 支持 `is_disabled` 参数；模型表格新增多选批量操作（批量停用/启用 `PUT /api/models/batch`、批量删除 `POST /api/models/batch-delete`，单次请求 + 单次缓存刷新）、类型筛选（全部/图片/视频/对话）与模型 ID/显示名称/类型/供应商列排序；Provider 编辑弹窗在输入框下方显示已保存的掩码 API Key（原来编辑时无任何已填充提示），模型表格新增「所属 Provider」列（按 provider_id 反查配置的 Provider 名称，区分多 Provider 接入同一供应商的模型）；修复表格固定操作列半透明底色透出滚动内容的问题（主题色均为半透明，改用「半透明主题色叠层 + 实色底」在固定列上合成不透明背景，普通/斑马纹/悬停/表头四态逐层对齐），统一操作按钮风格（删除改为 plain 描边、停用/启用补充图标，Provider 表格操作补齐图标并加宽到单行布局）；模型同步失败不再静默返回空列表——`AGNSDKClientWrapper.list_models` 失败改为抛出中文错误（认证失败/路径不存在等），同步接口以 502 透出 detail 给前端提示，避免"同步成功但 0 个"无线索的假成功；Provider 表格默认列改为可点击的「设为默认」链接，操作列新增「添加模型」（打开模型弹窗并预选该 Provider，适配方舟 Agent Plan 等不提供 /models 接口、需手动录入模型名的端点）；LLM 文本对话按 Provider 路由的设计建议稿见 `docs/superpowers/specs/2026-08-30-chat-model-provider-routing-design.md`（已含落地记录）
- 对话模型配置化（消除硬编码，支持模型迭代随时切换）：新增两级配置——用户偏好「默认对话模型」（`generation.default_chat_model_id`，覆盖分镜脚本/剧本聊天/项目向导/镜头/角色/场景/道具/字幕等创作环节，解析链为显式指定 > 用户偏好 > 系统默认 > 注册表第一个）与管理员「模型服务配置」页（`/admin/system-models`，system_configs 新增 `model.chat_default` / `model.moderation_chat` / `model.title_summary_chat`，覆盖审核、标题总结等系统级任务与全局兜底，`PUT /api/admin/system-config/models` 带注册表校验）；清零全部 `agnes-2.0-flash` 硬编码与"第一个 chat 模型"硬依赖（wizard 步骤显式模型仍然优先），非流式遗留 `chat()` 走系统链，流式聊天跟随会话用户偏好；解析链逐级校验模型仍在注册表中（偏好/管理员配置/显式指定指向已停用或已下线的模型时自动落到下一级），全部落空时各调用点快速报中文错误（审核安全降级放行、标题总结静默降级），不再把空模型名或失效模型名发往上游

### 修复（归档功能验收问题）
- 分享审核闭环断裂：资产分享后无人复审则永远无法上广场——统一审核后台（列表/通过/驳回/统计/批量）新增 `asset` 类型，`UnifiedReview` 增加资产 Tab 与图片/视频预览
- 剧本分镜图/分镜视频误归入「画布」容器：画布生成执行器读取节点 `lineage`，有剧本来源时归档到 `canvas_script` 容器并按 `#镜头号` 命名
- 项目制归档丢失产物类型/名称：`submit_image_task` / `submit_video_task` 增加 `asset_type` / `asset_name` 透传，角色/场景/道具参考图、分镜帧图、镜头视频按产物归档
- 历史页「存为资产」放开到所有成功记录（自动归档失败的补存兜底）；手动保存按 `source_generation_id` 幂等去重，重复点击不再产生重复资产
