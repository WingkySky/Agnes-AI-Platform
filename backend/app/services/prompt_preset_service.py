# =====================================================
# 提示词预设 CRUD 服务
# 提供 PromptPreset 的增删改查业务逻辑 + 统一预设广场查询。
# 创建/更新/删除时同步写入/维护 preset_index 索引表（审核队列依赖）。
# =====================================================

from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import String, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.user import User
from app.models.prompt_preset import PromptPreset, PresetIndex, PresetFavorite, PresetRecentUse


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
    prompt_config: Optional[dict] = None,
    cover_image: Optional[str] = None,
    is_official: bool = False,
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
        prompt_config=prompt_config,
        cover_image=cover_image,
        is_official=is_official,
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


# ---------- 统一预设广场查询 ----------

# pipeline 是画布工作流配置，不是生成素材，不进广场
PLAZA_EXCLUDED_TYPES = ("pipeline",)


def _to_plaza_item(p: PromptPreset, is_favorite: bool, author: str) -> dict:
    """PromptPreset → 广场卡片统一 dict"""
    return {
        "id": p.id,
        "user_id": p.user_id,
        "name": p.name,
        "description": p.description,
        "type": p.type,
        "category": p.category,
        "tags": p.tags or [],
        "prompt_text": p.prompt_text or "",
        "camera_params": p.camera_params,
        "style_params": p.style_params,
        "prompt_config": p.prompt_config,
        "cover_image": p.cover_image,
        "cover_video": p.cover_video,
        "script_text": p.script_text,
        "is_public": p.is_public,
        "is_approved": p.is_approved,
        "is_official": p.is_official,
        "usage_count": p.usage_count,
        "author_nickname": author,
        "is_favorite": is_favorite,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


async def list_plaza(
    db: AsyncSession,
    user_id: int,
    tab: str = "plaza",
    preset_types: Optional[list[str]] = None,
    category: Optional[str] = None,
    q: Optional[str] = None,
    sort: str = "new",
    page: int = 1,
    page_size: int = 24,
) -> tuple[list[dict], int]:
    """
    统一预设广场查询。

    - tab=plaza: 自己的 + 公开审核通过的（含官方种子），sort=new/hot/name
    - tab=favorites: 当前用户收藏的，按收藏时间倒序
    - tab=recent: 当前用户最近使用的，按最后使用时间倒序
    - tab=mine: 当前用户的全部预设（含 pipeline，管理视图用）

    广场各 tab 均排除 pipeline 类型（mine 除外）；返回统一 dict，附 is_favorite / author_nickname。
    """
    offset = (page - 1) * page_size
    conditions = []
    if tab != "mine":
        conditions.append(PromptPreset.type.notin_(PLAZA_EXCLUDED_TYPES))

    if tab == "favorites":
        conditions.append(PresetFavorite.user_id == user_id)
    elif tab == "recent":
        conditions.append(PresetRecentUse.user_id == user_id)
    elif tab == "mine":
        conditions.append(PromptPreset.user_id == user_id)
    else:
        # plaza：自己的或公开审核通过的
        conditions.append(
            or_(
                PromptPreset.user_id == user_id,
                and_(
                    PromptPreset.is_public == True,  # noqa: E712
                    PromptPreset.is_approved == True,  # noqa: E712
                ),
            )
        )

    if preset_types:
        conditions.append(PromptPreset.type.in_(preset_types))
    if category:
        conditions.append(PromptPreset.category == category)
    if q:
        pattern = f"%{q}%"
        conditions.append(
            or_(
                PromptPreset.name.like(pattern),
                PromptPreset.description.like(pattern),
                # tags 为 JSON 数组，SQLite 中以 TEXT 存储按片段模糊匹配
                PromptPreset.tags.cast(String).like(pattern),
                User.nickname.like(pattern),
                User.username.like(pattern),
            )
        )

    stmt = select(PromptPreset)
    if tab == "favorites":
        stmt = stmt.join(
            PresetFavorite,
            and_(PresetFavorite.preset_id == PromptPreset.id, PresetFavorite.user_id == user_id),
        )
    elif tab == "recent":
        stmt = stmt.join(
            PresetRecentUse,
            and_(PresetRecentUse.preset_id == PromptPreset.id, PresetRecentUse.user_id == user_id),
        )
    stmt = stmt.outerjoin(User, User.id == PromptPreset.user_id)

    where = and_(*conditions)
    base_query = stmt.filter(where)

    count_stmt = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # 排序：收藏/最近使用 tab 固定按时间倒序；plaza 按 sort 参数
    if tab == "favorites":
        order_by = (PresetFavorite.created_at.desc(),)
    elif tab == "recent":
        order_by = (PresetRecentUse.last_used_at.desc(),)
    elif sort == "hot":
        order_by = (PromptPreset.is_official.desc(), PromptPreset.usage_count.desc())
    elif sort == "name":
        order_by = (PromptPreset.name.asc(),)
    else:
        order_by = (PromptPreset.created_at.desc(), PromptPreset.id.desc())

    rows = (
        await db.execute(base_query.order_by(*order_by).offset(offset).limit(page_size))
    ).scalars().all()

    # 批量取当前用户收藏状态 + 作者昵称
    fav_ids: set = set()
    if rows:
        fav_stmt = select(PresetFavorite.preset_id).filter(
            PresetFavorite.user_id == user_id,
            PresetFavorite.preset_id.in_([p.id for p in rows]),
        )
        fav_ids = {r[0] for r in (await db.execute(fav_stmt)).all()}

    author_map: dict = {}
    uids = {p.user_id for p in rows if p.user_id}
    if uids:
        u_stmt = select(User).filter(User.id.in_(list(uids)))
        for u in (await db.execute(u_stmt)).scalars().all():
            author_map[u.id] = u.nickname or u.username

    items = [
        _to_plaza_item(p, is_favorite=p.id in fav_ids, author=author_map.get(p.user_id, ""))
        for p in rows
    ]
    return items, total


async def toggle_favorite(db: AsyncSession, user_id: int, preset_id: int) -> bool:
    """收藏/取消收藏 toggle，返回操作后的收藏状态"""
    preset = await get_preset(db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")

    result = await db.execute(
        select(PresetFavorite).filter(
            and_(PresetFavorite.user_id == user_id, PresetFavorite.preset_id == preset_id)
        )
    )
    entry = result.scalar_one_or_none()
    if entry:
        await db.delete(entry)
        await db.commit()
        return False
    db.add(PresetFavorite(user_id=user_id, preset_id=preset_id))
    await db.commit()
    return True


async def record_use(db: AsyncSession, user_id: int, preset_id: int) -> None:
    """记录一次使用：upsert 最近使用记录 + 预设 usage_count+1"""
    preset = await get_preset(db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")

    result = await db.execute(
        select(PresetRecentUse).filter(
            and_(PresetRecentUse.user_id == user_id, PresetRecentUse.preset_id == preset_id)
        )
    )
    entry = result.scalar_one_or_none()
    if entry:
        entry.use_count = (entry.use_count or 0) + 1
        entry.last_used_at = datetime.utcnow()
    else:
        db.add(PresetRecentUse(user_id=user_id, preset_id=preset_id))
    preset.usage_count = (preset.usage_count or 0) + 1
    await db.commit()


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
