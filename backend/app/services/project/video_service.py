# =====================================================
# 视频服务 — 分镜视频多版本管理 + 生成 + 上传
#
# 对应 project_shot_videos 表。
# 生成时基于采用帧图（或指定帧图）做图生视频，
# 通过 agnes_client.create_video_task 创建任务并轮询。
# =====================================================

import logging
from typing import List, Optional

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    ProjectShot,
    ProjectShotVideo,
    ProjectShotFrameImage,
)
from app.services.provider_registry import provider_registry
from app.services.project._async_gen import submit_video_task, claim_generation
from app.services.project._generation_history import record_manual_upload
from app.services.project.sse_manager import project_sse_manager

# 默认视频模型（仅当 Provider 未配置任何视频模型时使用）
_DEFAULT_VIDEO_MODEL_FALLBACK = "agnes-video-2.0"

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


async def _resolve_video_model(model: str) -> str:
    """
    解析实际使用的视频模型 ID：
    1. 用户传了 model 且 Provider 已配置该模型 → 直接使用
    2. 否则取 Provider 已配置的第一个视频模型
    3. 都没有则回退到 _DEFAULT_VIDEO_MODEL_FALLBACK（由上游报错）
    """
    available = await provider_registry.list_models_by_type("video")
    available_ids = [m.id for m in available if m.id]
    if available_ids:
        if model and model in available_ids:
            return model
        return available_ids[0]
    return model or _DEFAULT_VIDEO_MODEL_FALLBACK


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
) -> dict:
    """
    生成分镜视频（异步模式）

    提交到 video_poller_manager，立即返回 task_id。
    任务完成后前端调 claim 端点认领结果到 ProjectShotVideo。
    """
    shot = (
        await db.execute(select(ProjectShot).where(ProjectShot.id == shot_id))
    ).scalar_one_or_none()
    if not shot:
        return None

    # 确定来源帧图
    source_frame_id = frame_image_id or shot.active_frame_image_id
    if not source_frame_id:
        # 自动 fallback：取该分镜最新帧图（按 id 倒序）
        latest_frame = (
            await db.execute(
                select(ProjectShotFrameImage)
                .where(ProjectShotFrameImage.shot_id == shot_id)
                .order_by(ProjectShotFrameImage.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest_frame:
            source_frame_id = latest_frame.id
            logger.info("[视频生成] 无采用帧图，自动选择最新帧图: shot_id=%s frame_id=%s", shot_id, source_frame_id)
        else:
            raise ValueError("分镜没有帧图，无法生成视频（请先生成或上传帧图）")

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

    from app.models.project import Project
    project = (
        await db.execute(select(Project).where(Project.id == shot.project_id))
    ).scalar_one_or_none()
    width, height = _resolve_video_dimensions(
        project.resolution if project else "1280x720",
        project.aspect_ratio if project else "16:9",
    )

    prompt = shot.image_prompt or shot.visual_desc or shot.title or "scene"
    # 动态解析视频模型：优先用户传入，否则取 Provider 已配置的第一个视频模型
    used_model = await _resolve_video_model(model)
    logger.info(
        "[视频生成] 解析视频模型: input=%s → used=%s shot_id=%s",
        model or "(empty)", used_model, shot_id,
    )

    # 提交到 video_poller（poller 负责扣费 + AI 调用 + 轮询 + 写 Generation + confirm/refund）
    task_id = await submit_video_task(
        db, user_id, prompt, used_model, duration, num_frames,
        width, height, frame_rate=24, mode="image2video",
        image_url=frame_image.file_url,
        ref_type="project_video",
    )

    await project_sse_manager.push(
        shot.project_id,
        "generation_started",
        {
            "target": f"shot:{shot_id}:video",
            "version_type": "video",
            "user_id": user_id,
            "frame_image_id": source_frame_id,
            "task_id": task_id,
        },
    )

    return {
        "task_id": task_id,
        "shot_id": shot_id,
        "status": "pending",
        "prompt": prompt,
    }


async def claim_video(
    db: AsyncSession, shot_id: int, task_id: str, frame_image_id: Optional[int] = None
) -> Optional[ProjectShotVideo]:
    """任务完成后认领结果：从 Generation 拿 result_url，创建视频新版本"""
    shot = (
        await db.execute(select(ProjectShot).where(ProjectShot.id == shot_id))
    ).scalar_one_or_none()
    if not shot:
        return None

    gen = await claim_generation(db, task_id)
    if not gen or not gen.result_url:
        return None

    # 取来源帧图作为缩略图
    thumbnail_url = None
    source_frame_id = frame_image_id or shot.active_frame_image_id
    if source_frame_id:
        fi = (
            await db.execute(
                select(ProjectShotFrameImage).where(
                    ProjectShotFrameImage.id == source_frame_id
                )
            )
        ).scalar_one_or_none()
        if fi:
            thumbnail_url = fi.thumbnail_url

    version_no = await _next_version(db, shot_id)
    await _reset_active_flags(db, shot_id)

    video = ProjectShotVideo(
        shot_id=shot_id,
        version=version_no,
        is_active=True,
        is_manual=False,
        file_url=gen.result_url,
        thumbnail_url=thumbnail_url,
        frame_image_id=source_frame_id,
        prompt=gen.prompt or "",
        model=gen.model or "",
        generation_id=gen.id,
        duration_ms=gen.params.get("duration_ms") if gen.params else None,
        width=gen.params.get("width") if gen.params else None,
        height=gen.params.get("height") if gen.params else None,
        created_by="ai",
    )
    db.add(video)
    await db.flush()

    shot.active_video_id = video.id
    await db.commit()
    await db.refresh(video)

    await project_sse_manager.push(
        shot.project_id,
        "generation_completed",
        {
            "target": f"shot:{shot_id}:video",
            "version_id": video.id,
            "file_url": gen.result_url,
            "generation_id": gen.id,
            "task_id": task_id,
        },
    )
    return video


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

    # 写入生成历史（手动上传，不计费）
    gen_record = await record_manual_upload(
        db, user_id, "video", file_url, name=shot.title or f"分镜{shot.sequence_no}",
    )

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
        generation_id=gen_record.id,
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
