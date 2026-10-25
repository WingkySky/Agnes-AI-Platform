# =====================================================
# 存储配额服务 —— 用户级本地存储记账与限额（可靠性三件套 ②）
#
# 台账 = storage_objects 表（只增不删，storage_key 唯一幂等）。
# 语义：
#   - 用户主动上传：先 check_upload_quota 预检（总配额 + 滚动 24h 上传量），
#     落盘成功后 record_file 记账；预检不预占行，单实例并发同检的少量超卖可接受。
#   - 生成归档/渲染输出：软处理——超限仅告警跳过记账，不阻断主流程（积分已扣）。
#   - S3 转存件不落台账（不占本地磁盘）。
# =====================================================

import logging
import os
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.database import new_async_session
from app.core.pathsafe import ensure_within
from app.models.storage_object import StorageObject
from app.services.system_config_service import get_config_value
from app.services.upload_service import UPLOADS_DIR

logger = logging.getLogger("agnes_platform")

LOG_PREFIX = "[存储配额]"

# 台账记账的来源
SOURCE_UPLOAD = "upload"
SOURCE_GENERATION = "generation"
SOURCE_RENDER = "render"

_EXT_KIND = {
    "jpg": "image", "jpeg": "image", "png": "image", "webp": "image", "gif": "image",
    "mp4": "video", "mov": "video", "webm": "video",
    "mp3": "audio", "wav": "audio",
}


def _kind_of(storage_key: str) -> str:
    ext = storage_key.rsplit(".", 1)[-1].lower() if "." in storage_key else ""
    return _EXT_KIND.get(ext, "file")


def _local_abs_path(storage_key: str) -> str | None:
    """台账 key → 本地绝对路径；文件不存在（S3 件/已被清理）返回 None"""
    try:
        path = ensure_within(UPLOADS_DIR, storage_key)
    except ValueError:
        return None
    return path if os.path.isfile(path) else None


def _parse_mb(value: str) -> int:
    try:
        return max(0, int(str(value).strip() or "0"))
    except (TypeError, ValueError):
        return 0


async def get_quota_limits(db) -> tuple[int | None, int | None]:
    """读取配额上限（字节）；None = 不限制（配置 0 或空）"""
    total_mb = _parse_mb(await get_config_value(db, "storage_quota_mb", "5120"))
    daily_mb = _parse_mb(await get_config_value(db, "daily_upload_quota_mb", "2048"))
    return (total_mb * 1024 * 1024 or None, daily_mb * 1024 * 1024 or None)


async def check_upload_quota(user_id: int, incoming_bytes: int) -> None:
    """
    用户主动上传前的两阶段预检（总量 + 滚动 24h 上传量）。超限抛 HTTPException 413。

    自建 session：预检与请求级 db 事务解耦，独立读账即可。
    """
    async with new_async_session() as db:
        total_limit, daily_limit = await get_quota_limits(db)

        total_used = (
            await db.scalars(
                select(func.coalesce(func.sum(StorageObject.bytes), 0)).where(
                    StorageObject.user_id == user_id
                )
            )
        ).one()
        if total_limit is not None and total_used + incoming_bytes > total_limit:
            raise HTTPException(
                status_code=413,
                detail=f"存储空间已满（{total_used // 1024 // 1024}/{total_limit // 1024 // 1024}MB），请清理资产后重试",
            )

        if daily_limit is not None:
            # 滚动 24h 窗口；created_at 为 naive UTC（utcnow 惯例），直接做差勿用 .timestamp()
            since = datetime.utcnow() - timedelta(hours=24)
            daily_used = (
                await db.scalars(
                    select(func.coalesce(func.sum(StorageObject.bytes), 0)).where(
                        StorageObject.user_id == user_id,
                        StorageObject.source == SOURCE_UPLOAD,
                        StorageObject.created_at >= since,
                    )
                )
            ).one()
            if daily_used + incoming_bytes > daily_limit:
                raise HTTPException(
                    status_code=413,
                    detail=f"已达到滚动 24 小时上传上限（{daily_limit // 1024 // 1024}MB），请明日再试",
                )


