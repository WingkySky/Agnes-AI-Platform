# Agnes AI Platform · REST API 文档

后端端口：`http://localhost:8000`  
Swagger UI（交互式文档）：`http://localhost:8000/docs`  
健康检查：`http://localhost:8000/health`

> 说明：所有接口（除 `/health`、`/docs` 外）均以 `/api` 为前缀。返回 JSON 格式响应。

---

## 官方文档参考

完整的 Agnes AI 官方 API 文档已保存在 `doc/` 目录：
- [Agnes Video V2.0 接入指南](doc/agnes-video-v2.0.md)
- [Agnes Image 2.1 Flash 接入指南](doc/agnes-image-2.1-flash.md)

---

## 1. 平台配置

### `GET /api/config`

获取前端可用的非敏感配置（不包含 API Key 等敏感信息）。

**响应示例：**
```json
{
  "image_sizes": ["1024x1024", "1024x768", "768x1024", "576x1024", "1024x576"],
  "image_models": ["agnes-image-2.1-flash"],
  "video_models": ["agnes-video-v2.0"],
  "video_num_frames": [81, 121, 161, 241, 321, 401, 441],
  "video_resolutions": ["480p", "720p", "1080p", "2K", "4K"],
  "default_frame_rate": 24,
  "default_video_width": 1152,
  "default_video_height": 768,
  "max_upload_size_mb": 10,
  "max_image_prompt_length": 4000,
  "max_video_prompt_length": 3000
}
```

**配置说明：**
- 视频分辨率支持：480p、720p、1080p、2K、4K（宽高必须为 8 的倍数）
- 视频帧数 `num_frames` 必须满足 `8n + 1` 格式且 ≤ 441
- 视频帧率 `frame_rate` 支持范围 1-60，默认 24
- 图片提示词最大长度：4000 字符
- 视频提示词最大长度：3000 字符

---

## 2. 图片生成

### 模型说明

当前使用 `agnes-image-2.1-flash` 模型，支持：
- 文生图（text-to-image）
- 图生图（image-to-image）
- 支持 URL 或 Base64 输入输出
- 针对高信息密度图像优化

**重要参数规范（来自官方文档）：**
- `response_format` **必须**放在 `extra_body` 中（顶层会返回 400 错误）
- 文生图 Base64 输出使用顶层参数 `return_base64: true`
- 图生图图片放在 `extra_body.image` 数组中
- 不需要传 `tags: ["img2img"]`

### `POST /api/images/generations`

创建图片生成请求。此接口**同步阻塞**直到 Agnes AI 返回结果（通常 15-60 秒）。

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `prompt` | string | ✅ | 提示词（1-4000 字符） |
| `model` | string | | 模型名，默认 `agnes-image-2.1-flash` |
| `size` | string | | 尺寸，如 `1024x1024`、`1024x768`、`768x1024`、`576x1024`、`1024x576` |
| `response_format` | string | | `url`（默认）或 `b64_json` |
| `base64_image` | string | | **图生图时必填**，纯 base64 字符串，不带 `data:image/...` 前缀 |
| `image_url` | string | | 图生图时可传入公网图片 URL |
| `base64_images` | string[] | | 多图图生图：base64 数组 |
| `image_urls` | string[] | | 多图图生图：URL 数组 |
| `mask` | string | | 局部编辑：蒙版图 base64（白色为编辑区域） |

**支持的标准尺寸：**

| 尺寸 | 宽高比 | 适用场景 |
|------|--------|----------|
| `1024x1024` | 1:1 | 方形、社交媒体 Feed |
| `1024x768` | 4:3 | 传统横图 |
| `768x1024` | 3:4 | 竖图、人物/商品展示 |
| `1024x576` | 16:9 | 横屏视频封面、宽屏展示 |
| `576x1024` | 9:16 | 竖屏短视频封面 |

**请求示例（文生图）：**
```json
{
  "prompt": "一只坐在月球上的小猫，超现实主义风格，电影级光照",
  "size": "1024x1024"
}
```

**请求示例（图生图）：**
```json
{
  "prompt": "把图片改成日落风格，保持原构图",
  "size": "1024x1024",
  "base64_image": "iVBORw0KGgoAAAANS..."
}
```

