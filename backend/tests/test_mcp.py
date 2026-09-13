# =====================================================
# MCP 桥测试：脱敏 / CRUD 语义 / transport 校验 / 鉴权 / 连接缓存指纹
# （不依赖真实 MCP 服务器：连接行为通过 mock 与指纹逻辑覆盖）
# =====================================================

import json

import pytest

from app.core.security import create_access_token
from app.models.mcp_server import McpServer
from app.models.user import User
from app.services import mcp_service


# ---------- 模型脱敏 ----------

@pytest.mark.asyncio
async def test_to_safe_dict_masks_secrets(db):
    server = McpServer(
        name="fs", transport="stdio", command="npx",
        args_json=json.dumps(["-y", "@modelcontextprotocol/server-filesystem"]),
        env_json=json.dumps({"HOME": "/tmp", "TOKEN": "secret-value"}),
        url=None, headers_json=None,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)

    data = server.to_safe_dict()
    assert data["env_keys"] == {"HOME": True, "TOKEN": True}
    # 值永不出后端
    assert "secret-value" not in json.dumps(data)
    assert data["args"] == ["-y", "@modelcontextprotocol/server-filesystem"]


# ---------- transport 校验 ----------

def test_upsert_rejects_bad_transport():
    from app.routes.mcp import McpServerUpsert
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        McpServerUpsert(name="x", transport="websocket")
    # stdio 缺 command 在 transport_fields 校验
    with pytest.raises(ValueError, match="启动命令"):
        McpServerUpsert(name="x", transport="stdio").transport_fields()
    body = McpServerUpsert(name="x", transport="stdio", command="npx")
    assert body.transport_fields()["args_json"] == "[]"


def test_upsert_requires_url_for_http():
    from app.routes.mcp import McpServerUpsert
    with pytest.raises(ValueError, match="服务器地址"):
        McpServerUpsert(name="x", transport="http").transport_fields()


# ---------- CRUD 语义 ----------

@pytest.mark.asyncio
async def test_create_duplicate_name_rejected(db):
    db.add(McpServer(name="dup", transport="http", url="http://x"))
    await db.commit()
    with pytest.raises(ValueError, match="已存在"):
        await mcp_service.create_server(db, {"name": "dup", "transport": "http", "url": "http://y"})


@pytest.mark.asyncio
async def test_update_preserves_secret_when_absent(db):
    server = McpServer(name="api", transport="http", url="http://x",
                       headers_json=json.dumps({"Authorization": "Bearer k"}))
    db.add(server)
    await db.commit()
    await db.refresh(server)

    # 更新未传 headers（None）→ 保留原值；传 {} → 清空
    from app.routes.mcp import McpServerUpsert
    body = McpServerUpsert(name="api", transport="http", url="http://x2")
    fields = {"name": body.name, "transport": body.transport, "enabled": body.enabled, **body.transport_fields()}
    await mcp_service.update_server(db, server, fields)
    await db.refresh(server)
    assert json.loads(server.headers_json) == {"Authorization": "Bearer k"}

    body2 = McpServerUpsert(name="api", transport="http", url="http://x3", headers={})
    fields2 = {"name": body2.name, "transport": body2.transport, "enabled": True, **body2.transport_fields()}
    await mcp_service.update_server(db, server, fields2)
    await db.refresh(server)
    assert json.loads(server.headers_json) == {}


@pytest.mark.asyncio
async def test_delete_drops_session(db):
    server = McpServer(name="gone", transport="http", url="http://x")
    db.add(server)
    await db.commit()
    await db.refresh(server)
    # 预置缓存连接 → 删除后应被回收
    mcp_service._sessions[(server.id, None)] = mcp_service._ServerSession(server)
    await mcp_service.delete_server(db, server)
    assert server.id not in mcp_service._sessions


# ---------- 连接缓存指纹 ----------

def test_fingerprint_rebuild_on_config_change():
    a = McpServer(id=1, name="s", transport="http", url="http://x")
    b = McpServer(id=1, name="s", transport="http", url="http://y")
    assert mcp_service._config_fingerprint(a) != mcp_service._config_fingerprint(b)


