# =====================================================
# 实体素材版本管理共享逻辑
#
# 角色/场景/道具三类实体的 ProjectEntityAsset 多版本管理
# （列表/切换/删除/上传）逻辑完全一致，统一抽到此模块。
#
# 各实体服务（character_service / scene_service / prop_service）
# 通过传入 entity_type 复用本模块的函数。
# =====================================================

from typing import List, Optional, Tuple
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    Project,
    ProjectCharacter,
    ProjectScene,
    ProjectProp,
    ProjectEntityAsset,
)
from app.services.project.sse_manager import project_sse_manager


# 实体类型 → ORM 模型 映射
_ENTITY_MODEL = {
    "character": ProjectCharacter,
    "scene": ProjectScene,
    "prop": ProjectProp,
}


# =====================================================
# 内部工具
# =====================================================

async def _get_entity(
    db: AsyncSession, entity_type: str, entity_id: int
):
    """获取实体对象（按 entity_type 路由到对应表）"""
    model = _ENTITY_MODEL.get(entity_type)
    if not model:
        raise ValueError(f"不支持的实体类型: {entity_type}")
    result = await db.execute(select(model).where(model.id == entity_id))
    return result.scalar_one_or_none()


async def _next_version(
    db: AsyncSession, entity_type: str, entity_id: int
) -> int:
    """计算下一个版本号"""
    result = await db.execute(
        select(func.max(ProjectEntityAsset.version)).where(
            ProjectEntityAsset.entity_type == entity_type,
            ProjectEntityAsset.entity_id == entity_id,
        )
    )
    cur = result.scalar()
    return (cur or 0) + 1


async def _reset_active_flags(
    db: AsyncSession, entity_type: str, entity_id: int
) -> None:
    """将该实体所有版本的 is_active 置为 False"""
    await db.execute(
        update(ProjectEntityAsset)
        .where(
            ProjectEntityAsset.entity_type == entity_type,
            ProjectEntityAsset.entity_id == entity_id,
        )
        .values(is_active=False)
    )


# =====================================================
# 版本管理 API（供 character/scene/prop 服务调用）
# =====================================================

async def list_versions(
    db: AsyncSession, entity_type: str, entity_id: int
) -> List[ProjectEntityAsset]:
    """列出某实体的所有版本（按版本号倒序，激活版优先）"""
    result = await db.execute(
        select(ProjectEntityAsset)
        .where(
            ProjectEntityAsset.entity_type == entity_type,
            ProjectEntityAsset.entity_id == entity_id,
        )
        .order_by(ProjectEntityAsset.version.desc())
    )
    return result.scalars().all()


async def get_version(
    db: AsyncSession, version_id: int
) -> Optional[ProjectEntityAsset]:
    """获取版本记录"""
    result = await db.execute(
        select(ProjectEntityAsset).where(ProjectEntityAsset.id == version_id)
    )
    return result.scalar_one_or_none()


async def set_active_version(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    version_id: int,
) -> Optional[ProjectEntityAsset]:
    """
    设为采用版：
    1. 校验版本归属该实体
    2. 重置同实体其他版本 is_active=False
    3. 目标版本 is_active=True
    4. 写回实体表的 active_image_id
    5. 推送 SSE active_version_changed
    """
    asset = await get_version(db, version_id)
    if not asset or asset.entity_type != entity_type or asset.entity_id != entity_id:
        return None

    await _reset_active_flags(db, entity_type, entity_id)
    asset.is_active = True

    # 同步实体表的 active_image_id 指针
    entity = await _get_entity(db, entity_type, entity_id)
    if entity:
        entity.active_image_id = asset.id

    await db.commit()
    await db.refresh(asset)

    if entity:
        await project_sse_manager.push(
            entity.project_id,
            "active_version_changed",
            {
                "target": f"{entity_type}:{entity_id}",
                "version_id": version_id,
                "file_url": asset.file_url,
            },
        )
    return asset


async def delete_version(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    version_id: int,
) -> bool:
    """
    删除版本：
    - 不允许删除当前激活版（返回 False）
    - 删除后若实体 active_image_id 指向该版本，置空
    """
    asset = await get_version(db, version_id)
    if not asset or asset.entity_type != entity_type or asset.entity_id != entity_id:
        return False
    if asset.is_active:
        return False  # 不允许删除激活版

    await db.delete(asset)

    # 若实体指针指向该版本，置空
    entity = await _get_entity(db, entity_type, entity_id)
    if entity and entity.active_image_id == version_id:
        entity.active_image_id = None

    await db.commit()
    return True


async def create_version(
    db: AsyncSession,
    project_id: int,
    entity_type: str,
    entity_id: int,
    *,
    file_url: str = "",
    thumbnail_url: str = "",
    prompt: str = "",
    model: str = "",
    generation_id: Optional[int] = None,
    file_type: str = "image",
    file_size: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    is_manual: bool = False,
    set_active: bool = True,
) -> Tuple[ProjectEntityAsset, bool]:
    """
    新建一个版本（生成 / 上传 / 导入共用入口）

    Args:
        set_active: 是否同时设为激活版（默认 True）
    Returns:
        (asset, became_active)
    """
    version_no = await _next_version(db, entity_type, entity_id)

    if set_active:
        await _reset_active_flags(db, entity_type, entity_id)

    asset = ProjectEntityAsset(
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        version=version_no,
        is_active=set_active,
        is_manual=is_manual,
        file_url=file_url or None,
        thumbnail_url=thumbnail_url or None,
        prompt=prompt or None,
        model=model or None,
        generation_id=generation_id,
        file_type=file_type,
        file_size=file_size,
        width=width,
        height=height,
        created_by="manual" if is_manual else "ai",
    )
    db.add(asset)
    await db.flush()  # 拿到 asset.id

    # 同步实体指针
    if set_active:
        entity = await _get_entity(db, entity_type, entity_id)
        if entity:
            entity.active_image_id = asset.id

    await db.commit()
    await db.refresh(asset)

    if set_active:
        await project_sse_manager.push(
            project_id,
            "active_version_changed",
            {
                "target": f"{entity_type}:{entity_id}",
                "version_id": asset.id,
                "file_url": asset.file_url,
            },
        )
    return asset, set_active
