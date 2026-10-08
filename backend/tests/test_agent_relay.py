# =====================================================
# Agent 反向控制桥测试
# - 服务层：注册/顶替(demote)/注销/回执分发/relay_call 超时与断连
# - WS 协议：坏 token 4401 / register→registered / ping→pong / 未知回执静默（回环替身，不触 lifespan）
# - 路由层：/call 离线路由 + 白名单 403 + 未知 host 400 + 归属 404/403 + 三态鉴权 + /targets
# =====================================================

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from starlette.websockets import WebSocketDisconnect

pytestmark = pytest.mark.asyncio

from app.core.database import get_async_db
from app.core.security import create_access_token, decode_access_token
from app.main import app
from app.models.canvas_workspace import CanvasWorkspace
from app.models.editing_project import EditingProject
from app.models.user import User
from app.routes.agent_relay import relay_ws
from app.services import relay_service
from app.services.relay_service import (
    BridgeConnection,
    BridgeOffline,
    BridgeTimeout,
    handle_relay_result,
    relay_call,
    register,
    run_ws,
    unregister,
)


# ---------- 测试替身：内存 WebSocket ----------

class FakeSendWebSocket:
    """仅发送侧（服务层单测用）"""

    def __init__(self):
        self.sent: list = []

    async def send_json(self, payload):
        self.sent.append(payload)


class LoopbackWebSocket:
    """双向内存 WS：send_json 进 outbox，receive_json 从 inbox 弹（空即断开）"""

    def __init__(self):
        self.outbox: list = []
        self.inbox: list = []

    async def send_json(self, payload):
        self.outbox.append(payload)

    async def receive_json(self):
        if not self.inbox:
            raise WebSocketDisconnect(1000)
        return self.inbox.pop(0)


class CloseRecordingWebSocket:
    """route 层用：记录 accept/close，receive 立即断开"""

    def __init__(self):
        self.accepted = False
        self.close_code: int | None = None

    async def accept(self):
        self.accepted = True

    async def close(self, code: int):
        self.close_code = code

    async def receive_json(self):
        raise WebSocketDisconnect(1000)

    async def send_json(self, payload):
        pass


@pytest.fixture(autouse=True)
def _clean_registry():
    relay_service.reset_registry()
    yield
    relay_service.reset_registry()


def _conn(user_id: int = 1) -> BridgeConnection:
    return BridgeConnection(FakeSendWebSocket(), user_id)


# ---------- 服务层 ----------

async def test_register_and_get_connection():
    conn = _conn(user_id=7)
    await register(conn, "canvas", "ws_1")
    got = relay_service.get_connection(7, "canvas", "ws_1")
    assert got is conn
    assert {"host": "canvas", "target_id": "ws_1"} in relay_service.list_targets(7)
    assert relay_service.list_targets(8) == []


async def test_register_supersede_demotes_old():
    old, new = _conn(7), _conn(7)
    await register(old, "canvas", "ws_1")
    await register(new, "canvas", "ws_1")
    assert old.superseded is True
    assert old.ws.sent[-1] == {"type": "demoted"}
    assert relay_service.get_connection(7, "canvas", "ws_1") is new
    # 被顶替连接不可再执行
    with pytest.raises(BridgeOffline):
        await relay_call(old, "agent_get_state", {}, 0.1)


async def test_register_target_change_migrates_index():
    """同一连接换目标（画布切工作区重注册）：旧索引清理、新索引生效"""
    conn = _conn(7)
    await register(conn, "canvas", "ws_a")
    await register(conn, "canvas", "ws_b")
    assert relay_service.get_connection(7, "canvas", "ws_a") is None
    assert relay_service.get_connection(7, "canvas", "ws_b") is conn


async def test_unregister_fails_pending():
    conn = _conn(7)
    await register(conn, "editor", "proj_1")
    task = asyncio.create_task(relay_call(conn, "editor_apply_ops", {"ops": []}, 1.0))
    await asyncio.sleep(0)
    unregister(conn)
    with pytest.raises(BridgeOffline):
        await task


async def test_relay_call_roundtrip():
    conn = _conn(7)
    await register(conn, "canvas", "ws_1")
    task = asyncio.create_task(relay_call(conn, "agent_get_state", {}, 1.0))
    await asyncio.sleep(0)
    # 下发载荷含 call_id/tool/args
    sent = conn.ws.sent[-1]
    assert sent["type"] == "relay_call" and sent["tool"] == "agent_get_state"
    handle_relay_result(conn, {"type": "relay_result", "call_id": sent["call_id"],
                               "payload": {"ok": True, "data": {"x": 1}}})
    assert await task == {"ok": True, "data": {"x": 1}}


async def test_relay_call_timeout():
    conn = _conn(7)
    await register(conn, "canvas", "ws_1")
    with pytest.raises(BridgeTimeout):
        await relay_call(conn, "agent_get_state", {}, 0.01)


# ---------- WS 协议（回环替身） ----------

