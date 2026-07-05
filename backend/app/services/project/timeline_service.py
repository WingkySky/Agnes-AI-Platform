# =====================================================
# 时间线服务 — 多轨时间线片段管理 + 自动初始化（Phase 2）
#
# 核心能力:
#   1. init_timeline: 从分镜数据自动初始化时间线（视频轨 + 音频轨）
#   2. list_clips: 列出所有片段（按轨道 + start_time 排序）
#   3. create_clip / update_clip / delete_clip: 片段 CRUD
#   4. get_timeline_data: 获取完整时间线数据（含字幕样式）
#   5. save_timeline_data: 保存时间线草稿数据（projects.timeline_data）
#   6. get_subtitle_style / update_subtitle_style: 字幕样式管理
#
# 轨道类型:
#   - video (track_index 0=主轨, 1=PIP画中画)
#   - audio (track_index 0=TTS, 1=BGM)
#   - subtitle (track_index 0=主字幕, 1=次字幕)
# =====================================================

import logging
from typing import List, Optional, Dict, Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    Project,
    ProjectShot,
    ProjectShotVideo,
    ProjectShotAudio,
    ProjectTimelineClip,
)
from app.services.project.sse_manager import project_sse_manager
from app.services.project.subtitle_service import DEFAULT_SUBTITLE_STYLE

logger = logging.getLogger("agnes_platform.project.timeline")


# =====================================================
# 时间线初始化
# =====================================================

async def init_timeline(db: AsyncSession, project_id: int) -> Dict[str, Any]:
    """
    从分镜数据自动初始化时间线

    自动生成:
    - 视频轨 0：每个分镜的采用视频（按 sort_order）
    - 音频轨 0：每个分镜的采用音频（如有）
    - 字幕轨：不自动生成（由 subtitle_service.generate_subtitles 单独触发）

    返回初始化统计
    """
    # 清空旧的时间线片段
    await db.execute(
        delete(ProjectTimelineClip).where(ProjectTimelineClip.project_id == project_id)
    )

    # 取所有分镜（按 sort_order）
    shots = (await db.execute(
        select(ProjectShot)
        .where(ProjectShot.project_id == project_id)
        .order_by(ProjectShot.sort_order)
    )).scalars().all()

    video_clips: List[ProjectTimelineClip] = []
    audio_clips: List[ProjectTimelineClip] = []
    current_time = 0.0

    for shot in shots:
        shot_duration = (shot.duration_ms or 3000) / 1000.0

        # 视频轨 0：采用视频
        if shot.active_video_id:
            video = (await db.execute(
                select(ProjectShotVideo).where(ProjectShotVideo.id == shot.active_video_id)
            )).scalar_one_or_none()
            if video and video.file_url:
                # 视频实际时长优先用 video.duration_ms
                video_duration = (video.duration_ms or shot.duration_ms or 3000) / 1000.0
                clip = ProjectTimelineClip(
                    project_id=project_id,
                    track_type="video",
                    track_index=0,
                    source_type="shot_video",
                    source_id=video.id,
                    shot_id=shot.id,
                    start_time=current_time,
                    duration=video_duration,
                    transition_type="fade",  # 默认淡入淡出
                    transition_duration=0.5,
                    sort_order=len(video_clips),
                )
                db.add(clip)
                video_clips.append(clip)
                shot_duration = video_duration  # 推进时间轴用视频时长

        # 音频轨 0：采用音频
        if shot.active_audio_id:
            audio = (await db.execute(
                select(ProjectShotAudio).where(ProjectShotAudio.id == shot.active_audio_id)
            )).scalar_one_or_none()
            if audio and audio.file_url:
                audio_duration = (audio.duration_ms or shot.duration_ms or 3000) / 1000.0
                clip = ProjectTimelineClip(
                    project_id=project_id,
                    track_type="audio",
                    track_index=0,
                    source_type="shot_audio",
                    source_id=audio.id,
                    shot_id=shot.id,
                    start_time=current_time,
                    duration=audio_duration,
                    sort_order=len(audio_clips),
                )
                db.add(clip)
                audio_clips.append(clip)

        current_time += shot_duration

    await db.commit()

    # 更新项目的 timeline_data（记录初始化时间）
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project:
        timeline_data = project.timeline_data or {}
        timeline_data["initialized"] = True
        timeline_data["total_duration"] = current_time
        project.timeline_data = timeline_data
        project.total_duration = current_time
        await db.commit()

    await project_sse_manager.push(project_id, "timeline_initialized", {
        "video_clips": len(video_clips),
        "audio_clips": len(audio_clips),
        "total_duration": current_time,
    })

    return {
        "video_clips": len(video_clips),
        "audio_clips": len(audio_clips),
        "total_duration": current_time,
    }


