# Agnes AI Platform · REST API 文档

后端端口：`http://localhost:8000`  
Swagger UI（交互式文档）：`http://localhost:8000/docs`  
健康检查：`http://localhost:8000/health`

> 说明：所有接口（除 `/health`、`/docs` 外）均以 `/api` 为前缀。返回 JSON 格式响应。
>
> **统一响应结构**：业务成功响应统一为 envelope `{"status": "success", "message": "", "data": ...}`（`data` 为原业务载荷）；业务失败一律返回 `HTTPException` 标准 `{"detail": "错误说明"}` 配合 4xx/5xx 状态码。前端 axios 客户端已对 envelope 透明解包。文件流 / SSE / 图片代理等非 JSON 响应不包装。

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
- 视频转视频（video2video）：传入 `reference_videos` 参考视频，仅支持该模式的模型可用（按模型 `capabilities` 声明协商）
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
| `mode` | string | | `text2video`（默认）\| `image2video` \| `keyframes` \| `video2video` |
| `image` | string | | 图生视频模式：单张参考图（URL 或 base64，可选，也可使用 images 数组） |
| `images` | string[] | | 参考图数组（URL/base64）：图生视频支持任意数量，关键帧模式最多2张 |
| `reference_videos` | string[] | | 视频转视频模式参考视频 URL 数组，1-5 个；仅 `video2video` 模式使用，需所选模型能力表声明 `video2video` |
| `reference_audios` | string[] | | 参考音频 URL 数组（预留，可选） |
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

**请求示例（视频转视频，需模型声明 `video2video` 能力）：**
```json
{
  "prompt": "保持人物动作与镜头运动，将画面风格替换为赛博朋克夜景",
  "mode": "video2video",
  "reference_videos": ["https://example.com/source.mp4"],
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

获取生成历史（任务视图）。支持按类型 / 来源 / 状态筛选 + 分页。

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | | `all`（默认）\| `image` \| `video` |
| `source` | string | | 来源筛选：`all`（默认，任务视图统一展示）\| `independent`（独立生成）\| `canvas`（画布创作）\| `project`（项目创作） |
| `status` | string | | 状态筛选（任务视图）：`success` \| `failed` \| `pending`（进行中） |
| `task_id` | string | | 按 task_id 精确匹配（积分明细跳转定位用，忽略 source） |
| `page` | int | | 页码，从 1 开始，默认 1 |
| `page_size` | int | | 每页数量，默认 20 |

**响应示例：**
```json
{
  "total": 128,
  "page": 1,
  "page_size": 20,
  "total_image_count": 90,
  "total_video_count": 38,
  "items": [
    {
      "id": 1,
      "type": "image",
      "prompt": "一只坐在月球上的小猫...",
      "model": "agnes-image-2.1-flash",
      "params": { "size": "1024x1024" },
      "result_url": "https://...",
      "status": "success",
      "error_category": null,
      "error_message": null,
      "task_id": "task_xxx",
      "credits_consumed": 10,
      "created_at": "2025-06-08T10:30:00Z",
      "asset_id": 953
    }
  ]
}
```

> 历史页定位为**任务视图**：任务执行状态、失败归因（`error_category`/`error_message`）、积分消耗；成果媒体的浏览/下载/批量/分享在资产库（`/api/assets`）。

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

### 统一资产层（`/api/assets`，登录级）

> 全平台媒体唯一身份 `assets.id`；画布节点/剪辑片段只持有 `asset_id` 引用。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/assets` | 画布/上传素材建统一资产行。请求体 `{ url, media_type, name?, work_id? }`；`/uploads/` 地址直推导 storage_key，远程 http(s) URL 下载转存 |
| GET | `/api/assets` | 本人资产列表。查询参数：`media_type` / `source` / `work_id` / `type`（资产分类）/ `keyword`（匹配名称/描述/视觉描述）/ `page` / `page_size`，按 `updated_at` 倒序 |
| GET | `/api/assets/{asset_id}` | 本人资产详情。非本人或不存在返回 404 |
| PATCH | `/api/assets/{asset_id}` | 编辑资产元数据。请求体 `{ name?, type?, description?, visual_description? }`（可选字段，仅更新提交项）；`type` 限 `character/prop/scene/brand/material/clip/final`，空 `name` 或非法 `type` 返回 400，非本人返回 404；不触碰公开/审核状态。响应为更新后的完整资产行 |
| POST | `/api/assets/backfill` | 存量补课（仅管理员/审核员）：资产行字段回填 + 历史成功生成批量入库，幂等，`?limit=` 控制单次上限 |
| PATCH | `/api/assets/batch-share` | 批量设置分享状态。请求体 `{ ids, is_public }`；公开复用审核管道（进入 pending、敏感词预检、异步 AI 审核），被屏蔽（rejected）资产自动跳过。响应 `{ updated_count, failed_ids }` |
| POST | `/api/assets/batch-delete` | 批量删除资产（按用户隔离；归档影子记录仅删资产库记录，不影响画布/项目本体）。请求体 `{ ids }`，响应 `{ deleted_count, failed_ids }` |
| GET | `/api/assets/batch-download` | 批量下载打包 zip。`?ids=1,2,3`（单次 ≤100）；`/uploads/` 本地文件直读磁盘、远程地址服务端抓取，失败文件跳过 |

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

