# =====================================================
# 剧本模板服务
# 提供剧本模板的 CRUD、查询等功能
# =====================================================

import logging
from typing import List, Optional, Dict, Any

from fastapi import HTTPException
from jinja2 import Template
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline import ScriptTemplate
from app.schemas.assets import ScriptTemplateCreate, ScriptTemplateUpdate

logger = logging.getLogger("agnes_platform")


# ---------- 查询 ----------

async def get_script_template_by_id(db: AsyncSession, tpl_id: int) -> Optional[ScriptTemplate]:
    """根据 ID 获取剧本模板"""
    result = await db.execute(select(ScriptTemplate).filter(ScriptTemplate.id == tpl_id))
    return result.scalar_one_or_none()


async def get_script_template_by_key(db: AsyncSession, key: str) -> Optional[ScriptTemplate]:
    """根据 key 获取剧本模板"""
    result = await db.execute(select(ScriptTemplate).filter(ScriptTemplate.key == key))
    return result.scalar_one_or_none()


async def list_script_templates(
    db: AsyncSession,
    category: Optional[str] = None,
    search: Optional[str] = None,
    is_builtin: Optional[bool] = None,
    is_public: Optional[bool] = None,
    author_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[List[ScriptTemplate], int]:
    """获取剧本模板列表（支持分页、筛选、搜索）"""
    query = select(ScriptTemplate)

    filters = []
    if category:
        filters.append(ScriptTemplate.category == category)
    if is_builtin is not None:
        filters.append(ScriptTemplate.is_builtin == is_builtin)
    if is_public is not None:
        filters.append(ScriptTemplate.is_public == is_public)
    if author_id is not None:
        filters.append(ScriptTemplate.author_id == author_id)
    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            ScriptTemplate.name.ilike(search_pattern),
            ScriptTemplate.description.ilike(search_pattern),
            ScriptTemplate.key.ilike(search_pattern),
        ))

    if filters:
        query = query.where(*filters)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(
        ScriptTemplate.is_builtin.desc(),
        ScriptTemplate.id.asc(),
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()
    return list(items), total


# ---------- 创建 ----------

async def create_script_template(
    db: AsyncSession,
    data: ScriptTemplateCreate,
    author_id: Optional[int] = None,
    is_builtin: bool = False,
) -> ScriptTemplate:
    """创建剧本模板"""
    existing = await get_script_template_by_key(db, data.key)
    if existing:
        raise HTTPException(status_code=400, detail=f"剧本模板 key '{data.key}' 已存在")

    tpl = ScriptTemplate(
        key=data.key,
        name=data.name,
        description=data.description,
        category=data.category,
        structure=data.structure,
        prompt_template=data.prompt_template,
        output_schema=data.output_schema,
        scenes_min=data.scenes_min,
        scenes_max=data.scenes_max,
        default_scene_duration=data.default_scene_duration,
        is_builtin=is_builtin,
        is_public=data.is_public if not is_builtin else True,
        author_id=author_id,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return tpl


# ---------- 更新 ----------

async def update_script_template(
    db: AsyncSession,
    tpl_id: int,
    data: ScriptTemplateUpdate,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> ScriptTemplate:
    """更新剧本模板"""
    tpl = await get_script_template_by_id(db, tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="剧本模板不存在")

    if not is_admin and tpl.author_id != user_id:
        raise HTTPException(status_code=403, detail="无权修改此剧本模板")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(tpl, field) and value is not None:
            setattr(tpl, field, value)

    await db.commit()
    await db.refresh(tpl)
    return tpl


# ---------- 删除 ----------

async def delete_script_template(
    db: AsyncSession,
    tpl_id: int,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> None:
    """删除剧本模板"""
    tpl = await get_script_template_by_id(db, tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="剧本模板不存在")

    if tpl.is_builtin:
        raise HTTPException(status_code=400, detail="内置剧本模板不可删除")

    if not is_admin and tpl.author_id != user_id:
        raise HTTPException(status_code=403, detail="无权删除此剧本模板")

    await db.delete(tpl)
    await db.commit()


# ---------- 渲染提示词 ----------

def render_prompt_template(
    template_text: str,
    variables: Dict[str, Any],
) -> str:
    """
    使用 Jinja2 渲染剧本提示词模板。

    Args:
        template_text: 模板文本（Jinja2 语法）
        variables: 模板变量字典

    Returns:
        渲染后的提示词
    """
    try:
        template = Template(template_text)
        return template.render(**variables)
    except Exception as e:
        logger.warning(f"剧本模板渲染失败，回退到简单替换: {e}")
        # 回退：简单的 {{key}} 替换
        result = template_text
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result
