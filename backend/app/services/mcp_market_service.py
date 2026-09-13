# =====================================================
# MCP 市场服务：官方内置目录 + 管理员自建源（URL → manifest JSON）
#
# - 安装 = 从市场项生成 mcp_servers 记录（复用 mcp_service.create_server 名称查重）
# - 源刷新：仅 http(s)、超时/大小/条数上限；事务内整源替换
# - 官方目录为后端常量，seed 幂等（按 slug upsert）
# =====================================================

import json
import logging
from datetime import datetime

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mcp_market import McpMarketItem, McpMarketSource
from app.models.mcp_server import McpServer

logger = logging.getLogger("agnes_platform")

FETCH_TIMEOUT = 15          # 源拉取超时（秒）
MAX_MANIFEST_BYTES = 2 * 1024 * 1024   # manifest 响应上限 2MB
MAX_ITEMS_PER_SOURCE = 100

CATEGORY_OFFICIAL = "官方精选"


# ---------- 官方内置目录 ----------

OFFICIAL_ITEMS: list[dict] = [
    {
        "slug": "official-filesystem",
        "name": "本地文件系统",
        "description": "让 Agent 读取/搜索/写入服务器本机自己专属目录的文件（官方 filesystem 服务器）。按用户隔离：每个用户一个独立沙箱目录。需要后端环境已安装 Node.js（npx）。",
        "category": CATEGORY_OFFICIAL,
        "transport": "stdio",
        "isolation": "per_user",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "data/mcp-ws/u_{user_id}"],
        "url": None,
        "env": {},
        "env_fields": [],
        "headers_fields": [],
        "tools_preview": ["read_file", "write_file", "list_directory", "search_files"],
    },
    {
        "slug": "official-fetch",
        "name": "网页抓取",
        "description": "让 Agent 抓取网页并转为 Markdown 供阅读总结（官方 fetch 服务器）。无状态，全站共享一个实例。需要后端环境已安装 uv/uvx（Python）。",
        "category": CATEGORY_OFFICIAL,
        "transport": "stdio",
        "isolation": "shared",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "url": None,
        "env": {},
        "env_fields": [],
        "headers_fields": [],
        "tools_preview": ["fetch"],
    },
    {
        "slug": "official-memory",
        "name": "知识记忆库",
        "description": "给 Agent 一个跨会话的知识图谱记忆（官方 memory 服务器，基于本地 JSON 持久化）。按用户隔离：每人一份独立记忆文件，互不可见。需要后端环境已安装 Node.js（npx）。",
        "category": CATEGORY_OFFICIAL,
        "transport": "stdio",
        "isolation": "per_user",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "url": None,
        "env": {"MEMORY_FILE_PATH": "data/mcp-memory/u_{user_id}.json"},
        "env_fields": [],
        "headers_fields": [],
        "tools_preview": ["create_entities", "search_nodes", "read_graph"],
    },
]


async def seed_official_items(db: AsyncSession) -> None:
    """官方目录幂等入库（启动/种子脚本调用；按 slug upsert）"""
    for item in OFFICIAL_ITEMS:
        row = (await db.execute(select(McpMarketItem).where(McpMarketItem.slug == item["slug"]))).scalar()
        payload = json.dumps(item, ensure_ascii=False)
        if row:
            row.payload = payload
            row.category = item["category"]
        else:
            db.add(McpMarketItem(source_type="official", source_id=None, slug=item["slug"], category=item["category"], payload=payload))
    await db.commit()


# ---------- 源管理 ----------

async def list_sources(db: AsyncSession) -> list[McpMarketSource]:
    return list((await db.execute(select(McpMarketSource).order_by(McpMarketSource.id))).scalars().all())


async def create_source(db: AsyncSession, name: str, url: str) -> McpMarketSource:
    if not url.startswith(("http://", "https://")):
        raise ValueError("市场源地址必须以 http(s) 开头")
    source = McpMarketSource(name=name.strip() or "未命名市场源", url=url.strip())
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


async def delete_source(db: AsyncSession, source: McpMarketSource) -> None:
    await db.execute(delete(McpMarketItem).where(McpMarketItem.source_type == "remote", McpMarketItem.source_id == source.id))
    await db.delete(source)
    await db.commit()


