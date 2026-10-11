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
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import async_session
from app.models.pat_token import PatToken
from app.models.user import User
from app.routes.images import create_image_task_async, get_image_task_status
from app.routes.videos import create_video_task, get_video_status
from app.schemas.images import ImageGenerationRequest
from app.schemas.videos import VideoGenerationRequest
from app.services.asset_library import list_assets
from app.services.canvas_workspace_service import (
    apply_workspace_ops,
    create_workspace,
    get_owned_workspace,
    list_workspaces,
)
from app.services.editor import project_service, render_service, rough_cut_service
from app.services.model_registry import get_all_models, get_models_by_type

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
# 编辑器工具实现（复用 project_service / render_service / rough_cut_service）
# =====================================================

def _brief_project(p) -> Dict[str, Any]:
    return {k: v for k, v in project_service._to_dict(p).items() if k != "document"}


async def _load_user(db: AsyncSession, user_id: int) -> User:
    """MCP 场景只有 user_id：同一 session 内加载真实 User（编辑器/生成 service 吃 User 对象）"""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="令牌对应用户不存在")
    return user


async def editor_list_projects_impl(db: AsyncSession, user_id: int, work_id: Optional[int]) -> Dict[str, Any]:
    items = await project_service.list_projects(db, user_id, work_id)
    return {"ok": True, "items": [_brief_project(p) for p in items]}


async def editor_create_project_impl(
    db: AsyncSession, user_id: int, title: Optional[str], work_id: Optional[int]
) -> Dict[str, Any]:
    user = await _load_user(db, user_id)
    project = await project_service.create_project(db, user, title or f"外部工程 {datetime.utcnow():%Y-%m-%d %H:%M}", work_id=work_id)
    return {"ok": True, **project_service._to_dict(project)}


async def editor_get_document_impl(db: AsyncSession, user_id: int, uid: str) -> Dict[str, Any]:
    user = await _load_user(db, user_id)
    project = await project_service.get_owned_project(db, uid, user)
    return {"ok": True, **project_service._to_dict(project)}


async def editor_put_document_impl(
    db: AsyncSession, user_id: int, uid: str, document: Dict[str, Any], base_revision: int,
    snapshot_reason: Optional[str],
) -> Dict[str, Any]:
    user = await _load_user(db, user_id)
    project = await project_service.get_owned_project(db, uid, user)
    if project.render_status == render_service.RENDER_RENDERING:
        raise HTTPException(status_code=409, detail="渲染进行中（使用提交时快照），渲染完成后可继续保存")
    project = await project_service.save_document(
        db, project, document, base_revision, snapshot_reason=snapshot_reason
    )
    return {"ok": True, "revision": project.revision, "saved_at": project.updated_at.isoformat() if project.updated_at else None}


async def editor_render_submit_impl(
    db: AsyncSession, user_id: int, uid: str, client_operation_id: Optional[str]
) -> Dict[str, Any]:
    user = await _load_user(db, user_id)
    project = await project_service.get_owned_project(db, uid, user)
    body = {"client_operation_id": client_operation_id} if client_operation_id else {}
    result = await render_service.submit_render(db, project, body)
    return {"ok": True, **result}


async def editor_render_status_impl(db: AsyncSession, user_id: int, uid: str) -> Dict[str, Any]:
    user = await _load_user(db, user_id)
    project = await project_service.get_owned_project(db, uid, user)
    return {"ok": True, **render_service.render_status_payload(project)}


