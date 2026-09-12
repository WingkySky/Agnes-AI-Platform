# Agnes AI 官方 API 文档

本目录保存 Agnes AI 官方开发者文档的本地副本，便于开发时参考。

## 文档列表

| 文档 | 模型 | 更新说明 |
|------|------|----------|
| [agnes-video-v2.0.md](agnes-video-v2.0.md) | Agnes Video V2.0 | 2026-06 更新：新增 video_id 轮询、多图视频、关键帧动画、分辨率标准化等 |
| [agnes-image-2.1-flash.md](agnes-image-2.1-flash.md) | Agnes Image 2.1 Flash | 最新图像模型文档，高信息密度优化、extra_body 参数规范 |

## 主要更新点（视频模型）

相比旧版文档，Agnes Video V2.0 有以下重要变更：

1. **双 ID 机制**：创建任务同时返回 `task_id` 和 `video_id`，推荐使用 `video_id` 查询
2. **新查询端点**：`GET /agnesapi?video_id=xxx`（推荐，响应更快）
3. **状态字段更新**：`queued` → `in_progress` → `completed` → `failed`
4. **视频 URL 字段**：使用 `remixed_from_video_id` 字段
5. **多图/关键帧支持**：通过 `extra_body.image` 数组和 `extra_body.mode: "keyframes"`
6. **分辨率标准化**：系统自动映射到 480p/720p/1080p 标准档位
7. **轮询间隔**：建议 5 秒
8. **参数更新**：默认分辨率 1152×768，支持 negative_prompt、seed、num_inference_steps
9. **宽高要求**：必须为 8 的倍数（视频编码硬性要求）
10. **最大帧数**：441 帧（@24fps 约 18 秒）

## 图片模型更新点

Agnes Image 2.1 Flash 的重要注意事项：

1. **参数位置**：`response_format` 必须放在 `extra_body` 中（顶层会 400）
2. **Base64 输出**：
   - 文生图：使用顶层 `return_base64: true`
   - 图生图：使用 `extra_body.response_format: "b64_json"`
3. **图生图图片**：放在 `extra_body.image` 数组中
4. **不需要** `tags: ["img2img"]`
5. **支持的标准尺寸**：1024x1024, 1024x768, 768x1024, 576x1024, 1024x576

## 相关平台文档

- 平台 API 文档：[../API.md](../API.md)
