# =====================================================
# 媒体合成公共层 — ffmpeg 命令构造与执行（从 merge_service 抽出，只挪不改）
#
# 供两条链路复用:
#   - 项目制高级合成（merge_service）
#   - 无限画布合成（canvas_media_service）
#
# 内容: ffmpeg 子进程执行 / 流式下载 / 分辨率与时长探测 /
#       字幕滤镜能力检测（libass + drawtext）/ 视频归一化 /
#       drawtext 字幕滤镜链构造 / 最终合成（视频+音频+字幕）
# =====================================================

import asyncio
import logging
import os
import re
from typing import Optional, List, Any

logger = logging.getLogger("agnes_platform.media_compose")

# 缓存 ffmpeg subtitles 滤镜可用性（避免每次合成重复检测）
_subtitles_filter_cache: Optional[bool] = None

# drawtext 滤镜可用性缓存
_drawtext_filter_cache: Optional[bool] = None


# ffmpeg -filters 输出中滤镜条目正则：匹配 "  T. subtitles  V->V  ..." 这类行
# 滤镜名前后有空格，前面可能有标志位（T./S/C/..），后面跟输入输出流规格
_FILTER_LINE_RE = re.compile(r"^\s*[A-Z.]*\s+(\S+)\s+[AVN]->[AVN]", re.MULTILINE)


async def _get_ffmpeg_filter_list() -> set:
    """
    获取 ffmpeg 支持的滤镜名集合，缓存结果。

    解析 `ffmpeg -filters` 输出，每行格式如:
      T.. subtitles       V->V  Render text subtitles onto input video using the libass library
      ...C drawtext        V->V  Draw text on top of video frames using libfreetype
    """
    global _subtitles_filter_cache, _drawtext_filter_cache
    # 同时缓存两个滤镜的检测结果，避免重复执行 ffmpeg -filters
    if _subtitles_filter_cache is not None and _drawtext_filter_cache is not None:
        return set()
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-filters",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        output = stdout.decode("utf-8", errors="ignore")
        names = set(_FILTER_LINE_RE.findall(output))
        if _subtitles_filter_cache is None:
            _subtitles_filter_cache = "subtitles" in names
        if _drawtext_filter_cache is None:
            _drawtext_filter_cache = "drawtext" in names
        return names
    except Exception as e:
        logger.warning("检测 ffmpeg 滤镜列表失败: %s", e)
        _subtitles_filter_cache = False
        _drawtext_filter_cache = False
        return set()


async def check_subtitles_filter_available() -> bool:
    """
    检测当前 ffmpeg 是否支持 subtitles 滤镜（需要编译 libass）。

    结果缓存，避免每次合成重复执行 ffmpeg -filters。
    """
    global _subtitles_filter_cache
    if _subtitles_filter_cache is None:
        await _get_ffmpeg_filter_list()
    if not _subtitles_filter_cache:
        logger.warning(
            "[合成] 当前 ffmpeg 未编译 libass，subtitles 滤镜不可用，"
            "将尝试 drawtext 直烧（无 libass 依赖）。"
        )
    return _subtitles_filter_cache


async def check_drawtext_filter_available() -> bool:
    """
    检测当前 ffmpeg 是否支持 drawtext 滤镜（ffmpeg 内置，通常可用，无需 libass）。

    作为 subtitles 滤镜不可用时的兜底硬烧方案。
    """
    global _drawtext_filter_cache
    if _drawtext_filter_cache is None:
        await _get_ffmpeg_filter_list()
    if not _drawtext_filter_cache:
        logger.warning(
            "[合成] 当前 ffmpeg 不支持 drawtext 滤镜，"
            "字幕只能以软字幕形式嵌入（mov_text）。"
        )
    return _drawtext_filter_cache


