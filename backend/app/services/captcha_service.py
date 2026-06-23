# =====================================================
# 图片验证码服务
# - 生成随机验证码文字 + 干扰线/干扰点的图片
# - 验证码存储在内存中（带过期时间），使用 captcha_id 标识
# - 依赖 Pillow 库
# =====================================================

import io
import random
import string
import time
import logging
from typing import Optional, Tuple

from app.core.config import settings

logger = logging.getLogger("agnes_platform")

# 内存存储验证码：{captcha_id: {"code": "xxxx", "expire_at": 1234567890}}
_captcha_store: dict[str, dict] = {}
# 最近一次清理时间
_last_cleanup_time = 0


def _generate_random_code(length: int = 4) -> str:
    """生成随机验证码（字母数字混合，去掉易混淆字符）"""
    # 去掉容易混淆的字符：0, O, o, 1, I, l
    chars = string.ascii_uppercase + string.digits
    chars = chars.replace("0", "").replace("O", "").replace("I", "").replace("1", "")
    return "".join(random.choices(chars, k=length))


def _generate_captcha_image(code: str, width: int = 120, height: int = 40) -> bytes:
    """
    生成验证码图片，返回 PNG 格式的字节数据。
    - 随机干扰线、干扰点
    - 随机字体颜色、大小、位置
    - 轻微旋转
    """
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
    except ImportError:
        # Pillow 未安装时，返回一个简单的占位图片（1x1 透明像素）
        logger.warning("[验证码] Pillow 未安装，无法生成图片验证码")
        # 返回一个 1x1 的透明 PNG 作为兜底
        return base64_to_bytes(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )

    # 创建画布
    image = Image.new("RGB", (width, height), (245, 247, 250))
    draw = ImageDraw.Draw(image)

    # 随机背景色（浅色）
    bg_r = random.randint(240, 250)
    bg_g = random.randint(240, 250)
    bg_b = random.randint(245, 255)
    image = Image.new("RGB", (width, height), (bg_r, bg_g, bg_b))
    draw = ImageDraw.Draw(image)

    # 画干扰线
    for _ in range(3):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        color = (
            random.randint(150, 200),
            random.randint(150, 200),
            random.randint(180, 220),
        )
        draw.line([(x1, y1), (x2, y2)], fill=color, width=1)

    # 画干扰点
    for _ in range(30):
        x = random.randint(0, width)
        y = random.randint(0, height)
        color = (
            random.randint(100, 200),
            random.randint(100, 200),
            random.randint(150, 220),
        )
        draw.point((x, y), fill=color)

    # 绘制验证码文字
    font_size = 26
    try:
        # 尝试使用系统默认字体
        font = ImageFont.truetype("Arial.ttf", font_size)
    except Exception:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

    # 每个字符随机颜色、位置、旋转
    char_width = width // len(code)
    for i, char in enumerate(code):
        # 随机颜色（深色）
        color = (
            random.randint(30, 100),
            random.randint(30, 100),
            random.randint(100, 180),
        )

        # 字符位置（带随机偏移）
        x = i * char_width + random.randint(2, 8)
        y = random.randint(2, 8)

        # 绘制字符
        draw.text((x, y), char, font=font, fill=color)

    # 轻微模糊
    image = image.filter(ImageFilter.SMOOTH)

    # 保存到内存
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def base64_to_bytes(b64_str: str) -> bytes:
    """Base64 字符串转字节（兜底用）"""
    import base64
    return base64.b64decode(b64_str)


def create_captcha(captcha_id: Optional[str] = None) -> Tuple[str, bytes]:
    """
    创建一个新的验证码。

    参数：
    - captcha_id: 可选，指定验证码 ID；不指定则自动生成

    返回：(captcha_id, image_bytes)
    """
    import uuid

    # 清理过期验证码（每 100 次请求清理一次）
    global _last_cleanup_time
    if time.time() - _last_cleanup_time > 60:
        _cleanup_expired()
        _last_cleanup_time = time.time()

    if not captcha_id:
        captcha_id = str(uuid.uuid4()).replace("-", "")

    code = _generate_random_code(4)
    image_bytes = _generate_captcha_image(code)

    _captcha_store[captcha_id] = {
        "code": code,
        "expire_at": time.time() + settings.captcha_expire_seconds,
    }

    logger.debug("[验证码] 已生成 captcha_id=%s code=%s", captcha_id, code)
    return captcha_id, image_bytes


