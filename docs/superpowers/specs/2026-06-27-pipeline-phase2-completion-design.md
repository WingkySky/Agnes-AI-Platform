# 创作工坊 Phase 2 收尾 — 设计文档

> 版本：v1.0
> 日期：2026-06-27
> 状态：设计中
> 关联文档：
> - [01-creative-pipeline-overview.md](../../01-creative-pipeline-overview.md) — 总体设计
> - [02-creative-pipeline-todolist.md](../../02-creative-pipeline-todolist.md) — 任务清单

---

## 1. 背景

创作工坊 Phase 2 目标是「输出完整带字幕配音视频」。代码探索发现：todolist 标记滞后于实际代码，多项功能其实已实现（SRT 生成、TimelinePreview、SubtitleEditor、字幕保存接口都已就位），但存在 4 项真实残留问题，导致用户感知「成片不可用」：

| 残留问题 | 影响 |
|---------|------|
| ① FinalVideoPlayer 用 `<track>` 加载 .srt | 浏览器原生只支持 WebVTT，字幕根本不显示 |
| ② 字幕烧录样式硬编码 | 用户无法调整字号/颜色/位置，风格不统一 |
| ③ 下载链接直连静态文件 | 不走水印服务，下载的视频无水印 |
| ④ 字幕编辑后只更新 SRT 文件 | 视频里烧录的还是旧字幕，编辑没意义 |

Phase 2 已实现部分（SRT 生成、TimelinePreview、SubtitleEditor、字幕保存接口）均不在本设计范围内。

---

## 2. 目标

让漫剧流水线产出的成片达到「可发布」质量：

1. 字幕在播放器里能正确显示（修复 WebVTT bug）
2. 字幕烧录样式可在前端配置（字号/颜色/底框/位置）
3. 下载视频时按用户配置加水印（复用现有 watermark_service）
4. 字幕编辑保存后能一键重新烧录到视频

**不做**：
- 时间轴精确对齐（配音长度 vs 视频片段长度，影响小，等真实场景反馈）
- 时间轴可视化重做（TimelinePreview 已能用）
- TTS 相关改进（已稳定）

---

## 3. 架构设计

### 3.1 整体数据流

```
[SubtitleEditor 编辑字幕] ──保存──> POST /runs/{id}/subtitles
                                          │
                                          ├─> 更新 step.output_data.subtitles
                                          ├─> 覆盖写 subtitles_{run_id}.srt
                                          └─> (新增) 同步生成 subtitles_{run_id}.vtt
                                                │
[SubtitleEditor 应用样式] ──重新烧录──> POST /runs/{id}/recompose
                                          │
                                          ├─> 读取 video_batch 步骤的视频 URL
                                          ├─> 用新字幕 + 样式重跑 ffmpeg drawtext
                                          ├─> 重新 concat 拼接
                                          ├─> 覆盖 final_{run_id}.mp4
                                          └─> 重新生成 .srt + .vtt

[FinalVideoPlayer 播放] ──加载──> .vtt 字幕（浏览器原生支持）

[FinalVideoPlayer 下载] ──请求──> GET /runs/{id}/download?watermark=1
                                          │
                                          ├─> 读取 final_{run_id}.mp4
                                          ├─> 调用扩展后的 watermark_service.apply_video_watermark
                                          ├─> ffmpeg overlay/drawtext 实时处理
                                          └─> 返回 Content-Disposition: attachment
```

### 3.2 字幕样式模型

字幕样式作为 `ffmpeg_composite` 步骤 `config` 的一部分存储，前端可编辑后随 recompose 请求传入。

```python
# 字幕样式配置（嵌入到 step.config.subtitle_style）
{
  "font_size": 36,            # 字号（px，按 1080p 高度基准）
  "font_color": "#FFFFFF",    # 字体颜色（hex）
  "box_color": "#000000",     # 底框颜色（hex）
  "box_opacity": 0.5,         # 底框不透明度（0~1）
  "position": "bottom",       # 位置：top / center / bottom
  "margin": 40                # 距边缘距离（px）
}
```

**默认值** = 当前硬编码值，保证不破坏现有流水线。

### 3.3 模块职责

#### 后端

