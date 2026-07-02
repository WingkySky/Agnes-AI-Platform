# 创作工坊 Phase 2 收尾实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让漫剧流水线产出的成片达到可发布质量（修复字幕播放 bug、字幕样式可配置、下载带水印、字幕可重新烧录）

**Architecture:** 在现有 ffmpeg_composite 基础上同步生成 VTT、抽出 drawtext 滤镜构建方法支持样式配置；扩展 watermark_service 支持视频水印；新增 recompose 服务复用合成内部方法；前端 SubtitleEditor 加样式面板，FinalVideoPlayer 改用 .vtt，下载走带水印路由。

**Tech Stack:** FastAPI（async/await）+ ffmpeg/ffprobe 子进程 + Vue 3 + Element Plus + Pinia + SSE

**关联文档：** [2026-06-27-pipeline-phase2-completion-design.md](../specs/2026-06-27-pipeline-phase2-completion-design.md)

**项目约束（AGENTS.md）：** 不写测试、不执行构建、增量修改、保留功能模块备注、文案走 i18n 不硬编码中文、保留现有功能不受影响

---

## 文件结构

**后端修改：**
- `backend/app/services/pipeline/steps/ffmpeg_composite.py` — 新增 `_generate_vtt_file`、`_build_drawtext_filter`、`_render_subtitles_to_video`；改造 `_compose_single` 支持样式
- `backend/app/services/watermark_service.py` — 新增 `apply_video_watermark`、`_calc_ffmpeg_position`
- `backend/app/services/pipeline/run_service.py` — 新增 `recompose_video`
- `backend/app/routes/pipeline.py` — 新增 recompose / download 路由；改 SRT 保存接口同步生成 VTT；改 outputs 路由白名单加 .vtt
- `backend/app/schemas/pipeline.py` — 新增 RecomposeRequest schema

**前端修改：**
- `frontend/src/components/pipeline/FinalVideoPlayer.vue` — 下载按钮改调 downloadRunVideo
- `frontend/src/components/pipeline/SubtitleEditor.vue` — 新增字幕样式折叠面板 + 保存并重新烧录按钮
- `frontend/src/views/PipelineResultView.vue` — 新增 finalVttUrl 计算属性、recompose 进度弹窗、下载改用新 API
- `frontend/src/api/pipeline.ts` — 新增 recomposeVideo、downloadRunVideo
- `frontend/src/i18n/zh-CN.ts` + `en-US.ts` — 新增字幕样式/recompose/水印下载文案

---

## Task 1：后端 - ffmpeg_composite 新增 VTT 生成

**Files:**
- Modify: `backend/app/services/pipeline/steps/ffmpeg_composite.py`

- [ ] **Step 1: 在 `_generate_srt_file` 方法下方新增 `_generate_vtt_file` 方法**

在 `ffmpeg_composite.py` 的 `_format_srt` 方法之后（约第 716 行）、`_seconds_to_srt_time` 之前，新增：

```python
    async def _generate_vtt_file(
        self,
        subtitles: List[str],
        segment_durations: List[float],
        entries: Optional[List[Dict[str, Any]]] = None,
    ) -> tuple:
        """
        生成独立 WebVTT 字幕文件（供 HTML5 <track> 标签使用）

        浏览器原生 <track> 只支持 WebVTT，不支持 SRT。VTT 与 SRT 几乎同构，
        主要差异：文件头 WEBVTT、时间分隔符用 . 而非 ,

        Args:
            subtitles: 每个场景的字幕文本列表（仅用于 fallback 重新计算 entries）
            segment_durations: 每个片段的实际时长（秒）
            entries: 已计算好的字幕条目（优先用，避免重复计算；来自 _generate_srt_file）

        Returns:
            (vtt_url, entries)
            - vtt_url: 前端可访问的 VTT 文件 URL（如 /api/pipeline/outputs/subtitles_xxx.vtt）
            - entries: 字幕条目列表（与 SRT 一致）
        """
        # 如果未传入 entries，自行计算（与 _generate_srt_file 同逻辑）
        if not entries:
            entries = []
            current_time = 0.0
            for idx, text in enumerate(subtitles):
                duration = (
                    segment_durations[idx]
                    if idx < len(segment_durations) and segment_durations[idx] > 0
                    else 5.0
                )
                start = current_time
                end = current_time + duration
                current_time = end
                if not text or not text.strip():
                    continue
                entries.append({
                    "index": len(entries),
                    "scene_index": idx,
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": text.strip(),
                })

        if not entries:
            return "", []

        vtt_content = self._format_vtt(entries)
        run_id = self.context.run_id or "tmp"
        vtt_filename = f"subtitles_{run_id}.vtt"
        vtt_path = os.path.join(_OUTPUT_BASE, vtt_filename)

        try:
            with open(vtt_path, "w", encoding="utf-8") as f:
                f.write(vtt_content)
            vtt_url = f"/api/pipeline/outputs/{vtt_filename}"
            logger.info(
                f"[FFmpeg合成] VTT 字幕生成完成: {vtt_path}, 共 {len(entries)} 条"
            )
            return vtt_url, entries
        except Exception as e:
            logger.warning(f"[FFmpeg合成] VTT 字幕生成失败: {e}")
            return "", entries

    def _format_vtt(self, entries: List[Dict[str, Any]]) -> str:
        """
        格式化为标准 WebVTT 文件内容

        VTT 格式：
            WEBVTT

            00:00:00.000 --> 00:00:05.200
            字幕文本

            00:00:05.200 --> 00:00:10.500
            字幕文本
        """
        lines: List[str] = ["WEBVTT", ""]
        for entry in entries:
            # VTT 不需要序号（可选），但加 NOTE 注释会破坏解析，所以直接写时间戳
            start_str = self._seconds_to_vtt_time(entry["start"])
            end_str = self._seconds_to_vtt_time(entry["end"])
            lines.append(f"{start_str} --> {end_str}")
            lines.append(entry["text"])
            lines.append("")  # 空行分隔
        return "\n".join(lines)

    def _seconds_to_vtt_time(self, seconds: float) -> str:
        """将秒数转换为 VTT 时间格式 HH:MM:SS.mmm（与 SRT 的唯一差异：用 . 而非 ,）"""
        if seconds < 0:
            seconds = 0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
```

- [ ] **Step 2: 修改 `execute` 方法，在生成 SRT 后同步生成 VTT**

定位 `execute` 方法第 188-191 行（`if with_subtitle and subtitles:` 块），替换为：

```python
        # 9. 生成独立 SRT + VTT 字幕文件（时间戳基于每个片段的实际时长累积）
        srt_url = ""
        vtt_url = ""  # 新增 VTT URL（浏览器 <track> 标签需要 VTT 格式）
        subtitles_list: List[Dict[str, Any]] = []
        if with_subtitle and subtitles:
            srt_url, subtitles_list = await self._generate_srt_file(
                subtitles, segment_durations
            )
            # 同步生成 VTT（复用已计算的 entries，避免重复计算）
            vtt_url, _ = await self._generate_vtt_file(
                subtitles, segment_durations, entries=subtitles_list
            )
```

- [ ] **Step 3: 修改 `execute` 方法返回值，新增 vtt_url 字段**

定位 `execute` 方法返回值（约第 221-237 行），在 `srt_url` 后新增 `vtt_url`：

```python
        return {
            "videos": [{
                "index": 0,
                "video_url": final_url,
                "success": True,
                "is_final": True,
            }],
            "final_video_url": final_url,
            "final_video_path": final_path,
            "srt_url": srt_url,
            "vtt_url": vtt_url,  # 新增：浏览器 <track> 标签需要的 VTT 格式
            "subtitles": subtitles_list,
            "segments_count": len(composed_paths),
            "duration_seconds": duration,
            "with_subtitle": with_subtitle,
            "with_audio": bool(audios),
            "with_bgm": with_bgm and bool(bgm_url),
        }
```

- [ ] **Step 4: 修改 `save_generation_from_step` 调用的 params，加 vtt_url**

定位 `execute` 方法第 205-214 行（`params={...}` 块），在 `"srt_url": srt_url,` 后加：

```python
                        params={
                            "segments_count": len(composed_paths),
                            "with_subtitle": with_subtitle,
                            "with_bgm": with_bgm and bool(bgm_url),
                            "with_audio": bool(audios),
                            "duration_seconds": duration,
                            "local_path": final_path,
                            "srt_url": srt_url,
                            "vtt_url": vtt_url,  # 新增
                            "has_srt": bool(srt_url),
                            "has_vtt": bool(vtt_url),  # 新增
                        },
```

