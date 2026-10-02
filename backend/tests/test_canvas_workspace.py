# =====================================================
# 画布工作区云端落库测试
# - CRUD 全链路 + 鉴权三态（未登录 401 / 非本人 403 / 本人 200）
# - 乐观锁：revision 自增 / base_revision 过期 409 返回 current_revision
# - 自动快照节流：间隔未到不拍 / 内容未变不拍 / 超间隔且变化才拍 / auto 超 20 滚动删
# - manual/pre_danger 不占滚动额度 / kind 校验
# - 删除工作区连带删快照 / 列表不含 data
# =====================================================

import json
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func
from sqlalchemy.future import select

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.canvas_workspace import MAX_AUTO_SNAPSHOTS, CanvasSnapshot, CanvasWorkspace
from app.models.user import User
from app.routes.canvas_workspace import _data_hash


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
async def other_client(memory_db, seed_user):
    other = User(username="other", email="other@example.com", password_hash="x",
                 role="user", credits=0)
    memory_db.add(other)
    await memory_db.commit()
    await memory_db.refresh(other)
    async for client in _build_client(memory_db, other):
        yield client


@pytest_asyncio.fixture
async def anon_client(memory_db):
    async for client in _build_client(memory_db):
        yield client


@pytest_asyncio.fixture
async def seeded_ws(memory_db, seed_user) -> CanvasWorkspace:
    """预置一个属主工作区"""
    ws = CanvasWorkspace(id="ws_test_1", user_id=seed_user.id, name="我的画布",
                         data={"panels": [{"id": "p1"}], "connections": [], "groups": []})
    memory_db.add(ws)
    await memory_db.commit()
    await memory_db.refresh(ws)
    return ws


async def _snapshot_count(db, ws_id, kind=None) -> int:
    db.expire_all()
    q = select(func.count()).select_from(CanvasSnapshot).where(CanvasSnapshot.workspace_id == ws_id)
    if kind:
        q = q.where(CanvasSnapshot.kind == kind)
    return (await db.scalars(q)).first() or 0


async def _all_snapshots(db, ws_id) -> list:
    db.expire_all()
    return list((await db.scalars(
        select(CanvasSnapshot).where(CanvasSnapshot.workspace_id == ws_id)
        .order_by(CanvasSnapshot.created_at.desc())
    )).all())


async def _backdate(db, ws_id, seconds: float):
    """把该工作区全部快照回拨指定秒数（模拟距上次快照已超间隔）"""
    db.expire_all()
    snaps = (await db.scalars(
        select(CanvasSnapshot).where(CanvasSnapshot.workspace_id == ws_id)
    )).all()
    for s in snaps:
        s.created_at = s.created_at - timedelta(seconds=seconds)
    await db.commit()


async def _save(owner_client, rev: int, panels: list, ws_id: str, expect=200) -> dict:
    """保存一次，返回响应体 data（含 revision）；rev 由调用方跟踪"""
    resp = await owner_client.put(f"/api/canvas/workspaces/{ws_id}", json={
        "data": {"panels": panels, "connections": [], "groups": []},
        "base_revision": rev})
    assert resp.status_code == expect, resp.text
    if expect == 200:
        return resp.json()["data"]
    return {}


# ---------- 鉴权三态 ----------

@pytest.mark.asyncio
async def test_endpoints_require_auth(anon_client, seeded_ws):
    ws = seeded_ws.id
    assert (await anon_client.get("/api/canvas/workspaces")).status_code == 401
    assert (await anon_client.post("/api/canvas/workspaces", json={"name": "x"})).status_code == 401
    assert (await anon_client.get(f"/api/canvas/workspaces/{ws}")).status_code == 401
    assert (await anon_client.put(f"/api/canvas/workspaces/{ws}", json={
        "data": {}, "base_revision": 1})).status_code == 401
    assert (await anon_client.delete(f"/api/canvas/workspaces/{ws}")).status_code == 401
    assert (await anon_client.post(f"/api/canvas/workspaces/{ws}/snapshots", json={
        "kind": "manual"})).status_code == 401
    assert (await anon_client.get(f"/api/canvas/workspaces/{ws}/snapshots")).status_code == 401
    assert (await anon_client.get(f"/api/canvas/workspaces/{ws}/snapshots/1")).status_code == 401


