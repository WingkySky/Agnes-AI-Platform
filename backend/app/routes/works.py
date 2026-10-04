# =====================================================
# 作品（轻容器）路由（/api/works）
# 用户自助功能：路由级挂登录依赖；归属校验非本人 403 / 不存在 404
# =====================================================

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.response import ok
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.work import (
    WorkCreateRequest,
    WorkListResponse,
    WorkResponse,
    WorkUpdateRequest,
)
from app.services import work_service

router = APIRouter(prefix="/works", tags=["作品"], dependencies=[Depends(get_current_user)])


@router.get("", summary="本人作品列表")
async def list_works(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    works = await work_service.list_works(db, current_user.id)
    return ok(data=WorkListResponse(
        total=len(works),
        items=[WorkResponse.model_validate(w) for w in works],
    ).model_dump(mode="json"))


@router.post("", summary="创建作品")
async def create_work(
    payload: WorkCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    work = await work_service.create_work(
        db, current_user.id, title=payload.title,
        description=payload.description, cover_url=payload.cover_url,
    )
    return ok(data=WorkResponse.model_validate(work).model_dump(mode="json"))


@router.get("/{work_id}", summary="作品详情")
async def get_work(
    work_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    work, is_owner = await work_service.get_work_owned(db, work_id, current_user.id)
    if work is None:
        raise HTTPException(status_code=404, detail="作品不存在")
    if not is_owner:
        raise HTTPException(status_code=403, detail="无权访问该作品")
    return ok(data=WorkResponse.model_validate(work).model_dump(mode="json"))


@router.patch("/{work_id}", summary="更新作品（标题/简介/封面）")
async def update_work(
    work_id: int,
    payload: WorkUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    work, is_owner = await work_service.get_work_owned(db, work_id, current_user.id)
    if work is None:
        raise HTTPException(status_code=404, detail="作品不存在")
    if not is_owner:
        raise HTTPException(status_code=403, detail="无权操作该作品")
    work = await work_service.update_work(
        db, work, title=payload.title,
        description=payload.description, cover_url=payload.cover_url,
    )
    return ok(data=WorkResponse.model_validate(work).model_dump(mode="json"))


@router.delete("/{work_id}", summary="删除作品（名下画布解绑为自由画布，画布本体保留）")
async def delete_work(
    work_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    work, is_owner = await work_service.get_work_owned(db, work_id, current_user.id)
    if work is None:
        raise HTTPException(status_code=404, detail="作品不存在")
    if not is_owner:
        raise HTTPException(status_code=403, detail="无权操作该作品")
    await work_service.delete_work(db, work)
    return ok(message="作品已删除")