---

## Task 2：后端 - 字幕样式 drawtext 构建

**Files:**
- Modify: `backend/app/services/pipeline/steps/ffmpeg_composite.py`

- [ ] **Step 1: 新增 `_build_drawtext_filter` 方法（在 `_escape_drawtext_text` 之前）**

在 `_compose_single` 方法之后、`_escape_drawtext_text` 方法之前（约第 417 行），新增：

```python
    # 字幕样式默认值（与原硬编码保持一致，保证向后兼容）
    _DEFAULT_SUBTITLE_STYLE = {
        "font_size": 36,
        "font_color": "FFFFFF",
        "box_color": "000000",
        "box_opacity": 0.5,
        "position": "bottom",
        "margin": 40,
    }

    def _resolve_subtitle_style(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析字幕样式配置，合并默认值

        优先级（高到低）：
        1. config.subtitle_style（运行时传入，recompose 时由 run_service 注入）
        2. 默认值 _DEFAULT_SUBTITLE_STYLE

        校验规则：
        - font_size: 12~120
        - box_opacity: 0~1
        - position: top/center/bottom
        - 颜色：6 位 hex（不带 #）
        """
        style = dict(self._DEFAULT_SUBTITLE_STYLE)
        user_style = config.get("subtitle_style") or {}
        if isinstance(user_style, dict):
            # 字号校验
            font_size = user_style.get("font_size")
            if font_size is not None:
                try:
                    fs = int(font_size)
                    style["font_size"] = max(12, min(120, fs))
                except (ValueError, TypeError):
                    pass
            # 颜色校验（去掉 # 前缀，转大写）
            for key in ("font_color", "box_color"):
                val = user_style.get(key)
                if val and isinstance(val, str):
                    cleaned = val.lstrip("#").upper()
                    if len(cleaned) == 6 and all(c in "0123456789ABCDEF" for c in cleaned):
                        style[key] = cleaned
            # 不透明度校验
            opacity = user_style.get("box_opacity")
            if opacity is not None:
                try:
                    op = float(opacity)
                    style["box_opacity"] = max(0.0, min(1.0, op))
                except (ValueError, TypeError):
                    pass
            # 位置校验
            pos = user_style.get("position")
            if pos in ("top", "center", "bottom"):
                style["position"] = pos
            # 边距校验
            margin = user_style.get("margin")
            if margin is not None:
                try:
                    m = int(margin)
                    style["margin"] = max(0, min(500, m))
                except (ValueError, TypeError):
                    pass
        return style

    def _build_drawtext_filter(
        self,
        style: Dict[str, Any],
        text: str,
    ) -> str:
        """
        根据字幕样式配置构建 drawtext 滤镜字符串

        Args:
            style: 字幕样式配置（已合并默认值）
            text: 字幕文本（未转义）

        Returns:
            drawtext 滤镜字符串，如：
            drawtext=text='...':fontfile='...':fontcolor=0xFFFFFF:fontsize=36:box=1:boxcolor=0x000000@0.50:boxborderw=8:x=(w-text_w)/2:y=h-text_h-40
        """
        font_size = int(style.get("font_size", 36))
        font_color = style.get("font_color", "FFFFFF")
        box_color = style.get("box_color", "000000")
        box_opacity = float(style.get("box_opacity", 0.5))
        position = style.get("position", "bottom")
        margin = int(style.get("margin", 40))

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
            f":box=1:boxcolor=0x{box_color}@{box_opacity:.2f}:boxborderw=8"
            f":{pos}"
        )
```

- [ ] **Step 2: 修改 `_compose_single` 方法，从 config 读取 subtitle_style 并调用 `_build_drawtext_filter`**

定位 `_compose_single` 方法（约第 323-415 行），替换其中构建 drawtext 滤镜的部分（约第 353-365 行）。

将原来的：

```python
        # 构建视频滤镜（drawtext 烧录字幕）
        vf_filters: List[str] = []
        if has_subtitle:
            escaped = self._escape_drawtext_text(subtitle_text)
            fontfile = self._find_font()
            font_opt = f":fontfile='{fontfile}'" if fontfile else ""
            vf_filters.append(
                f"drawtext=text='{escaped}'{font_opt}:fontcolor=white:fontsize=36:"
                f"box=1:boxcolor=black@0.5:boxborderw=8:"
                f"x=(w-text_w)/2:y=h-text_h-40"
            )

        vf_arg = ",".join(vf_filters) if vf_filters else None
```

替换为：

```python
        # 构建视频滤镜（drawtext 烧录字幕，支持样式配置）
        vf_filters: List[str] = []
        if has_subtitle:
            # 从 step config 读取字幕样式（recompose 时会注入更新后的样式）
            style = self._resolve_subtitle_style(self.config.get("config", {}))
            vf_filters.append(self._build_drawtext_filter(style, subtitle_text))

        vf_arg = ",".join(vf_filters) if vf_filters else None
```

---

## Task 3：后端 - 抽出 `_render_subtitles_to_video` 供 recompose 复用

**Files:**
- Modify: `backend/app/services/pipeline/steps/ffmpeg_composite.py`

- [ ] **Step 1: 新增 `_render_subtitles_to_video` 方法（在 `_concat_videos` 之后）**

在 `_concat_videos` 方法之后（约第 483 行）、`_try_concat_copy` 之前，新增：

```python
    async def _render_subtitles_to_video(
        self,
        video_paths: List[str],
        subtitles_by_index: Dict[int, str],
        audio_paths_by_index: Dict[int, str],
        subtitle_style: Optional[Dict[str, Any]] = None,
    ) -> tuple:
        """
        重新烧录字幕到现有视频片段（供 recompose 复用）

        与 _compose_single 类似，但接受外部传入的字幕和样式。
        recompose 流程使用此方法避免重新下载视频（直接复用本地缓存或重新下载）。

        Args:
            video_paths: 视频文件路径列表（按 index 排序）
            subtitles_by_index: {index: 字幕文本} 字典
            audio_paths_by_index: {index: 音频路径} 字典（可选）
            subtitle_style: 字幕样式配置（None 时用 step config 中的样式）

        Returns:
            (composed_paths, segment_durations)
            - composed_paths: 合成后的视频路径列表
            - segment_durations: 每个片段的实际时长（秒）
        """
        # 如果传入新样式，临时注入到 self.config 供 _compose_single 读取
        original_config = self.config.get("config", {})
        if subtitle_style is not None:
            merged_config = dict(original_config)
            merged_config["subtitle_style"] = subtitle_style
            # 注入到 self.config（_compose_single 通过 self.config.config 读取）
            self.config["config"] = merged_config

        composed_paths: List[str] = []
        segment_durations: List[float] = []
        try:
            for idx, vpath in enumerate(video_paths):
                if not vpath or not os.path.exists(vpath):
                    logger.warning(f"[FFmpeg合成-recompose] 跳过空视频 #{idx}")
                    continue
                subtitle_text = subtitles_by_index.get(idx, "")
                audio_path = audio_paths_by_index.get(idx)
                composed = await self._compose_single(
                    vpath, idx, subtitle_text, audio_path
                )
                composed_paths.append(composed)
                seg_duration = await self._get_video_duration(composed)
                segment_durations.append(seg_duration)
        finally:
            # 恢复原始 config（避免污染后续执行）
            if subtitle_style is not None:
                self.config["config"] = original_config

        return composed_paths, segment_durations
```

- [ ] **Step 2: 在 `FFmpegCompositeExecutor` 类外新增模块级函数 `recompose_pipeline_video`（文件末尾）**

在文件末尾（`_seconds_to_srt_time` 方法之后）新增模块级函数：

