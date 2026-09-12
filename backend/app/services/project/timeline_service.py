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
    ProjectShotFrameImage,
    ProjectTimelineClip,
)
from app.services.project.bgm_library import list_bgms, get_bgm_by_id
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
# 高级编辑操作 — 分割 / 波纹删除
# =====================================================

async def split_clip(
    db: AsyncSession, project_id: int, clip_id: int, split_time: float
) -> Optional[Dict[str, Any]]:
    """
    在指定时间点分割时间线片段

    参数:
    - clip_id: 待分割的片段 ID
    - split_time: 分割点（项目时间线上的绝对时间，秒）

    行为:
    - 找到包含 split_time 的片段
    - 原片段保留 [start_time, split_time] 区间，duration 调整为 split_time - start_time
    - 新片段承担 [split_time, start_time + 原duration] 区间，trim_start 相应调整
    - 新片段继承原片段的 source/source_type/transition 等字段

    返回: {"original": {...}, "new": {...}} 或 None（片段不存在/分割点不在片段范围内）
    """
    clip = (await db.execute(
        select(ProjectTimelineClip).where(
            ProjectTimelineClip.id == clip_id,
            ProjectTimelineClip.project_id == project_id,
        )
    )).scalar_one_or_none()
    if not clip:
        return None

    # 分割点必须在片段范围内（不允许在边界上分割）
    clip_start = float(clip.start_time or 0.0)
    clip_duration = float(clip.duration or 0.0)
    clip_end = clip_start + clip_duration
    # 容差 0.01s，避免浮点误差导致无法分割
    if split_time <= clip_start + 0.01 or split_time >= clip_end - 0.01:
        return None

    # 原片段保留前半部分
    original_new_duration = split_time - clip_start
    # 新片段承担后半部分
    split_offset = split_time - clip_start  # 分割点在片段内的偏移
    new_clip_duration = clip_duration - split_offset
    new_clip_trim_start = float(clip.trim_start or 0.0) + split_offset

    # 更新原片段 duration
    clip.duration = original_new_duration
    # 原片段的转场不应延续到新片段（转场是片段出场时的效果）
    # 保留原片段的转场设置不变（用户可后续调整）

    # 创建新片段（承担后半部分）
    new_clip = ProjectTimelineClip(
        project_id=project_id,
        track_type=clip.track_type,
        track_index=clip.track_index,
        source_type=clip.source_type,
        source_id=clip.source_id,
        shot_id=clip.shot_id,
        start_time=split_time,
        duration=new_clip_duration,
        trim_start=new_clip_trim_start,
        trim_end=clip.trim_end,
        transition_type="none",  # 新片段出场不带转场（避免叠加）
        transition_duration=0.0,
        subtitle_text=clip.subtitle_text,
        sort_order=clip.sort_order + 1,
    )
    db.add(new_clip)
    await db.commit()
    await db.refresh(new_clip)

    await project_sse_manager.push(project_id, "timeline_clip_updated", {"clip_id": clip_id})
    await project_sse_manager.push(project_id, "timeline_clip_created", {"clip_id": new_clip.id})

    return {
        "original": {
            "id": clip.id, "start_time": clip.start_time, "duration": clip.duration,
            "trim_start": clip.trim_start,
        },
        "new": {
            "id": new_clip.id, "start_time": new_clip.start_time, "duration": new_clip.duration,
            "trim_start": new_clip.trim_start,
        },
    }


async def ripple_delete_clip(db: AsyncSession, project_id: int, clip_id: int) -> Optional[Dict[str, Any]]:
    """
    波纹删除：删除片段后，同轨后续片段自动前移填补空隙

    行为:
    - 删除指定片段
    - 找到同 track_type + track_index 中 start_time 大于被删片段 end_time 的所有片段
    - 将这些片段的 start_time 减去被删片段的 duration（前移填补空隙）

    返回: {"deleted_clip_id": id, "shifted_clips": [...]} 或 None
    """
    clip = (await db.execute(
        select(ProjectTimelineClip).where(
            ProjectTimelineClip.id == clip_id,
            ProjectTimelineClip.project_id == project_id,
        )
    )).scalar_one_or_none()
    if not clip:
        return None

    deleted_duration = float(clip.duration or 0.0)
    deleted_end = float(clip.start_time or 0.0) + deleted_duration
    track_type = clip.track_type
    track_index = clip.track_index

    # 删除片段
    await db.delete(clip)
    await db.commit()

    # 找到同轨后续片段并前移
    later_clips = (await db.execute(
        select(ProjectTimelineClip).where(
            ProjectTimelineClip.project_id == project_id,
            ProjectTimelineClip.track_type == track_type,
            ProjectTimelineClip.track_index == track_index,
            ProjectTimelineClip.start_time >= deleted_end - 0.01,  # 容差
        ).order_by(ProjectTimelineClip.start_time)
    )).scalars().all()

    shifted = []
    for c in later_clips:
        c.start_time = max(0.0, float(c.start_time or 0.0) - deleted_duration)
        shifted.append({"clip_id": c.id, "new_start_time": c.start_time})
    if shifted:
        await db.commit()

    await project_sse_manager.push(project_id, "timeline_clip_deleted", {"clip_id": clip_id, "ripple": True})

    return {
        "deleted_clip_id": clip_id,
        "shifted_clips": shifted,
        "shift_duration": deleted_duration,
    }


