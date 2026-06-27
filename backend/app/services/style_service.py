# =====================================================
# 风格预设服务
# 提供风格预设的 CRUD、查询、缓存等功能
# =====================================================

import logging
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline import StylePreset
from app.schemas.assets import StylePresetCreate, StylePresetUpdate

logger = logging.getLogger("agnes_platform")


# ---------- 查询 ----------

async def get_style_by_id(db: AsyncSession, style_id: int) -> Optional[StylePreset]:
    """根据 ID 获取风格预设"""
    result = await db.execute(select(StylePreset).filter(StylePreset.id == style_id))
    return result.scalar_one_or_none()


async def get_style_by_key(db: AsyncSession, key: str) -> Optional[StylePreset]:
    """根据 key 获取风格预设"""
    result = await db.execute(select(StylePreset).filter(StylePreset.key == key))
    return result.scalar_one_or_none()


async def list_styles(
    db: AsyncSession,
    category: Optional[str] = None,
    search: Optional[str] = None,
    is_builtin: Optional[bool] = None,
    is_public: Optional[bool] = None,
    author_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[List[StylePreset], int]:
    """
    获取风格预设列表（支持分页、筛选、搜索）

    返回: (items, total)
    """
    query = select(StylePreset)

    # 筛选条件
    filters = []
    if category:
        filters.append(StylePreset.category == category)
    if is_builtin is not None:
        filters.append(StylePreset.is_builtin == is_builtin)
    if is_public is not None:
        filters.append(StylePreset.is_public == is_public)
    if author_id is not None:
        filters.append(StylePreset.author_id == author_id)
    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            StylePreset.name.ilike(search_pattern),
            StylePreset.description.ilike(search_pattern),
            StylePreset.key.ilike(search_pattern),
        ))

    if filters:
        query = query.where(*filters)

    # 总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # 分页 + 排序（内置优先，按使用次数排序）
    query = query.order_by(
        StylePreset.is_builtin.desc(),
        StylePreset.use_count.desc(),
        StylePreset.id.asc(),
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    return list(items), total


# ---------- 创建 ----------

async def create_style(
    db: AsyncSession,
    data: StylePresetCreate,
    author_id: Optional[int] = None,
    is_builtin: bool = False,
) -> StylePreset:
    """创建风格预设"""
    # 检查 key 是否已存在
    existing = await get_style_by_key(db, data.key)
    if existing:
        raise HTTPException(status_code=400, detail=f"风格 key '{data.key}' 已存在")

    style = StylePreset(
        key=data.key,
        name=data.name,
        description=data.description,
        category=data.category,
        visual_prefix=data.visual_prefix,
        lighting=data.lighting,
        color_palette=data.color_palette,
        quality_suffix=data.quality_suffix,
        negative_prompt=data.negative_prompt,
        camera_language=data.camera_language,
        mood_keywords=data.mood_keywords,
        preview_image=data.preview_image,
        is_builtin=is_builtin,
        is_public=data.is_public if not is_builtin else True,
        author_id=author_id,
    )
    db.add(style)
    await db.commit()
    await db.refresh(style)
    return style


# ---------- 更新 ----------

async def update_style(
    db: AsyncSession,
    style_id: int,
    data: StylePresetUpdate,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> StylePreset:
    """更新风格预设"""
    style = await get_style_by_id(db, style_id)
    if not style:
        raise HTTPException(status_code=404, detail="风格预设不存在")

    # 权限检查：只有作者或管理员可以修改
    if not is_admin and style.author_id != user_id:
        raise HTTPException(status_code=403, detail="无权修改此风格预设")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(style, field) and value is not None:
            setattr(style, field, value)

    await db.commit()
    await db.refresh(style)
    return style


# ---------- 删除 ----------

async def delete_style(
    db: AsyncSession,
    style_id: int,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> None:
    """删除风格预设"""
    style = await get_style_by_id(db, style_id)
    if not style:
        raise HTTPException(status_code=404, detail="风格预设不存在")

    # 内置风格不可删除
    if style.is_builtin:
        raise HTTPException(status_code=400, detail="内置风格预设不可删除")

    # 权限检查
    if not is_admin and style.author_id != user_id:
        raise HTTPException(status_code=403, detail="无权删除此风格预设")

    await db.delete(style)
    await db.commit()


# ---------- 工具方法 ----------

async def increment_use_count(db: AsyncSession, style_id: int) -> None:
    """增加使用次数（使用后调用）"""
    style = await get_style_by_id(db, style_id)
    if style:
        style.use_count += 1
        await db.commit()


def build_prompt_with_style(base_prompt: str, style: StylePreset) -> tuple[str, str]:
    """
    将风格预设应用到提示词上。

    返回: (增强后的正向提示词, 负面提示词)
    """
    parts = []

    # 视觉风格前缀
    if style.visual_prefix:
        parts.append(style.visual_prefix)

    # 主体描述
    parts.append(base_prompt)

    # 光影
    if style.lighting:
        parts.append(style.lighting)

    # 配色
    if style.color_palette:
        parts.append(style.color_palette)

    # 镜头语言
    if style.camera_language:
        parts.append(style.camera_language)

    # 氛围关键词
    if style.mood_keywords:
        parts.append(style.mood_keywords)

    # 品质词
    if style.quality_suffix:
        parts.append(style.quality_suffix)

    positive = ", ".join(parts)
    negative = style.negative_prompt or ""

    return positive, negative


def build_negative_prompt_suffix(style: StylePreset) -> str:
    """
    构建图片负面提示词后缀（拼接到 prompt 末尾）。

    Agnes Image API 不支持 negative_prompt 参数（官方文档参数表无此字段），
    只能用自然语言描述避免内容。格式：avoid: xxx, yyy, zzz

    Args:
        style: 风格预设

    Returns:
        负面提示词后缀字符串（如 "avoid: color, photorealistic, 3d render"）；
        如风格无 negative_prompt，返回空字符串
    """
    negative = (style.negative_prompt or "").strip()
    if not negative:
        return ""
    return f"avoid: {negative}"
