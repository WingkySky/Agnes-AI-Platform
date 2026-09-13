# =====================================================
# MCP 网关服务（stdio / streamable HTTP 双传输）
#
# - 官方 mcp SDK（async）；连接按 server id 缓存，配置变更或进程退出后失效重建
# - 每个连接一个 owner task 持有客户端上下文（anyio cancel scope 约束：上下文必须
#   在进入它的任务里退出），请求从其他任务直接走 session（asyncio 原语，任务无关）
# - 调用失败即报错不做守护重启（下次调用按需重建）；env/headers 值只存服务端
# =====================================================

import asyncio
import json
import logging
import os
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mcp_server import McpServer

logger = logging.getLogger("agnes_platform")

# 连接/调用超时（秒）
CONNECT_TIMEOUT = 30
CALL_TIMEOUT = 120
IDLE_TTL_SECONDS = 600      # per_user 实例空闲回收阈值（秒）


def _config_fingerprint(server: McpServer) -> str:
    """配置指纹：任一连接相关字段变更即触发重建"""
    return "|".join([
        server.transport or "",
        server.command or "",
        server.args_json or "",
        server.env_json or "",
        server.url or "",
        server.headers_json or "",
        str(server.updated_at or ""),
    ])


class _ServerSession:
    """单服务器连接：owner task 进入客户端上下文并保持，暴露 list_tools / call_tool"""

    def __init__(self, server: McpServer, user_id: int | None = None):
        self._server = server
        self.user_id = user_id          # per_user 实例所属用户；shared 恒为 None
        self.last_used = time.monotonic()
        self._task: asyncio.Task | None = None
        self._session = None
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._error: str | None = None
        self.fingerprint = _config_fingerprint(server)

    def _apply_user_template(self, value: str | None) -> str | None:
        """配置模板替换：{user_id} → 实例所属用户 id（shared 实例无用户上下文，原样返回）"""
        if value is None or self.user_id is None or "{user_id}" not in value:
            return value
        return value.replace("{user_id}", str(int(self.user_id)))

    # ---------- 生命周期 ----------

    async def ensure(self) -> None:
        """按需启动并等待就绪；连接死亡/出错时重建"""
        self.last_used = time.monotonic()
        if self._task is None or self._task.done():
            self._session = None
            self._error = None
            self._ready = asyncio.Event()
            self._stop = asyncio.Event()
            self._task = asyncio.create_task(self._run())
        if not self._ready.is_set():
            try:
                await asyncio.wait_for(self._ready.wait(), timeout=CONNECT_TIMEOUT)
            except asyncio.TimeoutError:
                await self.close()
                raise RuntimeError("MCP 服务器连接超时")
        if self._error:
            raise RuntimeError(f"MCP 服务器连接失败：{self._error}")

    async def _run(self) -> None:
        """owner task：进入传输与客户端上下文，初始化后保持到 stop。
        SDK 导入放 try 内：导入失败（版本不匹配）转为可读连接错误而非超时。"""
        try:
            import contextlib

            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

            extra_client = None
            if self._server.transport == "stdio":
                args = [self._apply_user_template(a) for a in McpServer.parse_json(self._server.args_json, [])]
                env = {k: self._apply_user_template(v) for k, v in (McpServer.parse_json(self._server.env_json, None) or {}).items()}
                if self.user_id is not None:
                    _ensure_user_dirs(args + list(env.values()))
                params = StdioServerParameters(
                    command=self._apply_user_template(self._server.command) or "",
                    args=args,
                    env=env or None,  # 空 {} 视为默认环境（保留 PATH）
                )
                streams_ctx = stdio_client(params)
            else:
                url = self._apply_user_template(self._server.url)
                headers = {k: self._apply_user_template(v) for k, v in (McpServer.parse_json(self._server.headers_json, None) or {}).items()}
                # mcp 2.x：headers 经自建 httpx 客户端传入，且自建客户端由本任务管理生命周期
                extra_client = create_mcp_http_client(headers=headers) if headers else None
                streams_ctx = streamable_http_client(url or "", http_client=extra_client)

            async with contextlib.AsyncExitStack() as stack:
                if extra_client is not None:
                    await stack.enter_async_context(extra_client)
                async with streams_ctx as streams:
                    read, write = streams[0], streams[1]
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        self._session = session
                        self._ready.set()
                        await self._stop.wait()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 —— 传输/初始化/导入失败统一转可读错误
            self._error = str(e)
            self._ready.set()

    async def close(self) -> None:
        self._stop.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 —— 关闭路径吞异常
                pass
        self._task = None
        self._session = None

    # ---------- 能力 ----------

    async def list_tools(self) -> list[dict]:
        await self.ensure()
        result = await asyncio.wait_for(self._session.list_tools(), timeout=CALL_TIMEOUT)
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {},
            }
            for tool in result.tools
        ]

    async def call_tool(self, name: str, arguments: dict | None) -> dict:
        await self.ensure()
        result = await asyncio.wait_for(self._session.call_tool(name, arguments or {}), timeout=CALL_TIMEOUT)
        # MCP 结果统一转文本（content 块拼接）；结构化输出放 data 字段
        texts: list[str] = []
        for block in getattr(result, "content", None) or []:
            block_text = getattr(block, "text", None)
            if isinstance(block_text, str):
                texts.append(block_text)
        return {
            "text": "\n".join(texts),
            "is_error": bool(getattr(result, "isError", False)),
        }


