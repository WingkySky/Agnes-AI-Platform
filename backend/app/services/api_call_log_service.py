# =====================================================
# 上游调用记账服务（api_call_log_service）
#
# record_api_call 在客户端出口（agnes_client / aibridge wrapper）调用，
# best-effort 写库：任何异常只告警，绝不影响生成主流程。
# 错误类目复用 error_taxonomy；user/费用归因走 generations 表（本表可为 NULL）。
# =====================================================

import logging
from typing import Optional

from app.core.database import new_async_session
from app.models.api_call_log import ApiCallLog

logger = logging.getLogger("agnes_platform")


async def record_api_call(
    *,
    provider_name: Optional[str] = None,
    provider_id: Optional[int] = None,
    model: Optional[str] = None,
    call_type: str = "other",
    endpoint: Optional[str] = None,
    status: str = "success",
    error_category: Optional[str] = None,
    error_message: Optional[str] = None,
    request_id: Optional[str] = None,
    latency_ms: Optional[int] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
) -> None:
    """记一行上游调用日志；失败仅告警（可观测性不能拖垮业务）"""
    try:
        async with new_async_session() as session:
            session.add(ApiCallLog(
                provider_id=provider_id,
                provider_name=provider_name,
                model=model,
                call_type=call_type,
                endpoint=endpoint,
                status=status,
                error_category=error_category,
                error_message=(error_message or "")[:2000] or None,
                request_id=request_id,
                latency_ms=latency_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            ))
            await session.commit()
    except Exception as e:
        logger.warning("[ApiCallLog] 写入失败（已忽略）: %s", e)
