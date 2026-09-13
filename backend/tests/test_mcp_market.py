# =====================================================
# MCP 市场测试：官方 seed 幂等 / 源刷新整源替换 / manifest 校验 / install 合成与查重
# =====================================================

import json

import httpx
import pytest

from app.models.mcp_market import McpMarketItem, McpMarketSource
from app.services import mcp_market_service


def _manifest(items: list[dict]) -> dict:
    return {"name": "测试市场", "items": items}


VALID_ITEM = {
    "slug": "team-tools",
    "name": "团队工具",
    "description": "内部工具集",
    "category": "内部",
    "transport": "http",
    "url": "https://mcp.internal.example/sse",
    "headers_fields": [{"key": "Authorization", "description": "Bearer token", "required": True}],
    "tools_preview": ["do_thing"],
}


@pytest.mark.asyncio
async def test_seed_official_items_idempotent(db):
    await mcp_market_service.seed_official_items(db)
    await mcp_market_service.seed_official_items(db)
    rows = (await db.execute(db_query_official())).scalars().all()
    assert len(rows) == len(mcp_market_service.OFFICIAL_ITEMS)
    slugs = {r.slug for r in rows}
    assert "official-filesystem" in slugs and "official-fetch" in slugs


def db_query_official():
    from sqlalchemy import select
    return select(McpMarketItem).where(McpMarketItem.source_type == "official")


@pytest.mark.asyncio
async def test_refresh_replaces_source_items(db, monkeypatch):
    await mcp_market_service.seed_official_items(db)
    source = await mcp_market_service.create_source(db, "内部市场", "https://market.example/manifest.json")

    async def _fake_get(self, url):
        return httpx.Response(200, json=_manifest([VALID_ITEM, {**VALID_ITEM, "slug": "team-tools-2", "name": "工具2"}]), request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    count = await mcp_market_service.refresh_source(db, source)
    assert count == 2
    assert source.item_count == 2

    # 再次刷新（只回 1 条）→ 整源替换，不残留
    async def _fake_get_single(self, url):
        return httpx.Response(200, json=_manifest([VALID_ITEM]), request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get_single)
    count = await mcp_market_service.refresh_source(db, source)
    assert count == 1
    items = await mcp_market_service.list_market_items(db)
    slugs = [i["slug"] for i in items]
    assert "team-tools" in slugs and "team-tools-2" not in slugs
    # 官方项也在合并列表里且标 installed=False
    official = [i for i in items if i["source_type"] == "official"]
    assert official and all(i["installed"] is False for i in official)


@pytest.mark.asyncio
async def test_refresh_rejects_bad_manifest(db, monkeypatch):
    source = await mcp_market_service.create_source(db, "坏源", "https://bad.example/manifest.json")

    async def _no_items(self, url):
        return httpx.Response(200, json={"foo": 1}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", _no_items)
    with pytest.raises(ValueError, match="items"):
        await mcp_market_service.refresh_source(db, source)

    async def _bad_transport(self, url):
        return httpx.Response(200, json=_manifest([{**VALID_ITEM, "slug": "x", "transport": "websocket"}]), request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", _bad_transport)
    with pytest.raises(ValueError, match="transport"):
        await mcp_market_service.refresh_source(db, source)

    async def _http_url_source(self, url):
        return httpx.Response(200, json=_manifest([{**VALID_ITEM, "slug": "y", "transport": "http", "url": ""}]), request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", _http_url_source)
    with pytest.raises(ValueError, match="url"):
        await mcp_market_service.refresh_source(db, source)


@pytest.mark.asyncio
async def test_create_source_rejects_non_http(db):
    with pytest.raises(ValueError, match="http"):
        await mcp_market_service.create_source(db, "本地", "file:///etc/passwd")


@pytest.mark.asyncio
async def test_install_composes_fields_and_marks_slug(db):
    item = McpMarketItem(source_type="official", source_id=None, slug="official-memory", category="官方精选",
                         payload=json.dumps(mcp_market_service.OFFICIAL_ITEMS[2]))
    db.add(item)
    await db.commit()
    await db.refresh(item)

    server = await mcp_market_service.install_item(
        db, item,
        overrides={"name": "我的记忆库"},
        secrets={"env": {"MEMORY_FILE_PATH": "/data/memory.json", "EMPTY": ""}},
    )
    assert server.market_slug == "official-memory"
    assert server.name == "我的记忆库"
    assert json.loads(server.env_json) == {"MEMORY_FILE_PATH": "/data/memory.json"}  # 空值剔除
    assert server.command == "npx"

    # 已安装标记出现在市场列表
    items = await mcp_market_service.list_market_items(db)
    hit = [i for i in items if i["slug"] == "official-memory"][0]
    assert hit["installed"] is True

    # 重名再装被拒
    from app.models.mcp_server import McpServer  # noqa: F401
    with pytest.raises(ValueError, match="已存在"):
        await mcp_market_service.install_item(db, item, overrides={"name": "我的记忆库"}, secrets={})
