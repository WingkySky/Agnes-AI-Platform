# =====================================================
# 剪辑器路由（/api/editor，登录级）
#
# - POST/GET /api/editor/projects            新建（支持画布圈选素材草稿）/ 列表
# - GET/PATCH/DELETE /api/editor/projects/{uid}  详情 / 改标题挂靠 / 删
# - PUT  /api/editor/projects/{uid}/document 时间线保存（revision 乐观锁 409；
#        snapshot_reason 仅 agent 工具层携带，触发写前快照）
# - GET  /api/editor/projects/{uid}/revision  远端 revision 轻查询（编辑器页轮询）
# - GET  /api/editor/projects/{uid}/snapshots[/{id}]  agent 写前快照列表/全量（还原走正常保存链路）
# - POST /api/editor/projects/{uid}/subtitles/preview  whisper 转写字幕草稿
#   （渲染端点在 render_service 落地阶段接入）
#
# 鉴权双挂：router 级 dependencies + 端点显式 Depends（401/403/200 三态测试锁死）
# =====================================================

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.response import ok
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.editor import (
    EditorDocumentSave,
    EditorProjectBrief,
    EditorProjectCreate,
    EditorProjectListResponse,
    EditorProjectUpdate,
    SubtitlePreviewRequest,
)
from app.services.editor import project_service, render_service, transcribe_bridge

router = APIRouter(
    prefix="/editor/projects",
    tags=["剪辑器"],
    dependencies=[Depends(get_current_user)],
)


def _brief(p) -> dict:
    return {k: v for k, v in project_service._to_dict(p).items() if k != "document"}


@router.post("", summary="新建剪辑工程")
async def create_project(
    body: EditorProjectCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    document = body.document
    source_ws = body.source_workspace_id
    # 圈选素材建草稿：未入库素材懒入库，按序排入主轨
    if body.asset_ids and not document:
        document, source_ws = await project_service.build_draft_from_assets(
            db, current_user, body.asset_ids, source_ws
        )
    project = await project_service.create_project(
        db, current_user, body.title, work_id=body.work_id,
        document=document, source_workspace_id=source_ws,
    )
    return ok(data=project_service._to_dict(project))


@router.get("", summary="剪辑工程列表（按 work_id 可筛）")
async def list_projects(
    work_id: Optional[int] = None,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    items = await project_service.list_projects(db, current_user.id, work_id)
    data = EditorProjectListResponse(
        total=len(items),
        items=[EditorProjectBrief(**_brief(p)) for p in items],
    )
    return ok(data=data.model_dump())


@router.get("/{uid}", summary="剪辑工程详情")
async def get_project(
    uid: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await project_service.get_owned_project(db, uid, current_user)
    return ok(data=project_service._to_dict(project))


@router.patch("/{uid}", summary="编辑剪辑工程（标题/挂靠作品）")
async def update_project(
    uid: str,
    body: EditorProjectUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await project_service.get_owned_project(db, uid, current_user)
    project = await project_service.update_project(db, project, body.title, body.work_id, cover_url=body.cover_url)
    return ok(data=project_service._to_dict(project))


@router.delete("/{uid}", summary="删除剪辑工程")
async def delete_project(
    uid: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await project_service.get_owned_project(db, uid, current_user)
    await project_service.delete_project(db, project)
    return ok(message="已删除剪辑工程")


@router.put("/{uid}/document", summary="保存时间线文档（revision 乐观锁；snapshot_reason 触发写前快照）")
async def save_document(
    uid: str,
    body: EditorDocumentSave,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await project_service.get_owned_project(db, uid, current_user)
    if project.render_status == render_service.RENDER_RENDERING:
        raise HTTPException(status_code=409, detail="渲染进行中（使用提交时快照），渲染完成后可继续保存")
    project = await project_service.save_document(
        db, project, body.document, body.base_revision, snapshot_reason=body.snapshot_reason
    )
    return ok(data={"revision": project.revision, "saved_at": project.updated_at.isoformat()})


@router.get("/{uid}/revision", summary="远端 revision 轻查询（编辑器页轮询感知外部写入）")
async def get_revision(
    uid: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await project_service.get_owned_project(db, uid, current_user)
    return ok(data={
        "revision": project.revision,
        "render_status": project.render_status,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    })


@router.get("/{uid}/snapshots", summary="快照列表（不含 data，时间倒序）")
async def list_snapshots(
    uid: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await project_service.get_owned_project(db, uid, current_user)
    rows = await project_service.list_snapshots(db, project)
    return ok(data={"items": [project_service.snapshot_brief(s) for s in rows]})


@router.get("/{uid}/snapshots/{snapshot_id}", summary="快照全量（含 data，还原时拉取）")
async def get_snapshot(
    uid: str,
    snapshot_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await project_service.get_owned_project(db, uid, current_user)
    snap = await project_service.get_snapshot(db, project, snapshot_id)
    return ok(data={**project_service.snapshot_brief(snap), "data": snap.data})


@router.post("/{uid}/render", summary="提交渲染（提交时快照 + client_operation_id 幂等）")
async def submit_render(
    uid: str,
    body: dict | None = None,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await project_service.get_owned_project(db, uid, current_user)
    result = await render_service.submit_render(db, project, body or {})
    return ok(data=result)


@router.get("/{uid}/render", summary="轮询渲染状态")
async def get_render(
    uid: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await project_service.get_owned_project(db, uid, current_user)
    return ok(data=render_service.render_status_payload(project))


@router.post("/{uid}/subtitles/preview", summary="whisper 转写字幕草稿（指定音频轨）")
async def subtitles_preview(
    uid: str,
    body: SubtitlePreviewRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await project_service.get_owned_project(db, uid, current_user)
    segments = await transcribe_bridge.preview_subtitle_segments(db, project, body.track_id)
    return ok(data={"segments": segments})
