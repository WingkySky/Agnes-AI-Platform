# =====================================================
# 项目生成任务提交 + 认领 共享 helper（异步模式）
#
# 复用现有 image_poller_manager / video_poller_manager：
#   - 提交：构建 prompt → 预扣积分 → 调 poller.create_task → 返回 task_id
#   - 认领：任务完成后，前端调 claim 端点 → 查 Generation(task_id) → 写项目实体版本
#
# poller 全权负责：AI 调用 + 积分 confirm/refund + Generation 写入
# 项目模块只负责：prompt 构建 + 提交 + 认领结果到项目实体版本
# =====================================================

import asyncio
import logging
import time
import uuid
import os
import base64
from typing import Optional

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.generation import Generation
from app.models.user import User
from app.models.credit_transaction import CreditTransaction
from app.services.credits_service import (
    get_image_cost_async,
    get_video_cost_async,
    consume_credits,
)
from app.services.image_poller import image_poller_manager
from app.services.video_poller import poller_manager as video_poller_manager

logger = logging.getLogger("agnes_platform.project.async_gen")

# backend/ 目录的绝对路径（用于拼接本地上传文件路径）
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# =====================================================
# 视频生成速率限制器（按 model 缓存，乐观 + 429 降级）
# -------------------------------------------------
# 不同 Provider / 不同模型的限流策略不同：
#   - Agnes AI agnes-video-2.0：每分钟 1 次（HTTP 429:
#     "allows 1 requests per 1 minute(s)"）
#   - 其他模型（volcengine_cv / kling / runway 等）：可能无此限制
#
# 策略：默认乐观直接提交，不预先等待。
#   撞 429 后解析错误信息中的限制时间，缓存该 model 的 next_allowed_time，
#   后续对同 model 的请求自动等待；其他 model 不受影响。
# =====================================================
_model_rate_limit_lock = asyncio.Lock()
# {model_id: next_allowed_time_seconds}
_model_rate_limit: dict = {}
# 429 后默认等待时间（秒），用于解析失败时的兜底
_DEFAULT_RATE_LIMIT_WAIT_SEC = 62.0
# 单次请求最多重试次数（避免无限循环）
_RATE_LIMIT_MAX_RETRY = 3


def _parse_rate_limit_wait(message: str) -> float:
    """
    从 429 错误信息中解析需要等待的秒数。

    示例：
      "allows 1 requests per 1 minute(s)" → 62.0
      "allows 1 requests per 60 second(s)" → 62.0
      "Retry-After: 30" → 32.0
    无法识别时返回默认值 62.0。
    """
    import re
    msg = message or ""
    # 形如 "per 1 minute(s)" / "per 5 minute(s)"
    m = re.search(r"per\s+(\d+)\s*minute", msg, re.IGNORECASE)
    if m:
        return float(m.group(1)) * 60 + 2  # 加 2 秒缓冲
    # 形如 "per 60 second(s)"
    m = re.search(r"per\s+(\d+)\s*second", msg, re.IGNORECASE)
    if m:
        return float(m.group(1)) + 2
    # 形如 "Retry-After: 30"
    m = re.search(r"retry[-_]after[:\s]+(\d+)", msg, re.IGNORECASE)
    if m:
        return float(m.group(1)) + 2
    return _DEFAULT_RATE_LIMIT_WAIT_SEC


def _is_rate_limit_error(exc: BaseException) -> bool:
    """判断异常是否为 429 限流错误"""
    msg = str(exc)
    return (
        "HTTP 429" in msg
        or "rate limit" in msg.lower()
        or "rate_limit" in msg.lower()
        or "too many requests" in msg.lower()
    )


async def _acquire_model_rate_limit(model: str) -> None:
    """
    如果该 model 之前撞过 429（缓存中有 next_allowed_time），
    等待到允许时间；否则立即返回（乐观并发）。
    """
    async with _model_rate_limit_lock:
        next_allowed = _model_rate_limit.get(model, 0)
    now = time.time()
    if next_allowed > now:
        wait = next_allowed - now
        logger.info(
            "[项目异步] 模型 %s 已知限流规则：等待 %.1f 秒",
            model, wait,
        )
        await asyncio.sleep(wait)


async def _record_model_rate_limit(model: str, message: str) -> float:
    """
    撞 429 后记录该 model 的限流规则，返回需要等待的秒数。
    """
    wait_sec = _parse_rate_limit_wait(message)
    async with _model_rate_limit_lock:
        _model_rate_limit[model] = time.time() + wait_sec
    logger.info(
        "[项目异步] 模型 %s 触发限流，缓存等待 %.1f 秒",
        model, wait_sec,
    )
    return wait_sec


