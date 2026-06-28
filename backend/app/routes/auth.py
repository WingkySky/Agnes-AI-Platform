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
import os
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Body
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
    UpdateProfileRequest,
    CaptchaResponse,
    SendEmailCodeRequest,
    ResetPasswordRequest,
)

logger = logging.getLogger("agnes_platform")
router = APIRouter(prefix="/auth", tags=["用户认证"])


# =====================================================
# 图片验证码
# =====================================================

@router.get("/captcha", response_model=CaptchaResponse, summary="获取图片验证码")
async def get_captcha():
    """
    获取图片验证码。
    - 返回 captcha_id 和 base64 编码的图片
    - 验证码有效期由 settings.captcha_expire_seconds 控制（默认 5 分钟）
    - 验证成功后自动删除，防止重复使用
    """
    from app.services.captcha_service import create_captcha
    import base64

    captcha_id, image_bytes = create_captcha()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    return CaptchaResponse(
        captcha_id=captcha_id,
        image_base64=image_base64,
    )


# =====================================================
# 发送邮箱验证码（重置密码用）
# =====================================================

@router.post("/send-email-code", summary="发送邮箱验证码")
async def send_email_code(req: SendEmailCodeRequest):
    """
    发送邮箱验证码（用于重置密码）。
    - 6 位数字验证码，有效期 10 分钟
    - 发送间隔限制：默认 60 秒
    - 只有已注册的邮箱才能收到验证码（避免泄漏哪些邮箱已注册）
    """
    from app.services.captcha_service import (
        can_send_email_code,
        generate_email_code,
        set_email_code,
    )
    from app.services.email_service import send_email, build_reset_password_email, is_email_enabled
    from app.services.system_config_service import get_smtp_config
    from app.core.config import settings

    email = req.email.lower().strip()

    # 从数据库读取 SMTP 配置
    from app.core.database import async_session
    async with async_session() as db:
        smtp_config = await get_smtp_config(db)

    # 检查邮件服务是否启用
    if not is_email_enabled(smtp_config):
        raise HTTPException(status_code=503, detail="邮件服务未配置，无法发送验证码")

    # 检查重发间隔
    can_send, msg = can_send_email_code(email)
    if not can_send:
        raise HTTPException(status_code=429, detail=msg)

    # 检查邮箱是否已注册（不注册不发送，但返回成功，避免泄漏邮箱是否存在）
    from sqlalchemy.future import select
    async with async_session() as db:
        result = await db.execute(select(User).filter(User.email == email))
        user = result.scalar_one_or_none()

    if not user:
        # 邮箱未注册：不发送，但返回成功，防止枚举用户
        logger.info("[邮箱验证码] 邮箱未注册，不发送（安全考虑） email=%s", email)
        return {"ok": True, "message": "验证码已发送，请查收邮箱"}

    # 生成并保存验证码
    code = generate_email_code()
    set_email_code(email, code, purpose=req.purpose)

    # 发送邮件
    expire_minutes = settings.email_code_expire_seconds // 60
    html_content, text_content = build_reset_password_email(code, expire_minutes)
    success = await send_email(
        to_email=email,
        subject="Agnes AI Platform 重置密码验证码",
        html_content=html_content,
        text_content=text_content,
        smtp_config=smtp_config,
    )

    if not success:
        raise HTTPException(status_code=500, detail="邮件发送失败，请稍后重试")

    return {"ok": True, "message": "验证码已发送，请查收邮箱"}


# =====================================================
# 重置密码
# =====================================================

