# Agnes AI 平台重构 - 实现计划（Implementation Plan）

## 任务依赖图
```
Task 1 (项目骨架) ──┐
                     ├──► Task 2 (后端核心) ──┐
                     │                        ├──► Task 3 (后端路由) ──┐
                     │                        │                        ├──► Task 4 (后端完整)
                     ├──► Task 5 (前端项目) ──┤                        │
                                              ├──► Task 6 (前端页面) ──┤
                                                                       ├──► Task 7 (联调测试)
                                                                       └──► Task 8 (文档)
```

---

## [ ] Task 1: 创建项目骨架与目录结构
- **Priority**: P0
- **Depends On**: None
- **Description**:
  - 创建 `frontend/` 目录（Vue 3 + Vite 项目）
  - 创建 `backend/` 目录（FastAPI 项目）
  - 创建根目录 `README.md`
  - 将原有 `app.js` / `index.html` / `styles.css` 标记为 legacy（或归档到 `legacy/` 目录）
  - 创建根目录 `.gitignore`（忽略 `__pycache__`, `node_modules`, `.env`, `*.db` 等）
- **Acceptance Criteria Addressed**: AC-1（前后端目录分离）
- **Test Requirements**:
  - `programmatic` TR-1.1: 目录结构中存在 `frontend/` 和 `backend/`，且各自有独立配置文件
  - `programmatic` TR-1.2: 根目录 `README.md` 存在并包含项目简介
  - `human-judgement` TR-1.3: 目录结构清晰，原文件已归档，不影响新项目
- **Expected Output Structure**:
  ```
  agnes-platform/
  ├── README.md
  ├── .gitignore
  ├── frontend/          (Vue 3 + Vite)
  │   └── package.json
  ├── backend/           (FastAPI)
  │   ├── requirements.txt
  │   └── .env.example
  └── legacy/            (原有 app.js/index.html/styles.css)
  ```

---

## [ ] Task 2: 后端核心基础设施（FastAPI + 数据库 + 配置）
- **Priority**: P0
- **Depends On**: Task 1
- **Description**:
  - 创建 `backend/app/main.py` 作为 FastAPI 入口，配置 CORS、健康检查路由
  - 创建 `backend/app/core/config.py`（使用 pydantic-settings 加载 `.env` 环境变量，包含 `AGNES_API_KEY`, `AGNES_API_BASE_URL`, `DATABASE_URL` 等）
  - 创建 `backend/app/core/database.py`（SQLAlchemy 引擎、SessionLocal、Base 模型基类）
  - 创建 `backend/app/models/` 目录，定义 `Generation` 模型（对应历史记录表）
  - 创建 `backend/app/schemas/` 目录，定义 Pydantic 请求/响应 Schema（ImageRequest, VideoRequest, GenerationResponse 等）
  - 创建 `backend/app/services/agnes_client.py` — Agnes AI API 客户端封装（三层设计：底层 HTTP / API 方法 / 业务方法），参考 agnes-media-create Skill 的模块组织
  - 创建 `backend/app/services/video_poller.py` — 视频异步任务轮询管理器（基于 asyncio，内存缓存任务状态）
  - 创建 `backend/requirements.txt` 并列出依赖（fastapi, uvicorn[standard], httpx, sqlalchemy, pydantic-settings, python-dotenv, aiofiles）
  - 创建 `backend/.env.example`
- **Acceptance Criteria Addressed**: AC-5（API Key 安全）、AC-6（历史持久化）的基础部分
- **Test Requirements**:
  - `programmatic` TR-2.1: `python -m uvicorn app.main:app --reload` 可成功启动，访问 `/health` 返回 200
  - `programmatic` TR-2.2: 访问 `/docs` 可看到 Swagger UI
  - `programmatic` TR-2.3: 数据库文件在首次启动时自动创建（`sqlite:///./agnes_platform.db`）
  - `human-judgement` TR-2.4: 代码分层清晰（core/models/schemas/services/routes），符合 PEP 8
- **Notes**: Agnes AI API 调用使用 httpx（支持同步+异步），注意视频请求需要 asyncio 事件循环

---

## [ ] Task 3: 后端路由层实现（REST API）
- **Priority**: P0
- **Depends On**: Task 2
- **Description**:
  - 创建 `backend/app/routes/images.py`：
    - `POST /api/images/generations` - 接收 prompt + 可选 base64 图片 → 调用 Agnes AI → 存储历史 → 返回结果
    - `GET /api/images/{id}` - 从数据库查询单张图片生成记录
  - 创建 `backend/app/routes/videos.py`：
    - `POST /api/videos` - 创建视频生成任务，返回 task_id，启动后台轮询
    - `GET /api/videos/{task_id}` - 查询视频任务状态（从内存缓存读取，若完成则从 DB）
  - 创建 `backend/app/routes/history.py`：
    - `GET /api/history?type=image|video|all&page=1&limit=20` - 分页查询历史
    - `DELETE /api/history/{id}` - 删除单条记录
  - 创建 `backend/app/routes/config.py`：
    - `GET /api/config` - 返回非敏感配置（支持的模型名、默认尺寸列表等）
  - 在 `main.py` 中注册所有路由
  - 添加全局异常处理器，返回统一格式的 JSON 错误响应
