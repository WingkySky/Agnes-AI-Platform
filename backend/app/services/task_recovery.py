# =====================================================
# 任务恢复体系 —— 进程重启后按账本恢复在途任务 + 运行时对账
#
# 事实源 = generations 表的 pending/processing 账本行（提交即落，
# 终态由轮询器幂等 upsert）。本模块职责：
#   1. recover_pending_tasks：lifespan 启动时调用——
#      视频行凭 task_id/video_id 重注册续轮询（本地 task_id 不变，前端无感）；
#      超限视频行与全部图片行（同步接口无上游凭据）置 uncertain + 退积分。
#   2. _reconcile_loop：周期兜底——轮询协程异常死亡漏置终态的行，
#      超过 age 上限后对账退款（refund 按 pending 流水过滤，幂等）。
# =====================================================

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.database import new_async_session
from app.models.generation import Generation
from app.services._generation_persist import finalize_uncertain
from app.services.video_poller import poller_manager

logger = logging.getLogger("agnes_platform")

LOG_PREFIX = "[任务恢复]"
# 视频恢复窗口：重注册后轮询器自带的 max_wait 仍生效，这里只挡「早已该终态」的陈年行
RECONCILE_INTERVAL_SEC = 300


def _max_age_sec() -> int:
    return 2 * int(settings.video_poll_timeout_sec or 600)


def _age_sec(created_at: datetime | None) -> float:
    """账本行年龄（秒）。created_at 是 naive UTC（datetime.utcnow 惯例），
    必须显式挂 UTC 后再做差——直接 .timestamp() 会按本地时区解释产生时区偏移量级的偏差。"""
    if created_at is None:
        return float("inf")
    return (datetime.now(UTC) - created_at.replace(tzinfo=UTC)).total_seconds()


async def _pending_rows() -> list[Generation]:
    async with new_async_session() as db:
        stmt = select(Generation).filter(
            Generation.status.in_(("pending", "processing")),
            Generation.type.in_(("image", "video")),
            Generation.task_id.isnot(None),
        )
        return list((await db.scalars(stmt)).all())


async def recover_pending_tasks() -> dict[str, int]:
    """
    启动恢复：扫描账本未终态行，视频续轮询、其余对账退款。

    必须在 provider_registry 初始化与两个 poller start 之后调用。
    返回各分支计数（日志与测试断言用）。
    """
    rows = await _pending_rows()
    counts = {"video_resumed": 0, "video_finalized": 0, "image_finalized": 0}
    if not rows:
        return counts

    max_age = _max_age_sec()
    for row in rows:
        age = _age_sec(row.created_at)
        if row.type == "video" and age <= max_age:
            await poller_manager.start_polling(
                task_id=row.task_id,
                video_id=row.video_id,
                prompt=row.prompt or "",
                params=row.params or {},
                user_id=row.user_id,
                credits_consumed=row.credits_consumed or 0,
                preset_id=row.preset_id,
                context=row.context,
            )
            counts["video_resumed"] += 1
            logger.warning(
                "%s 在途视频任务已恢复轮询: task_id=%s video_id=%s age=%.0fs",
                LOG_PREFIX, row.task_id, row.video_id, max(age, 0),
            )
        else:
            kind_label = "视频" if row.type == "video" else "图片"
            reason = (
                f"进程重启后{kind_label}任务已超出等待窗口，无法确认生成结局"
                if row.type == "video"
                else "进程重启中断了图片生成，无法确认生成结局"
            )
            done = await finalize_uncertain(
                kind=row.type,
                user_id=row.user_id,
                task_id=row.task_id,
                reason=reason,
                log_prefix=LOG_PREFIX,
            )
            if done:
                if row.type == "video":
                    counts["video_finalized"] += 1
                else:
                    counts["image_finalized"] += 1
    logger.warning(
        "%s 启动恢复完成: 共 %d 行，视频续轮询 %d / 视频对账 %d / 图片对账 %d",
        LOG_PREFIX, len(rows),
        counts["video_resumed"], counts["video_finalized"], counts["image_finalized"],
    )
    return counts


async def _reconcile_loop() -> None:
    """周期兜底：pending/processing 行超过 age 上限（轮询协程死亡/上游失联）→ 对账退款。"""
    while True:
        await asyncio.sleep(RECONCILE_INTERVAL_SEC)
        try:
            rows = await _pending_rows()
            if not rows:
                continue
            max_age = _max_age_sec()
            for row in rows:
                if _age_sec(row.created_at) <= max_age:
                    continue
                await finalize_uncertain(
                    kind=row.type,
                    user_id=row.user_id,
                    task_id=row.task_id,
                    reason="任务长时间未到终态（轮询异常终止），已对账退款",
                    log_prefix=LOG_PREFIX,
                )
        except Exception as e:
            logger.error("%s 对账协程异常: %s", LOG_PREFIX, e, exc_info=True)


def start_reconcile_loop() -> Any:
    """启动周期对账协程（lifespan 调用一次；返回 task 便于测试/关闭）"""
    return asyncio.create_task(_reconcile_loop())
