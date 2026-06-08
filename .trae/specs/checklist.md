# Agnes AI 平台重构 - 验收清单（Verification Checklist）

## 1. 项目结构（AC-1）

- [ ] 根目录存在 `frontend/` 与 `backend/` 两个独立目录
- [ ] `frontend/` 下有 `package.json`，不含任何 Python/数据库相关文件
- [ ] `backend/` 下有 `requirements.txt`，不含任何 Node.js/Vue 相关文件
- [ ] 原有 `app.js` / `index.html` / `styles.css` 已归档到 `legacy/` 目录
- [ ] 根目录存在 `.gitignore`，包含 `__pycache__`, `node_modules`, `.env`, `*.db`, `*.sqlite` 等忽略项

## 2. 后端服务启动与基础功能（AC-8）

- [ ] `cd backend && pip install -r requirements.txt` 可成功安装依赖
- [ ] `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` 可成功启动
- [ ] 访问 `http://localhost:8000/health` 返回 `{"status": "ok"}` 200 响应
- [ ] 访问 `http://localhost:8000/docs` 可看到 Swagger UI，列出所有接口
- [ ] 访问 `http://localhost:8000/api/config` 返回包含支持模型/尺寸的 JSON，**不含 API Key**
- [ ] 首次启动时 `backend/agnes_platform.db` SQLite 文件自动创建

## 3. API Key 安全（AC-5）

- [ ] `frontend/src` 目录全文搜索 `AGNES_API_KEY` / `agnes_api_key` / `sk-` 无匹配
- [ ] `frontend/.env.example` 中不含 API Key 配置项
- [ ] 浏览器开发者工具查看网络请求，不包含对 `apihub.agnes-ai.com` 的直接请求
- [ ] 所有 AI 生成请求均通过 `http://localhost:8000/api/*` 代理

## 4. 图片生成功能（AC-2, AC-3）

- [ ] 图片生成页面正常显示：模式切换 Tab、Prompt 输入框、预设风格 chips、尺寸选择器、生成按钮
- [ ] **文生图流程**：输入 prompt → 点击生成 → 显示加载动画 → ~30s 内返回图片 → 图片预览显示 → 可点击放大 → 可下载 → 可复制链接
- [ ] **图生图流程**：切换到图生图模式 → 上传本地图片（或粘贴 URL）→ 输入 prompt → 点击生成 → 结果正确显示
- [ ] 上传超过 10MB 图片时返回明确错误提示
- [ ] 空 prompt 点击生成时，前端有即时校验，不发送无效请求

## 5. 视频生成功能（AC-4）

- [ ] 视频生成页面正常显示：模式切换、参考图上传区、Prompt 输入、帧数/帧率/分辨率配置、负向 Prompt、生成/中止按钮
- [ ] **文生视频流程**：输入 prompt → 选择参数 → 点击生成 → 立即返回 task_id 并显示进度条 → 每 5s 自动轮询后端状态 → 完成后显示 video 播放器 → 可播放/下载/复制链接
- [ ] **中止功能**：生成过程中点击中止 → 立即停止轮询，显示"已中止"提示
- [ ] **图生视频/关键帧流程**：上传参考图 → 输入 prompt → 生成 → 同上完整流程
- [ ] 视频参数校验：帧数不符合 8n+1 规则时给出友好提示（如果有此校验）

## 6. 生成历史持久化（AC-6）

- [ ] 历史页面显示已生成的所有记录，卡片网格布局
- [ ] 每条记录包含：缩略图、类型标签（图片/视频）、Prompt 片段、时间
- [ ] 类型筛选 Tab（全部/图片/视频）正常工作
- [ ] 点击卡片弹出详情 Modal：大图/视频预览、完整 Prompt、参数列表
- [ ] 删除按钮带确认对话框，确认后记录从列表和数据库中移除
- [ ] **重启后端服务后**，历史记录仍然保留
- [ ] 分页工作正常（如果实现了分页）

## 7. 错误处理与用户体验（AC-7）

- [ ] API Key 未配置时启动后端，日志中有明确警告
- [ ] Agnes AI API 返回错误（如 401 Unauthorized），前端显示可读错误消息，不显示原始 stack trace
- [ ] 网络断开时，前端不会卡死，显示"网络连接失败，请检查网络"类提示
- [ ] 请求超时后有自动重试或明确超时提示
- [ ] Toast/通知样式统一，不遮挡主要操作区

## 8. 前端响应式布局（AC-10）

- [ ] 桌面宽度（≥1200px）：左右布局，图片/视频生成界面左侧输入区、右侧结果区
- [ ] 平板宽度（768-1199px）：布局自适应上下结构，元素不重叠
- [ ] 所有输入控件在各种宽度下均可操作
- [ ] 无水平滚动条出现

## 9. 代码质量与可维护性（NFR-3, NFR-4）

- [ ] 后端文件组织：`core/`, `models/`, `schemas/`, `services/`, `routes/` 分层清晰
- [ ] 前端文件组织：`components/`, `views/`, `api/`, `stores/`, `router/`, `assets/` 分层清晰
- [ ] 关键函数/复杂逻辑包含中文注释
- [ ] Python 代码遵循 PEP 8（命名规范、4 空格缩进、行宽合理）
- [ ] Vue 组件使用 `<script setup>` 组合式 API，逻辑清晰
- [ ] HTTP 请求统一经过 axios 封装，错误处理一致

## 10. 文档完整性（AC-9）

- [ ] 根目录 `README.md` 存在，包含：项目简介、技术栈、快速启动（包含具体命令）、目录说明
- [ ] `frontend/README.md` 存在，包含：前端技术栈、目录结构、组件说明、开发/构建命令
- [ ] `backend/README.md` 存在，包含：后端技术栈、环境变量列表、API 路由说明、启动命令
- [ ] `API.md`（或同等文档）存在，列出所有 REST 接口的路径、方法、请求/响应字段
- [ ] `backend/.env.example` 存在，包含所需的全部环境变量配置项
- [ ] `frontend/.env.example` 存在，包含前端配置项

## 11. 架构完整性（整体设计验证）

- [ ] 前端通过 axios + Vite dev proxy 访问后端 `/api/*`
- [ ] 后端通过 httpx 访问 Agnes AI 官方 API，统一管理 API Key
- [ ] 数据库通过 SQLAlchemy 操作，与业务逻辑解耦
- [ ] 视频任务轮询在后端通过 asyncio 管理，前端仅轮询后端接口
- [ ] FastAPI lifespan 事件正确初始化资源

## 12. 安全性检查

- [ ] CORS 配置仅允许配置的前端域名访问
- [ ] 请求体大小限制已配置，防止超大上传
- [ ] API Key 只在服务端进程环境中使用，不记录到日志
- [ ] 用户输入（Prompt）在返回前端展示时做了 HTML 转义，防止 XSS
- [ ] `.env` 文件已在 `.gitignore` 中排除

---

## 最终验收状态

- [ ] **全部检查项通过** — 可标记为完成
- [ ] **存在未解决问题** — 记录问题并回到相应 Task 修复

### 发现的问题记录

（此处填写联调测试中发现的具体问题与修复状态）
