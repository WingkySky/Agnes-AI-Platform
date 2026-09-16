# =====================================================
# 首启初始化路由
#
# GET  /api/setup/status    当前实例初始化状态（登录用户可查）
# POST /api/setup/complete  标记实例初始化完成（仅管理员）
#
# 状态语义：
#   - password_pending：当前用户 must_change_password（默认 admin 首登强制改密）
#   - provider_pending：当前用户是管理员且实例未配置任何 AI Provider
#   - setup_completed：实例级标记（system_config setup.completed），管理员完成向导后置位
# =====================================================

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.response import ok
from app.core.security import get_current_admin_user, get_current_user
from app.models.api_provider import ApiProvider
from app.models.user import User
from app.services.system_config_service import get_config_value, set_config_value

router = APIRouter(prefix="/setup", tags=["首启初始化"])

SETUP_COMPLETED_KEY = "setup.completed"


@router.get("/status", summary="获取首启初始化状态")
async def setup_status(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    provider_pending = False
    if current_user.is_admin:
        provider_count = (
            await db.scalars(select(func.count(ApiProvider.id)))
        ).first() or 0
        provider_pending = provider_count == 0
    return ok(data={
        "password_pending": bool(current_user.must_change_password),
        "provider_pending": provider_pending,
        "setup_completed": await _setup_completed(db),
    })


async def _setup_completed(db: AsyncSession) -> bool:
    return (await get_config_value(db, SETUP_COMPLETED_KEY, "0")) == "1"


@router.post("/complete", summary="标记首启初始化完成（仅管理员）")
async def setup_complete(
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    await set_config_value(db, SETUP_COMPLETED_KEY, "1")
    return ok(data={"setup_completed": True})
