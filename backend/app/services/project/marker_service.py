# =====================================================
# 标记 Markers 服务 — Phase 2 增强
#
# 职责:
#   - 标记 CRUD（创建/列出/删除）
#   - 标记按时间排序
# =====================================================

from typing import List, Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import ProjectMarker


async def list_markers(db: AsyncSession, project_id: int) -> List[ProjectMarker]:
    """列出项目的所有标记（按时间升序）"""
    result = await db.execute(
        select(ProjectMarker)
        .where(ProjectMarker.project_id == project_id)
        .order_by(ProjectMarker.time.asc())
    )
    return list(result.scalars().all())


async def create_marker(
    db: AsyncSession, project_id: int,
    time: float, name: Optional[str] = None, color: str = "#4a9eff",
) -> ProjectMarker:
    """创建标记"""
    marker = ProjectMarker(
        project_id=project_id,
        time=time,
        name=name,
        color=color,
    )
    db.add(marker)
    await db.commit()
    await db.refresh(marker)
    return marker


async def delete_marker(db: AsyncSession, project_id: int, marker_id: int) -> bool:
    """删除标记（校验 project_id 防越权）"""
    result = await db.execute(
        delete(ProjectMarker)
        .where(ProjectMarker.id == marker_id)
        .where(ProjectMarker.project_id == project_id)
    )
    await db.commit()
    return result.rowcount > 0


async def find_nearest_marker(
    db: AsyncSession, project_id: int, time: float
) -> Optional[ProjectMarker]:
    """找到离指定时间最近的标记（用于 Shift+M 删除最近标记）"""
    markers = await list_markers(db, project_id)
    if not markers:
        return None
    return min(markers, key=lambda m: abs(m.time - time))