```python


# =====================================================
# 模块级 recompose 函数（供 run_service 调用，无需走完整 step 执行流程）
# =====================================================

async def recompose_pipeline_video(
    run_id: int,
    user_id: int,
    video_urls: List[str],
    audio_urls: List[str],
    subtitles: List[Dict[str, Any]],
    subtitle_style: Optional[Dict[str, Any]],
    step_config: Dict[str, Any],
    audio_base_dir: str,
) -> Dict[str, Any]:
    """
    重新烧录字幕到视频（recompose 入口，由 run_service.recompose_video 调用）

    复用 FFmpegCompositeExecutor 的内部方法，但不走完整 step 执行框架。

    流程：
    1. 下载所有视频片段到临时目录
    2. 用新字幕+样式重跑 _compose_single
    3. 拼接所有视频（_concat_videos）
    4. 重新生成 SRT + VTT
    5. 覆盖 final_{run_id}.mp4、subtitles_{run_id}.srt/.vtt

    Args:
        run_id: 流水线运行 ID
        user_id: 用户 ID（日志用）
        video_urls: 上游 video_batch 步骤的视频 URL 列表
        audio_urls: 上游 tts_generate 步骤的音频 URL 列表（可为空）
        subtitles: 字幕条目列表 [{start, end, text, scene_index}, ...]
        subtitle_style: 字幕样式配置（None 用默认）
        step_config: 原 ffmpeg_composite 步骤的 config
        audio_base_dir: 音频文件本地缓存的基目录

    Returns:
        {
            "final_video_url": str,
            "final_video_path": str,
            "srt_url": str,
            "vtt_url": str,
            "subtitles": List[Dict],
            "duration_seconds": float,
            "segments_count": int,
        }
    """
    # 构造一个临时 executor 实例，复用其内部方法
    from app.services.pipeline.steps.base import StepExecutionContext

    context = StepExecutionContext(
        run_id=run_id,
        user_id=user_id,
        inputs={},
        steps_output={},
    )
    executor = FFmpegCompositeExecutor(
        step_config={"config": {**step_config, "subtitle_style": subtitle_style or {}}},
        run_context=context,
    )

    # 1. 下载视频（复用 _download_all_videos）
    logger.info(f"[recompose] run={run_id} 开始下载 {len(video_urls)} 个视频片段")
    videos_data = [{"index": i, "video_url": url} for i, url in enumerate(video_urls)]
    video_paths = await executor._download_all_videos(videos_data)

    # 2. 准备字幕映射（按 scene_index 对应到视频 index）
    subtitles_by_index: Dict[int, str] = {}
    for sub in subtitles:
        scene_idx = int(sub.get("scene_index", sub.get("index", 0)))
        subtitles_by_index[scene_idx] = sub.get("text", "")

    # 3. 准备音频映射（如有）
    audio_paths_by_index: Dict[int, str] = {}
    if audio_urls:
        # 下载音频到临时目录（音频 URL 形如 /api/pipeline/outputs/tts_run_X_seg_000.mp3）
        import tempfile
        audio_temp_dir = tempfile.mkdtemp(prefix="agnes_recompose_audio_")
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            for idx, url in enumerate(audio_urls):
                if not url:
                    continue
                try:
                    # 相对 URL 转本地路径（pipeline outputs 都在 _OUTPUT_BASE 下）
                    if url.startswith("/api/pipeline/outputs/"):
                        fname = url.rsplit("/", 1)[-1]
                        local_path = os.path.join(_OUTPUT_BASE, fname)
                        if os.path.exists(local_path):
                            audio_paths_by_index[idx] = local_path
                            continue
                    # 远程 URL 下载
                    resp = await client.get(url, headers={"User-Agent": "Agnes-Platform"})
                    if resp.status_code == 200:
                        out_path = os.path.join(audio_temp_dir, f"audio_{idx:03d}.mp3")
                        with open(out_path, "wb") as f:
                            f.write(resp.content)
                        audio_paths_by_index[idx] = out_path
                except Exception as e:
                    logger.warning(f"[recompose] 下载音频 #{idx} 失败: {e}")

    # 4. 重新烧录字幕
    logger.info(f"[recompose] run={run_id} 开始重新烧录字幕")
    composed_paths, segment_durations = await executor._render_subtitles_to_video(
        video_paths=video_paths,
        subtitles_by_index=subtitles_by_index,
        audio_paths_by_index=audio_paths_by_index,
        subtitle_style=subtitle_style,
    )

    if not composed_paths:
        raise RuntimeError("recompose 失败：没有可合成的视频片段")

    # 5. 拼接
    if len(composed_paths) == 1:
        final_path = composed_paths[0]
    else:
        final_path = await executor._concat_videos(composed_paths)

    # 6. 重新生成 SRT + VTT（基于实际时长）
    # 将 subtitles 的 start/end 重新计算（基于 segment_durations 累积）
    entries: List[Dict[str, Any]] = []
    current_time = 0.0
    for idx, sub in enumerate(subtitles):
        duration = (
            segment_durations[idx]
            if idx < len(segment_durations) and segment_durations[idx] > 0
            else 5.0
        )
        # 保留用户编辑的 text，但 start/end 按实际时长重新计算（确保与视频对齐）
        entries.append({
            "index": len(entries),
            "scene_index": sub.get("scene_index", idx),
            "start": round(current_time, 3),
            "end": round(current_time + duration, 3),
            "text": sub.get("text", "").strip(),
        })
        current_time += duration

    # 过滤空文本（与原 _generate_srt_file 逻辑一致）
    entries = [e for e in entries if e["text"]]

    # 写 SRT
    srt_content = executor._format_srt(entries)
    srt_filename = f"subtitles_{run_id}.srt"
    srt_path = os.path.join(_OUTPUT_BASE, srt_filename)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
    srt_url = f"/api/pipeline/outputs/{srt_filename}"

    # 写 VTT
    vtt_content = executor._format_vtt(entries)
    vtt_filename = f"subtitles_{run_id}.vtt"
    vtt_path = os.path.join(_OUTPUT_BASE, vtt_filename)
    with open(vtt_path, "w", encoding="utf-8") as f:
        f.write(vtt_content)
    vtt_url = f"/api/pipeline/outputs/{vtt_filename}"

    # 7. 最终视频覆盖到 _OUTPUT_BASE/final_{run_id}.mp4
    final_filename = f"final_{run_id}.mp4"
    final_dest = os.path.join(_OUTPUT_BASE, final_filename)
    # 如果合成路径与目标不同，复制过去
    if os.path.abspath(final_path) != os.path.abspath(final_dest):
        import shutil
        shutil.copy2(final_path, final_dest)
    final_url = f"/api/pipeline/outputs/{final_filename}"
    duration = await executor._get_video_duration(final_dest)

    logger.info(
        f"[recompose] run={run_id} 完成: {final_dest}, 时长={duration}s, "
        f"字幕={len(entries)} 条"
    )

    return {
        "final_video_url": final_url,
        "final_video_path": final_dest,
        "srt_url": srt_url,
        "vtt_url": vtt_url,
        "subtitles": entries,
        "duration_seconds": duration,
        "segments_count": len(composed_paths),
    }
```

注意：此处新增了模块级函数，绕过完整 step 执行框架，便于 recompose 直接复用内部方法。需在文件顶部确认已 import `Optional`（已有）。

---

## Task 4：后端 - 扩展 watermark_service 支持视频水印

**Files:**
- Modify: `backend/app/services/watermark_service.py`

- [ ] **Step 1: 在文件末尾新增 `_calc_ffmpeg_position` 辅助函数**

在文件末尾（`_hex_to_rgb` 函数之后）新增：

```python


# =====================================================
# 视频水印（ffmpeg drawtext / overlay）
# =====================================================

def _calc_ffmpeg_position(
    position: str,
    video_width: int,
    video_height: int,
    wm_width: int,
    wm_height: int,
    margin: int,
) -> str:
    """
    根据位置字符串计算 ffmpeg overlay 滤镜的坐标表达式

    ffmpeg overlay 坐标系：左上角为原点，支持表达式（W/H 为主视频宽高，w/h 为水印宽高）

    Returns:
        ffmpeg 坐标表达式字符串，如 "x=W-w-20:y=H-h-20"
    """
    position_str = str(position or "bottom-right").lower()
    # 安全转换
    try:
        margin = max(0, int(margin or 20))
    except (ValueError, TypeError):
        margin = 20

    if position_str == "top-left":
        return f"x={margin}:y={margin}"
    elif position_str == "top-right":
        return f"x=W-w-{margin}:y={margin}"
    elif position_str == "bottom-left":
        return f"x={margin}:y=H-h-{margin}"
    elif position_str == "center":
        return f"x=(W-w)/2:y=(H-h)/2"
    else:  # bottom-right（默认）
        return f"x=W-w-{margin}:y=H-h-{margin}"


def _find_video_font() -> str:
    """查找系统中可用的中文字体文件（与 ffmpeg_composite._find_font 逻辑一致）"""
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for f in candidates:
        if os.path.exists(f):
            return f
    return ""


def _escape_drawtext_text(text: str) -> str:
    """转义 drawtext 文本中的特殊字符（与 ffmpeg_composite 一致）"""
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    text = text.replace("%", "\\%")
    text = text.replace("\n", " ").replace("\r", " ")
    return text
```

