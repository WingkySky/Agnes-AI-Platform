# =====================================================
# Provider/模型管理路由鉴权测试
# 整路由挂 get_current_admin_user（router 级依赖）：
#   - 未登录 401 / 普通用户 403 / admin 200
#   - 写端点同样被 router 级依赖拦截
# =====================================================

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.services.provider_registry import provider_registry


async def _fake_list_providers(include_key: bool = False):
    return []


@pytest.fixture(autouse=True)
def _fake_registry(monkeypatch):
    """registry 自建 session（不走注入的 get_async_db），测试里打桩隔离"""
    monkeypatch.setattr(provider_registry, "list_providers", _fake_list_providers)


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
async def test_anon_get_providers_401(memory_db):
    async for client in _build_client(memory_db):
        resp = await client.get("/api/providers")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_normal_user_403_on_read_and_write(memory_db):
    user = await _seed_user(memory_db, username="u1", role="user")
    async for client in _build_client(memory_db, user):
        read = await client.get("/api/providers")
        write = await client.post("/api/models/batch-delete", json={"ids": ["m1"]})
    assert read.status_code == 403
    assert write.status_code == 403


@pytest.mark.asyncio
async def test_batch_cost_multiplier_auth_gates(memory_db):
    body = {"model_ids": ["m1"], "cost_multiplier": 2.0}
    async for client in _build_client(memory_db):
        anon = await client.put("/api/models/batch-cost-multiplier", json=body)
    user = await _seed_user(memory_db, username="u1", role="user")
    async for client in _build_client(memory_db, user):
        forbidden = await client.put("/api/models/batch-cost-multiplier", json=body)
    assert anon.status_code == 401
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_admin_batch_cost_multiplier_200(memory_db, monkeypatch):
    admin = await _seed_user(memory_db, username="root", role="admin", is_admin=True)
    seen: dict = {}

    async def _fake_batch(model_ids, cost_multiplier):
        seen["ids"] = list(model_ids)
        seen["multiplier"] = cost_multiplier
        return len(model_ids)

    monkeypatch.setattr(provider_registry, "batch_update_cost_multiplier", _fake_batch)
    async for client in _build_client(memory_db, admin):
        resp = await client.put(
            "/api/models/batch-cost-multiplier",
            json={"model_ids": ["m1", "m2"], "cost_multiplier": 2.5},
        )
        low = await client.put(
            "/api/models/batch-cost-multiplier",
            json={"model_ids": ["m1"], "cost_multiplier": 0.05},
        )
        empty = await client.put(
            "/api/models/batch-cost-multiplier",
            json={"model_ids": [], "cost_multiplier": 2.0},
        )
    assert resp.status_code == 200
    assert resp.json()["data"]["updated"] == 2
    assert seen["ids"] == ["m1", "m2"]
    assert seen["multiplier"] == 2.5
    assert low.status_code == 400  # 倍率低于下限 0.1（校验错误全局统一 400）
    assert empty.status_code == 400


@pytest.mark.asyncio
async def test_admin_get_providers_200(memory_db):
    admin = await _seed_user(memory_db, username="root", role="admin", is_admin=True)
    async for client in _build_client(memory_db, admin):
        resp = await client.get("/api/providers")
    assert resp.status_code == 200
    assert resp.json()["data"]["items"] == []
