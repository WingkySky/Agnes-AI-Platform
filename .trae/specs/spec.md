# Agnes AI 图片与视频生成平台 - Product Requirement Document (PRD)

## Overview
- **Summary**: 本项目将现有纯前端 Agnes AI 生成平台重构为前后端分离架构。前端采用 Vue 3 + Vite 构建单页应用（SPA），后端采用 FastAPI 构建 BFF（Backend for Frontend）服务，作为前端与 Agnes AI 官方 API 之间的代理层，统一管理鉴权、请求、异步任务轮询与生成历史。
- **Purpose**: 解决现有纯前端架构中 API Key 暴露于浏览器、缺乏统一错误处理、前端代码耦合度高不易维护、缺乏服务端持久化能力等问题。通过 BFF 架构提升安全性、可维护性和扩展性。
- **Target Users**: 需要快速生成 AI 图片/视频的创作者、设计师、内容运营人员；以及作为团队内部统一生成服务的开发团队。

## Goals
- G1: 完成前端从原生 JS → Vue 3 组件化重构，保留全部功能（文生图、图生图、文生视频、图生视频、关键帧动画、生成历史）
- G2: 完成后端 FastAPI BFF 服务，提供统一的 REST API，封装 Agnes AI 平台调用细节
- G3: 前后端文件夹清晰区隔，项目结构规范，易于后续扩展
- G4: API Key 由后端统一管理（环境变量 / 配置文件），不暴露在前端
- G5: 生成历史由服务端持久化存储（SQLite 文件数据库）
- G6: 视频异步任务由后端统一轮询管理，前端只需轮询后端接口
- G7: 提供完整的项目文档（README、API 文档、开发指南）

## Non-Goals (Out of Scope)
- 不实现多租户/用户系统（初期仅服务于单用户或内部团队）
- 不实现付费/计费功能（使用官方 Agnes AI 的配额机制）
- 不实现内容审核（依赖官方 API 的审核能力）
- 不实现移动端 App（仅响应式 Web 端）
- 不引入额外的 AI 模型供应商（仅对接 Agnes AI 官方 API）
- 不实现实时协作功能

## Background & Context
- **现有项目**: 位于 `app.js` / `index.html` / `styles.css`，是一个功能完善的纯前端单页应用，直接从浏览器调用 Agnes AI 官方 API（`https://apihub.agnes-ai.com/v1`），通过 localStorage 存储 API Key 和生成历史。
- **技术选型理由**:
  - **Vue 3**: 轻量易上手、组件化完善、Composition API 逻辑复用、Vite 构建工具链成熟
  - **FastAPI (Python)**: 自动生成 OpenAPI 文档、原生异步支持（便于视频生成的异步轮询）、类型提示友好、与 Agnes AI Python SDK 生态兼容
  - **SQLite**: 零配置、文件型数据库，适合中小规模生成历史存储，易于部署
- **Agnes AI API 对接参考**: 参考 agnes-media-create Skill 的三层模块化设计（底层 HTTP / 业务 API 封装 / 独立功能入口），将在后端服务中应用类似模式
- **视频生成流程**: POST 创建任务 → 返回 task_id/video_id → 轮询查询状态 → 完成后返回视频 URL

## Functional Requirements

### FR-1: 前端应用（Vue 3 SPA）
- 提供图片生成界面（文生图 / 图生图）
- 提供视频生成界面（文生视频 / 图生视频 / 关键帧动画）
- 提供生成历史浏览、筛选、删除、详情查看
- 支持上传本地图片作为参考图 / 关键帧
- 支持粘贴图片 URL 作为参考图
- 提供预设风格模板 chips（图片风格 + 视频运镜模板）
- 显示生成进度（图片加载动画 + 视频进度条）
- 支持生成结果预览、下载、复制链接
- 响应式布局，支持桌面与平板浏览
- 深色主题 UI（沿用现有设计语言）

### FR-2: 后端服务（FastAPI BFF）
- `POST /api/images/generations` - 创建图片生成任务
  - Body: `{ prompt, model?, size?, response_format?, image?: [base64] }`
  - 返回: `{ id, status, url?, b64_json?, params, created_at }`