**响应示例（成功，HTTP 200）：**
```json
{
  "id": 42,
  "status": "success",
  "url": "https://storage.googleapis.com/agnes-aigc/xxx.png",
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

### `POST /api/images/tasks`

创建图片生成异步任务（前端任务队列使用）。立即返回 `task_id`，通过 `GET /api/images/tasks/{task_id}` 轮询状态。

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `prompt` | string | ✅ | 提示词 |
| `model` / `size` / `mode` / `image_urls` / `base64_images` 等 | - | | 与 `POST /api/images/generations` 一致 |
| `context` | object | | 创作上下文（可选），结构与视频接口相同：`{ source, container_type, container_id, container_name, asset_type, asset_name }`。带 `container_type`/`container_id` 时生成结果自动归档进资产库 |

---

## 3. 视频生成

### 模型说明

当前使用 `agnes-video-v2.0` 模型，支持：
- 文生视频（text-to-video）
- 图生视频（image-to-video）：支持单张或多张参考图，自动识别
- 关键帧动画（keyframes）：1-2张图片（起始帧必填，结束帧可选），在帧之间生成平滑过渡
- 异步任务 API，需要轮询结果

**重要更新（来自最新官方文档）：**
1. **推荐使用 `video_id` 查询结果**：创建任务返回 `video_id`，使用 `/agnesapi?video_id=...` 端点轮询
2. **旧版 `task_id` 查询仍兼容**：`/v1/videos/{task_id}` 继续可用
3. **状态字段更新**：`queued`（排队）、`in_progress`（生成中）、`completed`（完成）、`failed`（失败）
4. **视频 URL 字段**：`remixed_from_video_id`（而不是 `video_url`）
5. **分辨率标准化**：系统自动将输入分辨率映射到 480p/720p/1080p 标准档位
6. **轮询间隔建议**：5 秒
7. **宽高必须为 8 的倍数**（视频编码硬性要求）

### `POST /api/videos`

创建视频生成异步任务。立即返回 `task_id` 和 `video_id`，前端需通过 GET 接口轮询状态。

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `prompt` | string | ✅ | 提示词（1-3000 字符） |
| `negative_prompt` | string | | 负向提示词，用于描述需要避免的内容 |
| `model` | string | | 默认 `agnes-video-v2.0` |
| `num_frames` | int | | 帧数，**必须是 `8n+1`** 且 ≤ 441（如 81, 121, 161, 241, 321, 401, 441）。默认 121 |
| `frame_rate` | int | | 帧率 1-60，默认 24 |
| `width` / `height` | int | | 分辨率，宽高必须为 8 的倍数。默认 1152×768 |
| `resolution` | string | | 快捷分辨率选择：`480p`/`720p`/`1080p`/`2K`/`4K`（会自动计算对应宽高） |
| `mode` | string | | `text2video`（默认）\| `image2video` \| `keyframes` |
| `image` | string | | 图生视频模式：单张参考图（URL 或 base64，可选，也可使用 images 数组） |
| `images` | string[] | | 参考图数组（URL/base64）：图生视频支持任意数量，关键帧模式最多2张 |
| `seed` | int | | 随机种子，可选（用于可复现结果） |
| `context` | object | | 创作上下文（可选）：`{ source, container_type, container_id, container_name, asset_type, asset_name }`。带 `container_type`/`container_id` 时生成结果自动归档进资产库，`source`（`independent`/`canvas`/`project`）用于历史来源筛选 |

**帧数与时长对照表（@24fps）：**

| 帧数 | 时长（约） | 适用场景 |
|------|-----------|----------|
| 81 | ~3 秒 | 短视频、预览 |
| 121 | ~5 秒 | **默认推荐** |
| 161 | ~7 秒 | 中等长度 |
| 241 | ~10 秒 | 较长视频 |
| 321 | ~13 秒 | 长视频 |
| 401 | ~17 秒 | 更长视频 |
| 441 | ~18 秒 | 最大帧数 |

**分辨率标准档位：**

| 档位 | 16:9 尺寸 | 9:16 尺寸 | 1:1 尺寸 |
|------|----------|----------|---------|
| 480p | 854×480 | 480×854 | 480×480 |
| 720p | 1280×720 | 720×1280 | 720×720 |
| 1080p | 1920×1080 | 1080×1920 | 1080×1080 |
| 2K | 2560×1440 | 1440×2560 | 1440×1440 |
| 4K | 3840×2160 | 2160×3840 | 2160×2160 |

> **注意**：分辨率会被系统自动标准化到最接近的档位，实际输出尺寸以返回结果中的 `size` 字段为准。

**请求示例（文生视频）：**
```json
{
  "prompt": "一只猫在日落海滩上行走，电影级镜头，温暖金色光线",
  "num_frames": 121,
  "frame_rate": 24,
  "width": 1152,
  "height": 768
}
```

**请求示例（图生视频：单张/多张参考图自动识别）：**
```json
{
  "prompt": "人物慢慢转身看向镜头，自然表情，电影级运镜",
  "mode": "image2video",
  "images": ["https://example.com/image1.png"],
  "num_frames": 121
}
```

> 多张参考图时直接传入 `images` 数组即可，无需额外指定模式，系统自动识别多图参考：
> ```json
> {
>   "prompt": "根据多张参考图生成连贯视频，保持画面风格和内容一致性",
>   "mode": "image2video",
>   "images": [
>     "https://example.com/image1.png",
>     "https://example.com/image2.png",
>     "https://example.com/image3.png"
>   ],
>   "num_frames": 121
> }
> ```

**请求示例（关键帧动画）：**
```json
{
  "prompt": "在关键帧之间生成平滑过渡，保持视觉一致性和自然运镜",
  "mode": "keyframes",
  "images": [
    "https://example.com/keyframe1.png",
    "https://example.com/keyframe2.png"
  ],
  "num_frames": 121
}
```

**响应示例（HTTP 200）：**
```json
{
  "task_id": "task_abc123xyz",
  "video_id": "video_xyz789",
  "status": "queued",
  "prompt": "...",
  "model": "agnes-video-v2.0",
  "num_frames": 121,
  "frame_rate": 24,
  "width": 1152,
  "height": 768,
  "seconds": "5.0",
  "size": "1152x768",
  "mode": "text2video",
  "message": "任务已创建，请轮询 GET /api/videos/{task_id} 获取最新状态"
}
```

### `GET /api/videos/{task_id}`

查询视频生成任务状态。后端优先使用 `video_id` 走推荐端点轮询（响应更快），失败时自动回退到旧版 `task_id` 端点。

**响应字段说明（映射自官方 API）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 任务 ID |
| `video_id` | string | 视频 ID（推荐用于查询） |
| `status` | string | `queued`/`processing`/`success`/`failed` |
| `progress` | int | 进度百分比 0-100 |
| `video_url` | string | 最终视频 URL，仅在 `success` 时可用（对应官方的 `remixed_from_video_id`） |
| `error` | string | 错误信息，失败时返回 |
| `elapsed_sec` | int | 已用时间（秒） |
| `seconds` | string | 视频时长（秒） |
| `size` | string | 实际输出分辨率（标准化后） |

**响应示例（排队中）：**
```json
{
  "task_id": "task_abc123xyz",
  "video_id": "video_xyz789",
  "status": "queued",
  "progress": 0,
  "video_url": null,
  "error": null,
  "elapsed_sec": 2
}
```

**响应示例（生成中）：**
```json
{
  "task_id": "task_abc123xyz",
  "video_id": "video_xyz789",
  "status": "processing",
  "progress": 35,
  "video_url": null,
  "error": null,
  "elapsed_sec": 62
}
```

**响应示例（成功）：**
```json
{
  "task_id": "task_abc123xyz",
  "video_id": "video_xyz789",
  "status": "success",
  "progress": 100,
  "video_url": "https://storage.googleapis.com/agnes-aigc/aigc/videos/2026/06/03/video_xxxxxx.mp4",
  "error": null,
  "elapsed_sec": 186,
  "seconds": "10.0",
  "size": "1280x720"
}
```

**响应示例（失败）：**
```json
{
  "task_id": "task_abc123xyz",
  "video_id": "video_xyz789",
  "status": "failed",
  "progress": 0,
  "video_url": null,
  "error": "Invalid prompt: contains blocked words",
  "elapsed_sec": 3
}
```

**官方状态码映射：**

| 官方状态 | 平台状态 | 说明 |
|----------|---------|------|
| `queued` | `queued` | 排队中 |
| `in_progress` | `processing` | 生成中 |
| `pending`/`running`/`not_start` | `processing` | 兼容旧状态 |
| `completed`/`succeeded`/`success` | `success` | 完成 |
| `failed`/`error` | `failed` | 失败 |

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
| `type` | string | | `all`（默认）\| `image` \| `video` |
| `source` | string | | 来源筛选：`independent`（默认，独立生成）\| `canvas`（画布创作）\| `project`（项目创作）\| `all` |
| `page` | int | | 页码，从 1 开始，默认 1 |
| `page_size` | int | | 每页数量，默认 20 |
| `content_id` | string | | 按内容 ID 精确搜索 |
| `creator` | string | | 按创建者用户名/昵称搜索 |

**响应示例：**
```json
{
  "total": 128,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 1,
      "content_id": "img_abc123",
      "type": "image",
      "prompt": "一只坐在月球上的小猫...",
      "model": "agnes-image-2.1-flash",
      "params": { "size": "1024x1024" },
      "result_url": "https://...",
      "status": "success",
      "task_id": null,
      "created_at": "2025-06-08T10:30:00Z",
      "creator_id": 42,
      "creator_nickname": "用户昵称"
    }
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