async def refresh_source(db: AsyncSession, source: McpMarketSource) -> int:
    """拉取 manifest 并整源替换市场项；返回条数。校验失败抛 ValueError。"""
    if not source.enabled:
        raise ValueError("市场源已停用")
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(source.url)
    if resp.status_code != 200:
        raise ValueError(f"市场源返回 {resp.status_code}")
    if len(resp.content) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest 超过 2MB 上限")
    try:
        manifest = resp.json()
    except ValueError as e:
        raise ValueError(f"manifest 不是合法 JSON：{e}")
    items = manifest.get("items") if isinstance(manifest, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError("manifest 缺少 items 数组或为空")
    if len(items) > MAX_ITEMS_PER_SOURCE:
        raise ValueError(f"items 超过 {MAX_ITEMS_PER_SOURCE} 条上限")

    cleaned: list[dict] = []
    slugs: set[str] = set()
    for raw in items:
        item = _normalize_item(raw)
        if item["slug"] in slugs:
            raise ValueError(f"slug 重复：{item['slug']}")
        slugs.add(item["slug"])
        cleaned.append(item)

    await db.execute(delete(McpMarketItem).where(McpMarketItem.source_type == "remote", McpMarketItem.source_id == source.id))
    for item in cleaned:
        db.add(McpMarketItem(source_type="remote", source_id=source.id, slug=item["slug"], category=item.get("category") or source.name, payload=json.dumps(item, ensure_ascii=False)))
    source.last_fetched_at = datetime.utcnow()
    source.item_count = len(cleaned)
    await db.commit()
    return len(cleaned)


def _normalize_item(raw) -> dict:
    """市场项守卫归一：必填 slug/name/transport，传输配置按类型校验"""
    if not isinstance(raw, dict):
        raise ValueError("items 中存在非对象条目")
    slug = str(raw.get("slug") or "").strip()
    name = str(raw.get("name") or "").strip()
    transport = raw.get("transport")
    if not slug or not name:
        raise ValueError("市场项缺少 slug 或 name")
    if transport not in ("stdio", "http"):
        raise ValueError(f"市场项 {slug} 的 transport 非法")
    if transport == "stdio" and not str(raw.get("command") or "").strip():
        raise ValueError(f"市场项 {slug} 为 stdio 但缺少 command")
    if transport == "http" and not str(raw.get("url") or "").strip():
        raise ValueError(f"市场项 {slug} 为 http 但缺少 url")
    isolation = raw.get("isolation") or "shared"
    if isolation not in ("shared", "per_user"):
        raise ValueError(f"市场项 {slug} 的 isolation 非法")
    return {
        "slug": slug,
        "name": name,
        "description": str(raw.get("description") or ""),
        "category": str(raw.get("category") or "").strip(),
        "isolation": isolation,
        "transport": transport,
        "command": str(raw.get("command") or "") or None,
        "args": [str(a) for a in raw.get("args") or []],
        "url": str(raw.get("url") or "") or None,
        "env": {str(k): str(v) for k, v in (raw.get("env") or {}).items()} if isinstance(raw.get("env"), dict) else {},
        "env_fields": [f for f in raw.get("env_fields") or [] if isinstance(f, dict) and f.get("key")],
        "headers_fields": [f for f in raw.get("headers_fields") or [] if isinstance(f, dict) and f.get("key")],
        "tools_preview": [str(t) for t in raw.get("tools_preview") or []],
    }


# ---------- 列表与安装 ----------

async def list_market_items(db: AsyncSession, q: str = "") -> list[dict]:
    """官方 + 远程市场项合并；标记 installed（mcp_servers.market_slug 命中）"""
    stmt = select(McpMarketItem).order_by(McpMarketItem.source_type, McpMarketItem.id)
    if q.strip():
        stmt = stmt.where(McpMarketItem.payload.contains(q.strip()))
    rows = (await db.execute(stmt)).scalars().all()
    installed_slugs = set((await db.execute(select(McpServer.market_slug).where(McpServer.market_slug.isnot(None)))).scalars().all())

    out: list[dict] = []
    for row in rows:
        try:
            payload = json.loads(row.payload)
        except ValueError:
            continue
        payload["slug"] = row.slug
        payload["category"] = row.category
        payload["source_type"] = row.source_type
        payload["installed"] = row.slug in installed_slugs
        out.append(payload)
    return out


async def get_market_item(db: AsyncSession, slug: str) -> McpMarketItem | None:
    return (await db.execute(select(McpMarketItem).where(McpMarketItem.slug == slug))).scalar()


async def install_item(db: AsyncSession, item: McpMarketItem, overrides: dict, secrets: dict) -> McpServer:
    """从市场项安装为 MCP 服务器：预填可被覆盖，env/headers 按声明 key 与传入值合成"""
    payload = json.loads(item.payload)
    transport = overrides.get("transport") or payload["transport"]
    fields: dict = {
        "name": str(overrides.get("name") or payload["name"]).strip(),
        "transport": transport,
        "isolation": payload.get("isolation") or "shared",
        "enabled": True,
        "market_slug": item.slug,
    }
    if transport == "stdio":
        fields["command"] = str(overrides.get("command") or payload.get("command") or "").strip()
        fields["args_json"] = json.dumps(overrides.get("args") if overrides.get("args") is not None else payload.get("args") or [], ensure_ascii=False)
        # 预置 env 模板（可含 {user_id}，网关按调用者替换）+ 安装时填写的密钥值（覆盖同名）
        env_values = {**(payload.get("env") or {}), **{k: v for k, v in (secrets.get("env") or {}).items() if v != ""}}
        fields["env_json"] = json.dumps(env_values, ensure_ascii=False) if env_values else None
        fields["url"] = None
        fields["headers_json"] = None
    else:
        fields["url"] = str(overrides.get("url") or payload.get("url") or "").strip()
        header_values = secrets.get("headers") or {}
        fields["headers_json"] = json.dumps({k: str(v) for k, v in header_values.items() if v != ""}, ensure_ascii=False) if header_values else None
        fields["command"] = None
        fields["args_json"] = None
        fields["env_json"] = None

    from app.services import mcp_service
    try:
        return await mcp_service.create_server(db, fields)
    except ValueError as e:
        raise ValueError(f"{e}（安装失败，市场项未变动）")


async def drop_items_of_source(db: AsyncSession, source_id: int) -> None:
    await db.execute(delete(McpMarketItem).where(McpMarketItem.source_type == "remote", McpMarketItem.source_id == source_id))
    await db.commit()