- `GET /api/images/:id` - 获取单张图片生成结果
- `GET /api/images` - 获取图片生成历史列表（分页）
- `POST /api/videos` - 创建视频生成任务
  - Body: `{ prompt, model?, num_frames?, frame_rate?, width?, height?, negative_prompt?, image?: base64|URL, images?: [...], keyframes?: bool }`
  - 返回: `{ task_id, video_id?, status, created_at }`
- `GET /api/videos/:task_id` - 查询视频生成状态和结果（后端自动轮询 Agnes API）
- `GET /api/history` - 获取全部生成历史（含图片+视频，可按类型筛选）
- `DELETE /api/history/:id` - 删除单条历史记录
- `GET /api/health` - 健康检查
- `GET /docs` - FastAPI 自动生成的 Swagger API 文档

### FR-3: API Key 安全管理
- 后端通过环境变量 `AGNES_API_KEY` 或 `.env` 文件读取 API Key
- 前端无需知晓 API Key
- 提供 `GET /api/config` 返回前端需要的非敏感配置（如支持的模型列表、尺寸选项等）

### FR-4: 生成历史持久化
- SQLite 数据库存储所有生成记录
- 字段: id, type (image/video), prompt, params(json), url, thumbnail, model, status, created_at
- 支持按类型筛选、按时间倒序排列
- 服务端定时清理可选（初期不限制，由用户手动删除）

### FR-5: 视频异步任务管理
- 后端收到视频创建请求后，同步转发给 Agnes AI，获取 task_id/video_id
- 后端维护任务状态缓存（内存），前端轮询后端接口
- 后端轮询 Agnes AI 官方接口（间隔 5s，超时 10 分钟），将结果缓存
- 任务完成/失败后，结果写入数据库

### FR-6: 项目文档
- `README.md` - 项目介绍、功能特性、快速启动指南
- `frontend/README.md` - 前端开发指南、项目结构、组件说明、启动命令
- `backend/README.md` - 后端开发指南、API 路由说明、数据库模型、启动命令
- `API.md` - API 接口文档（从 FastAPI 自动导出或手写 Markdown）

## Non-Functional Requirements

### NFR-1: 性能
- 图片生成接口响应时间（P95）< 30s（主要依赖 Agnes AI 官方响应速度）
- 视频创建接口响应时间（P95）< 5s（仅转发，不等待生成完成）
- 历史查询接口响应时间（P95）< 500ms（本地数据库）
- 前端首屏加载 < 3s（基于 Vite 构建优化 + 代码分割）

### NFR-2: 安全性
- API Key 不得出现在前端代码或浏览器网络请求中
- 所有第三方请求（Agnes AI API）均由后端发起
- 图片上传大小限制 ≤ 10MB，视频请求参数校验
- 后端 CORS 配置仅允许前端域名访问

### NFR-3: 可维护性
- 前端组件化，单一职责，组件目录结构清晰
- 后端分层（routes / services / models / schemas / core）
- Python 代码遵循 PEP 8，前端代码遵循 ESLint + Prettier
- 关键逻辑包含中文注释

### NFR-4: 可扩展性
- 易于新增其他 AI 生成模型（仅需添加 service 层实现）
- 数据库抽象层（SQLAlchemy），后续可迁移到 PostgreSQL/MySQL
- 前端路由与组件解耦，便于新增页面

### NFR-5: 可靠性
- 所有网络请求包含错误处理与重试机制（视频轮询）
- Agne AI API 故障时返回清晰错误信息
- 数据库文件自动创建，首次启动无需手动初始化

## Constraints
- **技术栈固定**: 前端 Vue 3 + Vite，后端 Python 3.10+ FastAPI，数据库 SQLite
- **API 供应商固定**: 仅对接 Agnes AI 官方 API（`apihub.agnes-ai.com/v1`）
- **项目结构固定**: `frontend/` 与 `backend/` 目录完全分离，根目录保留 `README.md`
- **部署约束**: 前后端可独立运行，也可由 FastAPI 提供前端静态文件服务（一键部署）