| 文件 | 改动 |
|------|------|
| [ffmpeg_composite.py](../../../backend/app/services/pipeline/steps/ffmpeg_composite.py) | ① `_compose_single` 读取 `subtitle_style` config 构建 drawtext 滤镜；② 新增 `_generate_vtt_file` 方法，与 SRT 同步生成；③ 抽出 `_build_drawtext_filter(style)` 和 `_render_subtitles_to_video(...)` 供 recompose 复用 |
| [watermark_service.py](../../../backend/app/services/watermark_service.py) | 新增 `apply_video_watermark(video_path, config, output_path)`：文字水印用 ffmpeg drawtext、图片水印用 overlay；返回输出路径 |
| [run_service.py](../../../backend/app/services/pipeline/run_service.py) | 新增 `recompose_video(db, run_id, user_id, subtitles, subtitle_style)`：复用 ffmpeg_composite 的内部方法重新合成；更新 step.output_data |
| [routes/pipeline.py](../../../backend/app/routes/pipeline.py) | ① 新增 `POST /runs/{id}/recompose`；② 新增 `GET /runs/{id}/download`（query 参数 `watermark=1` 触发加水印，否则原文件直链）；③ SRT 保存接口同步生成 VTT |

#### 前端

| 文件 | 改动 |
|------|------|
| [FinalVideoPlayer.vue](../../../frontend/src/components/pipeline/FinalVideoPlayer.vue) | ① `subtitleUrl` 改用 .vtt 而非 .srt；② 下载按钮调 `downloadRunVideo(runId, {watermark:true})` 而非直链 |
| [SubtitleEditor.vue](../../../frontend/src/components/pipeline/SubtitleEditor.vue) | ① 新增「字幕样式」折叠面板（字号/颜色/底框/位置）；② 保存按钮区分「仅保存字幕」和「保存并重新烧录」 |
| [PipelineResultView.vue](../../../frontend/src/views/PipelineResultView.vue) | ① `finalSrtUrl` 旁加 `finalVttUrl` 计算属性传给 FinalVideoPlayer；② 处理 recompose 后的产物 URL 刷新（避免缓存） |
| [api/pipeline.ts](../../../frontend/src/api/pipeline.ts) | 新增 `recomposeVideo(runId, payload)` 和 `downloadRunVideo(runId, params)` |
| i18n (zh-CN / en-US) | 新增字幕样式、重新烧录、水印下载相关文案 |

---

## 4. 详细设计

### 4.1 WebVTT 转换（修复播放器字幕）

**问题**：HTML5 `<track>` 标签浏览器原生只支持 WebVTT（.vtt）格式，加载 .srt 字幕文件不会渲染。

**方案**：SRT 与 VTT 同步生成。VTT 与 SRT 几乎同构，主要差异：
- 文件头：VTT 必须以 `WEBVTT\n` 开头
- 时间分隔符：SRT 用 `,`，VTT 用 `.`（如 `00:00:05,200` → `00:00:05.200`）

**实现**：在 [ffmpeg_composite.py `_generate_srt_file`](../../../backend/app/services/pipeline/steps/ffmpeg_composite.py) 旁新增 `_generate_vtt_file`，复用相同的 entries 数据。两个文件都写入 `data/pipeline_outputs/`。

**返回值扩展**：
```python
# ffmpeg_composite.execute() 返回值新增字段
{
  "final_video_url": "...",
  "srt_url": "...",
  "vtt_url": "/api/pipeline/outputs/subtitles_{run_id}.vtt",  # 新增
  "subtitles": [...]
}
```

**路由扩展**：[get_pipeline_output](../../../backend/app/routes/pipeline.py) 的 `allowed_exts` 白名单加入 `.vtt`，mime_map 加 `".vtt": "text/vtt"`。

**前端**：FinalVideoPlayer 的 `subtitleUrl` prop 由父组件传 .vtt URL（PipelineResultView 计算 `finalVttUrl`）。

### 4.2 字幕样式可配置

**配置位置**：`pipeline_templates.steps_config[i].config.subtitle_style`（已有 config 字段，无需改表结构）。

