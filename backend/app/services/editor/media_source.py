# =====================================================
# 素材本地化工具（剪辑器域共享：字幕转写 / 渲染取材）
#
# asset（assets 行）→ 本地文件路径：
#   1. /uploads/ 本地地址（或 storage_key）直读磁盘
#   2. 远程 http(s) 经 media_storage.ingest_url 收口（SSRF 校验 + 永久转存，
#      回写 storage_key 后续渲染/转写零重复下载）
# =====================================================

import logging
from pathlib import Path
from typing import Optional

from app.services.media_storage import ingest_url
from app.services.upload_service import UPLOADS_DIR

logger = logging.getLogger("agnes_platform.editor.media_source")


def uploads_local_path(asset_url: Optional[str], storage_key: Optional[str]) -> Optional[Path]:
    """/uploads/ 地址或 storage_key → 磁盘绝对路径（文件存在才返回）"""
    rel = storage_key or (
        asset_url.removeprefix("/uploads/") if asset_url and asset_url.startswith("/uploads/") else None
    )
    if not rel:
        return None
    path = Path(UPLOADS_DIR) / rel
    return path if path.is_file() else None


async def resolve_asset_local_file(asset, tmp_dir: str) -> Optional[str]:
    """资产 → 本地文件路径；本地缺失时远程收口转存（SSRF 校验失败/不可达返回 None）"""
    local = uploads_local_path(asset.asset_url, asset.storage_key)
    if local:
        return str(local)
    if asset.asset_url and asset.asset_url.startswith(("http://", "https://")):
        try:
            ingested = await ingest_url(asset.asset_url, media_type=asset.kind or "image")
            asset.asset_url = ingested["url"]
            asset.storage_key = ingested["storage_key"]
            remade = uploads_local_path(asset.asset_url, asset.storage_key)
            return str(remade) if remade else None
        except Exception as e:  # noqa: BLE001 — 单文件收口失败由调用方决定跳过或报错
            logger.warning("[剪辑器] 素材收口失败 url=%s error=%s", asset.asset_url, e)
            return None
    return None
