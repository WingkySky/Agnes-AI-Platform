# Agnes AI Platform · 后端 (FastAPI)

> BFF（Backend for Frontend）服务：统一管理 Agnes AI API 调用、
> 视频异步任务轮询、生成历史持久化。

---

## 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI 0.115 |
| 异步 HTTP 客户端 | httpx |
| ORM | SQLAlchemy 2.0 |
| 数据库 | SQLite（默认）/ PostgreSQL（可选） |
| 配置管理 | pydantic-settings + .env |
| Python | ≥ 3.10 |

---

## 目录结构

```
backend/
├── app/
│   ├── main.py                 # FastAPI 入口 / 路由注册 / CORS / Lifespan
│   ├── core/
│   │   ├── config.py           # 环境变量加载与全局配置
│   │   └── database.py         # SQLAlchemy engine / Session / Base
│   ├── models/
│   │   └── generation.py       # Generation 历史记录表模型
│   ├── schemas/
│   │   ├── common.py           # 通用 / 历史记录 Schema
│   │   ├── images.py           # 图片请求/响应 Schema
│   │   └── videos.py           # 视频请求/响应 Schema
│   ├── services/
│   │   ├── agnes_client.py     # Agnes AI API 客户端封装（3 层模块化设计）
│   │   └── video_poller.py     # 视频异步任务轮询管理器
│   └── routes/
│       ├── config.py           # GET /api/config
│       ├── images.py           # POST /api/images/generations
│       ├── videos.py           # POST /api/videos + GET /api/videos/{id}
│       └── history.py          # GET /api/history + DELETE /api/history/{id}
├── requirements.txt
├── .env.example
└── README.md
```

---

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 Agnes AI API Key
```

`.env` 关键变量：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AGNES_API_KEY` | Agnes AI API Key | **必填** |
| `AGNES_API_BASE_URL` | API 根地址 | `https://apihub.agnes-ai.com/v1` |
| `AGNES_API_POLL_URL` | 视频轮询专用接口 | `https://apihub.agnes-ai.com/agnesapi` |
| `DATABASE_URL` | 数据库连接串 | `sqlite:///./agnes_platform.db` |
| `FRONTEND_ORIGINS` | 允许的前端来源（逗号分隔） | `http://localhost:5173` |
| `VIDEO_POLL_INTERVAL_SEC` | 视频轮询间隔秒数 | `5` |
| `VIDEO_POLL_TIMEOUT_SEC` | 视频轮询超时秒数 | `600` |

### 3. 启动服务

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- API 文档 (Swagger UI): http://localhost:8000/docs
- 健康检查: http://localhost:8000/health
- 前端配置: http://localhost:8000/api/config

### 4. 切换到 PostgreSQL（可选）

```bash
pip install psycopg2-binary
# 修改 .env:
# DATABASE_URL=postgresql://username:password@localhost:5432/agnes_platform
```

---

## API 接口一览

| 方法 | 路径 | 功能 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `GET` | `/api/config` | 获取前端非敏感配置 |
| `POST` | `/api/images/generations` | 创建图片生成任务（同步返回结果） |
| `GET` | `/api/images/{id}` | 获取单张图片历史记录 |
| `POST` | `/api/videos` | 创建视频生成任务（异步，返回 task_id） |
| `GET` | `/api/videos/{task_id}` | 查询视频任务状态 / 获取视频 URL |
| `DELETE` | `/api/videos/{task_id}` | 中止视频任务 |
| `GET` | `/api/history` | 获取历史列表（支持 type 筛选 + 分页） |
| `DELETE` | `/api/history/{id}` | 删除单条历史记录 |

---

## 架构说明

### 三层模块化的 API 调用设计（参考 agnes-media-create Skill）

```
┌──────────────────────────────────────────────┐
│  routes/*.py                                  │   路由层：参数校验、依赖注入、返回响应
│  (images.py / videos.py / history.py)         │
└──────────────┬───────────────────────────────┘
               │
┌──────────────▼───────────────────────────────┐
│  services/*.py                                │   业务服务层
│  ├── agnes_client.py  -> API 方法层           │   - 图片/视频的 Agnes AI API 封装
│  └── video_poller.py -> 轮询管理器            │   - 视频异步任务后台轮询
└──────────────┬───────────────────────────────┘
               │
┌──────────────▼───────────────────────────────┐
│  core/                                        │   底层基础层
│  ├── config.py    -> 环境变量 + 配置         │
│  └── database.py  -> SQLAlchemy 连接         │
└──────────────────────────────────────────────┘
```

### 视频任务流程

```
前端 POST /api/videos
    └─► 后端转发给 Agnes AI /v1/videos
        └─► 返回 {video_id, task_id}
    └─► 立即返回前端（异步）
    └─► 后台启动 video_poller 协程：
           ├─ 每 5 秒调用 agnesapi?video_id=xxx
           ├─ 更新内存中的任务状态
           └─ 完成/失败时写入 Generation 表

前端 GET /api/videos/{task_id} (定时轮询)
    └─► 优先读取 poller_manager 的内存缓存
           └─ 已完成? 返回 video_url
           └─ 未完成? 返回进度 / 状态
    └─► 缓存中找不到，则回退查询数据库历史
```

### 图片任务流程

```
前端 POST /api/images/generations
    └─► 后端同步调用 Agnes AI /v1/images/generations
    └─► 成功后写入 Generation 表
    └─► 返回图片 URL 或 base64
```
