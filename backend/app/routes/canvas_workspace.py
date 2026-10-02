# =====================================================
# 画布工作区云端落库路由
#
# - 每工作区一行（canvas_workspaces），data JSON 全量保存
# - 乐观锁：PUT 带 base_revision，不符返回 409 + current_revision（前端走冲突副本流程）
# - 自动快照节流内嵌在 PUT：内容有变化且距上次快照 >= SNAPSHOT_MIN_INTERVAL_SEC 才拍，
#   kind=auto 超 MAX_AUTO_SNAPSHOTS 滚动删最旧；manual/pre_danger 由前端显式触发，无节流
# - 还原无独立端点：前端拉快照 data 后走 PUT 写回（写回前先拍 pre_danger 快照）
# =====================================================

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_async_db
from app.core.response import ok
from app.core.security import get_current_user
from app.models.canvas_workspace import (
    MAX_AUTO_SNAPSHOTS,
    SNAPSHOT_MIN_INTERVAL_SEC,
    CanvasSnapshot,
    CanvasWorkspace,
)
from app.models.user import User
from app.schemas.canvas_workspace import (
    SnapshotBrief,
    SnapshotCreate,
    SnapshotDetail,
    SnapshotListResponse,
    WorkspaceBrief,
    WorkspaceCreate,
    WorkspaceDetail,
    WorkspaceOpsCreate,
    WorkspaceSave,
)
from app.services.canvas_ops import apply_canvas_ops

router = APIRouter(prefix="/canvas/workspaces", tags=["画布工作区"])

# 手动快照允许的 kind（auto 只能由保存链路内嵌生成）
MANUAL_SNAPSHOT_KINDS = {"manual", "pre_danger"}


def _data_hash(data: dict) -> str:
    """工作区数据的内容指纹（canonical json 后 sha256，节流比较用）"""
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _get_owned_workspace(db: AsyncSession, workspace_id: str, user: User) -> CanvasWorkspace:
    """按 id 取当前用户的工作区；不存在 404 / 非本人 403"""
    ws = (await db.scalars(select(CanvasWorkspace).where(CanvasWorkspace.id == workspace_id))).first()
    if not ws:
        raise HTTPException(status_code=404, detail="画布工作区不存在")
    if ws.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该画布工作区")
    return ws


async def _create_snapshot(
    db: AsyncSession, ws: CanvasWorkspace, kind: str, name: Optional[str] = None
) -> CanvasSnapshot:
    snap = CanvasSnapshot(
        workspace_id=ws.id,
        user_id=ws.user_id,
        kind=kind,
        name=name,
        revision=ws.revision,
        content_hash=_data_hash(ws.data),
        data=ws.data,
    )
    db.add(snap)
    return snap


async def _maybe_auto_snapshot(db: AsyncSession, ws: CanvasWorkspace) -> None:
    """PUT 内嵌的自动快照节流：内容有变化且距最近快照超过间隔才拍，auto 类滚动保 20 份"""
    last = (
        await db.scalars(
            select(CanvasSnapshot)
            .where(CanvasSnapshot.workspace_id == ws.id)
            .order_by(CanvasSnapshot.created_at.desc())
            .limit(1)
        )
    ).first()
    now = datetime.utcnow()
    if last is not None:
        if last.content_hash == _data_hash(ws.data):
            return  # 内容没变不拍
        if now - last.created_at < timedelta(seconds=SNAPSHOT_MIN_INTERVAL_SEC):
            return  # 间隔未到不拍
    await _create_snapshot(db, ws, kind="auto")
    # autoflush=False（见 core/database.py）：显式 flush 让下面的滚动查询看到刚插入的快照
    await db.flush()
    # 滚动清理：auto 类超过上限删最旧（manual/pre_danger 不占额度）
    autos = (
        await db.scalars(
            select(CanvasSnapshot)
            .where(CanvasSnapshot.workspace_id == ws.id, CanvasSnapshot.kind == "auto")
            .order_by(CanvasSnapshot.created_at.desc())
        )
    ).all()
    for stale in autos[MAX_AUTO_SNAPSHOTS:]:
        await db.delete(stale)


