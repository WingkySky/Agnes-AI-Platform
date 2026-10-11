# =====================================================
# MCP Server 网关 —— 外部 Agent/CLI 经 PAT 接入的工具层
#
# - PAT 鉴权：hash_token/new_token + authenticate_pat（明文不落库，吊销即时生效，
#   last_used_at 节流 60s 防高频写库）
# - 身份传递：ASGI 中间件（core/mcp_endpoint）校验后写入 ContextVar，工具内读取
# - 工具面：外部语义的资源型工具（显式 workspace_id，无页面态），v1 先画布 4 件；
#   impl 函数与 register_tools 薄壳分离，impl 可直测（db + user_id 注入）
# - 写类工具按 PAT 档位拦截：readonly 拒绝 / full 直通（人工确认发生在
#   外部 agent 自己的交互层，平台侧无确认卡可弹）
# =====================================================

import hashlib
import math
import secrets
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import async_session
from app.models.pat_token import PatToken
from app.services.canvas_workspace_service import (
    apply_workspace_ops,
    create_workspace,
    get_owned_workspace,
    list_workspaces,
)

# last_used_at 更新节流（秒）
_LAST_USED_THROTTLE_SEC = 60
TOKEN_PREFIX = "agn_pat_"


# =====================================================
# PAT 令牌材料与鉴权
# =====================================================

def new_token() -> str:
    """生成明文 PAT（仅创建响应返回一次；secrets CSPRNG）"""
    return f"{TOKEN_PREFIX}{secrets.token_hex(16)}"


def hash_token(plain: str) -> str:
    """明文 → sha256 hex（落库形态）"""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


@dataclass
class PatPrincipal:
    """PAT 解析出的请求身份（等价于登录用户 + 档位）"""

    user_id: int
    permission: str  # readonly | full
    token_id: int


async def authenticate_pat(db: AsyncSession, token: str) -> Optional[PatPrincipal]:
    """校验 Bearer token → PatPrincipal；无效/已吊销返回 None（每次实时查表，吊销即时生效）"""
    if not token or not token.startswith(TOKEN_PREFIX):
        return None
    row = (
        await db.scalars(
            select(PatToken).where(PatToken.token_hash == hash_token(token), PatToken.revoked_at.is_(None))
        )
    ).first()
    if not row:
        return None
    now = datetime.utcnow()
    if row.last_used_at is None or (now - row.last_used_at).total_seconds() >= _LAST_USED_THROTTLE_SEC:
        row.last_used_at = now
        await db.commit()
    return PatPrincipal(user_id=row.user_id, permission=row.permission, token_id=row.id)


async def authenticate_request(token: str) -> Optional[PatPrincipal]:
    """开独立 session 完成校验（ASGI 鉴权层无请求级 session 可注入；测试 monkeypatch async_session 打桩）"""
    async with async_session() as db:
        return await authenticate_pat(db, token)


# ASGI 中间件注入、工具函数读取的请求身份
pat_principal: ContextVar[Optional[PatPrincipal]] = ContextVar("pat_principal", default=None)


# =====================================================
# overview 分页纯函数（与前端 chat-tools.ts overviewPage/panelContentSummary 对齐）
# =====================================================

def parse_overview_cursor(cursor: Optional[str]) -> int:
    """游标 → 起始索引（非法/负值回退 0）"""
    if not cursor:
        return 0
    try:
        n = int(cursor)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def overview_page(panels: List[Dict[str, Any]], cursor: Optional[str], page_size: Optional[int]) -> Dict[str, Any]:
    """面板分页：size 钳 10~100（缺省 60）；游标越过末尾视为画布已收缩，回第一页重读"""
    size = math.floor(page_size) if isinstance(page_size, (int, float)) else 0
    size = min(100, max(10, size or 60))
    raw = parse_overview_cursor(cursor)
    start = raw if raw < len(panels) else 0
    end = min(len(panels), start + size)
    result: Dict[str, Any] = {
        "items": panels[start:end],
        "page_range": [start, end],
        "total": len(panels),
    }
    if end < len(panels):
        result["next_cursor"] = str(end)
    return result


def _truncate(s: str, n: int = 120) -> str:
    return f"{s[:n]}…" if len(s) > n else s