@pytest.mark.asyncio
async def test_endpoints_forbid_other_user(other_client, seeded_ws):
    ws = seeded_ws.id
    assert (await other_client.get(f"/api/canvas/workspaces/{ws}")).status_code == 403
    assert (await other_client.put(f"/api/canvas/workspaces/{ws}", json={
        "data": {}, "base_revision": 1})).status_code == 403
    assert (await other_client.delete(f"/api/canvas/workspaces/{ws}")).status_code == 403
    assert (await other_client.post(f"/api/canvas/workspaces/{ws}/snapshots", json={
        "kind": "manual"})).status_code == 403
    assert (await other_client.get(f"/api/canvas/workspaces/{ws}/snapshots")).status_code == 403
    assert (await other_client.get(f"/api/canvas/workspaces/{ws}/snapshots/1")).status_code == 403
    assert (await other_client.delete(f"/api/canvas/workspaces/{ws}/snapshots/1")).status_code == 403


@pytest.mark.asyncio
async def test_get_missing_workspace_404(owner_client):
    resp = await owner_client.get("/api/canvas/workspaces/nope")
    assert resp.status_code == 404


# ---------- 创建 / 列表 ----------

@pytest.mark.asyncio
async def test_create_with_id_passthrough_and_idempotent(owner_client):
    body = {"id": "ws_local_1", "name": "迁移画布",
            "data": {"panels": [], "connections": [], "groups": []}}
    resp = await owner_client.post("/api/canvas/workspaces", json=body)
    assert resp.status_code == 200
    created = resp.json()["data"]
    assert created["id"] == "ws_local_1"
    assert created["revision"] == 1
    # 幂等：同 id 重复创建返回已有
    resp2 = await owner_client.post("/api/canvas/workspaces", json=body)
    assert resp2.json()["data"]["id"] == "ws_local_1"


@pytest.mark.asyncio
async def test_create_id_owned_by_other_user_409(owner_client, other_client):
    resp = await owner_client.post("/api/canvas/workspaces", json={"id": "ws_shared", "name": "a"})
    assert resp.status_code == 200
    resp2 = await other_client.post("/api/canvas/workspaces", json={"id": "ws_shared", "name": "b"})
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_create_without_id_generates(owner_client):
    resp = await owner_client.post("/api/canvas/workspaces", json={"name": "新画布"})
    assert resp.status_code == 200
    assert resp.json()["data"]["id"]


@pytest.mark.asyncio
async def test_list_excludes_data(owner_client, seeded_ws):
    resp = await owner_client.get("/api/canvas/workspaces")
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) == 1
    assert "data" not in items[0]
    assert items[0]["id"] == seeded_ws.id


# ---------- 保存与乐观锁 ----------

@pytest.mark.asyncio
async def test_save_increments_revision(owner_client, seeded_ws):
    rev_before = seeded_ws.revision  # 路由共用同 session，PUT 后 identity map 会就地更新该值
    resp = await _save(owner_client, rev_before, [{"id": "p2"}], seeded_ws.id)
    assert resp["revision"] == rev_before + 1


@pytest.mark.asyncio
async def test_save_conflict_409_returns_current_revision(owner_client, seeded_ws):
    rev_before = seeded_ws.revision  # 先取基准（expire 后 ORM 属性懒加载会炸同步测试代码）
    stale = rev_before + 5  # 客户端版本超前，必冲突
    resp = await owner_client.put(f"/api/canvas/workspaces/{seeded_ws.id}", json={
        "data": {"panels": []}, "base_revision": stale})
    assert resp.status_code == 409
    assert resp.json()["detail"]["current_revision"] == rev_before
    # 用正确版本重试成功
    ok_resp = await _save(owner_client, rev_before, [], seeded_ws.id)
    assert ok_resp["revision"] == rev_before + 1


