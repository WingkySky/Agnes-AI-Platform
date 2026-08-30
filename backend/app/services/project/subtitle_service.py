# =====================================================
# 字幕生成服务 — 从分镜对白生成 SRT/ASS 字幕（Phase 2）
#
# 核心能力:
#   1. generate_subtitles: 从分镜对白批量生成字幕（双模式：LLM 拆分 / Whisper 对齐）
#   2. generate_subtitles_with_whisper: 基于 TTS 音频做 forced alignment，时间戳精确
#   3. build_srt: 生成 SRT 格式文件供 ffmpeg 烧录
#   4. build_ass: 生成 ASS 格式文件（含样式）供 ffmpeg 烧录
#   5. format_srt_time / format_ass_time: 时间格式化
#   6. get_subtitle_clips: 查询项目的字幕片段
#
# 字幕生成策略（双模式，对齐竞品 MoneyPrinterTurbo edge/whisper 设计）:
#   - mode="llm"（默认）: 输入分镜对白 + 分镜时长
#       LLM 拆分为多条短字幕（每条≤20字），按权重比例分配时长
#   - mode="whisper": 输入分镜的 TTS 音频（active_audio_id）
#       faster-whisper 本地转写获取 segment-level 时间戳
#       时间戳精确到毫秒，无需按权重估算
#
# Whisper 为可选依赖：
#   - 未安装 faster-whisper 时自动回退 LLM 模式 + info 日志
#   - 分镜无 active_audio_id 时回退 LLM 模式处理该分镜
#
# 字幕片段统一写入 project_timeline_clips 表（track_type='subtitle'）
# =====================================================

import json
import logging
import os
import tempfile
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import ProjectShot, ProjectShotAudio, ProjectTimelineClip
from app.services.project.sse_manager import project_sse_manager
from app.services.model_registry import resolve_project_chat_model_id
from app.services.project.wizard import parse_json_loose, _call_llm

logger = logging.getLogger("agnes_platform.project.subtitle")

# =====================================================
# Whisper 可选依赖（faster-whisper）
# -------------------------------------------------
# 竞品 MoneyPrinterTurbo 使用 edge-tts + whisper 双模式对齐字幕。
# 本项目 whisper 为可选依赖：未安装时自动回退 LLM 拆分模式。
# 安装方式：pip install faster-whisper
# =====================================================
try:
    from faster_whisper import WhisperModel  # type: ignore
    _WHISPER_AVAILABLE = True
except ImportError:
    _WHISPER_AVAILABLE = False


def is_whisper_available() -> bool:
    """检查 faster-whisper 是否已安装"""
    return _WHISPER_AVAILABLE


# Whisper 模型缓存（按 model_size 复用，避免重复加载）
_whisper_model_cache: dict = {}


def _get_whisper_model(model_size: str = "small", device: str = "cpu"):
    """
    获取（必要时加载）whisper 模型实例。

    model_size: tiny/base/small/medium/large-v3 等，默认 small（中文识别效果与性能平衡）
    device: cpu/cuda，默认 cpu（不依赖 GPU）
    """
    if not _WHISPER_AVAILABLE:
        raise RuntimeError("faster-whisper 未安装，请先 pip install faster-whisper")
    cache_key = f"{model_size}:{device}"
    if cache_key not in _whisper_model_cache:
        logger.info(f"加载 whisper 模型: size={model_size}, device={device}")
        # compute_type=int8 默认，CPU 友好；GPU 环境可改 float16
        _whisper_model_cache[cache_key] = WhisperModel(
            model_size, device=device, compute_type="int8"
        )
    return _whisper_model_cache[cache_key]


# =====================================================
# 默认字幕样式
# =====================================================
DEFAULT_SUBTITLE_STYLE = {
    "font_family": "Microsoft YaHei",
    "font_size": 48,
    "font_color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 2,
    "position": "bottom",
    "margin_vertical": 60,
}


# =====================================================
# 字幕生成
# =====================================================

