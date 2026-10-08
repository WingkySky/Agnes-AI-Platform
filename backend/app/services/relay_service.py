# =====================================================
# Agent 反向控制桥（Agent 一级公民批次 2）
#
# 浏览器页面（画布/剪辑器）经 WS 注册为某 (host, target_id) 的执行者；
# chat 内核等页外调用方经 POST /api/agent/relay/call 把工具调用中继到
# 该页面执行并等回执——用户实时看到 Agent 操作过程。
#
# - 纯通道：本服务不执行任何业务逻辑；离线/超时语义由路由层结构化返回
# - 同 (user_id, host, target_id) 多连接：后注册者顶替，被顶替连接收 demoted 后失能
# - 执行器白名单（与前端 lib/agent/bridge.ts 的 BRIDGE_*_TOOLS 对齐，双侧维护）：
#   canvas=页面深度工具（剔 agent_delegate——其执行体依赖内核对象，不可跨页）；
#   editor=两个写类工具（读类与页外可执行类不经桥）
# =====================================================

import asyncio
import uuid
from typing import Any, Dict, List, Optional

from fastapi import WebSocket

# 中继执行器白名单（host → 工具名清单；新增工具前后端各加一行）
BRIDGE_CANVAS_TOOLS: List[str] = [
    "agent_get_state",
    "agent_get_selection",
    "agent_get_models",
    "agent_read_image",
    "agent_apply_ops",
    "agent_create_text_node",
    "agent_select",
    "storyboard_set_style",
    "storyboard_list_styles",
    "storyboard_extract_entities",
    "storyboard_split",
    "agent_run_generation",
    "agent_stage_review",
]
BRIDGE_EDITOR_TOOLS: List[str] = [
    "editor_apply_ops",
    "editor_generate_subtitles",
]
BRIDGE_HOSTS: Dict[str, List[str]] = {
    "canvas": BRIDGE_CANVAS_TOOLS,
    "editor": BRIDGE_EDITOR_TOOLS,
}

# 中继超时分级（秒）：生成类内部含任务轮询给长窗，其余结构/查询操作短窗
RELAY_TOOL_TIMEOUTS: Dict[str, float] = {"agent_run_generation": 600.0}
RELAY_DEFAULT_TIMEOUT = 60.0


class BridgeOffline(Exception):
    """执行者连接已断开（调用方不可重试，防双执行）"""


class BridgeTimeout(Exception):
    """执行者未在窗口内回执（写操作可能已执行，调用方不可重试）"""


class BridgeConnection:
    """一条页面 WS 连接（注册后成为某 target 的执行者）"""

    def __init__(self, ws: WebSocket, user_id: int):
        self.conn_id = uuid.uuid4().hex
        self.ws = ws
        self.user_id = user_id
        self.host: str = ""
        self.target_id: str = ""
        self.superseded = False                # 被更新的连接顶替后失能
        self.send_lock = asyncio.Lock()        # WS 并发发送互斥
        self.pending: Dict[str, asyncio.Future] = {}

    async def _send(self, payload: Dict[str, Any]) -> None:
        async with self.send_lock:
            await self.ws.send_json(payload)


# (user_id, host, target_id) → conn_id；进程内注册表（单实例部署语义）
_connections: Dict[str, BridgeConnection] = {}
_target_index: Dict[tuple, str] = {}


def reset_registry() -> None:
    """测试专用：清空注册表"""
    _connections.clear()
    _target_index.clear()


def get_connection(user_id: int, host: str, target_id: str) -> Optional[BridgeConnection]:
    conn_id = _target_index.get((user_id, host, target_id))
    if not conn_id:
        return None
    conn = _connections.get(conn_id)
    if conn is None or conn.superseded:
        return None
    return conn


def list_targets(user_id: int) -> List[Dict[str, str]]:
    return [
        {"host": c.host, "target_id": c.target_id}
        for c in _connections.values()
        if c.user_id == user_id and c.host and not c.superseded
    ]


async def _demote(old: BridgeConnection) -> None:
    old.superseded = True
    try:
        await old._send({"type": "demoted"})
    except Exception:  # 旧连接可能已死，静默
        pass


async def register(conn: BridgeConnection, host: str, target_id: str) -> None:
    """注册执行者：同 target 后注册顶替（旧连接收 demoted 失能）；同连接换目标自动迁移索引"""
    key = (conn.user_id, host, target_id)
    old_id = _target_index.get(key)
    if old_id and old_id in _connections and old_id != conn.conn_id:
        await _demote(_connections[old_id])
        _connections.pop(old_id, None)
    if conn.host:
        old_key = (conn.user_id, conn.host, conn.target_id)
        if old_key != key and _target_index.get(old_key) == conn.conn_id:
            _target_index.pop(old_key, None)
    conn.host = host
    conn.target_id = target_id
    conn.superseded = False
    _connections[conn.conn_id] = conn
    _target_index[key] = conn.conn_id


def unregister(conn: BridgeConnection) -> None:
    """连接关闭：清注册并让所有在途回执落空（调用方收到 offline 语义）"""
    key = (conn.user_id, conn.host, conn.target_id)
    if _target_index.get(key) == conn.conn_id:
        _target_index.pop(key, None)
    _connections.pop(conn.conn_id, None)
    for fut in conn.pending.values():
        if not fut.done():
            fut.set_exception(BridgeOffline("执行者连接已断开"))
    conn.pending.clear()


def handle_relay_result(conn: BridgeConnection, data: Dict[str, Any]) -> bool:
    """页面回执（payload=工具结果，不透明透传）→ resolve 在途 future；返回是否命中在途调用"""
    call_id = str(data.get("call_id") or "")
    fut = conn.pending.pop(call_id, None)
    if fut is None or fut.done():
        return False
    fut.set_result(data.get("payload"))
    return True


async def relay_call(conn: BridgeConnection, tool: str, args: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    """下发工具调用并等回执；页面执行结果（AgentToolResult）原样返回"""
    if conn.superseded:
        raise BridgeOffline("执行者已被顶替")
    call_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    conn.pending[call_id] = fut
    try:
        try:
            await conn._send({"type": "relay_call", "call_id": call_id, "tool": tool, "args": args})
        except Exception as e:
            raise BridgeOffline(f"执行者连接不可用: {e}")
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            raise BridgeTimeout(f"执行者 {timeout}s 内未回执")
    finally:
        conn.pending.pop(call_id, None)


async def run_ws(ws: WebSocket, user_id: int) -> None:
    """WS 消息主循环：register / ping / relay_result 分发；断开清注册"""
    conn = BridgeConnection(ws, user_id)
    _connections[conn.conn_id] = conn
    try:
        while True:
            try:
                data = await ws.receive_json()
            except Exception:  # 断开/非 JSON 消息一律退出
                break
            if not isinstance(data, dict):
                continue
            mtype = str(data.get("type") or "")
            if mtype == "register":
                host = str(data.get("host") or "")
                target_id = str(data.get("target_id") or "")
                if host not in BRIDGE_HOSTS or not target_id:
                    await conn._send({"type": "register_rejected", "reason": "host 或 target_id 非法"})
                    continue
                await register(conn, host, target_id)
                await conn._send({"type": "registered", "host": host, "target_id": target_id})
            elif mtype == "ping":
                await conn._send({"type": "pong"})
            elif mtype == "relay_result":
                handle_relay_result(conn, data)
    finally:
        unregister(conn)
