# =====================================================
# 视频服务 — 分镜视频多版本管理 + 生成 + 上传
#
# 对应 project_shot_videos 表。
# 生成时基于采用帧图（或指定帧图）做图生视频，
# 通过 agnes_client.create_video_task 创建任务并轮询。
# =====================================================

import asyncio
import logging
from typing import List, Optional

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    ProjectShot,
    ProjectShotVideo,
    ProjectShotFrameImage,
)
from app.services.agnes_client import agnes_client
from app.services.project.sse_manager import project_sse_manager

logger = logging.getLogger("agnes_platform.project.video")


# =====================================================
# 内部工具
# =====================================================

async def _next_version(db: AsyncSession, shot_id: int) -> int:
    """计算下一个版本号"""
    result = await db.execute(
        select(func.max(ProjectShotVideo.version)).where(
            ProjectShotVideo.shot_id == shot_id
        )
    )
    cur = result.scalar()
    return (cur or 0) + 1


async def _reset_active_flags(db: AsyncSession, shot_id: int) -> None:
    """将该分镜所有视频的 is_active 置为 False"""
    await db.execute(
        update(ProjectShotVideo)
        .where(ProjectShotVideo.shot_id == shot_id)
        .values(is_active=False)
    )


def _resolve_video_dimensions(
    project_resolution: str, aspect_ratio: str
) -> tuple:
    """
    根据项目分辨率/宽高比计算视频 width/height
    必须为 8 的倍数（避免编码失败导致 NOT_START）
    """
    # 默认 1280x720
    width, height = 1280, 720
    if project_resolution and "x" in project_resolution:
        try:
            w, h = project_resolution.lower().split("x", 1)
            width, height = int(w), int(h)
        except ValueError:
            pass

    # 按宽高比调整（以高度 720 为基准）
    if aspect_ratio and ":" in aspect_ratio:
        try:
            ar_w, ar_h = aspect_ratio.split(":", 1)
            ar_w_int, ar_h_int = int(ar_w), int(ar_h)
            base_h = 720
            base_w = int(round(base_h * ar_w_int / ar_h_int))
            # 必须是 8 的倍数
            base_w = (base_w // 8) * 8
            base_h = (base_h // 8) * 8
            width, height = base_w, base_h
        except ValueError:
            pass

    return width, height


def _duration_to_num_frames(duration_ms: int) -> int:
    """
    时长（毫秒）→ num_frames（必须满足 8n+1）
    25fps 基准：frames = duration_seconds * 25
    """
    seconds = max(1, duration_ms / 1000.0)
    raw = int(seconds * 24)  # 24fps
    # 调整到 8n+1
    n = (raw - 1) // 8
    num_frames = 8 * n + 1
    # 限制到合法范围
    valid = [81, 121, 161, 241, 321, 401, 441]
    for v in valid:
        if v >= num_frames:
            return v
    return 441


# =====================================================
# 视频版本查询
# =====================================================

async def list_videos(
    db: AsyncSession, shot_id: int
) -> List[ProjectShotVideo]:
    """列出分镜所有视频版本（按版本号倒序）"""
    result = await db.execute(
        select(ProjectShotVideo)
        .where(ProjectShotVideo.shot_id == shot_id)
        .order_by(ProjectShotVideo.version.desc())
    )
    return result.scalars().all()


async def get_video(
    db: AsyncSession, video_id: int
) -> Optional[ProjectShotVideo]:
    """获取视频版本"""
    result = await db.execute(
        select(ProjectShotVideo).where(ProjectShotVideo.id == video_id)
    )
    return result.scalar_one_or_none()


# =====================================================
# 视频生成
# =====================================================

async def generate_video(
    db: AsyncSession,
    shot_id: int,
    user_id: int,
    frame_image_id: Optional[int] = None,
    model: str = "",
    duration_ms: Optional[int] = 3000,
) -> Optional[ProjectShotVideo]:
    """
    生成分镜视频（图生视频，基于采用帧图或指定帧图）

    Args:
        frame_image_id: 来源帧图 ID，不传则用 shot.active_frame_image_id
        duration_ms: 视频时长（毫秒）
    """
    shot = (
        await db.execute(select(ProjectShot).where(ProjectShot.id == shot_id))
    ).scalar_one_or_none()
    if not shot:
        return None

    # 确定来源帧图
    source_frame_id = frame_image_id or shot.active_frame_image_id
    if not source_frame_id:
        raise ValueError("分镜没有采用帧图，无法生成视频")

    frame_image = (
        await db.execute(
            select(ProjectShotFrameImage).where(
                ProjectShotFrameImage.id == source_frame_id
            )
        )
    ).scalar_one_or_none()
    if not frame_image or not frame_image.file_url:
        raise ValueError("来源帧图不存在或无 URL")

    # 计算视频参数
    duration = duration_ms or shot.duration_ms or 3000
    num_frames = _duration_to_num_frames(duration)

    # 获取项目分辨率/宽高比
    from app.models.project import Project
    project = (
        await db.execute(select(Project).where(Project.id == shot.project_id))
    ).scalar_one_or_none()
    width, height = _resolve_video_dimensions(
        project.resolution if project else "1280x720",
        project.aspect_ratio if project else "16:9",
    )

    # 取 prompt（优先 image_prompt）
    prompt = shot.image_prompt or shot.visual_desc or shot.title or "scene"

    await project_sse_manager.push(
        shot.project_id,
        "generation_started",
        {
            "target": f"shot:{shot_id}:video",
            "version_type": "video",
            "user_id": user_id,
            "frame_image_id": source_frame_id,
        },
    )

    try:
        # 创建视频任务
        task = await agnes_client.create_video_task(
            prompt=prompt,
            model=model or "agnes-video-2.0",
            num_frames=num_frames,
            frame_rate=24,
            width=width,
            height=height,
            mode="ti2vid",  # 图生视频
            image=frame_image.file_url,
        )
        video_id = task.get("video_id") or task.get("task_id")
        if not video_id:
            raise RuntimeError("视频任务创建未返回 ID")

        # 创建新版本（status=running，文件 URL 等待轮询完成后回填）
        version_no = await _next_version(db, shot_id)
        await _reset_active_flags(db, shot_id)

        video = ProjectShotVideo(
            shot_id=shot_id,
            version=version_no,
            is_active=True,
            is_manual=False,
            file_url=None,  # 等待轮询完成
            thumbnail_url=frame_image.thumbnail_url,
            frame_image_id=source_frame_id,
            prompt=prompt,
            model=model or "agnes-video-2.0",
            duration_ms=duration,
            width=width,
            height=height,
            created_by="ai",
        )
        db.add(video)
        await db.flush()

        shot.active_video_id = video.id
        await db.commit()
        await db.refresh(video)

        await project_sse_manager.push(
            shot.project_id,
            "generation_progress",
            {
                "target": f"shot:{shot_id}:video",
                "version_id": video.id,
                "progress": 0,
                "status": "running",
            },
        )

        # 后台轮询视频状态（不阻塞当前请求）
        asyncio.create_task(
            _poll_video_and_update(
                shot.project_id, shot_id, video.id, video_id
            )
        )
        return video
    except Exception as e:
        await project_sse_manager.push(
            shot.project_id,
            "generation_failed",
            {"target": f"shot:{shot_id}:video", "error": str(e)},
        )
        raise


async def _poll_video_and_update(
    project_id: int, shot_id: int, video_record_id: int, task_video_id: str
) -> None:
    """
    后台轮询视频任务状态，完成后回填 file_url 并推送 SSE

    使用 new_async_session 创建独立 session（不依赖原请求 session）
    """
    from app.core.database import new_async_session

    db = new_async_session()
    try:
        # 轮询 agnes_client.poll_video_status
        result = await agnes_client.poll_video_status(task_video_id)
        status = result.get("status", "")
        video_url = result.get("video_url") or result.get("url", "")
        duration_ms = result.get("duration_ms")
        width = result.get("width")
        height = result.get("height")

        # 更新记录
        video = (
            await db.execute(
                select(ProjectShotVideo).where(
                    ProjectShotVideo.id == video_record_id
                )
            )
        ).scalar_one_or_none()
        if not video:
            return

        if status == "succeeded" and video_url:
            video.file_url = video_url
            if duration_ms:
                video.duration_ms = duration_ms
            if width:
                video.width = width
            if height:
                video.height = height
            await db.commit()

            await project_sse_manager.push(
                project_id,
                "generation_completed",
                {
                    "target": f"shot:{shot_id}:video",
                    "version_id": video_record_id,
                    "file_url": video_url,
                },
            )
        elif status == "failed":
            await project_sse_manager.push(
                project_id,
                "generation_failed",
                {
                    "target": f"shot:{shot_id}:video",
                    "error": result.get("error", "视频生成失败"),
                },
            )
        else:
            # 仍在处理中，推送进度
            await project_sse_manager.push(
                project_id,
                "generation_progress",
                {
                    "target": f"shot:{shot_id}:video",
                    "version_id": video_record_id,
                    "status": status,
                    "progress": result.get("progress", 0),
                },
            )
    except Exception as e:
        logger.error(f"轮询视频状态失败 video_record_id={video_record_id}: {e}")
        await project_sse_manager.push(
            project_id,
            "generation_failed",
            {
                "target": f"shot:{shot_id}:video",
                "error": f"轮询失败: {e}",
            },
        )
    finally:
        await db.close()


# =====================================================
# 上传视频
# =====================================================

async def upload_video(
    db: AsyncSession,
    shot_id: int,
    user_id: int,
    file_url: str,
    thumbnail_url: str = "",
    duration_ms: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    file_size: Optional[int] = None,
) -> Optional[ProjectShotVideo]:
    """用户手动上传视频作为新版本（G1）"""
    shot = (
        await db.execute(select(ProjectShot).where(ProjectShot.id == shot_id))
    ).scalar_one_or_none()
    if not shot:
        return None

    version_no = await _next_version(db, shot_id)
    await _reset_active_flags(db, shot_id)

    video = ProjectShotVideo(
        shot_id=shot_id,
        version=version_no,
        is_active=True,
        is_manual=True,
        file_url=file_url,
        thumbnail_url=thumbnail_url,
        prompt="(用户上传)",
        duration_ms=duration_ms,
        width=width,
        height=height,
        file_size=file_size,
        created_by="manual",
    )
    db.add(video)
    await db.flush()

    shot.active_video_id = video.id
    await db.commit()
    await db.refresh(video)

    await project_sse_manager.push(
        shot.project_id,
        "active_version_changed",
        {
            "target": f"shot:{shot_id}:video",
            "version_id": video.id,
            "file_url": file_url,
        },
    )
    return video


# =====================================================
# 切换激活版 / 删除版本
# =====================================================

async def set_active_video(
    db: AsyncSession, shot_id: int, version_id: int
) -> Optional[ProjectShotVideo]:
    """设为激活版"""
    video = await get_video(db, version_id)
    if not video or video.shot_id != shot_id:
        return None

    await _reset_active_flags(db, shot_id)
    video.is_active = True

    shot = (
        await db.execute(select(ProjectShot).where(ProjectShot.id == shot_id))
    ).scalar_one_or_none()
    if shot:
        shot.active_video_id = video.id
        project_id = shot.project_id
    else:
        project_id = None

    await db.commit()
    await db.refresh(video)

    if project_id:
        await project_sse_manager.push(
            project_id,
            "active_version_changed",
            {
                "target": f"shot:{shot_id}:video",
                "version_id": version_id,
                "file_url": video.file_url,
            },
        )
    return video


async def delete_video(
    db: AsyncSession, shot_id: int, version_id: int
) -> bool:
    """删除版本（不允许删除激活版）"""
    video = await get_video(db, version_id)
    if not video or video.shot_id != shot_id:
        return False
    if video.is_active:
        return False

    await db.delete(video)

    shot = (
        await db.execute(select(ProjectShot).where(ProjectShot.id == shot_id))
    ).scalar_one_or_none()
    if shot and shot.active_video_id == version_id:
        shot.active_video_id = None

    await db.commit()
    return True
