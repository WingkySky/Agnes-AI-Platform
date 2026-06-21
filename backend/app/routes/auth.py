# =====================================================
# 用户认证路由
#
# POST   /api/auth/register   注册新用户
# POST   /api/auth/login      登录（返回 JWT）
# GET    /api/auth/me         获取当前登录用户信息
# GET    /api/auth/credits    获取当前积分余额
#
# 管理员接口：
# GET    /api/auth/users                列出所有用户（仅管理员）
# PUT    /api/auth/users/{id}/role      修改用户角色（仅管理员）
# PUT    /api/auth/users/{id}/credits   修改用户积分余额（仅管理员）
# PUT    /api/auth/users/{id}/active    启用/禁用用户（仅管理员）
# =====================================================

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import get_async_db
from app.core.security import (
    create_access_token,
    get_current_user,
    get_current_admin_user,
    hash_password,
    verify_password,
)
from app.models.user import User, ROLE_ADMIN, ROLE_USER
from app.schemas.user import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserCreditsResponse,
    UserInfoResponse,
    UserListResponse,
    UserAdminRow,
    UpdateRoleRequest,
    UpdateCreditsRequest,
    UpdateActiveRequest,
)

logger = logging.getLogger("agnes_platform")
router = APIRouter(prefix="/auth", tags=["用户认证"])


# =====================================================
# 注册
# =====================================================

@router.post("/register", response_model=TokenResponse, summary="用户注册")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_async_db)):
    """
    注册新用户：
    - 检查用户名是否已被占用
    - 检查邮箱是否已被占用（若提供）
    - 将密码以 bcrypt 哈希形式存储
    - 成功后返回 JWT token（自动登录）
    - 新用户默认积分从 settings 或积分规则表中读取
    """

    # 1. 检查用户名是否已存在
    existing = await db.execute(select(User).filter(User.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该用户名已被占用")

    # 2. 检查邮箱是否已被占用
    if req.email:
        existing_email = await db.execute(select(User).filter(User.email == req.email))
        if existing_email.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="该邮箱已被注册")

    # 3. 写入数据库 —— 新用户初始积分从 credit_rules 表读取（new_user.default_credits）
    #    缺失时回落到 settings.new_user_default_credits
    from app.models.credit_rule import CreditRule
    new_user_credits = settings.new_user_default_credits
    try:
        credit_result = await db.execute(
            select(CreditRule.value).filter(CreditRule.rule_key == "new_user.default_credits")
        )
        credit_val = credit_result.scalar_one_or_none()
        if credit_val is not None:
            new_user_credits = credit_val
    except Exception:
        pass

    user = User(
        username=req.username,
        email=req.email or None,
        password_hash=hash_password(req.password),
        credits=new_user_credits,
        role=ROLE_USER,
        is_active=True,
        is_admin=False,
        created_at=datetime.utcnow(),
        last_login_at=datetime.utcnow(),
    )

    # 第一个注册用户自动成为超级管理员（避免没有管理员账号）
    from sqlalchemy import func
    count_result = await db.execute(select(func.count(User.id)))
    total_users = count_result.scalar_one() or 0
    if total_users == 0:
        user.role = ROLE_ADMIN
        user.is_admin = True
        logger.info("[首个用户] 第一个注册用户自动提升为超级管理员")

    # 保持 role / is_admin 一致
    user.sync_role_and_is_admin()
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("[注册成功] user=%s id=%d initial_credits=%d", user.username, user.id, user.credits)

    # 4. 生成 JWT
    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


# =====================================================
# 登录
# =====================================================

@router.post("/login", response_model=TokenResponse, summary="用户登录")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_async_db)):
    """
    使用用户名 + 密码登录，返回 JWT token。
    - 用户名不存在 / 密码错误：均返回 401（避免泄漏用户存在性）
    - 密码正确但账号已被管理员停用：返回 403 并明确提示「账号已被停用」
    - 成功：更新 last_login_at，并返回 JWT
    """
    GENERIC_401 = HTTPException(status_code=401, detail="用户名或密码错误")

    result = await db.execute(select(User).filter(User.username == req.username))
    user = result.scalar_one_or_none()
    # 用户名不存在：返回通用 401，避免泄漏用户是否存在
    if user is None:
        raise GENERIC_401

    # 密码错误：返回通用 401
    if not verify_password(req.password, user.password_hash):
        raise GENERIC_401

    # 密码正确但账号已被管理员停用：返回 403 并给出明确提示
    # 此时已通过密码验证，不再需要隐藏用户存在性，应让用户知道停用状态
    if not user.is_active:
        logger.info("[登录拒绝] 账号已停用 user=%s id=%d", user.username, user.id)
        raise HTTPException(status_code=403, detail="账号已被停用，请联系管理员")

    # 保证 role / is_admin 一致性
    user.sync_role_and_is_admin()
    user.last_login_at = datetime.utcnow()
    await db.commit()

    token = create_access_token(user.id)
    logger.info("[登录成功] user=%s id=%d role=%s", user.username, user.id, user.role)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