# =====================================================
# 时间线数据聚合
# =====================================================

async def get_timeline_data(db: AsyncSession, project_id: int) -> Dict[str, Any]:
    """
    获取完整时间线数据（片段 + 字幕样式 + 总时长）

    为支持前端预览，每个 clip 附带源文件信息（source_file_url / source_duration_ms /
    source_width / source_height / source_thumbnail_url），避免前端 N+1 查询。
    """
    clips = await list_clips(db, project_id)
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()

    timeline_data = (project.timeline_data if project else {}) or {}
    subtitle_style = timeline_data.get("subtitle_style", DEFAULT_SUBTITLE_STYLE)
    total_duration = timeline_data.get("total_duration", project.total_duration if project else 0)

    # 批量预取视频/音频/帧图源数据，避免逐 clip N+1 查询
    video_ids = {c.source_id for c in clips if c.source_type == "shot_video" and c.source_id}
    audio_ids = {c.source_id for c in clips if c.source_type == "shot_audio" and c.source_id}
    frame_image_ids = {c.source_id for c in clips if c.source_type == "shot_frame_image" and c.source_id}

    video_map: Dict[int, ProjectShotVideo] = {}
    audio_map: Dict[int, ProjectShotAudio] = {}
    frame_image_map: Dict[int, ProjectShotFrameImage] = {}

    if video_ids:
        rows = (
            await db.execute(
                select(ProjectShotVideo).where(ProjectShotVideo.id.in_(video_ids))
            )
        ).scalars().all()
        video_map = {v.id: v for v in rows}

    if audio_ids:
        rows = (
            await db.execute(
                select(ProjectShotAudio).where(ProjectShotAudio.id.in_(audio_ids))
            )
        ).scalars().all()
        audio_map = {a.id: a for a in rows}

    if frame_image_ids:
        rows = (
            await db.execute(
                select(ProjectShotFrameImage).where(ProjectShotFrameImage.id.in_(frame_image_ids))
            )
        ).scalars().all()
        frame_image_map = {f.id: f for f in rows}

    # 序列化片段，注入 source_* 字段
    serialized_clips = []
    for c in clips:
        item: Dict[str, Any] = {
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
            "source_file_url": None,
            "source_duration_ms": None,
            "source_width": None,
            "source_height": None,
            "source_thumbnail_url": None,
        }

        # 根据来源类型注入源文件信息
        if c.source_type == "shot_video" and c.source_id and c.source_id in video_map:
            v = video_map[c.source_id]
            item["source_file_url"] = v.file_url
            item["source_duration_ms"] = v.duration_ms
            item["source_width"] = v.width
            item["source_height"] = v.height
            item["source_thumbnail_url"] = v.thumbnail_url
        elif c.source_type == "shot_audio" and c.source_id and c.source_id in audio_map:
            a = audio_map[c.source_id]
            item["source_file_url"] = a.file_url
            item["source_duration_ms"] = a.duration_ms
        elif c.source_type == "shot_frame_image" and c.source_id and c.source_id in frame_image_map:
            f = frame_image_map[c.source_id]
            item["source_file_url"] = f.file_url
            item["source_duration_ms"] = int(c.duration * 1000)  # 静态图无 duration_ms，用片段 duration 反推
            item["source_width"] = f.width
            item["source_height"] = f.height
            item["source_thumbnail_url"] = f.thumbnail_url
        elif c.source_type == "bgm" and c.source_ref:
            # BGM 通过 source_ref 字符串引用，url 由前端拼接 /bgms/{bgm_id}/file
            bgm = get_bgm_by_id(c.source_ref)
            if bgm:
                item["source_file_url"] = f"/api/projects/{project_id}/bgms/{c.source_ref}/file"
                item["source_duration_ms"] = int(bgm["duration"] * 1000)

        serialized_clips.append(item)

    return {
        "clips": serialized_clips,
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


# =====================================================
# 项目素材库聚合（Phase 2 增强）
# =====================================================

async def get_media_library(db: AsyncSession, project_id: int) -> Dict[str, Any]:
    """
    获取项目素材库（4 类素材聚合）— Phase 2 增强

    返回:
    - videos: 分镜视频列表（按 shot.sort_order 排序）
    - audios: 配音音频列表
    - frame_images: 帧图列表（静态图，duration_ms 默认 3000）
    - bgms: BGM 库（含 file_url）
    """
    # 查所有分镜（带排序）
    shots = (
        await db.execute(
            select(ProjectShot)
            .where(ProjectShot.project_id == project_id)
            .order_by(ProjectShot.sort_order.asc())
        )
    ).scalars().all()
    shot_map = {s.id: s for s in shots}

    # 查所有视频（关联分镜的 active_video_id）
    active_video_ids = [s.active_video_id for s in shots if s.active_video_id]
    videos: List[Dict[str, Any]] = []
    if active_video_ids:
        rows = (
            await db.execute(
                select(ProjectShotVideo).where(ProjectShotVideo.id.in_(active_video_ids))
            )
        ).scalars().all()
        for v in rows:
            shot = shot_map.get(v.shot_id)
            videos.append({
                "id": v.id,
                "type": "shot_video",
                "name": f"分镜{(shot.sequence_no if shot else '?')}视频",
                "file_url": v.file_url or "",
                "thumbnail_url": v.thumbnail_url,
                "duration_ms": v.duration_ms or 3000,
                "width": v.width,
                "height": v.height,
                "shot_id": v.shot_id,
                "meta": {},
            })

    # 查所有音频（关联分镜的 active_audio_id）
    active_audio_ids = [s.active_audio_id for s in shots if s.active_audio_id]
    audios: List[Dict[str, Any]] = []
    if active_audio_ids:
        rows = (
            await db.execute(
                select(ProjectShotAudio).where(ProjectShotAudio.id.in_(active_audio_ids))
            )
        ).scalars().all()
        for a in rows:
            shot = shot_map.get(a.shot_id)
            audios.append({
                "id": a.id,
                "type": "shot_audio",
                "name": f"分镜{(shot.sequence_no if shot else '?')}配音",
                "file_url": a.file_url or "",
                "thumbnail_url": None,
                "duration_ms": a.duration_ms or 3000,
                "width": None,
                "height": None,
                "shot_id": a.shot_id,
                "meta": {"voice_name": a.voice_name},
            })

    # 查所有帧图（active_frame_image_id，duration_ms 默认 3000）
    active_frame_ids = [s.active_frame_image_id for s in shots if s.active_frame_image_id]
    frame_images: List[Dict[str, Any]] = []
    if active_frame_ids:
        rows = (
            await db.execute(
                select(ProjectShotFrameImage).where(ProjectShotFrameImage.id.in_(active_frame_ids))
            )
        ).scalars().all()
        for f in rows:
            shot = shot_map.get(f.shot_id)
            frame_images.append({
                "id": f.id,
                "type": "shot_frame_image",
                "name": f"分镜{(shot.sequence_no if shot else '?')}帧图",
                "file_url": f.file_url or "",
                "thumbnail_url": f.thumbnail_url,
                "duration_ms": 3000,  # 静态图默认 3 秒
                "width": f.width,
                "height": f.height,
                "shot_id": f.shot_id,
                "meta": {"is_static_image": True},
            })

    # BGM 库（含 file_url 路径）
    bgm_list = list_bgms()
    bgms: List[Dict[str, Any]] = []
    for b in bgm_list:
        if not b.get("available"):
            continue
        bgms.append({
            "id": abs(hash(b["id"])) % (10**9),  # 字符串 id 转数字 id 供前端使用
            "type": "bgm",
            "name": b["name"],
            "file_url": f"/api/projects/{project_id}/bgms/{b['id']}/file",
            "thumbnail_url": None,
            "duration_ms": int(b["duration"] * 1000),
            "width": None,
            "height": None,
            "shot_id": None,
            "meta": {"mood": b["mood"], "bgm_id": b["id"]},  # bgm_id 字符串存在 meta
        })

    return {
        "videos": videos,
        "audios": audios,
        "frame_images": frame_images,
        "bgms": bgms,
    }