### `POST /api/history/batch-delete`

批量删除历史记录（管理员功能）。

**请求体：**
```json
{
  "ids": [1, 2, 3]
}
```

---

## 5. 资产库（创作归档与分享）

> 画布/项目生成会自动归档进资产库（容器：`project` / `canvas_script` / `canvas`），历史默认只显示独立生成。
> 资产可手动存为资产、按创作单元分组管理、分享到广场（复用审核管道）。

### `GET /api/pipeline/assets`

获取资产库列表。

- `scope=market`（默认，无需登录）：返回公开资产（`is_public=true`），供广场资产浏览。
- `scope=my`（需登录）：返回当前用户自己的传统资产（`container_type` 为空），含公开与私有，用于「我的资产」区。

**查询参数**：`asset_type`（character/prop/scene/brand/...，可选）、`search`（可选）、`page`、`page_size`。

**响应**：`{ items: Asset[], total, page, page_size }`

### `GET /api/pipeline/assets/{id}`

获取单个资产详情。

### `POST /api/pipeline/assets/save-from-generation`

将生成记录保存为资产（手动存为资产 / 归档失败补存）。见 `AssetSaveFromGenerationRequest`。

### `GET /api/pipeline/assets/containers`

获取当前用户的**创作单元分组列表**（需登录）。

