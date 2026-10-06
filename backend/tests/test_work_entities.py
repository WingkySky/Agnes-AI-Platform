# =====================================================
# 作品实体库端点测试（/api/works/{id}/entities、/api/entities）
# 401 未登录 / 200 本人 / 403 非本人 / 404 不存在；
# 版本自动采用与回切、产图自动入版本钩子（作品不匹配拒绝）
# =====================================================

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.asset import Asset
from app.models.user import User
from app.models.work import Work
from app.services import work_entity_service

pytestmark = pytest.mark.asyncio

WORKS_URL = "/api/works"


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


async def _seed_asset(memory_db, user_id: int, url: str = "/uploads/a.png") -> Asset:
    asset = Asset(type="material", name="设定图", visual_description="图",
                  user_id=user_id, asset_url=url)
    memory_db.add(asset)
    await memory_db.commit()
    await memory_db.refresh(asset)
    return asset


async def _seed_work(memory_db, user_id: int, title: str = "我的剧") -> Work:
    work = Work(user_id=user_id, title=title)
    memory_db.add(work)
    await memory_db.commit()
    await memory_db.refresh(work)
    return work


async def test_anon_401(memory_db):
    async for client in _build_client(memory_db):
        assert (await client.get(f"{WORKS_URL}/1/entities")).status_code == 401
        assert (await client.post(f"{WORKS_URL}/1/entities", json={"kind": "character", "name": "x"})).status_code == 401
        assert (await client.patch("/api/entities/1", json={"name": "x"})).status_code == 401
        assert (await client.post("/api/entities/1/versions", json={"asset_id": 1})).status_code == 401


