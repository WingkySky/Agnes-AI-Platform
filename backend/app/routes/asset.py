# =====================================================
# 资源转存管理路由（管理员）
#
# 职责：提供管理员接口，批量重试 migrate_status=pending 的转存记录
#       复用 app.services.asset_storage.migrate_pending_record 完成单条重试
#
# API 列表:
#   POST /api/asset/migrate-pending - 批量重试 pending 状态的转存记录
# =====================================================

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.security import get_current_user
from app.models.generation import Generation
from app.models.user import User
from app.services import asset_storage

logger = logging.getLogger("agnes_platform")
router = APIRouter(prefix="/asset", tags=["管理员-资源转存"])


# =====================================================
# 批量重试 pending 状态的转存记录
# =====================================================

@router.post("/migrate-pending", summary="批量重试 pending 状态的转存记录")
async def migrate_pending_records(
    limit: int = Query(100, ge=1, le=500, description="单次处理的记录上限，1-500"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量重试 migrate_status=pending 的转存记录。

    - 仅管理员/审核员可调用
    - 单次最多处理 500 条，按 created_at 升序处理（先入先重试）
    - 返回 success/failed/skipped 计数：
      * success：转存成功
      * skipped：记录本身不可重试（不存在 / 状态非 pending / 原始 URL 为空）
      * failed：重试转存但失败（保持 pending 状态，可再次调用本接口重试）
    """
    # ---------- 管理员权限校验（复用 admin_review 的内联校验逻辑）----------
    if not current_user.is_admin and current_user.role not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="仅管理员/审核员可访问")

    # ---------- 查询 pending 记录（只取 id，按创建时间升序处理）----------
    stmt = (
        select(Generation.id)
        .where(Generation.migrate_status == "pending")
        .order_by(Generation.created_at.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    record_ids = [row[0] for row in result.all()]

    if not record_ids:
        return {
            "status": "success",
            "message": "没有 pending 状态的记录",
            "data": {"total": 0, "success": 0, "failed": 0, "skipped": 0},
        }

    # ---------- 逐条重试（每条独立 session，互不影响）----------
    success_count = 0
    failed_count = 0
    skipped_count = 0

    for record_id in record_ids:
        try:
            ok, msg = await asset_storage.migrate_pending_record(record_id)
            if ok:
                success_count += 1
            else:
                # 区分"记录本身跳过"和"转存失败"
                # - 记录不存在 / 状态不是 pending / 原始 URL 为空 → skipped
                # - 其他（转存失败、异常）→ failed（保持 pending，可再次重试）
                if "不存在" in msg or "不是 pending" in msg or "原始 URL 为空" in msg:
                    skipped_count += 1
                else:
                    failed_count += 1
        except Exception as e:
            logger.error("[资源转存] 批量重试异常: record_id=%s error=%s", record_id, e)
            failed_count += 1

    return {
        "status": "success",
        "message": f"处理完成: 成功 {success_count}, 失败 {failed_count}, 跳过 {skipped_count}",
        "data": {
            "total": len(record_ids),
            "success": success_count,
            "failed": failed_count,
            "skipped": skipped_count,
        },
    }
