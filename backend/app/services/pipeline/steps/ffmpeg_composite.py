# =====================================================
# FFmpeg 合成步骤执行器
# 功能：
#   1. 将上游 video_batch 产出的多个分镜视频拼接为最终成片
#   2. 可选：烧录字幕（从剧本 parsed_result.scenes 提取对白/描述）
#   3. 可选：混入 BGM 背景音乐（amix）
#   4. 可选：替换原音轨为配音音轨（来自 tts_generate 步骤）
#   5. 生成独立 SRT 字幕文件（时间戳基于实际片段时长累积）
#
# 输出：
#   {
#     "final_video_url": "/api/pipeline/outputs/final_xxx.mp4",  # 前端可直接访问的 URL
#     "final_video_path": "/tmp/.../final_xxx.mp4",              # 本地文件路径
#     "srt_url": "/api/pipeline/outputs/subtitles_xxx.srt",      # 独立 SRT 字幕文件 URL
#     "segments_count": 8,
#     "duration_seconds": 40.0,
#     "with_subtitle": true,
#     "with_audio": false,
#     "with_bgm": false,
#     "subtitles": [{"index":0, "start":0.0, "end":5.2, "text":"..."}, ...]  # 字幕条目（供前端预览）
#   }
# =====================================================

import asyncio
import logging
import os
import tempfile
import hashlib
from typing import Dict, Any, List, Optional

import httpx

from app.core.database import new_async_session
from app.services.pipeline.steps import register_step_executor
from app.services.pipeline.steps.base import BaseStepExecutor
from app.services.pipeline import integration

logger = logging.getLogger("agnes_platform.pipeline")

# 最终视频输出目录（持久化，通过路由对外提供访问）
# 放在项目根目录 data/pipeline_outputs/ 下，便于通过 FileResponse 代理
_OUTPUT_BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
    "data", "pipeline_outputs",
)
os.makedirs(_OUTPUT_BASE, exist_ok=True)


