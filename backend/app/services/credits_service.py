# =====================================================
# 积分服务：生成任务的积分计算与消耗
#
# 关键约束：
#   - 已登录用户：必须积分足够，否则 402 拒绝
#   - 匿名用户：无积分概念，直接放行（兼容旧行为）
#   - 积分规则（image.text2image.base_cost 等）从数据库 credit_rules 表读取
#     不存在时回落到默认值（见 DEFAULT_CREDIT_RULES）
#   - 为兼容 SQLite（不支持 SELECT ... FOR UPDATE），采用原子 UPDATE WHERE
#     方式实现并发安全：UPDATE ... SET credits = credits - amount WHERE id = ? AND credits >= amount
# =====================================================

import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update as sa_update
from sqlalchemy.future import select

from app.models.user import User
from app.models.credit_rule import DEFAULT_CREDIT_RULES, CreditRule

logger = logging.getLogger("agnes_platform")


# ---------- 缓存：进程内的积分规则快照，避免每次都查询 ----------
# 每次 consume_credits 前都会读取；这里提供一个轻量函数
async def _get_rule_value(db: AsyncSession, rule_key: str, default: int) -> int:
    """从 credit_rules 表读取指定 key 的 value；不存在则写入并返回默认值。"""
    result = await db.execute(select(CreditRule.value).filter(CreditRule.rule_key == rule_key))
    value = result.scalar_one_or_none()
    if value is None:
        return default
    return value


def _get_default_value(rule_key: str) -> int:
    for d in DEFAULT_CREDIT_RULES:
        if d["rule_key"] == rule_key:
            return d["value"]
    return 0


# ---------- 尺寸解析 ----------
def _parse_size_to_px(size: Optional[str]) -> float:
    """将 '1024x768' 格式的尺寸字符串估算为总像素数，用于计算积分"""
    if not size:
        return 1024.0 * 1024.0
    try:
        w, h = size.lower().split("x")
        return float(int(w) * int(h))
    except Exception:
        return 1024.0 * 1024.0


# ---------- 图片：计算一次任务的成本 ----------
async def get_image_cost_async(
    db: AsyncSession,
    mode: Optional[str] = "text2image",
    size: Optional[str] = None,
) -> int:
    """
    异步版本：从数据库读取积分规则，计算一次图片任务的消耗。
    当 db 为 None 时使用默认值（便于在无数据库上下文的单元测试中使用）。
    """
    mode_key = "image.image2image.base_cost"
    if mode and mode.lower() in ("image2image", "img2img"):
        rule_key = "image.image2image.base_cost"
    else:
        rule_key = "image.text2image.base_cost"

    default_val = _get_default_value(rule_key) or 10
    if db is not None:
        try:
            base_cost = await _get_rule_value(db, rule_key, default_val)
        except Exception as e:
            logger.warning("[积分服务] 读取 %s 失败，回落到默认: %s", rule_key, e)
            base_cost = default_val
    else:
        base_cost = default_val

    # 图片尺寸影响（>= 5 积分下限）
    ratio = max(0.5, _parse_size_to_px(size) / (1024.0 * 1024.0))
    return max(5, int(base_cost * ratio))


def get_image_cost(mode: Optional[str] = "text2image", size: Optional[str] = None) -> int:
    """
    同步版本：仅使用默认积分规则计算（保留向后兼容；
    有数据库上下文时，请调用 get_image_cost_async 以读取数据库中的规则）。
    """
    base_cost = 15 if mode and mode.lower() in ("image2image", "img2img") else 10
    ratio = max(0.5, _parse_size_to_px(size) / (1024.0 * 1024.0))
    return max(5, int(base_cost * ratio))


# ---------- 视频：计算一次任务的成本 ----------
async def get_video_cost_async(
    db: AsyncSession,
    mode: Optional[str] = "text2video",
    seconds: int = 5,
    num_frames: Optional[int] = None,
) -> int:
    """异步版本：读取数据库中的视频积分规则"""
    # 每秒消耗基础积分
    if mode and mode.lower() in ("image2video", "keyframes"):
        per_second = _get_default_value("video.image2video.per_second") or 6
        if db is not None:
            try:
                per_second = await _get_rule_value(db, "video.image2video.per_second", per_second)
            except Exception as e:
                logger.warning("[积分服务] 读取 video.image2video.per_second 失败: %s", e)
        mode_factor = 1.2
    else:
        per_second = _get_default_value("video.text2video.per_second") or 5
        if db is not None:
            try:
                per_second = await _get_rule_value(db, "video.text2video.per_second", per_second)
            except Exception as e:
                logger.warning("[积分服务] 读取 video.text2video.per_second 失败: %s", e)
        mode_factor = 1.0

    duration_factor = max(1.0, (seconds or 5) / 5.0)
    frame_factor = max(0.8, (num_frames or 33) / 33.0) if num_frames else 1.0
    return max(10, int(max(1, per_second) * duration_factor * frame_factor * mode_factor))


def get_video_cost(
    mode: Optional[str] = "text2video",
    seconds: int = 5,
    num_frames: Optional[int] = None,
) -> int:
    """同步版本：使用默认值（仅保留向后兼容）"""
    per_second = 5
    duration_factor = max(1.0, (seconds or 5) / 5.0)
    frame_factor = max(0.8, (num_frames or 33) / 33.0) if num_frames else 1.0
    mode_factor = 1.2 if mode and mode.lower() in ("image2video", "keyframes") else 1.0
    return max(10, int(per_second * duration_factor * frame_factor * mode_factor))


# ---------- 扣除积分 ----------
async def consume_credits(
    db: AsyncSession,
    user: Optional[User],
    amount: int,
    description: str = "",
) -> int:
    """
    从用户账户扣除 amount 积分，返回扣除后的余额。
    - user 为 None（匿名）：直接返回 0
    - amount <= 0：不扣除，直接返回原积分
    - 余额不足：抛出 HTTPException(402)
    """
    if user is None:
        return 0
    if amount <= 0:
        return user.credits

    stmt = (
        sa_update(User)
        .where(User.id == user.id)
        .where(User.credits >= amount)
        .values(credits=User.credits - amount)
    )
    result = await db.execute(stmt)
    affected = getattr(result, "rowcount", 0)
    await db.commit()

    if affected == 0:
        result2 = await db.execute(select(User.credits).filter(User.id == user.id))
        current_credits = result2.scalar_one_or_none() or 0
        raise HTTPException(
            status_code=402,
            detail=f"积分不足（当前 {current_credits}，需要 {amount}），请联系管理员充值",
        )

    await db.refresh(user)

    logger.info(
        "[积分消耗] user=%s amount=%d remaining=%d description=%s",
        user.username, amount, user.credits, description,
    )
    return user.credits
