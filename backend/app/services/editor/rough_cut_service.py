# =====================================================
# AI 辅助粗剪检测层（静音剔除 / 场景切分）
#
# - 纯 Python 检测：PyAV 解码 + numpy，零 CLI 依赖（生产镜像无 ffmpeg 可执行，
#   渲染链路的 ffmpeg 是存量缺口，检测层不跟随其假设）
# - 统一输出合同 segments: [{start, end}]（秒，升序不重叠）
# - 静音检测 = 音频 RMS 桶化 → 低于阈值连续超 min_silence 判静音 → 有声段取补集
# - 场景检测 = 降采样灰度帧相邻平均绝对差 → 差值超阈值处切开 → 碎镜头并入前段
# =====================================================

import asyncio
import logging
import shutil
import tempfile
from typing import Any

import av
import numpy as np
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.asset_library import get_asset_by_id
from app.services.editor.media_source import resolve_asset_local_file

logger = logging.getLogger("agnes_platform.editor.rough_cut")

# 音频 RMS 桶宽（秒）
_AUDIO_BUCKET_SEC = 0.05
# 场景检测采样率（帧/秒）与降采样尺寸（宽）
_SCENE_SAMPLE_FPS = 5
_SCENE_SAMPLE_WIDTH = 64


def _norm_segments(raw: list[tuple[float, float]], duration: float, min_keep: float) -> list[dict[str, Any]]:
    """原始段 → 合同段：钳位（钳后判碎）、去重叠、剔碎段；空段返回 []"""
    segs: list[tuple[float, float]] = []
    for start, end in sorted(raw):
        start = max(0.0, start)
        end = min(duration, end) if duration > 0 else end
        if end - start < min_keep:
            continue
        if segs and start < segs[-1][1]:
            segs[-1] = (segs[-1][0], max(segs[-1][1], end))
        else:
            segs.append((start, end))
    return [{"start": round(s, 3), "end": round(e, 3)} for s, e in segs]


def _media_duration(container: av.container.InputContainer) -> float:
    """容器时长（秒）：流 duration 优先，元数据兜底；均缺失返回 0（调用方按流帧推进兜底）"""
    if container.duration and container.duration > 0:
        return container.duration / av.time_base
    for stream in container.streams:
        if stream.duration and stream.duration > 0 and stream.time_base:
            return stream.duration / stream.time_base
    return 0.0


def detect_silence_speech(
    media_path: str,
    *,
    threshold_db: float = -30.0,
    min_silence: float = 0.5,
    min_keep: float = 0.4,
) -> dict[str, Any]:
    """静音剔除：音频帧 RMS → 静音游程（帧级起止秒推进）→ 有声段补集。返回 {segments, duration_total, kept_ratio}"""
    with av.open(media_path) as container:
        duration = _media_duration(container)
        audio = next((s for s in container.streams if s.type == "audio"), None)
        if audio is None:
            raise ValueError("no_audio_stream")
        rate = float(audio.rate or 0) or 48000.0
        # 帧级 (起点秒, 终点秒, dB)：终点 = pts + 采样数/rate，不假设固定帧长
        frame_db: list[tuple[float, float, float]] = []
        container.seek(0)
        for frame in container.decode(audio):
            t0 = float(frame.time) if frame.time is not None else None
            samples = getattr(frame, "samples", 0) or 0
            arr = frame.to_ndarray().astype(np.float32)
            if arr.ndim > 1:
                arr = arr.reshape(-1)
            rms = float(np.sqrt(np.mean(arr * arr))) if arr.size else 0.0
            db = 20.0 * float(np.log10(rms)) if rms > 0 else -120.0
            if t0 is None:
                prev_end = frame_db[-1][1] if frame_db else 0.0
                t0 = prev_end
            t1 = t0 + (samples / rate if samples > 0 else _AUDIO_BUCKET_SEC)
            frame_db.append((t0, t1, db))
    if not frame_db:
        raise ValueError("no_audio_frames")

    # 静音游程：连续低于阈值的帧跨度 ≥ min_silence 判静音
    silence: list[tuple[float, float]] = []
    run_start: float | None = None
    run_end = 0.0
    for t0, t1, db in frame_db:
        if db < threshold_db:
            if run_start is None:
                run_start = t0
            run_end = t1
        elif run_start is not None:
            if run_end - run_start >= min_silence:
                silence.append((run_start, run_end))
            run_start = None
    tail = frame_db[-1][1]
    if run_start is not None and run_end - run_start >= min_silence:
        silence.append((run_start, run_end))
    if duration > 0:
        silence = [(s, min(e, duration)) for s, e in silence]

    # 有声段 = [0, duration] 减静音段
    speech: list[tuple[float, float]] = []
    cursor = 0.0
    for s, e in silence:
        if s > cursor:
            speech.append((cursor, s))
        cursor = max(cursor, e)
    end_total = duration if duration > 0 else tail
    if end_total > cursor:
        speech.append((cursor, end_total))

    segments = _norm_segments(speech, end_total, min_keep)
    kept = sum(s["end"] - s["start"] for s in segments)
    return {
        "segments": segments,
        "duration_total": round(end_total, 3),
        "kept_ratio": round(kept / end_total, 3) if end_total > 0 else 0.0,
    }


