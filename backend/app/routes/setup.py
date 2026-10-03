# =====================================================
# 首启初始化路由
#
# GET  /api/setup/bootstrap   实例是否已有管理员（免登录，前端守卫用）
# POST /api/setup/bootstrap   创建首个管理员（免登录，仅实例无管理员时可用）
# GET  /api/setup/status      当前实例初始化状态（登录用户可查）
# POST /api/setup/complete    标记实例初始化完成（仅管理员）
#
# 状态语义：
#   - provider_pending：当前用户是管理员且实例未配置任何 AI Provider
#   - setup_completed：实例级标记（system_config setup.completed），管理员完成向导后置位
# =====================================================

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_db
from app.core.response import ok
from app.core.security import (
    create_access_token,
    get_current_admin_user,
    get_current_user,
    hash_password,
)
from app.models.api_provider import ApiProvider
from app.models.user import ROLE_ADMIN, User
from app.schemas.setup import SetupBootstrapRequest
from app.schemas.user import TokenResponse
from app.seed import admin_config
from app.services.system_config_service import get_config_value, set_config_value

logger = logging.getLogger("agnes_platform")

router = APIRouter(prefix="/setup", tags=["首启初始化"])

SETUP_COMPLETED_KEY = "setup.completed"


async def _admin_count(db: AsyncSession) -> int:
    return (await db.scalars(
        select(func.count(User.id)).filter(User.role == ROLE_ADMIN)
    )).first() or 0


@router.get("/bootstrap", summary="获取首启引导状态（免登录）")
async def setup_bootstrap_status(db: AsyncSession = Depends(get_async_db)):
    """实例是否已存在管理员；false 时前端将所有路由强制引导至首启向导创建管理员"""
    return ok(data={"admin_exists": await _admin_count(db) > 0})


@router.post("/bootstrap", summary="创建首个管理员（仅实例无管理员时可用）")
async def setup_bootstrap(req: SetupBootstrapRequest, db: AsyncSession = Depends(get_async_db)):
    """
    免登录创建实例的第一个管理员账号（首启向导第一步）。
    - 仅当实例管理员数为 0 时可用（否则 409），窗口期内谁先到谁创建
    - 用户名冲突 409；校验规则与注册一致（3~32 位字母/数字/下划线/中文，密码 6~64）
    - 成功后直接签发 JWT，前端免登录进入向导下一步
    """
    if await _admin_count(db) > 0:
        raise HTTPException(status_code=409, detail="实例已完成初始化，请直接登录")

    existing = (await db.scalars(
        select(User).filter(User.username == req.username)
    )).first()
    if existing:
        raise HTTPException(status_code=409, detail="该用户名已被占用")

    user = User(
        username=req.username,
        email=None,
        password_hash=hash_password(req.password),
        credits=admin_config.admin_credits(),
        role=ROLE_ADMIN,
        is_admin=True,
        is_active=True,
        created_at=datetime.utcnow(),
        last_login_at=datetime.utcnow(),
    )
    user.sync_role_and_is_admin()
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("[首启引导] 管理员已创建 user=%s id=%d", user.username, user.id)
    return ok(data=TokenResponse(
        access_token=create_access_token(user.id),
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    ))


@router.get("/status", summary="获取首启初始化状态")
async def setup_status(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    provider_pending = False
    if current_user.effective_is_admin:
        provider_count = (
            await db.scalars(select(func.count(ApiProvider.id)))
        ).first() or 0
        provider_pending = provider_count == 0
    return ok(data={
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
