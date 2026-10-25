# =====================================================
# 存储配额路由
# GET /api/storage/usage          - 我的存储用量（登录级）
# GET /api/admin/storage/overview - 全平台存储概览（管理员级，显式挂鉴权）
# =====================================================


from fastapi import APIRouter, Depends, Query

from app.core.response import ok
from app.core.security import get_current_admin_user, get_current_user
from app.models.user import User
from app.services.storage_quota import admin_overview, usage_for

router = APIRouter(tags=["存储"])


@router.get("/storage/usage", summary="我的存储用量（总量/配额 + 滚动 24h 上传）")
async def get_storage_usage(
    current_user: User = Depends(get_current_user),
):
    """当前登录用户的存储用量；quota 为 null 表示不限制（配置为 0）"""
    data = await usage_for(current_user.id)
    return ok(data=data)


@router.get("/admin/storage/overview", summary="全平台存储概览（管理员）")
async def get_storage_overview(
    limit: int = Query(10, ge=1, le=50),
    _admin: User | None = Depends(get_current_admin_user),
):
    """平台总用量 + 用量 top N 用户（台账口径，S3 件不计）"""
    data = await admin_overview(limit=limit)
    return ok(data=data)