def detect_scenes(
    media_path: str,
    *,
    threshold: float = 14.0,
    min_scene: float = 0.5,
) -> dict[str, Any]:
    """场景切分：降采样灰度帧相邻平均绝对差超阈值处切开。返回 {segments, duration_total}"""
    cuts: list[float] = []
    duration = 0.0
    prev: np.ndarray | None = None
    prev_t = 0.0
    with av.open(media_path) as container:
        duration = _media_duration(container)
        video = next((s for s in container.streams if s.type == "video"), None)
        if video is None:
            raise ValueError("no_video_stream")
        container.seek(0)
        # 采样节拍：平均帧间隔的 _SCENE_SAMPLE_FPS 倍数周期性取样（按 pts 秒对齐，免逐帧计数）
        interval = 1.0 / _SCENE_SAMPLE_FPS
        next_sample_t = 0.0
        for frame in container.decode(video):
            t = float(frame.time) if frame.time is not None else prev_t
            if t < next_sample_t:
                continue
            next_sample_t = t + interval
            small = frame.to_ndarray().astype(np.float32)
            if small.ndim == 3:
                small = small.mean(axis=2)
            h, w = small.shape[:2]
            if w > _SCENE_SAMPLE_WIDTH:
                step = max(1, w // _SCENE_SAMPLE_WIDTH)
                small = small[::step, ::step]
            if prev is not None:
                diff = float(np.mean(np.abs(small - prev)))
                if diff > threshold:
                    cuts.append(t)
            prev = small
            prev_t = t

    if duration <= 0:
        duration = prev_t
    raw: list[tuple[float, float]] = []
    cursor = 0.0
    for cut in cuts:
        if cut - cursor >= min_scene:
            raw.append((cursor, cut))
            cursor = cut
    if duration > cursor:
        raw.append((cursor, duration))
    segments = _norm_segments(raw, duration, min_scene)
    return {"segments": segments, "duration_total": round(duration, 3)}


# =====================================================
# 分析编排（HTTP 路由与 MCP 工具共用入口）
# =====================================================

# 同步分析上限（秒）：解码全片 CPU 型，超时明确报错引导用户改用手动剪辑
ANALYZE_TIMEOUT_SEC = 120


async def analyze_asset(
    db: AsyncSession, user_id: int, asset_id: int, mode: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """归属/类型/mode 校验 → 源文件就位 → 检测（线程池 + 超时）→ segments"""
    asset = await get_asset_by_id(db, asset_id)
    if not asset or asset.user_id != user_id:
        raise HTTPException(status_code=404, detail="素材不存在")
    if (asset.kind or "") not in ("video", "audio"):
        raise HTTPException(status_code=400, detail="仅支持视频/音频素材分析")
    if mode not in ("silence", "scenes"):
        raise HTTPException(status_code=400, detail="mode 仅支持 silence / scenes")

    tmp_dir = tempfile.mkdtemp(prefix="rough-cut-")
    try:
        local_path = await resolve_asset_local_file(asset, tmp_dir)
        if not local_path:
            raise HTTPException(status_code=502, detail="素材源文件不可用（本地缺失且远程转存失败）")

        params = params or {}
        try:
            if mode == "silence":
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        detect_silence_speech,
                        local_path,
                        threshold_db=float(params.get("threshold_db", -30.0)),
                        min_silence=float(params.get("min_silence", 0.5)),
                    ),
                    timeout=ANALYZE_TIMEOUT_SEC,
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        detect_scenes,
                        local_path,
                        threshold=float(params.get("threshold", 14.0)),
                        min_scene=float(params.get("min_scene", 0.5)),
                    ),
                    timeout=ANALYZE_TIMEOUT_SEC,
                )
        except TimeoutError:
            raise HTTPException(status_code=503, detail="分析超时（素材过长），请改用手动剪辑")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"素材无法分析：{e}")
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 —— 解码失败转可读错误
            raise HTTPException(status_code=502, detail=f"分析失败：{e}")
        return {"asset_id": asset.id, "mode": mode, **result}
    finally:
        # resolve_asset_local_file 远程转存/本地缺失时的临时副本都落这里；素材本就在本地时路径在外，rmtree 无害
        shutil.rmtree(tmp_dir, ignore_errors=True)