- **Acceptance Criteria Addressed**: AC-2, AC-3, AC-4, AC-6, AC-7
- **Test Requirements**:
  - `programmatic` TR-3.1: 所有 `/api/*` 路由在 Swagger 中可见且 schema 定义完整
  - `programmatic` TR-3.2: `/api/config` 返回 JSON，不包含任何 API Key 信息
  - `programmatic` TR-3.3: 无效请求参数返回 422 错误并带有可读错误信息
  - `human-judgement` TR-3.4: 视频轮询的后台任务逻辑正确，不会阻塞主线程

---

## [ ] Task 4: 后端完整性与安全性检查
- **Priority**: P1
- **Depends On**: Task 3
- **Description**:
  - 添加请求体大小限制（图片 base64 限制 10MB）
  - 添加 CORS 配置，仅允许 `http://localhost:5173`（Vite dev server）及配置的 `FRONTEND_URL`
  - 添加输入校验：prompt 非空、尺寸合法性、帧数规则（视频 num_frames 需满足 8n+1 规则，参考 agnes-media-create Skill 中的校验逻辑）
  - 添加日志记录（图片/视频请求的成功/失败日志）
  - 添加 startup event，在应用启动时验证 Agnes AI API Key 是否配置
  - 在 `backend/README.md` 中记录 API 接口列表与启动说明
- **Acceptance Criteria Addressed**: AC-5, AC-7, AC-8
- **Test Requirements**:
  - `programmatic` TR-4.1: 未配置 API Key 时启动服务会在日志中输出警告
  - `programmatic` TR-4.2: CORS 配置正确，非法来源被拒绝
  - `programmatic` TR-4.3: prompt 为空返回 422 错误
  - `human-judgement` TR-4.4: 后端代码的核心逻辑有中文注释

---

## [ ] Task 5: 前端项目基础（Vue 3 + Vite）
- **Priority**: P0
- **Depends On**: Task 1
- **Description**:
  - 使用 Vite 创建 Vue 3 项目，初始化 `frontend/package.json`
  - 安装依赖：`vue`, `vue-router`, `pinia`, `axios`, `element-plus`（UI 框架），以及 dev 依赖
  - 创建目录结构：
    - `frontend/src/components/` - 可复用组件（ImageUploader, PromptTemplates, ResultCard 等）
    - `frontend/src/views/` - 页面级组件（ImageView, VideoView, HistoryView）
    - `frontend/src/api/` - API 请求封装（基于 axios，统一 baseURL, 错误处理）
    - `frontend/src/stores/` - Pinia stores（history 管理、全局状态）
    - `frontend/src/assets/` - CSS/图片资源（沿用现有深色主题设计）
    - `frontend/src/router/` - Vue Router 路由配置
  - 配置 `vite.config.js`（代理 `/api` 到后端 `http://localhost:8000`）
  - 创建 `frontend/.env.example`（仅含 `VITE_API_BASE_URL`，不含 API Key！）
- **Acceptance Criteria Addressed**: AC-1, AC-5 的前端部分
- **Test Requirements**:
  - `programmatic` TR-5.1: `npm install && npm run dev` 可启动前端服务
  - `programmatic` TR-5.2: 访问首页显示基础布局
  - `human-judgement` TR-5.3: 组件目录结构清晰，职责分明
- **Notes**: Element Plus 使用深色主题（`el-theme-dark` 或自定义 CSS 变量），与现有设计语言一致

---

## [ ] Task 6: 前端页面与业务逻辑实现
- **Priority**: P0
- **Depends On**: Task 5
- **Description**:
  - 图片生成页面 (`views/ImageView.vue`)：
    - 模式切换（文生图 / 图生图）
    - 图片上传组件（支持拖拽上传 + URL 粘贴，base64 转换）
    - Prompt 输入 + 预设风格 chips
    - 参数配置（尺寸、输出格式）
    - 生成按钮 + 加载动画
    - 结果区：图片预览、下载按钮、复制链接按钮
  - 视频生成页面 (`views/VideoView.vue`)：
    - 模式切换（文生视频 / 图生视频 / 关键帧动画）
    - 多图上传（关键帧模式）
    - Prompt + 负向 Prompt 输入
    - 参数配置（帧数、帧率、分辨率）
    - 生成按钮 + 进度条 + 中止按钮
    - 结果区：`<video>` 播放器、下载、复制链接
  - 历史页面 (`views/HistoryView.vue`)：
    - 卡片网格展示历史记录
    - 类型筛选 Tab（全部/图片/视频）
    - 点击卡片弹出详情 Modal（大图/视频预览 + 参数列表）
    - 删除按钮（带确认对话框）
  - 主布局（`App.vue` / `components/AppLayout.vue`）：
    - 顶部导航（Logo、页面切换）
    - Tab 页面切换（图片/视频/历史）
    - 深色主题整体布局
