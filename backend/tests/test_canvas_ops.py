# =====================================================
# 画布远程操作测试
# - ops 端点：批量 add_panel / add_connection、默认值、批内按名引用、revision 推进
# - 连线类型规则全分支（对齐前端 validateConnectionTypes）
# - 全部失败 400 不写回 / 部分失败整批落库 / ops 数量校验
# - revision 端点 / 鉴权三态（未登录 401 / 非本人 403 / 本人 200）
# =====================================================

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.future import select

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.canvas_workspace import CanvasWorkspace
from app.models.user import User


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
    other = User(username="other_ops", email="other_ops@example.com", password_hash="x",
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
async def empty_ws(memory_db, seed_user) -> CanvasWorkspace:
    ws = CanvasWorkspace(id="ws_ops_1", user_id=seed_user.id, name="操作画布", data={})
    memory_db.add(ws)
    await memory_db.commit()
    await memory_db.refresh(ws)
    return ws


async def _ws_data(memory_db, ws_id: str) -> dict:
    memory_db.expire_all()
    ws = (await memory_db.scalars(
        select(CanvasWorkspace).where(CanvasWorkspace.id == ws_id)
    )).first()
    return ws.data or {}


# ---------- 鉴权三态 ----------

@pytest.mark.asyncio
async def test_ops_endpoints_require_auth(anon_client, empty_ws):
    ws = empty_ws.id
    assert (await anon_client.post(f"/api/canvas/workspaces/{ws}/ops", json={
        "ops": [{"op": "add_panel", "name": "a"}]})).status_code == 401
    assert (await anon_client.get(f"/api/canvas/workspaces/{ws}/revision")).status_code == 401


@pytest.mark.asyncio
async def test_ops_endpoints_forbid_other_user(other_client, empty_ws):
    ws = empty_ws.id
    assert (await other_client.post(f"/api/canvas/workspaces/{ws}/ops", json={
        "ops": [{"op": "add_panel", "name": "a"}]})).status_code == 403
    assert (await other_client.get(f"/api/canvas/workspaces/{ws}/revision")).status_code == 403


@pytest.mark.asyncio
async def test_ops_missing_workspace_404(owner_client):
    resp = await owner_client.post("/api/canvas/workspaces/nope/ops", json={
        "ops": [{"op": "add_panel", "name": "a"}]})
    assert resp.status_code == 404


# ---------- add_panel 语义 ----------

@pytest.mark.asyncio
async def test_add_panel_defaults(owner_client, empty_ws, memory_db):
    rev0 = empty_ws.revision
    resp = await owner_client.post(f"/api/canvas/workspaces/{empty_ws.id}/ops", json={
        "ops": [{"op": "add_panel"}]})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["revision"] == rev0 + 1
    (result,) = data["results"]
    assert result["ok"] is True and result["panel_id"]
    (panel,) = (await _ws_data(memory_db, empty_ws.id))["panels"]
    assert panel["type"] == "text"
    assert panel["x"] == 120 and panel["y"] == 120
    assert panel["width"] == 240 and panel["height"] == 180
    assert panel["zIndex"] == 1
    assert panel["content"] == {}
    assert panel["workspace_id"] == empty_ws.id
    assert panel["created_at"] and panel["updated_at"]


@pytest.mark.asyncio
async def test_add_panel_position_cycles_and_zindex(owner_client, empty_ws, memory_db):
    resp = await owner_client.post(f"/api/canvas/workspaces/{empty_ws.id}/ops", json={
        "ops": [{"op": "add_panel", "name": f"p{i}"} for i in range(9)]})
    assert resp.status_code == 200
    panels = (await _ws_data(memory_db, empty_ws.id))["panels"]
    assert [p["x"] for p in panels] == [120 + (i % 8) * 40 for i in range(9)]
    assert [p["zIndex"] for p in panels] == [i + 1 for i in range(9)]


@pytest.mark.asyncio
async def test_add_panel_explicit_fields(owner_client, empty_ws, memory_db):
    resp = await owner_client.post(f"/api/canvas/workspaces/{empty_ws.id}/ops", json={
        "ops": [{"op": "add_panel", "type": "image", "name": "主角图",
                 "content": {"status": "success", "content": "http://x/a.png"},
                 "x": 10, "y": 20, "width": 300, "height": 200}]})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["new_panel_ids"]) == 1
    (panel,) = (await _ws_data(memory_db, empty_ws.id))["panels"]
    assert panel["type"] == "image" and panel["name"] == "主角图"
    assert panel["content"]["status"] == "success"
    assert panel["x"] == 10 and panel["width"] == 300


# ---------- 批内按名引用 + add_connection ----------

