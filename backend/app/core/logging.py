# =====================================================
# 日志配置中心
# 负责：
#   1. 统一配置日志 Handler（控制台 + 文件轮转）
#   2. 提供 JSON 格式化器（ERROR 级别输出 JSON，便于 Agent 解析）
#   3. 提供 Request ID 过滤器（通过 contextvars 自动注入请求 ID）
#   4. 日志文件自动轮转（按大小，防止磁盘爆满）
#
# 关键设计：
#   - INFO 及以下级别：人类可读格式（控制台 + 文件）
#   - WARNING 及以上级别：同时输出 JSON 格式到独立文件（errors.jsonl）
#   - 每条日志自动携带 request_id（如有），串联完整请求链路
#   - 全部使用 Python 标准库，无需额外依赖
# =====================================================

import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional


# ---------- 请求 ID 上下文变量（全局共享）----------
# 中间件写入，日志 Filter 读取，实现请求链路追踪
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


# =====================================================
# Request ID 过滤器 — 自动注入 request_id 到日志记录
# =====================================================
class RequestIdFilter(logging.Filter):
    """
    日志过滤器：从 contextvars 中读取当前请求的 request_id，
    注入到 LogRecord 的 request_id 属性中，便于格式化输出。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"  # type: ignore[attr-defined]
        return True


# =====================================================
# JSON 格式化器 — ERROR 级别输出结构化 JSON
# =====================================================
class JsonFormatter(logging.Formatter):
    """
    将日志记录格式化为 JSON 字符串，便于 Agent/程序化解析。
    输出字段：timestamp, level, request_id, module, func, lineno, message, exception
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "request_id": getattr(record, "request_id", "-"),
            "module": record.module,
            "func": record.funcName,
            "lineno": record.lineno,
            "message": record.getMessage(),
        }

        # 异常信息
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # 额外上下文（如 task_id、video_id 等）
        if hasattr(record, "extra_context") and isinstance(record.extra_context, dict):
            log_entry["context"] = record.extra_context

        return json.dumps(log_entry, ensure_ascii=False)


# =====================================================
# 人类可读格式化器 — 控制台和普通日志文件
# =====================================================
class HumanFormatter(logging.Formatter):
    """
    人类可读的日志格式，在标准格式基础上增加 request_id 和模块信息。
    格式：2026-06-25 15:30:45.123 [INFO] [req-xxx] module.func:12: 消息内容
    包含毫秒精度，便于排查性能问题和请求耗时
    """

    def __init__(self, datefmt: str = None):
        # 正确设置格式字符串到 self._fmt（而不是 record._fmt）
        # 增加毫秒显示（%(msecs)03d）
        fmt = (
            "%(asctime)s.%(msecs)03d [%(levelname)s] "
            "[%(request_id)s] "
            "%(module)s.%(funcName)s:%(lineno)d: "
            "%(message)s"
        )
        # 默认日期格式：年-月-日 时:分:秒
        default_datefmt = "%Y-%m-%d %H:%M:%S"
        super().__init__(fmt=fmt, datefmt=datefmt or default_datefmt)

    def format(self, record: logging.LogRecord) -> str:
        # 确保 request_id 属性存在（防止没有经过 RequestIdFilter 的日志报错）
        if not hasattr(record, "request_id"):
            record.request_id = "-"  # type: ignore[attr-defined]
        return super().format(record)