---

## 11. 预设（统一预设广场）

> Deprecated：独立 `camera_presets` 摄像机预设表已删除（运镜统一走 `prompt_presets` camera 类型，参数拼接仍由 `camera_prompt.build_camera_prompt_suffix` 承担）；`style_presets` 与 `style_elements` 两套风格体系停用。风格/运镜库唯一入口为 `prompt_presets`。

五类预设（style / effect / camera / prompt / script）统一存于 `prompt_presets` 表，pipeline 类型不进广场。广场卡片支持封面图、收藏、最近使用与官方标记；投稿公开沿用审核流（submit + admin_review）。

### GET /api/presets — 预设列表（需登录）

| 参数 | 说明 |
| --- | --- |
| `tab` | `plaza`（默认，自己的 + 公开审核通过的）/ `favorites`（我的收藏）/ `recent`（最近使用）/ `mine`（我的全部预设，含 pipeline） |
| `type` | 预设类型，逗号分隔多类型，如 `style,effect` |
| `category` | 分类筛选 |
| `q` | 搜索名称 / 描述 / 标签 / 作者昵称 |
| `sort` | `new`（默认）/ `hot`（官方优先 + 使用量）/ `name` |
| `page` / `page_size` | 分页，默认 1 / 24 |

响应：`{ items: [...], total }`，item 含 `cover_image`、`prompt_config`、`is_official`、`author_nickname`、`is_favorite`。

### POST /api/presets/{id}/favorite — 收藏 / 取消收藏

返回 `{ is_favorite: boolean }`（toggle 后状态）。

### POST /api/presets/{id}/use — 记录使用

应用预设时调用：upsert 最近使用记录 + `usage_count` +1。返回 `{ message }`。

### POST /api/uploads/image — 上传图片（预设封面等）

multipart 上传，支持 jpeg/png/webp，≤5MB，存 `uploads/preset-covers/`。返回 `{ url }`。

### 数据模型变更

- `prompt_presets` 新增：`cover_image`（封面 URL）、`prompt_config`（JSON：`{prefix, suffix, negative_prompt}`，style/effect 使用）、`is_official`（官方卡标记，管理员创建自动置 1）
- 新表：`preset_favorites`（收藏，user_id+preset_id 唯一）、`preset_recent_uses`（最近使用，含 `last_used_at` / `use_count`）
- 官方预设与封面随应用启动自动灌入（`app/seed/` 包，lifespan 幂等 ensure 链路），无需手动脚本

### POST /api/presets/{id}/generate-cover — AI 生成预设封面（管理员）

按预设类型分流（已生成则覆盖）：

- **effect / camera 类型 → 动态封面**：视频 API（agnes-video-2.5-flash，4s、3:4）以「运动主体 + 特效/运镜提示词片段」生成示例片段，轮询至完成（约 1-3 分钟）后写回 `cover_video`，响应 `{cover_video}`；
- **其他类型 → 静态封面**：生图 API（agnes-image-2.1-flash，512x512）写回 `cover_image`，响应 `{cover_image}`。

