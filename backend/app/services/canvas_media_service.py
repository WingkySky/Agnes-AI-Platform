# =====================================================
# 画布媒体服务 — 无限画布三节点（tts / subtitle / compose）执行体
#
# 设计（spec: 2026-08-29-final-cut-pipeline-design M3）:
#   - 无状态、不建表：按节点 content 传参，产物落盘 uploads/canvas/
#     （经 main.py 的 /uploads 静态挂载直接可访问）
#   - tts:      复用 audio_service._call_tts_provider（Edge TTS）
#   - subtitle: LLM 拆分文案 → SRT + 片段数组（时长按字数估算）
#   - compose:  下载上游视频 → 归一化 → concat → 混音（TTS/BGM）→ 字幕烧录
#               ffmpeg 能力复用 media_compose 公共层
# =====================================================

import logging
import os
import shutil
import tempfile
from typing import List, Optional
from uuid import uuid4

import httpx

from app.services.media_compose import (
    run_ffmpeg,
    parse_resolution,
    video_normalize_only_cmd,
    stream_download,
    probe_durations,
    probe_video_resolution,
    check_subtitles_filter_available,
    check_drawtext_filter_available,
    build_drawtext_subtitles_filter,
    concat_normalized_videos,
    ffmpeg_final_composite,
)
from app.services.upload_service import UPLOADS_DIR
from app.services.project.audio_service import _call_tts_provider, _resolve_edge_voice
from app.services.project.subtitle_service import DEFAULT_SUBTITLE_STYLE, build_ass, build_srt
from app.services.project.wizard import _call_llm, parse_json_loose

logger = logging.getLogger("agnes_platform.canvas.media")

# 画布产物目录（backend/uploads/canvas，经 /uploads/canvas/... 访问）
CANVAS_OUTPUTS_DIR = os.path.join(UPLOADS_DIR, "canvas")

# 画布 tts 节点简写音色 → Edge TTS 音色名（内置音色 ID / Edge 音色名原样透传 _resolve_edge_voice）
_CANVAS_VOICE_MAP = {
    "default": "zh-CN-YunxiNeural",
    "female": "zh-CN-XiaoxiaoNeural",
    "male": "zh-CN-YunxiNeural",
}


# =====================================================
# TTS 配音
# =====================================================

async def generate_tts(text: str, voice: str = "default", speed: float = 1.0) -> dict:
    """画布文本 → TTS 音频，返回 {audio_url, duration_ms}"""
    if not (text or "").strip():
        raise ValueError("文本内容为空，无法生成配音")
    voice_id = _CANVAS_VOICE_MAP.get(voice, voice)
    audio_url, duration_ms, _file_size = await _call_tts_provider(
        text=text, voice_id=voice_id, speed=speed, save_folder="canvas/tts",
    )
    logger.info("[画布TTS] voice=%s speed=%s duration=%sms url=%s", voice_id, speed, duration_ms, audio_url)
    return {"audio_url": audio_url, "duration_ms": duration_ms}


# =====================================================
# 字幕拆分
# =====================================================

async def generate_subtitles(text: str, max_chars: int = 20) -> dict:
    """
    画布文案 → LLM 拆分字幕，返回 {srt, segments, total_duration}

    segments: [{start_time, duration, text}]，时长按字数估算（0.24s/字，最短 1s）
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("文本内容为空，无法生成字幕")

    prompt = f"""请将以下文案拆分为字幕片段，每条不超过 {max_chars} 字，保持语序完整。
输出 JSON 数组，每个元素包含:
- text: 字幕文本
- weight: 时长权重（0-1，按朗读时长比例估算）

文案:
{text}

