# 前端 (frontend)

基于 **Vue 3 + Vite + Element Plus** 构建的 Agnes AI Platform 前端应用。

---

## 技术栈

| 技术 | 版本/说明 |
|------|-----------|
| Vue | 3.4+（Composition API） |
| Vite | 5.x |
| Vue Router | 4.x |
| Pinia | 2.x（目前仅预留了结构，简单状态可直接使用 reactive/ref） |
| Element Plus | 2.7+ |
| Axios | 1.x |

---

## 快速启动

```bash
cd frontend

# 安装依赖（首次或 package.json 更新后）
npm install

# 开发模式（默认端口 5173，自动代理 /api 到后端 8000）
npm run dev

# 生产构建（输出到 dist/）
npm run build

# 预览生产构建
npm run preview
```

> ⚠️ 前端启动前**必须先启动后端服务**（端口 8000），否则所有接口调用都会返回 504/500。

---

## 目录结构

```
frontend/
├── index.html               # 入口 HTML（含首屏 loading）
├── vite.config.js           # Vite 配置（代理规则 / 构建优化 / chunk 拆分）
├── package.json
├── .env.example             # 环境变量示例（生产部署时 VITE_API_BASE_URL）
│
└── src/
    ├── main.js              # Vue 应用入口（Element Plus、Router、Pinia 挂载）
    ├── App.vue              # 根组件（顶部导航 + 路由视图）
    │
    ├── router/index.js      # Vue Router 路由配置
    │                          /images, /videos, /history
    │
    ├── api/                 # axios 请求层（统一请求/响应拦截）
    │   ├── client.js        # axios 实例（统一超时、错误提示）
    │   ├── images.js        # 图片生成接口
    │   ├── videos.js        # 视频生成接口（创建任务 + 轮询 + 中止）
    │   └── history.js       # 历史记录 + 平台配置接口
    │
    ├── components/          # 可复用组件
    │   ├── PromptTemplates.vue  # 预设风格 chips（点击追加到 prompt）
    │   └── ImageUploader.vue    # 图片上传（拖拽/本地/URL、自动转 base64）
    │
    ├── views/               # 页面级组件
    │   ├── ImageView.vue    # 图片生成（文生图 / 图生图）
    │   ├── VideoView.vue    # 视频生成（文生视频 / 图生视频 / 关键帧）
    │   └── HistoryView.vue  # 历史记录（筛选 + 详情弹窗 + 删除）
    │
    └── assets/main.css      # 全局样式（深色主题、卡片、按钮美化）
```

---

## 主要设计点

### 1. axios 请求层
`src/api/client.js` 统一封装：
- **开发环境**：使用 Vite 代理，`/api/*` → `http://localhost:8000`
- **生产环境**：通过 `VITE_API_BASE_URL` 配置后端地址
- **超时**：5 分钟（图片生成可能需要较长时间）
- **统一错误提示**：响应拦截器中统一调用 `ElMessage.error`

### 2. 图片上传（ImageUploader）
支持两种模式：
- **本地文件**：拖拽或点击上传，读取为 base64 提交给后端（后端会调用 Agnes AI API）
- **URL**：直接粘贴公网可访问的图片 URL

### 3. 视频异步任务流
```
前端 POST /api/videos           — 创建任务，返回 task_id
      ↓ 每 5s GET /api/videos/{task_id}
后端查询 Agnes 并返回状态
      ↓
完成后前端显示视频播放器
```

### 4. Element Plus 主题
- 使用默认深色变量 + `assets/main.css` 中的自定义样式
- 渐变主色：`linear-gradient(135deg, #5a86ff, #9a7bff)`
- 深色背景：`#0b0f1a`

---

## 环境变量

仅在**生产部署**时需要配置。在开发模式下，通过 Vite 代理到 `http://localhost:8000`，无需配置：

```bash
# frontend/.env （仅在生产部署时创建）
VITE_API_BASE_URL=https://your-backend-domain.com
```

---

## 开发注意事项

- 所有对后端的请求都应使用 `src/api/*.js` 中封装的方法，**不要在组件内直接使用裸 axios**
- 新增页面时，在 `src/router/index.js` 中添加路由，并在顶部导航 `<App.vue>` 中添加菜单
- UI 组件优先使用 Element Plus，必要时才写自定义样式
- 响应式布局使用 Element Plus 的 `el-row/el-col` 栅格系统 + `:xs/:md` 断点
- 新增接口后，也请同步更新根目录的 `API.md`