仅管理员可用；用户自建卡通过上传或「从生成记录选图」设置封面。

## 12. 画布 Agent LLM 透传

### POST /api/chat/completions — LLM 透传（画布 Agent 前端内核专用，SSE 流式）

代理 Agnes Chat API 的流式调用。工具循环由前端驱动（画布 Agent 内核 `lib/agent/kernel.ts`），本端点**不落会话库**；API key 仅存后端 `.env`，前端不接触。请求为 OpenAI Chat Completions 形状的子集：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `messages` | array | 是 | OpenAI 格式消息数组（含 tool 结果回填） |
| `tools` | array | 否 | OpenAI function calling 工具定义 |
| `tool_choice` | any | 否 | 工具选择策略（`auto` 或具体函数） |
| `temperature` | number | 否 | 0-2 |
| `model` | string | 否 | 模型提示：命中聊天模型注册表才采用（分镜管线/对话模型选择）；未命中（含内核占位 id 如 `agnes-chat`）走后端默认解析链（用户偏好 > 管理员配置 > 注册表第一个） |

响应：`text/event-stream`，原样转发上游 SSE 行（`data: {...}` chunk 与 `data: [DONE]` 收尾；上游提前断流时补发 `[DONE]`，连接异常下发 `{"error": {...}}` 事件后收尾）。**本端点为统一 ok() envelope 的特例**（流式响应不包装）；上游非 200 时返回 HTTP 502。前端由 openai-completions 适配负责 SSE 解析与 tool_calls 增量聚合。

## 13. MCP 服务器（Agent 外部工具桥）

管理员配置 MCP 服务器（stdio / streamable HTTP 双传输），Agent 经 BFF 调用其工具。工具在前端内核以 `mcp__{serverId}__{tool}` 命名注入；env/headers 的值只存服务端，任何响应不回传（只回键名）。

### 管理接口（需管理员）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/mcp/servers` | 服务器列表（脱敏：env/headers 只回 `env_keys`/`header_keys` 键名） |
| POST | `/api/mcp/servers` | 创建。stdio 传 `command`+`args`+`env`；http 传 `url`+`headers`；`transport` 必填 `stdio\|http` |
| PUT | `/api/mcp/servers/{id}` | 更新。env/headers **缺省=保留原值，传 `{}`=清空**；切换传输类型时两侧密钥重置 |
| DELETE | `/api/mcp/servers/{id}` | 删除（同时回收后端连接） |
| POST | `/api/mcp/servers/{id}/test` | 连接测试，返回该服务器工具清单（name/description/input_schema） |

### 工具调用（需登录）

### POST /api/mcp/call — Agent 调用 MCP 工具

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `server_id` | int | 是 | 服务器 id（必须存在且 enabled） |
| `tool` | string | 是 | 工具名 |
| `arguments` | object | 否 | 工具入参 |

响应 `data`: `{ "text": "内容块拼接文本", "is_error": false }`。连接/超时/工具错误统一 502（detail 带原因）；服务器不存在或停用 404。