- [ ] **Step 2: 在文件顶部添加 asyncio import，并新增 `apply_video_watermark` 函数**

修改文件顶部 import 区（第 7-10 行附近），在 `import os` 后新增：

```python
import asyncio
import hashlib
import tempfile
import logging
```

然后在新辅助函数之后新增 `apply_video_watermark`：

```python
_video_watermark_logger = logging.getLogger("agnes_platform.watermark")


async def apply_video_watermark(
    video_path: str,
    config: "WatermarkConfig",
    output_path: str,
) -> str:
    """
    给视频加水印（文字或图片），返回输出文件路径

    实现策略：
    - 文字水印：ffmpeg drawtext 滤镜
    - 图片水印：ffmpeg overlay 滤镜
    - 必须重编码视频流（drawtext/overlay 需要 -filter_complex，不能用 -c:v copy）
    - 用 libx264 -preset fast 平衡速度与质量

    Args:
        video_path: 输入视频文件路径
        config: 水印配置（WatermarkConfig ORM 对象）
        output_path: 输出文件路径

    Returns:
        输出文件路径（处理失败时返回原 video_path，不阻断下载）
    """
    if not os.path.exists(video_path):
        _video_watermark_logger.warning(f"[视频水印] 输入视频不存在: {video_path}")
        return video_path

    opacity = max(0, min(100, int(config.opacity or 50)))
    alpha = opacity / 100.0  # 0.0~1.0
    margin = int(getattr(config, "margin", 20) or 20)
    position = str(getattr(config, "position", "bottom-right") or "bottom-right")

    wm_type = str(getattr(config, "type", "text") or "text").lower()
    fontfile = _find_video_font()
    font_opt = f":fontfile='{fontfile}'" if fontfile else ""

    # 构建 filter_complex
    if wm_type == "image" and getattr(config, "image_url", None):
        # 图片水印：用 overlay 滤镜
        from urllib.parse import urlparse
        image_url = str(config.image_url or "")
        parsed = urlparse(image_url)
        local_path = parsed.path
        if not local_path or not os.path.exists(local_path):
            _video_watermark_logger.warning(
                f"[视频水印] 水印图片不存在或为远程URL: {image_url}，跳过"
            )
            return video_path

        # 计算水印图片缩放后的尺寸（用于位置计算）
        wm_width = int(getattr(config, "image_width", 120) or 120)
        if wm_width <= 0:
            wm_width = 120
        # overlay 表达式不直接知道缩放后的高，用 -filter_complex 链
        pos_expr = _calc_ffmpeg_position(
            position, 0, 0, 0, 0, margin  # video_width/height 用 W/H 表达式
        )
        # 注意：图片水印的高需要从输入读取，这里用 w/h 表达式
        # 替换占位为 ffmpeg 表达式
        if "W-w-" in pos_expr:
            pos_expr = pos_expr.replace("W-w-", "W-w-")
        elif "W-w" in pos_expr:
            pass  # 已是表达式
        # 简化：overlay 直接用 W/H/w/h 表达式
        if position == "top-left":
            overlay_pos = f"x={margin}:y={margin}"
        elif position == "top-right":
            overlay_pos = f"x=W-w-{margin}:y={margin}"
        elif position == "bottom-left":
            overlay_pos = f"x={margin}:y=H-h-{margin}"
        elif position == "center":
            overlay_pos = f"x=(W-w)/2:y=(H-h)/2"
        else:  # bottom-right
            overlay_pos = f"x=W-w-{margin}:y=H-h-{margin}"

        filter_complex = (
            f"[1:v]scale={wm_width}:-1[wm];"
            f"[0:v][wm]overlay={overlay_pos}:format=auto[outv]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", local_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "0:a?",  # 保留原音轨（如有）
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]
    else:
        # 文字水印：用 drawtext 滤镜
        text = str(getattr(config, "text", None) or "Agnes AI")
        escaped = _escape_drawtext_text(text)
        font_size = int(getattr(config, "font_size", 24) or 24)
        if font_size <= 0:
            font_size = 24
        color_hex = str(getattr(config, "color", None) or "#FFFFFF").lstrip("#")
        color_rgb = _hex_to_rgb(color_hex)
        # drawtext fontcolor 用 0xRRGGBB@alpha 格式
        fontcolor = f"0x{color_rgb[0]:02X}{color_rgb[1]:02X}{color_rgb[2]:02X}@{alpha:.2f}"

        # 位置表达式
        if position == "top-left":
            pos = f"x={margin}:y={margin}"
        elif position == "top-right":
            pos = f"x=w-text_w-{margin}:y={margin}"
        elif position == "bottom-left":
            pos = f"x={margin}:y=h-text_h-{margin}"
        elif position == "center":
            pos = f"x=(w-text_w)/2:y=(h-text_h)/2"
        else:  # bottom-right
            pos = f"x=w-text_w-{margin}:y=h-text_h-{margin}"

        drawtext = (
            f"drawtext=text='{escaped}'{font_opt}"
            f":fontcolor={fontcolor}:fontsize={font_size}"
            f":{pos}"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", drawtext,
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        if proc.returncode != 0:
            err_text = stderr.decode(errors="ignore")[-300:]
            _video_watermark_logger.warning(f"[视频水印] ffmpeg 失败: {err_text}")
            return video_path
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
        _video_watermark_logger.warning("[视频水印] 输出文件为空")
        return video_path
    except asyncio.TimeoutError:
        _video_watermark_logger.warning("[视频水印] ffmpeg 超时（5min）")
        return video_path
    except Exception as e:
        _video_watermark_logger.warning(f"[视频水印] 异常: {e}")
        return video_path
```

---

## Task 5：后端 - run_service 新增 recompose_video

**Files:**
- Modify: `backend/app/services/pipeline/run_service.py`

- [ ] **Step 1: 在 `save_subtitles` 函数之后新增 `recompose_video` 函数**

先在文件顶部确认 import（应有 `from app.services.pipeline.steps.ffmpeg_composite import _OUTPUT_BASE`），新增 `recompose_pipeline_video` 的 import。

定位 `save_subtitles` 函数末尾（约第 870-880 行），在其后新增：

