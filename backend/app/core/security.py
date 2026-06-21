# =====================================================
# 安全工具模块
# 1. 包含：
#    - API Key Fernet 对称加密/解密（已有）
#    - bcrypt 密码哈希/验证（新增）
#    - JWT（JSON Web Token）生成/解析（新增）
#    - FastAPI Depends：从 Authorization 头解析当前用户
# =====================================================

import base64
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import get_async_db
from app.models.user import User

logger = logging.getLogger("agnes_platform")

# =====================================================
# 一、API Key Fernet 对称加密（保留原有功能）
# =====================================================

def _derive_key(raw_key: str) -> bytes:
    if not raw_key:
        raw_key = "agnes-platform-default-encryption-key"
        logger.warning("[security] ENCRYPTION_KEY 未配置，使用默认密钥（生产环境请务必配置）")
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_api_key(plaintext: str) -> str:
    """加密 API Key（空串直接返回）"""
    from cryptography.fernet import Fernet
    if not plaintext:
        return ""
    try:
        key = _derive_key(settings.encryption_key)
        f = Fernet(key)
        return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error("[security] 加密 API Key 失败: %s", e)
        return plaintext


def decrypt_api_key(ciphertext: str) -> str:
    """解密 API Key（非 Fernet token 按明文返回）"""
    from cryptography.fernet import Fernet, InvalidToken
    if not ciphertext:
        return ""
    try:
        key = _derive_key(settings.encryption_key)
        f = Fernet(key)
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return ciphertext
    except Exception as e:
        logger.warning("[security] 解密 API Key 失败，按明文处理: %s", e)
        return ciphertext


def mask_api_key(api_key: str) -> str:
    """生成掩码后的 API Key（用于前端展示）"""
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}****{api_key[-4:]}"


# =====================================================
# 二、密码哈希（bcrypt）
# =====================================================

def hash_password(plain_password: str) -> str:
    """使用 bcrypt 对明文密码做哈希，返回可存储字符串（含 salt）"""
    # bcrypt 的工作因子取默认 12，兼顾安全与速度
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """验证明文密码与存储哈希是否匹配"""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        return False


# =====================================================
# 三、JWT（JSON Web Token）
# =====================================================
# JWT 的签名密钥从 settings.jwt_secret 读取
# HS256 对称签名，payload 中只放 user_id（避免在前端可篡改）
# =====================================================

ALGORITHM = "HS256"


def create_access_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """
    生成 access token（默认有效期取 settings.jwt_access_token_expire_minutes）

    - user_id 以 "sub"（subject）字段存入 JWT payload
    - "exp"（expiry）
    """
    expire_minutes = expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    expire = datetime.now(timezone.utc) + expire_minutes
    payload = {
        "sub": str(user_id),  # sub: user_id
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    # PyJWT 2.x 返回 str，兼容 str
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def decode_access_token(token: str) -> Optional[int]:
    """
    解析 JWT，返回 user_id；若签名错误、失效则返回 None
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITHM],
        )
        sub = payload.get("sub")
        if sub is None:
            return None
        return int(sub)
    except jwt.ExpiredSignatureError:
            return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
        return None


# =====================================================
# 四、FastAPI 依赖注入：get_current_user
# =====================================================

def _extract_token_from_header(auth_header: Optional[str]) -> Optional[str]:
    """从 Authorization: Bearer <token> 中提取纯 token 字符串"""
    if not auth_header:
        return None
    parts = auth_header.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> Optional[User]:
    """
    FastAPI 依赖：从请求头解析 JWT 并返回当前登录用户。

    - Authorization: Bearer <token>
    - 未提供 token 或 token 无效：抛出 401
    - 已被禁用的用户：抛出 401
    """
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    token = _extract_token_from_header(auth_header)
    if token is None:
        raise HTTPException(status_code=401, detail="未登录或 token 无效")

    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="token 已过期或无效，请重新登录")

    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="账号已被禁用")

    return user


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> Optional[User]:
    """
    可选当前用户（用于允许匿名的场景）。未登录时返回 None。
    """
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    token = _extract_token_from_header(auth_header)
    if token is None:
        return None

    user_id = decode_access_token(token)
    if user_id is None:
        return None

    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    仅允许超级管理员访问。在普通用户访问时返回 403。
    """
    # 统一判断：role == ROLE_ADMIN 或 is_admin == True 都视为管理员
    from app.models.user import ROLE_ADMIN
    if not (current_user.role == ROLE_ADMIN or getattr(current_user, "is_admin", False)):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问此接口")
    return current_user
