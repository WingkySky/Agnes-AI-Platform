# =====================================================
# 剧本服务 — 剧本 CRUD
#
# 剧本是项目创作的源头；剧本生成已迁前端 lib/storyboard 管线（generateScript）。
# =====================================================

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectScript
from app.schemas.project import ScriptCreate, ScriptUpdate

logger = logging.getLogger("agnes_platform.project.script")


# =====================================================
# 剧本 CRUD
# =====================================================

async def list_scripts(db: AsyncSession, project_id: int) -> List[ProjectScript]:
    """列出项目所有剧本分集（按 episode_no 升序）"""
    result = await db.execute(
        select(ProjectScript)
        .where(ProjectScript.project_id == project_id)
        .order_by(ProjectScript.episode_no)
    )
    return result.scalars().all()


async def get_script(db: AsyncSession, script_id: int) -> Optional[ProjectScript]:
    """获取剧本详情"""
    result = await db.execute(
        select(ProjectScript).where(ProjectScript.id == script_id)
    )
    return result.scalar_one_or_none()


async def create_script(
    db: AsyncSession, project_id: int, data: ScriptCreate
) -> ProjectScript:
    """新增剧本分集"""
    script = ProjectScript(
        project_id=project_id,
        episode_no=data.episode_no,
        title=data.title,
        content=data.content,
        outline=data.outline,
        status="draft",
    )
    db.add(script)
    await db.commit()
    await db.refresh(script)
    return script


async def update_script(
    db: AsyncSession, script_id: int, data: ScriptUpdate
) -> Optional[ProjectScript]:
    """编辑剧本"""
    script = await get_script(db, script_id)
    if not script:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(script, k, v)
    await db.commit()
    await db.refresh(script)
    return script


async def delete_script(db: AsyncSession, script_id: int) -> bool:
    """删除剧本分集"""
    script = await get_script(db, script_id)
    if not script:
        return False
    await db.delete(script)
    await db.commit()
    return True