## Assumptions
- 用户已安装 Python 3.10+ 和 Node.js 18+
- 用户可自行从 Agnes AI 平台获取 API Key
- 网络环境可访问 Agnes AI 官方 API
- 单用户/小团队使用，无需复杂的权限管理
- SQLite 数据库存储量足够（单文件通常 ≤ 100MB）

## Acceptance Criteria

### AC-1: 前后端项目结构清晰
- **Given**: 查看项目根目录
- **When**: 列出目录结构
- **Then**: 存在 `frontend/`（Vue 项目）和 `backend/`（FastAPI 项目）两个独立目录，各自有独立的 `package.json` / `requirements.txt`
- **Verification**: human-judgment
- **Notes**: 目录命名需清晰，不混用前后端代码

### AC-2: 文生图功能可用
- **Given**: 用户已启动前后端服务
- **When**: 在前端输入 prompt，选择尺寸，点击"生成图片"
- **Then**: 前端显示加载动画，后端调用 Agnes AI API，在 30s 内返回图片结果，可预览并下载
- **Verification**: programmatic

### AC-3: 图生图功能可用
- **Given**: 用户有一张本地图片
- **When**: 上传图片作为参考图，输入 prompt，点击生成
- **Then**: 图片被转为 base64 发送至后端，后端携带 image 参数调用 Agnes AI，返回生成结果
- **Verification**: programmatic

### AC-4: 文生视频功能可用
- **Given**: 用户输入视频 prompt
- **When**: 选择帧数/帧率/分辨率，点击"生成视频"
- **Then**: 后端创建异步任务返回 task_id，前端显示进度条并每 5s 轮询后端状态，生成完成后显示视频播放器并支持下载
- **Verification**: programmatic

### AC-5: API Key 安全管理
- **Given**: 检查前端构建产物和网络请求
- **When**: 搜索 "AGNES_API_KEY" / "sk-" 等敏感字符串
- **Then**: 前端代码和浏览器网络请求中不出现 Agnes AI API Key，所有对 Agnes API 的调用均经后端代理
- **Verification**: programmatic + human-judgment

### AC-6: 生成历史持久化
- **Given**: 用户已生成若干图片/视频
- **When**: 重启前后端服务后，访问"生成历史"页面
- **Then**: 历史记录仍存在，可按类型筛选、查看详情、删除
- **Verification**: programmatic

### AC-7: 错误处理友好
- **Given**: Agnes AI API 返回错误或 API Key 无效
- **When**: 用户触发生成操作
- **Then**: 前端显示清晰可读的错误信息（非技术参数），不崩溃
- **Verification**: human-judgment

### AC-8: API 文档可访问
- **Given**: 后端服务已启动
- **When**: 访问 `http://localhost:8000/docs`
- **Then**: Swagger UI 展示所有接口，可交互式测试
- **Verification**: programmatic

### AC-9: 项目文档齐全
- **Given**: 查看项目目录
- **When**: 检查根目录、frontend、backend 中的文档文件
- **Then**: 存在 `README.md`（根+前后端），包含安装、配置、启动、API 使用说明
- **Verification**: human-judgment

### AC-10: 响应式布局
- **Given**: 访问前端应用
- **When**: 在桌面 (≥1200px) 和 平板 (768-1199px) 宽度浏览
- **Then**: 布局自适应，不出现水平滚动和元素重叠
- **Verification**: human-judgment

## Open Questions
- [ ] 是否需要引入用户登录/鉴权？（默认: 不需要，单用户模式）
- [ ] 是否需要将 SQLite 替换为 PostgreSQL/MySQL 的配置选项？（默认: 保留 SQLite，但通过 SQLAlchemy 抽象以便未来迁移）
- [ ] 是否需要生成结果的文件本地缓存（将图片/视频下载到本地 output/ 目录）？（默认: 保留 URL，不强制本地存储，可作为可选功能）
- [ ] 前端 UI 框架选择：Element Plus / Ant Design Vue / 纯 CSS？（推荐: Element Plus，组件丰富节省开发时间）
- [ ] 是否需要 Docker 化部署？（默认: 提供 Dockerfile 和 docker-compose.yml 作为可选）