@register_step_executor
class FFmpegCompositeExecutor(BaseStepExecutor):
    """
    FFmpeg 合成步骤执行器

    将上游 video_batch 产出的多个分镜视频合并为最终成片。
    支持字幕烧录、BGM 混合、配音替换（依赖 tts_generate 步骤产出）。
    """

    step_type = "ffmpeg_composite"

    # 类级别缓存：drawtext 滤镜可用性（None=未检测）
    _drawtext_available: Optional[bool] = None

    @classmethod
    async def _check_drawtext_available(cls) -> bool:
        """检测 ffmpeg 是否编译了 drawtext 滤镜（依赖 libfreetype）。结果缓存到类属性。"""
        if cls._drawtext_available is not None:
            return cls._drawtext_available
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-filters",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            cls._drawtext_available = b"drawtext" in stdout
        except Exception:
            cls._drawtext_available = False
        if not cls._drawtext_available:
            logger.warning(
                "[FFmpeg合成] drawtext 滤镜不可用（ffmpeg 未启用 libfreetype），"
                "字幕将仅生成外挂 SRT 文件不烧录。修复: brew reinstall ffmpeg --with-libfreetype (macOS)"
            )
        return cls._drawtext_available

    async def validate(self) -> None:
        """验证输入：必须指定 from_step，且 ffmpeg/ffprobe 可用"""
        config = self.config.get("config", {})
        from_step = config.get("from_step")
        if not from_step:
            raise ValueError("ffmpeg_composite 必须指定 from_step（上游 video_batch 步骤）")

        # 检查 ffmpeg 是否可用
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if proc.returncode != 0:
                raise RuntimeError("ffmpeg 不可用")
        except Exception as e:
            raise ValueError(f"ffmpeg 不可用: {e}")

    async def execute(self) -> Dict[str, Any]:
        """执行视频合成"""
        config = self.config.get("config", {})
        from_step = config.get("from_step")
        audio_step = config.get("audio_from_step")  # 可选：tts_generate 步骤 key
        bgm_url = config.get("bgm_url")  # 可选：BGM 音乐 URL
        with_subtitle = config.get("with_subtitle", True)
        with_bgm = config.get("with_bgm", False)
        bgm_volume = config.get("bgm_volume", 0.3)  # BGM 音量（0~1）

        # 1. 获取上游视频列表（按 index 排序）
        step_output = self.context.steps_output.get(from_step, {})
        videos = step_output.get("videos", [])
        if not videos:
            raise ValueError(f"上游步骤 '{from_step}' 没有视频产出")

        videos = sorted(videos, key=lambda v: v.get("index", 0))
        self._total = len(videos)
        logger.info(f"[FFmpeg合成] 开始合成 {len(videos)} 个视频片段")

        # 2. 提取字幕文本（可选）
        subtitles: List[str] = []
        if with_subtitle:
            subtitles = self._extract_subtitles(config)

        # 3. 获取配音音频（可选，来自 tts_generate 步骤）
        audios: List[Dict[str, Any]] = []
        if audio_step:
            audio_output = self.context.steps_output.get(audio_step, {})
            audios = audio_output.get("audios", [])

        # 4. 下载所有视频片段到临时目录
        self._progress_phase = "downloading"
        self._completed_count = 0
        video_paths = await self._download_all_videos(videos)

        # 5. 对每个视频烧录字幕 + 混入配音（如果有）
        # 同时获取每个片段的实际时长，用于生成 SRT 时间戳
        self._progress_phase = "composing"
        self._completed_count = 0
        composed_paths: List[str] = []
        segment_durations: List[float] = []  # 每个片段的实际时长（秒）
        for idx, vpath in enumerate(video_paths):
            if not vpath:
                logger.warning(f"[FFmpeg合成] 跳过空视频 #{idx}")
                continue
            subtitle_text = subtitles[idx] if idx < len(subtitles) else ""
            audio_path = audios[idx].get("audio_path") if idx < len(audios) else None
            composed = await self._compose_single(
                vpath, idx, subtitle_text, audio_path
            )
            composed_paths.append(composed)
            # 获取合成后片段的实际时长（关键：用实际时长而非配置时长，确保 SRT 与视频对齐）
            seg_duration = await self._get_video_duration(composed)
            segment_durations.append(seg_duration)
            self._completed_count = idx + 1

        if not composed_paths:
            raise ValueError("没有可合成的视频片段（全部下载失败或为空）")

        # 6. 拼接所有视频
        self._progress_phase = "concatenating"
        if len(composed_paths) == 1:
            # 只有一个片段，直接作为最终视频
            final_path = composed_paths[0]
        else:
            final_path = await self._concat_videos(composed_paths)

        # 7. 混入 BGM（如果配置了）
        if with_bgm and bgm_url:
            self._progress_phase = "mixing_bgm"
            final_path = await self._mix_bgm(final_path, bgm_url, bgm_volume)

        # 8. 生成前端可访问的相对 URL + 获取时长
        final_filename = os.path.basename(final_path)
        final_url = f"/api/pipeline/outputs/{final_filename}"
        duration = await self._get_video_duration(final_path)

        logger.info(f"[FFmpeg合成] 完成: {final_path}, 时长={duration}s, URL={final_url}")

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

        # 10. 保存到 generations 表（result_url 存相对 URL，前端可直接访问）
        if self.context.run_id:
            try:
                async with new_async_session() as db:
                    await integration.save_generation_from_step(
                        db=db,
                        run_id=self.context.run_id,
                        step_key=self.step_key,
                        gen_type="video",
                        prompt="最终合成视频",
                        result_url=final_url,
                        model="ffmpeg",
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
                        user_id=self.context.user_id,
                        credits_consumed=0,
                    )
            except Exception as e:
                logger.warning(f"[FFmpeg合成] 保存生成记录失败: {e}")

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
            "subtitles": subtitles_list,  # 字幕条目列表（供前端预览/编辑）
            "segments_count": len(composed_paths),
            "duration_seconds": duration,
            "with_subtitle": with_subtitle,
            "with_audio": bool(audios),
            "with_bgm": with_bgm and bool(bgm_url),
        }

    async def estimate_credits(self) -> int:
        """合成步骤不消耗外部 API 积分"""
        return 2

    async def get_progress(self) -> Dict[str, Any]:
        """返回合成进度（分阶段：下载/合成/拼接/混音）"""
        total = getattr(self, "_total", 0)
        if total == 0:
            return {}
        phase = getattr(self, "_progress_phase", "")
        completed = getattr(self, "_completed_count", 0)

        phase_map = {
            "downloading": (0.0, 0.3, "下载视频片段"),
            "composing": (0.3, 0.7, "烧录字幕/混入配音"),
            "concatenating": (0.7, 0.9, "拼接视频"),
            "mixing_bgm": (0.9, 1.0, "混入背景音乐"),
        }
        if phase not in phase_map:
            return {}
        start, end, text = phase_map[phase]
        if phase in ("downloading", "composing"):
            percent = round(start + (end - start) * (completed / total if total > 0 else 0), 3)
        else:
            percent = end
        return {
            "current": completed if phase in ("downloading", "composing") else total,
            "total": total,
            "percent": percent,
            "phase": phase,
            "phase_text": text,
        }

    # ---------- 内部方法 ----------

    def _extract_subtitles(self, config: Dict[str, Any]) -> List[str]:
        """从剧本步骤的 parsed_result.scenes 中提取字幕文本"""
        script_step = config.get("script_from_step", "")
        if not script_step:
            return []

        script_output = self.context.steps_output.get(script_step, {})
        parsed = script_output.get("parsed_result") or {}
        if not isinstance(parsed, dict):
            return []

        scenes = parsed.get("scenes", []) or []
        subtitles: List[str] = []
        for scene in scenes:
            if not isinstance(scene, dict):
                subtitles.append("")
                continue
            # 优先用对白，没有则用场景描述
            text = scene.get("dialogue") or scene.get("description") or ""
            subtitles.append(text)
        return subtitles

    async def _download_all_videos(self, videos: List[Dict[str, Any]]) -> List[str]:
        """下载所有视频片段到临时目录"""
        temp_dir = tempfile.mkdtemp(prefix="agnes_composite_")
        paths: List[str] = []
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            for idx, video in enumerate(videos):
                url = video.get("video_url") or video.get("url", "")
                if not url:
                    paths.append("")
                    continue
                try:
                    out_path = os.path.join(temp_dir, f"seg_{idx:03d}.mp4")
                    resp = await client.get(url, headers={"User-Agent": "Agnes-Platform"})
                    if resp.status_code == 200:
                        with open(out_path, "wb") as f:
                            f.write(resp.content)
                        paths.append(out_path)
                        logger.debug(f"[FFmpeg合成] 下载视频 #{idx} 成功: {len(resp.content)} bytes")
                    else:
                        logger.warning(f"[FFmpeg合成] 下载视频 #{idx} 失败: HTTP {resp.status_code}")
                        paths.append("")
                except Exception as e:
                    logger.warning(f"[FFmpeg合成] 下载视频 #{idx} 异常: {e}")
                    paths.append("")
                self._completed_count = idx + 1
        return paths

    async def _compose_single(
        self,
        video_path: str,
        index: int,
        subtitle_text: str,
        audio_path: Optional[str],
    ) -> str:
        """
        对单个视频烧录字幕 + 混入配音（如果有）

        - 如果有字幕且需要烧录，用 drawtext 滤镜
        - 如果有配音音频，替换原音轨
        - 如果都没有，直接返回原视频路径（跳过重编码）
        """
        has_subtitle = bool(subtitle_text.strip())
        has_audio = bool(audio_path)

        # 没有字幕也没有配音，跳过重编码
        if not has_subtitle and not has_audio:
            return video_path

        # 检测 drawtext 滤镜可用性（只检测一次，结果缓存）
        if has_subtitle and not await self._check_drawtext_available():
            # drawtext 不可用：跳过字幕烧录，保留外挂 SRT
            if not has_audio:
                return video_path
            has_subtitle = False  # 降至仅配音模式

        out_path = video_path.replace(".mp4", f"_composed_{index:03d}.mp4")

        # 构建视频滤镜（drawtext 烧录字幕，支持样式配置）
        vf_filters: List[str] = []
        if has_subtitle:
            # 从 step config 读取字幕样式（recompose 时会注入更新后的样式）
            style = self._resolve_subtitle_style(self.config.get("config", {}))
            vf_filters.append(self._build_drawtext_filter(style, subtitle_text))

        vf_arg = ",".join(vf_filters) if vf_filters else None

        # 构建 ffmpeg 命令
        cmd: List[str] = ["ffmpeg", "-y", "-i", video_path]
        if has_audio:
            cmd.extend(["-i", audio_path])

        if vf_arg:
            cmd.extend(["-vf", vf_arg])

        if has_audio:
            # 用配音替换原音轨：视频来自输入0，音频来自输入1
            cmd.extend(["-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-c:a", "aac"])
        else:
            # 保留原音轨，只烧录字幕
            cmd.extend(["-c:v", "libx264", "-c:a", "aac"])

        cmd.extend(["-preset", "fast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
            if proc.returncode != 0:
                err_text = stderr.decode(errors="ignore")
                # 完整 stderr 用 DEBUG 级别记录，方便排查
                logger.debug(f"[FFmpeg合成] 单片 #{index} 完整 stderr:\n{err_text}")
                # 优先提取包含关键错误的行，否则取末尾 300 字符
                err_keywords = ["Error", "No such filter", "Invalid", "No such file",
                                "Unrecognized option", "Permission denied", "failed"]
                err_lines = [line for line in err_text.split("\n")
                             if any(kw in line for kw in err_keywords)]
                if err_lines:
                    err_summary = " | ".join(err_lines[:5])
                else:
                    err_summary = err_text[-300:] if len(err_text) > 300 else err_text
                logger.warning(
                    f"[FFmpeg合成] 单片合成失败 #{index}: {err_summary}"
                )
                # 失败时用原视频
                return video_path
            return out_path
        except asyncio.TimeoutError:
            logger.warning(f"[FFmpeg合成] 单片合成超时 #{index}")
            return video_path
        except Exception as e:
            logger.warning(f"[FFmpeg合成] 单片合成异常 #{index}: {e}")
            return video_path

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

    def _escape_drawtext_text(self, text: str) -> str:
        """转义 drawtext 文本中的特殊字符"""
        text = text.replace("\\", "\\\\")
        text = text.replace(":", "\\:")
        text = text.replace("'", "\\'")
        text = text.replace("%", "\\%")
        # drawtext 不支持换行，替换为空格
        text = text.replace("\n", " ").replace("\r", " ")
        return text

    def _find_font(self) -> str:
        """查找系统中可用的中文字体文件"""
        candidates = [
            # macOS
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            # Linux Noto CJK
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
            # Linux 文泉驿
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
            # Linux fallback（不含中文但能避免 drawtext 报错）
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for f in candidates:
            if os.path.exists(f):
                return f
        return ""

    async def _concat_videos(self, video_paths: List[str]) -> str:
        """
        拼接多个视频（concat demuxer）

        优先用 -c copy（无重编码，最快）；
        如果失败（编码/分辨率不一致），fallback 到重编码。
        """
        valid_paths = [p for p in video_paths if p and os.path.exists(p)]
        if not valid_paths:
            raise ValueError("没有可拼接的视频文件")

        # 创建 concat list 文件
        run_id = self.context.run_id or "tmp"
        list_path = os.path.join(_OUTPUT_BASE, f"concat_{run_id}.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for p in valid_paths:
                # concat demuxer 要求单引号转义
                escaped = p.replace("'", "\\'")
                f.write(f"file '{escaped}'\n")

        final_path = os.path.join(_OUTPUT_BASE, f"final_{run_id}.mp4")

        # 第一阶段：尝试 -c copy（最快）
        copy_ok = await self._try_concat_copy(list_path, final_path)
        if copy_ok:
            self._cleanup_file(list_path)
            return final_path

        # 第二阶段：fallback 到重编码
        logger.warning("[FFmpeg合成] concat copy 失败，改用重编码模式")
        reencode_ok = await self._try_concat_reencode(list_path, final_path)
        self._cleanup_file(list_path)
        if not reencode_ok:
            raise RuntimeError("视频拼接失败（copy 和 reencode 均失败）")
        return final_path

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

    async def _try_concat_copy(self, list_path: str, output_path: str) -> bool:
        """尝试用 -c copy 拼接（无重编码）"""
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c", "copy",
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
                logger.debug(
                    f"[FFmpeg合成] concat copy 失败: {stderr.decode(errors='ignore')[:200]}"
                )
                return False
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception as e:
            logger.debug(f"[FFmpeg合成] concat copy 异常: {e}")
            return False

    async def _try_concat_reencode(self, list_path: str, output_path: str) -> bool:
        """重编码拼接（处理编码/分辨率不一致的情况）"""
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=600.0)
            if proc.returncode != 0:
                logger.warning(
                    f"[FFmpeg合成] concat reencode 失败: {stderr.decode(errors='ignore')[:300]}"
                )
                return False
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception as e:
            logger.warning(f"[FFmpeg合成] concat reencode 异常: {e}")
            return False

    async def _mix_bgm(
        self, video_path: str, bgm_url: str, bgm_volume: float
    ) -> str:
        """混入 BGM 背景音乐（原音轨保留，BGM 作为第二音轨混合）"""
        # 下载 BGM（带缓存，避免重复下载）
        bgm_hash = hashlib.md5(bgm_url.encode()).hexdigest()[:8]
        bgm_path = os.path.join(_OUTPUT_BASE, f"bgm_{bgm_hash}.mp3")
        if not os.path.exists(bgm_path):
            try:
                async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                    resp = await client.get(bgm_url, headers={"User-Agent": "Agnes-Platform"})
                    if resp.status_code == 200:
                        with open(bgm_path, "wb") as f:
                            f.write(resp.content)
                    else:
                        logger.warning(f"[FFmpeg合成] 下载 BGM 失败: HTTP {resp.status_code}")
                        return video_path
            except Exception as e:
                logger.warning(f"[FFmpeg合成] 下载 BGM 异常: {e}")
                return video_path

        out_path = video_path.replace(".mp4", "_bgm.mp4")
        # BGM 音量降低，与原音轨混合；原音轨为主（duration=first 以原视频为准）
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", bgm_path,
            "-filter_complex",
            f"[1:a]volume={bgm_volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            "-movflags", "+faststart",
            out_path,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
            if proc.returncode != 0:
                logger.warning(
                    f"[FFmpeg合成] BGM 混入失败: {stderr.decode(errors='ignore')[:200]}"
                )
                return video_path
            return out_path
        except Exception as e:
            logger.warning(f"[FFmpeg合成] BGM 混入异常: {e}")
            return video_path

    async def _get_video_duration(self, video_path: str) -> float:
        """用 ffprobe 获取视频时长（秒）"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            return float(stdout.decode().strip())
        except Exception:
            return 0.0

    def _cleanup_file(self, path: str) -> None:
        """清理临时文件"""
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    async def _generate_srt_file(
        self,
        subtitles: List[str],
        segment_durations: List[float],
    ) -> tuple:
        """
        生成独立 SRT 字幕文件

        时间戳基于每个片段的实际时长累积计算，确保与最终视频对齐。

        Args:
            subtitles: 每个场景的字幕文本列表
            segment_durations: 每个片段的实际时长（秒），来自 ffprobe

        Returns:
            (srt_url, subtitles_list)
            - srt_url: 前端可访问的 SRT 文件 URL（如 /api/pipeline/outputs/subtitles_xxx.srt）
            - subtitles_list: 字幕条目列表，供前端预览/编辑
              [{"index":0, "start":0.0, "end":5.2, "text":"..."}, ...]
        """
        # 过滤掉空字幕，只保留有内容的条目
        entries: List[Dict[str, Any]] = []
        current_time = 0.0

        for idx, text in enumerate(subtitles):
            # 获取该片段时长（优先用实际测量值，否则用默认 5 秒）
            duration = (
                segment_durations[idx]
                if idx < len(segment_durations) and segment_durations[idx] > 0
                else 5.0
            )
            start = current_time
            end = current_time + duration
            current_time = end

            # 跳过空文本（无对白的场景不生成字幕条目）
            if not text or not text.strip():
                continue

            entries.append({
                "index": len(entries),  # SRT 序号从 0 开始连续递增
                "scene_index": idx,  # 对应原场景序号
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text.strip(),
            })

        if not entries:
            return "", []

        # 生成 SRT 文件内容
        srt_content = self._format_srt(entries)
        run_id = self.context.run_id or "tmp"
        srt_filename = f"subtitles_{run_id}.srt"
        srt_path = os.path.join(_OUTPUT_BASE, srt_filename)

        try:
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
            srt_url = f"/api/pipeline/outputs/{srt_filename}"
            logger.info(
                f"[FFmpeg合成] SRT 字幕生成完成: {srt_path}, 共 {len(entries)} 条"
            )
            return srt_url, entries
        except Exception as e:
            logger.warning(f"[FFmpeg合成] SRT 字幕生成失败: {e}")
            return "", entries

    def _format_srt(self, entries: List[Dict[str, Any]]) -> str:
        """
        格式化为标准 SRT 文件内容

        SRT 格式：
            1
            00:00:00,000 --> 00:00:05,200
            字幕文本

            2
            00:00:05,200 --> 00:00:10,500
            字幕文本
        """
        lines: List[str] = []
        for i, entry in enumerate(entries, start=1):
            # SRT 序号从 1 开始
            lines.append(str(i))
            # 时间戳格式: HH:MM:SS,mmm
            start_str = self._seconds_to_srt_time(entry["start"])
            end_str = self._seconds_to_srt_time(entry["end"])
            lines.append(f"{start_str} --> {end_str}")
            # 字幕文本（支持多行）
            lines.append(entry["text"])
            # 空行分隔
            lines.append("")

        return "\n".join(lines)

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

    def _seconds_to_srt_time(self, seconds: float) -> str:
        """将秒数转换为 SRT 时间格式 HH:MM:SS,mmm"""
        if seconds < 0:
            seconds = 0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


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
        context=context,
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