# =====================================================
# 获取当前用户信息
# =====================================================

@router.get("/me", response_model=UserInfoResponse, summary="获取当前登录用户信息")
async def get_me(current_user: User = Depends(get_current_user)):
    """
    需要携带有效的 Authorization: Bearer <token>。
    返回当前登录用户的公开信息（不含密码哈希）。
    """
    # 读取角色时保持一致性逻辑
    is_admin = current_user.role == ROLE_ADMIN or current_user.is_admin
    return UserInfoResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        credits=current_user.credits,
        role=current_user.role,
        is_active=current_user.is_active,
        is_admin=is_admin,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
    )


# =====================================================
# 查询当前积分
# =====================================================

@router.get("/credits", response_model=UserCreditsResponse, summary="获取当前积分余额")
async def get_credits(current_user: User = Depends(get_current_user)):
    return UserCreditsResponse(credits=current_user.credits)


# =====================================================
# 管理员：列出所有用户
# =====================================================

@router.get("/users", response_model=UserListResponse, summary="[管理员] 列出所有用户")
async def list_users(
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(User).order_by(User.id.asc()))
    rows = result.scalars().all()
    items = []
    for u in rows:
        is_admin = u.role == ROLE_ADMIN or u.is_admin
        items.append(UserAdminRow(
            id=u.id, username=u.username, email=u.email,
            credits=u.credits, role=u.role, is_active=u.is_active, is_admin=is_admin,
            created_at=u.created_at, last_login_at=u.last_login_at,
        ))
    return UserListResponse(items=items, total=len(items))


# =====================================================
# 管理员：修改用户角色
# =====================================================

@router.put("/users/{user_id}/role", summary="[管理员] 修改用户角色")
async def update_user_role(
    user_id: int,
    req: UpdateRoleRequest,
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 不允许把自己改成非管理员（防止锁死）
    if user.id == _admin.id and req.role != ROLE_ADMIN:
        raise HTTPException(status_code=400, detail="无法将自己的角色取消为普通用户")

    user.role = req.role
    user.is_admin = (req.role == ROLE_ADMIN)
    await db.commit()

    is_admin = user.role == ROLE_ADMIN or user.is_admin
    logger.info("[管理员操作] %s 修改用户 id=%d 角色为 %s", _admin.username, user.id, req.role)
    return {
        "id": user.id,
        "role": user.role,
        "is_admin": is_admin,
        "ok": True,
    }


# =====================================================
# 管理员：修改用户积分
# =====================================================

@router.put("/users/{user_id}/credits", summary="[管理员] 修改用户积分余额")
async def update_user_credits(
    user_id: int,
    req: UpdateCreditsRequest,
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    old_value = user.credits
    # 计算差额，通过 recharge_credits 写入流水（amount 可正可负）
    delta = req.credits - old_value
    if delta != 0:
        from app.services.credits_service import recharge_credits
        await recharge_credits(
            db, user_id, delta,
            operator_id=_admin.id,
            description=f"管理员 {_admin.username} 调整积分 {old_value} -> {req.credits}",
        )
    logger.info(
        "[管理员操作] %s 修改用户 id=%d 积分 %d -> %d",
        _admin.username, user.id, old_value, req.credits,
    )
    return {"id": user.id, "credits": req.credits, "ok": True}


# =====================================================
# 管理员：启用 / 禁用用户
# =====================================================

@router.put("/users/{user_id}/active", summary="[管理员] 启用/禁用用户")
async def update_user_active(
    user_id: int,
    req: UpdateActiveRequest,
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.id == _admin.id and not req.is_active:
        raise HTTPException(status_code=400, detail="无法禁用自己")

    user.is_active = req.is_active
    await db.commit()
    logger.info(
        "[管理员操作] %s 将用户 id=%d is_active 改为 %s",
        _admin.username, user.id, req.is_active,
    )
    return {"id": user.id, "is_active": user.is_active, "ok": True}