**drawtext 滤镜构建**（替换 [ffmpeg_composite.py:359-363](../../../backend/app/services/pipeline/steps/ffmpeg_composite.py#L359) 的硬编码）：

```python
def _build_drawtext_filter(self, style: Dict[str, Any], text: str) -> str:
    """根据字幕样式配置构建 drawtext 滤镜字符串"""
    font_size = int(style.get("font_size", 36))
    font_color = style.get("font_color", "#FFFFFF").lstrip("#")
    box_color = style.get("box_color", "#000000").lstrip("#")
    box_opacity = float(style.get("box_opacity", 0.5))
    position = style.get("position", "bottom")
    margin = int(style.get("margin", 40))

    # box_opacity 转 0x00~0xFF
    box_alpha = int(box_opacity * 255)
    box_color_with_alpha = f"0x{box_color}@{box_opacity:.2f}"

    escaped = self._escape_drawtext_text(text)
    fontfile = self._find_font()
    font_opt = f":fontfile='{fontfile}'" if fontfile else ""

    # 位置计算
    if position == "top":
        pos = f"x=(w-text_w)/2:y={margin}"
    elif position == "center":
        pos = f"x=(w-text_w)/2:y=(h-text_h)/2"
    else:  # bottom（默认）
        pos = f"x=(w-text_w)/2:y=h-text_h-{margin}"

    return (
        f"drawtext=text='{escaped}'{font_opt}"
        f":fontcolor=0x{font_color}:fontsize={font_size}"
        f":box=1:boxcolor={box_color_with_alpha}:boxborderw=8"
        f":{pos}"
    )
```

**配置层级**（覆盖优先级从低到高）：
1. 默认硬编码值（保证向后兼容）
2. 模板 `steps_config[i].config.subtitle_style`
3. recompose 请求传入的 `subtitle_style`（最高优先级）

**前端 SubtitleEditor 样式面板**：用 Element Plus 折叠面板，包含 `el-input-number`（字号）、`el-color-picker`（字体/底框颜色）、`el-slider`（底框不透明度）、`el-radio-group`（位置 top/center/bottom）、`el-input-number`（边距）。

### 4.3 下载带水印

**现状**：[watermark_service.py:5](../../../backend/app/services/watermark_service.py#L5) 明确写「视频水印暂不处理」。[PipelineResultView.vue:525-534](../../../frontend/src/views/PipelineResultView.vue#L525) 的 handleDownload 直接走静态文件 URL。

**扩展 watermark_service**：

```python
async def apply_video_watermark(
    video_path: str,
    config: WatermarkConfig,
    output_path: str,
) -> str:
    """
    给视频加水印（文字或图片），返回输出文件路径。

    实现策略：
    - 文字水印：ffmpeg drawtext 滤镜（与字幕烧录复用字体查找逻辑）
    - 图片水印：ffmpeg overlay 滤镜
    - 不重编码视频流（-c:v copy 不可用，因 drawtext/overlay 需要 -filter_complex，必须重编码）
    - 用 libx264 -preset fast 平衡速度与质量
    """
```

**水印位置复用**：复用 [_calc_position](../../../backend/app/services/watermark_service.py#L194)，但 ffmpeg overlay 坐标系与 Pillow 不同，需做适配（如 `bottom-right` → `x=W-w-margin:y=H-h-margin`）。

**新路由**：

```
GET /api/pipeline/runs/{run_id}/download?watermark=1
```

- 不带 `watermark=1`：302 重定向到 `/api/pipeline/outputs/final_{run_id}.mp4`（保留原行为）
- 带 `watermark=1`：
  1. 读取 run 关联的 user
  2. 调 `get_watermark_config(db)` + `should_apply_watermark(config, user)`
  3. 不需要水印时，仍重定向到静态文件
  4. 需要水印时，调 `apply_video_watermark`（输出到临时文件），返回 FileResponse，`Content-Disposition: attachment; filename="pipeline_{run_id}_watermarked.mp4"`
  5. 水印文件做缓存（按 run_id + 水印配置 hash 命名），避免重复处理

**前端**：FinalVideoPlayer 的下载按钮改为调 `downloadRunVideo(runId, {watermark: true})`，浏览器直接下载（后端已设 Content-Disposition）。

### 4.4 字幕重新烧录接口

**新路由**：

```
POST /api/pipeline/runs/{run_id}/recompose
Body: {
  "subtitles": [{"start": 0.0, "end": 5.2, "text": "..."}, ...],  # 可选，不传则用已保存的字幕
  "subtitle_style": {"font_size": 36, ...}                        # 可选，不传则用模板默认
}
```

**服务层 `recompose_video`**：

```python
async def recompose_video(
    db: AsyncSession,
    run_id: int,
    user_id: int,
    subtitles: Optional[List[Dict]] = None,
    subtitle_style: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    用新字幕/样式重新烧录视频。

    流程：
    1. 校验 run 归属 + 找到 video_batch 步骤（取视频 URL）
    2. 找到 ffmpeg_composite 步骤（取原 config）
    3. 如 subtitles 为 None，用 step.output_data.subtitles
    4. 如 subtitle_style 为 None，用 step.config.subtitle_style 或默认
    5. 调 FFmpegCompositeExecutor 的内部方法重新合成
       - _download_all_videos
       - _compose_single（传入新 style）
       - _concat_videos
       - _generate_srt_file + _generate_vtt_file
    6. 覆盖 final_{run_id}.mp4、subtitles_{run_id}.srt/.vtt
    7. 更新 step.output_data（final_video_url/subtitles/srt_url/vtt_url）
    8. 返回新产物 URL（带 ?v=timestamp 防缓存）

    注意：这是耗时操作（约 30s-2min），同步执行会阻塞请求。
    方案：用 BackgroundTasks 后台执行，立即返回 task_id，前端轮询状态。
    """
```

**异步执行**：复用现有 SSE 推送进度。recompose 启动后，通过 sse_manager 推送 `recompose_started` / `recompose_progress` / `recompose_completed` / `recompose_failed` 事件，前端复用 usePipelineSSE 监听。

**前端交互**：SubtitleEditor 的「保存并重新烧录」按钮点击后：
1. 先调 `saveRunSubtitles` 保存字幕
2. 再调 `recomposeVideo(runId, {subtitle_style})`
3. 显示进度弹窗（复用 el-progress + SSE 事件）
4. 完成后刷新 PipelineResultView 的产物 URL（带时间戳防缓存）

### 4.5 错误处理

| 场景 | 处理 |
|------|------|
| recompose 时找不到 video_batch 步骤 | 返回 400「未找到上游视频步骤」 |
| ffmpeg drawtext 不可用 | 跳过烧录，仅生成外挂 SRT/VTT，前端提示「字幕仅外挂」 |
| 水印服务处理失败 | 日志记录，回退到无水印下载，不阻断用户 |
| recompose 后端任务超时 | 5 分钟超时，标记 failed，前端提示重试 |
| VTT 生成失败 | 不影响主流程，仅日志告警（SRT 仍可用） |

---

## 5. 数据模型变更

**无表结构变更**。所有新增字段都嵌入到现有的 JSON 列：
- `pipeline_steps.output_data` 新增 `vtt_url` 字段
- `pipeline_steps.config`（运行时副本）的 `subtitle_style` 由 recompose 接口写入

---

## 6. API 变更汇总

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| POST | `/api/pipeline/runs/{id}/subtitles` | 保存字幕（已存在） | 改：同步生成 VTT |
| POST | `/api/pipeline/runs/{id}/recompose` | 重新烧录视频 | 新增 |
| GET | `/api/pipeline/runs/{id}/download` | 下载视频（带水印参数） | 新增 |
| GET | `/api/pipeline/outputs/{filename}` | 静态产物访问（已存在） | 改：白名单加 .vtt |

---

## 7. 前端 i18n 文案清单

新增 i18n key（zh-CN / en-US 同步）：

```
pipelineResult.recompose              // 重新烧录
pipelineResult.recomposing            // 重新烧录中...
pipelineResult.recomposeSuccess       // 重新烧录完成
pipelineResult.recomposeFailed        // 重新烧录失败
pipelineResult.downloadWithWatermark  // 下载（带水印）
subtitleEditor.styleSettings          // 字幕样式
subtitleEditor.fontSize               // 字号
subtitleEditor.fontColor              // 字体颜色
subtitleEditor.boxColor               // 底框颜色
subtitleEditor.boxOpacity             // 底框不透明度
subtitleEditor.position               // 位置
subtitleEditor.positionTop            // 顶部
subtitleEditor.positionCenter         // 居中
subtitleEditor.positionBottom         // 底部
subtitleEditor.margin                 // 边距
subtitleEditor.saveAndRecompose       // 保存并重新烧录
subtitleEditor.recomposeTip           // 重新烧录会耗时约 1-2 分钟
```

---

## 8. 测试要点

| 场景 | 预期 |
|------|------|
| 播放器加载 .vtt 字幕 | 字幕正常显示 |
| SubtitleEditor 修改字号后保存并重新烧录 | 视频里字幕字号变化 |
| 用户开启水印配置时下载视频 | 下载的 mp4 含水印 |
| 用户未启用水印时下载 | 直链下载，无水印 |
| drawtext 不可用的环境 | 字幕仅外挂，不报错 |
| recompose 过程中网络断开 | 前端进度停止，刷新后可重新触发 |

---

## 9. 实施顺序

1. **后端 - WebVTT 生成**（独立、影响最小，先做）
2. **后端 - 字幕样式 drawtext 构建**（修改 _compose_single）
3. **后端 - recompose 服务 + 路由**（依赖 2）
4. **后端 - 视频水印扩展 + 下载路由**（独立，可并行）
5. **前端 - FinalVideoPlayer 改用 vtt**（依赖 1）
6. **前端 - SubtitleEditor 样式面板 + recompose 触发**（依赖 3）
7. **前端 - PipelineResultView 下载逻辑**（依赖 4）
8. **i18n 文案补充**（贯穿）
9. **端到端联调**

---

## 10. 风险

| 风险 | 应对 |
|------|------|
| recompose 是耗时操作，HTTP 同步请求可能超时 | 用 BackgroundTasks + SSE 推送进度，立即返回 task_id |
| 水印文件缓存可能占用磁盘 | 按 run_id + 水印配置 hash 命名，定期清理（本期不做自动清理，等后续） |
| 字幕样式配置不当导致 drawtext 报错 | 样式值做范围校验（字号 12-120、opacity 0-1），失败回退默认 |
| 重新烧录覆盖原视频文件 | 文件名带 run_id，覆盖前先备份到 `final_{run_id}.bak.mp4`（可选） |

---

*文档结束*
