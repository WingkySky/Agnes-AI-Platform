# =====================================================
# 摄像机预设 CRUD 服务
# 提供 CameraPreset 的增删改查业务逻辑。
# 创建/更新/删除时同步写入/维护 preset_index 索引表。
# =====================================================

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.camera_preset import CameraPreset
from app.models.prompt_preset import PresetIndex


# ---------- preset_index 同步辅助 ----------

async def _sync_preset_index(db: AsyncSession, preset: CameraPreset) -> None:
    """将 CameraPreset 同步写入/更新 preset_index 索引表"""
    result = await db.execute(
        select(PresetIndex).filter(
            and_(
                PresetIndex.preset_type == "camera",
                PresetIndex.preset_id == preset.id,
            )
        )
    )
    entry = result.scalar_one_or_none()

    if entry:
        # 更新已有索引
        entry.category = preset.category
        entry.tags = preset.tags
        entry.user_id = preset.user_id
        entry.is_public = preset.is_public
        entry.is_approved = preset.is_approved
        entry.is_rejected = preset.is_rejected
        entry.usage_count = preset.usage_count
        entry.name = preset.name
        entry.description = preset.description
    else:
        # 新建索引
        entry = PresetIndex(
            preset_type="camera",
            preset_id=preset.id,
            category=preset.category,
            tags=preset.tags,
            user_id=preset.user_id,
            is_public=preset.is_public,
            is_approved=preset.is_approved,
            is_rejected=preset.is_rejected,
            usage_count=preset.usage_count,
            name=preset.name,
            description=preset.description,
        )
        db.add(entry)

    await db.flush()


async def _remove_camera_preset_index(db: AsyncSession, preset: CameraPreset) -> None:
    """从 preset_index 中移除 CameraPreset 对应条目"""
    result = await db.execute(
        select(PresetIndex).filter(
            and_(
                PresetIndex.preset_type == "camera",
                PresetIndex.preset_id == preset.id,
            )
        )
    )
    entry = result.scalar_one_or_none()
    if entry:
        await db.delete(entry)
        await db.flush()


async def create_preset(
    db: AsyncSession,
    user_id: int,
    name: str,
    description: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[list] = None,
    camera_model: Optional[str] = None,
    focal_length: Optional[str] = None,
    aperture: Optional[str] = None,
    depth_of_field: Optional[str] = None,
    shutter_speed: Optional[str] = None,
    shutter_angle: Optional[str] = None,
    camera_movement: Optional[str] = None,
    camera_angle: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
    visual_style: Optional[str] = None,
    is_public: bool = False,
) -> CameraPreset:
    """创建摄像机预设"""
    preset = CameraPreset(
        user_id=user_id,
        name=name,
        description=description,
        type="camera",
        category=category or "通用",
        tags=tags or [],
        camera_model=camera_model,
        focal_length=focal_length,
        aperture=aperture,
        depth_of_field=depth_of_field,
        shutter_speed=shutter_speed,
        shutter_angle=shutter_angle,
        camera_movement=camera_movement,
        camera_angle=camera_angle,
        aspect_ratio=aspect_ratio,
        visual_style=visual_style,
        is_public=is_public,
    )
    db.add(preset)
    await db.flush()
    await _sync_preset_index(db, preset)
    await db.commit()
    await db.refresh(preset)
    return preset


async def get_preset(db: AsyncSession, preset_id: int) -> Optional[CameraPreset]:
    """按 ID 获取摄像机预设"""
    result = await db.execute(select(CameraPreset).filter(CameraPreset.id == preset_id))
    return result.scalar_one_or_none()


async def list_presets(
    db: AsyncSession,
    user_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None,
    category: Optional[str] = None,
    is_public: Optional[bool] = None,
) -> tuple[list[CameraPreset], int]:
    """
    列出摄像机预设。

    规则:
    - 若指定 user_id，则返回该用户的所有预设 + 所有公开预设
    - 若未指定 user_id，则仅返回公开且审核通过的预设
    - 支持按 name/description 模糊搜索（search）
    - 支持按 category 过滤
    - 支持按 is_public 过滤（仅对当前用户预设生效）
    """
    conditions = []
    if user_id is not None:
        # 自己的所有预设 + 公开预设
        conditions.append(
            or_(
                CameraPreset.user_id == user_id,
                and_(CameraPreset.is_public == True, CameraPreset.is_approved == True),
            )
        )
    else:
        conditions.append(
            and_(CameraPreset.is_public == True, CameraPreset.is_approved == True)
        )

    # 按分类过滤
    if category:
        conditions.append(CameraPreset.category == category)

    # 按公开状态过滤（仅过滤自己的预设时常用）
    if is_public is not None:
        conditions.append(CameraPreset.is_public == is_public)

    # 名称/描述搜索
    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            or_(
                CameraPreset.name.like(search_pattern),
                CameraPreset.description.like(search_pattern),
            )
        )

    where = and_(*conditions) if conditions else None

    # 计数（用 count 替代全量加载，提高效率）
    from sqlalchemy import func
    count_query = select(func.count(CameraPreset.id))
    if where is not None:
        count_query = count_query.filter(where)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # 分页查询
    list_query = select(CameraPreset).order_by(CameraPreset.updated_at.desc())
    if where is not None:
        list_query = list_query.filter(where)
    result = await db.execute(
        list_query.offset(offset).limit(limit)
    )
    presets = result.scalars().all()

    return list(presets), total


async def update_preset(
    db: AsyncSession,
    preset_id: int,
    **kwargs,
) -> CameraPreset:
    """更新摄像机预设（仅更新传入的非 None 字段）"""
    preset = await get_preset(db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="摄像机预设不存在")

    for key, value in kwargs.items():
        if value is not None and hasattr(preset, key):
            setattr(preset, key, value)

    await db.flush()
    await _sync_preset_index(db, preset)
    await db.commit()
    await db.refresh(preset)
    return preset


async def delete_preset(db: AsyncSession, preset_id: int) -> bool:
    """删除摄像机预设"""
    preset = await get_preset(db, preset_id)
    if not preset:
        return False
    await _remove_camera_preset_index(db, preset)
    await db.delete(preset)
    await db.commit()
    return True
