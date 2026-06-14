# =====================================================
# 日志查询 API（供 Agent / 运维使用）
# GET /api/logs          - 查询日志（支持多维度过滤）
# GET /api/logs/errors   - 快速获取最近错误日志
# GET /api/logs/stats    - 日志统计信息
#
# 关键设计：
#   - 读取 errors.jsonl 文件（JSON 格式，每行一条，易于解析）
#   - 支持按级别、request_id、关键词、模块、时间范围过滤
#   - Agent 出错时可直接调此 API 查日志定位问题
#   - 仅读取 JSON 日志文件，不影响主日志性能
# =====================================================

import json
import os
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings

logger = __import__("logging").getLogger("agnes_platform")
router = APIRouter()


# =====================================================
# 工具函数：读取 JSON 日志文件
# =====================================================
def _read_jsonl_logs(
    log_dir: str,
    filename: str = "errors.jsonl",
    level: Optional[str] = None,
    request_id: Optional[str] = None,
    keyword: Optional[str] = None,
    module: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    读取 JSON Lines 格式的日志文件，支持多维度过滤。

    参数：
        log_dir: 日志目录
        filename: 日志文件名
        level: 按级别过滤（WARNING/ERROR/CRITICAL）
        request_id: 按请求 ID 过滤
        keyword: 关键词搜索（匹配 message 字段）
        module: 按模块名过滤
        since: 起始时间（ISO 格式字符串）
        limit: 最大返回条数
    """
    log_path = os.path.join(log_dir, filename)
    if not os.path.exists(log_path):
        return []

    results: List[Dict[str, Any]] = []

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            # 从文件末尾倒序读取，优先返回最新日志
            lines = f.readlines()
            for line in reversed(lines):
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
                if since:
                    entry_ts = entry.get("timestamp", "")
                    if entry_ts < since:
                        # 由于是倒序读取，时间已过范围，后续更旧，可提前终止
                        break

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
    log_dir: str,
    filename: str = "agnes_platform.log",
    keyword: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    读取人类可读格式的日志文件，按关键词过滤。
    返回结构化结果，每条包含 raw（原始行）和 parsed 信息。
    """
    log_path = os.path.join(log_dir, filename)
    if not os.path.exists(log_path):
        return []

    results: List[Dict[str, Any]] = []

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue

                # 关键词过滤
                if keyword and keyword.lower() not in line.lower():
                    continue

                # 尝试提取基本字段
                entry: Dict[str, Any] = {"raw": line}

                # 解析格式：2024-01-01 12:00:00 [LEVEL] [req-id] module.func:12: message
                try:
                    if "[" in line:
                        # 提取级别
                        level_start = line.index("[") + 1
                        level_end = line.index("]", level_start)
                        entry["level"] = line[level_start:level_end]
                except (ValueError, IndexError):
                    pass

                results.append(entry)
                if len(results) >= limit:
                    break

    except Exception as e:
        logger.error("[日志API] 读取文本日志文件失败: %s", e)

    return results


# =====================================================
# 日志查询接口
# =====================================================
@router.get("/logs", summary="查询日志（支持多维度过滤）")
async def query_logs(
    level: Optional[str] = Query(
        None, description="按级别过滤：WARNING / ERROR / CRITICAL"
    ),
    request_id: Optional[str] = Query(
        None, description="按请求 ID 过滤，串联完整请求链路"
    ),
    keyword: Optional[str] = Query(
        None, description="关键词搜索（匹配消息和异常信息）"
    ),
    module: Optional[str] = Query(
        None, description="按模块名过滤（如 agnes_client、video_poller）"
    ),
    since: Optional[str] = Query(
        None, description="起始时间（ISO 格式，如 2024-01-01T00:00:00）"
    ),
    limit: int = Query(
        50, ge=1, le=200, description="返回条数限制（1-200）"
    ),
    format: str = Query(
        "json", description="日志格式：json（JSON Lines 文件）/ text（普通文本文件）"
    ),
):
    """
    查询日志，支持按级别、request_id、关键词、模块、时间范围过滤。
    Agent 出错时可直接调此接口定位问题。

    示例：
      - 查询最近错误：GET /api/logs?level=ERROR&limit=10
      - 按请求追踪：GET /api/logs?request_id=xxx-xxx
      - 关键词搜索：GET /api/logs?keyword=视频生成失败
    """
    log_dir = settings.log_dir

    if not os.path.exists(log_dir):
        return {"logs": [], "total": 0, "message": "日志目录不存在，可能尚未生成日志文件"}

    if format == "json":
        logs = _read_jsonl_logs(
            log_dir=log_dir,
            level=level,
            request_id=request_id,
            keyword=keyword,
            module=module,
            since=since,
            limit=limit,
        )
    else:
        logs = _read_text_logs(
            log_dir=log_dir,
            keyword=keyword,
            limit=limit,
        )

    return {
        "logs": logs,
        "total": len(logs),
        "query": {
            "level": level,
            "request_id": request_id,
            "keyword": keyword,
            "module": module,
            "since": since,
            "limit": limit,
            "format": format,
        },
    }


@router.get("/logs/errors", summary="快速获取最近错误日志")
async def get_recent_errors(
    limit: int = Query(
        20, ge=1, le=100, description="返回条数限制"
    ),
    keyword: Optional[str] = Query(
        None, description="关键词搜索"
    ),
):
    """
    快速获取最近的错误日志（仅 ERROR 和 CRITICAL 级别）。
    适用于 Agent 快速定位最近发生的错误。
    """
    log_dir = settings.log_dir

    if not os.path.exists(log_dir):
        return {"errors": [], "total": 0, "message": "日志目录不存在"}

    # 先查 ERROR 级别
    errors = _read_jsonl_logs(
        log_dir=log_dir,
        level="ERROR",
        keyword=keyword,
        limit=limit,
    )

    # 如果不够，补充 CRITICAL 级别
    if len(errors) < limit:
        criticals = _read_jsonl_logs(
            log_dir=log_dir,
            level="CRITICAL",
            keyword=keyword,
            limit=limit - len(errors),
        )
        errors.extend(criticals)

    # 按时间倒序排列
    errors.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return {
        "errors": errors[:limit],
        "total": len(errors[:limit]),
    }


@router.get("/logs/stats", summary="日志统计信息")
async def get_log_stats():
    """
    获取日志统计信息，包括文件大小、日志条数等。
    """
    log_dir = settings.log_dir

    if not os.path.exists(log_dir):
        return {"exists": False, "message": "日志目录不存在"}

    stats: Dict[str, Any] = {"exists": True, "files": {}}

    for filename in os.listdir(log_dir):
        filepath = os.path.join(log_dir, filename)
        if not os.path.isfile(filepath):
            continue

        file_stat = os.stat(filepath)
        file_info: Dict[str, Any] = {
            "size_bytes": file_stat.st_size,
            "size_mb": round(file_stat.st_size / (1024 * 1024), 2),
            "modified": __import__("datetime").datetime.fromtimestamp(
                file_stat.st_mtime,
                tz=__import__("datetime").timezone.utc,
            ).isoformat(),
        }

        # JSON Lines 文件：统计行数
        if filename.endswith(".jsonl"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    line_count = sum(1 for _ in f)
                file_info["line_count"] = line_count
            except Exception:
                pass

        stats["files"][filename] = file_info

    return stats