### 市场接口（需管理员）——发现与一键安装

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/mcp/market/sources` | 市场源列表（官方内置目录不在此表） |
| POST | `/api/mcp/market/sources` | 添加自建源（`{ name, url }`，URL 指向 manifest JSON，仅 http(s)） |
| DELETE | `/api/mcp/market/sources/{id}` | 删除源（其市场项一并移除，已安装服务器不受影响） |
| POST | `/api/mcp/market/sources/{id}/refresh` | 拉取 manifest 并整源替换市场项（超时 15s/≤2MB/≤100 条） |
| GET | `/api/mcp/market/items?q=` | 市场项合并列表（官方 + 远程，带 `installed` 标记；官方目录首次访问自动入库） |
| POST | `/api/mcp/market/install` | 从市场项安装：`{ slug, name?, command?, args?, url?, env?, headers? }`（预填可覆盖，密钥按声明的 key 传入合成；成功后 `market_slug` 写入安装溯源） |

manifest 格式：`{ "name": "...", "items": [{ "slug", "name", "description", "category", "transport": "stdio\|http", "command", "args", "url", "env_fields": [{key, description, required}], "headers_fields": [...], "tools_preview": [...] }] }`。

### 用户记忆库（需登录）

创作偏好存储在用户自己的 MCP 记忆图谱里（「创作偏好」实体，observations 格式"类别：内容"），per_user 隔离。写入由 Agent 按系统提示记忆守则调用 memory 工具完成，本组接口只做读取与管理：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/mcp/memory/summary` | 当前用户偏好摘要 `{ available, preferences }`（未安装/未启用官方记忆服务器 → available:false） |
| DELETE | `/api/mcp/memory/preference` | 删除单条偏好（body `{ observation }`） |
| DELETE | `/api/mcp/memory/preferences` | 清空偏好实体（保留图谱其他记忆） |

### 数据表

- `mcp_servers`：name（唯一）/ transport('stdio'\|'http') / command / args_json / env_json / url / headers_json / enabled / market_slug（市场安装溯源）/ created_at / updated_at。stdio 的 env_json 与 http 的 headers_json 为敏感值存储，仅服务端持有。
- `mcp_market_sources`：name / url / enabled / last_fetched_at / item_count（管理员自建市场源）。
- `mcp_market_items`：source_type('official'\|'remote') / source_id / slug（唯一）/ category / payload（市场项完整定义 JSON）。

## 14. 日志查询与前端错误上报

后端日志文件在 `backend/logs/`：`agnes_platform.log`（全量，10MB 轮转 ×5 备份 `.1`~`.5`）、`errors.jsonl`（WARNING 及以上 JSON 行）、`frontend.jsonl`（浏览器端错误上报，同样 10MB 轮转 ×5）。管理界面在 `/admin/logs`。

### 查询与管理（需 `log:view` 权限，admin 天然持有）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/logs` | 查询日志（倒序最新在前）。参数：`file`（白名单：`agnes_platform.log[.1~.5]` / `errors.jsonl` / `frontend.jsonl`，默认 `errors.jsonl`）、`level`（INFO/WARNING/ERROR/CRITICAL）、`request_id`、`keyword`（匹配 message 与 exception）、`module`、`since`（起始 ISO 时间）、`before`（翻页游标：只返回早于该时间的条目，取上一页最后一条 `timestamp`）、`limit`（1-200，默认 50）。响应 `data`: `{ logs, total, file }`；jsonl 条目为结构化字段（timestamp/level/request_id/module/func/lineno/message/exception/context），文本文件条目为 `{ raw, timestamp, level }` |
| GET | `/api/logs/errors` | 最近错误日志（仅 ERROR/CRITICAL），参数 `limit`（默认 20）、`keyword` |
| GET | `/api/logs/stats` | 日志文件统计：`{ exists, files: { 文件名: { size_bytes, size_mb, line_count, modified } } }` |
| GET | `/api/logs/download` | 下载日志文件，参数 `file`（白名单内，含轮转备份）；文件不存在 404 |
| DELETE | `/api/logs` | 清空 / 删除：`file` 为主文件时截断当前文件并删除 `.1`~`.5` 轮转备份；`file` 为备份时单独删除。响应 `data`: `{ cleared, removed }` |

`file` 白名单外取值（含目录穿越形态）一律 400。

### 前端错误上报（公开，无需登录）

### POST /api/logs/frontend

浏览器端错误批量上报。登录态请求会由服务端解析 `user_id` 记入 `context`（客户端传的 `user_id` 被忽略）；限频每 IP 每分钟 60 条，超出整批丢弃（恒返回 `received: 0`）；除单批超过 50 条返回 400 外恒返回 200，客户端不重试。

请求体：`{ "events": [{ "message", "stack?", "level?"（error/warning，缺省 error）, "url?", "timestamp?" }] }`，`message` 截断 2048 字符、`stack` 截断 8192 字符（服务端兜底，前端先行截断）。