async def generate_subtitles(
    db: AsyncSession,
    project_id: int,
    shot_ids: Optional[List[int]] = None,
    mode: str = "llm",
    whisper_model_size: str = "small",
) -> List[dict]:
    """
    从分镜对白生成字幕片段（双模式）

    参数:
    - shot_ids: 指定分镜 ID，不传则全部有对白的分镜
    - mode: "llm"（默认，LLM 拆分按权重分配时长）/ "whisper"（基于 TTS 音频 forced alignment）
    - whisper_model_size: whisper 模型大小，仅 mode="whisper" 时生效

    模式回退策略:
    - mode="whisper" 但 faster-whisper 未安装 → 回退 LLM + info 日志
    - mode="whisper" 但分镜无 active_audio_id → 该分镜回退 LLM 拆分

    1. 取所有有对白的分镜（或指定 shot_ids）
    2. 按 mode 走对应路径生成字幕片段
    3. 写入 project_timeline_clips 表（track_type='subtitle'）
    4. 推送 SSE
    """
    # 模式回退：whisper 不可用时回退 LLM
    if mode == "whisper" and not _WHISPER_AVAILABLE:
        logger.info(
            "faster-whisper 未安装，字幕生成回退 LLM 模式（pip install faster-whisper 启用）"
        )
        mode = "llm"

    # 1. 查询分镜
    query = select(ProjectShot).where(ProjectShot.project_id == project_id)
    if shot_ids:
        query = query.where(ProjectShot.id.in_(shot_ids))
    query = query.order_by(ProjectShot.sort_order)
    shots = (await db.execute(query)).scalars().all()

    if not shots:
        return []

    # 2. 按 mode 路由到对应实现
    if mode == "whisper":
        clips_created, total_duration = await _generate_subtitles_with_whisper(
            db, project_id, shots, whisper_model_size
        )
    else:
        clips_created, total_duration = await _generate_subtitles_llm(
            db, project_id, shots
        )

    if not clips_created:
        return []

    await db.commit()

    await project_sse_manager.push(project_id, "subtitle_completed", {
        "count": len(clips_created),
        "total_duration": total_duration,
        "mode": mode,
    })
    return clips_created


# =====================================================
# LLM 模式 — 对白拆分 + 按权重分配时长
# =====================================================

async def _generate_subtitles_llm(
    db: AsyncSession, project_id: int, shots: List[ProjectShot]
) -> tuple:
    """
    LLM 拆分模式：将分镜对白拆分为多条短字幕，按权重分配时长。

    返回: (clips_created, total_duration)
    """
    shots_input = [
        {"id": s.id, "dialogue": s.dialogue or "", "duration_ms": s.duration_ms or 3000}
        for s in shots if s.dialogue
    ]
    if not shots_input:
        return [], 0.0

    prompt = f"""请将以下分镜对白拆分为字幕片段，每条字幕不超过 20 字。
输出 JSON 数组，每个元素包含:
- shot_id: 分镜 ID
- segments: 数组，每条包含 text（字幕文本）和 weight（时长权重，0-1，按权重分配分镜时长）

分镜列表:
{json.dumps(shots_input, ensure_ascii=False, indent=2)}

严格输出 JSON，不要多余文字。"""

    result_text = await _call_llm(
        prompt, temperature=0.3,
        fallback_model=await resolve_project_chat_model_id(db, project_id),
    )
    parsed = parse_json_loose(result_text)

    clips_created: List[dict] = []
    current_time = 0.0  # 全局时间轴起点

    for shot in shots:
        shot_subtitle = next(
            (item for item in parsed if item.get("shot_id") == shot.id),
            None,
        )
        if not shot_subtitle:
            # 无字幕的分镜，仅推进时间轴
            current_time += (shot.duration_ms or 3000) / 1000.0
            continue

        segments = shot_subtitle.get("segments", [])
        if not segments:
            current_time += (shot.duration_ms or 3000) / 1000.0
            continue

        shot_duration = (shot.duration_ms or 3000) / 1000.0
        total_weight = sum(seg.get("weight", 1.0) for seg in segments) or 1.0

        for seg in segments:
            weight = seg.get("weight", 1.0)
            seg_duration = shot_duration * (weight / total_weight)
            clip = ProjectTimelineClip(
                project_id=project_id,
                track_type="subtitle",
                track_index=0,
                source_type="subtitle",
                shot_id=shot.id,
                start_time=current_time,
                duration=seg_duration,
                subtitle_text=seg.get("text", "").strip(),
                sort_order=len(clips_created),
            )
            db.add(clip)
            clips_created.append({
                "shot_id": shot.id,
                "start_time": current_time,
                "duration": seg_duration,
                "text": seg.get("text", "").strip(),
            })
            current_time += seg_duration

    return clips_created, current_time


