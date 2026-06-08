# Agnes AI · 图片与视频生成平台

> 基于 **Vue 3 + FastAPI** 构建的前后端分离 AI 内容生成平台，对接 Agnes AI 官方 API，支持文生图、图生图、文生视频、图生视频以及关键帧动画。

---

## 🌟 功能特性

- 🖼️ **图片生成**：文生图 / 图生图，支持多种尺寸与风格模板
- 🎬 **视频生成**：文生视频 / 图生视频 / 关键帧动画，异步任务自动轮询
- 📜 **历史记录**：SQLite 持久化存储，支持类型筛选、详情查看、删除
- 🔐 **API Key 安全管理**：Key 仅存储于服务端环境变量，前端无感知
- 🎨 **现代化 UI**：基于 Element Plus 的深色主题，响应式布局
- 📚 **自动 API 文档**：FastAPI Swagger UI，交互式调试接口

---

## 🏗️ 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 (Composition API) + Vite + Vue Router + Pinia + Axios + Element Plus |
| 后端 | Python 3.10+ · FastAPI · SQLAlchemy · httpx（异步 HTTP 客户端） |
| 数据库 | SQLite（默认）/ PostgreSQL（可选，通过 `DATABASE_URL` 切换） |
| AI 服务商 | Agnes AI（`https://apihub.agnes-ai.com/v1`） |

### 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    用户浏览器 (Chrome/Safari...)              │
│  ┌──────────────────────────┐   ┌─────────────────────────┐ │
│  │   Vue 3 SPA (frontend)   │   │  生成结果 / 历史界面    │ │
│  │  - 图片/视频生成页面     │   │  - 下载 / 预览 / 复制   │ │
│  │  - 历史页面              │   └─────────────────────────┘ │
│  │  - Element Plus UI       │                                 │
│  └──────────────────────────┘                                 │
└──────────────┬────────────────────────────────────────────────┘
               │ HTTP / JSON (Vite dev proxy 或生产静态文件)
               ▼
┌─────────────────────────────────────────────────────────────┐
│                BFF 层 - FastAPI (backend)                    │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Routes: /api/images, /api/videos, /api/history, ...    │ │
│  └─────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Services: agnes_client (Agnes AI API 封装)              │ │
│  │            video_poller (视频异步任务轮询管理器)          │ │
│  └─────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  SQLAlchemy → SQLite / PostgreSQL (生成历史持久化)        │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────┬────────────────────────────────────────────────┘
               │ HTTP / JSON (带 Bearer Token)
               ▼
┌─────────────────────────────────────────────────────────────┐
│               Agnes AI 官方 API (apihub.agnes-ai.com)        │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 1. 前置条件

- **Python** ≥ 3.10（建议 3.11+）
- **Node.js** ≥ 18（建议 20+ LTS）
- 一个有效的 **Agnes AI API Key**（前往 [platform.agnes-ai.com](https://platform.agnes-ai.com) 申请）

### 2. 克隆项目

```bash
git clone <your-repo-url>
cd agnes-platform
```

### 3. 配置后端

```bash
cd backend

# 安装 Python 依赖（建议使用虚拟环境）
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# 或 Windows: .venv\Scripts\activate

pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

### 4. 启动后端服务

```bash
# 位于 backend/ 目录下
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

打开浏览器访问以下地址验证：
- **健康检查**：http://localhost:8000/health
- **API 文档（Swagger UI）**：http://localhost:8000/docs

### 5. 配置并启动前端

打开**新的终端窗口**：

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器（默认 5173 端口，Vite 自动代理 /api 到后端 8000）
npm run dev
```

访问 http://localhost:5173 即可使用平台。

---

## 📁 项目结构

```
agnes-platform/
├── README.md                         # 根目录总览
├── API.md                            # REST API 接口文档
├── .gitignore
│
├── frontend/                         # 前端（Vue 3 + Vite）
│   ├── README.md
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   ├── .env.example
│   └── src/
│       ├── main.js                   # 入口（挂载 Element Plus / Router / Pinia）
│       ├── App.vue                   # 根组件
│       ├── router/index.js           # 路由配置
│       ├── stores/                   # Pinia 全局状态
│       │   └── index.js
│       ├── api/                      # axios 封装与接口请求
│       │   ├── client.js
│       │   ├── images.js
│       │   ├── videos.js
│       │   └── history.js
│       ├── components/               # 可复用组件
│       │   ├── AppLayout.vue
│       │   ├── ImageUploader.vue
│       │   ├── PromptTemplates.vue
│       │   └── ...
│       ├── views/                    # 页面级组件
│       │   ├── ImageView.vue
│       │   ├── VideoView.vue
│       │   └── HistoryView.vue
│       └── assets/                   # CSS 样式与静态资源
│           └── main.css
│
├── backend/                          # 后端（FastAPI）
│   ├── README.md
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── main.py                   # FastAPI 入口，路由注册、CORS、Lifespan
│       ├── core/                     # 核心配置
│       │   ├── config.py             # pydantic-settings 环境变量加载
│       │   └── database.py           # SQLAlchemy engine / session / Base
│       ├── models/                   # ORM 模型
│       │   └── generation.py         # Generation 模型（历史记录）
│       ├── schemas/                  # Pydantic 请求/响应 Schema
│       │   ├── images.py
│       │   ├── videos.py
│       │   └── common.py
│       ├── services/                 # 业务服务层
│       │   ├── agnes_client.py       # Agnes AI API 客户端封装
│       │   └── video_poller.py       # 视频异步任务轮询管理器
│       └── routes/                   # API 路由
│           ├── images.py
│           ├── videos.py
│           ├── history.py
│           └── config.py
│
└── legacy/                           # 原始纯前端实现（归档，仅供参考）
    ├── index.html
    ├── app.js
    └── styles.css
```

---

## 💡 切换到 PostgreSQL（可选）

本项目默认使用 SQLite，零配置即可运行。如需切换到 PostgreSQL：

1. 安装驱动：`pip install psycopg2-binary`
2. 在 `backend/.env` 中修改：
   ```
   DATABASE_URL=postgresql://username:password@localhost:5432/agnes_platform
   ```
3. 重启后端服务即可，SQLAlchemy 会自动处理

---

## ❓ FAQ

**Q: 为什么需要 BFF 层？直接在前端调 Agnes AI 不行吗？**

A: 纯前端架构有两个核心问题：(1) API Key 暴露在浏览器中，容易被窃取；(2) 无法实现持久化历史记录、服务端任务管理等功能。引入 BFF 层后，API Key 仅在服务端，安全性显著提升。

**Q: 视频生成需要多久？**

A: 通常需要 2–6 分钟。平台会在后台自动轮询，前端显示实时进度，无需手动刷新。

**Q: 生成的图片/视频保存在哪里？**

A: 默认由 Agnes AI 托管，返回公网 URL。历史记录（Prompt、参数、URL）保存在本地 SQLite 数据库中。

---

## 📜 License

MIT © Agnes AI Platform
