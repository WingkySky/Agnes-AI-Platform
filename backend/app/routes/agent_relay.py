# =====================================================
# Agent 反向控制桥路由
#
# - WS /api/agent/relay/ws?token=  页面执行者注册（JWT 查询参认证）
# - POST /api/agent/relay/call     页外工具调用中继（在线→下发等回执 / 离线→routed:offline）
# - GET  /api/agent/relay/targets  当前用户在线执行目标（前端工具注入条件用）
#
# 纯通道：回退逻辑在前端（离线时走既有 HTTP 实现），本路由不做业务执行；
# 归属校验逐请求执行（跨用户不可触达），工具白名单在服务层 BRIDGE_HOSTS。
# =====================================================

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_async_db
from app.core.response import ok
from app.core.security import decode_access_token, get_current_user
from app.models.canvas_workspace import CanvasWorkspace
from app.models.editing_project import EditingProject
from app.models.user import User
from app.schemas.agent_relay import RelayCallCreate
from app.services import relay_service
from app.services.relay_service import (
    BRIDGE_HOSTS,
    RELAY_DEFAULT_TIMEOUT,
    RELAY_TOOL_TIMEOUTS,
    BridgeOffline,
    BridgeTimeout,
)

router = APIRouter(prefix="/agent/relay", tags=["Agent 反向控制桥"])


async def _check_target_owned(
    db: AsyncSession, user: User, host: str, target_id: str
) -> None:
    """目标归属校验：画布工作区按 id、剪辑工程按 uid；不存在 404 / 非本人 403"""
    if host == "canvas":
        row = (
            await db.scalars(select(CanvasWorkspace).where(CanvasWorkspace.id == target_id))
        ).first()
    elif host == "editor":
        row = (
            await db.scalars(select(EditingProject).where(EditingProject.uid == target_id))
        ).first()
    else:
        raise HTTPException(status_code=400, detail=f"未知宿主种类: {host}")
    if not row:
        raise HTTPException(status_code=404, detail="目标不存在（画布工作区/剪辑工程）")
    if row.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该目标")


@router.websocket("/ws")
async def relay_ws(websocket: WebSocket, token: str = Query(default="")):
    """页面执行者注册通道；JWT 查询参认证，失败以 4401 关闭"""
    user_id = decode_access_token(token)
    if user_id is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    await relay_service.run_ws(websocket, user_id)


@router.post("/call", summary="中继工具调用到打开着的目标页面")
async def relay_call(
    payload: RelayCallCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    tool_list = BRIDGE_HOSTS.get(payload.host)
    if tool_list is None:
        raise HTTPException(status_code=400, detail=f"未知宿主种类: {payload.host}")
    if payload.tool not in tool_list:
        raise HTTPException(status_code=403, detail=f"工具 {payload.tool} 不在桥白名单内")
    await _check_target_owned(db, current_user, payload.host, payload.target_id)

    conn = relay_service.get_connection(current_user.id, payload.host, payload.target_id)
    if conn is None:
        # 调用方（前端工具层）按 routed=offline 走既有回退实现
        return ok(data={"routed": "offline"})
    timeout = RELAY_TOOL_TIMEOUTS.get(payload.tool, RELAY_DEFAULT_TIMEOUT)
    try:
        result = await relay_service.relay_call(conn, payload.tool, payload.args, timeout)
    except BridgeOffline:
        # 下发即发现连接死亡：等同离线，可安全回退
        return ok(data={"routed": "offline"})
    except BridgeTimeout:
        # 已下发未回执：写操作可能已执行，绝不回退，调用方原样报错
        raise HTTPException(
            status_code=504,
            detail={"message": "画布/剪辑器页面未在窗口内回执", "code": "bridge_timeout"},
        )
    return ok(data={"routed": "relay", "result": result})


@router.get("/targets", summary="当前用户在线执行目标清单")
async def relay_targets(current_user: User = Depends(get_current_user)):
    return ok(data={"targets": relay_service.list_targets(current_user.id)})
