# =====================================================
# 生成历史记录路由（全异步）
# GET    /api/history           - 获取历史列表（分页 + 按类型筛选）
# DELETE /api/history/{id}      - 删除单条记录
# =====================================================

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, func

from app.core.database import get_async_db
from app.models.generation import Generation
from app.schemas.common import HistoryListResponse, GenerationRecord, DeleteResponse

logger = logging.getLogger("agnes_platform")
router = APIRouter()


@router.get("/history", response_model=HistoryListResponse, summary="获取生成历史列表")
async def get_history(
    type: Optional[str] = Query(None, description="筛选类型: image / video / all（默认）"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    分页获取生成历史记录（异步查询，不阻塞事件循环），按创建时间倒序排列。
    """
    stmt = select(Generation)

    if type and type.lower() in ("image", "video"):
        stmt = stmt.filter(Generation.type == type.lower())

    # 总数查询
    count_stmt = select(func.count()).select_from(stmt.subquery())
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one() or 0

    # 分页 + 倒序查询
    stmt = stmt.order_by(desc(Generation.created_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = result.scalars().all()

    # 转换为响应对象
    records = []
    for item in items:
        records.append(GenerationRecord(
            id=item.id,
            type=item.type,
            prompt=item.prompt,
            model=item.model,
            params=item.params,
            result_url=item.result_url,
            status=item.status,
            task_id=item.task_id,
            created_at=item.created_at,
        ))

    return HistoryListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=records,
    )


@router.delete("/history/{record_id}", response_model=DeleteResponse, summary="删除单条历史记录")
async def delete_history_record(record_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    根据 ID 删除一条生成历史记录（异步操作，不阻塞事件循环）。
    """
    result = await db.execute(
        select(Generation).filter(Generation.id == record_id)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="未找到对应记录")

    try:
        await db.delete(record)
        await db.commit()
        logger.info("[历史记录] 已异步删除: id=%s", record_id)
        return DeleteResponse(success=True, message=f"已删除记录 ID={record_id}")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")
