# =====================================================
# 画布工作区业务服务 —— 供 HTTP 路由与 MCP Server（mcp_gateway）共用
#
# - 归属校验（404 不存在 / 403 非本人）
# - 创建幂等：透传 id 已存在且属于本人 → 直接返回已有
# - ops 应用：apply_canvas_ops + JSON 列整体赋值 + revision 自增；全部失败 400 不写回
# =====================================================

import uuid
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.canvas_workspace import CanvasWorkspace
from app.models.work import Work
from app.services.canvas_ops import apply_canvas_ops


async def get_owned_workspace(db: AsyncSession, workspace_id: str, user_id: int) -> CanvasWorkspace:
    """按 id 取当前用户的工作区；不存在 404 / 非本人 403"""
    ws = (await db.scalars(select(CanvasWorkspace).where(CanvasWorkspace.id == workspace_id))).first()
    if not ws:
        raise HTTPException(status_code=404, detail="画布工作区不存在")
    if ws.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作该画布工作区")
    return ws


async def list_workspaces(
    db: AsyncSession, user_id: int, work_id: Optional[int] = None
) -> List[CanvasWorkspace]:
    """工作区列表（不含 data，更新时间倒序；可按作品筛选）"""
    stmt = (
        select(CanvasWorkspace)
        .where(CanvasWorkspace.user_id == user_id)
        .order_by(CanvasWorkspace.updated_at.desc())
    )
    if work_id is not None:
        stmt = stmt.where(CanvasWorkspace.work_id == work_id)
    return (await db.scalars(stmt)).all()


async def create_workspace(
    db: AsyncSession,
    user_id: int,
    name: str,
    work_id: Optional[int] = None,
    data: Optional[Dict[str, Any]] = None,
    workspace_id: Optional[str] = None,
) -> CanvasWorkspace:
    """创建工作区；透传 id 已存在幂等返回已有（被他人占用 409）；挂靠他人作品 403"""
    if work_id is not None:
        owned = (
            await db.scalars(select(Work.id).where(Work.id == work_id, Work.user_id == user_id))
        ).first()
        if not owned:
            raise HTTPException(status_code=403, detail="无权挂靠该作品")
    if workspace_id:
        existing = (
            await db.scalars(select(CanvasWorkspace).where(CanvasWorkspace.id == workspace_id))
        ).first()
        if existing:
            if existing.user_id != user_id:
                # id 是全局主键：被其他用户占用时明确拒绝，不落地 IntegrityError
                raise HTTPException(status_code=409, detail="画布工作区 id 已被占用")
            return existing
    ws = CanvasWorkspace(
        id=workspace_id or uuid.uuid4().hex,
        user_id=user_id,
        name=name,
        work_id=work_id,
        data=data or {},
    )
    db.add(ws)
    await db.commit()
    await db.refresh(ws)
    return ws


async def apply_workspace_ops(
    db: AsyncSession, ws: CanvasWorkspace, ops: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """批量应用画布操作并落库（revision 自增）；全部操作失败时 400 且不写回

    返回 outcome = { results, new_panel_ids, failed, revision }
    """
    new_data, outcome = apply_canvas_ops(ws.data or {}, ops, workspace_id=ws.id)
    if outcome["failed"] and outcome["failed"] == len(outcome["results"]):
        raise HTTPException(status_code=400, detail={"message": "全部操作失败", "results": outcome["results"]})
    # 全量赋值新对象：SQLAlchemy JSON 列需重新赋值才会被变更跟踪
    ws.data = new_data
    ws.revision += 1
    await db.commit()
    return {**outcome, "revision": ws.revision}
