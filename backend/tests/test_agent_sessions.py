# =====================================================
# 画布 Agent 会话同步端点测试
# 创建 → 全量同步（context + 消息行）→ 读取往返；
# 归属校验（他人 404）、未登录 401、消息全量替换幂等
# =====================================================

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import get_async_db
from app.core.security import create_access_token
from app.models.user import User

SYNC_PAYLOAD = {
    "title": "画布会话 A",
    "workspace_id": "ws-1",
    "context": {"messages": [{"role": "user", "content": "hi"}]},
    "messages": [
        {
            "role": "user",
            "content": "画一只猫",
            "attachments": [{"name": "cat.png", "base64_image": "data:image/png;base64,QQ==", "mime_type": "image/png"}],
        },
        {
            "role": "assistant",
            "content": "好的",
            "steps": [{"callId": "t1", "tool": "agent_create_text_node", "args": {}, "status": "done", "result": "{}"}],
        },
    ],
}


@pytest.mark.asyncio
async def test_agent_session_roundtrip(auth_client):
    create = await auth_client.post("/api/chat/agent-sessions", json={"title": "画布会话 A", "workspace_id": "ws-1"})
    assert create.status_code == 200
    session = create.json()["data"]
    assert session["session_type"] == "canvas"
    assert session["workspace_id"] == "ws-1"
    sid = session["id"]

    synced = await auth_client.put(f"/api/chat/agent-sessions/{sid}", json=SYNC_PAYLOAD)
    assert synced.status_code == 200

    detail = (await auth_client.get(f"/api/chat/agent-sessions/{sid}")).json()["data"]
    assert detail["context"] == SYNC_PAYLOAD["context"]
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["attachments"][0]["base64_image"].startswith("data:image/png")
    assert detail["messages"][1]["steps"][0]["tool"] == "agent_create_text_node"


@pytest.mark.asyncio
async def test_agent_session_sync_replaces_messages(auth_client):
    sid = (await auth_client.post("/api/chat/agent-sessions", json={"workspace_id": "ws-1"})).json()["data"]["id"]
    await auth_client.put(f"/api/chat/agent-sessions/{sid}", json=SYNC_PAYLOAD)

    # 第二次同步消息减半：行数应为 1（全量替换而非追加），标题保留
    payload = {**SYNC_PAYLOAD, "messages": [{"role": "user", "content": "只有一条"}]}
    await auth_client.put(f"/api/chat/agent-sessions/{sid}", json=payload)
    detail = (await auth_client.get(f"/api/chat/agent-sessions/{sid}")).json()["data"]
    assert len(detail["messages"]) == 1
    assert detail["messages"][0]["content"] == "只有一条"
    assert detail["title"] == "画布会话 A"
    assert detail["workspace_id"] == "ws-1"


@pytest.mark.asyncio
async def test_agent_session_list_marks_type(auth_client):
    await auth_client.post("/api/chat/agent-sessions", json={"workspace_id": "ws-2"})
    items = (await auth_client.get("/api/chat/sessions")).json()["data"]["items"]
    canvas = [s for s in items if s["session_type"] == "canvas"]
    assert len(canvas) == 1
    assert canvas[0]["workspace_id"] == "ws-2"


@pytest.mark.asyncio
async def test_agent_session_not_accessible_by_other_user(memory_db, auth_client):
    sid = (await auth_client.post("/api/chat/agent-sessions", json={"workspace_id": "ws-1"})).json()["data"]["id"]

    other = User(username="other", email="other@example.com", password_hash="x", role="user", credits=0)
    memory_db.add(other)
    await memory_db.commit()
    await memory_db.refresh(other)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client2:
        client2.headers["Authorization"] = f"Bearer {create_access_token(other.id)}"
        assert (await client2.get(f"/api/chat/agent-sessions/{sid}")).status_code == 404
        assert (await client2.put(f"/api/chat/agent-sessions/{sid}", json=SYNC_PAYLOAD)).status_code == 404


@pytest.mark.asyncio
async def test_agent_session_requires_login():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        assert (await anon.post("/api/chat/agent-sessions", json={"workspace_id": "ws-1"})).status_code == 401
        assert (await anon.get("/api/chat/agent-sessions/1")).status_code == 401


@pytest.mark.asyncio
async def test_chat_type_session_sync_via_agent_channel(auth_client):
    """三期内核统一：对话页（session_type=chat）会话同样走 agent-sessions 全量同步通道"""
    create = await auth_client.post("/api/chat/sessions", json={})
    assert create.status_code == 200
    sid = create.json()["data"]["id"]
    assert create.json()["data"]["session_type"] == "chat"

    synced = await auth_client.put(f"/api/chat/agent-sessions/{sid}", json=SYNC_PAYLOAD)
    assert synced.status_code == 200

    detail = (await auth_client.get(f"/api/chat/agent-sessions/{sid}")).json()["data"]
    assert detail["context"] == SYNC_PAYLOAD["context"]
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["steps"][0]["tool"] == "agent_create_text_node"