def build_drawtext_subtitles_filter(
    clips: List[dict],
    style: dict,
    video_width: int = 1920,
    video_height: int = 1080,
) -> str:
    """
    根据字幕片段列表 + SubtitleStyle 构造 drawtext 滤镜链。

    每条字幕对应一个 drawtext 滤镜，通过 enable='between(t,start,end)' 控制显示时段。
    多个 drawtext 用逗号串联成单个 -vf 滤镜链。

    参数:
    - clips: 字幕片段列表 [{start_time, duration, text}, ...]
    - style: SubtitleStyle dict（font_family / font_size / font_color / outline_color / outline_width / position / margin_vertical）
    - video_width / video_height: 目标视频分辨率（用于位置计算）

    返回:
    - drawtext 滤镜字符串，如 "drawtext=...:enable='between(t,0,2.5)',drawtext=...:enable='between(t,2.5,4.3)'"
    """
    from app.services.watermark_service import _find_video_font, _escape_drawtext_text

    fontfile = _find_video_font()
    font_opt = f":fontfile='{fontfile}'" if fontfile else ""

    font_size = int(style.get("font_size") or 48)
    font_color_hex = (style.get("font_color") or "#FFFFFF").lstrip("#")
    outline_color_hex = (style.get("outline_color") or "#000000").lstrip("#")
    outline_width = int(style.get("outline_width") or 2)
    margin_v = int(style.get("margin_vertical") or 60)
    position = (style.get("position") or "bottom").lower()

    # fontcolor 用 0xRRGGBB 格式
    try:
        fr, fg, fb = int(font_color_hex[0:2], 16), int(font_color_hex[2:4], 16), int(font_color_hex[4:6], 16)
        fontcolor = f"0x{fr:02X}{fg:02X}{fb:02X}"
    except Exception:
        fontcolor = "0xFFFFFF"
    try:
        br, bg, bb = int(outline_color_hex[0:2], 16), int(outline_color_hex[2:4], 16), int(outline_color_hex[4:6], 16)
        bordercolor = f"0x{br:02X}{bg:02X}{bb:02X}"
    except Exception:
        bordercolor = "0x000000"

    # 位置表达式（drawtext 用 w/h/text_w/text_h 表示视频/文字尺寸）
    if position == "top":
        pos = f"x=(w-text_w)/2:y={margin_v}"
    elif position == "center":
        pos = f"x=(w-text_w)/2:y=(h-text_h)/2"
    else:  # bottom（默认）
        pos = f"x=(w-text_w)/2:y=h-text_h-{margin_v}"

    filters: List[str] = []
    for clip in clips:
        text = (clip.get("text") or "").strip()
        if not text:
            continue
        start = float(clip.get("start_time") or 0.0)
        dur = float(clip.get("duration") or 0.0)
        end = start + dur

        escaped = _escape_drawtext_text(text)
        # 每条字幕一个 drawtext 滤镜，用 enable 控制时段
        f = (
            f"drawtext=text='{escaped}'{font_opt}"
            f":fontcolor={fontcolor}:fontsize={font_size}"
            f":borderw={outline_width}:bordercolor={bordercolor}"
            f":{pos}"
            f":enable='between(t,{start:.3f},{end:.3f})'"
        )
        filters.append(f)

    return ",".join(filters)


async def run_ffmpeg(cmd: List[str], timeout: int = 900, error_label: str = "ffmpeg") -> None:
    """运行 ffmpeg 子进程，失败抛出可读错误（含完整 stderr）"""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        # 完整 stderr 输出到日志，便于排查 ffmpeg 错误
        full_err = stderr.decode("utf-8", errors="ignore")
        logger.error("[%s] ffmpeg 命令: %s", error_label, " ".join(cmd))
        logger.error("[%s] ffmpeg 完整 stderr:\n%s", error_label, full_err)
        # 抛出时保留尾部 2000 字符（通常包含真正错误原因）
        raise RuntimeError(f"{error_label} 失败: {full_err[-2000:]}")


def parse_resolution(aspect_ratio: str) -> tuple:
    """从 aspect_ratio 字符串解析 (width, height)，默认 1280x720"""
    # 支持 "16:9" / "9:16" / "1:1" / "1280x720" 等
    if "x" in aspect_ratio:
        parts = aspect_ratio.split("x")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            w, h = int(parts[0]), int(parts[1])
            # 强制 8 倍数（视频编码要求）
            return (w - w % 8, h - h % 8)
    ratio_map = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (720, 720), "4:3": (960, 720)}
    return ratio_map.get(aspect_ratio, (1280, 720))


def video_normalize_only_cmd(src_path: str, out_path: str, width: int, height: int) -> List[str]:
    """构造视频归一化命令（不裁剪，保留完整时长）。

    用于视频拼接前：各片段分辨率/编码/SAR 不一致时直接 concat 会失败或前几秒黑屏，
    因此先用此命令统一格式再 concat。
    """
    return [
        "ffmpeg", "-y",
        "-i", src_path,
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
               f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",  # 拼接阶段不需要音频，最终合成时再混入
        out_path,
    ]


async def stream_download(client: Any, url: str, dest_path: str) -> None:
    """流式下载文件到指定路径，避免大文件一次性读入内存导致 OOM。

    使用 8KB 块写入磁盘，内存占用恒定。
    client 参数为 httpx.AsyncClient 实例（httpx 在调用函数内导入）。
    """
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        with open(dest_path, "wb") as f:
            async for chunk in response.aiter_bytes(chunk_size=8192):
                f.write(chunk)