响应 `data`: `{ "received": 实际落盘条数 }`。落盘条目与 errors.jsonl 字段对齐，`module` 固定 `frontend`，`url`/`ip`/`ua`/`user_id`/`client_ts` 在 `context` 内。

## 15. 首启初始化

数据库建表、积分规则、内置角色/敏感词/系统配置、流水线内置模板与官方预设卡（含随仓库分发的封面静态资源 `/seed-assets/*`）均由后端 lifespan 启动时自动幂等灌入，无手动初始化脚本。默认超管仅当 `ADMIN_USERNAME` + `ADMIN_PASSWORD` 同时显式设置时种子（自动化部署）；否则不种任何账号，由首启向导引导免登录创建。

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/setup/bootstrap` | 免登录 | 返回 `{ admin_exists }`。实例无管理员时前端将所有路由强制引导至 `/setup` 向导创建管理员 |
| POST | `/api/setup/bootstrap` | 免登录（仅实例管理员数为 0 时可用，否则 409） | 创建首个管理员，body `{ username, password }`（用户名 3~32 位字母/数字/下划线/中文，密码 6~64；校验失败按全局惯例返回 400）。用户名冲突 409。成功签发 JWT（`TokenResponse`），前端免登录进入向导下一步。此窗口同时是管理员被全删后的恢复路径 |
| GET | `/api/setup/status` | 登录用户 | 返回 `{ provider_pending, setup_completed }`。`provider_pending` 仅在当前用户是管理员且实例未配置任何 Provider 时为 true（非管理员恒 false，不泄露配置状态）；`setup_completed` 为实例级标记（`system_config` 的 `setup.completed`） |
| POST | `/api/setup/complete` | 仅管理员（401/403/200 三态） | 写入实例级完成标记，幂等。前端向导走完（Provider 步可跳过）后调用，之后不再拦截 |

前端拦截条件：未登录且 `admin_exists=false` → 强制 `/setup` 创建管理员；登录态 `provider_pending && !setup_completed` → 强制 `/setup` 配置 Provider。向导 Provider 步提交后自动调用 `POST /api/providers/{id}/sync-models` 拉取模型列表（失败可重试/跳过）；跳过或失败时完成页警示且生成页显示空态引导。

## 16. 画布工作区云端落库（画布持久化 + 版本历史）

无限画布工作区数据云端落库：登录态画布经 400ms 防抖 + 串行单飞队列保存到 `canvas_workspaces`（每工作区一行，`data` JSON 存 panels/connections/groups/viewport/styleConfig，前端 uid 直作主键），`revision` 乐观锁冲突返回 409（前端自动把云端版本落地为「冲突副本」工作区后按新 revision 续推）。版本快照存 `canvas_snapshots`（`kind`: `auto` 保存节流自动 / `manual` 手动命名 / `pre_danger` 危险操作前；auto 每 5 分钟且内容有变化才拍、滚动保留 20 份，manual/pre_danger 不占额度）。拖入/粘贴的本地图素材经 `POST /api/uploads/canvas` 上云，节点直接引用远程 URL。未登录（anon）画布仍纯浏览器本地存储。前端入口：底栏工具栏「历史版本」弹窗（存一版/还原/删除），顶栏标题旁同步状态指示器，Ctrl+S 立即强制保存。

### 工作区 CRUD（全部登录态，非本人 403）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/canvas/workspaces` | 当前用户工作区列表（不含 data，按 updated_at 倒序；支持 `work_id` 筛选作品下集画布） |
| POST | `/api/canvas/workspaces` | 创建 `{ id?, name, work_id?, data }`；id 可透传前端 uid（迁移/懒创建用），同 id 重复创建幂等返回已有，id 被其他用户占用 409；`work_id` 挂靠作品（非本人作品 403） |
| GET | `/api/canvas/workspaces/{id}` | 全量 `{ id, name, revision, data, created_at, updated_at }` |
| PATCH | `/api/canvas/workspaces/{id}` | 挂靠/解绑作品 `{ work_id }`（None=解绑为自由画布；目标作品非本人 403） |
| PUT | `/api/canvas/workspaces/{id}` | 保存 `{ data, base_revision, name? }` → `{ revision }`；`base_revision` 不符返回 409 `{ detail: { current_revision } }`。PUT 内嵌自动快照节流（见上） |
| DELETE | `/api/canvas/workspaces/{id}` | 删除工作区并连带删除其全部快照 |

