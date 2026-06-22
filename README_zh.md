# Agnes AI Platform

![Python](https://img.shields.io/badge/python-3776AB?logo=python&logoColor=white) ![Vue](https://img.shields.io/badge/vue-4FC08D?logo=vuedotjs&logoColor=white) ![License](https://img.shields.io/badge/license-Apache%202.0%20%2B%20Commons%20Clause-red)

**🌐 Language / 语言**

[English](README.md) | [**中文** ](README_zh.md)

**一站式 AI 创作平台 —— 与 AI 对话、生成图片与视频、在无限画布上自由编排。** 基于 Agnes AI，采用 Vue 3 + FastAPI 全栈架构，API Key 安全地保存在服务端。

## Agnes AI Platform 是什么

Agnes AI Platform 是一个可自部署的 Web 应用，将多种 AI 能力整合为统一体验：

- **AI 对话** — 支持工具调用的对话式 AI。自然聊天，AI 检测到你的意图时会自动触发生图或生视频。
- **图片生成** — 文生图、图生图，支持多种模型和尺寸选择。
- **视频生成** — 文生视频、图生视频、关键帧动画，异步轮询 + 实时进度。
- **无限画布** — 自由工作区，将生成的图片放置为节点、连线、基于上下文重新生成或混合创作。
- **多 Provider 管理** — 在设置页面添加和切换多个 AI API 提供商（不同 base URL、API Key），首次配置后无需再改 `.env` 文件。
- **生成历史** — 持久化历史记录，缩略图、GIF 预览、筛选、批量操作。

所有 API Key 均加密存储在服务端，不会暴露到浏览器。

## 项目演进

Agnes AI Platform 最初只是一个简单的图片和视频生成工具，逐步演化为现在的综合 AI 创作平台：

| 阶段 | 变化 |
|---|---|
| **v1 — 生成器** | 文生图、图生图、文生视频、图生视频。一个干净的生成工具，带异步轮询和历史记录。 |
| **v2 — 多 Provider** | 用数据库驱动的 Provider 系统替代了单一的 `.env` API Key。可在前端界面增删改查 Provider，API Key 加密存储。 |
| **v3 — AI 对话** | 加入对话式 AI 界面，支持工具调用。AI 能识别意图并自动触发生图/生视频，完整 SSE 流式输出。 |
| **v4 — 无限画布** | 引入自由画布，用于编排和混合已生成的图片。节点、连线、蒙版编辑、上下文感知的重新生成。 |

平台仍在持续演进，但核心理念始终不变：**一个自部署、安全、一站式 AI 创作工作台。**

## 快速开始

### 前置条件

| 工具 | 版本 | 用途 |
|---|---|---|
| **Python** | 3.10+（推荐 3.11+） | 后端运行时 |
| **Node.js** | 18+（推荐 20+ LTS） | 前端构建 |

### 1. 一键启动

在项目根目录下打开终端，运行：

```bash
# macOS / Linux — 首次运行需授予执行权限
chmod +x start.sh
./start.sh

# Windows
start.bat

# 或使用跨平台 Python 启动器（无需额外授权）
python start.py
```

> **macOS / Linux 首次运行**：从 Git 下载或跨机器拷贝的 `.sh` 脚本可能没有执行权限，直接运行会报 "permission denied"。首次运行前需执行一次 `chmod +x start.sh` 授权。
>
> **macOS Gatekeeper 拦截**：如果 macOS 提示"无法打开，因为来自身份不明的开发者"，前往 **系统设置 → 隐私与安全性** 点击"仍要打开"，或在终端执行 `xattr -d com.apple.quarantine start.sh`。
>
> **Windows**：`.bat` 文件可直接运行，无需额外授权。若被 SmartScreen 拦截，点击"更多信息 → 仍要运行"即可。

脚本会自动启动后端和前端，首次运行会提示你配置 API Key。

> **默认管理员账号**：启动脚本会自动初始化数据库并创建超级管理员：
> - 用户名：`admin`
> - 密码：`admin123`
>
> 可在首次运行前通过环境变量 `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ADMIN_EMAIL` / `ADMIN_CREDITS` 自定义。首次登录后请及时修改默认密码。

### 2. 手动启动

#### 后端

```bash
cd backend

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate      # macOS / Linux
# Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env — 至少填入 AGNES_API_KEY 作为初始默认 Provider。
# 首次启动后，可在前端设置页面管理 Provider，无需再改 .env。
```

启动后端（macOS / Linux）：

```bash
./start.sh
```

启动后端（Windows）：

```batch
start.bat
```

或手动启动：

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

验证：http://localhost:8000/health 或 http://localhost:8000/docs

#### 前端

打开一个**新终端**：

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器（端口 5173，自动代理 /api → 后端:8000）
npm run dev
```

访问 http://localhost:5173 即可使用。

### 3. 首次配置

1. 打开**设置**页面（`/settings`）。
2. `.env` 中的 API Key 会自动加载为默认 Provider。
3. 如需添加更多 Provider，直接在设置页面操作 — 每个 Provider 可配置独立的 base URL 和 API Key。
4. 开始创作 — 对话、生成图片/视频、或打开画布。

## 技术栈

| 层级 | 技术 |
|---|---|
| 前端 | Vue 3（Composition API）+ Vite + TypeScript + Vue Router + Pinia + Element Plus |
| 后端 | Python 3.10+ · FastAPI · SQLAlchemy 2.0（异步）· httpx（异步 HTTP 客户端） |
| 数据库 | SQLite（默认，零配置）/ PostgreSQL（可选） |
| AI 服务 | Agnes AI API（兼容 OpenAI 格式） |

## 常见问题

**Q：为什么需要 BFF 层，而不是直接在浏览器调用 AI API？**

A：两个原因 — (1) API Key 始终留在服务端，不会暴露到浏览器；(2) 服务端负责异步任务轮询、历史持久化和媒体处理，这些纯前端无法可靠完成。

**Q：视频生成需要多长时间？**

A：通常 2–6 分钟。平台在后台自动轮询，你可以离开当前页面，稍后回来查看结果。

**Q：可以使用其他兼容 OpenAI 的 API 吗？**

A：可以。在设置页面添加新 Provider，填入自定义 base URL 和 API Key 即可。平台支持任何兼容 OpenAI 格式的对话、图片和视频接口。

**Q：可以部署到生产环境吗？**

A：可以。构建前端（`npm run build`）后以静态文件方式部署，后端使用任何 ASGI 宿主部署。设置 `FRONTEND_ORIGINS` 和 `DATABASE_URL` 为生产环境值即可。

## 许可证

Apache License 2.0 + Commons Clause — 源码开放，个人、教育和研究用途可自由使用。**禁止商用。** 详见 [LICENSE](LICENSE)。