async def editor_rough_cut_analyze_impl(
    db: AsyncSession, user_id: int, asset_id: int, mode: str, params: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    result = await rough_cut_service.analyze_asset(db, user_id, asset_id, mode, params)
    return {"ok": True, **result}


# =====================================================
# 素材 / 模型 / 生成工具实现
# =====================================================

def _envelope_data(resp: Dict[str, Any]) -> Any:
    """内部路由函数返回 ok() 信封 → data；pydantic 模型转 dict"""
    data = resp.get("data")
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    return data


async def asset_list_impl(
    db: AsyncSession, user_id: int, kind: Optional[str], work_id: Optional[int],
    keyword: Optional[str], page: int, page_size: int,
) -> Dict[str, Any]:
    result = await list_assets(
        db, user_id=user_id, media_type=kind, work_id=work_id, keyword=keyword,
        page=page, page_size=min(page_size, 100),
    )
    return {"ok": True, "total": result["total"], "page": result["page"], "page_size": result["page_size"], "items": result["items"]}


async def model_list_impl(kind: Optional[str]) -> Dict[str, Any]:
    if kind in ("image", "video", "chat"):
        models = await get_models_by_type(kind)
    else:
        models = await get_all_models()
    return {
        "ok": True,
        "items": [
            {"id": m.id, "name": m.name, "type": m.type, "provider": m.provider, "capabilities": m.capabilities}
            for m in models
        ],
    }


async def image_generate_impl(
    db: AsyncSession, user: User, prompt: str, model: Optional[str], size: Optional[str],
    ref_image_urls: Optional[List[str]],
) -> Dict[str, Any]:
    req = ImageGenerationRequest(
        prompt=prompt, model=model or "", size=size or "1024x1024",
        image_urls=ref_image_urls or None,
    )
    data = _envelope_data(await create_image_task_async(req, db, user))
    return {"ok": True, **data}


async def video_generate_impl(
    db: AsyncSession, user: User, prompt: str, model: Optional[str], aspect_ratio: Optional[str],
    seconds: Optional[float], ref_image_urls: Optional[List[str]],
) -> Dict[str, Any]:
    req = VideoGenerationRequest(
        prompt=prompt, model=model or "",
        aspect_ratio=aspect_ratio or "16:9", seconds=seconds,
        mode="image2video" if ref_image_urls else "text2video",
        images=ref_image_urls or None,
    )
    data = _envelope_data(await create_video_task(req, db, user))
    return {"ok": True, **data}


async def generation_get_impl(db: AsyncSession, user: User, task_ids: List[str]) -> Dict[str, Any]:
    """逐任务复用既有状态端点（内存实时态 → DB 完成态回退，双类型 + 用户隔离全继承）"""
    items: List[Dict[str, Any]] = []
    for tid in task_ids:
        kind, data = None, None
        for getter, k in ((get_image_task_status, "image"), (get_video_status, "video")):
            try:
                data = _envelope_data(await getter(task_id=tid, db=db, current_user=user))
                kind = k
                break
            except HTTPException as e:
                if e.status_code != 404:
                    raise
        if kind:
            items.append({"kind": kind, **data})
        else:
            items.append({"task_id": tid, "status": "not_found"})
    return {"ok": True, "items": items}


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

    # ---------- 编辑器 ----------

    @mcp.tool(
        name="editor_list_projects",
        description="列出剪辑工程（uid/标题/版本/渲染状态/更新时间，不含文档）。要编辑某工程的时间线前先调用确定 uid。",
    )
    async def editor_list_projects(
        work_id: Annotated[Optional[int], Field(description="按所属作品 id 筛选")] = None,
    ) -> Dict[str, Any]:
        principal = _principal()
        try:
            async with async_session() as db:
                return await editor_list_projects_impl(db, principal.user_id, work_id)
        except Exception as e:
            return _tool_error(e)

    @mcp.tool(name="editor_create_project", description="新建剪辑工程，返回 uid。title 缺省自动命名。")
    async def editor_create_project(
        title: Annotated[Optional[str], Field(description="工程标题")] = None,
        work_id: Annotated[Optional[int], Field(description="挂靠作品 id")] = None,
    ) -> Dict[str, Any]:
        principal = _principal()
        denied = _denied(principal, write=True)
        if denied:
            return {"ok": False, "error": denied}
        try:
            async with async_session() as db:
                return await editor_create_project_impl(db, principal.user_id, title, work_id)
        except Exception as e:
            return _tool_error(e)

    @mcp.tool(
        name="editor_get_document",
        description="读取剪辑工程全量（含时间线 document JSON 与 revision）。改时间线前先读，保存时把原 revision 传回 base_revision。",
    )
    async def editor_get_document(
        uid: Annotated[str, Field(description="剪辑工程 uid（editor_list_projects 获得）")],
    ) -> Dict[str, Any]:
        principal = _principal()
        try:
            async with async_session() as db:
                return await editor_get_document_impl(db, principal.user_id, uid)
        except Exception as e:
            return _tool_error(e)

    @mcp.tool(
        name="editor_put_document",
        description=(
            "保存剪辑工程时间线 document（revision 乐观锁：base_revision 传 editor_get_document 返回的 revision，"
            "不符报冲突需重读）。snapshot_reason 非空时保存前自动拍快照（可还原）。"
        ),
    )
    async def editor_put_document(
        uid: Annotated[str, Field(description="剪辑工程 uid")],
        document: Annotated[Dict[str, Any], Field(description="完整时间线文档 JSON")],
        base_revision: Annotated[int, Field(description="客户端持有的版本号（乐观锁）")],
        snapshot_reason: Annotated[Optional[str], Field(description="写前快照原因（触发自动快照）")] = None,
    ) -> Dict[str, Any]:
        principal = _principal()
        denied = _denied(principal, write=True)
        if denied:
            return {"ok": False, "error": denied}
        try:
            async with async_session() as db:
                return await editor_put_document_impl(db, principal.user_id, uid, document, base_revision, snapshot_reason)
        except Exception as e:
            return _tool_error(e)

    @mcp.tool(
        name="editor_render_submit",
        description=(
            "提交剪辑工程渲染成片（异步）。重试时带同一 client_operation_id 即幂等（返回上次结果）；"
            "提交后用 editor_render_status 轮询。时间线为空会报错。"
        ),
    )
    async def editor_render_submit(
        uid: Annotated[str, Field(description="剪辑工程 uid")],
        client_operation_id: Annotated[Optional[str], Field(description="幂等键：重试时传同一值")] = None,
    ) -> Dict[str, Any]:
        principal = _principal()
        denied = _denied(principal, write=True)
        if denied:
            return {"ok": False, "error": denied}
        try:
            async with async_session() as db:
                return await editor_render_submit_impl(db, principal.user_id, uid, client_operation_id)
        except Exception as e:
            return _tool_error(e)

    @mcp.tool(
        name="editor_render_status",
        description="查询剪辑工程渲染状态（status/progress/video_url）。render 完成后 video_url 即成片地址。",
    )
    async def editor_render_status(
        uid: Annotated[str, Field(description="剪辑工程 uid")],
    ) -> Dict[str, Any]:
        principal = _principal()
        try:
            async with async_session() as db:
                return await editor_render_status_impl(db, principal.user_id, uid)
        except Exception as e:
            return _tool_error(e)

    @mcp.tool(
        name="editor_rough_cut_analyze",
        description=(
            "AI 粗剪分析：对视频/音频素材做静音剔除（mode=silence，保留有声段）或场景切分（mode=scenes），"
            "返回 segments [{start,end}]（秒）。拿到段后通常配合 editor_get/put_document 落成草稿时间线。"
        ),
    )
    async def editor_rough_cut_analyze(
        asset_id: Annotated[int, Field(description="素材 id（asset_list 获得）")],
        mode: Annotated[str, Field(description="silence=静音剔除 / scenes=场景切分")],
        threshold_db: Annotated[Optional[float], Field(description="silence：静音判定阈值 dB（默认 -30）")] = None,
        min_gap: Annotated[Optional[float], Field(description="silence：最短静音秒（默认 0.5）")] = None,
        threshold: Annotated[Optional[float], Field(description="scenes：画面差阈值（默认 14）")] = None,
    ) -> Dict[str, Any]:
        principal = _principal()
        params: Dict[str, Any] = {}
        if mode == "silence":
            if threshold_db is not None:
                params["threshold_db"] = threshold_db
            if min_gap is not None:
                params["min_silence"] = min_gap
        elif mode == "scenes":
            if threshold is not None:
                params["threshold"] = threshold
        try:
            async with async_session() as db:
                return await editor_rough_cut_analyze_impl(db, principal.user_id, asset_id, mode, params or None)
        except Exception as e:
            return _tool_error(e)

    # ---------- 素材 / 模型 / 生成 ----------

    @mcp.tool(
        name="asset_list",
        description="列出用户素材库（图片/视频/音频，含 URL 与媒体元信息）。粗剪分析、视频参考图取 asset 的 url 用。",
    )
    async def asset_list(
        kind: Annotated[Optional[str], Field(description="image / video / audio")] = None,
        work_id: Annotated[Optional[int], Field(description="按所属作品 id 筛选")] = None,
        keyword: Annotated[Optional[str], Field(description="名称/描述关键词")] = None,
        page: Annotated[int, Field(description="页码，从 1 起")] = 1,
        page_size: Annotated[int, Field(description="每页数量（≤100）")] = 50,
    ) -> Dict[str, Any]:
        principal = _principal()
        try:
            async with async_session() as db:
                return await asset_list_impl(db, principal.user_id, kind, work_id, keyword, page, page_size)
        except Exception as e:
            return _tool_error(e)

    @mcp.tool(
        name="model_list",
        description="列出可用生成模型（id/名称/能力标签）。image_generate / video_generate 的 model 参数从此处取。",
    )
    async def model_list(
        kind: Annotated[Optional[str], Field(description="image / video / chat，缺省全部")] = None,
    ) -> Dict[str, Any]:
        _principal()
        try:
            return await model_list_impl(kind)
        except Exception as e:
            return _tool_error(e)

    @mcp.tool(
        name="image_generate",
        description=(
            "创建图片生成异步任务（扣积分），返回 task_id；用 generation_get 轮询。"
            "一次一张，多张请多次调用。ref_image_urls 给参考图 URL 即为图生图（可从 asset_list 或画布节点拿 URL）。"
        ),
    )
    async def image_generate(
        prompt: Annotated[str, Field(description="提示词")],
        model: Annotated[Optional[str], Field(description="模型 id（model_list 获得，缺省用默认模型）")] = None,
        size: Annotated[Optional[str], Field(description="尺寸 宽x高（默认 1024x1024）")] = None,
        ref_image_urls: Annotated[Optional[List[str]], Field(description="参考图 URL 列表（给了就是图生图）")] = None,
    ) -> Dict[str, Any]:
        principal = _principal()
        denied = _denied(principal, write=True)
        if denied:
            return {"ok": False, "error": denied}
        try:
            async with async_session() as db:
                user = await _load_user(db, principal.user_id)
                return await image_generate_impl(db, user, prompt, model, size, ref_image_urls)
        except Exception as e:
            return _tool_error(e)

    @mcp.tool(
        name="video_generate",
        description=(
            "创建视频生成异步任务（扣积分，耗时分钟级），返回 task_id；用 generation_get 轮询。"
            "ref_image_urls 给参考图即为图生视频（首帧/多图参考）。"
        ),
    )
    async def video_generate(
        prompt: Annotated[str, Field(description="提示词")],
        model: Annotated[Optional[str], Field(description="模型 id（model_list 获得）")] = None,
        aspect_ratio: Annotated[Optional[str], Field(description="画面比例，默认 16:9")] = None,
        seconds: Annotated[Optional[float], Field(description="时长（秒）")] = None,
        ref_image_urls: Annotated[Optional[List[str]], Field(description="参考图 URL 列表（给了就是图生视频）")] = None,
    ) -> Dict[str, Any]:
        principal = _principal()
        denied = _denied(principal, write=True)
        if denied:
            return {"ok": False, "error": denied}
        try:
            async with async_session() as db:
                user = await _load_user(db, principal.user_id)
                return await video_generate_impl(db, user, prompt, model, aspect_ratio, seconds, ref_image_urls)
        except Exception as e:
            return _tool_error(e)

    @mcp.tool(
        name="generation_get",
        description=(
            "批量查询生成任务状态（image/video 通用）：status/progress/result_url/error。"
            "success 时 result_url 即成品地址；失败时读 error 与 error_category。"
        ),
    )
    async def generation_get(
        task_ids: Annotated[List[str], Field(description="任务 id 列表（image_generate / video_generate 返回）", min_length=1, max_length=20)],
    ) -> Dict[str, Any]:
        principal = _principal()
        try:
            async with async_session() as db:
                user = await _load_user(db, principal.user_id)
                return await generation_get_impl(db, user, task_ids)
        except Exception as e:
            return _tool_error(e)
