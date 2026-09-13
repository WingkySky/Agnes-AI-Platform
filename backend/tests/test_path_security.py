# =====================================================
# 路径与 URL 安全加固测试
# - upload_service：MIME 缺失/非白名单拒绝、folder 穿越 400、正常保存
# - _resolve_local_media：/uploads/../ 越界返回 None
# - compose_videos：内网 / 非法协议素材地址 400
# - is_safe_url 基本判定
# =====================================================

import os

import pytest
from fastapi import HTTPException

from app.core.urlsafe import is_safe_url
from app.services import upload_service
from app.services.upload_service import save_upload_file, save_audio_bytes
from app.services.canvas_media_service import _resolve_local_media, compose_videos


class _FakeUpload:
    """模拟 Starlette UploadFile 的最小接口"""

    def __init__(self, content_type, filename, data=b"hello"):
        self.content_type = content_type
        self.filename = filename
        self._data = data

    async def read(self):
        return self._data


@pytest.fixture(autouse=True)
def _uploads_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_service, "UPLOADS_DIR", str(tmp_path))


@pytest.mark.asyncio
async def test_upload_rejects_missing_content_type():
    with pytest.raises(HTTPException) as exc:
        await save_upload_file(_FakeUpload(None, "a.png"))
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_disallowed_type():
    with pytest.raises(HTTPException) as exc:
        await save_upload_file(_FakeUpload("application/octet-stream", "a.bin"))
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_folder_traversal():
    with pytest.raises(HTTPException) as exc:
        await save_upload_file(
            _FakeUpload("image/png", "a.png"), folder="projects/../.."
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_saves_normally():
    url = await save_upload_file(
        _FakeUpload("image/png", "photo.PNG"), folder="projects/7/characters"
    )
    assert url.startswith("/uploads/projects/7/characters/")
    assert url.endswith(".png")


@pytest.mark.asyncio
async def test_save_audio_rejects_bad_ext():
    with pytest.raises(HTTPException):
        await save_audio_bytes(b"x", ext=".mp3/../evil")


@pytest.mark.asyncio
async def test_resolve_local_media_blocks_escape(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.canvas_media_service.UPLOADS_DIR", str(tmp_path))
    (tmp_path / "a.mp4").write_bytes(b"x")
    assert _resolve_local_media("/uploads/a.mp4") == os.path.realpath(str(tmp_path / "a.mp4"))
    assert _resolve_local_media("/uploads/../secret.env") is None


@pytest.mark.asyncio
async def test_compose_rejects_loopback_url():
    with pytest.raises(HTTPException):
        await compose_videos(video_urls=["http://127.0.0.1:6379/"])


@pytest.mark.asyncio
async def test_compose_rejects_bad_scheme():
    with pytest.raises(HTTPException):
        await compose_videos(video_urls=["ftp://cdn.example.com/v.mp4"])


def test_is_safe_url():
    assert is_safe_url("https://cdn.example.com/a.png")
    assert not is_safe_url("http://127.0.0.1/x")
    assert not is_safe_url("http://10.1.2.3/x")
    assert not is_safe_url("http://192.168.1.1/x")
    assert not is_safe_url("http://169.254.169.254/meta")
    assert not is_safe_url("file:///etc/passwd")
    assert not is_safe_url("http://localhost/x")