async def probe_durations(video_paths: List[str]) -> List[float]:
    """用 ffprobe 获取每个视频的时长（秒）"""
    durations: List[float] = []
    for p in video_paths:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            p,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        try:
            dur = float(stdout.decode("utf-8", errors="ignore").strip())
        except (ValueError, AttributeError):
            dur = 3.0  # 默认 3 秒
        durations.append(dur)
    return durations


async def probe_video_resolution(video_path: str) -> tuple:
    """
    用 ffprobe 获取视频分辨率，返回 (width, height)。

    失败时返回默认值 (1920, 1080)，用于 drawtext 位置计算的兜底。
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        video_path,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        out = stdout.decode("utf-8", errors="ignore").strip()
        # 输出格式如 "1920x1080"
        if "x" in out:
            w_str, h_str = out.split("x", 1)
            return int(w_str), int(h_str)
    except Exception as e:
        logger.warning("ffprobe 读取视频分辨率失败: %s", e)
    return 1920, 1080


async def concat_normalized_videos(normalized_paths: List[str], output_path: str) -> None:
    """用 concat demuxer 拼接已归一化片段（-c copy，最快）"""
    if len(normalized_paths) == 1:
        import shutil
        shutil.copy2(normalized_paths[0], output_path)
        return
    concat_list_path = output_path + ".concat.txt"
    with open(concat_list_path, "w") as f:
        for p in normalized_paths:
            # ffmpeg concat demuxer 要求绝对路径，单引号转义
            f.write(f"file '{os.path.abspath(p)}'\n")
    await run_ffmpeg(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-c", "copy", output_path],
        timeout=600,
        error_label="ffmpeg 视频拼接（concat）",
    )


async def ffmpeg_final_composite(
    video_path: str,
    audio_path: Optional[str],
    subtitle_path: Optional[str],
    output_path: str,
    subtitle_mode: Optional[str] = None,
    drawtext_filter: Optional[str] = None,
) -> None:
    """
    最终合成：视频 + 音频 + 字幕

    - subtitle_mode="hard": 字幕硬烧到画面（subtitles 滤镜 + ASS，需要 libass）
    - subtitle_mode="drawtext": 字幕直烧到画面（drawtext 滤镜，ffmpeg 内置无需 libass）
    - subtitle_mode="soft": 字幕作为软字幕嵌入（mov_text，播放器可选显示）
    - subtitle_mode=None: 无字幕
    """
    cmd: List[str] = ["ffmpeg", "-y", "-i", video_path]

    if audio_path:
        cmd.extend(["-i", audio_path])

    # 软字幕：作为独立输入流
    if subtitle_mode == "soft" and subtitle_path:
        cmd.extend(["-i", subtitle_path])

    # 视频滤镜（hard / drawtext 模式使用 -vf）
    vf_filters: List[str] = []
    if subtitle_mode == "hard" and subtitle_path:
        # 注意：ffmpeg 8.0 的 subtitles 滤镜不再支持 subtitles='path' 单引号包裹整个路径的写法
        # 改用 subtitles=filename=path 显式参数语法，路径中的冒号需转义
        escaped_path = subtitle_path.replace(":", "\\:")
        vf_filters.append(f"subtitles=filename={escaped_path}")
    elif subtitle_mode == "drawtext" and drawtext_filter:
        # drawtext 模式：直接传入已构造好的 drawtext 滤镜链
        vf_filters.append(drawtext_filter)

    if vf_filters:
        cmd.extend(["-vf", ",".join(vf_filters)])

    # 映射流
    # 输入索引：0=video, 1=audio(可选), 2=subtitle(可选,仅soft模式)
    if audio_path and subtitle_mode == "soft" and subtitle_path:
        cmd.extend(["-map", "0:v", "-map", "1:a", "-map", "2:s"])
    elif audio_path:
        cmd.extend(["-map", "0:v", "-map", "1:a"])
    elif subtitle_mode == "soft" and subtitle_path:
        cmd.extend(["-map", "0:v", "-map", "1:s"])
    else:
        cmd.extend(["-map", "0:v"])

    # 编码参数
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
    ])
    if audio_path:
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])
    # 软字幕编码为 mov_text（mp4 容器标准字幕格式）
    if subtitle_mode == "soft" and subtitle_path:
        cmd.extend(["-c:s", "mov_text"])

    cmd.append(output_path)

    await run_ffmpeg(cmd, timeout=900, error_label="ffmpeg 最终合成")
