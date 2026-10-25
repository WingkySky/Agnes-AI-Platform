# =====================================================
# 风格预设服务
# =====================================================


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline import StylePreset


async def get_style_by_id(db: AsyncSession, style_id: int) -> StylePreset | None:
    """根据 ID 获取风格预设"""
    result = await db.execute(select(StylePreset).filter(StylePreset.id == style_id))
    return result.scalar_one_or_none()
