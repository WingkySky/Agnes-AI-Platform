# =====================================================
# 统一资产端点测试（/api/assets）
# POST 素材入库（/uploads 直推导 / 远程地址收口 / 挂靠归属校验）
# GET 列表筛选（media_type/source/work_id/keyword）+ 401/403/200 三态
# =====================================================

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.models.work import Work

pytestmark = pytest.mark.asyncio

ASSETS_URL = "/api/assets"


async def _build_client(memory_db, user=None):
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"} if user else {}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
    app.dependency_overrides.clear()


async def _seed_user(memory_db, username: str) -> User:
    user = User(username=username, email=f"{username}@example.com",
                password_hash="x", role="user", is_admin=False, credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    return user


async def test_anon_401(memory_db):
    async for client in _build_client(memory_db):
        assert (await client.get(ASSETS_URL)).status_code == 401
        assert (await client.post(ASSETS_URL, json={"url": "/uploads/x.png", "media_type": "image"})).status_code == 401


async def test_create_and_list_200(memory_db):
    user = await _seed_user(memory_db, "u1")
    work = Work(user_id=user.id, title="我的剧")
    memory_db.add(work)
    await memory_db.commit()
    await memory_db.refresh(work)

    async for client in _build_client(memory_db, user):
        # /uploads/ 地址直推导 storage_key
        resp = await client.post(ASSETS_URL, json={
            "url": "/uploads/canvas/a.png", "media_type": "image", "name": "画布素材", "work_id": work.id,
        })
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["storage_key"] == "canvas/a.png"
        assert body["source"] == "upload"
        assert body["work_id"] == work.id
        assert body["media_type"] == "image"

        # 列表筛选
        resp = await client.get(ASSETS_URL, params={"media_type": "image"})
        assert resp.json()["data"]["total"] == 1
        resp = await client.get(ASSETS_URL, params={"work_id": work.id})
        assert resp.json()["data"]["total"] == 1
        resp = await client.get(ASSETS_URL, params={"keyword": "画布"})
        assert resp.json()["data"]["total"] == 1
        resp = await client.get(ASSETS_URL, params={"media_type": "video"})
        assert resp.json()["data"]["total"] == 0


async def test_create_forbidden_and_invalid(memory_db):
    user = await _seed_user(memory_db, "u1")
    other = await _seed_user(memory_db, "u2")
    foreign_work = Work(user_id=other.id, title="别人的")
    memory_db.add(foreign_work)
    await memory_db.commit()
    await memory_db.refresh(foreign_work)

    async for client in _build_client(memory_db, user):
        # 挂靠他人作品 403
        resp = await client.post(ASSETS_URL, json={
            "url": "/uploads/x.png", "media_type": "image", "work_id": foreign_work.id,
        })
        assert resp.status_code == 403
        # 非法媒体类型 400
        resp = await client.post(ASSETS_URL, json={"url": "/uploads/x.png", "media_type": "pdf"})
        assert resp.status_code == 400
        # 非法协议地址 400（SSRF 防护）
        resp = await client.post(ASSETS_URL, json={"url": "http://127.0.0.1/x.png", "media_type": "image"})
        assert resp.status_code == 400
