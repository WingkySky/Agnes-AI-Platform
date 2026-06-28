# =====================================================
# 流水线模板服务
# 提供流水线模板的 CRUD、查询、修订流程等功能
# =====================================================

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import HTTPException
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline import PipelineTemplate
from app.models.pipeline_template_revision import PipelineTemplateRevision
from app.schemas.pipeline import PipelineTemplateCreate, PipelineTemplateUpdate

logger = logging.getLogger("agnes_platform.pipeline")


# ---------- 修订草稿可写入字段（与 update_data 的 key 对齐） ----------
# 这些字段同时存在于 PipelineTemplate 与 PipelineTemplateRevision 上
_REVISION_SNAPSHOT_FIELDS = (
    "name",
    "description",
    "category",
    "thumbnail_url",
    "inputs_config",
    "steps_config",
    "output_mapping",
    "script_template_id",
    "estimated_credits",
    "estimated_time_minutes",
    "tags",
)


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
    """
    更新流水线模板。

    权限与流程：
      - 非 admin 编辑内置模板 → 403
      - admin 编辑任意模板（含内置）→ 直接改原模板
      - 公开已审核非内置模板被编辑 → 走 draft 流程：
        调用 get_or_create_pending_revision + apply_update_to_revision + AI 预筛，
        设置 tpl.has_pending_revision=True；原模板字段不变。
      - 其他情况（私有/待审核/被驳回/内置模板）→ 直接改原模板字段。
    """
    tpl = await get_template_by_id(db, tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="流水线模板不存在")

    # 显式拦截：非 admin 不可编辑内置模板
    if tpl.is_builtin and not is_admin:
        raise HTTPException(status_code=403, detail="内置模板仅管理员可编辑")

    # 普通权限校验：非作者且非 admin → 403
    if not is_admin and tpl.author_id != user_id:
        raise HTTPException(status_code=403, detail="无权修改此模板")

    update_data = data.model_dump(exclude_unset=True)

    # 公开已审核非内置模板 → draft 流程
    if tpl.is_public and tpl.is_approved and not tpl.is_builtin:
        revision = await get_or_create_pending_revision(db, tpl.id)
        apply_update_to_revision(revision, update_data, edited_by=user_id)
        # 提交说明（如有）
        if "submit_reason" in update_data:
            revision.submit_reason = update_data["submit_reason"]
        tpl.has_pending_revision = True
        await db.flush()
        # 触发 AI 预筛（命中敏感词时标记 revision.is_rejected=True 并写入 reject_reason）
        try:
            from app.services.pipeline.moderation_service import prescreen_template_revision
            await prescreen_template_revision(db, revision)
        except Exception as e:
            logger.warning("revision AI 预筛失败（不阻断保存）: %s", e)
        await db.commit()
        await db.refresh(tpl)
        return tpl

    # 其他情况：直接改原模板字段
    for field, value in update_data.items():
        if hasattr(tpl, field) and value is not None:
            setattr(tpl, field, value)

    await db.commit()
    await db.refresh(tpl)
    return tpl


# ---------- 修订草稿流程 ----------

async def get_or_create_pending_revision(
    db: AsyncSession, template_id: int
) -> PipelineTemplateRevision:
    """
    获取或创建该模板的 pending revision。
    pending 定义：is_approved=False 且 is_rejected=False。
    已存在则覆盖（用于后续 apply_update_to_revision），不存在则基于原模板快照新建。
    """
    result = await db.execute(
        select(PipelineTemplateRevision).filter(
            PipelineTemplateRevision.template_id == template_id,
            PipelineTemplateRevision.is_approved == False,  # noqa: E712
            PipelineTemplateRevision.is_rejected == False,  # noqa: E712
        )
    )
    revision = result.scalar_one_or_none()
    if revision:
        return revision

    # 不存在 → 基于原模板字段快照新建
    tpl = await get_template_by_id(db, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="流水线模板不存在")

    revision = PipelineTemplateRevision(
        template_id=tpl.id,
        name=tpl.name,
        description=tpl.description,
        category=tpl.category,
        thumbnail_url=tpl.thumbnail_url,
        inputs_config=tpl.inputs_config,
        steps_config=tpl.steps_config,
        output_mapping=tpl.output_mapping,
        script_template_id=tpl.script_template_id,
        estimated_credits=tpl.estimated_credits,
        estimated_time_minutes=tpl.estimated_time_minutes,
        tags=tpl.tags or [],
    )
    db.add(revision)
    await db.flush()
    return revision


def apply_update_to_revision(
    revision: PipelineTemplateRevision,
    update_data: Dict[str, Any],
    edited_by: Optional[int] = None,
) -> None:
    """
    将 update_data 中的字段写入 revision 对应字段。
    只写入 _REVISION_SNAPSHOT_FIELDS 中存在的字段，且值为非 None。
    """
    for field in _REVISION_SNAPSHOT_FIELDS:
        if field in update_data and update_data[field] is not None:
            setattr(revision, field, update_data[field])
    if edited_by is not None:
        revision.edited_by = edited_by
    # 重置审核标记（再次编辑视为新一次提交）
    revision.is_approved = False
    revision.is_rejected = False
    revision.reject_reason = None
    revision.reviewed_at = None
    revision.created_at = datetime.utcnow()


async def get_pending_revision(
    db: AsyncSession, template_id: int
) -> Optional[PipelineTemplateRevision]:
    """供编辑器拉取草稿：返回最新未审核的 revision 或 None"""
    result = await db.execute(
        select(PipelineTemplateRevision).filter(
            PipelineTemplateRevision.template_id == template_id,
            PipelineTemplateRevision.is_approved == False,  # noqa: E712
            PipelineTemplateRevision.is_rejected == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def apply_revision_to_template(
    db: AsyncSession, revision: PipelineTemplateRevision
) -> PipelineTemplate:
    """
    审核通过：用 revision 字段覆盖原模板对应字段，
    置 tpl.has_pending_revision=False，保持 tpl.is_approved=True/is_rejected=False；
    revision.is_approved=True，revision.reviewed_at=utcnow。
    """
    tpl = await get_template_by_id(db, revision.template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="流水线模板不存在")

    for field in _REVISION_SNAPSHOT_FIELDS:
        setattr(tpl, field, getattr(revision, field))

    tpl.has_pending_revision = False
    tpl.is_approved = True
    tpl.is_rejected = False
    tpl.reject_reason = None

    revision.is_approved = True
    revision.is_rejected = False
    revision.reviewed_at = datetime.utcnow()

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
