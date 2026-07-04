# =====================================================
# 项目 CRUD 服务
#
# 功能:
#   1. 项目的创建 / 查询 / 列表 / 更新 / 删除 / 归档
#   2. 活动视图切换（manager / canvas）
#   3. 项目状态机维护
#
# 状态机:
#   draft → creating → in_progress → merging → completed → archived
# =====================================================

from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import (
    Project,
    PROJECT_STATUS_DRAFT,
    PROJECT_STATUS_IN_PROGRESS,
    PROJECT_STATUS_ARCHIVED,
)
from app.schemas.project import ProjectCreate, ProjectUpdate


# =====================================================
# 项目 CRUD
# =====================================================

async def create_project(db: AsyncSession, user_id: int, data: ProjectCreate) -> Project:
    """创建空项目（status=in_progress，空白创建模式）"""
    project = Project(
        title=data.title,
        description=data.description,
        template_id=data.template_id,
        user_id=user_id,
        status=PROJECT_STATUS_IN_PROGRESS,
        aspect_ratio=data.aspect_ratio or "16:9",
        resolution=data.resolution or "1280x720",
        wizard_inputs=data.wizard_inputs or {},
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def create_draft_for_wizard(
    db: AsyncSession, user_id: int, data: ProjectCreate
) -> Project:
    """为向导流程创建草稿项目（status=creating，向导完成后转为 in_progress）"""
    project = Project(
        title=data.title,
        description=data.description,
        template_id=data.template_id,
        user_id=user_id,
        status="creating",
        aspect_ratio=data.aspect_ratio or "16:9",
        resolution=data.resolution or "1280x720",
        wizard_inputs=data.wizard_inputs or {},
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def get_project(db: AsyncSession, project_id: int) -> Optional[Project]:
    """获取项目详情（预加载 scripts）"""
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.scripts))
        .where(Project.id == project_id)
    )
    return result.scalar_one_or_none()


async def list_projects(
    db: AsyncSession,
    user_id: int,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Project], int]:
    """获取用户项目列表（分页，按更新时间倒序）"""
    query = select(Project).where(Project.user_id == user_id)
    if status:
        query = query.where(Project.status == status)
    query = query.order_by(Project.updated_at.desc())

    # 总数
    count_q = select(func.count()).select_from(Project).where(Project.user_id == user_id)
    if status:
        count_q = count_q.where(Project.status == status)
    total = (await db.execute(count_q)).scalar() or 0

    # 分页
    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    return result.scalars().all(), total


async def update_project(
    db: AsyncSession, project_id: int, data: ProjectUpdate
) -> Optional[Project]:
    """更新项目可变字段"""
    project = await get_project(db, project_id)
    if not project:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(project, k, v)
    await db.commit()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, project_id: int) -> bool:
    """删除项目（级联删除所有实体表）"""
    project = await get_project(db, project_id)
    if not project:
        return False
    await db.delete(project)
    await db.commit()
    return True


async def archive_project(db: AsyncSession, project_id: int) -> Optional[Project]:
    """归档项目"""
    project = await get_project(db, project_id)
    if not project:
        return None
    project.status = PROJECT_STATUS_ARCHIVED
    await db.commit()
    await db.refresh(project)
    return project


async def update_active_view(
    db: AsyncSession, project_id: int, view: str
) -> Optional[Project]:
    """切换活动视图（manager / canvas）"""
    project = await get_project(db, project_id)
    if not project:
        return None
    project.active_view = view
    await db.commit()
    await db.refresh(project)
    return project


async def update_status(
    db: AsyncSession, project_id: int, status: str
) -> Optional[Project]:
    """更新项目状态（用于状态机迁移）"""
    project = await get_project(db, project_id)
    if not project:
        return None
    project.status = status
    await db.commit()
    await db.refresh(project)
    return project
