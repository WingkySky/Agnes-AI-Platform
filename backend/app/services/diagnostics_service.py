# =====================================================
# 诊断包服务（可靠性三件套 ③）—— 管理员一键导出脱敏诊断 ZIP
#
# 九项内容：meta / 脱敏配置 / 三份日志尾部 / 最近生成（任务账本口径）/
# 最近上游调用 / 存储摘要 / 表统计。全部脱敏 + 行数封顶：
#   - secret 类（键名含 password/secret/token/key）整值打码 ***<len>
#   - prompt 截 200 字、错误文案截 300~500 字
#   - 用户身份内容不入包（无用户名/邮箱；top_users 仅 user_id）
# 服务函数统一接收 db（路由注入），测试可直接用内存库。
# =====================================================

import io
import json
import logging
import os
import platform
import sys
import time
import zipfile
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.api_call_log import ApiCallLog
from app.models.asset import Asset
from app.models.chat import ChatMessage, ChatSession
from app.models.credit_transaction import CreditTransaction
from app.models.generation import Generation
from app.models.storage_object import StorageObject
from app.models.user import User
from app.services.storage_quota import admin_overview

logger = logging.getLogger("agnes_platform")

LOG_PREFIX = "[诊断包]"

# 行数 / 字数封顶
TAIL_LOG_LINES = 2000
TAIL_FRONTEND_LINES = 1000
TAIL_ERRORS_LINES = 500
RECENT_GENERATIONS = 100
RECENT_API_CALLS = 100
PROMPT_MAX = 200
ERROR_MAX = 500

# .env / 环境清单
SECRET_KEY_TOKENS = ("password", "secret", "token", "key")

_ZIP_COMMENT = "Agnes AI Platform diagnostics bundle (sanitized)"


def _mask_value(value: str) -> str:
    return f"***<len={len(value)}>"


def sanitize_pair(key: str, value: str) -> str:
    """键名含敏感词（password/secret/token/key）→ 值整段打码"""
    lowered = (key or "").lower()
    if any(t in lowered for t in SECRET_KEY_TOKENS):
        return _mask_value(value or "")
    return value


def _truncate(text: Optional[str], limit: int) -> Optional[str]:
    if not text:
        return text
    return text[:limit] + ("…" if len(text) > limit else "")


def _tail_lines(path: str, max_lines: int) -> str:
    """从文件尾向前找 max_lines 个换行（避免整读大日志），缺失/异常返回空串"""
    if not os.path.isfile(path):
        return ""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            chunk = min(size, 1024 * 1024)
            f.seek(size - chunk)
            data = f.read()
        lines = data.decode("utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception as e:
        logger.warning("%s 读取日志尾部失败: %s error=%s", LOG_PREFIX, path, e)
        return ""


def _env_keys() -> List[str]:
    """.env 只列键名不列值；文件缺失返回空"""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    if not os.path.isfile(path):
        return []
    try:
        keys = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    keys.append(line.split("=", 1)[0].strip())
        return keys
    except Exception as e:
        logger.warning("%s 读取 .env 键名失败: %s", LOG_PREFIX, e)
        return []


def _engine_label() -> str:
    url = settings.database_url or ""
    if url.startswith("sqlite"):
        return f"sqlite ({os.path.basename(url.split('///')[-1]) or 'memory'})"
    return url.split(":")[0] or "unknown"


def _version_label() -> str:
    """优先读仓库根 VERSION 文件，缺失回落 dev"""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "VERSION")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip() or "dev"
    except Exception:
        return "dev"


def _meta_text(started_at: float) -> str:
    now = datetime.now(timezone.utc)
    lines = [
        f"exported_at_utc: {now.isoformat()}",
        f"version: {_version_label()}",
        f"python: {sys.version.split()[0]}",
        f"os: {platform.platform()}",
        f"process_uptime_sec: {int(time.time() - started_at)}",
        f"database: {_engine_label()}",
        f"backend_cwd: {os.getcwd()}",
    ]
    return "\n".join(lines) + "\n"


