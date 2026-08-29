# Changelog

本文件记录 Agnes AI Platform 的所有版本变更。格式参考 [Keep a Changelog](https://keepachangelog.com/)。

## [Unreleased]

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
- 剧本节点分镜资产一体化（设计文档 `docs/superpowers/specs/2026-08-29-script-node-asset-derivation-design.md`）：`POST /api/storyboard` 一次 LLM 调用同时输出全剧角色/场景清单与分镜数组，镜头携带 `characters`/`location` 与资产按名关联；请求新增 `scenes` 反向通道（已有资产卡回传，分镜沿用已有设定）；向导步骤①新增场景/出场角色列、步骤②资产卡按名去重自动预填（卡片显示"出现镜头"）、资产参考图 prompt 注入关联镜头剧情与剧情概述；分镜图派生按镜头命中注入设定文本与参考图（未标注镜头保持全量注入，与旧行为一致）
- 创作内容归档与资产激活（设计文档 `docs/superpowers/specs/2026-08-29-creation-archive-asset-activation-design.md`）
  - 生成记录新增来源标记（`source` / `container_type` / `container_id`），历史默认只显示独立生成，提供来源筛选（独立生成 / 画布创作 / 项目创作 / 全部）
  - 画布与项目生成自动归档进资产库（按创作容器分组），新增归档服务 `asset_archive.archive_to_asset` 与成片归档 `archive_final_video`
  - 资产表新增容器归组字段（`container_type` / `container_id` / `container_name` / `source_generation_id`）与 `kind` / `asset_url`；`type` 扩展 `material` / `clip` / `final`
  - 资产页重构为「创作单元 + 我的资产」两区：创作单元按容器分组、支持单元详情（按类型分栏）、预览、分享到广场（复用审核管道）、删除归档影子记录
  - 新增端点：`GET /api/pipeline/assets/containers`、`GET /api/pipeline/assets/container/{type}/{id}`、`PATCH /api/pipeline/assets/{id}/share`、`DELETE /api/pipeline/assets/{id}`；`GET /api/pipeline/assets` 新增 `scope=my` 仅返回当前用户资产
  - 审核逻辑下沉至 `moderation_service.run_async_asset_moderation` 共用（资产分享与历史分享统一走敏感词 + AI 预审管道）
  - 广场新增「创作」Tab（M4）：`GET /api/plaza/creations` 返回已公开且审核通过的资产，支持 `asset_type` / `kind` / `sort(latest|popular)` 筛选与分页；复用 `asset_likes` 表新增 `POST/DELETE /api/plaza/creations/{id}/like` 点赞/取消与 `GET /api/plaza/creations/likes/status` 批量状态查询；`GET /api/plaza/creations/{id}` 详情浏览量自增；前端 `PlazaView` 增加作品/创作双 Tab、类型标签、点赞按钮与创作详情弹窗
  - 资产「用于生成」闭环（M5）：`POST /api/pipeline/assets/{id}/use` 记录使用并递增 `use_count`；资产卡「用于生成」写入 Pinia `pendingUse`，跳转生图/视频页在 `onMounted` 预填参考图/视频并调用 use 接口；替换「功能开发中」占位文案并补充 i18n（zh-CN / en-US）

### 修复（归档功能验收问题）
- 分享审核闭环断裂：资产分享后无人复审则永远无法上广场——统一审核后台（列表/通过/驳回/统计/批量）新增 `asset` 类型，`UnifiedReview` 增加资产 Tab 与图片/视频预览
- 剧本分镜图/分镜视频误归入「画布」容器：画布生成执行器读取节点 `lineage`，有剧本来源时归档到 `canvas_script` 容器并按 `#镜头号` 命名
- 项目制归档丢失产物类型/名称：`submit_image_task` / `submit_video_task` 增加 `asset_type` / `asset_name` 透传，角色/场景/道具参考图、分镜帧图、镜头视频按产物归档
- 历史页「存为资产」放开到所有成功记录（自动归档失败的补存兜底）；手动保存按 `source_generation_id` 幂等去重，重复点击不再产生重复资产