async def _call_video_provider_with_rate_limit(
    model: str,
    prompt: str,
    num_frames: int,
    frame_rate: int,
    width: int,
    height: int,
    image_input: Optional[str],
):
    """
    调 Provider 创建视频任务，乐观尝试 + 429 降级重试。

    - 第一次直接调（不等待）
    - 撞 429 → 解析限制时间 → 缓存到 _model_rate_limit → sleep 后重试
    - 同 model 的后续请求进来时，_acquire_model_rate_limit 会自动等待
    - 其他 model 不受影响
    """
    from app.services.provider_registry import provider_registry
    await _acquire_model_rate_limit(model)
    client = await provider_registry.get_client_for_model(model)

    last_exc: Optional[BaseException] = None
    for attempt in range(_RATE_LIMIT_MAX_RETRY + 1):
        try:
            task = await client.create_video_task(
                prompt=prompt,
                model=model,
                num_frames=num_frames,
                frame_rate=frame_rate,
                width=width,
                height=height,
                mode="image2video",
                image=image_input,
            )
            return task
        except Exception as e:
            if not _is_rate_limit_error(e):
                # 非限流错误，直接抛出
                raise
            last_exc = e
            if attempt >= _RATE_LIMIT_MAX_RETRY:
                # 已重试上限，抛出
                raise
            # 记录该 model 的限流规则，sleep 后重试
            wait_sec = await _record_model_rate_limit(model, str(e))
            logger.warning(
                "[项目异步] 模型 %s 第 %s/%s 次撞限流，等待 %.1f 秒后重试",
                model, attempt + 1, _RATE_LIMIT_MAX_RETRY, wait_sec,
            )
            await asyncio.sleep(wait_sec)
            # 重试前再次确认 client（防止 Provider 配置变更）
            client = await provider_registry.get_client_for_model(model)

    if last_exc:
        raise last_exc
    raise RuntimeError("调用视频生成 Provider 失败：未知错误")


# =====================================================
# 内部工具
# =====================================================

def _read_file_as_pure_base64(file_url: str) -> str:
    """
    将本地上传文件路径读为纯 base64 字符串（不带 data: 前缀）。

    file_url 格式为 /uploads/projects/...，相对于 backend/ 目录。
    返回纯 base64 字符串，可直接传给 agnes_client.create_video_task(image=...)
    对应 create_video_task 内部 is_single_i2v_direct 路径（纯 base64 直传，跳过 pass-through）。
    """
    relpath = file_url.lstrip("/")
    filepath = os.path.join(_BACKEND_DIR, relpath)
    filepath = os.path.normpath(filepath)
    if not os.path.isfile(filepath):
        raise RuntimeError(f"文件不存在: {file_url}")
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _read_file_as_data_uri(file_url: str, mime: str = "image/png") -> str:
    """
    将本地上传文件路径读为 Data URI 格式（data:<mime>;base64,<base64>）。

    用于图片生成 API（create_image），该 API 接受 Data URI 格式的图片输入。
    """
    pure_b64 = _read_file_as_pure_base64(file_url)
    return f"data:{mime};base64,{pure_b64}"


async def _get_user(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# =====================================================
# 图片任务提交
# =====================================================

async def submit_image_task(
    db: AsyncSession,
    user_id: int,
    prompt: str,
    model: str,
    size: str,
    mode: str = "text2image",
    image_urls: Optional[list] = None,
    ref_type: str = "project_image",
) -> str:
    """
    预扣积分 + 提交到 image_poller_manager，返回 task_id。

    poller 负责：AI 调用 + confirm/refund 积分 + 写 Generation 记录。
    调用方在任务完成后调 claim_image_result 把结果认领到项目实体。

    注意：image_urls 中的本地路径（/uploads/...）会自动转为 Data URI 格式，
    与 agnes_client.create_image 的预期输入格式一致。
    """
    user = await _get_user(db, user_id)
    if not user:
        raise ValueError(f"用户 {user_id} 不存在")

    cost = await get_image_cost_async(db, mode=mode, size=size)
    task_id = f"proj_img_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    await consume_credits(
        db, user, cost,
        description=f"project/{mode}/{size}",
        ref_type=ref_type,
        ref_id=task_id,
    )

    params = {
        "model": model,
        "size": size,
        "response_format": "url",
        "mode": mode,
        "is_public": False,
    }
    if image_urls:
        # 本地路径转 Data URI（图片 API 接受 Data URI 格式）
        resolved = []
        for url in image_urls:
            if isinstance(url, str) and url.startswith("/uploads/"):
                resolved.append(_read_file_as_data_uri(url))
            else:
                resolved.append(url)
        params["image_urls"] = resolved

    await image_poller_manager.create_task(
        prompt=prompt,
        params=params,
        user_id=user_id,
        credits_consumed=cost,
        task_id=task_id,
    )
    logger.info(
        "[项目异步] 图片任务已提交: task_id=%s user=%s cost=%s mode=%s",
        task_id, user_id, cost, mode,
    )
    return task_id


