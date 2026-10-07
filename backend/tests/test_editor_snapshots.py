# =====================================================
# 剪辑工程快照 + revision 轻查询测试
# 快照：agent 写前触发 / 5 分钟窗口内容哈希去重 / 非本人 403 / 列表不含 data
# =====================================================

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User

pytestmark = pytest.mark.asyncio

URL = "/api/editor/projects"


def _doc(clip_id="c1"):
    return {
        "timebase": 30, "width": 1280, "height": 720,
        "tracks": [
            {"id": "v1", "kind": "video", "order": 0, "flags": {}},
            {"id": "a1", "kind": "audio", "order": 0, "flags": {}},
        ],
        "clips": [
            {"id": clip_id, "trackId": "v1", "assetId": None, "start": 0.0,
             "duration": 2.0, "trimStart": 0.0, "props": {}},
        ],
    }


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


async def test_revision_and_snapshots_anon_401(memory_db):
    async for client in _build_client(memory_db):
        assert (await client.get(f"{URL}/some-uid/revision")).status_code == 401
        assert (await client.get(f"{URL}/some-uid/snapshots")).status_code == 401
        assert (await client.get(f"{URL}/some-uid/snapshots/1")).status_code == 401


async def test_owner_boundary_403(memory_db):
    owner = await _seed_user(memory_db, "owner")
    other = await _seed_user(memory_db, "other")
    async for client in _build_client(memory_db, owner):
        uid = (await client.post(URL, json={"title": "我的工程"})).json()["data"]["uid"]
    async for client in _build_client(memory_db, other):
        assert (await client.get(f"{URL}/{uid}/revision")).status_code == 403
        assert (await client.get(f"{URL}/{uid}/snapshots")).status_code == 403
        assert (await client.get(f"{URL}/{uid}/snapshots/1")).status_code == 403


async def test_snapshot_write_before_and_dedup(memory_db):
    """带 snapshot_reason 保存：快照捕获写前文档；窗口内写前内容与最新快照一致时去重"""
    user = await _seed_user(memory_db, "u1")
    async for client in _build_client(memory_db, user):
        uid = (await client.post(URL, json={"title": "对话剪辑"})).json()["data"]["uid"]

        # 第一次 agent 保存：写前快照 = 初始文档（revision 1，无片段）
        resp = await client.put(f"{URL}/{uid}/document", json={
            "document": _doc("c_new"), "base_revision": 1, "snapshot_reason": "agent_edit"})
        assert resp.status_code == 200
        snaps = (await client.get(f"{URL}/{uid}/snapshots")).json()["data"]["items"]
        assert len(snaps) == 1
        assert snaps[0]["revision"] == 1 and snaps[0]["kind"] == "agent"
        assert snaps[0]["reason"] == "agent_edit"
        assert "data" not in snaps[0], "列表不携带 data"
        full = (await client.get(f"{URL}/{uid}/snapshots/{snaps[0]['id']}")).json()["data"]
        assert full["data"]["clips"] == []

        # 第二次 agent 保存相同内容：写前文档（c_new）与最新快照（初始）不同 → 新快照
        await client.put(f"{URL}/{uid}/document", json={
            "document": _doc("c_new"), "base_revision": 2, "snapshot_reason": "agent_edit"})
        snaps = (await client.get(f"{URL}/{uid}/snapshots")).json()["data"]["items"]
        assert len(snaps) == 2
        full = (await client.get(f"{URL}/{uid}/snapshots/{snaps[0]['id']}")).json()["data"]
        assert [c["id"] for c in full["data"]["clips"]] == ["c_new"]

        # 第三次 agent 保存仍相同内容：写前内容与最新快照一致 → 去重不新增
        await client.put(f"{URL}/{uid}/document", json={
            "document": _doc("c_new"), "base_revision": 3, "snapshot_reason": "agent_edit"})
        assert len((await client.get(f"{URL}/{uid}/snapshots")).json()["data"]["items"]) == 2

        # 无 snapshot_reason 的普通保存：不触发快照
        await client.put(f"{URL}/{uid}/document", json={
            "document": _doc("c_ui"), "base_revision": 4})
        assert len((await client.get(f"{URL}/{uid}/snapshots")).json()["data"]["items"]) == 2

        # 快照还原走正常保存链路：拉最旧快照 data 带 snapshot_reason PUT 回去
        oldest = (await client.get(f"{URL}/{uid}/snapshots")).json()["data"]["items"][-1]
        restore_doc = (await client.get(f"{URL}/{uid}/snapshots/{oldest['id']}")).json()["data"]["data"]
        resp = await client.put(f"{URL}/{uid}/document", json={
            "document": restore_doc, "base_revision": 5, "snapshot_reason": "restore"})
        assert resp.status_code == 200
        detail = (await client.get(f"{URL}/{uid}")).json()["data"]
        assert detail["document"]["clips"] == []

        # 跨工程隔离：他工程 uid 查不到本工程快照
        other_uid = (await client.post(URL, json={"title": "别的工程"})).json()["data"]["uid"]
        resp = await client.get(f"{URL}/{other_uid}/snapshots/{oldest['id']}")
        assert resp.status_code == 404


async def test_revision_endpoint(memory_db):
    user = await _seed_user(memory_db, "u1")
    async for client in _build_client(memory_db, user):
        uid = (await client.post(URL, json={"title": "x"})).json()["data"]["uid"]
        resp = await client.get(f"{URL}/{uid}/revision")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["revision"] == 1 and data["render_status"] == "idle"
        await client.put(f"{URL}/{uid}/document", json={"document": _doc(), "base_revision": 1})
        data = (await client.get(f"{URL}/{uid}/revision")).json()["data"]
        assert data["revision"] == 2

        # 不存在 404
        assert (await client.get(f"{URL}/nope/revision")).status_code == 404
