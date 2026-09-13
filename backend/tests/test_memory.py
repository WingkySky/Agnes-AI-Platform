# =====================================================
# 用户记忆库测试：服务器定位 / 图谱解析 / 删除与清空（网关调用 mock，不依赖真实 memory 服务器）
# =====================================================

import json

import pytest

from app.models.mcp_server import McpServer
from app.services import memory_service, mcp_service


async def _seed_memory_server(db) -> McpServer:
    server = McpServer(name="知识记忆库", transport="stdio", command="npx", enabled=True,
                       market_slug=memory_service.MEMORY_SERVER_SLUG, isolation="per_user")
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


def _mock_gateway(monkeypatch, captured: list):
    async def _fake_call(server, tool, arguments, user_id=None):
        captured.append({"tool": tool, "arguments": arguments, "user_id": user_id})
        if tool == "read_graph":
            graph = {"entities": [
                {"name": "创作偏好", "type": "preference", "observations": ["画幅：竖屏 9:16", "风格：赛博朋克"]},
                {"name": "项目X", "type": "fact", "observations": ["主角叫小明"]},
            ], "relations": []}
            return {"text": json.dumps(graph, ensure_ascii=False), "is_error": False}
        return {"text": "ok", "is_error": False}

    monkeypatch.setattr(mcp_service, "call_server_tool", _fake_call)


@pytest.mark.asyncio
async def test_summary_no_server_returns_unavailable(db):
    result = await memory_service.read_preferences(db, user_id=1)
    assert result == {"available": False, "preferences": []}


@pytest.mark.asyncio
async def test_summary_extracts_preference_entity(db, monkeypatch):
    await _seed_memory_server(db)
    captured: list = []
    _mock_gateway(monkeypatch, captured)

    result = await memory_service.read_preferences(db, user_id=7)
    assert result["available"] is True
    assert result["preferences"] == ["画幅：竖屏 9:16", "风格：赛博朋克"]
    # 网关调用带用户身份（per_user 隔离）且只 read_graph
    assert captured[0]["tool"] == "read_graph"
    assert captured[0]["user_id"] == 7


@pytest.mark.asyncio
async def test_summary_survives_broken_graph(db, monkeypatch):
    await _seed_memory_server(db)

    async def _broken(server, tool, arguments, user_id=None):
        return {"text": "不是 JSON", "is_error": False}

    monkeypatch.setattr(mcp_service, "call_server_tool", _broken)
    result = await memory_service.read_preferences(db, user_id=1)
    assert result == {"available": True, "preferences": []}

    async def _boom(server, tool, arguments, user_id=None):
        raise RuntimeError("子进程挂了")

    monkeypatch.setattr(mcp_service, "call_server_tool", _boom)
    result = await memory_service.read_preferences(db, user_id=1)
    assert result == {"available": False, "preferences": []}


@pytest.mark.asyncio
async def test_delete_and_clear_routing(db, monkeypatch):
    await _seed_memory_server(db)
    captured: list = []
    _mock_gateway(monkeypatch, captured)

    done = await memory_service.delete_preference(db, user_id=7, observation="画幅：竖屏 9:16")
    assert done is True
    assert captured[-1]["tool"] == "delete_observations"
    assert captured[-1]["arguments"]["observations"] == [
        {"entityName": "创作偏好", "observations": ["画幅：竖屏 9:16"]}
    ]

    done = await memory_service.clear_preferences(db, user_id=7)
    assert done is True
    assert captured[-1]["tool"] == "delete_entities"
    assert captured[-1]["arguments"]["entityNames"] == ["创作偏好"]


@pytest.mark.asyncio
async def test_delete_without_server_returns_false(db):
    assert await memory_service.delete_preference(db, user_id=1, observation="x") is False
    assert await memory_service.clear_preferences(db, user_id=1) is False
