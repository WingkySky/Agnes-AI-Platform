# Agnes Platform 优化计划（Spec）

> 制定日期：2026-07-02
> 调查范围：后端代码重复 + 前端代码重复 + 架构性能 + 测试工程化（4 个维度并行调查）
> 与前期《冗余审计报告验证》关系：本计划**不重复**已审计的 Poller/Preset/Style/auto-migrate/启动脚本/check_db 项，聚焦迭代过程中产生的新问题

---

## 一、问题全景概览

| 维度 | 问题数 | 最严重项 |
|---|---|---|
| **安全/配置** | 5 项 | JWT 默认密钥、`encryption_key` 默认空、`.env.example` 缺 17+ 变量、默认 admin123 |
| **性能/架构** | 6 项 | 无缓存层、25 处临时 httpx 违反持久化规范、admin_review 内存分页、敏感词无缓存 |
| **后端代码重复** | 9 项 | image_batch/video_batch 重复 150 行、camera/prompt preset service 对称 220 行、分页 dict 27 处 |
| **前端代码重复** | 12 项 | formatTime 15 处重复、copyText 6 处、confirmDialog 19 处、Image/VideoView 500+ 行重复 |
| **工程化缺失** | 8 项 | 零测试、零 CI、无 lint、无 lock 文件、API.md 覆盖率 10%、VERSION/CHANGELOG 缺失 |

**总计可消除的重复代码**：后端约 800 行、前端约 1700 行，合计约 2500 行。

---

## 二、分阶段行动计划

### 第一阶段：安全与配置加固（P0，必须先做）

| 序号 | 行动 | 文件 | 风险 | 复杂度 |
|---|---|---|---|---|
| S1 | 移除 `jwt_secret` 不安全默认值，启动时校验 | `backend/app/core/config.py:75-78` | 高（密钥可伪造 token） | 低 |
| S2 | 移除 `encryption_key` 默认空兜底 | `backend/app/core/config.py:49-52` + `core/security.py:32-37` | 高（API Key 等于没加密） | 低 |
| S3 | 补全 `.env.example` 17+ 缺失变量（JWT、SMTP、日志、ADMIN_* 等） | `backend/.env.example` | 中（部署易遗漏） | 低 |
| S4 | 默认 admin 密码首次登录强制修改 | `backend/init_db.py:125` + 前端登录逻辑 | 中（README 公开 admin123） | 中 |
| S5 | `/uploads` 静态文件加鉴权代理或用 UUID 文件名 | `backend/app/main.py:433-436` | 中（头像可枚举） | 中 |

**验收标准**：未配置 `JWT_SECRET`/`ENCRYPTION_KEY` 时启动失败并给出明确错误；`.env.example` 与 `config.py` 的 Settings 字段一一对应。

---

### 第二阶段：架构性能修复（P0，与第一阶段并行）

| 序号 | 行动 | 文件 | 收益 | 复杂度 |
|---|---|---|---|---|
| A1 | 修复 `system_config_service` 缓存永不过期 bug | `services/system_config_service.py:37-53` | 配置变更生效 | 低 |
| A2 | 给 `check_sensitive_text` 加进程内 TTL 缓存（60s） | `services/moderation_service.py:38-63` | 每次审核少一次全表 SELECT | 低 |
| A3 | 给 `credits_service.get_image/video_cost_async` 加缓存 | `services/credits_service.py:36-42, 83, 118` | 高频扣费路径少打 DB | 低 |
| A4 | 修复 `admin_review` 跨表聚合内存分页 | `routes/admin_review.py:89-141` | 改多路归并分页，避免拉全量 | 中 |
| A5 | 修复 `preset_aggregator` 用 `len(scalars().all())` 做 count | `services/preset_aggregator.py:102,148,195,224,249,274` | 改 `select(func.count())`，避免全表实例化 | 低 |
| A6 | 统一 25 处临时 `httpx.AsyncClient` 为全局持久化 client | `routes/history.py`、`routes/videos.py`、`services/moderation_service.py`、`services/asset_storage.py`、`pipeline/steps/*.py` 等 | 复用连接，符合 AGENTS.md 规范 | 中 |
| A7 | `recompose_run_video` 改为 BackgroundTasks 真异步 | `routes/pipeline.py:1174, 1198` | 避免 30s-2min 阻塞 worker | 中 |
| A8 | 引入 Redis 统一缓存层（敏感词/积分规则/验证码/角色权限） | 新增 `backend/app/core/cache.py` | 解决多 worker 数据不一致 | 中-高 |
| A9 | 给 `/api/auth/*`、`/api/images/generate`、`/api/videos/generate` 加限流 | 新增中间件 | 防撞库/刷量 | 中 |
| A10 | 修复 `admin_review` 静默吞异常（`except: pass`） | `routes/admin_review.py:97-99, 106-107, 114-115` 等 | 改 `logger.exception`，避免审核列表假装为空 | 低 |

**验收标准**：高频路径（生图/生视频/审核）DB 查询数减少 50%+；多 worker 部署验证码与配置一致；worker 不再被长任务阻塞。