@pytest.mark.asyncio
async def test_save_can_rename(owner_client, seeded_ws):
    rev_before = seeded_ws.revision
    resp = await owner_client.put(f"/api/canvas/workspaces/{seeded_ws.id}", json={
        "data": seeded_ws.data, "base_revision": rev_before, "name": "改名后"})
    assert resp.status_code == 200
    detail = (await owner_client.get(f"/api/canvas/workspaces/{seeded_ws.id}")).json()["data"]
    assert detail["name"] == "改名后"
    assert detail["revision"] == rev_before + 1


@pytest.mark.asyncio
async def test_get_detail_includes_data(owner_client, seeded_ws):
    resp = await owner_client.get(f"/api/canvas/workspaces/{seeded_ws.id}")
    body = resp.json()["data"]
    assert body["data"]["panels"] == [{"id": "p1"}]
    assert body["revision"] == seeded_ws.revision


# ---------- 自动快照节流 ----------

@pytest.mark.asyncio
async def test_auto_snapshot_throttle(owner_client, seeded_ws, memory_db):
    ws_id = seeded_ws.id
    rev = seeded_ws.revision
    # 首次保存：无任何快照 → 拍第 1 份
    rev = (await _save(owner_client, rev, [{"id": "a"}], ws_id))["revision"]
    assert await _snapshot_count(memory_db, ws_id, kind="auto") == 1
    # 间隔未到（300s 内）连续保存 → 不再拍
    rev = (await _save(owner_client, rev, [{"id": "b"}], ws_id))["revision"]
    rev = (await _save(owner_client, rev, [{"id": "c"}], ws_id))["revision"]
    assert await _snapshot_count(memory_db, ws_id, kind="auto") == 1
    # 超间隔 + 内容变化 → 拍第 2 份
    await _backdate(memory_db, ws_id, 400)
    rev = (await _save(owner_client, rev, [{"id": "c"}], ws_id))["revision"]
    assert await _snapshot_count(memory_db, ws_id, kind="auto") == 2
    # 超间隔 + 内容未变（同 hash）→ 不拍
    await _backdate(memory_db, ws_id, 400)
    rev = (await _save(owner_client, rev, [{"id": "c"}], ws_id))["revision"]
    assert await _snapshot_count(memory_db, ws_id, kind="auto") == 2
    # 内容变化 → 拍第 3 份
    rev = (await _save(owner_client, rev, [{"id": "d"}], ws_id))["revision"]
    assert await _snapshot_count(memory_db, ws_id, kind="auto") == 3


@pytest.mark.asyncio
async def test_auto_snapshot_rolls_over_20(owner_client, seeded_ws, memory_db):
    ws = seeded_ws
    base = datetime.utcnow() - timedelta(seconds=400 * (MAX_AUTO_SNAPSHOTS + 1))
    for i in range(MAX_AUTO_SNAPSHOTS):
        memory_db.add(CanvasSnapshot(
            workspace_id=ws.id, user_id=ws.user_id, kind="auto", revision=1,
            content_hash=f"old-{i}", data={},
            created_at=base + timedelta(seconds=400 * i)))
    await memory_db.commit()
    rev = (await _save(owner_client, ws.revision, [{"id": "new"}], ws.id))["revision"]
    autos = [s for s in await _all_snapshots(memory_db, ws.id) if s.kind == "auto"]
    assert len(autos) == MAX_AUTO_SNAPSHOTS
    hashes = {s.content_hash for s in autos}
    assert "old-0" not in hashes          # 最旧的被滚删
    new_hash = _data_hash({"panels": [{"id": "new"}], "connections": [], "groups": []})
    assert new_hash in hashes             # 新快照在内