def panel_content_summary(p: Dict[str, Any]) -> str:
    """节点内容摘要：文本取正文；媒体取状态+prompt；有二进制内容标注「有媒体内容」"""
    content = p.get("content") if isinstance(p.get("content"), dict) else {}
    ptype = p.get("type") if isinstance(p.get("type"), str) else "text"
    if ptype == "text":
        body = content.get("content")
        return _truncate(body) if isinstance(body, str) else ""
    parts: List[str] = []
    if isinstance(content.get("status"), str):
        parts.append(f"status={content['status']}")
    if isinstance(content.get("prompt"), str) and content.get("prompt"):
        parts.append(f"prompt={_truncate(content['prompt'], 60)}")
    if isinstance(content.get("content"), str) and content.get("content"):
        parts.append("有媒体内容")
    return " ".join(parts)


# =====================================================
# 工具实现（db + user_id 注入，可直测）
# =====================================================

def _brief(ws) -> Dict[str, Any]:
    return {
        "id": ws.id,
        "name": ws.name,
        "work_id": ws.work_id,
        "revision": ws.revision,
        "updated_at": ws.updated_at.isoformat() if ws.updated_at else None,
    }


async def canvas_list_impl(db: AsyncSession, user_id: int) -> Dict[str, Any]:
    items = await list_workspaces(db, user_id)
    return {"ok": True, "items": [_brief(w) for w in items]}


async def canvas_create_impl(db: AsyncSession, user_id: int, name: Optional[str]) -> Dict[str, Any]:
    ws = await create_workspace(db, user_id, name or f"外部画布 {datetime.utcnow():%Y-%m-%d %H:%M}")
    return {"ok": True, "workspace": _brief(ws)}


async def canvas_overview_impl(
    db: AsyncSession, user_id: int, workspace_id: str, cursor: Optional[str], page_size: Optional[int]
) -> Dict[str, Any]:
    ws = await get_owned_workspace(db, workspace_id, user_id)
    data = ws.data if isinstance(ws.data, dict) else {}
    panels = data.get("panels") if isinstance(data.get("panels"), list) else []
    connections = data.get("connections") if isinstance(data.get("connections"), list) else []

    def name_of(pid: Any) -> str:
        for p in panels:
            if p.get("id") == pid:
                return str(p.get("name") or p.get("id") or pid)
        return str(pid if pid is not None else "")

    page = overview_page(panels, cursor, page_size)
    page_ids = {str(p.get("id")) for p in page["items"]}
    page_connections = [
        c for c in connections
        if str(c.get("source_panel_id")) in page_ids or str(c.get("target_panel_id")) in page_ids
    ]
    result: Dict[str, Any] = {
        "ok": True,
        "workspace_id": ws.id,
        "name": ws.name,
        "panel_count": page["total"],
        "panels": [
            {
                "id": p.get("id"),
                "type": p.get("type") if isinstance(p.get("type"), str) else "text",
                "name": p.get("name") if isinstance(p.get("name"), str) else "",
                "x": p.get("x"),
                "y": p.get("y"),
                "summary": panel_content_summary(p),
            }
            for p in page["items"]
        ],
        "connections": [
            {"id": c.get("id"), "source": name_of(c.get("source_panel_id")), "target": name_of(c.get("target_panel_id"))}
            for c in page_connections
        ],
    }
    if "next_cursor" in page:
        lo, hi = page["page_range"]
        result["next_cursor"] = page["next_cursor"]
        result["note"] = f"本页第 {lo + 1}~{hi} / 共 {page['total']} 个节点；还需要更多节点时把 cursor=\"{page['next_cursor']}\" 传回继续读"
    return result


async def canvas_apply_ops_impl(
    db: AsyncSession, user_id: int, workspace_id: str, ops: List[Dict[str, Any]]
) -> Dict[str, Any]:
    ws = await get_owned_workspace(db, workspace_id, user_id)
    outcome = await apply_workspace_ops(db, ws, ops)
    return {"ok": True, **outcome}


# =====================================================
# 工具注册（薄壳：取 PAT 身份 → 档位门 → 开 session → impl → 错误合同）
# =====================================================

def _principal() -> PatPrincipal:
    principal = pat_principal.get()
    if principal is None:
        raise RuntimeError("PAT 身份上下文缺失（应仅出现在绕过 ASGI 鉴权层的调用）")
    return principal