严格输出 JSON 数组，不要多余文字。"""
    result_text = await _call_llm(prompt, temperature=0.3)
    parsed = parse_json_loose(result_text)
    if isinstance(parsed, dict):
        parsed = parsed.get("segments") or []

    clips: List[dict] = []
    cursor = 0.0
    for seg in parsed if isinstance(parsed, list) else []:
        seg_text = (seg.get("text") or "").strip() if isinstance(seg, dict) else ""
        if not seg_text:
            continue
        duration = max(1.0, len(seg_text) * 0.24)
        clips.append({
            "start_time": round(cursor, 3),
            "duration": round(duration, 3),
            "text": seg_text,
        })
        cursor += duration

    if not clips:
        raise ValueError("字幕拆分结果为空，请重试")
    logger.info("[画布字幕] 拆分 %d 条, 总时长 %.1fs", len(clips), cursor)
    return {"srt": build_srt(clips), "segments": clips, "total_duration": round(cursor, 3)}


# =====================================================
# 成片合成
# =====================================================

def _resolve_local_media(url: str) -> Optional[str]:
    """本地 /uploads/... URL 直接映射磁盘文件（上传素材无需绕 HTTP 下载）"""
    if url.startswith("/uploads/"):
        path = os.path.join(UPLOADS_DIR, url.removeprefix("/uploads/"))
        return path if os.path.isfile(path) else None
    return None


async def compose_videos(
    video_urls: List[str],
    audio_url: Optional[str] = None,
    subtitles: Optional[List[dict]] = None,
    with_subtitle: bool = True,
    bgm_id: Optional[str] = None,
    aspect_ratio: str = "16:9",
) -> dict:
    """
    多段视频 → 一条成片，返回 {video_url, duration_ms}

    流程: 下载 → 归一化（统一分辨率/帧率/SAR）→ concat → 混音（TTS/BGM）→ 字幕烧录
    产物写入 uploads/canvas/{uuid}.mp4。
    """
    if not video_urls:
        raise ValueError("没有可合成的视频")

    tmp_dir = tempfile.mkdtemp(prefix="canvas_compose_")
    try:
        # 1. 下载视频片段（/uploads 本地文件直接映射，其余走 HTTP）
        async with httpx.AsyncClient(timeout=300) as client:
            local_paths: List[str] = []
            for idx, url in enumerate(video_urls):
                local_path = _resolve_local_media(url)
                if not local_path:
                    local_path = os.path.join(tmp_dir, f"video_{idx:04d}.mp4")
                    await stream_download(client, url, local_path)
                local_paths.append(local_path)

        # 2. 归一化
        width, height = parse_resolution(aspect_ratio)
        normalized_paths: List[str] = []
        for idx, p in enumerate(local_paths):
            norm_path = os.path.join(tmp_dir, f"norm_{idx:04d}.mp4")
            await run_ffmpeg(
                video_normalize_only_cmd(p, norm_path, width, height),
                timeout=300, error_label=f"ffmpeg 视频归一化（片段 {idx}）",
            )
            normalized_paths.append(norm_path)

        # 3. 拼接
        composite_video_path = os.path.join(tmp_dir, "composite.mp4")
        await concat_normalized_videos(normalized_paths, composite_video_path)
        total_duration = (await probe_durations([composite_video_path]))[0]

        # 4. 混音（TTS + 可选 BGM）
        composite_audio_path: Optional[str] = None
        tts_path: Optional[str] = None
        if audio_url:
            tts_path = _resolve_local_media(audio_url)
            if not tts_path:
                tts_path = os.path.join(tmp_dir, "tts_audio")
                async with httpx.AsyncClient(timeout=120) as client:
                    await stream_download(client, audio_url, tts_path)
        bgm_path: Optional[str] = None
        if bgm_id:
            from app.services.project.bgm_library import get_bgm_path
            bgm_path = get_bgm_path(bgm_id)
        if tts_path or bgm_path:
            composite_audio_path = await _mix_audio(tts_path, bgm_path, total_duration, tmp_dir)

        # 5. 字幕（硬烧 ASS → drawtext 直烧 → 软字幕，三级降级）
        subtitle_path: Optional[str] = None
        subtitle_mode: Optional[str] = None
        drawtext_filter: Optional[str] = None
        clips = subtitles if (with_subtitle and subtitles) else None
        if clips:
            if await check_subtitles_filter_available():
                subtitle_path = os.path.join(tmp_dir, "subtitles.ass")
                with open(subtitle_path, "w", encoding="utf-8") as f:
                    f.write(build_ass(clips, DEFAULT_SUBTITLE_STYLE))
                subtitle_mode = "hard"
            elif await check_drawtext_filter_available():
                vid_w, vid_h = await probe_video_resolution(composite_video_path)
                drawtext_filter = build_drawtext_subtitles_filter(clips, DEFAULT_SUBTITLE_STYLE, vid_w, vid_h)
                subtitle_mode = "drawtext"
            else:
                subtitle_path = os.path.join(tmp_dir, "subtitles.srt")
                with open(subtitle_path, "w", encoding="utf-8") as f:
                    f.write(build_srt(clips))
                subtitle_mode = "soft"

        # 6. 最终合成 → uploads/canvas/
        os.makedirs(CANVAS_OUTPUTS_DIR, exist_ok=True)
        out_name = f"{uuid4().hex}.mp4"
        output_path = os.path.join(CANVAS_OUTPUTS_DIR, out_name)
        await ffmpeg_final_composite(
            video_path=composite_video_path,
            audio_path=composite_audio_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
            subtitle_mode=subtitle_mode,
            drawtext_filter=drawtext_filter,
        )
        logger.info(
            "[画布合成] 完成: videos=%d audio=%s subtitle_mode=%s duration=%.1fs → %s",
            len(video_urls), bool(composite_audio_path), subtitle_mode, total_duration, output_path,
        )
        return {"video_url": f"/uploads/canvas/{out_name}", "duration_ms": int(total_duration * 1000)}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def _mix_audio(
    tts_path: Optional[str], bgm_path: Optional[str],
    total_duration: float, tmp_dir: str,
) -> str:
    """混合 TTS 与 BGM（BGM 音量 0.15 + 首尾淡入淡出），返回混音产物路径"""
    # 仅 TTS：直接使用原始音频
    if tts_path and not bgm_path:
        return tts_path

    # BGM 预处理：按成片时长截取 + 淡入淡出 + 降音量
    dur = total_duration if total_duration > 0 else 60.0
    bgm_processed = os.path.join(tmp_dir, "bgm_processed.aac")
    await run_ffmpeg(
        [
            "ffmpeg", "-y", "-i", bgm_path,
            "-t", str(dur),
            "-af", f"afade=t=in:st=0:d=0.5,afade=t=out:st={max(0, dur - 0.5)}:d=0.5,volume=0.15",
            "-c:a", "aac", "-b:a", "128k",
            bgm_processed,
        ],
        timeout=300, error_label="ffmpeg BGM 预处理",
    )
    if not tts_path:
        return bgm_processed

    # TTS + BGM amix（以 TTS 时长为准）
    mixed = os.path.join(tmp_dir, "mixed.aac")
    await run_ffmpeg(
        [
            "ffmpeg", "-y", "-i", tts_path, "-i", bgm_processed,
            "-filter_complex", "amix=inputs=2:duration=first:dropout_transition=0",
            "-c:a", "aac", "-b:a", "128k",
            mixed,
        ],
        timeout=300, error_label="ffmpeg TTS+BGM 混音",
    )
    return mixed
