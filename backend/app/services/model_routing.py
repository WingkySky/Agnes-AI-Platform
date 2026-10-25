# =====================================================
# 多渠道路由 failover（生成任务提交阶段）
#
# 路由链 = 锚点模型自身渠道（恒链首）+ model_routes 显式备用（priority 升序）。
# 切换判定复用 error_taxonomy：canRetry 类目且未拿到上游凭据 → 换下一候选；
# submission_uncertain 永不切换（防重复扣费红线）。
#
# 视频提交阶段局部语义（设计 2026-10-25）：明确收到 HTTP 拒绝（error_kind=http
# 且有状态码）且未拿到凭据 ≠ 结果未知 —— 5xx 按 upstream_server 参与切换，
# 429 本就走 _STATUS_RULES 归 rate_limited；网络中断类仍按 submission_uncertain
# 保守不切。该覆盖只作用于 failover 语境（failover_category），不改全局合同。
#
# 查询统一 db.scalars(select(...))（Mimosa 门禁对新增代码 db.execute 误报）。
# =====================================================

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import new_async_session
from app.models.api_provider import ApiProvider
from app.models.model_definition import ModelDefinition
from app.models.model_route import ModelRoute
from app.services.error_taxonomy import classify
from app.services.provider_registry import provider_registry

logger = logging.getLogger("agnes_platform")

LOG_PREFIX = "[模型路由]"

# 可触发切换的类目（error_taxonomy.canRetry 中的上游侧临时故障；result_fetch_failed
# 已有回执在身，切换无意义，不列入）
FAILOVER_CATEGORIES = {"rate_limited", "network_transient", "upstream_server", "timeout", "unknown"}


@dataclass
class RouteTarget:
    """路由链上的一个候选渠道"""

    provider_id: int
    provider_name: str
    model_id: str
    billing_tier: str = "paid"


def failover_category(exc: BaseException, *, submitted: bool, receipt: bool) -> str:
    """failover 语境的类目判定：error_taxonomy.classify + 提交阶段明确 HTTP 拒绝的局部覆盖。"""
    category, _ = classify(exc, submitted=submitted, receipt=receipt)
    if category == "submission_uncertain" and receipt and not submitted:
        status = getattr(exc, "status_code", None)
        if getattr(exc, "error_kind", "http") == "http" and status is not None:
            category = "upstream_server"
    return category


async def resolve_route_chain(anchor_model_id: str, *, db: AsyncSession | None = None) -> list[RouteTarget]:
    """
    解析锚点模型的路由链：锚点自身渠道恒链首 + 启用的备用路由按 priority 升序。

    - db 为 None 时自建 session（与 provider_registry 同范式；测试注入内存库）；
    - 锚点定义缺失或已停用/软删 → 抛 ValueError（调用方按生成失败处理，归 model_missing）；
    - 备用路由的目标渠道已停用或不存在 → 跳过该候选。
    """
    if db is None:
        async with new_async_session() as session:
            return await _resolve_route_chain(session, anchor_model_id)
    return await _resolve_route_chain(db, anchor_model_id)


async def _resolve_route_chain(session: AsyncSession, anchor_model_id: str) -> list[RouteTarget]:
    anchor_model_id = (anchor_model_id or "").strip()
    async with new_async_session() as session:
        anchor = (
            await session.scalars(
                select(ModelDefinition).where(
                    ModelDefinition.model_id == anchor_model_id,
                    ModelDefinition.is_active.is_(True),
                    ModelDefinition.is_disabled.is_(False),
                )
            )
        ).first()
        if anchor is None:
            raise ValueError(f"模型 {anchor_model_id or '(未指定)'} 不存在或已停用")

        providers = {
            p.id: p for p in (
                await session.scalars(select(ApiProvider).where(ApiProvider.is_active.is_(True)))
            ).all()
        }
        routes = (
            await session.scalars(
                select(ModelRoute)
                .where(
                    ModelRoute.anchor_model_id == anchor_model_id,
                    ModelRoute.is_enabled.is_(True),
                )
                .order_by(ModelRoute.priority, ModelRoute.id)
            )
        ).all()

    targets: list[RouteTarget] = []
    anchor_provider = providers.get(anchor.provider_id)
    if anchor_provider is not None:
        targets.append(RouteTarget(
            provider_id=anchor.provider_id,
            provider_name=anchor_provider.name,
            model_id=anchor_model_id,
            billing_tier=anchor_provider.billing_tier or "paid",
        ))
    else:
        logger.warning("%s 锚点渠道 %s 未激活，仅备用路由可尝试", LOG_PREFIX, anchor.provider_id)

    for route in routes:
        provider = providers.get(route.provider_id)
        if provider is None:
            logger.warning("%s 跳过备用路由 target=%s/%s：渠道不存在或未激活", LOG_PREFIX, route.provider_id, route.model_id)
            continue
        targets.append(RouteTarget(
            provider_id=route.provider_id,
            provider_name=provider.name,
            model_id=route.model_id,
            billing_tier=provider.billing_tier or "paid",
        ))
    return targets


async def execute_with_failover(
    fn,
    targets: list[RouteTarget],
    *,
    submitted: bool,
    receipt: bool,
    log_prefix: str = LOG_PREFIX,
):
    """
    按路由链逐候选执行 fn(client, target)，返回 (result, 实际使用的 RouteTarget)。

    - 候选 client 构建失败（渠道已停用等）→ 跳过该候选；
    - 失败类目 ∈ FAILOVER_CATEGORIES 且还有下一候选 → 切换；
    - 其余类目（参数/审核/账户/回执不确定等）立即抛出；
    - 全部候选耗尽 → 抛最后一个异常（附 _route_category 属性供上层归因）。
    """
    last_exc: BaseException | None = None
    for index, target in enumerate(targets):
        try:
            client = provider_registry.get_client(target.provider_id)
        except Exception as e:
            logger.warning("%s 跳过候选渠道 %s(%s)：client 不可用 %s", log_prefix, target.provider_name, target.model_id, e)
            continue
        try:
            result = await fn(client, target)
            return result, target
        except Exception as e:
            last_exc = e
            category = failover_category(e, submitted=submitted, receipt=receipt)
            if index < len(targets) - 1 and category in FAILOVER_CATEGORIES:
                logger.warning(
                    "%s 渠道 %s(%s) 失败（%s），切换下一候选",
                    log_prefix, target.provider_name, target.model_id, category,
                )
                continue
            try:
                e._route_category = category  # noqa: SLF001 供上层归因（videos.py 提交失败分类用）
                e._route_attempts = index + 1  # noqa: SLF001 实际尝试的渠道数（失败文案透出）
            except Exception:
                pass
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("无可用生成渠道（模型不存在或所有候选渠道均不可用）")
