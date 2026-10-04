# =====================================================
# 作品（轻容器）端点测试（/api/works）
# 401 未登录 / 200 本人 / 403 非本人；画布挂靠作品归属校验
# =====================================================

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.models.work import Work

pytestmark = pytest.mark.asyncio

WORKS_URL = "/api/works"
WS_URL = "/api/canvas/workspaces"


async def _build_client(memory_db, user=None):
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"} if user else {}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
    app.dependency_overrides.clear()


async def _seed_user(memory_db, username: str):
    user = User(username=username, email=f"{username}@example.com",
                password_hash="x", role="user", is_admin=False, credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    return user


async def test_anon_401(memory_db):
    async for client in _build_client(memory_db):
        assert (await client.get(WORKS_URL)).status_code == 401
        assert (await client.post(WORKS_URL, json={"title": "x"})).status_code == 401


async def test_work_crud_and_canvas_binding_200(memory_db):
    user = await _seed_user(memory_db, "u1")
    async for client in _build_client(memory_db, user):
        resp = await client.post(WORKS_URL, json={"title": "我的短剧", "description": "第一季"})
        assert resp.status_code == 200
        work_id = resp.json()["data"]["id"]

        resp = await client.get(WORKS_URL)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 1

        resp = await client.patch(f"{WORKS_URL}/{work_id}", json={"title": "改名"})
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "改名"

        # 画布挂靠自己的作品 + 按作品筛选列表
        resp = await client.post(WS_URL, json={"name": "第1集", "work_id": work_id})
        assert resp.status_code == 200
        assert resp.json()["data"]["work_id"] == work_id
        resp = await client.get(WS_URL, params={"work_id": work_id})
        assert resp.status_code == 200
        assert [w["name"] for w in resp.json()["data"]] == ["第1集"]

        # 删除作品：画布解绑为自由画布
        assert (await client.delete(f"{WORKS_URL}/{work_id}")).status_code == 200
        assert (await client.get(WORKS_URL)).json()["data"]["total"] == 0
        resp = await client.get(WS_URL, params={"work_id": work_id})
        assert resp.json()["data"] == []
        resp = await client.get(WS_URL)
        assert [w["name"] for w in resp.json()["data"]] == ["第1集"]
        assert resp.json()["data"][0]["work_id"] is None


async def test_other_user_403(memory_db):
    owner = await _seed_user(memory_db, "owner")
    other = await _seed_user(memory_db, "other")
    work = Work(user_id=owner.id, title="别人的剧")
    memory_db.add(work)
    await memory_db.commit()
    await memory_db.refresh(work)

    async for client in _build_client(memory_db, other):
        assert (await client.get(f"{WORKS_URL}/{work.id}")).status_code == 403
        assert (await client.patch(f"{WORKS_URL}/{work.id}", json={"title": "hack"})).status_code == 403
        assert (await client.delete(f"{WORKS_URL}/{work.id}")).status_code == 403
        # 画布挂靠他人作品 / 不存在的作品：统一 403
        resp = await client.post(WS_URL, json={"name": "x", "work_id": work.id})
        assert resp.status_code == 403
        resp = await client.post(WS_URL, json={"name": "x", "work_id": 999999})
        assert resp.status_code == 403


async def test_workspace_work_bind_unbind(memory_db):
    """PATCH 挂靠/解绑作品：401 未登录 / 403 他人作品 / 200 本人挂靠与解绑"""
    user = await _seed_user(memory_db, "u2")
    other = await _seed_user(memory_db, "u3")
    work = Work(user_id=user.id, title="我的剧")
    memory_db.add(work)
    await memory_db.commit()
    await memory_db.refresh(work)

    async for client in _build_client(memory_db, user):
        ws = (await client.post(WS_URL, json={"name": "自由画布"})).json()["data"]
        assert ws["work_id"] is None

    async for client in _build_client(memory_db):
        assert (await client.patch(f"{WS_URL}/{ws['id']}", json={"work_id": work.id})).status_code == 401

    # 挂到他人作品 403（同时覆盖非本人工作区 403）
    async for client in _build_client(memory_db, other):
        assert (await client.patch(f"{WS_URL}/{ws['id']}", json={"work_id": work.id})).status_code == 403

    async for client in _build_client(memory_db, user):
        resp = await client.patch(f"{WS_URL}/{ws['id']}", json={"work_id": work.id})
        assert resp.status_code == 200
        assert resp.json()["data"]["work_id"] == work.id
        # 解绑回自由画布
        resp = await client.patch(f"{WS_URL}/{ws['id']}", json={"work_id": None})
        assert resp.status_code == 200
        assert resp.json()["data"]["work_id"] is None