@pytest.mark.asyncio
async def test_manual_snapshots_not_rolled(owner_client, seeded_ws, memory_db):
    ws_id = seeded_ws.id
    rev = seeded_ws.revision  # 先取基准（expire 后 ORM 属性懒加载会炸同步测试代码）
    for i in range(25):
        resp = await owner_client.post(f"/api/canvas/workspaces/{ws_id}/snapshots", json={
            "kind": "manual", "name": f"版本{i}"})
        assert resp.status_code == 200
    # manual 无节流、不受 20 上限影响
    assert await _snapshot_count(memory_db, ws_id, kind="manual") == 25
    # 一次触发节流的保存不删 manual
    await _save(owner_client, rev, [{"id": "x"}], ws_id)
    assert await _snapshot_count(memory_db, ws_id, kind="manual") == 25


@pytest.mark.asyncio
async def test_snapshot_kind_validation(owner_client, seeded_ws):
    resp = await owner_client.post(f"/api/canvas/workspaces/{seeded_ws.id}/snapshots", json={
        "kind": "auto"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_manual_snapshot_records_revision(owner_client, seeded_ws):
    ws_id = seeded_ws.id
    rev = (await _save(owner_client, seeded_ws.revision, [{"id": "a"}], ws_id))["revision"]
    resp = await owner_client.post(f"/api/canvas/workspaces/{ws_id}/snapshots", json={
        "kind": "pre_danger"})
    body = resp.json()["data"]
    assert body["kind"] == "pre_danger"
    assert body["revision"] == rev


# ---------- 快照读取 ----------

@pytest.mark.asyncio
async def test_snapshot_list_excludes_data(owner_client, seeded_ws):
    await owner_client.post(f"/api/canvas/workspaces/{seeded_ws.id}/snapshots", json={
        "kind": "manual", "name": "定稿"})
    resp = await owner_client.get(f"/api/canvas/workspaces/{seeded_ws.id}/snapshots")
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert "data" not in items[0]
    assert items[0]["name"] == "定稿"


@pytest.mark.asyncio
async def test_snapshot_detail_roundtrip(owner_client, seeded_ws):
    await _save(owner_client, seeded_ws.revision, [{"id": "snap_data"}], seeded_ws.id)
    resp_list = await owner_client.get(f"/api/canvas/workspaces/{seeded_ws.id}/snapshots")
    sid = resp_list.json()["data"]["items"][0]["id"]
    resp = await owner_client.get(f"/api/canvas/workspaces/{seeded_ws.id}/snapshots/{sid}")
    body = resp.json()["data"]
    assert body["data"]["panels"] == [{"id": "snap_data"}]


@pytest.mark.asyncio
async def test_delete_snapshot(owner_client, seeded_ws, memory_db):
    ws_id = seeded_ws.id
    await owner_client.post(f"/api/canvas/workspaces/{ws_id}/snapshots", json={"kind": "manual"})
    resp_list = await owner_client.get(f"/api/canvas/workspaces/{ws_id}/snapshots")
    sid = resp_list.json()["data"]["items"][0]["id"]
    assert (await owner_client.delete(f"/api/canvas/workspaces/{ws_id}/snapshots/{sid}")).status_code == 200
    assert await _snapshot_count(memory_db, ws_id) == 0
    assert (await owner_client.delete(f"/api/canvas/workspaces/{ws_id}/snapshots/{sid}")).status_code == 404


# ---------- 删除级联 ----------

@pytest.mark.asyncio
async def test_delete_workspace_cascades_snapshots(owner_client, seeded_ws, memory_db):
    ws_id = seeded_ws.id
    await owner_client.post(f"/api/canvas/workspaces/{ws_id}/snapshots", json={"kind": "manual"})
    assert await _snapshot_count(memory_db, ws_id) == 1
    resp = await owner_client.delete(f"/api/canvas/workspaces/{ws_id}")
    assert resp.status_code == 200
    assert await _snapshot_count(memory_db, ws_id) == 0
    assert (await owner_client.get(f"/api/canvas/workspaces/{ws_id}")).status_code == 404