```python


async def recompose_video(
    db: AsyncSession,
    run_id: int,
    user_id: int,
    subtitles: Optional[List[Dict[str, Any]]] = None,
    subtitle_style: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    用新字幕/样式重新烧录视频

    流程：
    1. 校验 run 归属当前用户
    2. 定位 video_batch 步骤（取视频 URL 列表）
    3. 定位 ffmpeg_composite 步骤（取原 config + 已保存字幕）
    4. 如 subtitles 为 None，用 step.output_data.subtitles
    5. 如 subtitle_style 为 None，用 step.config.subtitle_style 或默认
    6. 调 recompose_pipeline_video 重新合成
    7. 更新 step.output_data（final_video_url/subtitles/srt_url/vtt_url）
    8. 返回新产物 URL（带 ?v=timestamp 防缓存）

    Args:
        db: 异步会话
        run_id: 流水线运行 ID
        user_id: 当前用户 ID（鉴权用）
        subtitles: 字幕条目列表（None 时用已保存的）
        subtitle_style: 字幕样式配置（None 时用 step config）

    Returns:
        {
            "final_video_url": str,
            "srt_url": str,
            "vtt_url": str,
            "subtitles": List[Dict],
            "duration_seconds": float,
            "segments_count": int,
        }
    """
    import time
    from app.services.pipeline.steps.ffmpeg_composite import (
        recompose_pipeline_video,
        _OUTPUT_BASE,
    )

    # 1. 校验 run 归属
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")
    if run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权修改此流水线")

    # 2. 获取所有步骤
    steps = await get_run_steps(db, run_id)

    # 3. 定位 video_batch 步骤（取视频 URL 列表）
    video_steps = [s for s in steps if s.step_type == "video_batch" and s.status == "success"]
    if not video_steps:
        raise HTTPException(
            status_code=400,
            detail="未找到已完成的视频生成步骤，无法重新烧录"
        )
    video_step = sorted(video_steps, key=lambda s: s.sort_order, reverse=True)[0]
    video_output = video_step.output_data or {}
    videos = video_output.get("videos", [])
    if not videos:
        raise HTTPException(status_code=400, detail="视频步骤无产出")
    video_urls = [v.get("video_url") or v.get("url", "") for v in videos]

    # 4. 定位 ffmpeg_composite 步骤（取原 config + 字幕）
    composite_steps = [
        s for s in steps
        if s.step_type == "ffmpeg_composite" and s.status == "success"
    ]
    if not composite_steps:
        raise HTTPException(
            status_code=400,
            detail="未找到已完成的合成步骤，无法重新烧录"
        )
    composite_step = sorted(composite_steps, key=lambda s: s.sort_order, reverse=True)[0]
    composite_output = dict(composite_step.output_data or {})

    # 5. 字幕：优先用传入的，否则用已保存的
    if subtitles is None:
        subtitles = composite_output.get("subtitles", [])
    if not subtitles:
        raise HTTPException(status_code=400, detail="字幕列表为空，无法重新烧录")

    # 6. 字幕样式：优先用传入的，否则用 step config 中的
    step_config = composite_step.config or composite_step.input_data or {}
    if isinstance(step_config, dict):
        step_config_dict = step_config.get("config", step_config)
    else:
        step_config_dict = {}

    # 7. 定位 tts_generate 步骤（如有，取音频 URL）
    audio_urls: List[str] = []
    tts_steps = [s for s in steps if s.step_type == "tts_generate" and s.status == "success"]
    if tts_steps:
        tts_step = sorted(tts_steps, key=lambda s: s.sort_order, reverse=True)[0]
        tts_output = tts_step.output_data or {}
        audios = tts_output.get("audios", [])
        audio_urls = [a.get("audio_url", "") for a in audios]

    # 8. 调 recompose_pipeline_video 执行
    try:
        result = await recompose_pipeline_video(
            run_id=run_id,
            user_id=user_id,
            video_urls=video_urls,
            audio_urls=audio_urls,
            subtitles=subtitles,
            subtitle_style=subtitle_style,
            step_config=step_config_dict,
            audio_base_dir=_OUTPUT_BASE,
        )
    except Exception as e:
        logger.error(f"[recompose] run={run_id} 失败: {e}")
        raise HTTPException(status_code=500, detail=f"重新烧录失败: {e}")

    # 9. 更新 step.output_data
    composite_step.output_data = {
        **composite_output,
        "final_video_url": result["final_video_url"],
        "final_video_path": result["final_video_path"],
        "srt_url": result["srt_url"],
        "vtt_url": result["vtt_url"],
        "subtitles": result["subtitles"],
        "duration_seconds": result["duration_seconds"],
        "segments_count": result["segments_count"],
        "recomposed_at": time.time(),
    }
    # 如果传入了新样式，同步到 step.config
    if subtitle_style is not None:
        updated_config = dict(step_config_dict)
        updated_config["subtitle_style"] = subtitle_style
        composite_step.config = {"config": updated_config}

    await db.commit()

    # 10. 返回带防缓存时间戳的 URL
    ts = int(time.time())
    return {
        "final_video_url": f"{result['final_video_url']}?v={ts}",
        "srt_url": f"{result['srt_url']}?v={ts}",
        "vtt_url": f"{result['vtt_url']}?v={ts}",
        "subtitles": result["subtitles"],
        "duration_seconds": result["duration_seconds"],
        "segments_count": result["segments_count"],
    }
```

注意：`composite_step.config` 字段是否可写需确认 PipelineStep 模型有 `config` 列；若没有则只更新 output_data，跳过样式持久化。先实现时按"有则更新，无则跳过"。

---

## Task 6：后端 - routes/pipeline.py 新增 recompose 和 download 路由

**Files:**
- Modify: `backend/app/routes/pipeline.py`
- Modify: `backend/app/schemas/pipeline.py`

- [ ] **Step 1: 在 schemas/pipeline.py 新增 RecomposeRequest**

在 `schemas/pipeline.py` 中（找到已有的 SubtitleEntry 附近）新增：

```python
class SubtitleStyle(BaseModel):
    """字幕样式配置"""
    font_size: Optional[int] = Field(None, ge=12, le=120, description="字号（12-120）")
    font_color: Optional[str] = Field(None, description="字体颜色 hex（如 FFFFFF）")
    box_color: Optional[str] = Field(None, description="底框颜色 hex")
    box_opacity: Optional[float] = Field(None, ge=0.0, le=1.0, description="底框不透明度（0-1）")
    position: Optional[str] = Field(None, pattern="^(top|center|bottom)$", description="位置")
    margin: Optional[int] = Field(None, ge=0, le=500, description="边距 px")


class RecomposeRequest(BaseModel):
    """重新烧录视频请求"""
    subtitles: Optional[List[Dict[str, Any]]] = Field(
        None, description="字幕条目列表（不传则用已保存的）"
    )
    subtitle_style: Optional[SubtitleStyle] = Field(
        None, description="字幕样式配置（不传则用模板默认）"
    )
```

如 `Dict`、`Any`、`List` 未导入，在文件顶部确认 `from typing import Any, Dict, List, Optional`。

- [ ] **Step 2: 在 routes/pipeline.py 顶部新增 import**

确认 routes/pipeline.py 顶部已 import 相关依赖，新增（如已有则跳过）：

```python
from fastapi.responses import RedirectResponse, FileResponse
from app.services.watermark_service import (
    get_watermark_config,
    should_apply_watermark,
    apply_video_watermark,
)
from app.schemas.pipeline import RecomposeRequest
from app.services.pipeline.run_service import recompose_video
```

- [ ] **Step 3: 在「保存字幕」路由之后新增 recompose 路由**

定位 `POST /pipeline/runs/{run_id}/subtitles` 路由之后（约第 380 行），新增：

```python
@router.post("/pipeline/runs/{run_id}/recompose", summary="重新烧录字幕到视频")
async def recompose_run_video(
    run_id: int,
    payload: RecomposeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    用新字幕/样式重新烧录视频。

    - 同步执行（耗时约 30s-2min，前端应显示进度）
    - 复用 ffmpeg_composite 的内部方法
    - 覆盖 final_{run_id}.mp4、subtitles_{run_id}.srt/.vtt
    - 返回新产物 URL（带 ?v=timestamp 防缓存）
    """
    # subtitle_style Pydantic 模型转 dict（None 保留）
    style_dict = None
    if payload.subtitle_style:
        # 只取非 None 字段
        style_dict = {
            k: v for k, v in payload.subtitle_style.model_dump().items()
            if v is not None
        }
        if not style_dict:
            style_dict = None

    result = await recompose_video(
        db=db,
        run_id=run_id,
        user_id=current_user.id,
        subtitles=payload.subtitles,
        subtitle_style=style_dict,
    )
    return {"message": "重新烧录完成", "data": result}
```

如 `BackgroundTasks` 未导入，从 `fastapi` 导入。

- [ ] **Step 4: 在 recompose 路由之后新增 download 路由**