### 快照

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/canvas/workspaces/{id}/snapshots` | 创建快照 `{ kind: 'manual'\|'pre_danger', name? }`（`auto` 仅由保存链路内嵌生成，传 auto 返回 400）→ 快照摘要（含当时 revision） |
| GET | `/api/canvas/workspaces/{id}/snapshots` | 快照列表（不含 data，created_at 倒序） |
| GET | `/api/canvas/workspaces/{id}/snapshots/{sid}` | 快照全量（含 data；前端还原=先 POST 一份 pre_danger 快照再拉 data 走 PUT 写回） |
| DELETE | `/api/canvas/workspaces/{id}/snapshots/{sid}` | 删除单份快照 |

### 画布素材上传

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/uploads/canvas` | 上传画布素材（拖入/粘贴的本地图片/视频），复用通用上传服务（图片+视频白名单、单文件 100MB），存 `uploads/canvas/assets/`，返回 `{ url }`（`/uploads/canvas/assets/<filename>`） |

### 偏好扩展

`/api/preferences` 的 `ui` 组新增画布全局小设置键：`canvas_active_workspace_id`（云端激活工作区 id）、`canvas_background_mode`、`canvas_show_image_info`（登录态经 `/api/preferences` 读写；anon 仍走浏览器本地）。

## 17. 画布远程操作（外部宿主增量写入）

无限画布操作服务端化：对话页 Agent（及将来的 MCP/CLI 宿主）经 ops 端点对 `canvas_workspaces.data` 做结构化增量写入，画布页以轻轮询感知远端变更。领域语义在 `app/services/canvas_ops.py`（连线类型规则与前端 `validateConnectionTypes` 对齐，pytest 锁死）。

### 端点（登录态，非本人 403）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/canvas/workspaces/{id}/ops` | 批量应用操作 `{ ops: [...] }`（1-50 条），整批一个 revision；逐条返回 `results`（`{ index, op, ok, panel_id?/connection_id?, error? }`）+ `new_panel_ids` + `revision`。全部失败返回 400（detail 含逐条 results），部分失败整批落库。op 仅 `add_panel` / `add_connection`（v1 只读+增量，不做改删） |
| GET | `/api/canvas/workspaces/{id}/revision` | `{ revision, updated_at }`，画布页轻轮询用（不拉 data） |

### op 语义

- `add_panel`：`type`（text/image/video/audio/config/tts/subtitle/compose/script，缺省 text）、`name`、`content`（dict）、`x/y/width/height`（缺省 120+(n%8)*40 排布、240×180，对齐画布 Agent 同款默认）；服务端生成 id（uuid hex）/`zIndex`（max+1）/时间戳，并写入 `workspace_id`。
- `add_connection`：`source_panel_id`/`target_panel_id` 支持**节点 id 或节点名称**（服务端全量解析，同批新建节点可按名引用）；连线类型规则：script 只出向 config、tts/subtitle 只受 text、compose 只受 video/tts/subtitle，违规该条返回 ok=false。

### 前端联动

- 对话页工具组：`canvas_list_workspaces` / `canvas_get_overview` / `canvas_add_panels` / `canvas_connect`（目标工作区缺省取偏好 `canvas_active_workspace_id`）；`generate_image` / `generate_video` 新增 `place_on_canvas` + `canvas_workspace_id` 参数——媒体轮询成功后自动调 ops 建媒体节点（content 带 prompt+URL，status=success），结果以步骤行回显。
- 画布页：每 10s（仅页面可见、云通道时）拉激活工作区 revision；有变化且本地保存队列空闲 → 自动拉取远端 data 合入（复用版本还原的 `applyWorkspaceData` 链路）+ 轻提示；队列忙碌 → 顶栏「云端有更新」指示器等待手动同步。空闲即本地无未保存内容，合入零丢失，无需快照兜底。