def verify_captcha(captcha_id: str, user_input: str, remove_after_verify: bool = True) -> bool:
    """
    验证用户输入的验证码是否正确。

    参数：
    - captcha_id: 验证码 ID
    - user_input: 用户输入的验证码
    - remove_after_verify: 验证后是否删除（默认删除，防止重复使用）

    返回：是否验证通过
    """
    if not captcha_id or not user_input:
        return False

    captcha = _captcha_store.get(captcha_id)
    if not captcha:
        logger.debug("[验证码] 验证失败：captcha_id 不存在 captcha_id=%s", captcha_id)
        return False

    # 检查是否过期
    if time.time() > captcha["expire_at"]:
        if captcha_id in _captcha_store:
            del _captcha_store[captcha_id]
        logger.debug("[验证码] 验证失败：已过期 captcha_id=%s", captcha_id)
        return False

    # 不区分大小写比较
    is_correct = user_input.strip().upper() == captcha["code"].upper()

    if is_correct and remove_after_verify:
        del _captcha_store[captcha_id]
        logger.debug("[验证码] 验证成功，已删除 captcha_id=%s", captcha_id)
    elif not is_correct:
        logger.debug("[验证码] 验证失败：不匹配 captcha_id=%s input=%s correct=%s", captcha_id, user_input, captcha["code"])

    return is_correct


def _cleanup_expired() -> None:
    """清理过期的验证码"""
    now = time.time()
    expired_keys = [
        k for k, v in _captcha_store.items()
        if now > v["expire_at"]
    ]
    for k in expired_keys:
        del _captcha_store[k]
    if expired_keys:
        logger.debug("[验证码] 已清理 %d 个过期验证码", len(expired_keys))


# =====================================================
# 邮箱验证码服务
# - 发送邮箱验证码（用于重置密码等）
# - 验证码存储在内存中，带过期时间和重发间隔
# =====================================================

# 内存存储邮箱验证码：{email: {"code": "xxxx", "expire_at": 1234567890, "last_sent_at": 1234567890, "purpose": "reset_password"}}
_email_code_store: dict[str, dict] = {}


def generate_email_code() -> str:
    """生成 6 位数字邮箱验证码"""
    return "".join(random.choices("0123456789", k=6))


def can_send_email_code(email: str) -> Tuple[bool, str]:
    """
    检查是否可以发送邮箱验证码（重发间隔限制）。

    返回：(是否可以发送, 提示信息)
    """
    email = email.lower().strip()
    record = _email_code_store.get(email)

    if not record:
        return True, ""

    time_since_last = time.time() - record["last_sent_at"]
    if time_since_last < settings.email_code_resend_interval:
        wait_seconds = int(settings.email_code_resend_interval - time_since_last)
        return False, f"发送过于频繁，请 {wait_seconds} 秒后再试"

    return True, ""


def set_email_code(email: str, code: str, purpose: str = "reset_password") -> None:
    """保存邮箱验证码"""
    email = email.lower().strip()
    _email_code_store[email] = {
        "code": code,
        "purpose": purpose,
        "expire_at": time.time() + settings.email_code_expire_seconds,
        "last_sent_at": time.time(),
    }
    logger.info("[邮箱验证码] 已保存 email=%s purpose=%s", email, purpose)


def verify_email_code(email: str, code: str, purpose: str = "reset_password", remove_after_verify: bool = True) -> Tuple[bool, str]:
    """
    验证邮箱验证码。

    返回：(是否验证通过, 错误信息)
    """
    email = email.lower().strip()
    if not email or not code:
        return False, "邮箱和验证码不能为空"

    record = _email_code_store.get(email)
    if not record:
        return False, "验证码不存在或已过期"

    if record["purpose"] != purpose:
        return False, "验证码用途不匹配"

    if time.time() > record["expire_at"]:
        del _email_code_store[email]
        return False, "验证码已过期，请重新获取"

    if code.strip() != record["code"]:
        return False, "验证码错误"

    if remove_after_verify:
        del _email_code_store[email]

    return True, ""


def cleanup_expired_email_codes() -> None:
    """清理过期的邮箱验证码"""
    now = time.time()
    expired_keys = [
        k for k, v in _email_code_store.items()
        if now > v["expire_at"]
    ]
    for k in expired_keys:
        del _email_code_store[k]