```python
@router.get("/pipeline/runs/{run_id}/download", summary="下载流水线最终视频")
async def download_run_video(
    run_id: int,
    watermark: int = 0,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    下载流水线最终视频。

    - watermark=0（默认）：302 重定向到静态文件（无水印）
    - watermark=1：按用户水印配置实时加水印，返回 FileResponse（attachment）

    水印处理策略：
    1. 读取 run 关联的 user
    2. 调 should_apply_watermark 判断是否需要加水印
    3. 不需要时仍重定向到静态文件
    4. 需要时调 apply_video_watermark，结果缓存到 data/pipeline_outputs/
    """
    import os
    import hashlib
    from app.services.pipeline.run_service import get_run_by_id
    from app.services.pipeline.steps.ffmpeg_composite import _OUTPUT_BASE
    from app.services.pipeline.run_service import get_run_steps
    from app.models.user import User as UserModel

    # 校验 run 归属
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")
    if run.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权下载此流水线视频")

    # 找到 ffmpeg_composite 步骤，取 final_video_path
    steps = await get_run_steps(db, run_id)
    composite_steps = [
        s for s in steps
        if s.step_type == "ffmpeg_composite" and s.status == "success"
    ]
    if not composite_steps:
        raise HTTPException(status_code=400, detail="未找到已完成的合成步骤")
    composite_step = sorted(composite_steps, key=lambda s: s.sort_order, reverse=True)[0]
    output_data = composite_step.output_data or {}

    # 优先用 output_data.final_video_path，否则从 URL 反推
    final_path = output_data.get("final_video_path", "")
    if not final_path:
        final_url = output_data.get("final_video_url", "")
        if final_url:
            fname = final_url.rsplit("/", 1)[-1].split("?")[0]
            final_path = os.path.join(_OUTPUT_BASE, fname)

    if not final_path or not os.path.exists(final_path):
        raise HTTPException(status_code=404, detail="最终视频文件不存在")

    # 不加水印：直接重定向到静态文件路由
    if watermark != 1:
        final_url = output_data.get("final_video_url", "")
        if not final_url:
            fname = os.path.basename(final_path)
            final_url = f"/api/pipeline/outputs/{fname}"
        return RedirectResponse(url=final_url, status_code=302)

    # 加水印：判断是否需要
    wm_config = await get_watermark_config(db)
    # 重新查 user（获取 watermark_enabled 字段）
    from sqlalchemy.future import select
    user_result = await db.execute(select(UserModel).filter(UserModel.id == run.user_id))
    user_obj = user_result.scalar_one_or_none()

    if not should_apply_watermark(wm_config, user_obj):
        # 不需要水印，重定向到静态文件
        final_url = output_data.get("final_video_url", "")
        if not final_url:
            fname = os.path.basename(final_path)
            final_url = f"/api/pipeline/outputs/{fname}"
        return RedirectResponse(url=final_url, status_code=302)

    # 需要加水印：缓存文件名 = final_{run_id}_wm_{config_hash}.mp4
    config_str = f"{wm_config.id}|{wm_config.text}|{wm_config.type}|{wm_config.position}|{wm_config.font_size}|{wm_config.opacity}|{wm_config.margin}"
    config_hash = hashlib.md5(config_str.encode()).hexdigest()[:8]
    wm_filename = f"final_{run_id}_wm_{config_hash}.mp4"
    wm_path = os.path.join(_OUTPUT_BASE, wm_filename)

    # 缓存命中：直接返回
    if not (os.path.exists(wm_path) and os.path.getsize(wm_path) > 0):
        # 实时加水印
        wm_path = await apply_video_watermark(
            video_path=final_path,
            config=wm_config,
            output_path=wm_path,
        )
        if wm_path == final_path:
            # 水印失败，回退到原文件
            wm_path = final_path

    download_name = f"pipeline_{run_id}.mp4"
    return FileResponse(
        path=wm_path,
        media_type="video/mp4",
        filename=download_name,
    )
```

- [ ] **Step 5: 修改保存字幕路由，同步生成 VTT**

定位 `POST /pipeline/runs/{run_id}/subtitles` 路由的 service 调用（约第 360-380 行），在 `save_subtitles` 调用后增加 VTT 生成。

由于 `save_subtitles` 在 service 层已经写 SRT 文件，我们需要在 service 层同步生成 VTT。修改 `run_service.save_subtitles` 函数末尾（写 SRT 之后），新增 VTT 写入：

定位 `save_subtitles` 函数中写 SRT 的部分（约第 845-870 行），在写 SRT 文件之后新增：

```python
    # 同步生成 VTT 文件（浏览器 <track> 标签需要 VTT 格式）
    try:
        vtt_filename = f"subtitles_{run_id}.vtt"
        vtt_path = os.path.join(_OUTPUT_BASE, vtt_filename)
        vtt_lines = ["WEBVTT", ""]
        for entry in cleaned:
            start_str = _seconds_to_vtt_time(entry["start"])
            end_str = _seconds_to_vtt_time(entry["end"])
            vtt_lines.append(f"{start_str} --> {end_str}")
            vtt_lines.append(entry["text"])
            vtt_lines.append("")
        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(vtt_lines))
        vtt_url = f"/api/pipeline/outputs/{vtt_filename}"
        # 更新 step.output_data.vtt_url
        old_output["vtt_url"] = vtt_url
    except Exception as e:
        # VTT 生成失败不阻断主流程
        import logging
        logging.getLogger("agnes_platform.pipeline").warning(
            f"save_subtitles VTT 生成失败: {e}"
        )
        vtt_url = old_output.get("vtt_url", "")
```

并在 `save_subtitles` 函数顶部新增辅助函数（如果文件中没有）：

```python
def _seconds_to_vtt_time(seconds: float) -> str:
    """秒数转 VTT 时间格式 HH:MM:SS.mmm"""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
```

更新 `save_subtitles` 返回值，加 `vtt_url`：

```python
    return {
        "srt_url": old_output.get("srt_url", ""),
        "vtt_url": vtt_url,
        "subtitles": cleaned,
    }
```

- [ ] **Step 6: 修改 get_pipeline_output 路由，白名单加 .vtt**

定位 `get_pipeline_output` 路由（约第 769 行），修改 `allowed_exts` 和 `mime_map`：

```python
    # 限制允许的扩展名（白名单）
    allowed_exts = {".mp4", ".mp3", ".wav", ".m4a", ".srt", ".vtt"}  # 新增 .vtt
    ext = os.path.splitext(filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

    file_path = os.path.join(_PIPELINE_OUTPUT_DIR, filename)
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    # 根据扩展名设置 MIME 类型
    mime_map = {
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".srt": "application/x-subrip",
        ".vtt": "text/vtt",  # 新增
    }
```

---

## Task 7：前端 - API 层新增 recompose / download 接口

**Files:**
- Modify: `frontend/src/api/pipeline.ts`

- [ ] **Step 1: 在 pipeline.ts 末尾新增 recomposeVideo 和 downloadRunVideo**

在文件末尾新增：

```typescript
// =====================================================
// 字幕重新烧录 / 视频下载
// =====================================================

/** 字幕样式配置 */
export interface SubtitleStyle {
  font_size?: number
  font_color?: string
  box_color?: string
  box_opacity?: number
  position?: 'top' | 'center' | 'bottom'
  margin?: number
}

/** 重新烧录请求 */
export interface RecomposeRequest {
  subtitles?: SubtitleEntry[]
  subtitle_style?: SubtitleStyle
}

/** 重新烧录响应 */
export interface RecomposeResult {
  message: string
  data: {
    final_video_url: string
    srt_url: string
    vtt_url: string
    subtitles: SubtitleEntry[]
    duration_seconds: number
    segments_count: number
  }
}

/**
 * 重新烧录字幕到视频（耗时操作，前端应显示 loading）
 */
export function recomposeVideo(
  runId: number,
  payload: RecomposeRequest
): Promise<RecomposeResult> {
  return client.post(`/api/pipeline/runs/${runId}/recompose`, payload)
}

/**
 * 构造下载视频 URL（带水印参数）
 *
 * 浏览器直接访问此 URL 触发下载（后端设置 Content-Disposition: attachment）
 */
export function buildDownloadUrl(runId: number, withWatermark: boolean = true): string {
  const watermark = withWatermark ? 1 : 0
  return `/api/pipeline/runs/${runId}/download?watermark=${watermark}`
}
```

---

## Task 8：前端 - FinalVideoPlayer 改用 downloadRunVideo

**Files:**
- Modify: `frontend/src/components/pipeline/FinalVideoPlayer.vue`

- [ ] **Step 1: 修改 handleDownload 函数，使用 buildDownloadUrl**

定位 FinalVideoPlayer.vue 第 167-178 行的 `handleDownload` 函数，替换为：

```typescript
// 下载处理：优先用传入的 downloadUrl（带水印路由），否则用 src
function handleDownload() {
  emit('download')
  // 优先用父组件传入的 downloadUrl（应该是 buildDownloadUrl 构造的带水印 URL）
  // 否则回退到 src（静态文件直链）
  const url = props.downloadUrl || props.src
  if (!url) return
  // 用 window.open 触发下载（后端已设 Content-Disposition: attachment）
  // 对带水印路由返回 attachment，会直接下载；对静态文件 URL 也兼容
  window.open(url, '_blank')
}
```

注意：`<track>` 标签加载 .vtt 是父组件传 `subtitleUrl` prop 的事，FinalVideoPlayer 本身无需改动 subtitleUrl 用法——只要父组件传 .vtt URL 即可。本任务只改下载逻辑。

---

## Task 9：前端 - SubtitleEditor 新增字幕样式面板 + recompose 触发