---

### 第三阶段：后端代码整合（P1，依赖第二阶段缓存基线）

| 序号 | 行动 | 重复处 | 预计减少 | 复杂度 |
|---|---|---|---|---|
| B1 | 抽 `BaseBatchExecutor`，合并 image_batch/video_batch 重复 | `_get_by_path`、`_auto_detect_items`、`_build_tasks_from_parsed_result` | ~150 行 | 中 |
| B2 | 抽 `BasePresetService`，合并 camera/prompt preset service 对称 CRUD | `camera_preset_service.py` + `prompt_preset_service.py`（各 ~234 行） | ~220 行 | 中 |
| B3 | 引入 `PaginatedResponse[T]` + `PaginationParams` 依赖注入 | 14 处 Query + 27 处分页 dict | ~70 行 | 低 |
| B4 | 抽 `require_moderator()` 依赖，替换 7 处内联权限校验 | `admin_review.py`（6 处）+ `asset.py`（1 处） | ~21 行 | 低 |
| B5 | 抽 `utcnow()` helper，替换 44 处 `datetime.utcnow()` | 18 文件 44 处 | 统一 + 兼容 Python 3.12+ deprecation | 低 |
| B6 | 抽 `OUTPUT_BASE` 常量，替换 4 处 pipeline steps 重复 | `tts_generate.py`、`ffmpeg_composite.py`、`color_grade.py`、`video_edit.py` | ~12 行 | 低 |
| B7 | 删除 `database.py` 同步引擎死代码（`engine`/`SessionLocal`/`get_db`） | `core/database.py` | ~30 行 | 低 |
| B8 | 抽 `paginate_query(stmt, p, sort_field_map)` helper，统一 5+ 个 `list_*` 函数 | `style_service.py`、`style_element_service.py`、`script_template_service.py`、`template_service.py`、`asset_library.py` | ~75 行 | 中 |
| B9 | 抽 `gen_task_id(prefix)` helper，替换 images/videos 路由内 ID 拼接 | `routes/images.py:88` 等 | 统一 ID 格式 | 低 |
| B10 | 注册全局 `HTTPException` handler，统一错误响应为 `{status,message}` | `main.py` + 60+ 处 `raise HTTPException` | 前端只需一套解析 | 低 |

**验收标准**：后端代码减少约 800 行；新增预设类型只需 10-20 行子类；分页接口响应格式统一。

---

### 第四阶段：前端代码整合（P1，与第三阶段独立可并行）

| 序号 | 行动 | 重复处 | 预计减少 | 复杂度 |
|---|---|---|---|---|
| F1 | 抽 `utils/formatTime.ts`，替换 15 处重复时间格式化 | 15 个 vue/ts 文件 | ~200 行 | 极低 |
| F2 | 抽 `composables/useCopyText.ts`，替换 6 处复制逻辑 | `ImageView`、`VideoView`、`HistoryView`、`PlazaView`、`CanvasView`、`preferences.ts` | ~120 行 | 低 |
| F3 | 抽 `composables/useConfirmDialog.ts`，替换 19 处确认弹窗 | 19 个 vue 文件 | ~100 行 | 低 |
| F4 | 抽 `composables/useGenerationTask(type)`，合并 ImageView/VideoView 任务逻辑 | `ImageView.vue` + `VideoView.vue`（各 ~1000 行） | ~500 行 | 中 |
| F5 | 提取 `GenerationResultPanel` + `GenerationModeTabs` 公共组件 | `ImageView.vue` + `VideoView.vue` 的模板与 ~365 行 CSS | ~350 行 CSS | 中 |
| F6 | 抽 `createCrudApi<T>` 工厂，合并 5 个 CRUD api 文件 | `presets.ts`、`cameraPresets.ts`、`styleElement.ts`、`scenes.ts`、`providers.ts` | ~400 行 | 中 |
| F7 | 统一 `ListResult<T>` 到 `@/types`，删除文件内重复定义 | 6+ 个 api 文件 | ~50 行 | 极低 |
| F8 | UnifiedReview.vue 改走 `@/api/admin` 封装，删除 10 处 `client.get/post` 直调 | `admin/UnifiedReview.vue` | ~50 行 | 低 |
| F9 | 修复 4 处 store 硬编码中文（违反 i18n 规范） | `stores/menu.ts:204,206,216,218`、`stores/preferences.ts:520`、`stores/user.ts:166`、`composables/useNodeMention.ts:23-28` | 合规 | 低 |
| F10 | 抽 `AdminPageHeader` + `AdminTableCard` 公共组件，替换 7 处 admin 页面头部与表格样式 | 7 个 admin view | ~150 行 | 低 |
| F11 | 修复 `admin.ts` 中 205 处 `as any`，补全类型到 `@/types` | `api/admin.ts` 全文 | 恢复类型安全 | 中 |
| F12 | 拆分 `preferences.ts`（596 行）为 `preferences` + `useAutoDownload` + `useNotifications` | `stores/preferences.ts` | 可读性 + 可测性 | 中 |