# =====================================================
# Whisper 模式 — TTS 音频 forced alignment（时间戳精确）
# -------------------------------------------------
# 竞品 MoneyPrinterTurbo 使用 whisper 对 TTS 音频做 forced alignment
# 获取精确的 segment 时间戳，避免 LLM 模式按权重估算的偏差。
#
# 流程:
#   1. 取每个分镜的 active_audio_id 对应音频
#   2. 下载到临时目录
#   3. faster-whisper 转写（language=zh, segment-level 时间戳）
#   4. 每条 segment 作为一个字幕片段，起始时间 = 分镜起始 + segment.start
#   5. 分镜起始时间按音频实际时长累加（更精确，不依赖 duration_ms 估算）
#
# 边界处理:
#   - 分镜无 active_audio_id：回退 LLM 拆分该分镜
#   - 音频下载失败：跳过该分镜
#   - whisper 转写返回空：跳过该分镜
# =====================================================

async def _generate_subtitles_with_whisper(
    db: AsyncSession, project_id: int, shots: List[ProjectShot],
    whisper_model_size: str = "small",
) -> tuple:
    """
    Whisper forced alignment 模式。

    返回: (clips_created, total_duration)
    """
    if not _WHISPER_AVAILABLE:
        logger.warning("whisper 模式调用但 faster-whisper 未安装，回退 LLM")
        return await _generate_subtitles_llm(db, project_id, shots)

    import httpx

    # 1. 收集需要 whisper 转写的分镜（有 active_audio_id）
    whisper_shots: List[tuple] = []  # [(shot, audio_url, audio_duration_ms)]
    fallback_shots: List[ProjectShot] = []  # 无音频的分镜，回退 LLM

    for shot in shots:
        if not shot.active_audio_id:
            if shot.dialogue:
                fallback_shots.append(shot)
            continue
        audio = (
            await db.execute(
                select(ProjectShotAudio).where(ProjectShotAudio.id == shot.active_audio_id)
            )
        ).scalar_one_or_none()
        if not audio or not audio.file_url:
            if shot.dialogue:
                fallback_shots.append(shot)
            continue
        whisper_shots.append((shot, audio.file_url, audio.duration_ms or 0))

    # 2. 下载音频 + whisper 转写
    tmp_dir = tempfile.mkdtemp(prefix=f"subtitle_whisper_{project_id}_")
    clips_created: List[dict] = []
    current_time = 0.0  # 全局时间轴起点

    try:
        model = _get_whisper_model(whisper_model_size, device="cpu")

        async with httpx.AsyncClient(timeout=300) as client:
            for idx, (shot, audio_url, audio_duration_ms) in enumerate(whisper_shots):
                # 下载音频
                local_path = os.path.join(tmp_dir, f"audio_{idx:04d}.mp3")
                try:
                    resp = await client.get(audio_url)
                    resp.raise_for_status()
                    with open(local_path, "wb") as f:
                        f.write(resp.content)
                except Exception as e:
                    logger.warning(f"分镜 {shot.id} 音频下载失败，跳过: {e}")
                    # 推进时间轴（用 duration_ms 估算）
                    current_time += (audio_duration_ms or shot.duration_ms or 3000) / 1000.0
                    if shot.dialogue:
                        fallback_shots.append(shot)
                    continue

                await project_sse_manager.push(project_id, "subtitle_progress", {
                    "status": "transcribing",
                    "shot_id": shot.id,
                    "progress": int(50 * (idx + 1) / max(len(whisper_shots), 1)),
                })

                # whisper 转写（同步 API，放在线程池避免阻塞事件循环）
                import asyncio
                segments_iter, _info = await asyncio.to_thread(
                    model.transcribe,
                    local_path,
                    language="zh",
                    vad_filter=True,
                    word_timestamps=False,  # segment-level 已足够
                )
                # segments_iter 是 generator，需消费
                segments = list(segments_iter)

                if not segments:
                    # whisper 没识别到内容，回退 LLM 处理该分镜
                    current_time += (audio_duration_ms or shot.duration_ms or 3000) / 1000.0
                    if shot.dialogue:
                        fallback_shots.append(shot)
                    continue

                # 每条 segment 作为一个字幕片段
                for seg in segments:
                    text = (seg.text or "").strip()
                    if not text:
                        continue
                    seg_start = float(seg.start)
                    seg_end = float(seg.end)
                    seg_duration = max(seg_end - seg_start, 0.3)  # 最短 0.3s 保证可读

                    clip = ProjectTimelineClip(
                        project_id=project_id,
                        track_type="subtitle",
                        track_index=0,
                        source_type="subtitle",
                        shot_id=shot.id,
                        start_time=current_time + seg_start,
                        duration=seg_duration,
                        subtitle_text=text,
                        sort_order=len(clips_created),
                    )
                    db.add(clip)
                    clips_created.append({
                        "shot_id": shot.id,
                        "start_time": current_time + seg_start,
                        "duration": seg_duration,
                        "text": text,
                    })

                # 推进时间轴（用音频实际时长，更精确）
                audio_actual_duration = float(segments[-1].end) if segments else (
                    (audio_duration_ms or shot.duration_ms or 3000) / 1000.0
                )
                current_time += audio_actual_duration

    finally:
        # 清理临时目录
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass

    # 3. 对回退分镜用 LLM 处理（追加在 whisper 字幕之后）
    if fallback_shots:
        # 重新计算 fallback 字幕的起始时间（在 whisper 字幕之后）
        # 注意：fallback 字幕的时间轴从 current_time 继续
        # 但 LLM 模式默认从 0 开始，所以这里需要偏移
        fallback_clips, fallback_duration = await _generate_subtitles_llm_fallback(
            db, project_id, fallback_shots, time_offset=current_time
        )
        clips_created.extend(fallback_clips)
        current_time += fallback_duration

    return clips_created, current_time


