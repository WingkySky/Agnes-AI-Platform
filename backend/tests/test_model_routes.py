# =====================================================
# 模型备用路由 CRUD 测试（M3）
# 鉴权三态（router 级 admin 依赖：401/403/200）、校验（锚点 404 / 渠道不存在 /
# 重复 400 / 目标类型不一致 400）、整表替换语义（含清空）
# =====================================================

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from tests.test_model_routing import _seed_def, _seed_provider, _seed_route


async def _build_client(memory_db, user=None):
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"} if user else {}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
    app.dependency_overrides.clear()


async def _seed_user(memory_db, username: str, role: str = "user", is_admin: bool = False):
    user = User(username=username, email=f"{username}@example.com",
                password_hash="x", role=role, is_admin=is_admin, credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_anon_routes_401(memory_db):
    await _seed_provider(memory_db, 1, "主渠道")
    await _seed_def(memory_db, "m1", 1)
    async for client in _build_client(memory_db):
        get_resp = await client.get("/api/models/m1/routes")
        put_resp = await client.put("/api/models/m1/routes", json={"routes": []})
    assert get_resp.status_code == 401
    assert put_resp.status_code == 401


@pytest.mark.asyncio
async def test_normal_user_routes_403(memory_db):
    user = await _seed_user(memory_db, username="u1", role="user")
    await _seed_provider(memory_db, 1, "主渠道")
    await _seed_def(memory_db, "m1", 1)
    async for client in _build_client(memory_db, user):
        get_resp = await client.get("/api/models/m1/routes")
        put_resp = await client.put("/api/models/m1/routes", json={"routes": []})
    assert get_resp.status_code == 403
    assert put_resp.status_code == 403


@pytest.mark.asyncio
async def test_save_and_list_routes_roundtrip(memory_db):
    admin = await _seed_user(memory_db, username="admin1", role="admin", is_admin=True)
    await _seed_provider(memory_db, 1, "主渠道")
    await _seed_provider(memory_db, 2, "备用渠道")
    await _seed_provider(memory_db, 3, "免费渠道", billing_tier="free")
    await _seed_def(memory_db, "m1", 1, type_="image")
    await _seed_def(memory_db, "m-b", 2, type_="image")
    await _seed_def(memory_db, "m-c", 3, type_="image")

    async for client in _build_client(memory_db, admin):
        resp = await client.put("/api/models/m1/routes", json={"routes": [
            {"provider_id": 3, "model_id": "m-c", "priority": 0, "is_enabled": True},
            {"provider_id": 2, "model_id": "m-b", "priority": 1, "is_enabled": False},
        ]})
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["anchor_model_id"] == "m1"
        assert body["anchor_type"] == "image"
        assert [i["model_id"] for i in body["items"]] == ["m-c", "m-b"]
        assert body["items"][0]["provider_name"] == "免费渠道"
        assert body["items"][0]["billing_tier"] == "free"
        assert body["items"][1]["is_enabled"] is False

        # 整表替换：只留一条
        resp2 = await client.put("/api/models/m1/routes", json={"routes": [
            {"provider_id": 2, "model_id": "m-b", "priority": 0},
        ]})
        assert resp2.status_code == 200
        assert [i["model_id"] for i in resp2.json()["data"]["items"]] == ["m-b"]

        # 清空
        resp3 = await client.put("/api/models/m1/routes", json={"routes": []})
        assert resp3.status_code == 200
        assert resp3.json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_routes_anchor_not_found_404(memory_db):
    admin = await _seed_user(memory_db, username="admin2", role="admin", is_admin=True)
    async for client in _build_client(memory_db, admin):
        resp = await client.get("/api/models/ghost/routes")
        assert resp.status_code == 404
        resp2 = await client.put("/api/models/ghost/routes", json={"routes": []})
        assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_routes_provider_missing_400(memory_db):
    admin = await _seed_user(memory_db, username="admin3", role="admin", is_admin=True)
    await _seed_provider(memory_db, 1, "主渠道")
    await _seed_def(memory_db, "m1", 1)
    async for client in _build_client(memory_db, admin):
        resp = await client.put("/api/models/m1/routes", json={"routes": [
            {"provider_id": 99, "model_id": "m-x", "priority": 0},
        ]})
        assert resp.status_code == 400
        assert "渠道 99 不存在" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_routes_duplicate_target_400(memory_db):
    admin = await _seed_user(memory_db, username="admin4", role="admin", is_admin=True)
    await _seed_provider(memory_db, 1, "主渠道")
    await _seed_provider(memory_db, 2, "备用渠道")
    await _seed_def(memory_db, "m1", 1)
    async for client in _build_client(memory_db, admin):
        resp = await client.put("/api/models/m1/routes", json={"routes": [
            {"provider_id": 2, "model_id": "m-b", "priority": 0},
            {"provider_id": 2, "model_id": "m-b", "priority": 1},
        ]})
        assert resp.status_code == 400
        assert "重复" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_routes_target_type_mismatch_400(memory_db):
    admin = await _seed_user(memory_db, username="admin5", role="admin", is_admin=True)
    await _seed_provider(memory_db, 1, "主渠道")
    await _seed_provider(memory_db, 2, "备用渠道")
    await _seed_def(memory_db, "m1", 1, type_="image")
    await _seed_def(memory_db, "v1", 2, type_="video")
    async for client in _build_client(memory_db, admin):
        resp = await client.put("/api/models/m1/routes", json={"routes": [
            {"provider_id": 2, "model_id": "v1", "priority": 0},
        ]})
        assert resp.status_code == 400
        assert "类型" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_routes_existing_rows_listed(memory_db):
    admin = await _seed_user(memory_db, username="admin6", role="admin", is_admin=True)
    await _seed_provider(memory_db, 1, "主渠道")
    await _seed_provider(memory_db, 2, "备用渠道")
    await _seed_def(memory_db, "m1", 1)
    await _seed_def(memory_db, "m-b", 2)
    await _seed_route(memory_db, "m1", 2, "m-b", priority=3)
    async for client in _build_client(memory_db, admin):
        resp = await client.get("/api/models/m1/routes")
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1 and items[0]["priority"] == 3