# =====================================================
# 视频任务提交
# =====================================================

async def submit_video_task(
    db: AsyncSession,
    user_id: int,
    prompt: str,
    model: str,
    duration_ms: int,
    num_frames: int,
    width: int,
    height: int,
    frame_rate: int,
    mode: str,
    image_url: str,
    ref_type: str = "project_video",
) -> str:
    """
    预扣积分 + 通过 provider_registry 路由到对应 Provider 创建视频任务 + 提交到 video_poller_manager，返回 task_id。

    poller 负责：轮询 + confirm/refund + 写 Generation 记录。

    路由：按 model 路由到对应 Provider 的 client
      - agnes provider_type → AgnesAIClient（业务适配层：8n+1 / 8 倍数 / mode 归一化等）
      - 其他 provider_type（volcengine_cv / kling 等）→ AGNSDKClientWrapper（agn-sdk 统一协议层）
    与 video_poller._poll_loop 轮询路径保持一致，避免创建走默认 client、轮询走路由 client 的不一致。

    注意：image_url 为本地路径（/uploads/...）时，自动转为纯 base64 字符串，
    与 create_video_task 内部 is_single_i2v_direct 路径匹配（纯 base64 直传，跳过 pass-through）。
    """
    user = await _get_user(db, user_id)
    if not user:
        raise ValueError(f"用户 {user_id} 不存在")

    seconds = max(1, (duration_ms or 3000) / 1000.0)
    cost = await get_video_cost_async(
        db, mode=mode, seconds=int(seconds), num_frames=num_frames,
    )

    # 视频任务的 task_id 由 Agnes AI 返回，先用临时 ref_id 扣分
    pending_ref_id = f"pending_{uuid.uuid4().hex}"
    await consume_credits(
        db, user, cost,
        description=f"project/{mode}/{int(seconds)}s",
        ref_type=ref_type,
        ref_id=pending_ref_id,
    )

    # 本地路径转纯 base64（视频 API 单图模式接受纯 base64 直传）
    if image_url.startswith("/uploads/"):
        image_input = _read_file_as_pure_base64(image_url)
        logger.info(
            "[项目异步] 帧图已转为纯 base64: %s (len=%s)",
            image_url[:60], len(image_input),
        )
    else:
        image_input = image_url

    # 调 Provider 创建视频任务（乐观尝试 + 429 降级重试）
    # - 第一次直接调，不预先等待
    # - 撞 429 后解析错误信息中的限制时间，缓存到 _model_rate_limit
    # - 同 model 的后续请求进来时自动等待；其他 model 不受影响
    task = await _call_video_provider_with_rate_limit(
        model=model,
        prompt=prompt,
        num_frames=num_frames,
        frame_rate=frame_rate,
        width=width,
        height=height,
        image_input=image_input,
    )
    video_id = task.get("video_id") or task.get("task_id")
    if not video_id:
        raise RuntimeError("视频任务创建未返回 ID")

    # 更新积分流水 ref_id 为真实 task_id（便于 confirm/refund 匹配）
    await db.execute(
        sa_update(CreditTransaction)
        .where(CreditTransaction.ref_id == pending_ref_id)
        .values(ref_id=video_id)
    )
    await db.commit()

    # 提交到 video_poller（负责轮询 + 写 Generation + confirm/refund）
    await video_poller_manager.start_polling(
        task_id=video_id,
        video_id=video_id,
        prompt=prompt,
        params={
            "model": model,
            "mode": mode,
            "duration_ms": duration_ms,
            "num_frames": num_frames,
            "width": width,
            "height": height,
            "frame_rate": frame_rate,
            "is_public": False,
        },
        user_id=user_id,
        credits_consumed=cost,
    )
    logger.info(
        "[项目异步] 视频任务已提交: task_id=%s user=%s cost=%s mode=%s",
        video_id, user_id, cost, mode,
    )
    return video_id


# =====================================================
# 认领结果（任务完成后，查 Generation → 写项目实体版本）
# =====================================================

async def claim_generation(
    db: AsyncSession, task_id: str,
) -> Optional[Generation]:
    """
    根据 task_id 查 Generation 记录。
    用于任务完成后的认领：从 Generation.result_url + generation.id 写入项目实体版本。
    """
    result = await db.execute(
        select(Generation).where(Generation.task_id == task_id)
    )
    return result.scalar_one_or_none()
