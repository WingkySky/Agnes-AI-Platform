# =====================================================
# 风格预设 / 剧本模板 / 资产库 路由
#
# 创意工坊（WorkshopView）及流水线模板 CRUD 已下线，
# 项目制创作（Project）已迁移到 /api/projects/*，
# 本文件仅保留前端共享的风格 / 剧本 / 资产 API。
#
# API 列表:
#   /api/pipeline/styles               - 风格预设列表
#   /api/pipeline/styles/{id}          - 风格预设详情
#   /api/pipeline/script-templates     - 剧本模板列表
#   /api/pipeline/script-templates/{id} - 剧本模板详情
#   /api/pipeline/assets               - 资产库列表
#   /api/pipeline/assets/{id}          - 资产详情
#   /api/pipeline/assets/save-from-generation - 从生成记录保存为资产
# =====================================================

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.security import get_current_user, get_current_user_optional
from app.models.user import User
from app.models.pipeline import StylePreset, ScriptTemplate
from app.models.asset import Asset
from app.schemas.assets import (
    StylePresetOut,
    ScriptTemplateOut,
    AssetOut,
    AssetSaveFromGenerationRequest,
)
from app.services import style_service
from app.services import script_template_service
from app.services import asset_library

logger = logging.getLogger("agnes_platform")
router = APIRouter()


# =====================================================
# 风格预设 API
# =====================================================

@router.get("/pipeline/styles", summary="获取风格预设列表")
async def get_style_presets(
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """获取风格预设列表（内置 + 用户自定义公开的）"""
    query = select(StylePreset)
    filters = []
    if category:
        filters.append(StylePreset.category == category)
    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            StylePreset.name.ilike(search_pattern),
            StylePreset.description.ilike(search_pattern),
            StylePreset.key.ilike(search_pattern),
        ))
    filters.append(or_(StylePreset.is_builtin == True, StylePreset.is_public == True))

    if filters:
        query = query.where(*filters)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(
        StylePreset.is_builtin.desc(),
        StylePreset.use_count.desc(),
        StylePreset.id.asc(),
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    return {
        "items": [StylePresetOut.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/pipeline/styles/{style_id}", summary="获取风格预设详情")
async def get_style_preset_detail(
    style_id: int,
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """获取单个风格预设详情"""
    style = await style_service.get_style_by_id(db, style_id)
    if not style:
        raise HTTPException(status_code=404, detail="风格预设不存在")

    return StylePresetOut.model_validate(style)


# =====================================================
# 剧本模板 API
# =====================================================

@router.get("/pipeline/script-templates", summary="获取剧本模板列表")
async def get_script_templates(
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """获取剧本模板列表"""
    query = select(ScriptTemplate)
    filters = []
    if category:
        filters.append(ScriptTemplate.category == category)
    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            ScriptTemplate.name.ilike(search_pattern),
            ScriptTemplate.description.ilike(search_pattern),
            ScriptTemplate.key.ilike(search_pattern),
        ))
    filters.append(or_(ScriptTemplate.is_builtin == True, ScriptTemplate.is_public == True))

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
    items = list(result.scalars().all())

    return {
        "items": [ScriptTemplateOut.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/pipeline/script-templates/{tpl_id}", summary="获取剧本模板详情")
async def get_script_template_detail(
    tpl_id: int,
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """获取单个剧本模板详情"""
    tpl = await script_template_service.get_script_template_by_id(db, tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="剧本模板不存在")

    return ScriptTemplateOut.model_validate(tpl)


# =====================================================
# 资产库 API
# =====================================================

@router.get("/pipeline/assets", summary="获取资产库列表")
async def get_assets(
    asset_type: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """获取资产库列表（角色、道具、场景等公开资产）"""
    query = select(Asset)
    filters = []
    if asset_type:
        filters.append(Asset.type == asset_type)
    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            Asset.name.ilike(search_pattern),
            Asset.description.ilike(search_pattern),
            Asset.visual_description.ilike(search_pattern),
        ))
    filters.append(Asset.is_public == True)

    if filters:
        query = query.where(*filters)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(
        Asset.use_count.desc(),
        Asset.id.desc(),
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    return {
        "items": [AssetOut.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/pipeline/assets/{asset_id}", summary="获取资产详情")
async def get_asset_detail(
    asset_id: int,
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """获取单个资产详情"""
    asset = await asset_library.get_asset_by_id(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    return AssetOut.model_validate(asset)


@router.post("/pipeline/assets/save-from-generation", summary="从生成记录保存为资产")
async def save_asset_from_generation(
    req: AssetSaveFromGenerationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """将生成的图片/视频保存为资产库中的资产"""
    asset = await asset_library.save_asset_from_generation(
        db, req, user_id=current_user.id
    )
    return AssetOut.model_validate(asset)