async def record_file(
    *,
    user_id: int | None,
    storage_key: str,
    source: str,
    kind: str | None = None,
    bytes_size: int | None = None,
    log_prefix: str = LOG_PREFIX,
) -> None:
    """
    落盘成功后记账（幂等：storage_key 已存在跳过）。best-effort：失败仅告警。

    bytes_size 缺省时从本地文件 os.stat 取；本地文件不存在（S3 件）直接跳过。
    """
    if not user_id or not storage_key:
        return
    try:
        size = bytes_size
        if size is None:
            path = _local_abs_path(storage_key)
            if path is None:
                return  # S3 件或文件已被清理，不落台账
            size = os.path.getsize(path)
        async with new_async_session() as db:
            exists = (
                await db.scalars(
                    select(StorageObject.id).where(StorageObject.storage_key == storage_key).limit(1)
                )
            ).first()
            if exists:
                return
            db.add(StorageObject(
                user_id=user_id,
                storage_key=storage_key,
                bytes=int(size),
                kind=kind or _kind_of(storage_key),
                source=source,
            ))
            await db.commit()
        logger.info("%s 已记账: user=%s key=%s bytes=%s source=%s", log_prefix, user_id, storage_key, size, source)
    except Exception as e:
        logger.warning("%s 记账失败（不影响主流程）: key=%s error=%s", log_prefix, storage_key, e)


async def usage_for(user_id: int) -> dict:
    """用户自查用量：总 used/quota + 滚动 24h 上传/上限（None = 不限制）"""
    async with new_async_session() as db:
        total_limit, daily_limit = await get_quota_limits(db)
        total_used = (
            await db.scalars(
                select(func.coalesce(func.sum(StorageObject.bytes), 0)).where(
                    StorageObject.user_id == user_id
                )
            )
        ).one()
        since = datetime.utcnow() - timedelta(hours=24)
        daily_used = (
            await db.scalars(
                select(func.coalesce(func.sum(StorageObject.bytes), 0)).where(
                    StorageObject.user_id == user_id,
                    StorageObject.source == SOURCE_UPLOAD,
                    StorageObject.created_at >= since,
                )
            )
        ).one()
    return {
        "total_used": int(total_used),
        "total_quota": total_limit,
        "daily_used": int(daily_used),
        "daily_quota": daily_limit,
    }


async def admin_overview(limit: int = 10) -> dict:
    """管理员概览：平台总量 + 用量 top N 用户（台账行级别 Python 聚合，概览低频可承受）"""
    async with new_async_session() as db:
        total_used = (
            await db.scalars(select(func.coalesce(func.sum(StorageObject.bytes), 0)))
        ).one()
        total_limit, _ = await get_quota_limits(db)
        rows = (await db.scalars(select(StorageObject))).all()

    per_user: dict[int, dict] = {}
    for r in rows:
        if r.user_id is None:
            continue
        agg = per_user.setdefault(r.user_id, {"used": 0, "files": 0})
        agg["used"] += r.bytes or 0
        agg["files"] += 1
    top = sorted(per_user.items(), key=lambda kv: kv[1]["used"], reverse=True)[:limit]
    return {
        "total_used": int(total_used),
        "default_quota": total_limit,
        "top_users": [
            {"user_id": uid, "used": agg["used"], "files": agg["files"]}
            for uid, agg in top
        ],
    }


async def ensure_storage_ledger(db) -> int:
    """
    存量回填（幂等）：按 assets.storage_key 补台账行（本地文件存在才计）。
    挂 lifespan ensure 链路；canvas 历史孤儿文件无法归属，不回填。
    """
    from app.models.asset import Asset

    added = 0
    known = set(
        (await db.scalars(select(StorageObject.storage_key))).all()
    )
    assets = (
        await db.scalars(
            select(Asset).where(Asset.storage_key.isnot(None)).order_by(Asset.id)
        )
    ).all()
    for asset in assets:
        key = asset.storage_key
        if not key or key in known:
            continue
        path = _local_abs_path(key)
        if path is None:
            continue  # S3 件或文件已不在本地
        db.add(StorageObject(
            user_id=asset.user_id,
            storage_key=key,
            bytes=os.path.getsize(path),
            kind=_kind_of(key),
            source=SOURCE_GENERATION,
        ))
        known.add(key)
        added += 1
    if added:
        await db.commit()
        logger.info("%s 存量回填完成: %d 个文件入账", LOG_PREFIX, added)
    return added