async def test_ws_rejects_bad_token():
    ws = CloseRecordingWebSocket()
    await relay_ws(ws, "not-a-token")
    assert ws.accepted is False
    assert ws.close_code == 4401


async def test_ws_protocol_register_ping_unknown_result():
    ws = LoopbackWebSocket()
    ws.inbox = [
        {"type": "register", "host": "canvas", "target_id": "ws_proto"},
        {"type": "ping"},
        # 未知 call_id 回执被静默忽略（连接不断）
        {"type": "relay_result", "call_id": "nope", "ok": True, "result": {}},
        {"type": "ping"},
        # 非法注册被拒绝
        {"type": "register", "host": "unknown-host", "target_id": "x"},
        {"type": "ping"},
    ]
    await run_ws(ws, user_id=7)
    types = [m.get("type") for m in ws.outbox]
    assert types[0] == "registered"
    assert "pong" in types
    assert "register_rejected" in types
    # 注册真实进了注册表（run_ws 退出时已注销）
    assert relay_service.get_connection(7, "canvas", "ws_proto") is None


# ---------- 路由层 ----------

async def _override(memory_db):
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db


async def _build_client(memory_db, user=None) -> AsyncClient:
    await _override(memory_db)
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"} if user else {}
    return AsyncClient(transport=transport, base_url="http://test", headers=headers)


@pytest_asyncio.fixture
async def owner_client(memory_db, seed_user):
    async with await _build_client(memory_db, seed_user) as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def other_client(memory_db, seed_user):
    other = User(username="other_relay", email="other_relay@example.com", password_hash="x",
                 role="user", credits=0)
    memory_db.add(other)
    await memory_db.commit()
    await memory_db.refresh(other)
    async with await _build_client(memory_db, other) as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client(memory_db):
    async with await _build_client(memory_db) as client:
        yield client
    app.dependency_overrides.clear()


async def _seed_workspace(memory_db, user) -> None:
    memory_db.add(CanvasWorkspace(id="ws_relay_1", user_id=user.id, name="t", data={}, revision=1))
    await memory_db.commit()


async def test_call_offline_when_no_executor(owner_client, memory_db, seed_user):
    await _seed_workspace(memory_db, seed_user)
    r = await owner_client.post("/api/agent/relay/call", json={
        "host": "canvas", "target_id": "ws_relay_1", "tool": "agent_apply_ops",
        "args": {"ops": [{"op": "add_panel", "name": "a"}]},
    })
    assert r.status_code == 200
    assert r.json()["data"]["routed"] == "offline"


async def test_call_rejects_unknown_host_and_tool(owner_client):
    r = await owner_client.post("/api/agent/relay/call", json={
        "host": "unknown", "target_id": "x", "tool": "agent_get_state", "args": {},
    })
    assert r.status_code == 400
    # agent_delegate 不可跨页执行（不在白名单）
    r = await owner_client.post("/api/agent/relay/call", json={
        "host": "canvas", "target_id": "x", "tool": "agent_delegate", "args": {},
    })
    assert r.status_code == 403


async def test_call_target_ownership(owner_client, other_client, memory_db, seed_user):
    await _seed_workspace(memory_db, seed_user)
    # 别人的工作区：403（存在但非本人）
    r = await other_client.post("/api/agent/relay/call", json={
        "host": "canvas", "target_id": "ws_relay_1", "tool": "agent_get_state", "args": {},
    })
    assert r.status_code == 403
    # 不存在：404
    r = await owner_client.post("/api/agent/relay/call", json={
        "host": "canvas", "target_id": "ws_missing", "tool": "agent_get_state", "args": {},
    })
    assert r.status_code == 404


async def test_call_three_state_auth(owner_client, anon_client, memory_db, seed_user):
    await _seed_workspace(memory_db, seed_user)
    body = {"host": "canvas", "target_id": "ws_relay_1", "tool": "agent_get_state", "args": {}}
    assert (await owner_client.post("/api/agent/relay/call", json=body)).status_code == 200
    assert (await anon_client.post("/api/agent/relay/call", json=body)).status_code == 401


async def test_call_editor_project_owned(memory_db, seed_user, owner_client):
    memory_db.add(EditingProject(uid="proj_relay_1", user_id=seed_user.id, title="t", document={}, revision=1))
    await memory_db.commit()
    r = await owner_client.post("/api/agent/relay/call", json={
        "host": "editor", "target_id": "proj_relay_1", "tool": "editor_apply_ops",
        "args": {"ops": []},
    })
    assert r.status_code == 200
    assert r.json()["data"]["routed"] == "offline"


async def test_targets_endpoint(owner_client, seed_user):
    conn = BridgeConnection(FakeSendWebSocket(), seed_user.id)
    await register(conn, "canvas", "ws_live")
    r = await owner_client.get("/api/agent/relay/targets")
    assert r.status_code == 200
    assert {"host": "canvas", "target_id": "ws_live"} in r.json()["data"]["targets"]