async def _generate_subtitles_llm_fallback(
    db: AsyncSession, project_id: int, shots: List[ProjectShot],
    time_offset: float = 0.0,
) -> tuple:
    """
    LLM 回退模式（带时间偏移，用于 whisper 模式中无音频分镜的处理）。

    返回: (clips_created, total_duration)
    """
    shots_input = [
        {"id": s.id, "dialogue": s.dialogue or "", "duration_ms": s.duration_ms or 3000}
        for s in shots if s.dialogue
    ]
    if not shots_input:
        return [], 0.0

    prompt = f"""请将以下分镜对白拆分为字幕片段，每条字幕不超过 20 字。
输出 JSON 数组，每个元素包含:
- shot_id: 分镜 ID
- segments: 数组，每条包含 text（字幕文本）和 weight（时长权重，0-1，按权重分配分镜时长）

分镜列表:
{json.dumps(shots_input, ensure_ascii=False, indent=2)}

严格输出 JSON，不要多余文字。"""

    result_text = await _call_llm(
        prompt, temperature=0.3,
        fallback_model=await resolve_project_chat_model_id(db, project_id),
    )
    parsed = parse_json_loose(result_text)

    clips_created: List[dict] = []
    current_time = time_offset

    for shot in shots:
        shot_subtitle = next(
            (item for item in parsed if item.get("shot_id") == shot.id),
            None,
        )
        if not shot_subtitle:
            current_time += (shot.duration_ms or 3000) / 1000.0
            continue

        segments = shot_subtitle.get("segments", [])
        if not segments:
            current_time += (shot.duration_ms or 3000) / 1000.0
            continue

        shot_duration = (shot.duration_ms or 3000) / 1000.0
        total_weight = sum(seg.get("weight", 1.0) for seg in segments) or 1.0

        for seg in segments:
            weight = seg.get("weight", 1.0)
            seg_duration = shot_duration * (weight / total_weight)
            clip = ProjectTimelineClip(
                project_id=project_id,
                track_type="subtitle",
                track_index=0,
                source_type="subtitle",
                shot_id=shot.id,
                start_time=current_time,
                duration=seg_duration,
                subtitle_text=seg.get("text", "").strip(),
                sort_order=len(clips_created),
            )
            db.add(clip)
            clips_created.append({
                "shot_id": shot.id,
                "start_time": current_time,
                "duration": seg_duration,
                "text": seg.get("text", "").strip(),
            })
            current_time += seg_duration

    return clips_created, current_time - time_offset