# =====================================================
# 片段 CRUD
# =====================================================

async def list_clips(
    db: AsyncSession, project_id: int,
    track_type: Optional[str] = None,
) -> List[ProjectTimelineClip]:
    """列出时间线片段（按轨道 + start_time 排序）"""
    query = select(ProjectTimelineClip).where(ProjectTimelineClip.project_id == project_id)
    if track_type:
        query = query.where(ProjectTimelineClip.track_type == track_type)
    query = query.order_by(
        ProjectTimelineClip.track_type,
        ProjectTimelineClip.track_index,
        ProjectTimelineClip.start_time,
    )
    result = await db.execute(query)
    return result.scalars().all()


async def create_clip(db: AsyncSession, project_id: int, data: dict) -> ProjectTimelineClip:
    """创建时间线片段"""
    clip = ProjectTimelineClip(project_id=project_id, **data)
    db.add(clip)
    await db.commit()
    await db.refresh(clip)
    await project_sse_manager.push(project_id, "timeline_clip_created", {"clip_id": clip.id})
    return clip


async def update_clip(
    db: AsyncSession, project_id: int, clip_id: int, data: dict
) -> Optional[ProjectTimelineClip]:
    """更新时间线片段"""
    clip = (await db.execute(
        select(ProjectTimelineClip).where(
            ProjectTimelineClip.id == clip_id,
            ProjectTimelineClip.project_id == project_id,
        )
    )).scalar_one_or_none()
    if not clip:
        return None
    for k, v in data.items():
        if hasattr(clip, k) and v is not None:
            setattr(clip, k, v)
    await db.commit()
    await db.refresh(clip)
    await project_sse_manager.push(project_id, "timeline_clip_updated", {"clip_id": clip_id})
    return clip


async def delete_clip(db: AsyncSession, project_id: int, clip_id: int) -> bool:
    """删除时间线片段"""
    clip = (await db.execute(
        select(ProjectTimelineClip).where(
            ProjectTimelineClip.id == clip_id,
            ProjectTimelineClip.project_id == project_id,
        )
    )).scalar_one_or_none()
    if not clip:
        return False
    await db.delete(clip)
    await db.commit()
    await project_sse_manager.push(project_id, "timeline_clip_deleted", {"clip_id": clip_id})
    return True


# =====================================================
# 时间线数据聚合
# =====================================================

async def get_timeline_data(db: AsyncSession, project_id: int) -> Dict[str, Any]:
    """获取完整时间线数据（片段 + 字幕样式 + 总时长）"""
    clips = await list_clips(db, project_id)
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()

    timeline_data = (project.timeline_data if project else {}) or {}
    subtitle_style = timeline_data.get("subtitle_style", DEFAULT_SUBTITLE_STYLE)
    total_duration = timeline_data.get("total_duration", project.total_duration if project else 0)

    return {
        "clips": [
            {
                "id": c.id,
                "project_id": c.project_id,
                "track_type": c.track_type,
                "track_index": c.track_index,
                "source_type": c.source_type,
                "source_id": c.source_id,
                "shot_id": c.shot_id,
                "start_time": c.start_time,
                "duration": c.duration,
                "trim_start": c.trim_start,
                "trim_end": c.trim_end,
                "transition_type": c.transition_type,
                "transition_duration": c.transition_duration,
                "subtitle_text": c.subtitle_text,
                "sort_order": c.sort_order,
            }
            for c in clips
        ],
        "subtitle_style": subtitle_style,
        "total_duration": total_duration,
    }


async def save_timeline_data(
    db: AsyncSession, project_id: int,
    subtitle_style: Optional[Dict[str, Any]] = None,
    draft: Optional[Dict[str, Any]] = None,
) -> Optional[Project]:
    """保存时间线草稿数据（字幕样式、轨道折叠状态等）"""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        return None
    timeline_data = project.timeline_data or {}
    if subtitle_style:
        timeline_data["subtitle_style"] = subtitle_style
    if draft:
        timeline_data["draft"] = draft
    project.timeline_data = timeline_data
    await db.commit()
    await db.refresh(project)
    return project


# =====================================================
# 字幕样式管理
# =====================================================

async def get_subtitle_style(db: AsyncSession, project_id: int) -> Dict[str, Any]:
    """获取字幕样式"""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        return DEFAULT_SUBTITLE_STYLE
    timeline_data = project.timeline_data or {}
    return timeline_data.get("subtitle_style", DEFAULT_SUBTITLE_STYLE)


async def update_subtitle_style(
    db: AsyncSession, project_id: int, style: Dict[str, Any]
) -> Optional[Project]:
    """更新字幕样式"""
    return await save_timeline_data(db, project_id, subtitle_style=style)
