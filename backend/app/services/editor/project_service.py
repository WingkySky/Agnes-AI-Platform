# =====================================================
# 剪辑工程服务层（CRUD + revision 乐观锁保存 + agent 写前快照）
# =====================================================

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.editing_project import EditorSnapshot, EditingProject
from app.models.user import User
from app.services.editor.document_schema import (
    check_document_size,
    validate_document_assets,
    validate_document_skeleton,
)

# agent 写前快照去重窗口：同窗口内内容哈希一致则不重复落快照（仿画布 auto snapshot 节流）
SNAPSHOT_DEDUP_WINDOW = timedelta(seconds=300)


def _to_dict(p: EditingProject) -> dict:
    return {
        "id": p.id,
        "uid": p.uid,
        "user_id": p.user_id,
        "work_id": p.work_id,
        "title": p.title,
        "document": p.document,
        "revision": p.revision,
        "final_url": p.final_url,
        "cover_url": p.cover_url,
        "render_status": p.render_status,
        "render_error": p.render_error,
        "render_progress": p.render_progress,
        "source_workspace_id": p.source_workspace_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


async def get_owned_project(db: AsyncSession, uid: str, user: User) -> EditingProject:
    """按 uid 取当前用户的剪辑工程；不存在 404 / 非本人 403"""
    project = (
        await db.scalars(select(EditingProject).where(EditingProject.uid == uid))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="剪辑工程不存在")
    if project.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作此剪辑工程")
    return project


def default_document() -> dict:
    """空工程默认时间线（三轨，无片段）；flags 与前端 TrackFlags 契约一致（四开全关）"""
    all_off = {"hidden": False, "locked": False, "muted": False, "solo": False}
    return {
        "timebase": 30, "width": 1280, "height": 720,
        "tracks": [
            {"id": "v1", "kind": "video", "order": 0, "flags": dict(all_off)},
            {"id": "a1", "kind": "audio", "order": 0, "flags": dict(all_off)},
            {"id": "s1", "kind": "subtitle", "order": 0, "flags": dict(all_off)},
        ],
        "clips": [],
        "subtitleStyle": {"font": "Noto Sans CJK SC", "size": 48, "color": "#FFFFFF",
                          "outline": True, "position": "bottom"},
    }


async def create_project(
    db: AsyncSession,
    user: User,
    title: str,
    work_id: Optional[int] = None,
    document: Optional[dict] = None,
    source_workspace_id: Optional[str] = None,
) -> EditingProject:
    if work_id is not None:
        from app.services import work_service

        work, owned = await work_service.get_work_owned(db, work_id, user.id)
        if not work:
            raise HTTPException(status_code=404, detail="作品不存在")
        if not owned:
            raise HTTPException(status_code=403, detail="无权挂靠此作品")
    doc = document if document is not None else default_document()
    check_document_size(doc)
    validate_document_skeleton(doc)
    await validate_document_assets(db, doc, user.id)
    project = EditingProject(
        uid=str(uuid.uuid4()),
        user_id=user.id,
        work_id=work_id,
        title=title,
        document=doc,
        source_workspace_id=source_workspace_id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def list_projects(
    db: AsyncSession, user_id: int, work_id: Optional[int] = None
) -> list[EditingProject]:
    stmt = select(EditingProject).where(EditingProject.user_id == user_id)
    if work_id is not None:
        stmt = stmt.where(EditingProject.work_id == work_id)
    stmt = stmt.order_by(EditingProject.updated_at.desc())
    return list((await db.scalars(stmt)).all())


async def update_project(
    db: AsyncSession, project: EditingProject, title: Optional[str], work_id: Optional[int],
    cover_url: Optional[str] = None,
) -> EditingProject:
    if cover_url is not None:
        project.cover_url = cover_url or None  # 空串=清空封面
    if title is not None:
        if not title.strip():
            raise HTTPException(status_code=400, detail="标题不能为空")
        project.title = title.strip()
    if work_id is not None:
        from app.services import work_service

        work, owned = await work_service.get_work_owned(db, work_id, project.user_id)
        if not work:
            raise HTTPException(status_code=404, detail="作品不存在")
        if not owned:
            raise HTTPException(status_code=403, detail="无权挂靠此作品")
        project.work_id = work_id
    await db.commit()
    return project


def _document_hash(document: dict) -> str:
    return hashlib.sha256(
        json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


async def maybe_snapshot(db: AsyncSession, project: EditingProject, reason: Optional[str]) -> Optional[EditorSnapshot]:
    """写前快照（当前文档未变时）：仅 agent 工具层携带 snapshot_reason 触发；
    去重窗口内内容哈希一致则跳过。与随后的保存同事务提交。"""
    since = datetime.utcnow() - SNAPSHOT_DEDUP_WINDOW
    latest = (
        await db.scalars(
            select(EditorSnapshot)
            .where(
                EditorSnapshot.project_uid == project.uid,
                EditorSnapshot.created_at >= since,
            )
            .order_by(EditorSnapshot.created_at.desc())
        )
    ).first()
    content_hash = _document_hash(project.document or {})
    if latest is not None and latest.content_hash == content_hash:
        return None
    snap = EditorSnapshot(
        project_uid=project.uid,
        user_id=project.user_id,
        kind="agent",
        reason=reason,
        revision=project.revision,
        content_hash=content_hash,
        data=project.document or {},
    )
    db.add(snap)
    await db.flush()
    return snap


async def save_document(
    db: AsyncSession, project: EditingProject, document: dict, base_revision: int,
    snapshot_reason: Optional[str] = None,
) -> EditingProject:
    """保存时间线文档；base_revision 不符返回 409（仿画布冲突语义）；
    snapshot_reason 非空时写前快照（agent 兜底还原用）"""
    if base_revision != project.revision:
        raise HTTPException(
            status_code=409,
            detail={"message": "文档已被其他会话修改", "current_revision": project.revision},
        )
    if snapshot_reason:
        await maybe_snapshot(db, project, snapshot_reason)
    check_document_size(document)
    validate_document_skeleton(document)
    await validate_document_assets(db, document, project.user_id)
    project.document = document
    project.revision += 1
    await db.commit()
    return project


async def list_snapshots(
    db: AsyncSession, project: EditingProject, limit: int = 50
) -> list[EditorSnapshot]:
    """快照列表（不含 data，时间倒序）"""
    stmt = (
        select(EditorSnapshot)
        .where(EditorSnapshot.project_uid == project.uid)
        .order_by(EditorSnapshot.created_at.desc())
        .limit(limit)
    )
    return list((await db.scalars(stmt)).all())


async def get_snapshot(db: AsyncSession, project: EditingProject, snapshot_id: int) -> EditorSnapshot:
    """取单条快照全量（含 data）；不属于该工程 404"""
    snap = (
        await db.scalars(
            select(EditorSnapshot).where(
                EditorSnapshot.id == snapshot_id,
                EditorSnapshot.project_uid == project.uid,
            )
        )
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="快照不存在")
    return snap


def snapshot_brief(s: EditorSnapshot) -> dict:
    return {
        "id": s.id,
        "kind": s.kind,
        "reason": s.reason,
        "revision": s.revision,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


async def delete_project(db: AsyncSession, project: EditingProject) -> None:
    await db.delete(project)
    await db.commit()


async def build_draft_from_assets(
    db: AsyncSession, user: User, asset_ids: list[int], source_workspace_id: Optional[str]
) -> tuple[dict, Optional[str]]:
    """
    画布圈选素材 → 剪辑工程草稿 document（单向快照）。

    - 素材必须已入库且属当前用户（前端送进剪辑器前先经 registerAsset 懒入库），缺失报 404
    - 视频/图片按选中顺序排主轨，音频排音频轨；视频片段 duration=0 是显式契约：
      前端打开工程后由媒体元数据加载补正（healDurations），图片默认 3s 静帧
    """
    from app.models.asset import Asset

    ids = list(dict.fromkeys(asset_ids))
    rows = (
        await db.scalars(
            select(Asset).where(Asset.id.in_(ids), Asset.user_id == user.id)
        )
    ).all()
    by_id = {a.id: a for a in rows}
    missing = [aid for aid in ids if aid not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"素材不存在或无权访问: {missing[:10]}")

    video_clips, audio_clips = [], []
    cursor = 0.0
    for aid in ids:
        asset = by_id[aid]
        if asset.kind == "audio":
            audio_clips.append({"id": f"clip_{aid}", "trackId": "a1", "assetId": aid,
                                "start": 0.0, "duration": 0.0, "trimStart": 0.0, "props": {}})
        else:
            video_clips.append({"id": f"clip_{aid}", "trackId": "v1", "assetId": aid,
                                "start": cursor, "duration": 0.0 if asset.kind == "video" else 3.0,
                                "trimStart": 0.0, "props": {}})
            cursor += 3.0 if asset.kind == "image" else 0.0

    doc = {
        "timebase": 30, "width": 1280, "height": 720,
        "tracks": [
            {"id": "v1", "kind": "video", "order": 0, "flags": {}},
            {"id": "a1", "kind": "audio", "order": 0, "flags": {}},
            {"id": "s1", "kind": "subtitle", "order": 0, "flags": {}},
        ],
        "clips": video_clips + audio_clips,
        "subtitleStyle": {"font": "Noto Sans CJK SC", "size": 48, "color": "#FFFFFF",
                          "outline": True, "position": "bottom"},
    }
    return doc, source_workspace_id
