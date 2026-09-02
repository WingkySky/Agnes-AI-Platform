# =====================================================
# 资产库服务
# =====================================================

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.generation import Generation
from app.schemas.assets import AssetSaveFromGenerationRequest

# 允许的资产类型
VALID_ASSET_TYPES = {"character", "prop", "scene", "brand", "material", "clip", "final"}


async def get_asset_by_id(db: AsyncSession, asset_id: int) -> Optional[Asset]:
    """根据 ID 获取资产"""
    result = await db.execute(select(Asset).filter(Asset.id == asset_id))
    return result.scalar_one_or_none()


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

    # 幂等：同一生成记录只保存一份资产（已自动归档或已手动保存时直接返回已有记录）
    existing = (await db.execute(
        select(Asset).filter(
            Asset.source_generation_id == generation.id,
            Asset.user_id == user_id,
        ).limit(1)
    )).scalar_one_or_none()
    if existing:
        return existing

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
        source_generation_id=generation.id,
        kind="video" if generation.type == "video" else "image",
        asset_url=generation.result_url,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


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


async def increment_use_count(db: AsyncSession, asset_id: int) -> None:
    """增加使用次数"""
    asset = await get_asset_by_id(db, asset_id)
    if asset:
        asset.use_count += 1
        await db.commit()
