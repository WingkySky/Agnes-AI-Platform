# =====================================================
# 统一媒体存储收口层测试（本地收口 / uploads 直映射 / SSRF 拒绝）
# =====================================================

import pytest

from app.services import media_storage

pytestmark = pytest.mark.asyncio


async def test_save_media_local(tmp_path, monkeypatch):
    """S3 未配置时本地落盘：url 前缀 /uploads/，storage_key 为相对路径且文件可读回"""
    monkeypatch.setattr(media_storage, "UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(media_storage.asset_storage, "get_storage_backend", lambda: None)

    result = await media_storage.save_media(b"hello", ext="png", folder="test-assets", media_type="image")

    assert result["url"].startswith("/uploads/test-assets/")
    assert result["storage_key"].startswith("test-assets/")
    assert (tmp_path / result["storage_key"]).read_bytes() == b"hello"


async def test_ingest_uploads_passthrough():
    """/uploads/ 本地地址直接推导 storage_key，不下载不转存"""
    result = await media_storage.ingest_url("/uploads/canvas/a.png")
    assert result == {"url": "/uploads/canvas/a.png", "storage_key": "canvas/a.png"}


async def test_ingest_rejects_unsafe_url():
    """SSRF 防护：环回/私有地址与非 http(s) 协议一律拒绝"""
    for bad in ("http://127.0.0.1:8000/secret", "http://192.168.1.10/x.png", "ftp://example.com/x.png"):
        with pytest.raises(ValueError):
            await media_storage.ingest_url(bad)