# ---------- 连接缓存（进程级） ----------

_sessions: dict[tuple[int, int | None], _ServerSession] = {}


def _session_key(server: McpServer, user_id: int | None) -> tuple[int, int | None]:
    """连接键：per_user 服务器按 (server_id, user_id) 隔离实例；shared 全局一个"""
    if (server.isolation or "shared") == "per_user":
        if user_id is None:
            raise ValueError("per_user 服务器必须携带用户身份")
        return (server.id, int(user_id))
    return (server.id, None)


def _sweep_idle_sessions() -> None:
    """回收长时间空闲的 per_user 实例（子进程数随用户增长需收敛）；shared 实例常驻不清"""
    now = time.monotonic()
    for key, conn in list(_sessions.items()):
        if key[1] is not None and now - conn.last_used > IDLE_TTL_SECONDS:
            _sessions.pop(key, None)
            asyncio.get_running_loop().create_task(conn.close())


def _get_session(server: McpServer, user_id: int | None = None) -> _ServerSession:
    """按连接键取实例；配置指纹变更或不存在时重建（旧连接异步回收）"""
    key = _session_key(server, user_id)
    old = _sessions.get(key)
    if old and old.fingerprint != _config_fingerprint(server):
        asyncio.get_running_loop().create_task(old.close())
        old = None
    if old is None:
        _sweep_idle_sessions()
        old = _ServerSession(server, key[1])
        _sessions[key] = old
    return old


# 工具清单缓存：{server_id: (fingerprint, tools)}，避免每次会话建立都拉起 stdio 子进程
_tools_cache: dict[int, tuple[str, list[dict]]] = {}


async def agent_tools(db: AsyncSession) -> list[dict]:
    """聚合启用服务器的工具清单（登录用户；单服务器失败跳过不阻塞整体）"""
    out: list[dict] = []
    for server in await list_servers(db, enabled_only=True):
        fp = _config_fingerprint(server)
        cached = _tools_cache.get(server.id)
        if cached and cached[0] == fp:
            tools = cached[1]
        else:
            try:
                tools = await _get_session(server).list_tools()
                _tools_cache[server.id] = (fp, tools)
            except Exception as e:  # noqa: BLE001 —— 单服务器故障不影响其余工具注入
                logger.warning("MCP 服务器「%s」工具清单获取失败：%s", server.name, e)
                _tools_cache.pop(server.id, None)
                continue
        out.append({"server_id": server.id, "server_name": server.name, "tools": tools})
    return out


async def drop_session(server_id: int) -> None:
    """服务器删除/停用时显式回收全部连接并失效工具缓存"""
    _tools_cache.pop(server_id, None)
    for key in [k for k in _sessions if k[0] == server_id]:
        session = _sessions.pop(key, None)
        if session:
            await session.close()


# ---------- 数据访问与对外接口 ----------

async def list_servers(db: AsyncSession, enabled_only: bool = False) -> list[McpServer]:
    stmt = select(McpServer).order_by(McpServer.id)
    if enabled_only:
        stmt = stmt.where(McpServer.enabled == True)  # noqa: E712
    return list((await db.execute(stmt)).scalars().all())


async def get_server(db: AsyncSession, server_id: int) -> McpServer | None:
    return await db.get(McpServer, server_id)


async def create_server(db: AsyncSession, fields: dict) -> McpServer:
    if fields.get("name") and await _name_taken(db, fields["name"]):
        raise ValueError(f"服务器名称「{fields['name']}」已存在")
    server = McpServer(**fields)
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


async def update_server(db: AsyncSession, server: McpServer, fields: dict) -> McpServer:
    name = fields.get("name")
    if name and name != server.name and await _name_taken(db, name):
        raise ValueError(f"服务器名称「{name}」已存在")
    for key, value in fields.items():
        setattr(server, key, value)
    server.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(server)
    return server


async def delete_server(db: AsyncSession, server: McpServer) -> None:
    await drop_session(server.id)
    await db.delete(server)
    await db.commit()


async def _name_taken(db: AsyncSession, name: str) -> bool:
    row = await db.execute(select(McpServer.id).where(McpServer.name == name))
    return row.scalar() is not None


async def list_server_tools(server: McpServer, user_id: int | None = None) -> list[dict]:
    """连接测试 / 工具清单（不含调用）；per_user 服务器以发起人身份出实例"""
    return await _get_session(server, user_id).list_tools()


async def call_server_tool(server: McpServer, tool: str, arguments: dict | None, user_id: int | None = None) -> dict:
    """Agent 调用入口（BFF /api/mcp/call）；per_user 服务器按调用者隔离实例"""
    return await _get_session(server, user_id).call_tool(tool, arguments)


def _ensure_user_dirs(values: list[str | None]) -> None:
    """per_user 实例路径自举：替换后的相对路径自动建目录（无扩展名视为目录本身，
    有扩展名视为文件、建其父目录），避免官方 memory/filesystem 项因目录缺失启动失败"""
    for raw in values:
        if not raw or "://" in raw:
            continue
        base = os.path.basename(raw)
        target = os.path.dirname(raw) if "." in base else raw
        if target:
            try:
                os.makedirs(target, exist_ok=True)
            except OSError:
                pass  # 路径不可建目录时交由服务器自身报错，不阻断连接


def dump_json(value, fallback: str) -> str:
    """请求里的 args/env/headers 对象 → JSON 字符串（入库存储用）"""
    if value is None:
        return fallback
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return fallback