- `containers`：container 非空的归档资产按 `(container_type, container_id)` 聚合为单元（名称快照、类型徽标、资产数、封面）。
- `standalone_total`：container 为空的传统资产数量（即「我的资产」区）。

**响应**：`{ containers: AssetContainer[], standalone_total: int }`

### `GET /api/pipeline/assets/container/{container_type}/{container_id}`

获取某个创作单元内的全部资产（需登录，按用户隔离），用于单元详情按类型分栏展示。

**响应**：`{ container_type, container_id, container_name, type_label, items: Asset[] }`

### `PATCH /api/pipeline/assets/{id}/share`

切换资产分享状态（需登录 + 归属校验）。设为公开时进入待审核（`pending`），先做敏感词快速筛查，再异步触发 AI 内容审核；未过审不展示到广场。被管理员屏蔽（`moderation_status=rejected`）的资产不可再次公开。

**请求体**：`{ "is_public": true | false }`  
**响应**：`{ success, id, is_public, message }`

### `DELETE /api/pipeline/assets/{id}`

删除资产（需登录 + 归属校验）。若资产是画布/项目自动归档的影子记录（`container_type` 非空），仅删除资产库影子记录，不影响画布/项目本体；若为手动保存的传统资产则一并删除。

**响应**：`{ success, id, message }`

### `POST /api/pipeline/assets/{id}/use`

记录资产被「用于生成」，递增 `use_count`（无需登录，`get_current_user_optional`）。

**响应**：`{ id: int, use_count: int }`

### `GET /api/plaza/creations`

广场「创作」Tab 列表（无需登录）。返回已公开、含可用 `asset_url`、且审核通过（`moderation_status=approved`）的资产。

**查询参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `asset_type` | string | 类型筛选：`all`（默认）/ `character` / `scene` / `material` / `clip` / `final` / `prop` / `brand` |
| `kind` | string | 媒体类型筛选：`all`（默认）/ `image` / `video` |
| `sort` | string | 排序：`latest`（默认，按公开时间倒序）/ `popular`（按点赞数倒序） |
| `page` | int | 页码，默认 1 |
| `page_size` | int | 每页数量，默认 24 |

**响应**：`{ total, page, page_size, items: PlazaCreation[] }`  
`PlazaCreation` 字段：`id, kind, asset_type, name, description, asset_url, container_type, container_name, likes_count, views_count, author_nickname, author_avatar_url, created_at, public_shared_at, is_mine, is_liked`

### `GET /api/plaza/creations/{creation_id}`

创作详情（无需登录）。浏览量 `views_count` 自增 1。响应为单个 `PlazaCreation`。

### `POST /api/plaza/creations/{creation_id}/like`

点赞创作（需登录）。幂等：唯一约束去重后 `likes_count + 1`。响应 `{ success, id, likes_count }`。

### `DELETE /api/plaza/creations/{creation_id}/like`

