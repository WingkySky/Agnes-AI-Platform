# =====================================================
# 管理员预设审核路由
# - GET  /admin/presets/pending     — 待审核列表
# - POST /admin/presets/{id}/approve — 审核通过
# - POST /admin/presets/{id}/reject  — 驳回（删除预设）
# =====================================================

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_async_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.camera_preset import CameraPreset
from app.models.prompt_preset import PromptPreset, PresetIndex
from app.services import camera_preset_service as cam_svc
from app.services import prompt_preset_service as prompt_svc


router = APIRouter(prefix="/admin/presets", tags=["管理员-预设审核"])


class PendingPresetResponse(BaseModel):
    """待审核预设响应（聚合字段）"""
    id: int
    preset_type: str
    preset_id: int
    user_id: int | None = None
    name: str
    description: str | None = None
    category: str
    type: str
    is_approved: bool
    created_at: str | None = None

    class Config:
        from_attributes = True


class PendingListResponse(BaseModel):
    items: list[PendingPresetResponse]
    total: int


# ---------- 待审核列表 ----------

@router.get("/pending", response_model=PendingListResponse, summary="待审核预设列表")
async def list_pending_presets(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    列出所有待审核的预设（is_public=True 且 is_approved=False）。
    仅管理员可访问。
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可访问")

    # 从 preset_index 查询所有待审核条目
    result = await db.execute(
        select(PresetIndex)
        .filter(
            and_(
                PresetIndex.is_public == True,
                PresetIndex.is_approved == False,
            )
        )
        .order_by(PresetIndex.created_at.desc())
    )
    entries = result.scalars().all()

    items = [
        PendingPresetResponse(
            id=entry.id,
            preset_type=entry.preset_type,
            preset_id=entry.preset_id,
            user_id=entry.user_id,
            name=entry.name,
            description=entry.description,
            category=entry.category,
            type=entry.preset_type,
            is_approved=entry.is_approved,
            created_at=entry.created_at.isoformat() if entry.created_at else None,
        )
        for entry in entries
    ]

    return PendingListResponse(items=items, total=len(items))


# ---------- 审核通过 ----------

@router.post("/{preset_id}/approve", summary="审核通过")
async def approve_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    审核通过一个预设（设置 is_approved=True 并同步 preset_index）。

    preset_id 指 preset_index 表的 id（即索引条目 ID）。
    根据 preset_type 路由到对应的原表进行审核。
    审核通过同时清除 is_rejected 标记（撤销驳回状态）。
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可访问")

    # 从 preset_index 查找
    result = await db.execute(
        select(PresetIndex).filter(PresetIndex.id == preset_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="待审核预设不存在")

    # 根据类型更新原表：通过审核 + 清除驳回标记
    if entry.preset_type == "camera":
        await cam_svc.update_preset(
            db, entry.preset_id, is_approved=True, is_rejected=False
        )
    else:
        await prompt_svc.update_preset(
            db, entry.preset_id, is_approved=True, is_rejected=False
        )

    return {"message": "审核通过", "preset_id": entry.preset_id}


# ---------- 驳回 ----------

@router.post("/{preset_id}/reject", summary="驳回")
async def reject_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    驳回一个预设（将其 is_public 设为 False，不再公开可见）。

    preset_id 指 preset_index 表的 id。
    同时设置 is_rejected=True：被驳回的预设后续不可再次提交公开审核
    （硬约束：Content marked as 'rejected' by admins cannot be set to public again）。
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可访问")

    # 从 preset_index 查找
    result = await db.execute(
        select(PresetIndex).filter(PresetIndex.id == preset_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="待审核预设不存在")

    # 根据类型更新原表：撤回公开 + 标记驳回
    if entry.preset_type == "camera":
        await cam_svc.update_preset(
            db,
            entry.preset_id,
            is_public=False,
            is_approved=False,
            is_rejected=True,
        )
    else:
        await prompt_svc.update_preset(
            db,
            entry.preset_id,
            is_public=False,
            is_approved=False,
            is_rejected=True,
        )

    return {"message": "已驳回", "preset_id": entry.preset_id}