---

## 18. 模型能力合同与提示词优化

### 模型能力合同（gen_params）

模型生成能力（参考图上限/水印/尺寸规则等）由后端合同层统一解析，三级优先：`model_definitions.gen_params` 显式配置（逐键覆盖）> 按模型名自动画像 > 默认兜底。解析结果随模型列表（`GET /api/config` 的 `models[].gen_params`）下发，前端统一经 models store 的 `getModelGenParams(modelId)` 读取。

- 现有画像：`seedream*` → `watermark_param_off=true, size_rule="seedream"`；`agnes-image-2*` → `max_ref_images=6`（上游 400 "too many input images" 实测约束）。
- 新增画像/调整上限在 `backend/app/services/capability_service.py`，不要在生成代码里写模型特例。

### `POST /api/prompts/optimize`

AI 提示词优化（登录用户），返回结构化正负提示词。

**请求：**
```json
{
  "prompt": "少女在花园",
  "mode": "refine",
  "target": "image",
  "context": { "model_id": "agnes-image-2.1-flash", "reference_asset_names": ["人物.png"] }
}
```

- `mode`：`expand`（扩展想法）/ `refine`（精修提示词）/ `style`（强化视觉风格）/ `model-adapt`（适配当前模型方言）/ `reference`（结合参考素材）
- `target`：`image` / `video`
- `context` 可选：`model_id` 供 model-adapt 注入方言规则；`reference_asset_names` 供 reference 模式注入参考素材名

**响应 `data`：**
```json
{
  "positive": "可直接用于生成的正向提示词",
  "negative": "需要规避的内容（可为空串）",
  "changes": ["关键变化"],
  "assumptions": ["对模糊需求的假设"],
  "variants": [{ "label": "电影感", "prompt": "备选版本提示词" }]
}
```

- `variants` 最多 2 个；LLM 走系统默认对话模型，解析失败自动重试一次，仍失败返回 502；未登录 401，空提示词 / 非法枚举 400。

### 批量创作表节点（画布）

画布 `table` 类型节点：N 行 × M 参考图列的矩阵批量生图。节点 content 含 `refSlots`（列数 = min(6, 模型合同 `max_ref_images`)）、`rows`（每行参考图槽位 + 行提示词 + 启用开关 + 状态）、`preset`（批量换装/创意生图/自定义预设模板）、`globalPrompt`（与行提示词追加拼接）。提交时逐行独立走图片生成任务，结果节点连线回表格节点；单行失败可单独重试，不影响其他行。前端纯函数层 `frontend/src/lib/canvas-batch-table.ts`。

---

## 19. 生成错误类目 + 上游调用记账 + 模型倍率定价

### 生成错误类目（error_taxonomy）

上游调用失败统一归类为 13 类类目之一（`backend/app/services/error_taxonomy.py` 唯一出处），每类绑定「能否手动重试」语义：

| 类目 | 说明 | canRetry |
|---|---|---|
| network_transient / upstream_server / timeout / rate_limited / result_fetch_failed / unknown | 临时性失败 | true |
| auth_failed / model_missing / invalid_params / moderation_rejected / upstream_quota / local_storage_failed | 明确判死 | false |
| submission_uncertain | 提交结果不确定（回执丢失/查询 5xx/超时），禁止原地重试以防重复扣费 | false |

**下发与透出**：
- `GET /api/config` 新增 `error_categories: [{code, can_retry}]`（语义表；用户文案由前端 i18n `errors.category_<code>` 渲染）。
- 图片/视频任务状态端点失败时返回 `error_category` + `message`（error_message）；`GET /api/images/tasks/{id}`、`GET /api/videos/tasks/{id}` 均适用。
- 任务提交失败响应 body 携带 `category` 字段（HTTP 502）。
- 失败归因落库：`generations` 表新增 `error_category`（VARCHAR 40 索引）与 `error_message`（TEXT）；历史记录接口随 `to_dict` 透出。存量库需手动 ALTER（见模型文件注释）。
- 前端重试闸门：画布节点重试与批量创作表行级重试在 `can_retry=false` 类目上拦截并提示；无类目行为不变。