@pytest.mark.asyncio
async def test_get_session_reuses_and_rebuilds():
    s1 = McpServer(id=9, name="s", transport="http", url="http://x")
    conn1 = mcp_service._get_session(s1)
    assert mcp_service._get_session(s1) is conn1  # 同配置复用
    s2 = McpServer(id=9, name="s", transport="http", url="http://y")
    conn2 = mcp_service._get_session(s2)
    assert conn2 is not conn1  # 配置变更重建
    await conn1.close()
    await conn2.close()
    mcp_service._sessions.pop((9, None), None)


# ---------- 多用户隔离 ----------

def test_session_key_isolation():
    shared = McpServer(id=1, name="s", transport="http", url="http://x")  # isolation 未设 → shared
    per_user = McpServer(id=2, name="m", transport="stdio", command="npx", isolation="per_user")

    assert mcp_service._session_key(shared, 7) == (1, None)          # shared 不按用户分
    assert mcp_service._session_key(per_user, 7) == (2, 7)
    with pytest.raises(ValueError, match="用户身份"):
        mcp_service._session_key(per_user, None)


def test_get_session_distinct_instances_per_user():
    per_user = McpServer(id=3, name="m", transport="http", url="http://x", isolation="per_user")
    c1 = mcp_service._get_session(per_user, 1)
    c2 = mcp_service._get_session(per_user, 2)
    c1_again = mcp_service._get_session(per_user, 1)
    assert c1 is not c2 and c1 is c1_again
    # shared 同配置跨用户同实例
    shared = McpServer(id=4, name="f", transport="http", url="http://x")
    assert mcp_service._get_session(shared, 1) is mcp_service._get_session(shared, 2)


def test_apply_user_template():
    per_user = McpServer(id=5, name="m", transport="stdio", command="npx", isolation="per_user")
    conn = mcp_service._ServerSession(per_user, 42)
    assert conn._apply_user_template("data/mcp-memory/u_{user_id}.json") == "data/mcp-memory/u_42.json"
    assert conn._apply_user_template("no-template") == "no-template"
    shared_conn = mcp_service._ServerSession(shared := McpServer(id=6, name="f", transport="http", url="http://x"))
    assert shared_conn._apply_user_template("data/u_{user_id}.json") == "data/u_{user_id}.json"  # shared 不替换


# ---------- 路由鉴权与调用守卫 ----------

@pytest.mark.asyncio
async def test_servers_require_admin(auth_client):
    resp = await auth_client.get("/api/mcp/servers")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_call_missing_or_disabled_server_404(auth_client, db):
    db.add(McpServer(name="off", transport="http", url="http://x", enabled=False))
    await db.commit()
    resp = await auth_client.post("/api/mcp/call", json={"server_id": 999, "tool": "t"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_manage_servers(auth_client, db, seed_user, monkeypatch):
    admin = User(username="mcpadmin", email="mcpadmin@example.com", password_hash="x",
                 role="admin", is_admin=True)
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    auth_client.headers["Authorization"] = f"Bearer {create_access_token(admin.id)}"

    # 创建（stdio，含 env）
    resp = await auth_client.post("/api/mcp/servers", json={
        "name": "fs", "transport": "stdio", "command": "npx",
        "args": ["-y", "server-fs"], "env": {"TOKEN": "k"},
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["env_keys"] == {"TOKEN": True}
    server_id = data["id"]

    # 连接测试：mock 掉真实连接
    async def _fake_tools(server, user_id=None):
        return [{"name": "read_file", "description": "d", "input_schema": {"type": "object"}}]

    monkeypatch.setattr(mcp_service, "list_server_tools", _fake_tools)
    resp = await auth_client.post(f"/api/mcp/servers/{server_id}/test")
    assert resp.status_code == 200
    assert resp.json()["data"]["tools"][0]["name"] == "read_file"

    # 列表/删除
    resp = await auth_client.get("/api/mcp/servers")
    assert resp.status_code == 200 and len(resp.json()["data"]) == 1
    resp = await auth_client.delete(f"/api/mcp/servers/{server_id}")
    assert resp.status_code == 200