**Files:**
- Modify: `frontend/src/components/pipeline/SubtitleEditor.vue`

- [ ] **Step 1: 在 SubtitleEditor.vue 顶部 import 区新增依赖**

定位 import 区（约第 130 行附近），新增：

```typescript
import { recomposeVideo, type SubtitleStyle, type SubtitleEntry } from '@/api/pipeline'
```

确认 `ElCollapse, ElCollapseItem, ElInputNumber, ElColorPicker, ElSlider, ElRadioGroup, ElRadioButton` 已从 element-plus 导入。若没有，添加到现有 element-plus import 中。

- [ ] **Step 2: 新增字幕样式响应式状态**

在 `subtitles`、`originalSubtitles` 等响应式状态之后（约第 145 行），新增：

```typescript
// ================ 字幕样式配置 ================
const defaultStyle: SubtitleStyle = {
  font_size: 36,
  font_color: 'FFFFFF',
  box_color: '000000',
  box_opacity: 0.5,
  position: 'bottom',
  margin: 40,
}
const subtitleStyle = ref<SubtitleStyle>({ ...defaultStyle })

// 重新烧录状态
const recomposing = ref(false)
const recomposeProgress = ref(0)
```

- [ ] **Step 3: 在 template 中新增字幕样式折叠面板**

定位 template 中字幕列表之后、保存按钮之前（约第 30 行附近），新增：

```vue
      <!-- 字幕样式配置（折叠面板） -->
      <el-collapse v-model="styleCollapse" class="style-collapse">
        <el-collapse-item :title="t('subtitleEditor.styleSettings')" name="style">
          <el-form label-width="100px" size="small">
            <el-form-item :label="t('subtitleEditor.fontSize')">
              <el-input-number
                v-model="subtitleStyle.font_size"
                :min="12"
                :max="120"
                :step="2"
              />
            </el-form-item>
            <el-form-item :label="t('subtitleEditor.fontColor')">
              <el-color-picker v-model="subtitleStyle.font_color" show-alpha />
            </el-form-item>
            <el-form-item :label="t('subtitleEditor.boxColor')">
              <el-color-picker v-model="subtitleStyle.box_color" show-alpha />
            </el-form-item>
            <el-form-item :label="t('subtitleEditor.boxOpacity')">
              <el-slider
                v-model="subtitleStyle.box_opacity"
                :min="0"
                :max="1"
                :step="0.1"
                show-input
              />
            </el-form-item>
            <el-form-item :label="t('subtitleEditor.position')">
              <el-radio-group v-model="subtitleStyle.position">
                <el-radio-button value="top">{{ t('subtitleEditor.positionTop') }}</el-radio-button>
                <el-radio-button value="center">{{ t('subtitleEditor.positionCenter') }}</el-radio-button>
                <el-radio-button value="bottom">{{ t('subtitleEditor.positionBottom') }}</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item :label="t('subtitleEditor.margin')">
              <el-input-number
                v-model="subtitleStyle.margin"
                :min="0"
                :max="500"
                :step="10"
              />
            </el-form-item>
          </el-form>
        </el-collapse-item>
      </el-collapse>
```

并在 script setup 中新增 `styleCollapse` ref：

```typescript
const styleCollapse = ref<string[]>([])  // 默认折叠
```

注意：`el-color-picker` 返回 `rgba(...)` 字符串，需要转 hex。如果 color-picker 与 hex 不兼容，改用普通 input + 正则校验。为简化，先保留 color-picker，在提交时转 hex：

```typescript
// 辅助：rgba/hex 转 6 位 hex
function colorToHex(color: string | undefined): string {
  if (!color) return 'FFFFFF'
  // 已是 #RRGGBB 或 RRGGBB
  const cleaned = color.replace('#', '').toUpperCase()
  if (/^[0-9A-F]{6}$/.test(cleaned)) return cleaned
  if (/^[0-9A-F]{3}$/.test(cleaned)) {
    return cleaned.split('').map(c => c + c).join('')
  }
  // rgba(r,g,b,a) 格式
  const m = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
  if (m) {
    return [m[1], m[2], m[3]].map(n => parseInt(n).toString(16).padStart(2, '0')).join('').toUpperCase()
  }
  return 'FFFFFF'
}
```

- [ ] **Step 4: 修改保存按钮区，新增「保存并重新烧录」按钮**

定位 template 中保存按钮区（约第 35-40 行），替换为：

```vue
      <div class="editor-actions">
        <el-button @click="handleDownloadSrt" size="small">
          {{ t('subtitleEditor.downloadSrt') }}
        </el-button>
        <el-button @click="handleSave" :loading="saving" type="primary" size="small">
          {{ saving ? t('subtitleEditor.saving') : t('subtitleEditor.save') }}
        </el-button>
        <el-button
          @click="handleSaveAndRecompose"
          :loading="recomposing"
          type="success"
          size="small"
        >
          {{ recomposing ? t('subtitleEditor.recomposing') : t('subtitleEditor.saveAndRecompose') }}
        </el-button>
      </div>
      <p v-if="recomposing" class="recompose-tip">
        {{ t('subtitleEditor.recomposeTip') }}
      </p>
```

- [ ] **Step 5: 新增 handleSaveAndRecompose 函数**

在 `handleSave` 函数之后新增：

```typescript
// ================ 保存并重新烧录 ================
async function handleSaveAndRecompose() {
  if (!props.runId) return
  // 先校验字幕
  if (subtitles.value.length === 0) {
    ElMessage.warning(t('subtitleEditor.noSubtitles'))
    return
  }

  recomposing.value = true
  recomposeProgress.value = 0
  try {
    // 1. 先保存字幕
    const styleForRequest: SubtitleStyle = {
      font_size: subtitleStyle.value.font_size,
      font_color: colorToHex(subtitleStyle.value.font_color),
      box_color: colorToHex(subtitleStyle.value.box_color),
      box_opacity: subtitleStyle.value.box_opacity,
      position: subtitleStyle.value.position as 'top' | 'center' | 'bottom',
      margin: subtitleStyle.value.margin,
    }

    // 2. 调 recompose 接口（同步等待，约 30s-2min）
    const result = await recomposeVideo(Number(props.runId), {
      subtitles: subtitles.value,
      subtitle_style: styleForRequest,
    })

    ElMessage.success(t('subtitleEditor.recomposeSuccess'))
    // 通知父组件刷新产物 URL
    emit('saved', {
      srt_url: result.data.srt_url,
      subtitles: result.data.subtitles,
      // 额外字段，父组件可识别为 recompose 完成
      recomposed: true,
      final_video_url: result.data.final_video_url,
      vtt_url: result.data.vtt_url,
    } as any)
  } catch (e: any) {
    ElMessage.error(e?.message || t('subtitleEditor.recomposeFailed'))
  } finally {
    recomposing.value = false
  }
}
```

修改 `emit` 定义，允许额外字段：

```typescript
const emit = defineEmits<{
  (e: 'saved', result: { srt_url: string; subtitles: SubtitleEntry[]; recomposed?: boolean; final_video_url?: string; vtt_url?: string }): void
}>()
```

- [ ] **Step 6: 新增 .recompose-tip 样式**

在 `<style scoped>` 末尾新增：

```css
.recompose-tip {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-color-warning);
  text-align: center;
}
.style-collapse {
  margin: 12px 0;
}
.editor-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 12px;
}
```

---

## Task 10：前端 - PipelineResultView 集成 vtt + recompose + 下载

**Files:**
- Modify: `frontend/src/views/PipelineResultView.vue`

- [ ] **Step 1: 新增 finalVttUrl 计算属性**

定位 PipelineResultView.vue 第 312-322 行（`finalSrtUrl` 计算属性附近），在 `finalSrtUrl` 之后新增：

```typescript
// 最终视频的 VTT 字幕 URL（浏览器 <track> 标签需要 VTT 格式，非 SRT）
const finalVttUrl = computed(() => {
  const vtt = finalCompositeOutput.value?.vtt_url || ''
  if (!vtt) return ''
  // 加时间戳防缓存（recompose 后会更新）
  return vtt
})
```

- [ ] **Step 2: 修改 FinalVideoPlayer 调用，传 vtt URL + 下载 URL**

定位 template 中 FinalVideoPlayer 调用（约第 108-115 行），修改：

