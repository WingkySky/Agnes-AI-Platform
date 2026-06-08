# Agnes AI Platform · REST API 文档

后端端口：`http://localhost:8000`  
Swagger UI（交互式文档）：`http://localhost:8000/docs`  
健康检查：`http://localhost:8000/health`

> 说明：所有接口（除 `/health`、`/docs` 外）均以 `/api` 为前缀。返回 JSON 格式响应。

---

## 1. 平台配置

### `GET /api/config`

获取前端可用的非敏感配置（不包含 API Key 等敏感信息）。

**响应示例：**
```json
{
  "image_sizes": ["1024x1024", "1024x768", "768x1024", "512x512"],
  "image_models": ["agnes-image-2.1-flash"],
  "video_models": ["agnes-video-v2.0"],
  "video_num_frames": [9, 33, 49, 81, 121, 161, 241, 441],
  "default_frame_rate": 24,
  "default_video_width": 1152,
  "default_video_height": 768,
  "max_upload_size_mb": 10
}
```

---

## 2. 图片生成

### `POST /api/images/generations`

创建图片生成请求。此接口**同步阻塞**直到 Agnes AI 返回结果（通常 15-60 秒）。

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `prompt` | string | ✅ | 提示词（1-2000 字符） |
| `model` | string | | 模型名，默认 `agnes-image-2.1-flash` |
| `size` | string | | 尺寸，如 `1024x1024`、`1024x768`、`768x1024` |
| `response_format` | string | | `url`（默认）或 `b64_json` |
| `base64_image` | string | | **图生图时必填**，纯 base64 字符串，不带 `data:image/...` 前缀 |

**请求示例（文生图）：**
```json
{
  "prompt": "一只坐在月球上的小猫，超现实主义风格",
  "size": "1024x1024"
}
```

**请求示例（图生图）：**
```json
{
  "prompt": "把图片改成日落风格",
  "size": "1024x1024",
  "base64_image": "iVBORw0KGgoAAAANS..."
}
```

**响应示例（成功，HTTP 200）：**
```json
{
  "id": 42,
  "status": "success",
  "url": "https://apihub.agnes-ai.com/v1/images/xxx/yyy.png",
  "model": "agnes-image-2.1-flash",
  "prompt": "一只坐在月球上的小猫...",
  "size": "1024x1024",
  "created_at": "2025-06-08T10:30:00"
}
```

**错误响应（示例）：**
```json
{
  "status": "error",
  "message": "Agnes AI API 错误（HTTP 401）: Invalid API key"
}
```

---

## 3. 视频生成

### `POST /api/videos`

创建视频生成异步任务。立即返回 `task_id`，前端需通过 GET 接口轮询状态。

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `prompt` | string | ✅ | 提示词 |
| `negative_prompt` | string | | 负向提示词 |
| `model` | string | | 默认 `agnes-video-v2.0` |
| `num_frames` | int | | 帧数，**必须是 `8n+1`**（如 9, 33, 121, 241, 441）。默认 121 |
| `frame_rate` | int | | 帧率 1-60，默认 24 |
| `width` / `height` | int | | 分辨率，默认 1152×768 |
| `mode` | string | | `text2video`（默认）| `image2video` | `keyframes` |
| `image` | string | | 图生视频模式：单张参考图（URL 或 base64） |
| `images` | string[] | | 关键帧模式：多张图片 URL/base64 数组 |
| `seed` | int | | 随机种子，可选 |

**响应示例（HTTP 200）：**
```json
{
  "task_id": "task_abc123xyz",
  "video_id": "video_xyz789",
  "status": "pending",
  "prompt": "...",
  "model": "agnes-video-v2.0",
  "num_frames": 121,
  "frame_rate": 24,
  "width": 1152,
  "height": 768,
  "mode": "text2video",
  "message": "任务已创建，请轮询 GET /api/videos/{task_id} 获取最新状态"
}
```

### `GET /api/videos/{task_id}`

查询视频生成任务状态。后端优先从内存缓存读取（实时），如任务已完成或缓存失效则返回数据库中的历史记录。

**响应示例（进行中）：**
```json
{
  "task_id": "task_abc123xyz",
  "status": "processing",
  "progress": 35,
  "video_url": null,
  "message": null,
  "elapsed_sec": 62
}
```

**响应示例（成功）：**
```json
{
  "task_id": "task_abc123xyz",
  "status": "success",
  "progress": 100,
  "video_url": "https://apihub.agnes-ai.com/v1/videos/xxx/yyy.mp4",
  "message": null,
  "elapsed_sec": 186
}
```

**响应示例（失败）：**
```json
{
  "task_id": "task_abc123xyz",
  "status": "failed",
  "progress": 0,
  "video_url": null,
  "message": "Invalid prompt: contains blocked words",
  "elapsed_sec": 3
}
```

### `DELETE /api/videos/{task_id}`

中止一个正在进行中的视频任务。仅停止本地轮询，不保证远端服务已停止。

**响应示例：**
```json
{
  "success": true,
  "message": "已尝试中止任务 task_abc123xyz"
}
```

---

## 4. 历史记录

### `GET /api/history`

获取生成历史。支持按类型筛选 + 分页。

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | | `all`（默认）| `image` | `video` |
| `page` | int | | 页码，从 1 开始，默认 1 |
| `page_size` | int | | 每页数量，默认 20 |

**响应示例：**
```json
{
  "total": 128,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 1,
      "type": "image",
      "prompt": "一只坐在月球上的小猫...",
      "model": "agnes-image-2.1-flash",
      "params": { "size": "1024x1024" },
      "result_url": "https://...",
      "status": "success",
      "task_id": null,
      "created_at": "2025-06-08T10:30:00Z"
    },
    ...
  ]
}
```

### `DELETE /api/history/{id}`

删除单条历史记录。

**响应示例：**
```json
{
  "success": true,
  "message": "已删除记录 ID=42"
}
```

---

## 5. 错误码说明

| HTTP 状态 | 含义 |
|----------|------|
| 200 | 成功 |
| 400 | 参数校验失败（如 num_frames 不符合 8n+1 规则） |
| 401 | Agnes AI API Key 未配置或无效 |
| 404 | 资源不存在（如查询不存在的 task_id） |
| 413 | 上传的图片超过大小限制（默认 10 MB） |
| 500 | 服务端内部错误 |
| 502 | Agnes AI 官方 API 返回错误 |
| 504 | 请求超时 |

---

## 6. 后端到 Agnes AI 的请求流

```
前端 axios
    ↓
Vite 代理（开发模式）或 Nginx（生产）
    ↓
FastAPI backend (8000)
    ├→ 校验 API Key 配置（AGNES_API_KEY）
    ├→ 组装请求参数
    └→ httpx → Agnes AI (apihub.agnes-ai.com)
            ↓ （图片同步 / 视频异步）
    ┌── 解析响应，写入 SQLite
    ↓
前端得到结果（url, task_id, video_url 等）
```
