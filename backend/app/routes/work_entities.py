# =====================================================
# 作品实体库路由（/api/works/{work_id}/entities、/api/entities）
# 用户自助功能：路由级挂登录依赖；归属校验非本人 403 / 不存在 404
# =====================================================

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.response import ok
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.work_entity import (
    EntityAdoptRequest,
    EntityCreateRequest,
    EntityListResponse,
    EntityResponse,
    EntityUpdateRequest,
    EntityVersionCreateRequest,
)
from app.services import work_entity_service, work_service

router = APIRouter(tags=["作品实体库"], dependencies=[Depends(get_current_user)])


async def _require_work(db: AsyncSession, work_id: int, user_id: int):
    work, is_owner = await work_service.get_work_owned(db, work_id, user_id)
    if work is None:
        raise HTTPException(status_code=404, detail="作品不存在")
    if not is_owner:
        raise HTTPException(status_code=403, detail="无权访问该作品")
    return work


async def _require_entity(db: AsyncSession, entity_id: int, user_id: int):
    entity, work, is_owner = await work_entity_service.get_entity_owned(db, entity_id, user_id)
    if entity is None or work is None:
        raise HTTPException(status_code=404, detail="实体不存在")
    if not is_owner:
        raise HTTPException(status_code=403, detail="无权操作该实体")
    return entity, work


async def _require_asset(db: AsyncSession, asset_id: int, user_id: int) -> None:
    if not await work_entity_service.asset_owned(db, asset_id, user_id):
        raise HTTPException(status_code=404, detail="资产不存在")


@router.get("/works/{work_id}/entities", summary="作品实体列表")
async def list_entities(
    work_id: int,
    kind: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    await _require_work(db, work_id, current_user.id)
    items = await work_entity_service.list_entity_dicts(db, work_id, kind)
    return ok(data=EntityListResponse(
        total=len(items),
        items=[EntityResponse.model_validate(item) for item in items],
    ).model_dump(mode="json"))


@router.post("/works/{work_id}/entities", summary="创建实体（可带首图建首版本并采用）")
async def create_entity(
    work_id: int,
    payload: EntityCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    await _require_work(db, work_id, current_user.id)
    if payload.asset_id:
        await _require_asset(db, payload.asset_id, current_user.id)
    item = await work_entity_service.create_entity(
        db, work_id, payload.kind, payload.name,
        description=payload.description, asset_id=payload.asset_id,
    )
    return ok(data=EntityResponse.model_validate(item).model_dump(mode="json"))


@router.patch("/entities/{entity_id}", summary="更新实体（名称/描述）")
async def update_entity(
    entity_id: int,
    payload: EntityUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    entity, _work = await _require_entity(db, entity_id, current_user.id)
    await work_entity_service.update_entity(
        db, entity, name=payload.name, description=payload.description,
    )
    items = await work_entity_service.list_entity_dicts(db, entity.work_id)
    item = next(i for i in items if i["id"] == entity.id)
    return ok(data=EntityResponse.model_validate(item).model_dump(mode="json"))


@router.delete("/entities/{entity_id}", summary="删除实体（不动资产，挂链卡片脱钩保留当前图）")
async def delete_entity(
    entity_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    entity, _work = await _require_entity(db, entity_id, current_user.id)
    await work_entity_service.delete_entity(db, entity)
    return ok(message="实体已删除")


@router.post("/entities/{entity_id}/versions", summary="新增表现图（design=新版本并自动采用；angle/turnaround=追加进采用版本）")
async def add_version(
    entity_id: int,
    payload: EntityVersionCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    entity, _work = await _require_entity(db, entity_id, current_user.id)
    await _require_asset(db, payload.asset_id, current_user.id)
    await work_entity_service.add_version(db, entity, payload.asset_id, payload.role)
    items = await work_entity_service.list_entity_dicts(db, entity.work_id)
    item = next(i for i in items if i["id"] == entity.id)
    return ok(data=EntityResponse.model_validate(item).model_dump(mode="json"))


@router.post("/entities/{entity_id}/adopt", summary="切换采用版本")
async def adopt_version(
    entity_id: int,
    payload: EntityAdoptRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    entity, _work = await _require_entity(db, entity_id, current_user.id)
    if not await work_entity_service.adopt_version(db, entity, payload.version_id):
        raise HTTPException(status_code=404, detail="版本不存在")
    items = await work_entity_service.list_entity_dicts(db, entity.work_id)
    item = next(i for i in items if i["id"] == entity.id)
    return ok(data=EntityResponse.model_validate(item).model_dump(mode="json"))