```vue
      <FinalVideoPlayer
        ref="finalPlayerRef"
        :src="finalVideoUrl"
        :subtitle-url="finalVttUrl"
        :duration="finalDuration"
        :segments-count="finalSegmentsCount"
        :download-url="downloadUrl"
        @download="handleDownload"
        @time-update="handleTimeUpdate"
      />
```

新增 `downloadUrl` 计算属性（在 finalVttUrl 之后）：

```typescript
// 下载 URL（走带水印路由）
const downloadUrl = computed(() => {
  if (!run.value) return ''
  return buildDownloadUrl(Number(runId.value), true)
})
```

并在 import 区新增：

```typescript
import { buildDownloadUrl } from '@/api/pipeline'
```

- [ ] **Step 3: 修改 handleDownload 函数**

定位 handleDownload 函数（约第 525-534 行），简化为：

```typescript
function handleDownload() {
  // FinalVideoPlayer 内部已用 window.open 触发下载
  // 这里只做日志/统计
  console.log('[PipelineResult] download triggered, runId=', runId.value)
}
```

注意：FinalVideoPlayer 的 handleDownload 已改为 `window.open(downloadUrl)`，这里父组件的 handleDownload 主要做副作用（如埋点），实际下载由 FinalVideoPlayer 完成。

- [ ] **Step 4: 修改 SubtitleEditor 的 @saved 事件处理，处理 recompose 结果**

定位 SubtitleEditor 的 `@saved` 事件处理函数（搜索 `onSubtitlesSaved` 或类似），修改以处理 recompose 场景：

```typescript
// 字幕保存/重新烧录完成回调
async function onSubtitlesSaved(result: {
  srt_url: string
  subtitles: any[]
  recomposed?: boolean
  final_video_url?: string
  vtt_url?: string
}) {
  // 更新本地字幕数据
  if (finalCompositeOutput.value) {
    finalCompositeOutput.value.subtitles = result.subtitles
    finalCompositeOutput.value.srt_url = result.srt_url
    if (result.vtt_url) {
      finalCompositeOutput.value.vtt_url = result.vtt_url
    }
  }

  if (result.recomposed && result.final_video_url) {
    // recompose 场景：更新 final_video_url，触发播放器重新加载
    // 由于 finalVideoUrl 是 computed，依赖 finalCompositeOutput.final_video_url
    // 需要更新 output_data 中的 final_video_url
    if (finalCompositeOutput.value) {
      finalCompositeOutput.value.final_video_url = result.final_video_url
    }
    ElMessage.success(t('pipelineResult.recomposeSuccess'))
  } else {
    ElMessage.success(t('pipelineResult.subtitlesSaved'))
  }
}
```

如果原本没有 `onSubtitlesSaved` 函数，需要在 setup 中搜索 `@saved` 绑定并补上。

---

## Task 11：i18n 文案补充

**Files:**
- Modify: `frontend/src/i18n/zh-CN.ts`
- Modify: `frontend/src/i18n/en-US.ts`

- [ ] **Step 1: 在 zh-CN.ts 的 pipelineResult 区块新增**

定位 `pipelineResult:` 区块，新增以下 key：

```typescript
  pipelineResult: {
    // ... 现有 key
    recompose: '重新烧录',
    recomposing: '重新烧录中...',
    recomposeSuccess: '重新烧录完成',
    recomposeFailed: '重新烧录失败',
    subtitlesSaved: '字幕已保存',
    downloadWithWatermark: '下载（带水印）',
  },
```

- [ ] **Step 2: 在 zh-CN.ts 的 subtitleEditor 区块新增**

```typescript
  subtitleEditor: {
    // ... 现有 key
    styleSettings: '字幕样式',
    fontSize: '字号',
    fontColor: '字体颜色',
    boxColor: '底框颜色',
    boxOpacity: '底框不透明度',
    position: '位置',
    positionTop: '顶部',
    positionCenter: '居中',
    positionBottom: '底部',
    margin: '边距',
    saveAndRecompose: '保存并重新烧录',
    recomposing: '重新烧录中...',
    recomposeTip: '重新烧录会耗时约 1-2 分钟，请勿离开页面',
    recomposeSuccess: '重新烧录完成，视频已更新',
    recomposeFailed: '重新烧录失败',
    noSubtitles: '字幕列表为空',
  },
```

- [ ] **Step 3: 在 en-US.ts 同步新增对应英文**

```typescript
  pipelineResult: {
    // ... existing keys
    recompose: 'Recompose',
    recomposing: 'Recomposing...',
    recomposeSuccess: 'Recompose completed',
    recomposeFailed: 'Recompose failed',
    subtitlesSaved: 'Subtitles saved',
    downloadWithWatermark: 'Download (with watermark)',
  },
  subtitleEditor: {
    // ... existing keys
    styleSettings: 'Subtitle Style',
    fontSize: 'Font Size',
    fontColor: 'Font Color',
    boxColor: 'Box Color',
    boxOpacity: 'Box Opacity',
    position: 'Position',
    positionTop: 'Top',
    positionCenter: 'Center',
    positionBottom: 'Bottom',
    margin: 'Margin',
    saveAndRecompose: 'Save & Recompose',
    recomposing: 'Recomposing...',
    recomposeTip: 'Recompose takes about 1-2 minutes, please do not leave the page',
    recomposeSuccess: 'Recompose completed, video updated',
    recomposeFailed: 'Recompose failed',
    noSubtitles: 'Subtitles list is empty',
  },
```

---

## Task 12：端到端联调验证

**Files:** 无代码改动，仅手动验证

- [ ] **Step 1: 启动后端服务**

```bash
cd backend && python -m uvicorn app.main:app --reload
```

确认无启动错误。

- [ ] **Step 2: 启动前端开发服务器**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: 验证 WebVTT 字幕显示**

1. 打开一个已完成的漫剧流水线结果页
2. 检查 FinalVideoPlayer 是否加载 .vtt 字幕（F12 Network 面板看到 .vtt 请求 + 200 响应）
3. 播放视频，确认字幕在画面上显示

- [ ] **Step 4: 验证字幕样式编辑**

1. 打开 SubtitleEditor，展开「字幕样式」面板
2. 修改字号（如 36 → 48）、位置（bottom → top）
3. 点击「保存并重新烧录」
4. 等待完成（约 1-2 分钟）
5. 视频自动刷新，确认字幕字号变大、位置在顶部

- [ ] **Step 5: 验证下载带水印**

1. 确认管理员后台已配置水印（force_all=true 或用户 watermark_enabled=true）
2. 点击 FinalVideoPlayer 的下载按钮
3. 浏览器下载 mp4 文件
4. 打开下载的 mp4，确认含水印

- [ ] **Step 6: 验证未启用水印时下载**

1. 关闭水印配置（force_all=false, 用户 watermark_enabled=false）
2. 点击下载
3. 浏览器下载 mp4，确认无水印（走 302 重定向到静态文件）

---

## Self-Review 检查

**Spec 覆盖：**
- ✅ 4.1 WebVTT 转换 → Task 1 + Task 6 Step 5/6 + Task 10 Step 1/2
- ✅ 4.2 字幕样式可配置 → Task 2 + Task 9
- ✅ 4.3 下载带水印 → Task 4 + Task 6 Step 4 + Task 8 + Task 10 Step 2/3
- ✅ 4.4 字幕重新烧录 → Task 3 + Task 5 + Task 6 Step 3 + Task 7 + Task 9 Step 5 + Task 10 Step 4
- ✅ 4.5 错误处理 → 各 Task 内的 try/except + 回退逻辑
- ✅ 7. i18n 文案 → Task 11
- ✅ 9. 实施顺序 → Task 1-12 按依赖顺序排列

**类型一致性：**
- `SubtitleStyle` 在 schema（Task 6 Step 1）和 frontend types（Task 7）字段名一致
- `recompose_video` 服务签名（Task 5）与路由调用（Task 6 Step 3）一致
- `recompose_pipeline_video` 函数签名（Task 3 Step 2）与 service 调用（Task 5）一致
- `RecomposeResult.data` 字段与 `recompose_video` 返回值一致

**Placeholder 扫描：** 无 TBD/TODO，所有代码块完整。

---

## 执行选择

Plan 已保存到 `docs/superpowers/plans/2026-06-27-pipeline-phase2-completion.md`。两种执行方式：

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，任务间 review，迭代快
2. **Inline Execution** — 在当前会话顺序执行，带检查点

**选哪种？**
