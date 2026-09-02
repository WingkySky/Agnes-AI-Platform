# =====================================================
# 剧本模板服务
# =====================================================

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline import ScriptTemplate


async def get_script_template_by_id(db: AsyncSession, tpl_id: int) -> Optional[ScriptTemplate]:
    """根据 ID 获取剧本模板"""
    result = await db.execute(select(ScriptTemplate).filter(ScriptTemplate.id == tpl_id))
    return result.scalar_one_or_none()
