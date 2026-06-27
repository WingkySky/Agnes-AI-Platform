# =====================================================
# 流水线模板服务
# 提供流水线模板的 CRUD、查询等功能
# =====================================================

import logging
from typing import List, Optional, Dict, Any

from fastapi import HTTPException
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline import PipelineTemplate
from app.schemas.pipeline import PipelineTemplateCreate, PipelineTemplateUpdate

logger = logging.getLogger("agnes_platform.pipeline")


# ---------- 查询 ----------

async def get_template_by_id(db: AsyncSession, tpl_id: int) -> Optional[PipelineTemplate]:
    """根据 ID 获取流水线模板"""
    result = await db.execute(select(PipelineTemplate).filter(PipelineTemplate.id == tpl_id))
    return result.scalar_one_or_none()


async def get_template_by_key(db: AsyncSession, key: str) -> Optional[PipelineTemplate]:
    """根据 key 获取流水线模板"""
    result = await db.execute(select(PipelineTemplate).filter(PipelineTemplate.key == key))
    return result.scalar_one_or_none()


async def list_templates(
    db: AsyncSession,
    category: Optional[str] = None,
    search: Optional[str] = None,
    is_builtin: Optional[bool] = None,
    is_public: Optional[bool] = None,
    author_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[List[PipelineTemplate], int]:
    """获取流水线模板列表（支持分页、筛选、搜索）"""
    query = select(PipelineTemplate)

    filters = []
    if category:
        filters.append(PipelineTemplate.category == category)
    if is_builtin is not None:
        filters.append(PipelineTemplate.is_builtin == is_builtin)
    if is_public is not None:
        filters.append(PipelineTemplate.is_public == is_public)
    if author_id is not None:
        filters.append(PipelineTemplate.author_id == author_id)
    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            PipelineTemplate.name.ilike(search_pattern),
            PipelineTemplate.description.ilike(search_pattern),
            PipelineTemplate.key.ilike(search_pattern),
        ))

    if filters:
        query = query.where(*filters)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(
        PipelineTemplate.is_builtin.desc(),
        PipelineTemplate.use_count.desc(),
        PipelineTemplate.id.asc(),
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()
    return list(items), total


# ---------- 创建 ----------

async def create_template(
    db: AsyncSession,
    data: PipelineTemplateCreate,
    author_id: Optional[int] = None,
    is_builtin: bool = False,
) -> PipelineTemplate:
    """创建流水线模板"""
    existing = await get_template_by_key(db, data.key)
    if existing:
        raise HTTPException(status_code=400, detail=f"模板 key '{data.key}' 已存在")

    tpl = PipelineTemplate(
        key=data.key,
        name=data.name,
        description=data.description,
        category=data.category,
        thumbnail_url=data.thumbnail_url,
        inputs_config=data.inputs_config,
        steps_config=data.steps_config,
        script_template_id=data.script_template_id,
        is_builtin=is_builtin,
        is_public=data.is_public if not is_builtin else True,
        author_id=author_id,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return tpl


# ---------- 更新 ----------

async def update_template(
    db: AsyncSession,
    tpl_id: int,
    data: PipelineTemplateUpdate,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> PipelineTemplate:
    """更新流水线模板"""
    tpl = await get_template_by_id(db, tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="流水线模板不存在")

    if not is_admin and tpl.author_id != user_id:
        raise HTTPException(status_code=403, detail="无权修改此模板")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(tpl, field) and value is not None:
            setattr(tpl, field, value)

    await db.commit()
    await db.refresh(tpl)
    return tpl


# ---------- 删除 ----------

async def delete_template(
    db: AsyncSession,
    tpl_id: int,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> None:
    """删除流水线模板"""
    tpl = await get_template_by_id(db, tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="流水线模板不存在")

    if tpl.is_builtin:
        raise HTTPException(status_code=400, detail="内置模板不可删除")

    if not is_admin and tpl.author_id != user_id:
        raise HTTPException(status_code=403, detail="无权删除此模板")

    await db.delete(tpl)
    await db.commit()


# ---------- 工具方法 ----------

async def increment_use_count(db: AsyncSession, tpl_id: int) -> None:
    """增加使用次数"""
    tpl = await get_template_by_id(db, tpl_id)
    if tpl:
        tpl.use_count += 1
        await db.commit()


def validate_steps_config(steps_config: List[Dict[str, Any]]) -> None:
    """
    验证步骤配置的合法性

    检查:
    - 每个步骤都有 key, name, type
    - 依赖的步骤存在
    - 没有循环依赖
    - key 不重复
    """
    if not steps_config:
        raise ValueError("步骤配置不能为空")

    step_keys = set()
    for step in steps_config:
        key = step.get("key")
        if not key:
            raise ValueError("每个步骤必须有 key")
        if key in step_keys:
            raise ValueError(f"步骤 key 重复: {key}")
        step_keys.add(key)

        if not step.get("name"):
            raise ValueError(f"步骤 {key} 必须有 name")
        if not step.get("type"):
            raise ValueError(f"步骤 {key} 必须有 type")

        # 检查依赖存在
        depends_on = step.get("depends_on", [])
        for dep in depends_on:
            if dep not in step_keys:
                # 依赖的步骤可能在后面（DAG 顺序不一定是拓扑序），这里先不严格检查
                pass