@pytest.mark.asyncio
async def test_batch_connection_by_name(owner_client, empty_ws, memory_db):
    resp = await owner_client.post(f"/api/canvas/workspaces/{empty_ws.id}/ops", json={
        "ops": [
            {"op": "add_panel", "type": "text", "name": "剧本", "content": {"content": "开场"}},
            {"op": "add_panel", "type": "image", "name": "主角设定图", "content": {"prompt": "a hero"}},
            {"op": "add_connection", "source_panel_id": "剧本", "target_panel_id": "主角设定图"},
        ]})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert [r["ok"] for r in data["results"]] == [True, True, True]
    assert len(data["new_panel_ids"]) == 2
    stored = await _ws_data(memory_db, empty_ws.id)
    (conn,) = stored["connections"]
    assert conn["source_panel_id"] == data["new_panel_ids"][0]
    assert conn["target_panel_id"] == data["new_panel_ids"][1]
    assert conn["type"] == "manual"


@pytest.mark.asyncio
async def test_connection_by_existing_panel_name(owner_client, seed_user, memory_db):
    ws = CanvasWorkspace(id="ws_ops_2", user_id=seed_user.id, name="已有画布",
                         data={"panels": [{"id": "p_text", "type": "text", "name": "旁白"}],
                               "connections": []})
    memory_db.add(ws)
    await memory_db.commit()
    resp = await owner_client.post("/api/canvas/workspaces/ws_ops_2/ops", json={
        "ops": [
            {"op": "add_panel", "type": "image", "name": "配图"},
            {"op": "add_connection", "source_panel_id": "旁白", "target_panel_id": "配图"},
        ]})
    assert resp.status_code == 200, resp.text
    conn = (await _ws_data(memory_db, "ws_ops_2"))["connections"][0]
    assert conn["source_panel_id"] == "p_text"
    assert conn["target_panel_id"] == resp.json()["data"]["new_panel_ids"][0]


# ---------- 连线类型规则 ----------

@pytest.mark.parametrize("source_type,target_type,expect_ok", [
    ("text", "image", True),
    ("image", "video", True),
    ("script", "config", True),
    ("script", "text", False),
    ("image", "tts", False),
    ("text", "tts", True),
    ("video", "subtitle", False),
    ("text", "subtitle", True),
    ("image", "compose", False),
    ("video", "compose", True),
    ("tts", "compose", True),
])
@pytest.mark.asyncio
async def test_connection_type_rules(owner_client, empty_ws, source_type, target_type, expect_ok):
    resp = await owner_client.post(f"/api/canvas/workspaces/{empty_ws.id}/ops", json={
        "ops": [
            {"op": "add_panel", "type": source_type, "name": "s"},
            {"op": "add_panel", "type": target_type, "name": "t"},
            {"op": "add_connection", "source_panel_id": "s", "target_panel_id": "t"},
        ]})
    assert resp.status_code == 200
    conn_result = resp.json()["data"]["results"][2]
    assert conn_result["ok"] is expect_ok
    if not expect_ok:
        assert "不接受" in conn_result["error"] or "只能" in conn_result["error"]


# ---------- 失败语义 ----------

@pytest.mark.asyncio
async def test_partial_failure_still_applies(owner_client, empty_ws, memory_db):
    resp = await owner_client.post(f"/api/canvas/workspaces/{empty_ws.id}/ops", json={
        "ops": [
            {"op": "add_panel", "name": "ok节点"},
            {"op": "add_panel"},
            {"op": "add_connection", "source_panel_id": "ok节点", "target_panel_id": "不存在"},
        ]})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [r["ok"] for r in data["results"]] == [True, True, False]
    assert data["failed"] == 1
    assert len((await _ws_data(memory_db, empty_ws.id))["panels"]) == 2


@pytest.mark.asyncio
async def test_all_failed_rejected_without_write(owner_client, empty_ws, memory_db):
    before = await _ws_data(memory_db, empty_ws.id)
    resp = await owner_client.post(f"/api/canvas/workspaces/{empty_ws.id}/ops", json={
        "ops": [
            {"op": "add_connection", "source_panel_id": "a", "target_panel_id": "b"},
            {"op": "frobnicate"},
        ]})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert [r["ok"] for r in detail["results"]] == [False, False]
    assert await _ws_data(memory_db, empty_ws.id) == before


@pytest.mark.asyncio
async def test_ops_requires_nonempty_list(owner_client, empty_ws):
    # 项目统一把 RequestValidationError 转为 400（见 main.py validation_exception_handler）
    resp = await owner_client.post(f"/api/canvas/workspaces/{empty_ws.id}/ops", json={"ops": []})
    assert resp.status_code == 400


# ---------- revision 端点 ----------

@pytest.mark.asyncio
async def test_revision_endpoint(owner_client, empty_ws):
    rev0 = empty_ws.revision
    resp = await owner_client.get(f"/api/canvas/workspaces/{empty_ws.id}/revision")
    assert resp.status_code == 200
    assert resp.json()["data"]["revision"] == rev0
    await owner_client.post(f"/api/canvas/workspaces/{empty_ws.id}/ops", json={
        "ops": [{"op": "add_panel", "name": "a"}]})
    resp = await owner_client.get(f"/api/canvas/workspaces/{empty_ws.id}/revision")
    assert resp.json()["data"]["revision"] == rev0 + 1