@router.post("/reset-password", summary="通过邮箱验证码重置密码")
async def reset_password(req: ResetPasswordRequest, db: AsyncSession = Depends(get_async_db)):
    """
    通过邮箱验证码重置密码。
    - 需要邮箱 + 验证码 + 新密码
    - 验证成功后密码立即更新，并删除验证码（一次性使用）
    """
    from app.services.captcha_service import verify_email_code

    email = req.email.lower().strip()

    # 验证邮箱验证码
    valid, msg = verify_email_code(email, req.code, purpose="reset_password")
    if not valid:
        raise HTTPException(status_code=400, detail=msg)

    # 查找用户
    result = await db.execute(select(User).filter(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 更新密码
    user.password_hash = hash_password(req.new_password)
    await db.commit()

    logger.info("[重置密码] 成功 user=%s id=%d", user.username, user.id)
    return {"ok": True, "message": "密码重置成功，请使用新密码登录"}


# =====================================================
# 注册
# =====================================================

@router.post("/register", response_model=TokenResponse, summary="用户注册")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_async_db)):
    """
    注册新用户：
    - 检查用户名是否已被占用
    - 检查邮箱是否已被占用（必填）
    - 图片验证码验证
    - 将密码以 bcrypt 哈希形式存储
    - 成功后返回 JWT token（自动登录）
    - 新用户默认积分从 settings 或积分规则表中读取
    """
    # 1. 验证图片验证码
    from app.services.captcha_service import verify_captcha
    if req.captcha_id and req.captcha_code:
        if not verify_captcha(req.captcha_id, req.captcha_code):
            raise HTTPException(status_code=400, detail="验证码错误或已过期")
    # 验证码字段为空时不强制验证（兼容旧版调用），前端应始终传递

    # 2. 检查用户名是否已存在
    existing = await db.execute(select(User).filter(User.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该用户名已被占用")

    # 3. 检查邮箱是否已被占用（邮箱必填）
    email = req.email.lower().strip()
    existing_email = await db.execute(select(User).filter(User.email == email))
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
        email=email,
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
    - 图片验证码验证（防止暴力破解）
    - 用户名不存在 / 密码错误：均返回 401（避免泄漏用户存在性）
    - 密码正确但账号已被管理员停用：返回 403 并明确提示「账号已被停用」
    - 成功：更新 last_login_at，并返回 JWT
    """
    # 1. 验证图片验证码
    from app.services.captcha_service import verify_captcha
    if req.captcha_id and req.captcha_code:
        if not verify_captcha(req.captcha_id, req.captcha_code):
            raise HTTPException(status_code=400, detail="验证码错误或已过期")
    # 验证码字段为空时不强制验证（兼容旧版调用），前端应始终传递

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
        nickname=current_user.nickname,
        email=current_user.email,
        avatar_url=current_user.avatar_url,
        credits=current_user.credits,
        role=current_user.role,
        is_active=current_user.is_active,
        is_admin=is_admin,
        watermark_enabled=current_user.watermark_enabled or False,
        content_safety_strict=current_user.content_safety_strict or False,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
    )


# =====================================================
# 更新个人资料（邮箱）
# =====================================================

@router.put("/me", response_model=UserInfoResponse, summary="更新当前用户个人资料")
async def update_my_profile(
    req: UpdateProfileRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新当前登录用户的个人资料（支持修改邮箱、昵称）。
    - 邮箱可选，传 null 清空
    - 昵称可选，传 null 清空，最多 32 字符
    """
    if req.email is not None:
        # 检查邮箱是否已被其他用户占用
        if req.email:
            existing = await db.execute(
                select(User).filter(User.email == req.email, User.id != current_user.id)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="该邮箱已被其他用户占用")
        current_user.email = req.email or None

    # nickname 字段：None 代表不修改，空字符串代表清空
    if req.nickname is not None:
        trimmed = (req.nickname or "").strip()
        current_user.nickname = trimmed if trimmed else None

    await db.commit()
    await db.refresh(current_user)
    logger.info("[个人资料更新] user=%s id=%d", current_user.username, current_user.id)

    is_admin = current_user.role == ROLE_ADMIN or current_user.is_admin
    return UserInfoResponse(
        id=current_user.id,
        username=current_user.username,
        nickname=current_user.nickname,
        email=current_user.email,
        avatar_url=current_user.avatar_url,
        credits=current_user.credits,
        role=current_user.role,
        is_active=current_user.is_active,
        is_admin=is_admin,
        watermark_enabled=current_user.watermark_enabled or False,
        content_safety_strict=current_user.content_safety_strict or False,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
    )


# =====================================================
# 上传头像
# =====================================================

# 头像保存目录（相对于后端工作目录）
AVATAR_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "avatars")
# 允许的头像 MIME 类型
ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
# 头像最大大小 2MB
MAX_AVATAR_BYTES = 2 * 1024 * 1024


@router.post("/avatar", response_model=UserInfoResponse, summary="上传/更新当前用户头像")
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    上传或更新当前登录用户的头像。
    - 接收 multipart/form-data 文件
    - 支持 jpeg/png/webp/gif，最大 2MB
    - 保存到 backend/uploads/avatars/，文件名带用户 ID + 时间戳防冲突
    - 返回更新后的用户信息（含新的 avatar_url）
    """
    # 校验文件类型
    if file.content_type not in ALLOWED_AVATAR_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的头像格式：{file.content_type}，仅支持 jpeg/png/webp/gif")

    # 读取文件内容并校验大小
    content = await file.read()
    if len(content) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="头像文件过大，最大 2MB")

    # 确保目录存在
    os.makedirs(AVATAR_DIR, exist_ok=True)

    # 根据 MIME 类型确定扩展名
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    ext = ext_map.get(file.content_type, ".jpg")

    # 文件名：用户 ID + 时间戳，避免覆盖旧文件；同时删除旧头像
    filename = f"{current_user.id}_{int(time.time())}{ext}"
    filepath = os.path.join(AVATAR_DIR, filename)

    # 删除旧头像文件（如果存在且不是默认头像）
    if current_user.avatar_url:
        old_filename = os.path.basename(current_user.avatar_url)
        old_filepath = os.path.join(AVATAR_DIR, old_filename)
        if os.path.exists(old_filepath) and old_filepath != filepath:
            try:
                os.remove(old_filepath)
            except OSError:
                pass

    # 写入新文件
    with open(filepath, "wb") as f:
        f.write(content)

    # 更新数据库中的 avatar_url（前端通过 /uploads/avatars/<filename> 访问）
    current_user.avatar_url = f"/uploads/avatars/{filename}"
    await db.commit()
    await db.refresh(current_user)

    logger.info("[头像更新] user=%s id=%d avatar=%s", current_user.username, current_user.id, current_user.avatar_url)

    is_admin = current_user.role == ROLE_ADMIN or current_user.is_admin
    return UserInfoResponse(
        id=current_user.id,
        username=current_user.username,
        nickname=current_user.nickname,
        email=current_user.email,
        avatar_url=current_user.avatar_url,
        credits=current_user.credits,
        role=current_user.role,
        is_active=current_user.is_active,
        is_admin=is_admin,
        watermark_enabled=current_user.watermark_enabled or False,
        content_safety_strict=current_user.content_safety_strict or False,
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
            id=u.id, username=u.username, nickname=u.nickname, email=u.email,
            avatar_url=u.avatar_url,
            credits=u.credits, role=u.role, is_active=u.is_active, is_admin=is_admin,
            watermark_enabled=u.watermark_enabled,
            content_safety_strict=u.content_safety_strict,
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
# 管理员：修改用户水印开关
# =====================================================

@router.put("/users/{user_id}/watermark", summary="[管理员] 修改用户水印开关")
async def update_user_watermark(
    user_id: int,
    req: dict = Body(...),
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    enabled = bool(req.get("enabled", False))
    user.watermark_enabled = enabled
    await db.commit()

    logger.info("[管理员操作] %s 修改用户 id=%d 水印开关 -> %s", _admin.username, user.id, enabled)
    return {"id": user.id, "watermark_enabled": enabled, "ok": True}


# =====================================================
# 管理员：修改用户内容安全严格模式
# =====================================================

@router.put("/users/{user_id}/content-safety", summary="[管理员] 修改用户内容安全严格模式")
async def update_user_content_safety(
    user_id: int,
    req: dict = Body(...),
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    enabled = bool(req.get("enabled", False))
    user.content_safety_strict = enabled
    await db.commit()

    logger.info("[管理员操作] %s 修改用户 id=%d 内容安全严格模式 -> %s", _admin.username, user.id, enabled)
    return {"id": user.id, "content_safety_strict": enabled, "ok": True}


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


# =====================================================
# 管理员：用户水印开关
# =====================================================

@router.put("/users/{user_id}/watermark", summary="[管理员] 开启/关闭用户水印")
async def update_user_watermark(
    user_id: int,
    req: UpdateActiveRequest,   # 复用 is_active 字段做布尔开关
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.watermark_enabled = req.is_active
    await db.commit()
    logger.info(
        "[管理员操作] %s 将用户 id=%d watermark_enabled 改为 %s",
        _admin.username, user.id, req.is_active,
    )
    return {"id": user.id, "watermark_enabled": user.watermark_enabled, "ok": True}


# =====================================================
# 管理员：用户内容安全严格模式开关
# =====================================================

@router.put("/users/{user_id}/content-safety", summary="[管理员] 开启/关闭用户严格内容安全")
async def update_user_content_safety(
    user_id: int,
    req: UpdateActiveRequest,   # 复用 is_active 字段做布尔开关
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.content_safety_strict = req.is_active
    await db.commit()
    logger.info(
        "[管理员操作] %s 将用户 id=%d content_safety_strict 改为 %s",
        _admin.username, user.id, req.is_active,
    )
    return {"id": user.id, "content_safety_strict": user.content_safety_strict, "ok": True}
