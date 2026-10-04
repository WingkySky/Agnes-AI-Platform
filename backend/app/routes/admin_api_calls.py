# =====================================================
# 上游调用记账管理端点（/api/admin/api-calls）
# 管理员只读观测：调用列表（分页筛选）+ 按日×类目聚合摘要
# 查询统一 db.scalars(select(...)) 写法（项目惯例）
# =====================================================

from datetime import datetime, timedelta, date, time as dtime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.response import ok
from app.core.security import get_current_admin_user
from app.models.api_call_log import ApiCallLog
from app.models.user import User

router = APIRouter(prefix="/admin/api-calls", tags=["管理员-上游调用记账"])


@router.get("", summary="查询上游调用日志（分页筛选）")
async def list_api_calls(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_admin_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    provider_id: Optional[int] = Query(None, description="渠道 ID"),
    model: Optional[str] = Query(None, description="模型 ID（精确）"),
    call_type: Optional[str] = Query(None, description="调用类型"),
    status: Optional[str] = Query(None, description="success / failed"),
    error_category: Optional[str] = Query(None, description="错误类目"),
    since: Optional[datetime] = Query(None, description="起始时间（ISO）"),
    before: Optional[datetime] = Query(None, description="截止时间（ISO）"),
):
    del current_user  # 仅管理员门槛
    conditions = []
    if provider_id is not None:
        conditions.append(ApiCallLog.provider_id == provider_id)
    if model:
        conditions.append(ApiCallLog.model == model)
    if call_type:
        conditions.append(ApiCallLog.call_type == call_type)
    if status:
        conditions.append(ApiCallLog.status == status)
    if error_category:
        conditions.append(ApiCallLog.error_category == error_category)
    if since:
        conditions.append(ApiCallLog.created_at >= since)
    if before:
        conditions.append(ApiCallLog.created_at < before)

    base = select(ApiCallLog)
    if conditions:
        base = base.where(*conditions)
    total = (await db.scalars(select(func.count()).select_from(base.subquery()))).first() or 0
    rows = (
        await db.scalars(
            base.order_by(ApiCallLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()

    return ok(data={
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "calls": [row.to_dict() for row in rows],
    })


@router.get("/summary", summary="上游调用聚合摘要（近 N 天，按日×类目）")
async def api_calls_summary(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_admin_user),
    days: int = Query(7, ge=1, le=30, description="统计窗口（天）"),
):
    del current_user  # 仅管理员门槛
    since = datetime.utcnow() - timedelta(days=days)

    async def _count(extra=None) -> int:
        stmt = select(func.count()).select_from(ApiCallLog).where(ApiCallLog.created_at >= since)
        if extra is not None:
            stmt = stmt.where(extra)
        return int((await db.scalars(stmt)).first() or 0)

    total = await _count()
    failed = await _count(ApiCallLog.status == "failed")

    # 按日 × 状态计数（逐日小查询，管理端低频调用可接受）
    daily: list[dict] = []
    today = date.today()
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        day_start = datetime.combine(day, dtime.min)
        day_end = datetime.combine(day + timedelta(days=1), dtime.min)
        for status in ("success", "failed"):
            count = int((await db.scalars(
                select(func.count()).select_from(ApiCallLog)
                .where(ApiCallLog.created_at >= day_start)
                .where(ApiCallLog.created_at < day_end)
                .where(ApiCallLog.status == status)
            )).first() or 0)
            daily.append({"date": day.isoformat(), "status": status, "count": count})

    # 按类目计数（仅失败；类目清单来自 distinct 单列查询）
    failed_categories = (
        await db.scalars(
            select(ApiCallLog.error_category)
            .where(ApiCallLog.created_at >= since)
            .where(ApiCallLog.status == "failed")
            .distinct()
        )
    ).all()
    by_category = []
    for category in failed_categories:
        count = int((await db.scalars(
            select(func.count()).select_from(ApiCallLog)
            .where(ApiCallLog.created_at >= since)
            .where(ApiCallLog.status == "failed")
            .where(ApiCallLog.error_category == category if category else ApiCallLog.error_category.is_(None))
        )).first() or 0)
        by_category.append({"category": category or "unknown", "count": count})

    # 按渠道计数（distinct 单列查询 + 逐渠道两计数）
    provider_names = (
        await db.scalars(
            select(ApiCallLog.provider_name).where(ApiCallLog.created_at >= since).distinct()
        )
    ).all()
    by_provider: dict[str, dict[str, int]] = {}
    for name in provider_names:
        key = name or "unknown"
        entry: dict[str, int] = {}
        for status in ("success", "failed"):
            cond = ApiCallLog.status == status
            cond = cond & (ApiCallLog.provider_name == name if name else ApiCallLog.provider_name.is_(None))
            entry[status] = int((await db.scalars(
                select(func.count()).select_from(ApiCallLog)
                .where(ApiCallLog.created_at >= since).where(cond)
            )).first() or 0)
        by_provider[key] = entry

    # 按模型计数（与渠道同法：distinct 单列查询 + 逐模型两计数）
    model_names = (
        await db.scalars(
            select(ApiCallLog.model).where(ApiCallLog.created_at >= since).distinct()
        )
    ).all()
    by_model: dict[str, dict[str, int]] = {}
    for name in model_names:
        key = name or "unknown"
        entry: dict[str, int] = {}
        for status in ("success", "failed"):
            cond = ApiCallLog.status == status
            cond = cond & (ApiCallLog.model == name if name else ApiCallLog.model.is_(None))
            entry[status] = int((await db.scalars(
                select(func.count()).select_from(ApiCallLog)
                .where(ApiCallLog.created_at >= since).where(cond)
            )).first() or 0)
        by_model[key] = entry

    return ok(data={
        "days": days,
        "total": total,
        "failed": failed,
        "failure_rate": round(failed / total, 4) if total else 0.0,
        "daily": daily,
        "by_category": by_category,
        "by_provider": by_provider,
        "by_model": by_model,
    })
