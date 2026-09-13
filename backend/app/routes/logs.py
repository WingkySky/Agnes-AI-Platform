# =====================================================
# 日志查询 / 前端错误上报 API
#
# GET    /api/logs            查询日志（管理员，支持多维度过滤与 before 翻页）
# GET    /api/logs/errors     快速获取最近错误日志（管理员）
# GET    /api/logs/stats      日志文件统计（管理员）
# GET    /api/logs/download   下载日志文件（管理员）
# DELETE /api/logs            清空 / 删除日志文件（管理员）
# POST   /api/logs/frontend   前端错误上报（公开：登录页错误也要收集）
#
# 关键设计：
#   - 查询读取 logs/ 下 JSON Lines 或人类可读文本文件，不影响主日志写入
#   - file 参数走白名单（含轮转备份），杜绝目录穿越
#   - 前端错误追加写入 frontend.jsonl，与 errors.jsonl 同目录同轮转策略
#   - 上报端点字段白名单 + 截断 + 每 IP 限频，恒返回 200 防重试风暴
#   - 除上报外全部端点要求 log:view 权限（admin 角色天然持有）
# =====================================================

import json
import logging
import os
import re
import time
from collections import deque
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.response import ok
from app.core.security import get_current_user_optional, require_permission
from app.models.user import User
from app.schemas.logs import BATCH_MAX, FrontendLogReport

logger = logging.getLogger("agnes_platform")
router = APIRouter()

# 可查询 / 下载 / 清空的日志文件白名单（主文件 + 轮转备份）
LOG_FILES = ["agnes_platform.log", "errors.jsonl", "frontend.jsonl"]
BACKUP_SUFFIXES = [".1", ".2", ".3", ".4", ".5"]
ALLOWED_FILES = {name + suffix for name in LOG_FILES for suffix in [""] + BACKUP_SUFFIXES}

# 文本日志行首时间戳（HumanFormatter：2026-09-13 21:26:41.032 [LEVEL] ...）
_TEXT_TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}")

# ---------- 前端上报限频：每 IP 每分钟最多 60 条 ----------
RATE_LIMIT = 60
RATE_WINDOW_SECONDS = 60.0
RATE_MAX_IPS = 1000
_rate_windows: Dict[str, deque] = {}


def _rate_allow(ip: str, count: int) -> bool:
    """滑动窗口限频；超出配额整批丢弃，IP 总数设上限防内存泄漏"""
    now = time.monotonic()
    window = _rate_windows.get(ip)
    if window is None:
        if len(_rate_windows) >= RATE_MAX_IPS:
            _rate_windows.pop(next(iter(_rate_windows)))
        window = _rate_windows[ip] = deque()
    while window and now - window[0] > RATE_WINDOW_SECONDS:
        window.popleft()
    if len(window) + count > RATE_LIMIT:
        return False
    window.extend([now] * count)
    return True


# ---------- frontend.jsonl 写入 logger（独立文件 + 轮转；模块级单例，测试可重置） ----------
_fe_logger: Optional[logging.Logger] = None


def _get_frontend_logger() -> logging.Logger:
    global _fe_logger
    if _fe_logger is None:
        os.makedirs(settings.log_dir, exist_ok=True)
        fe = logging.getLogger("agnes_platform.frontend")
        fe.setLevel(logging.INFO)
        fe.propagate = False
        fe.handlers.clear()
        handler = RotatingFileHandler(
            os.path.join(settings.log_dir, "frontend.jsonl"),
            maxBytes=10_485_760,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        fe.addHandler(handler)
        _fe_logger = fe
    return _fe_logger


def _append_frontend_events(events: List[Dict[str, Any]], user: Optional[User], ip: str, ua: str) -> int:
    """把前端事件归一为与 errors.jsonl 对齐的 JSON 行写入 frontend.jsonl"""
    fe = _get_frontend_logger()
    written = 0
    for event in events:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": event["level"].upper(),
            "request_id": "-",
            "module": "frontend",
            "func": "-",
            "lineno": 0,
            "message": event["message"],
            "exception": event.get("stack"),
            "context": {
                "url": event.get("url"),
                "ip": ip,
                "ua": ua,
                "user_id": user.id if user else None,
                "client_ts": event.get("timestamp"),
            },
        }
        record = logging.LogRecord(
            name="agnes_platform.frontend",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=json.dumps(entry, ensure_ascii=False),
            args=(),
            exc_info=None,
        )
        fe.handle(record)
        written += 1
    return written