async def test_entity_crud_versions_and_adopt(memory_db):
    user = await _seed_user(memory_db, "u1")
    work = await _seed_work(memory_db, user.id)
    asset1 = await _seed_asset(memory_db, user.id, "/uploads/v1.png")
    asset2 = await _seed_asset(memory_db, user.id, "/uploads/v2.png")
    asset3 = await _seed_asset(memory_db, user.id, "/uploads/v3.png")

    async for client in _build_client(memory_db, user):
        base = f"{WORKS_URL}/{work.id}/entities"
        # 建实体带首图 → 首版本即采用
        resp = await client.post(base, json={"kind": "character", "name": "林晚", "description": "女主角", "asset_id": asset1.id})
        assert resp.status_code == 200
        entity = resp.json()["data"]
        assert entity["active_image_url"] == "/uploads/v1.png"
        assert len(entity["versions"]) == 1 and entity["versions"][0]["is_active"] is True
        eid = entity["id"]

        # 列表 + kind 筛选
        resp = await client.get(base)
        assert resp.status_code == 200 and resp.json()["data"]["total"] == 1
        assert (await client.get(base, params={"kind": "scene"})).json()["data"]["total"] == 0

        # design 新版本 → 自动采用，旧版本保留
        resp = await client.post(f"/api/entities/{eid}/versions", json={"asset_id": asset2.id})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["active_image_url"] == "/uploads/v2.png"
        assert len(data["versions"]) == 2
        old_version_id = next(v["id"] for v in data["versions"] if not v["is_active"])

        # angle 表现图追加进当前采用版本（不新开版本、不翻采用）
        resp = await client.post(f"/api/entities/{eid}/versions", json={"asset_id": asset3.id, "role": "angle"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["versions"]) == 2
        active = next(v for v in data["versions"] if v["is_active"])
        assert [img["role"] for img in active["images"]] == ["design", "angle"]
        assert active["images"][1]["url"] == "/uploads/v3.png"

        # 回切旧版本
        resp = await client.post(f"/api/entities/{eid}/adopt", json={"version_id": old_version_id})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["active_image_url"] == "/uploads/v1.png"

        # 改名 / 不存在版本 404
        resp = await client.patch(f"/api/entities/{eid}", json={"name": "林晚（改）"})
        assert resp.status_code == 200 and resp.json()["data"]["name"] == "林晚（改）"
        assert (await client.post(f"/api/entities/{eid}/adopt", json={"version_id": 999999})).status_code == 404

        # 删除实体
        assert (await client.delete(f"/api/entities/{eid}")).status_code == 200
        assert (await client.get(base)).json()["data"]["total"] == 0


async def test_other_user_403_and_missing_404(memory_db):
    owner = await _seed_user(memory_db, "owner")
    other = await _seed_user(memory_db, "other")
    work = await _seed_work(memory_db, owner.id)
    asset = await _seed_asset(memory_db, owner.id)
    resp = None
    async for client in _build_client(memory_db, owner):
        resp = await client.post(f"{WORKS_URL}/{work.id}/entities", json={"kind": "prop", "name": "玉佩", "asset_id": asset.id})
    eid = resp.json()["data"]["id"]
    vid = resp.json()["data"]["versions"][0]["id"]

    async for client in _build_client(memory_db, other):
        assert (await client.get(f"{WORKS_URL}/{work.id}/entities")).status_code == 403
        assert (await client.post(f"{WORKS_URL}/{work.id}/entities", json={"kind": "prop", "name": "x"})).status_code == 403
        assert (await client.patch(f"/api/entities/{eid}", json={"name": "hack"})).status_code == 403
        assert (await client.delete(f"/api/entities/{eid}")).status_code == 403
        assert (await client.post(f"/api/entities/{eid}/versions", json={"asset_id": asset.id})).status_code == 403
        assert (await client.post(f"/api/entities/{eid}/adopt", json={"version_id": vid})).status_code == 403
        # 不存在
        assert (await client.get(f"{WORKS_URL}/999999/entities")).status_code == 404
        assert (await client.patch("/api/entities/999999", json={"name": "x"})).status_code == 404

    # 他人资产不能当表现图
    async for client in _build_client(memory_db, other):
        other_work = await _seed_work(memory_db, other.id, "别人的剧")
        resp = await client.post(f"{WORKS_URL}/{other_work.id}/entities", json={"kind": "prop", "name": "x", "asset_id": asset.id})
        assert resp.status_code == 404


async def test_add_version_from_generation_hook(memory_db):
    user = await _seed_user(memory_db, "u1")
    work = await _seed_work(memory_db, user.id)
    asset = await _seed_asset(memory_db, user.id)
    other_work = await _seed_work(memory_db, user.id, "第二部")
    entity_dict = await work_entity_service.create_entity(memory_db, work.id, "character", "钩子实体")
    entity_id = entity_dict["id"]

    # design 新版本自动采用
    version = await work_entity_service.add_version_from_generation(
        memory_db, entity_id, asset.id, 1001, role="design", work_id=work.id,
    )
    assert version is not None and version.is_active is True
    assert version.source_generation_id == 1001

    # angle 追加进采用版本（不新开版本）
    version2 = await work_entity_service.add_version_from_generation(
        memory_db, entity_id, asset.id, 1002, role="angle", work_id=work.id,
    )
    assert version2.id == version.id
    assert [img["role"] for img in version2.images] == ["design", "angle"]

    # 作品不匹配拒绝（防串库）
    assert await work_entity_service.add_version_from_generation(
        memory_db, entity_id, asset.id, 1003, role="design", work_id=other_work.id,
    ) is None
    # 实体不存在返回 None
    assert await work_entity_service.add_version_from_generation(
        memory_db, 999999, asset.id, 1004, role="design", work_id=work.id,
    ) is None


async def test_delete_work_cascades_entities(memory_db):
    """删作品：实体库随作品删除（versions 级联），不撞外键"""
    user = await _seed_user(memory_db, "u1")
    work = await _seed_work(memory_db, user.id)
    asset = await _seed_asset(memory_db, user.id)
    await work_entity_service.create_entity(memory_db, work.id, "character", "林晚", asset_id=asset.id)
    assert (await memory_db.scalars(select(work_entity_service.WorkEntity.id))).first() is not None

    async for client in _build_client(memory_db, user):
        assert (await client.delete(f"{WORKS_URL}/{work.id}")).status_code == 200
    assert (await memory_db.scalars(select(work_entity_service.WorkEntity))).all() == []
    assert (await memory_db.scalars(select(work_entity_service.WorkEntityVersion))).all() == []
