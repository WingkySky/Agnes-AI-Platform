# =====================================================
# 画布素材上传端点测试（POST /api/uploads/canvas）
# - 鉴权三态 / 类型白名单 / 成功返回 URL / 文件真实落盘（UPLOADS_DIR 指向临时目录）
# =====================================================

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.services import upload_service


async def _build_client(memory_db, user=None):
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"} if user else {}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def owner_client(memory_db, seed_user):
    async for client in _build_client(memory_db, seed_user):
        yield client


@pytest_asyncio.fixture
async def anon_client(memory_db):
    async for client in _build_client(memory_db):
        yield client


@pytest.fixture(autouse=True)
def _tmp_uploads(tmp_path, monkeypatch):
    """上传目录指向临时目录，避免测试污染真实 uploads/"""
    monkeypatch.setattr(upload_service, "UPLOADS_DIR", str(tmp_path))


def _asset_dir(tmp_path) -> str:
    return os.path.join(str(tmp_path), "canvas", "assets")


@pytest.mark.asyncio
async def test_upload_requires_auth(memory_db, anon_client):
    resp = await anon_client.post("/api/uploads/canvas", files={"file": ("a.png", b"x", "image/png")})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_upload_rejects_bad_type(owner_client):
    resp = await owner_client.post("/api/uploads/canvas", files={"file": ("a.txt", b"x", "text/plain")})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_image_ok(owner_client, tmp_path):
    resp = await owner_client.post("/api/uploads/canvas", files={"file": ("a.png", b"pngbytes", "image/png")})
    assert resp.status_code == 200
    url = resp.json()["data"]["url"]
    assert url.startswith("/uploads/canvas/assets/") and url.endswith(".png")
    filename = url.rsplit("/", 1)[-1]
    assert os.path.exists(os.path.join(_asset_dir(tmp_path), filename))


@pytest.mark.asyncio
async def test_upload_video_ok(owner_client, tmp_path):
    resp = await owner_client.post("/api/uploads/canvas", files={"file": ("a.mp4", b"mp4", "video/mp4")})
    assert resp.status_code == 200
    assert resp.json()["data"]["url"].endswith(".mp4")


@pytest.mark.asyncio
async def test_upload_rejects_oversize(owner_client, monkeypatch):
    # MAX_FILE_BYTES 是 save_upload_file 的默认参数（定义时绑定），改模块属性无效；
    # 用 partial 覆盖路由引用并显式收紧 max_size
    import functools
    from app.routes import uploads as uploads_route

    monkeypatch.setattr(
        uploads_route, "save_upload_file",
        functools.partial(upload_service.save_upload_file, max_size=8))
    resp = await owner_client.post("/api/uploads/canvas", files={"file": ("a.png", b"x" * 100, "image/png")})
    assert resp.status_code == 400