### 上游调用记账（管理员）

新表 `api_call_logs`：每次上游调用一行（provider/model/call_type/endpoint/status/error_category/latency_ms/tokens/created_at），由 `agnes_client` 与 aibridge 客户端出口 best-effort 写入（写库失败不影响生成主流程）。表由启动时 `create_all` 自动创建。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/api-calls` | 调用日志列表（分页筛选：`page`/`page_size`/`provider_id`/`model`/`call_type`/`status`/`error_category`/`since`/`before`） |
| GET | `/api/admin/api-calls/summary` | 聚合摘要（`days` 1-30，默认 7）：total/failed/failure_rate/daily（按日×状态）/by_category/by_provider/by_model（渠道与模型均为 `{success, failed}` 计数） |

均挂管理员鉴权（401/403/200 三态测试锁死）。管理界面：`/admin/logs` 第三 Tab「上游调用」。

### 模型倍率定价（动态定价）

- `model_definitions` 新增 `cost_multiplier`（FLOAT，默认 1.0；存量库手动 ALTER，见模型文件注释）。
- 计价：**实扣积分 = credit_rules 基准价 × 所选模型 cost_multiplier**（图片按张、视频按秒的既有规则不变；模型不存在按 1.0；倍率下限 0.1）。
- `GET /api/credits/estimate` 与实际扣费自动一致（同一计价函数）；先扣后退结构不变，退款按实扣原额退。
- 管理端「配置管理 → 模型编辑」新增「积分倍率」输入，保存立即生效。
- 批量设置：`PUT /api/models/batch-cost-multiplier`（body `{model_ids, cost_multiplier}`，倍率 0.1~100），管理端模型列表勾选多行后「批量设倍率」一次生效，立即生效。

## 20. 作品容器（轻容器）+ 画布轻成片

### 作品 works（用户自助，登录态；非本人 403 / 不存在 404）

新表 `works`（一部剧一条作品，聚合集画布/剪辑工程/实体库；存量库 create_all 自动建）。`canvas_workspaces` 新增 `work_id` 列（存量库手动 ALTER：`ALTER TABLE canvas_workspaces ADD COLUMN work_id INTEGER`；删除作品时名下画布自动解绑为自由画布）。前端入口：侧边栏「作品」→ `/works` 列表 → `/works/{id}` 详情（集画布管理，「进入画布」经 `/canvas?workspace={id}` 定位）。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/works` | 本人作品列表（updated_at 倒序） |
| POST | `/api/works` | 创建 `{ title, description?, cover_url? }` |
| GET/PATCH/DELETE | `/api/works/{id}` | 详情 / 更新 / 删除（删除解绑画布） |

### 画布媒体域与轻成片（/api/canvas）

媒体域公共层抽至 `services/media/`（tts_provider 音色库与 Edge TTS / subtitle_format SRT+ASS / bgm_library 曲库），画布与项目制共用；`media_compose` 新增 `concat_with_xfade`（xfade 转场链公共实现）。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/canvas/voices` | TTS 音色库（内置 8 音色，支持 Edge 音色名透传） |
| GET | `/api/canvas/bgms` | BGM 曲库（内置 + 用户自定义，含 available 与情绪分类） |
| POST | `/api/canvas/tts` | `{ text, voice?, speed? }` → `{ audio_url, duration_ms }`（不变） |
| POST | `/api/canvas/subtitle` | `{ text, max_chars?, prompt? }` → `{ srt, segments, total_duration }`；`prompt` 为拆分补充要求（拼进 LLM 提示词） |
| POST | `/api/canvas/compose` | `{ video_urls, audios?, subtitles?, with_subtitle?, bgm_id?, aspect_ratio?, transition? }` → `{ video_url, duration_ms }`；`audios` 多段配音按视频段顺序拼接成单轨（旧 `audio_url` 单段入口兼容保留）；`transition` none/fade/dissolve/wipe/slide，非 none 且多段走 xfade 重编码链 |
