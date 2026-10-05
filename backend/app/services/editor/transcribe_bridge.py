# =====================================================
# 剪辑器字幕转写桥接
#
# POST /api/editor/projects/{uid}/subtitles/preview 的服务层：
# 指定音频轨 → 取轨上片段对应素材 → whisper 转写 → 字幕片段草稿
# （入轨由前端 rebuildSubtitleClips 命令完成，本服务不写 document）
#
# 时间映射：源内 seg 时间减去 trimStart 得片段内偏移，再加 clip.start
# 得时间线时间；早于 trimStart 的段落丢弃，超出片段时长的部分截断。
# =====================================================

import shutil
import tempfile
from typing import List

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.editing_project import EditingProject
from app.services.asset_library import get_asset_by_id
from app.services.editor.media_source import resolve_asset_local_file
from app.services.media.transcribe_service import is_whisper_available, transcribe_audio

# 字幕最短可读时长（与项目域对齐）
MIN_SEGMENT_SEC = 0.3


def _audio_clips_on_track(project: EditingProject, track_id: str) -> list[dict]:
    doc = project.document or {}
    tracks = {t.get("id"): t for t in doc.get("tracks", []) if isinstance(t, dict)}
    track = tracks.get(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="字幕转写目标轨道不存在")
    if track.get("kind") != "audio":
        raise HTTPException(status_code=400, detail="字幕转写仅支持音频轨")
    clips = [
        c for c in doc.get("clips", [])
        if isinstance(c, dict) and c.get("trackId") == track_id and isinstance(c.get("assetId"), int)
    ]
    clips.sort(key=lambda c: float(c.get("start") or 0.0))
    return clips


async def preview_subtitle_segments(
    db: AsyncSession, project: EditingProject, track_id: str
) -> List[dict]:
    """转写音频轨 → 字幕片段草稿 [{start, end, text}]（时间线时间，秒）"""
    clips = _audio_clips_on_track(project, track_id)
    if not is_whisper_available():
        raise HTTPException(
            status_code=503,
            detail="转写服务未启用（服务器未安装 faster-whisper），请手动添加字幕",
        )
    if not clips:
        raise HTTPException(status_code=400, detail="目标音频轨上没有可转写的音频片段")

    tmp_dir = tempfile.mkdtemp(prefix="editor_subtitle_")
    out: List[dict] = []
    try:
        for clip in clips:
            asset = await get_asset_by_id(db, int(clip["assetId"]))
            if not asset or asset.user_id != project.user_id:
                continue  # 片段素材失效：跳过（骨架校验保证新写入有效，存量可能被删）
            local_path = await resolve_asset_local_file(asset, tmp_dir)
            if not local_path:
                continue
            segments = await transcribe_audio(local_path, language="zh")

            clip_start = float(clip.get("start") or 0.0)
            clip_duration = float(clip.get("duration") or 0.0)
            trim_start = float(clip.get("trimStart") or 0.0)
            for seg in segments:
                rel_start = seg["start"] - trim_start
                if rel_start >= clip_duration > 0:
                    break  # 片段按 start 升序，后面全部超出
                seg_start = max(rel_start, 0.0)
                seg_end = min(seg["end"] - trim_start, clip_duration) if clip_duration > 0 else seg["end"]
                if seg_end - seg_start < MIN_SEGMENT_SEC:
                    continue
                out.append({
                    "start": round(clip_start + seg_start, 3),
                    "end": round(clip_start + seg_end, 3),
                    "text": seg["text"],
                })
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return out