async def _generations_recent(db: AsyncSession, limit: int) -> List[dict]:
    rows = (
        await db.scalars(
            select(Generation).order_by(Generation.id.desc()).limit(limit)
        )
    ).all()
    return [
        {
            "id": r.id,
            "type": r.type,
            "status": r.status,
            "model": r.model,
            "mode": r.mode,
            "task_id": r.task_id,
            "video_id": r.video_id,
            "user_id": r.user_id,
            "prompt": _truncate(r.prompt, PROMPT_MAX),
            "error_category": r.error_category,
            "error_message": _truncate(r.error_message, ERROR_MAX),
            "credits_consumed": r.credits_consumed,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def _api_calls_recent(db: AsyncSession, limit: int) -> List[dict]:
    rows = (
        await db.scalars(
            select(ApiCallLog).order_by(ApiCallLog.id.desc()).limit(limit)
        )
    ).all()
    return [
        {
            "id": r.id,
            "provider_name": r.provider_name,
            "model": r.model,
            "call_type": r.call_type,
            "status": r.status,
            "error_category": r.error_category,
            "error_message": _truncate(r.error_message, 300),
            "request_id": r.request_id,
            "latency_ms": r.latency_ms,
            "tokens_in": r.tokens_in,
            "tokens_out": r.tokens_out,
            "estimated_credits": r.estimated_credits,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def _config_sanitized(db: AsyncSession) -> dict:
    from app.models.system_config import SystemConfig
    from app.models.api_provider import ApiProvider

    configs = (await db.scalars(select(SystemConfig).order_by(SystemConfig.config_key))).all()
    providers = (await db.scalars(select(ApiProvider).order_by(ApiProvider.id))).all()
    return {
        "system_configs": {
            c.config_key: sanitize_pair(c.config_key, c.config_value or "")
            for c in configs
        },
        "env_keys": _env_keys(),
        "providers": [
            {
                "id": p.id,
                "name": p.name,
                "provider_type": p.provider_type,
                "base_url": p.base_url,
                "is_active": p.is_active,
                "is_default": p.is_default,
                "api_key_configured": bool(p.api_key_encrypted),
            }
            for p in providers
        ],
    }


async def _table_stats(db: AsyncSession) -> dict:
    out = {}
    for label, model in (
        ("users", User),
        ("generations", Generation),
        ("assets", Asset),
        ("storage_objects", StorageObject),
        ("chat_sessions", ChatSession),
        ("chat_messages", ChatMessage),
        ("api_call_logs", ApiCallLog),
        ("credit_transactions", CreditTransaction),
    ):
        out[label] = int((await db.scalars(select(func.count(model.id)))).one())
    return out


async def build_diagnostics_zip(db: AsyncSession, started_at: Optional[float] = None) -> bytes:
    """组装诊断 ZIP（内存）；started_at 缺省用模块加载时间近似进程启动"""
    started = started_at if started_at is not None else _MODULE_LOAD_TIME
    log_dir = settings.log_dir

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.comment = _ZIP_COMMENT.encode()
        zf.writestr("meta.txt", _meta_text(started))
        zf.writestr(
            "config_sanitized.json",
            json.dumps(await _config_sanitized(db), ensure_ascii=False, indent=2),
        )
        zf.writestr("logs/backend.tail.log", _tail_lines(os.path.join(log_dir, "agnes_platform.log"), TAIL_LOG_LINES))
        zf.writestr("logs/frontend.tail.jsonl", _tail_lines(os.path.join(log_dir, "frontend.jsonl"), TAIL_FRONTEND_LINES))
        zf.writestr("logs/errors.tail.jsonl", _tail_lines(os.path.join(log_dir, "errors.jsonl"), TAIL_ERRORS_LINES))
        zf.writestr("generations_recent.json", json.dumps(await _generations_recent(db, RECENT_GENERATIONS), ensure_ascii=False, indent=2))
        zf.writestr("api_calls_recent.json", json.dumps(await _api_calls_recent(db, RECENT_API_CALLS), ensure_ascii=False, indent=2))
        zf.writestr("storage_summary.json", json.dumps(await admin_overview(limit=10), ensure_ascii=False, indent=2))
        zf.writestr("table_stats.json", json.dumps(await _table_stats(db), ensure_ascii=False, indent=2))

    logger.info("%s 诊断包已生成: %d bytes", LOG_PREFIX, buf.getbuffer().nbytes)
    return buf.getvalue()


def diagnostics_filename() -> str:
    return f"agnes-diagnostics-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.zip"


_MODULE_LOAD_TIME = time.time()
