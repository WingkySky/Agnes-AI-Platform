# =====================================================
# 统一媒体存储收口层（子批次 2a）
#
# 所有新媒体文件落盘/转存统一走这里，返回 {url, storage_key}：
#   - S3 后端已配置：key = assets/{media_type}/{yyyy-mm}/{uid}{ext}，url = 公共 URL
#   - 本地后端：uploads/{folder}/{yyyy-mm}/{uid}{ext}，storage_key = uploads 相对路径
# assets.storage_key 由调用方写入；/uploads/ 本地地址入库时直接推导 key 不重复转存。
# =====================================================

import io
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.core.urlsafe import is_safe_url
from app.services import asset_storage
from app.services.upload_service import UPLOADS_DIR

logger = logging.getLogger("agnes_platform.media_storage")

_DEFAULT_EXT = {"image": "png", "video": "mp4", "audio": "mp3"}


def _new_name(ext: str) -> str:
    ext = (ext or "").lower().lstrip(".")
    return f"{uuid.uuid4().hex}.{ext or 'bin'}"


def _infer_ext(url: str, content_type: Optional[str], media_type: str) -> str:
    """URL 路径后缀优先，其次 Content-Type，最后按媒体类型兜底"""
    if url:
        suffix = Path(urlparse(url).path).suffix.lower().lstrip(".")
        if suffix and suffix.isalpha() and len(suffix) <= 5:
            return suffix
    ct = (content_type or "").lower()
    for token, ext in (("png", "png"), ("jpeg", "jpg"), ("webp", "webp"), ("gif", "gif"),
                       ("mp4", "mp4"), ("webm", "webm"), ("mpeg", "mp3"), ("mp3", "mp3"), ("wav", "wav")):
        if token in ct:
            return ext
    return _DEFAULT_EXT.get(media_type, "bin")


def _local_save(data: bytes, folder: str, ext: str) -> tuple[str, str]:
    """本地落盘 uploads/{folder}/{yyyy-mm}/，返回 (url, storage_key=相对路径)"""
    rel_dir = os.path.join(folder, datetime.utcnow().strftime("%Y-%m"))
    abs_dir = os.path.join(UPLOADS_DIR, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    name = _new_name(ext)
    Path(os.path.join(abs_dir, name)).write_bytes(data)
    rel_key = os.path.join(rel_dir, name).replace("\\", "/")
    return f"/uploads/{rel_key}", rel_key


async def save_media(
    data: bytes, *, ext: str = "", folder: str = "assets", media_type: str = "image",
) -> dict:
    """
    统一媒体写入收口。返回 {url, storage_key}。

    - S3 后端已配置：key = assets/{media_type}/{yyyy-mm}/{uid}{ext}
    - 否则本地 uploads 落盘（folder 为业务前缀，如 canvas/assets）
    """
    ext = (ext or "").lower().lstrip(".")
    backend = asset_storage.get_storage_backend()
    if backend is not None:
        key = f"assets/{media_type}/{datetime.utcnow().strftime('%Y-%m')}/{_new_name(ext)}"
        url = await backend.upload_fileobj(io.BytesIO(data), key)
        return {"url": url, "storage_key": key}
    url, key = _local_save(data, folder, ext)
    return {"url": url, "storage_key": key}


async def ingest_url(
    url: str, *, folder: str = "assets", media_type: str = "image",
) -> dict:
    """
    远程/本地上游 URL → 统一收口（根治 assets 表存上游临时死链）。

    - /uploads/ 本地地址：直接推导 storage_key，不下载不转存
    - 远程地址：SSRF 校验（仅公网 http/https）后下载走 save_media
    """
    if url.startswith("/uploads/"):
        return {"url": url, "storage_key": url.removeprefix("/uploads/")}
    if not is_safe_url(url):
        raise ValueError(f"不允许的素材地址：{url[:80]}")
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.content
    ext = _infer_ext(url, resp.headers.get("content-type"), media_type)
    result = await save_media(data, ext=ext, folder=folder, media_type=media_type)
    logger.info("[media_storage] 上游地址已收口: media_type=%s bytes=%s key=%s", media_type, len(data), result["storage_key"])
    return result