# =====================================================
# 公开 API: 单独暴露 whisper 模式入口（供路由层直接调用）
# =====================================================

async def generate_subtitles_with_whisper(
    db: AsyncSession,
    project_id: int,
    shot_ids: Optional[List[int]] = None,
    whisper_model_size: str = "small",
) -> List[dict]:
    """
    显式调用 whisper 模式生成字幕（外部 API 入口）

    等价于 generate_subtitles(mode="whisper")，但语义更明确。
    未安装 faster-whisper 时自动回退 LLM 模式。
    """
    return await generate_subtitles(
        db, project_id, shot_ids=shot_ids,
        mode="whisper", whisper_model_size=whisper_model_size,
    )


# =====================================================
# SRT / ASS 格式构建
# =====================================================

def format_srt_time(seconds: float) -> str:
    """将秒数格式化为 SRT 时间格式 HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_ass_time(seconds: float) -> str:
    """ASS 时间格式 H:MM:SS.cc（百分秒）"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centisecs = int((seconds - int(seconds)) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"


def build_srt(clips: List[dict]) -> str:
    """构建 SRT 格式字幕文本"""
    lines: List[str] = []
    for idx, clip in enumerate(clips, start=1):
        start = format_srt_time(clip["start_time"])
        end = format_srt_time(clip["start_time"] + clip["duration"])
        lines.append(str(idx))
        lines.append(f"{start} --> {end}")
        lines.append(clip["text"])
        lines.append("")  # 空行分隔
    return "\n".join(lines)


def build_ass(clips: List[dict], style: Optional[dict] = None) -> str:
    """
    构建 ASS 格式字幕文件（含样式，供 ffmpeg subtitles 滤镜烧录）

    ASS 格式支持丰富的字幕样式（字体/颜色/位置/描边等），
    ffmpeg 的 subtitles 滤镜优先使用 ASS。
    """
    s = style or DEFAULT_SUBTITLE_STYLE

    # 颜色转换：#RRGGBB → ASS 的 &H00BBGGRR（BGR 倒序）
    def to_ass_color(hex_color: str) -> str:
        h = hex_color.lstrip("#")
        r, g, b = h[0:2], h[2:4], h[4:6]
        return f"&H00{b}{g}{r}".upper()

    primary_color = to_ass_color(s.get("font_color", "#FFFFFF"))
    outline_color = to_ass_color(s.get("outline_color", "#000000"))
    font_name = s.get("font_family", "Microsoft YaHei")
    font_size = int(s.get("font_size", 48))
    outline_width = int(s.get("outline_width", 2))
    # 位置：bottom→2 (默认), top→8, center→5
    alignment = {"bottom": 2, "top": 8, "center": 5}.get(s.get("position", "bottom"), 2)
    margin_v = int(s.get("margin_vertical", 60))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},{outline_color},&H00000000,0,0,0,0,100,100,0,0,1,{outline_width},0,{alignment},10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: List[str] = []
    for clip in clips:
        start = format_ass_time(clip["start_time"])
        end = format_ass_time(clip["start_time"] + clip["duration"])
        # 转义 ASS 特殊字符
        text = clip["text"].replace("\n", "\\N")
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    return header + "\n".join(events) + "\n"


# =====================================================
# 字幕片段查询
# =====================================================

async def get_subtitle_clips(db: AsyncSession, project_id: int) -> List[ProjectTimelineClip]:
    """获取项目的所有字幕片段（按 start_time 排序）"""
    result = await db.execute(
        select(ProjectTimelineClip)
        .where(
            ProjectTimelineClip.project_id == project_id,
            ProjectTimelineClip.track_type == "subtitle",
        )
        .order_by(ProjectTimelineClip.start_time)
    )
    return result.scalars().all()
