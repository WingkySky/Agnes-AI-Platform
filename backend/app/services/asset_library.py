# =====================================================
# 资产库服务
# 提供角色、道具、场景、品牌等创意资产的 CRUD 和查询功能
# =====================================================

import logging
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.generation import Generation
from app.schemas.assets import (
    AssetCreate,
    AssetUpdate,
    AssetSaveFromGenerationRequest,
)

logger = logging.getLogger("agnes_platform")

# 允许的资产类型
VALID_ASSET_TYPES = {"character", "prop", "scene", "brand"}


# ---------- 查询 ----------

async def get_asset_by_id(db: AsyncSession, asset_id: int) -> Optional[Asset]:
    """根据 ID 获取资产"""
    result = await db.execute(select(Asset).filter(Asset.id == asset_id))
    return result.scalar_one_or_none()


async def list_assets(
    db: AsyncSession,
    asset_type: Optional[str] = None,
    search: Optional[str] = None,
    style_id: Optional[int] = None,
    user_id: Optional[int] = None,
    is_public: Optional[bool] = None,
    tag: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[List[Asset], int]:
    """
    获取资产列表（支持分页、筛选、搜索）

    返回: (items, total)
    """
    query = select(Asset)

    filters = []
    if asset_type and asset_type in VALID_ASSET_TYPES:
        filters.append(Asset.type == asset_type)
    if style_id:
        filters.append(Asset.style_id == style_id)
    if user_id is not None:
        filters.append(Asset.user_id == user_id)
    if is_public is not None:
        filters.append(Asset.is_public == is_public)
    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            Asset.name.ilike(search_pattern),
            Asset.description.ilike(search_pattern),
            Asset.visual_description.ilike(search_pattern),
        ))
    if tag:
        # SQLite 用 LIKE 查询 JSON 数组中的标签（简单实现）
        filters.append(Asset.tags.contains([tag]))

    if filters:
        query = query.where(*filters)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(
        Asset.is_public.desc(),
        Asset.use_count.desc(),
        Asset.id.desc(),
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()
    return list(items), total


async def get_asset_versions(db: AsyncSession, asset_id: int) -> List[Asset]:
    """获取资产的版本历史（通过 parent_id 链向前追溯）"""
    versions = []
    current = await get_asset_by_id(db, asset_id)
    if not current:
        return versions

    versions.append(current)

    # 向前追溯父版本（最多 20 个版本，避免无限循环）
    visited = {current.id}
    parent_id = current.parent_id
    while parent_id and len(versions) < 20:
        parent = await get_asset_by_id(db, parent_id)
        if not parent or parent.id in visited:
            break
        visited.add(parent.id)
        versions.append(parent)
        parent_id = parent.parent_id

    return versions


# ---------- 创建 ----------

async def create_asset(
    db: AsyncSession,
    data: AssetCreate,
    user_id: Optional[int] = None,
) -> Asset:
    """创建资产"""
    if data.type not in VALID_ASSET_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"无效的资产类型: {data.type}，允许的类型: {', '.join(VALID_ASSET_TYPES)}",
        )

    asset = Asset(
        type=data.type,
        name=data.name,
        description=data.description,
        visual_description=data.visual_description,
        reference_images=data.reference_images,
        style_id=data.style_id,
        user_id=user_id,
        is_public=data.is_public,
        tags=data.tags,
        version=1,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


async def save_asset_from_generation(
    db: AsyncSession,
    data: AssetSaveFromGenerationRequest,
    user_id: int,
) -> Asset:
    """从生成记录保存为资产"""
    if data.type not in VALID_ASSET_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"无效的资产类型: {data.type}",
        )

    gen_result = await db.execute(
        select(Generation).filter(
            Generation.id == data.generation_id,
            Generation.user_id == user_id,
        )
    )
    generation = gen_result.scalar_one_or_none()
    if not generation:
        raise HTTPException(status_code=404, detail="生成记录不存在")

    visual_desc = data.visual_description or generation.prompt
    ref_images = [generation.result_url] if generation.result_url else []

    asset = Asset(
        type=data.type,
        name=data.name,
        description=data.description,
        visual_description=visual_desc,
        reference_images=ref_images,
        style_id=data.style_id,
        user_id=user_id,
        is_public=False,
        tags=data.tags,
        version=1,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


# ---------- 更新（创建新版本） ----------

async def update_asset(
    db: AsyncSession,
    asset_id: int,
    data: AssetUpdate,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> Asset:
    """
    更新资产（创建新版本，不覆盖旧版本）。
    修改 description / visual_description / reference_images / style_id / tags 等字段时，
    会创建新版本，parent_id 指向旧版本。
    """
    old_asset = await get_asset_by_id(db, asset_id)
    if not old_asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    if not is_admin and old_asset.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权修改此资产")

    update_data = data.model_dump(exclude_unset=True)

    # 如果只是改 is_public 或 name 这种不影响内容的字段，直接更新，不创建新版本
    content_fields = {"visual_description", "reference_images", "style_id", "description", "tags"}
    has_content_change = any(field in update_data for field in content_fields)

    if not has_content_change:
        for field, value in update_data.items():
            if hasattr(old_asset, field) and value is not None:
                setattr(old_asset, field, value)
        await db.commit()
        await db.refresh(old_asset)
        return old_asset

    # 创建新版本
    new_asset = Asset(
        type=old_asset.type,
        name=update_data.get("name", old_asset.name),
        description=update_data.get("description", old_asset.description),
        visual_description=update_data.get("visual_description", old_asset.visual_description),
        reference_images=update_data.get("reference_images", old_asset.reference_images),
        style_id=update_data.get("style_id", old_asset.style_id),
        user_id=old_asset.user_id,
        is_public=update_data.get("is_public", old_asset.is_public),
        tags=update_data.get("tags", old_asset.tags),
        version=old_asset.version + 1,
        parent_id=old_asset.id,
    )

    # 旧版本设为非公开（保留但不显示在列表中）
    old_asset.is_public = False

    db.add(new_asset)
    await db.commit()
    await db.refresh(new_asset)
    return new_asset


# ---------- 删除 ----------

async def delete_asset(
    db: AsyncSession,
    asset_id: int,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> None:
    """删除资产"""
    asset = await get_asset_by_id(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    if not is_admin and asset.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权删除此资产")

    await db.delete(asset)
    await db.commit()


# ---------- 工具方法 ----------

async def increment_use_count(db: AsyncSession, asset_id: int) -> None:
    """增加使用次数"""
    asset = await get_asset_by_id(db, asset_id)
    if asset:
        asset.use_count += 1
        await db.commit()
