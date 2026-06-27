# =====================================================
# 提示词预设 CRUD 服务
# 提供 PromptPreset 的增删改查业务逻辑。
# 创建/更新/删除时同步写入/维护 preset_index 索引表。
# =====================================================

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.prompt_preset import PromptPreset, PresetIndex


# ---------- preset_index 同步辅助 ----------

async def _sync_preset_index(db: AsyncSession, preset: PromptPreset) -> None:
    """将 PromptPreset 同步写入/更新 preset_index 索引表"""
    result = await db.execute(
        select(PresetIndex).filter(
            and_(
                PresetIndex.preset_type == preset.type,
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
            preset_type=preset.type,
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


async def _remove_preset_index(db: AsyncSession, preset: PromptPreset) -> None:
    """从 preset_index 中移除对应条目"""
    result = await db.execute(
        select(PresetIndex).filter(
            and_(
                PresetIndex.preset_type == preset.type,
                PresetIndex.preset_id == preset.id,
            )
        )
    )
    entry = result.scalar_one_or_none()
    if entry:
        await db.delete(entry)
        await db.flush()


# ---------- CRUD ----------

async def create_preset(
    db: AsyncSession,
    user_id: int,
    name: str,
    prompt_text: str = "",
    description: Optional[str] = None,
    preset_type: str = "prompt",
    category: Optional[str] = None,
    tags: Optional[list] = None,
    camera_params: Optional[dict] = None,
    style_params: Optional[dict] = None,
    script_text: Optional[str] = None,
    pipeline_config: Optional[dict] = None,
    is_public: bool = False,
) -> PromptPreset:
    """创建提示词预设，并同步写入 preset_index"""
    preset = PromptPreset(
        user_id=user_id,
        name=name,
        prompt_text=prompt_text,
        description=description,
        type=preset_type,
        category=category or "通用",
        tags=tags or [],
        camera_params=camera_params,
        style_params=style_params,
        script_text=script_text,
        pipeline_config=pipeline_config,
        is_public=is_public,
    )
    db.add(preset)
    await db.flush()
    await _sync_preset_index(db, preset)
    await db.commit()
    await db.refresh(preset)
    return preset


async def get_preset(db: AsyncSession, preset_id: int) -> Optional[PromptPreset]:
    """按 ID 获取提示词预设"""
    result = await db.execute(
        select(PromptPreset).filter(PromptPreset.id == preset_id)
    )
    return result.scalar_one_or_none()


async def list_presets(
    db: AsyncSession,
    user_id: Optional[int] = None,
    preset_type: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[list[str]] = None,
    search: Optional[str] = None,
    sort: str = "new",
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[PromptPreset], int]:
    """
    列出提示词预设。

    规则:
    - 若指定 user_id，返回该用户的所有预设 + 所有公开审核通过的预设
    - 若未指定 user_id，仅返回公开且审核通过的预设
    - 支持 type / category / tags / search 过滤
    - 支持 sort: new（最新）/ hot（使用量）/ usage（使用量，同 hot）
    """
    conditions = []

    # 可见性过滤
    if user_id is not None:
        conditions.append(
            or_(
                PromptPreset.user_id == user_id,
                and_(
                    PromptPreset.is_public == True,
                    PromptPreset.is_approved == True,
                ),
            )
        )
    else:
        conditions.append(
            and_(
                PromptPreset.is_public == True,
                PromptPreset.is_approved == True,
            )
        )

    # 类型过滤
    if preset_type:
        conditions.append(PromptPreset.type == preset_type)

    # 分类过滤
    if category:
        conditions.append(PromptPreset.category == category)

    # 名称/描述搜索
    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            or_(
                PromptPreset.name.like(search_pattern),
                PromptPreset.description.like(search_pattern),
            )
        )

    where = and_(*conditions)

    # 排序
    if sort in ("hot", "usage"):
        order_by = PromptPreset.usage_count.desc()
    else:
        order_by = PromptPreset.updated_at.desc()

    # 查询
    base_query = select(PromptPreset).filter(where)

    # 总数
    count_result = await db.execute(base_query)
    total = len(count_result.scalars().all())

    # 分页
    result = await db.execute(
        base_query.order_by(order_by).offset(offset).limit(limit)
    )
    presets = result.scalars().all()

    return list(presets), total


async def update_preset(
    db: AsyncSession,
    preset_id: int,
    **kwargs,
) -> PromptPreset:
    """更新提示词预设（仅更新传入的非 None 字段），并同步 preset_index"""
    preset = await get_preset(db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="提示词预设不存在")

    for key, value in kwargs.items():
        if value is not None and hasattr(preset, key):
            setattr(preset, key, value)

    await db.flush()
    await _sync_preset_index(db, preset)
    await db.commit()
    await db.refresh(preset)
    return preset


async def delete_preset(db: AsyncSession, preset_id: int) -> bool:
    """删除提示词预设，并同步移除 preset_index 条目"""
    preset = await get_preset(db, preset_id)
    if not preset:
        return False
    await _remove_preset_index(db, preset)
    await db.delete(preset)
    await db.commit()
    return True
