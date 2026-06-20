# =====================================================
# API Key 加密/解密工具（Fernet 对称加密）
# 用于安全存储 Provider 的 api_key 到数据库
# 加密密钥从 .env 的 ENCRYPTION_KEY 读取
# =====================================================

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger("agnes_platform")


def _derive_key(raw_key: str) -> bytes:
    """
    从任意长度的原始密钥派生合法的 Fernet key（32 字节 base64 编码）。
    这样用户在 .env 里写任意长度的 ENCRYPTION_KEY 都能正常工作。
    """
    if not raw_key:
        raw_key = "agnes-platform-default-encryption-key"
        logger.warning("[security] ENCRYPTION_KEY 未配置，使用默认密钥（生产环境请务必配置）")
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_api_key(plaintext: str) -> str:
    """
    加密 API Key，返回 Fernet token 字符串。
    空字符串直接返回空字符串（不加密）。
    """
    if not plaintext:
        return ""
    try:
        key = _derive_key(settings.encryption_key)
        f = Fernet(key)
        token = f.encrypt(plaintext.encode("utf-8"))
        return token.decode("utf-8")
    except Exception as e:
        logger.error("[security] 加密 API Key 失败: %s", e)
        # 加密失败时回退为明文（保证可用性，但记录告警）
        return plaintext


def decrypt_api_key(ciphertext: str) -> str:
    """
    解密 API Key。
    - 空字符串返回空字符串
    - 非 Fernet token（明文兼容）直接返回原值
    """
    if not ciphertext:
        return ""
    # 兼容明文存储：如果解密失败，认为是明文直接返回
    try:
        key = _derive_key(settings.encryption_key)
        f = Fernet(key)
        plaintext = f.decrypt(ciphertext.encode("utf-8"))
        return plaintext.decode("utf-8")
    except InvalidToken:
        # 不是合法的 Fernet token，当作明文返回（兼容旧数据）
        return ciphertext
    except Exception as e:
        logger.warning("[security] 解密 API Key 失败，按明文处理: %s", e)
        return ciphertext


def mask_api_key(api_key: str) -> str:
    """
    生成 API Key 的掩码字符串，用于前端展示。
    例如：sk-abcdefghijxxxxx → sk-abcd****xxxxx
    """
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    # 保留前 4 位和后 4 位，中间用 **** 替代
    prefix = api_key[:4]
    suffix = api_key[-4:]
    return f"{prefix}****{suffix}"
