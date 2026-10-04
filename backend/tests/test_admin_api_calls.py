# =====================================================
# 上游调用记账管理端点测试（/api/admin/api-calls）
# 401/403/200 三态锁死（admin 铁律）+ 列表筛选 + 聚合摘要结构
# =====================================================

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.main import app
from app.core.security import create_access_token
from app.models.api_call_log import ApiCallLog
from app.models.user import User

pytestmark = pytest.mark.asyncio

LIST_URL = "/api/admin/api-calls"
SUMMARY_URL = "/api/admin/api-calls/summary"


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


async def _seed_call(memory_db, **kwargs):
    memory_db.add(ApiCallLog(**kwargs))
    await memory_db.commit()


async def test_anon_401(memory_db):
    async for client in _build_client(memory_db):
        assert (await client.get(LIST_URL)).status_code == 401
        assert (await client.get(SUMMARY_URL)).status_code == 401


async def test_normal_user_403(memory_db):
    user = await _seed_user(memory_db, "u1", role="user")
    async for client in _build_client(memory_db, user):
        assert (await client.get(LIST_URL)).status_code == 403
        assert (await client.get(SUMMARY_URL)).status_code == 403


async def test_admin_list_and_summary_200(memory_db):
    admin = await _seed_user(memory_db, "root", role="admin", is_admin=True)
    await _seed_call(
        memory_db,
        provider_name="Agnes", provider_id=1, model="agnes-image-2.1-flash",
        call_type="image_create", endpoint="/v1/images/generations",
        status="success", latency_ms=1200,
    )
    await _seed_call(
        memory_db,
        provider_name="Agnes", provider_id=1, model="agnes-image-2.1-flash",
        call_type="image_create", endpoint="/v1/images/generations",
        status="failed", error_category="rate_limited", error_message="太快了",
        latency_ms=300,
    )
    async for client in _build_client(memory_db, admin):
        resp = await client.get(LIST_URL, params={"status": "failed"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["data"]["total"] == 1
        assert body["data"]["calls"][0]["error_category"] == "rate_limited"

        resp = await client.get(SUMMARY_URL, params={"days": 7})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2
        assert data["failed"] == 1
        assert {"category": "rate_limited", "count": 1} in data["by_category"]
        assert data["by_provider"]["Agnes"]["success"] == 1
        assert data["by_provider"]["Agnes"]["failed"] == 1
        assert data["by_model"]["agnes-image-2.1-flash"]["success"] == 1
        assert data["by_model"]["agnes-image-2.1-flash"]["failed"] == 1
