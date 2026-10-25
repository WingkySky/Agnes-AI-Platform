# =====================================================
# 3D 场景导演台测试：cover_url 视口截图封面（导演台第一批）
# 创建/更新 cover_url、响应透出、非创建者 403
# =====================================================

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.scene3d import Scene3D
from app.models.user import User


async def _build_client(memory_db, user):
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
    app.dependency_overrides.clear()


async def _seed_user(memory_db, username):
    user = User(username=username, email=f"{username}@example.com",
                password_hash="x", role="user", credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    return user


async def _seed_scene(memory_db, user_id: int, cover_url: str | None = None) -> Scene3D:
    scene = Scene3D(user_id=user_id, name="天台夜戏", scene_data={"camera": {"position": {"x": 0, "y": 1.6, "z": 5}}}, cover_url=cover_url)
    memory_db.add(scene)
    await memory_db.commit()
    await memory_db.refresh(scene)
    return scene


@pytest.mark.asyncio
async def test_update_cover_url_and_response(memory_db):
    user = await _seed_user(memory_db, "director1")
    scene = await _seed_scene(memory_db, user.id)
    async for client in _build_client(memory_db, user):
        resp = await client.put(f"/api/scenes/{scene.id}", json={"cover_url": "/uploads/scene-covers/a.png"})
        assert resp.status_code == 200
        assert resp.json()["data"]["cover_url"] == "/uploads/scene-covers/a.png"

        listed = await client.get("/api/scenes")
        assert listed.json()["data"]["items"][0]["cover_url"] == "/uploads/scene-covers/a.png"


@pytest.mark.asyncio
async def test_cover_url_forbidden_for_non_owner(memory_db):
    owner = await _seed_user(memory_db, "owner1")
    other = await _seed_user(memory_db, "other1")
    scene = await _seed_scene(memory_db, owner.id)
    async for client in _build_client(memory_db, other):
        resp = await client.put(f"/api/scenes/{scene.id}", json={"cover_url": "/uploads/x.png"})
        assert resp.status_code == 403