# =====================================================
# 工具函数：读取 JSON 日志文件（倒序，最新在前）
# =====================================================
def _read_jsonl_logs(
    path: str,
    level: Optional[str] = None,
    request_id: Optional[str] = None,
    keyword: Optional[str] = None,
    module: Optional[str] = None,
    since: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    读取 JSON Lines 格式日志文件，支持多维度过滤。

    before 为翻页游标：只返回 timestamp 早于该值的条目（取上一页最后一条的 timestamp）。
    """
    if not os.path.exists(path):
        return []

    results: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in reversed(f.readlines()):
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # 过滤：级别
                if level and entry.get("level", "").upper() != level.upper():
                    continue

                # 过滤：request_id
                if request_id and entry.get("request_id") != request_id:
                    continue

                # 过滤：关键词（搜索 message 和 exception 字段）
                if keyword:
                    keyword_lower = keyword.lower()
                    msg = entry.get("message", "").lower()
                    exc = entry.get("exception", "").lower()
                    if keyword_lower not in msg and keyword_lower not in exc:
                        continue

                # 过滤：模块名
                if module and module.lower() not in entry.get("module", "").lower():
                    continue

                # 过滤：时间范围
                entry_ts = entry.get("timestamp", "")
                if before and entry_ts >= before:
                    continue
                if since and entry_ts < since:
                    break  # 倒序读取，时间已过范围，后续更旧

                results.append(entry)
                if len(results) >= limit:
                    break

    except Exception as e:
        logger.error("[日志API] 读取日志文件失败: %s", e)

    return results


# =====================================================
# 工具函数：读取人类可读日志文件
# =====================================================
def _read_text_logs(
    path: str,
    level: Optional[str] = None,
    keyword: Optional[str] = None,
    since: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    读取人类可读格式日志文件。返回结构化结果，每条包含 raw（原始行）与解析出的 timestamp / level。
    """
    if not os.path.exists(path):
        return []

    results: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in reversed(f.readlines()):
                line = line.strip()
                if not line:
                    continue

                # 关键词过滤
                if keyword and keyword.lower() not in line.lower():
                    continue

                entry: Dict[str, Any] = {"raw": line}

                # 解析行首时间戳与级别：2026-09-13 21:26:41.032 [INFO] [req] module ...
                ts_match = _TEXT_TS_PATTERN.match(line)
                if ts_match:
                    entry["timestamp"] = ts_match.group(0)
                if "[" in line:
                    level_start = line.index("[") + 1
                    level_end = line.find("]", level_start)
                    if level_end > level_start:
                        entry["level"] = line[level_start:level_end]

                # 过滤：级别
                if level and entry.get("level", "").upper() != level.upper():
                    continue

                # 过滤：时间范围
                entry_ts = entry.get("timestamp", "")
                if before and entry_ts and entry_ts >= before:
                    continue
                if since and entry_ts and entry_ts < since:
                    break  # 倒序读取，时间已过范围，后续更旧

                results.append(entry)
                if len(results) >= limit:
                    break

    except Exception as e:
        logger.error("[日志API] 读取文本日志文件失败: %s", e)

    return results


def _resolve_log_path(file: str) -> str:
    """白名单校验 + realpath 规范化（父目录必须等于日志目录），杜绝目录穿越；返回绝对路径"""
    if file not in ALLOWED_FILES:
        raise HTTPException(status_code=400, detail=f"不支持的日志文件：{file}")
    base = os.path.realpath(settings.log_dir)
    path = os.path.realpath(os.path.join(base, file))
    if os.path.dirname(path) != base:
        raise HTTPException(status_code=400, detail=f"不支持的日志文件：{file}")
    return path


# =====================================================
# 日志查询接口（管理员）
# =====================================================
@router.get(
    "/logs",
    summary="查询日志（管理员，支持多维度过滤与翻页）",
    dependencies=[Depends(require_permission("log:view"))],
)
async def query_logs(
    level: Optional[str] = Query(None, description="按级别过滤：INFO / WARNING / ERROR / CRITICAL"),
    request_id: Optional[str] = Query(None, description="按请求 ID 过滤，串联完整请求链路"),
    keyword: Optional[str] = Query(None, description="关键词搜索（匹配消息和异常信息）"),
    module: Optional[str] = Query(None, description="按模块名过滤（如 agnes_client、video_poller、frontend）"),
    since: Optional[str] = Query(None, description="起始时间（ISO 格式，如 2024-01-01T00:00:00）"),
    before: Optional[str] = Query(None, description="翻页游标：只返回早于该时间的条目（取上一页最后一条 timestamp）"),
    limit: int = Query(50, ge=1, le=200, description="返回条数限制（1-200）"),
    file: str = Query("errors.jsonl", description="日志文件名（白名单：agnes_platform.log[.1~.5] / errors.jsonl / frontend.jsonl）"),
):
    """
    查询日志，支持按级别、request_id、关键词、模块、时间范围过滤。

    示例：
      - 查询最近错误：GET /api/logs?level=ERROR&limit=10
      - 按请求追踪：GET /api/logs?request_id=xxx-xxx
      - 查看前端上报：GET /api/logs?file=frontend.jsonl
      - 翻页：GET /api/logs?before=<上一页最后一条 timestamp>
    """
    log_path = _resolve_log_path(file)

    if not os.path.exists(log_path):
        return ok(data={"logs": [], "total": 0, "file": file}, message="日志文件不存在，可能尚未生成")

    if file.endswith(".jsonl"):
        logs = _read_jsonl_logs(
            path=log_path,
            level=level,
            request_id=request_id,
            keyword=keyword,
            module=module,
            since=since,
            before=before,
            limit=limit,
        )
    else:
        logs = _read_text_logs(
            path=log_path,
            level=level,
            keyword=keyword,
            since=since,
            before=before,
            limit=limit,
        )

    return ok(data={"logs": logs, "total": len(logs), "file": file})


@router.get(
    "/logs/errors",
    summary="快速获取最近错误日志（管理员）",
    dependencies=[Depends(require_permission("log:view"))],
)
async def get_recent_errors(
    limit: int = Query(20, ge=1, le=100, description="返回条数限制"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
):
    """
    快速获取最近的错误日志（仅 ERROR 和 CRITICAL 级别）。
    适用于 Agent 快速定位最近发生的错误。
    """
    log_path = os.path.join(settings.log_dir, "errors.jsonl")

    if not os.path.exists(log_path):
        return ok(data={"errors": [], "total": 0}, message="日志文件不存在")

    # 先查 ERROR 级别
    errors = _read_jsonl_logs(path=log_path, level="ERROR", keyword=keyword, limit=limit)

    # 如果不够，补充 CRITICAL 级别
    if len(errors) < limit:
        criticals = _read_jsonl_logs(path=log_path, level="CRITICAL", keyword=keyword, limit=limit - len(errors))
        errors.extend(criticals)

    # 按时间倒序排列
    errors.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return ok(data={"errors": errors[:limit], "total": len(errors[:limit])})


@router.get(
    "/logs/stats",
    summary="日志统计信息（管理员）",
    dependencies=[Depends(require_permission("log:view"))],
)
async def get_log_stats():
    """
    获取日志统计信息，包括文件大小、日志条数等。
    """
    log_dir = settings.log_dir

    if not os.path.exists(log_dir):
        return ok(data={"exists": False}, message="日志目录不存在")

    stats: Dict[str, Any] = {"exists": True, "files": {}}

    for filename in os.listdir(log_dir):
        filepath = os.path.join(log_dir, filename)
        if not os.path.isfile(filepath):
            continue

        file_stat = os.stat(filepath)
        file_info: Dict[str, Any] = {
            "size_bytes": file_stat.st_size,
            "size_mb": round(file_stat.st_size / (1024 * 1024), 2),
            "modified": datetime.fromtimestamp(
                file_stat.st_mtime, tz=timezone.utc
            ).isoformat(),
        }

        # JSON Lines 文件：统计行数
        if filename.endswith(".jsonl"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    file_info["line_count"] = sum(1 for _ in f)
            except Exception:
                pass

        stats["files"][filename] = file_info

    return ok(data=stats)


@router.get(
    "/logs/download",
    summary="下载日志文件（管理员）",
    dependencies=[Depends(require_permission("log:view"))],
)
async def download_log(
    file: str = Query(..., description="日志文件名（白名单内，含轮转备份）"),
):
    log_path = _resolve_log_path(file)
    if not os.path.exists(log_path):
        raise HTTPException(status_code=404, detail="日志文件不存在")
    return FileResponse(log_path, filename=file)


@router.delete(
    "/logs",
    summary="清空 / 删除日志文件（管理员）",
    dependencies=[Depends(require_permission("log:view"))],
)
async def clear_log(
    file: str = Query(..., description="日志文件名（主文件清空并删除轮转备份；备份文件单独删除）"),
):
    log_path = _resolve_log_path(file)
    removed: List[str] = []

    if file in LOG_FILES:
        # 主文件：删除轮转备份后截断当前文件（写入 handler 仍持有句柄，不能删除）
        for suffix in BACKUP_SUFFIXES:
            backup_path = log_path + suffix
            if os.path.exists(backup_path):
                os.remove(backup_path)
                removed.append(file + suffix)
        if os.path.exists(log_path):
            Path(log_path).write_text("", encoding="utf-8")
    else:
        # 备份文件：单独删除
        if os.path.exists(log_path):
            os.remove(log_path)
            removed.append(file)

    return ok(data={"cleared": file, "removed": removed})


# =====================================================
# 前端错误上报（公开：登录页错误也要收集）
# =====================================================
@router.post("/logs/frontend", summary="前端错误上报（公开，限频 + 字段白名单）")
async def report_frontend_logs(
    report: FrontendLogReport,
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
):
    """
    浏览器端错误批量上报。字段白名单 + 超长截断 + 每 IP 限频，
    客户端不重试，因此除参数级错误外恒返回 200。
    """
    if len(report.events) > BATCH_MAX:
        raise HTTPException(status_code=400, detail=f"单批最多 {BATCH_MAX} 条事件")

    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    events = [event.model_dump() for event in report.events]

    if not _rate_allow(ip, len(events)):
        return ok(data={"received": 0})

    written = _append_frontend_events(events, user, ip, ua)
    return ok(data={"received": written})