# =====================================================
# 日志初始化入口
# =====================================================
def setup_logging(
    log_level: str = "INFO",
    log_file_enabled: bool = True,
    log_dir: str = "./logs",
    log_max_bytes: int = 10_485_760,  # 10MB
    log_backup_count: int = 5,
    log_json_enabled: bool = True,
) -> logging.Logger:
    """
    初始化日志系统，返回配置好的 Logger 实例。

    参数：
        log_level: 全局日志级别
        log_file_enabled: 是否启用文件日志
        log_dir: 日志文件目录
        log_max_bytes: 单个日志文件最大字节数
        log_backup_count: 保留的备份文件数量
        log_json_enabled: 是否启用 JSON 格式错误日志
    """
    # 确保日志目录存在
    if log_file_enabled:
        os.makedirs(log_dir, exist_ok=True)

    # 获取根 Logger
    logger = logging.getLogger("agnes_platform")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # 清除已有 Handler（防止重复添加）
    logger.handlers.clear()

    # 公共过滤器：注入 request_id
    request_id_filter = RequestIdFilter()

    # ---------- Handler 1：控制台输出（人类可读）----------
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.addFilter(request_id_filter)
    console_handler.setFormatter(HumanFormatter(datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(console_handler)

    if log_file_enabled:
        # ---------- Handler 2：全量日志文件（人类可读）----------
        all_log_path = os.path.join(log_dir, "agnes_platform.log")
        file_handler = RotatingFileHandler(
            all_log_path,
            maxBytes=log_max_bytes,
            backupCount=log_backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.addFilter(request_id_filter)
        file_handler.setFormatter(HumanFormatter(datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(file_handler)

        if log_json_enabled:
            # ---------- Handler 3：错误日志文件（JSON 格式，每行一条）----------
            error_log_path = os.path.join(log_dir, "errors.jsonl")
            error_handler = RotatingFileHandler(
                error_log_path,
                maxBytes=log_max_bytes,
                backupCount=log_backup_count,
                encoding="utf-8",
            )
            error_handler.setLevel(logging.WARNING)  # WARNING 及以上
            error_handler.addFilter(request_id_filter)
            error_handler.setFormatter(JsonFormatter())
            logger.addHandler(error_handler)

    # 禁止日志向上传播，避免重复输出
    logger.propagate = False

    # ---------- 统一配置 uvicorn 相关 logger，使用相同格式 ----------
    # 解决 uvicorn 默认访问日志格式不一致、重复输出、无 request_id 的问题
    # - uvicorn / uvicorn.error：使用和业务日志相同的级别和格式
    # - uvicorn.access：设置为 WARNING 级别，不打印 INFO 访问日志
    #   （因为我们自己的 RequestIdMiddleware 已经在打印更详细的请求日志，包含 request_id 和精确耗时）
    for uvicorn_logger_name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        uvicorn_logger.addHandler(console_handler)
        if log_file_enabled:
            uvicorn_logger.addHandler(file_handler)
        uvicorn_logger.propagate = False

    # uvicorn.access：只保留 WARNING 及以上级别的日志（避免重复打印访问日志）
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.setLevel(logging.WARNING)
    access_logger.addHandler(console_handler)
    if log_file_enabled:
        access_logger.addHandler(file_handler)
    access_logger.propagate = False

    return logger


# =====================================================
# 便捷函数：获取带模块标识的子 Logger
# =====================================================
def get_logger(name: str = "agnes_platform") -> logging.Logger:
    """
    获取日志记录器。
    用法：logger = get_logger("agnes_platform")
    """
    return logging.getLogger(name)


# =====================================================
# 便捷函数：记录带上下文的日志
# =====================================================
def log_with_context(
    level: int,
    message: str,
    *,
    task_id: Optional[str] = None,
    video_id: Optional[str] = None,
    image_id: Optional[str] = None,
    **extra_kwargs,
):
    """
    记录带业务上下文的日志，上下文信息会附加到 JSON 日志的 context 字段中。

    用法：
        log_with_context(logging.ERROR, "视频生成失败", task_id="xxx", video_id="yyy")
    """
    logger = get_logger()
    context = {}
    if task_id:
        context["task_id"] = task_id
    if video_id:
        context["video_id"] = video_id
    if image_id:
        context["image_id"] = image_id
    context.update(extra_kwargs)

    record = logger.makeRecord(
        name=logger.name,
        level=level,
        fn="",
        lno=0,
        msg=message,
        args=(),
        exc_info=None,
    )
    record.extra_context = context  # type: ignore[attr-defined]
    logger.handle(record)