**验收标准**：前端代码减少约 1700 行；Image/VideoView 各减少 ~250 行；新增生成类页面（如音频）可复用 `useGenerationTask`。

---

### 第五阶段：工程化基础设施（P1）

| 序号 | 行动 | 当前状态 | 收益 | 复杂度 |
|---|---|---|---|---|
| E1 | 建立 `VERSION` 文件 + `CHANGELOG.md`（AGENTS.md 已规定但缺失） | 缺失 | 发版有据可依 | 低 |
| E2 | 补全 `API.md`（当前覆盖率 10%，缺 22 个 router 文档） | 严重过时 | 新人可上手 | 中 |
| E3 | 修复 `frontend/tsconfig.tsbuildinfo` 的 `errors:true` | 存在未解决 TS 错误 | 类型安全 | 中 |
| E4 | 从 `.gitignore` 移除 `docs/`（设计文档丢失风险） | `docs/` 被忽略 | 文档入库 | 低 |
| E5 | 引入 Ruff（Python lint + format） | 无任何 lint | 风格统一 | 低 |
| E6 | 引入 ESLint + Prettier（前端 lint） | 无任何 lint | 风格统一 | 低 |
| E7 | 引入 pytest + 覆盖率（后端） | 零测试 | 重构有保障 | 中 |
| E8 | 引入 Vitest（前端） | 零测试 | 纯函数可测 | 中 |
| E9 | 建立基础 GitHub Actions（lint + typecheck + test） | 无 CI | PR 自动校验 | 中 |
| E10 | 锁定后端依赖（`==` 或 pip-compile） | 全 `>=` 浮动 | 环境一致 | 低 |
| E11 | 拆分 three.js chunk + 修复 `chunkSizeWarningLimit:1500` | 大 chunk 被掩盖 | 首屏性能 | 低 |
| E12 | 生产开启 sourcemap（`hidden` 模式） | `sourcemap:false` | 线上排障 | 低 |

**验收标准**：`VERSION` 与 `CHANGELOG.md` 存在；`API.md` 覆盖所有 router；`npm run build` 无 TS 错误；CI 在 PR 上自动跑 lint + test。

---

## 三、优先级与依赖关系

```
第一阶段（安全 S1-S5）──┐
                       ├──→ 可独立先行，无依赖
第二阶段（性能 A1-A10）─┘

第三阶段（后端整合 B1-B10）──→ 依赖第二阶段缓存基线（A1/A2/A3）

第四阶段（前端整合 F1-F12）──→ 独立于后端，可并行

第五阶段（工程化 E1-E12）──→ E7/E8 依赖测试基础设施；其他可并行
```

**建议执行顺序**：
1. **本周**：第一阶段（安全）+ 第二阶段 A1/A2/A3/A10（缓存 bug 修复）+ 第五阶段 E1/E4（VERSION + docs/ gitignore）
2. **下周**：第三阶段 B1/B2/B3/B4（核心抽象）+ 第四阶段 F1/F2/F3（前端高频重复）
3. **后续**：按优先级表推进剩余项

---

## 四、调查覆盖范围说明

### 已覆盖维度（本次调查）
- 后端：路由层重复、Service 层 CRUD 对称、Schema 层缺泛型、配置硬编码、Pipeline steps 重复、Session 管理
- 前端：API 层 CRUD 五件套、Store 层职责重叠、Views 重复模式、Components 复用度、Composables 缺失、类型定义、样式管理、i18n 覆盖
- 架构：DB 查询性能、异步一致性、HTTP 客户端、缓存策略、错误处理、日志、认证权限、资源泄漏、API 设计一致性、CORS/限流/安全
- 工程化：测试覆盖、CI/CD、类型检查、代码质量工具、依赖管理、构建优化、文档一致性、环境管理、版本管理

### 未覆盖维度（已在前期《冗余审计报告验证》中处理）
- auto-migrate 删除（B1，需先启用 Alembic）
- check_db 双副本（A2）
- 启动脚本三冗余（A3）
- skills-lock.json 漏网（A1）
- TaskPoller 基类抽象（B2）
- Preset ORM 基类抽象（C4，ROI 低不建议）
- 移动端 API 抽包（C5，前提不成立）

---

## 五、总体目标

完成全部 5 个阶段后，预期收益：

| 维度 | 当前 | 目标 |
|---|---|---|
| 后端代码行数 | ~8000 行 | 减少 ~800 行（10%） |
| 前端代码行数 | ~25000 行 | 减少 ~1700 行（7%） |
| 重复代码占比 | 估 15% | < 5% |
| 测试覆盖率 | 0% | 核心模块 60%+ |
| 安全风险项 | 5 项 P0 | 0 项 |
| DB 查询热点 | 6 项无缓存 | 全部加缓存 |
| CI 自动化 | 无 | lint + typecheck + test |

**核心原则**：每个阶段独立可验收，不强制一次性完成。优先处理安全与性能，再处理代码整合，最后补工程化。

*（本计划基于 4 个维度的并行源码调查产出，所有问题点均附文件路径与行号，可直接据此启动实施）*
