# =====================================================
# 资产桥接 — 公共资产库 ↔ 项目实体（C2 引用模式）
#
# 双向桥接:
#   1. import_asset_to_project: 从资产库导入到项目（创建实体并引用 asset_id）
#   2. promote_entity_to_asset: 从项目实体沉淀到资产库（创建 Asset，需审核后公开）
#
# 设计要点:
#   - 引用关系记录在 project_characters/scenes/props.asset_id 字段
#   - 资产库的 reference_images 作为初始形象图来源
#   - 沉淀到资产库时默认 is_public=False（需用户后续公开审核）
# =====================================================

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.project import (
    Project,
    ProjectCharacter,
    ProjectScene,
    ProjectProp,
    ProjectEntityAsset,
)
from app.services.project._entity_versions import create_version

logger = logging.getLogger("agnes_platform.project.asset_bridge")


# 实体类型 → ORM 模型 + 资产类型 映射
_ENTITY_TO_ASSET_TYPE = {
    "character": (ProjectCharacter, "character"),
    "scene": (ProjectScene, "scene"),
    "prop": (ProjectProp, "prop"),
}


# =====================================================
# 资产库 → 项目（导入引用）
# =====================================================

async def import_asset_to_project(
    db: AsyncSession,
    asset_id: int,
    project_id: int,
    entity_type: str,
    user_id: int,
):
    """
    从资产库导入到项目（创建项目实体并引用 asset_id）

    Args:
        asset_id: 资产库 ID
        project_id: 目标项目 ID
        entity_type: character / scene / prop
        user_id: 操作用户 ID
    Returns:
        新创建的项目实体
    """
    model, asset_type = _ENTITY_TO_ASSET_TYPE.get(entity_type, (None, None))
    if not model:
        raise ValueError(f"不支持的实体类型: {entity_type}")

    # 获取资产
    asset = (
        await db.execute(select(Asset).where(Asset.id == asset_id))
    ).scalar_one_or_none()
    if not asset:
        raise ValueError(f"资产 {asset_id} 不存在")

    # 创建项目实体（按类型设置字段）
    common_kwargs = {
        "project_id": project_id,
        "name": asset.name,
        "description": asset.description,
        "asset_id": asset.id,
    }
    if entity_type == "character":
        entity = ProjectCharacter(
            **common_kwargs,
            appearance_desc=asset.visual_description,
            role_type="supporting",
        )
    elif entity_type == "scene":
        entity = ProjectScene(
            **common_kwargs,
            location=None,
            time_of_day=None,
            atmosphere=asset.visual_description,
        )
    else:  # prop
        entity = ProjectProp(
            **common_kwargs,
            visual_desc=asset.visual_description,
        )

    db.add(entity)
    await db.flush()  # 拿到 entity.id

    # 若资产有参考图，作为初始版本导入到 ProjectEntityAsset
    ref_images = asset.reference_images or []
    if ref_images:
        first_url = ref_images[0]
        await create_version(
            db,
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity.id,
            file_url=first_url,
            thumbnail_url=first_url,
            prompt=f"(从资产库导入: {asset.name})",
            model="import",
            file_type="image",
            is_manual=False,
            set_active=True,
        )

    await db.commit()
    await db.refresh(entity)
    return entity


# =====================================================
# 项目 → 资产库（沉淀）
# =====================================================

async def promote_entity_to_asset(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    user_id: int,
) -> Asset:
    """
    从项目实体沉淀到资产库（创建 Asset，默认 is_public=False）

    Args:
        entity_type: character / scene / prop
        entity_id: 项目实体 ID
        user_id: 操作用户 ID（资产归属）
    Returns:
        新创建的 Asset
    """
    model, asset_type = _ENTITY_TO_ASSET_TYPE.get(entity_type, (None, None))
    if not model:
        raise ValueError(f"不支持的实体类型: {entity_type}")

    entity = (
        await db.execute(select(model).where(model.id == entity_id))
    ).scalar_one_or_none()
    if not entity:
        raise ValueError(f"实体 {entity_type}:{entity_id} 不存在")

    # 收集实体的形象图 URL（激活版优先，否则取最新版本）
    ref_urls: list = []
    if entity.active_image_id:
        asset_record = (
            await db.execute(
                select(ProjectEntityAsset).where(
                    ProjectEntityAsset.id == entity.active_image_id
                )
            )
        ).scalar_one_or_none()
        if asset_record and asset_record.file_url:
            ref_urls = [asset_record.file_url]
    if not ref_urls:
        # 取该实体的最新版本
        recent = (
            await db.execute(
                select(ProjectEntityAsset)
                .where(
                    ProjectEntityAsset.entity_type == entity_type,
                    ProjectEntityAsset.entity_id == entity_id,
                )
                .order_by(ProjectEntityAsset.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if recent and recent.file_url:
            ref_urls = [recent.file_url]

    # 视觉描述按类型取
    if entity_type == "character":
        visual_desc = entity.appearance_desc or entity.description or entity.name
    elif entity_type == "scene":
        visual_desc = entity.atmosphere or entity.description or entity.name
    else:  # prop
        visual_desc = entity.visual_desc or entity.description or entity.name

    # 创建资产（默认私有，需用户后续公开审核）
    new_asset = Asset(
        type=asset_type,
        name=entity.name,
        description=entity.description or "",
        visual_description=visual_desc,
        reference_images=ref_urls,
        user_id=user_id,
        is_public=False,
        moderation_status="approved",  # 私有资产默认通过
        tags=[],
        version=1,
    )
    db.add(new_asset)
    await db.commit()
    await db.refresh(new_asset)

    # 回写 entity.asset_id（建立引用关系）
    entity.asset_id = new_asset.id
    await db.commit()

    logger.info(
        f"实体 {entity_type}:{entity_id} 沉淀为资产 asset_id={new_asset.id}"
    )
    return new_asset
