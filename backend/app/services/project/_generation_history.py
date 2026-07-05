# =====================================================
# 项目生成历史 + 积分扣费 共享 helper
#
# 把项目模块的图片/视频生成与原系统的：
#   - Generation 表（生成历史）
#   - credits_service（积分扣费）
#   - ProjectEntityAsset.generation_id / ProjectShotFrameImage.generation_id
# 串起来，让项目里生成的图/视频也能在 HistoryView 看到并扣费。
#
# 三种调用场景：
#   1. 同步图片生成（character/scene/prop/frame_image）
#      → charge_image_then_record()：预扣 → 调 AI → 成功写 Generation + confirm；失败 refund
#   2. 异步视频生成（video_service.generate_video）
#      → pre_charge_video_and_record()：预扣 + 写 pending Generation
#      → finalize_video_generation()：成功 confirm + 更新 url；失败 refund + 更新 status
#   3. 用户手动上传（不调 AI，不计费）
#      → record_manual_upload()：写 Generation(status=success, credits_consumed=0, mode=manual)
# =====================================================

import logging
from typing import Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.generation import Generation
from app.models.user import User
from app.services.credits_service import (
    get_image_cost_async,
    get_video_cost_async,
    consume_credits,
    confirm_credits,
    refund_credits,
)

logger = logging.getLogger("agnes_platform.project.history")


async def _get_user(db: AsyncSession, user_id: int) -> Optional[User]:
    """根据 user_id 查 User 对象（用于扣费）"""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# =====================================================
# 同步图片生成
# =====================================================

async def charge_image_then_record(
    db: AsyncSession,
    user_id: int,
    prompt: str,
    model: str,
    size: str,
    mode: str = "text2image",
    ref_type: str = "project_image",
    ref_id: Optional[str] = None,
) -> Tuple[int, str]:
    """
    图片生成前预扣费。返回 (cost, ref_id)。
    生成成功后调用 record_image_success 写 Generation + confirm；失败调用 refund_image_cost。
    """
    user = await _get_user(db, user_id)
    if not user:
        raise ValueError(f"用户 {user_id} 不存在")

    cost = await get_image_cost_async(db, mode=mode, size=size)
    ref_id = ref_id or f"project_image_{user_id}_{id(db)}"
    await consume_credits(
        db, user, cost,
        description=f"project/{mode}/{size}",
        ref_type=ref_type,
        ref_id=ref_id,
    )
    return cost, ref_id


async def record_image_success(
    db: AsyncSession,
    user_id: int,
    prompt: str,
    model: str,
    size: str,
    mode: str,
    result_url: str,
    ref_id: str,
    cost: int,
    is_public: bool = False,
) -> Generation:
    """图片生成成功后写 Generation + confirm 积分"""
    record = Generation(
        type="image",
        user_id=user_id,
        prompt=prompt,
        model=model,
        params={"size": size, "mode": mode},
        mode=mode,
        result_url=result_url,
        status="success",
        credits_consumed=cost,
        is_public=is_public,
        public_shared_at=None,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    try:
        await confirm_credits(db, user_id, ref_id)
    except Exception as e:
        logger.warning(f"[项目历史] confirm 积分失败 ref_id={ref_id}: {e}")

    logger.info(
        f"[项目历史] 图片生成记录已写入: id={record.id} user={user_id} cost={cost} mode={mode}"
    )
    return record


async def refund_image_cost(
    db: AsyncSession,
    user_id: int,
    ref_id: str,
    reason: str = "图片生成失败",
) -> None:
    """图片生成失败时退还预扣积分"""
    try:
        await refund_credits(db, user_id, ref_id, reason=reason)
    except Exception as e:
        logger.error(f"[项目历史] 退还图片积分失败 ref_id={ref_id}: {e}")


# =====================================================
# 异步视频生成
# =====================================================

async def pre_charge_video_and_record(
    db: AsyncSession,
    user_id: int,
    prompt: str,
    model: str,
    duration_ms: int,
    num_frames: Optional[int],
    mode: str = "image2video",
    task_id: Optional[str] = None,
    ref_type: str = "project_video",
) -> Tuple[Generation, int, str]:
    """
    视频生成前预扣费 + 写 pending 状态的 Generation
    Returns:
        (generation_record, cost, ref_id)
    """
    user = await _get_user(db, user_id)
    if not user:
        raise ValueError(f"用户 {user_id} 不存在")

    seconds = max(1, (duration_ms or 3000) / 1000.0)
    cost = await get_video_cost_async(
        db, mode=mode, seconds=int(seconds), num_frames=num_frames,
    )
    ref_id = task_id or f"project_video_{user_id}_{id(db)}"
    await consume_credits(
        db, user, cost,
        description=f"project/{mode}/{int(seconds)}s",
        ref_type=ref_type,
        ref_id=ref_id,
    )

    record = Generation(
        type="video",
        user_id=user.id,
        prompt=prompt,
        model=model,
        params={"mode": mode, "duration_ms": duration_ms, "num_frames": num_frames},
        mode=mode,
        result_url=None,
        status="pending",
        credits_consumed=cost,
        task_id=task_id,
        is_public=False,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    logger.info(
        f"[项目历史] 视频生成预扣已写入: id={record.id} user={user.id} cost={cost} task_id={task_id}"
    )
    return record, cost, ref_id


async def finalize_video_success(
    db: AsyncSession,
    generation_id: int,
    user_id: int,
    ref_id: str,
    result_url: str,
) -> None:
    """视频生成成功：更新 Generation.result_url/status + confirm 积分"""
    await db.execute(
        update(Generation)
        .where(Generation.id == generation_id)
        .values(result_url=result_url, status="success")
    )
    await db.commit()

    try:
        await confirm_credits(db, user_id, ref_id)
    except Exception as e:
        logger.warning(f"[项目历史] confirm 视频积分失败 ref_id={ref_id}: {e}")

    logger.info(f"[项目历史] 视频生成成功: generation_id={generation_id} url={result_url}")


async def finalize_video_failure(
    db: AsyncSession,
    generation_id: int,
    user_id: int,
    ref_id: str,
    error: str,
) -> None:
    """视频生成失败：更新 status=failed + refund 积分"""
    await db.execute(
        update(Generation)
        .where(Generation.id == generation_id)
        .values(status="failed")
    )
    await db.commit()

    try:
        await refund_credits(db, user_id, ref_id, reason=f"视频生成失败: {error}")
    except Exception as e:
        logger.error(f"[项目历史] 退还视频积分失败 ref_id={ref_id}: {e}")

    logger.info(f"[项目历史] 视频生成失败: generation_id={generation_id} error={error}")


# =====================================================
# 用户手动上传（不调 AI，不计费）
# =====================================================

async def record_manual_upload(
    db: AsyncSession,
    user_id: int,
    file_type: str,  # "image" | "video"
    file_url: str,
    name: str = "",
) -> Generation:
    """用户手动上传的图/视频也写一条 Generation 记录，便于在历史里看到"""
    record = Generation(
        type=file_type,
        user_id=user_id,
        prompt=f"(项目手动上传: {name})" if name else "(项目手动上传)",
        model=None,
        params={"source": "project_manual_upload"},
        mode="manual",
        result_url=file_url,
        status="success",
        credits_consumed=0,
        is_public=False,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    logger.info(f"[项目历史] 手动上传记录: id={record.id} type={file_type} user={user_id}")
    return record
