# =====================================================
# 积分明细路由 — 查询当前用户的积分变动流水
#
# 接口：
#   - GET /api/credits/transactions：查询当前登录用户的积分变动明细
#     支持分页、按类型过滤（recharge/consume/refund/adjust）
#   - GET /api/credits/transactions/all：[管理员] 查询所有用户的积分变动明细
#   - GET /api/credits/estimate：预估本次生成任务需要消耗的积分
#     支持 image / video 两种类型，参数与生成接口保持一致
# =====================================================

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.core.database import get_async_db
from app.core.security import get_current_user, get_current_admin_user
from app.models.user import User
from app.models.credit_transaction import CreditTransaction
from app.services.credits_service import get_image_cost_async, get_video_cost_async

router = APIRouter()


@router.get("/credits/estimate", summary="预估本次生成任务需要消耗的积分")
async def estimate_cost(
    type: str = Query(..., description="任务类型：image / video"),
    mode: Optional[str] = Query(None, description="生成模式：text2image / image2image / text2video / image2video / keyframes"),
    size: Optional[str] = Query(None, description="图片尺寸，例如 1024x1024（type=image 时使用）"),
    seconds: Optional[int] = Query(None, description="视频时长（秒，type=video 时使用）"),
    num_frames: Optional[int] = Query(None, description="视频帧数（type=video 时使用）"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """根据任务类型和参数预估本次生成需要消耗的积分数量"""
    if type == "image":
        cost = await get_image_cost_async(db, mode=mode or "text2image", size=size)
    elif type == "video":
        cost = await get_video_cost_async(
            db,
            mode=mode or "text2video",
            seconds=seconds or 5,
            num_frames=num_frames,
        )
    else:
        raise HTTPException(status_code=400, detail="type 必须是 image 或 video")

    return {
        "type": type,
        "mode": mode,
        "cost": cost,
        "balance": current_user.credits,
        "sufficient": current_user.credits >= cost,
    }


@router.get("/credits/transactions", summary="查询当前用户的积分变动明细")
async def list_my_transactions(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    type: Optional[str] = Query(None, description="按类型过滤：recharge/consume/refund/adjust"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """查询当前登录用户的积分变动明细，按时间倒序排列"""
    # 构建查询条件
    conditions = [CreditTransaction.user_id == current_user.id]
    if type:
        conditions.append(CreditTransaction.type == type)

    # 查询总数
    count_stmt = select(func.count()).select_from(CreditTransaction).where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    # 分页查询
    stmt = (
        select(CreditTransaction)
        .where(*conditions)
        .order_by(CreditTransaction.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    return {
        "items": [item.to_dict() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/credits/transactions/all", summary="[管理员] 查询所有用户的积分变动明细")
async def list_all_transactions(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    type: Optional[str] = Query(None, description="按类型过滤：recharge/consume/refund/adjust"),
    user_id: Optional[int] = Query(None, description="按用户 ID 过滤"),
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    """管理员查询所有用户的积分变动明细，按时间倒序排列"""
    conditions = []
    if type:
        conditions.append(CreditTransaction.type == type)
    if user_id:
        conditions.append(CreditTransaction.user_id == user_id)

    count_stmt = select(func.count()).select_from(CreditTransaction).where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(CreditTransaction)
        .where(*conditions)
        .order_by(CreditTransaction.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    # 管理员视图额外返回用户名（便于展示）
    user_ids = {item.user_id for item in items}
    user_map = {}
    if user_ids:
        user_result = await db.execute(select(User.id, User.username).filter(User.id.in_(user_ids)))
        for uid, uname in user_result:
            user_map[uid] = uname

    return {
        "items": [
            {**item.to_dict(), "username": user_map.get(item.user_id, "")}
            for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
