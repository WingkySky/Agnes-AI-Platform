# =====================================================
# Request ID 中间件
# 职责：
#   1. 为每个 HTTP 请求生成唯一 request_id（UUID4）
#   2. 将 request_id 注入 contextvars，供日志系统自动携带
#   3. 在响应头中返回 X-Request-ID，便于前端/Agent 追踪
#   4. 记录请求的基本信息（方法、路径、耗时、状态码）
#
# 关键设计：
#   - 使用 contextvars 实现协程安全的请求上下文传递
#   - request_id 贯穿整个请求链路，日志中可凭此 ID 串联完整调用
#   - 支持前端传入 X-Request-ID 头复用已有 ID（可选）
# =====================================================

import time
import uuid
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_var

logger = logging.getLogger("agnes_platform")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Request ID 中间件：为每个请求分配唯一标识，注入日志上下文。

    工作流程：
      1. 请求到达 → 生成/读取 request_id
      2. 将 request_id 写入 contextvars → 日志 Filter 自动读取
      3. 请求处理完成后 → 在响应头中返回 X-Request-ID
      4. 记录请求摘要日志（方法、路径、耗时、状态码）
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # ---------- 1. 生成或读取 request_id ----------
        # 优先使用前端传入的 X-Request-ID，否则生成新的 UUID
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # ---------- 2. 注入 contextvars ----------
        token = request_id_var.set(req_id)

        # ---------- 3. 记录请求开始 ----------
        start_time = time.time()
        method = request.method
        path = request.url.path

        # 跳过健康检查等高频低价值日志
        if path not in ("/health", "/"):
            logger.info("[请求] %s %s 开始处理", method, path)

        # ---------- 4. 处理请求 ----------
        try:
            response = await call_next(request)
        except Exception as exc:
            # 未被全局异常处理器捕获的异常
            elapsed = time.time() - start_time
            logger.error(
                "[请求] %s %s 异常: %.3fs error=%s",
                method, path, elapsed, str(exc),
                exc_info=True,
            )
            raise
        finally:
            # 确保清理 contextvars，防止协程复用时 ID 泄漏
            request_id_var.reset(token)

        # ---------- 5. 记录请求完成 ----------
        elapsed = time.time() - start_time
        status_code = response.status_code

        if path not in ("/health", "/"):
            # 根据状态码选择日志级别
            if status_code >= 500:
                log_fn = logger.error
            elif status_code >= 400:
                log_fn = logger.warning
            else:
                log_fn = logger.info
            log_fn(
                "[请求] %s %s → %d (%.3fs)",
                method, path, status_code, elapsed,
            )

        # ---------- 6. 响应头注入 request_id ----------
        response.headers["X-Request-ID"] = req_id

        return response