def _tool_error(e: Exception) -> Dict[str, Any]:
    if isinstance(e, HTTPException):
        detail = e.detail
        if isinstance(detail, dict):
            extra = {k: v for k, v in detail.items() if k != "message"}
            return {"ok": False, "error": str(detail.get("message") or "请求失败"), **extra}
        return {"ok": False, "error": str(detail or "请求失败")}
    return {"ok": False, "error": str(e)}


def _denied(principal: PatPrincipal, write: bool) -> Optional[str]:
    if write and principal.permission != "full":
        return "令牌为只读档（readonly），无权执行写操作；请在个人资料页换用 full 档令牌"
    return None


CANVAS_LIST_DESC = "列出用户的云端画布工作区（id/名称/所属作品/版本/更新时间）。操作画布前先调用确定目标工作区 id。"


def register_tools(mcp) -> None:
    """把外部工具面注册到 MCPServer 实例（core/mcp_endpoint 装配时调用）"""

    @mcp.tool(name="canvas_list", description=CANVAS_LIST_DESC)
    async def canvas_list() -> Dict[str, Any]:
        principal = _principal()
        try:
            async with async_session() as db:
                return await canvas_list_impl(db, principal.user_id)
        except Exception as e:
            return _tool_error(e)

    @mcp.tool(name="canvas_create", description="新建云端画布工作区，返回新工作区 id。name 缺省自动命名。")
    async def canvas_create(
        name: Annotated[Optional[str], Field(description="画布名称")] = None,
    ) -> Dict[str, Any]:
        principal = _principal()
        denied = _denied(principal, write=True)
        if denied:
            return {"ok": False, "error": denied}
        try:
            async with async_session() as db:
                return await canvas_create_impl(db, principal.user_id, name)
        except Exception as e:
            return _tool_error(e)

    @mcp.tool(
        name="canvas_get_overview",
        description=(
            "读取云端画布工作区概要：节点（id/类型/名称/坐标/内容摘要）与连线关系（按名称标注上下游）。"
            "引用已有节点/连线或回答画布内容问题前先调用；不返回图片/视频的二进制内容。"
            "大画布分页读取：响应含 next_cursor 且还需要更多节点时，把 cursor=next_cursor 传回继续读；每页只带与当页节点相关的连线。"
        ),
    )
    async def canvas_get_overview(
        canvas_workspace_id: Annotated[str, Field(description="画布工作区 id（canvas_list 获得）")],
        cursor: Annotated[Optional[str], Field(description="续读游标：上一页响应的 next_cursor 原样传回（缺省从第一页读）")] = None,
        page_size: Annotated[Optional[int], Field(description="每页节点数，缺省 60（10~100）")] = None,
    ) -> Dict[str, Any]:
        principal = _principal()
        try:
            async with async_session() as db:
                return await canvas_overview_impl(db, principal.user_id, canvas_workspace_id, cursor, page_size)
        except Exception as e:
            return _tool_error(e)

    @mcp.tool(
        name="canvas_apply_ops",
        description=(
            "向云端画布工作区批量应用增量操作（op 列表，单条失败不拖垮整批）。"
            "op 种类：add_panel（type：text/image/video/audio，缺省 text；name 建议命名，后续连线可按名引用；"
            "文本节点 content 写 {\"content\":\"文字\"}，媒体节点可直接给 url）与 "
            "add_connection（source_panel_id/target_panel_id 传节点 id 或本批新建节点的 name）。"
            "生成本地素材后落画布：把生成结果的 URL 用 add_panel 建媒体节点即可。"
        ),
    )
    async def canvas_apply_ops(
        canvas_workspace_id: Annotated[str, Field(description="画布工作区 id（canvas_list 获得）")],
        ops: Annotated[List[Dict[str, Any]], Field(description="op 列表", min_length=1, max_length=50)],
    ) -> Dict[str, Any]:
        principal = _principal()
        denied = _denied(principal, write=True)
        if denied:
            return {"ok": False, "error": denied}
        try:
            async with async_session() as db:
                return await canvas_apply_ops_impl(db, principal.user_id, canvas_workspace_id, ops)
        except Exception as e:
            return _tool_error(e)