@router.get("", summary="画布工作区列表（不含 data）")
async def list_workspaces(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    items = (
        await db.scalars(
            select(CanvasWorkspace)
            .where(CanvasWorkspace.user_id == current_user.id)
            .order_by(CanvasWorkspace.updated_at.desc())
        )
    ).all()
    return ok(data=[WorkspaceBrief.model_validate(w).model_dump(mode="json") for w in items])


@router.post("", summary="创建画布工作区（id 可透传，重复创建幂等返回已有）")
async def create_workspace(
    payload: WorkspaceCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    if payload.id:
        existing = (
            await db.scalars(
                select(CanvasWorkspace).where(CanvasWorkspace.id == payload.id)
            )
        ).first()
        if existing:
            if existing.user_id != current_user.id:
                # id 是全局主键：被其他用户占用时明确拒绝，不落地 IntegrityError
                raise HTTPException(status_code=409, detail="画布工作区 id 已被占用")
            return ok(data=WorkspaceDetail.model_validate(existing).model_dump(mode="json"))
    ws = CanvasWorkspace(
        id=payload.id or uuid.uuid4().hex,
        user_id=current_user.id,
        name=payload.name,
        data=payload.data,
    )
    db.add(ws)
    await db.commit()
    await db.refresh(ws)
    return ok(data=WorkspaceDetail.model_validate(ws).model_dump(mode="json"))


@router.get("/{workspace_id}", summary="画布工作区全量（data + revision）")
async def get_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    ws = await _get_owned_workspace(db, workspace_id, current_user)
    return ok(data=WorkspaceDetail.model_validate(ws).model_dump(mode="json"))


@router.put("/{workspace_id}", summary="保存画布工作区（乐观锁，冲突返回 409）")
async def save_workspace(
    workspace_id: str,
    payload: WorkspaceSave,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    ws = await _get_owned_workspace(db, workspace_id, current_user)
    if payload.base_revision != ws.revision:
        raise HTTPException(
            status_code=409,
            detail={"message": "画布工作区版本冲突", "current_revision": ws.revision},
        )
    ws.data = payload.data
    if payload.name is not None:
        ws.name = payload.name
    ws.revision += 1
    await _maybe_auto_snapshot(db, ws)
    await db.commit()
    await db.refresh(ws)
    return ok(data={"revision": ws.revision})


@router.post("/{workspace_id}/ops", summary="批量应用画布操作（对话 Agent / 外部宿主增量写入）")
async def apply_workspace_ops(
    workspace_id: str,
    payload: WorkspaceOpsCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    ws = await _get_owned_workspace(db, workspace_id, current_user)
    new_data, outcome = apply_canvas_ops(ws.data or {}, payload.ops, workspace_id=ws.id)
    if outcome["failed"] and outcome["failed"] == len(outcome["results"]):
        raise HTTPException(status_code=400, detail={"message": "全部操作失败", "results": outcome["results"]})
    # 全量赋值新对象：SQLAlchemy JSON 列需重新赋值才会被变更跟踪
    ws.data = new_data
    ws.revision += 1
    await db.commit()
    return ok(data={**outcome, "revision": ws.revision})


@router.get("/{workspace_id}/revision", summary="工作区当前版本号（轻轮询用）")
async def get_workspace_revision(
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    ws = await _get_owned_workspace(db, workspace_id, current_user)
    return ok(data={"revision": ws.revision, "updated_at": ws.updated_at})


@router.delete("/{workspace_id}", summary="删除画布工作区（连带删快照）")
async def delete_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    ws = await _get_owned_workspace(db, workspace_id, current_user)
    snaps = (
        await db.scalars(select(CanvasSnapshot).where(CanvasSnapshot.workspace_id == ws.id))
    ).all()
    for snap in snaps:
        await db.delete(snap)
    await db.delete(ws)
    await db.commit()
    return ok(data={"deleted": True})


@router.post("/{workspace_id}/snapshots", summary="创建快照（manual/pre_danger）")
async def create_snapshot(
    workspace_id: str,
    payload: SnapshotCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    if payload.kind not in MANUAL_SNAPSHOT_KINDS:
        raise HTTPException(status_code=400, detail="快照类型仅支持 manual / pre_danger")
    ws = await _get_owned_workspace(db, workspace_id, current_user)
    snap = await _create_snapshot(db, ws, kind=payload.kind, name=payload.name)
    await db.commit()
    await db.refresh(snap)
    return ok(data=SnapshotBrief.model_validate(snap).model_dump(mode="json"))


@router.get("/{workspace_id}/snapshots", summary="快照列表（不含 data，时间倒序）")
async def list_snapshots(
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    ws = await _get_owned_workspace(db, workspace_id, current_user)
    items = (
        await db.scalars(
            select(CanvasSnapshot)
            .where(CanvasSnapshot.workspace_id == ws.id)
            .order_by(CanvasSnapshot.created_at.desc())
        )
    ).all()
    return ok(data=SnapshotListResponse(
        items=[SnapshotBrief.model_validate(s) for s in items]
    ).model_dump(mode="json"))


@router.get("/{workspace_id}/snapshots/{snapshot_id}", summary="快照全量（含 data）")
async def get_snapshot(
    workspace_id: str,
    snapshot_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    ws = await _get_owned_workspace(db, workspace_id, current_user)
    snap = (
        await db.scalars(
            select(CanvasSnapshot).where(
                CanvasSnapshot.id == snapshot_id, CanvasSnapshot.workspace_id == ws.id
            )
        )
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="快照不存在")
    return ok(data=SnapshotDetail.model_validate(snap).model_dump(mode="json"))


@router.delete("/{workspace_id}/snapshots/{snapshot_id}", summary="删除快照")
async def delete_snapshot(
    workspace_id: str,
    snapshot_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    ws = await _get_owned_workspace(db, workspace_id, current_user)
    snap = (
        await db.scalars(
            select(CanvasSnapshot).where(
                CanvasSnapshot.id == snapshot_id, CanvasSnapshot.workspace_id == ws.id
            )
        )
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="快照不存在")
    await db.delete(snap)
    await db.commit()
    return ok(data={"deleted": True})
