# =====================================================
# MCP Server 端到端测试 —— ASGI PAT 鉴权 + stateless JSON-RPC 协议 + 工具闭环 + 档位拦截
#
# mcp_gateway.async_session 打桩为内存库（工具与 PAT 校验自开 session 的单一 patch 点）；
# mcp_session_manager 手动进入（挂载子应用 lifespan 不被 FastAPI 传播，conftest 不跑 lifespan）
# =====================================================

import json

import pytest
import pytest_asyncio
from httpx import AsyncClient
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.pat_token import PatToken
from app.models.user import User
from app.services import mcp_gateway

FULL_TOKEN = "agn_pat_full_e2e_0000000000000001"
READ_TOKEN = "agn_pat_read_e2e_0000000000000001"

JSON_HEADERS = {"Accept": "application/json, text/event-stream"}


@pytest_asyncio.fixture
async def mcp_env(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine.sync_engine, "connect")
    def _fk(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(mcp_gateway, "async_session", Session)

    async with Session() as db:
        user = User(username="mcper", email="mcp@e.com", password_hash="x", role="user", credits=100)
        db.add(user)
        await db.flush()
        db.add(PatToken(user_id=user.id, name="full", token_hash=mcp_gateway.hash_token(FULL_TOKEN), permission="full"))
        db.add(PatToken(user_id=user.id, name="read", token_hash=mcp_gateway.hash_token(READ_TOKEN), permission="readonly"))
        await db.commit()

    # 每用例独立 MCPServer + 进程内 uvicorn：session manager 的 anyio cancel scope
    # 不能跨 pytest-asyncio 的 fixture 任务进/出，交给 uvicorn lifespan 托管（也更贴近真实部署）
    import asyncio

    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Mount

    from app.core.mcp_endpoint import MCP_HTTP_PATH, PatAuthMiddleware
    from app.services.mcp_gateway import register_tools

    mcp = MCPServer(name="agnes-platform", version="1.0.0")
    register_tools(mcp)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lifespan(_app):  # 与 main.py 同款：挂载子应用的 lifespan 不被传播，手动启停
        async with mcp.session_manager.run():
            yield

    test_app = Starlette(
        routes=[
            Mount(
                "/",
                app=PatAuthMiddleware(
                    mcp.streamable_http_app(
                        streamable_http_path=MCP_HTTP_PATH,
                        json_response=True,
                        stateless_http=True,
                        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
                    )
                ),
            )
        ],
        lifespan=_lifespan,
    )
    server = uvicorn.Config(test_app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
    server = uvicorn.Server(server)
    serve_task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    async with AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=30) as client:
        yield {"client": client, "session_factory": Session}
    server.should_exit = True
    await serve_task
    await engine.dispose()


async def rpc(client: AsyncClient, token: str, id_: int, method: str, params: dict | None = None):
    payload: dict = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        payload["params"] = params
    return await client.post(
        "/mcp", json=payload, headers={"Authorization": f"Bearer {token}", **JSON_HEADERS}
    )


def unwrap(resp) -> dict:
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "result" in body, body
    return body["result"]


def tool_data(result: dict) -> dict:
    """tools/call 结果 → 工具返回的 dict（薄壳合同：永远 200 + ok 字段）"""
    return json.loads(result["content"][0]["text"])


# ---------- 鉴权层：无 token / 坏 token → 401 ----------
@pytest.mark.asyncio
async def test_missing_token_401(mcp_env):
    resp = await mcp_env["client"].post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={"Accept": "application/json"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bad_token_401(mcp_env):
    resp = await rpc(mcp_env["client"], "agn_pat_not_exist", 1, "tools/list")
    assert resp.status_code == 401


# ---------- 协议层：initialize + tools/list ----------
@pytest.mark.asyncio
async def test_initialize_and_tools_list(mcp_env):
    client = mcp_env["client"]
    init = unwrap(await rpc(client, FULL_TOKEN, 1, "initialize", {
        "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"},
    }))
    assert init["serverInfo"]["name"] == "agnes-platform"
    await client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                      headers={"Authorization": f"Bearer {FULL_TOKEN}", **JSON_HEADERS})
    tools = unwrap(await rpc(client, FULL_TOKEN, 2, "tools/list"))["tools"]
    assert {t["name"] for t in tools} == {
        "canvas_list", "canvas_create", "canvas_get_overview", "canvas_apply_ops",
    }


# ---------- 工具闭环：create → apply_ops → overview（经真实 HTTP + PAT 身份） ----------
@pytest.mark.asyncio
async def test_canvas_tool_closed_loop(mcp_env):
    client = mcp_env["client"]

    created = tool_data(unwrap(await rpc(client, FULL_TOKEN, 1, "tools/call", {
        "name": "canvas_create", "arguments": {"name": "CLI 画布"},
    })))
    assert created["ok"] is True and created["workspace"]["name"] == "CLI 画布"
    ws_id = created["workspace"]["id"]

    applied = tool_data(unwrap(await rpc(client, FULL_TOKEN, 2, "tools/call", {
        "name": "canvas_apply_ops",
        "arguments": {
            "canvas_workspace_id": ws_id,
            "ops": [
                {"op": "add_panel", "type": "text", "name": "第一幕", "content": {"content": "台词"}},
                {"op": "add_panel", "type": "image", "name": "海报"},
                {"op": "add_connection", "source_panel_id": "第一幕", "target_panel_id": "海报"},
            ],
        },
    })))
    assert applied["ok"] is True and applied["failed"] == 0 and applied["revision"] == 2

    overview = tool_data(unwrap(await rpc(client, FULL_TOKEN, 3, "tools/call", {
        "name": "canvas_get_overview", "arguments": {"canvas_workspace_id": ws_id},
    })))
    assert overview["ok"] is True and overview["panel_count"] == 2
    assert overview["panels"][0]["name"] == "第一幕" and overview["panels"][0]["summary"] == "台词"
    assert overview["connections"][0]["source"] == "第一幕"

    listing = tool_data(unwrap(await rpc(client, FULL_TOKEN, 4, "tools/call", {"name": "canvas_list", "arguments": {}})))
    assert [w["id"] for w in listing["items"]] == [ws_id]


# ---------- 档位门：readonly 调写类被拦（读类放行） ----------
@pytest.mark.asyncio
async def test_readonly_gate(mcp_env):
    client = mcp_env["client"]

    denied = tool_data(unwrap(await rpc(client, READ_TOKEN, 1, "tools/call", {
        "name": "canvas_create", "arguments": {"name": "不该被建出来"},
    })))
    assert denied["ok"] is False and "只读" in denied["error"]

    allowed = tool_data(unwrap(await rpc(client, READ_TOKEN, 2, "tools/call", {"name": "canvas_list", "arguments": {}})))
    assert allowed["ok"] is True and allowed["items"] == []  # 只读档可读，且确认上面的写没有发生
