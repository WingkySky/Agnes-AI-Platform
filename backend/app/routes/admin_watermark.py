# =====================================================
# 水印配置管理路由（仅管理员）
#
# GET    /api/admin/watermark/config           获取水印配置
# PUT    /api/admin/watermark/config           更新水印配置
# POST   /api/admin/watermark/preview          水印预览（返回预览图）
# =====================================================

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_async_db
from app.core.security import require_permission
from app.models.user import User
from app.models.watermark import WatermarkConfig
from app.services.watermark_service import get_watermark_config

logger = logging.getLogger("agnes_platform")
router = APIRouter(prefix="/admin/watermark", tags=["管理员-水印配置"])


@router.get("/config", summary="[管理员] 获取水印配置")
async def get_config(
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(require_permission("watermark:manage")),
):
    config = await get_watermark_config(db)
    return config.to_dict()


@router.put("/config", summary="[管理员] 更新水印配置")
async def update_config(
    config_data: dict = Body(...),
    db: AsyncSession = Depends(get_async_db),
    admin: User = Depends(require_permission("watermark:manage")),
):
    config = await get_watermark_config(db)

    # 允许更新的字段
    allowed_fields = [
        "type", "text", "font_size", "color", "opacity",
        "position", "margin", "image_url", "image_width", "force_all",
    ]
    for field in allowed_fields:
        if field in config_data:
            val = config_data[field]
            setattr(config, field, val)

    config.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(config)

    logger.info("[水印配置] %s 更新水印配置", admin.username)
    return config.to_dict()