- **Acceptance Criteria Addressed**: AC-2, AC-3, AC-4, AC-6, AC-7, AC-10
- **Test Requirements**:
  - `programmatic` TR-6.1: 三个页面均能正常渲染，接口调用正确（通过 Vite dev proxy 转发）
  - `programmatic` TR-6.2: 图片/视频生成的完整流程可跑通（从输入到显示结果）
  - `programmatic` TR-6.3: 历史页面能正确显示后端返回的数据
  - `human-judgement` TR-6.4: UI 视觉与现有项目一致（深色主题、渐变强调色、圆角卡片）
- **Notes**: 关键交互函数（下载、复制、base64 转换）参考现有 `app.js` 的实现逻辑，用 Vue 组合式 API 重写

---

## [ ] Task 7: 前后端联调与集成测试
- **Priority**: P0
- **Depends On**: Task 4, Task 6
- **Description**:
  - 编写启动说明（后端端口 8000，前端端口 5173）
  - 完整测试：文生图 → 查看结果 → 下载 → 历史中出现
  - 完整测试：图生图 → 同上
  - 完整测试：文生视频 → 轮询状态 → 视频播放 → 历史中出现
  - 测试历史删除功能
  - 测试错误场景（API Key 无效、网络错误、prompt 为空）
  - 测试响应式布局（1200px / 768px 两个断点）
  - 验证前端代码中不含 "sk-" / "AGNES_API_KEY" 等敏感字符串
- **Acceptance Criteria Addressed**: AC-2 through AC-10（全部验收标准）
- **Test Requirements**:
  - `programmatic` TR-7.1: `grep -r "sk-" frontend/src` 返回空
  - `programmatic` TR-7.2: 完整生成流程（图片+视频）可成功执行
  - `programmatic` TR-7.3: 历史记录在服务重启后保留
  - `human-judgement` TR-7.4: 错误信息友好清晰，用户可理解下一步操作

---

## [ ] Task 8: 文档编写
- **Priority**: P1
- **Depends On**: Task 7（需要先完成实现才能写准确的文档）
- **Description**:
  - 根目录 `README.md`：
    - 项目简介（功能特性、技术栈）
    - 架构图（前端 → BFF → Agnes AI）
    - 快速启动（克隆、安装依赖、配置 API Key、启动前后端）
    - 项目目录说明
    - FAQ
  - `frontend/README.md`：
    - 前端技术栈说明
    - 组件目录结构与组件职责说明
    - 开发/构建/预览命令
    - 路由说明
  - `backend/README.md`：
    - 后端技术栈说明
    - API 路由列表与功能
    - 数据库模型说明
    - 环境变量列表
    - 启动命令
  - `API.md`（根目录或 `docs/` 目录）：
    - 每个接口的详细说明（路径、方法、请求体、响应体、示例）
- **Acceptance Criteria Addressed**: AC-9
- **Test Requirements**:
  - `human-judgement` TR-8.1: 新开发人员阅读 README 能在 10 分钟内启动项目
  - `human-judgement` TR-8.2: API.md 覆盖所有接口且字段准确
  - `human-judgement` TR-8.3: 文档语言为中文，术语统一

---

## 任务优先级与顺序汇总

| Task | 标题 | 优先级 | 预估工作量 | 依赖 |
|------|------|--------|-----------|------|
| 1 | 项目骨架与目录 | P0 | 30 min | - |
| 2 | 后端核心基础设施 | P0 | 3 hr | Task 1 |
| 3 | 后端路由层 | P0 | 3 hr | Task 2 |
| 4 | 后端完整性检查 | P1 | 1.5 hr | Task 3 |
| 5 | 前端项目基础 | P0 | 2 hr | Task 1 |
| 6 | 前端页面实现 | P0 | 6 hr | Task 5 |
| 7 | 联调测试 | P0 | 2 hr | Task 4, 6 |
| 8 | 文档编写 | P1 | 2 hr | Task 7 |

**总预估工作量**: 约 20 小时（纯开发时间）