取消点赞（需登录）。`likes_count` 下限 0。响应 `{ success, id, likes_count }`。

### `GET /api/plaza/creations/likes/status`

批量查询当前用户对一组创作的点赞状态（需登录）。

**查询参数**：`ids`（逗号分隔的 creation_id 列表，如 `12,34,56`）。  
**响应**：`{ liked_ids: number[] }`

---

## 6. 分镜脚本生成

### `POST /api/storyboard`

为无限画布 script 节点生成分镜脚本 + 全剧资产清单（无状态，不存储，结果由前端写回画布节点）。

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `story` | string | ✅ | 剧情概述 |
| `characters` | object[] | | 已有角色设定 `[{ name, description, ref_image_url }]`（画布上游节点 + 资产卡回传） |
| `scenes` | object[] | | 已有场景设定（反向通道，分镜沿用已有设定） |
| `shot_count_min` / `shot_count_max` | int | | 期望镜头数范围，默认 6-12，上限 30 |
| `style` | string | | 画面风格 |

**响应 `data`：**

```json
{
  "shots": [{ "no": 1, "shot_size": "中景", "camera": "缓推", "characters": ["林小雨"], "location": "咖啡店", "description": "...", "dialogue": "..." }],
  "assets": { "characters": [{ "name": "林小雨", "description": "外貌/服饰/气质描述" }], "scenes": [{ "name": "咖啡店", "description": "环境/时间/氛围描述" }] }
}
```

> LLM 输出兼容旧的纯分镜数组格式（此时 `assets` 为空）。镜头的 `characters`/`location` 与资产清单按名关联，前端据此预填资产卡、并按镜头命中注入生成提示词与参考图。

---

## 7. 错误码说明

| HTTP 状态 | 含义 |
|----------|------|
| 200 | 成功 |
| 400 | 参数校验失败（如 num_frames 不符合 8n+1 规则、prompt 超长） |
| 401 | 未登录或 Token 无效 |
| 403 | 权限不足（如审核拒绝的内容无法再次公开） |
| 404 | 资源不存在（如查询不存在的 task_id） |
| 413 | 上传的图片超过大小限制（默认 10 MB） |
| 500 | 服务端内部错误 |
| 502 | Agnes AI 官方 API 返回错误 |
| 503 | Agnes AI 服务繁忙，请稍后重试 |
| 504 | 请求超时 |

---

## 8. 后端到 Agnes AI 的请求流

```
前端 axios
    ↓
Vite 代理（开发模式）或 Nginx（生产）
    ↓
FastAPI backend (8000)
    ├→ 校验用户登录态（JWT）
    ├→ 校验积分余额
    ├→ 获取当前激活的 Provider 配置（base_url + api_key）
    ├→ 参数校验与标准化（帧数、宽高对齐到 8 的倍数）
    └→ httpx → Agnes AI (apihub.agnes-ai.com)
            │
            ├→ 图片：POST /v1/images/generations（同步等待）
            │
            └→ 视频：POST /v1/videos（异步，返回 task_id + video_id）
                    ↓
            ┌── 后台轮询（推荐 GET /agnesapi?video_id=xxx，间隔 5s）
            ↓
    解析响应，写入数据库，扣减积分
    ↓
前端得到结果（url, task_id, video_url 等）
```

---

## 9. 视频生成 Prompt 最佳实践

### 文生视频推荐结构
`[主体] + [动作] + [场景] + [镜头运动] + [光照] + [风格]`

示例：
```
A young astronaut walking across a red desert planet, dust blowing in the wind, slow cinematic tracking shot, dramatic sunset lighting, realistic sci-fi style
```

### 图生视频建议
描述需要运动的部分，同时说明需要保持稳定的元素：
```
Animate the character with subtle breathing motion, hair moving gently in the wind, background lights flickering softly, while keeping the face and outfit consistent
```

### 关键帧动画建议
清晰描述关键帧之间的过渡关系：
```
Create a smooth transition from the first keyframe to the second keyframe, maintaining character identity, consistent camera angle, and natural motion between scenes
```

---

## 10. 图片生成 Prompt 最佳实践

### 推荐结构
`[主体] + [场景 / 环境] + [风格] + [光照] + [构图] + [质量要求]`

示例：
```
A luminous floating city above a misty canyon at sunrise, cinematic realism, wide-angle composition, rich architectural details, soft golden light, high visual density
```

### 图生图建议
同时说明"要改变什么"和"要保留什么"：
```
Transform the scene into a rain-soaked cyberpunk night with neon reflections while preserving the original composition and main subject layout
```
