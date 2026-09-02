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
#   /api/pipeline/assets/containers    - 我的创作单元分组列表（含我的资产数）
#   /api/pipeline/assets/container/{type}/{id} - 单元内资产列表
#   /api/pipeline/assets/{id}/share    - 切换资产分享状态（复用审核管道）
#   /api/pipeline/assets/{id}           - DELETE 删除资产（含归档影子记录）
# =====================================================

import logging
import asyncio
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import select, func, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.response import ok
from app.core.security import get_current_user, get_current_user_optional
from app.models.user import User
from app.models.pipeline import StylePreset, ScriptTemplate
from app.models.asset import Asset
from app.models.asset_like import AssetLike
from app.schemas.assets import (
    StylePresetOut,
    ScriptTemplateOut,
    AssetOut,
    AssetResponse,
    AssetContainerResponse,
    AssetContainersResponse,
    AssetContainerDetailResponse,
    AssetSaveFromGenerationRequest,
)
from app.schemas.plaza import UpdateShareStatusRequest
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

    return ok(data={
        "items": [StylePresetOut.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


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

    return ok(data=StylePresetOut.model_validate(style))


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

    return ok(data={
        "items": [ScriptTemplateOut.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


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

    return ok(data=ScriptTemplateOut.model_validate(tpl))


# =====================================================
# 资产库 API
# =====================================================

@router.get("/pipeline/assets", summary="获取资产库列表")
async def get_assets(
    asset_type: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    scope: Optional[str] = Query(None, description="market=公开资产(默认)；my=仅当前用户(需登录)，含私有传统资产"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """获取资产库列表。

    - scope=my（需登录）：返回当前用户自己的资产（container 为空的传统资产），
      含公开与私有，用于「我的资产」区。
    - 默认/ scope=market：返回公开资产（is_public=True），用于广场资产浏览。
    """
    query = select(Asset)
    filters = []

    if scope == "my":
        if not _current_user:
            raise HTTPException(status_code=401, detail="查看我的资产需先登录")
        filters.append(Asset.user_id == _current_user.id)
        filters.append(Asset.container_type.is_(None))
    else:
        filters.append(Asset.is_public == True)

    if asset_type:
        filters.append(Asset.type == asset_type)
    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            Asset.name.ilike(search_pattern),
            Asset.description.ilike(search_pattern),
            Asset.visual_description.ilike(search_pattern),
        ))

    if filters:
        query = query.where(*filters)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(
        Asset.use_count.desc(),
        Asset.updated_at.desc(),
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    return ok(data={
        "items": [AssetOut.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


# =====================================================
# 创作单元（容器）归组：分组列表 + 单元内资产
# 说明：container_type/container_id 非空的资产即画布/项目自动归档的影子记录，
#       按 (container_type, container_id) 聚合为「创作单元」。
# =====================================================

_CONTAINER_TYPE_LABELS = {
    "project": "项目",
    "canvas_script": "剧本",
    "canvas": "画布",
}


@router.get("/pipeline/assets/containers", summary="我的创作单元分组列表")
async def get_my_containers(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    当前用户的创作单元分组列表。

    - containers：container 非空的归档资产按 (container_type, container_id) 聚合为单元卡片
      （名称快照、类型徽标、资产数、封面）。
    - standalone_total：container 为空的传统资产数量（即「我的资产」区）。
    """
    # 归档影子记录（container 非空）
    stmt = (
        select(Asset)
        .where(
            Asset.user_id == current_user.id,
            Asset.container_type.isnot(None),
            Asset.container_id.isnot(None),
        )
        .order_by(Asset.updated_at.desc())
    )
    result = await db.execute(stmt)
    assets = result.scalars().all()

    groups: dict = {}
    for a in assets:
        key = (a.container_type, a.container_id)
        groups.setdefault(key, []).append(a)

    containers = []
    for (ctype, cid), items in groups.items():
        cover_url = None
        cover_kind = None
        for it in items:
            url = it.asset_url or (it.reference_images[0] if it.reference_images else None)
            if url:
                cover_url = url
                cover_kind = it.kind or (
                    "video" if it.type in ("clip", "final") else "image"
                )
                break
        containers.append(AssetContainerResponse(
            container_type=ctype,
            container_id=cid,
            container_name=items[0].container_name,
            type_label=_CONTAINER_TYPE_LABELS.get(ctype or "", ctype or ""),
            asset_count=len(items),
            cover_url=cover_url,
            cover_kind=cover_kind,
        ))

    # 我的资产（container 为空的传统资产）数量
    sc_stmt = (
        select(func.count())
        .select_from(Asset)
        .where(Asset.user_id == current_user.id, Asset.container_type.is_(None))
    )
    sc_res = await db.execute(sc_stmt)
    standalone_total = sc_res.scalar_one() or 0

    return ok(data=AssetContainersResponse(containers=containers, standalone_total=standalone_total))


@router.get(
    "/pipeline/assets/container/{container_type}/{container_id}",
    summary="单元内资产列表",
)
async def get_container_assets(
    container_type: str,
    container_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """获取某个创作单元内的全部资产（用于单元详情按类型分栏展示）"""
    stmt = (
        select(Asset)
        .where(
            Asset.user_id == current_user.id,
            Asset.container_type == container_type,
            Asset.container_id == container_id,
        )
        .order_by(Asset.created_at.asc())
    )
    result = await db.execute(stmt)
    items = result.scalars().all()
    container_name = items[0].container_name if items else None
    return ok(data=AssetContainerDetailResponse(
        container_type=container_type,
        container_id=container_id,
        container_name=container_name,
        type_label=_CONTAINER_TYPE_LABELS.get(container_type, container_type),
        items=[AssetResponse.model_validate(it) for it in items],
    ))


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

    return ok(data=AssetOut.model_validate(asset))


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
    return ok(data=AssetOut.model_validate(asset))


# =====================================================
# 资产分享状态切换（广场功能，复用 generations 的审核管道）
# PATCH /api/pipeline/assets/{id}/share - 切换公开状态（需登录 + 归属校验）
# DELETE /api/pipeline/assets/{id}        - 删除资产（含归档影子记录）
# =====================================================

@router.patch("/pipeline/assets/{asset_id}/share", summary="切换资产分享状态")
async def update_asset_share_status(
    asset_id: int,
    body: UpdateShareStatusRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    切换资产的公开/私有状态（需登录，按用户隔离）。
    设为公开时进入待审核（pending），先做敏感词快速筛查，再异步触发 AI 内容审核；
    未过审不展示到广场。被管理员屏蔽（rejected）的资产不可再次公开。
    """
    asset = await asset_library.get_asset_by_id(db, asset_id)
    if not asset or asset.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="未找到对应资产或无权操作")

    # 被管理员屏蔽的资产，用户不能再次设为公开
    if body.is_public and asset.moderation_status == "rejected":
        raise HTTPException(
            status_code=403,
            detail="该资产已被管理员屏蔽，无法公开到广场",
        )

    was_public = asset.is_public
    asset.is_public = body.is_public

    # 首次设为公开时记录时间
    if body.is_public and not was_public and not asset.public_shared_at:
        asset.public_shared_at = datetime.utcnow()

    # 设为公开时：进入待审核，敏感词快速筛查；AI 审核在提交后异步触发
    moderation_args = None
    if body.is_public and not was_public:
        asset.moderation_status = "pending"
        asset.moderation_reason = "审核中：等待系统预审"

        # 敏感词快速筛查（作用于 name / description）
        try:
            from app.services.moderation_service import check_sensitive_text
            hit, hit_words = await check_sensitive_text(
                db, f"{asset.name or ''} {asset.description or ''}"
            )
            if hit:
                asset.moderation_reason = (
                    f"审核中：文本命中敏感词（{', '.join(hit_words[:3])}），等待内容审核"
                )
        except Exception as mod_err:
            logger.warning("[广场] 资产分享时敏感词检测失败: %s", mod_err)

        # 计算审核参数（AI 审核在事务提交后异步触发，后台任务需读到本次提交的数据）
        from app.services.moderation_service import run_async_asset_moderation
        gen_type = "video" if (
            asset.kind == "video" or asset.type in ("clip", "final")
        ) else "image"
        result_url = asset.asset_url or (
            asset.reference_images[0] if asset.reference_images else None
        )
        moderation_args = (asset.id, gen_type, result_url, asset.name)

    await db.commit()
    await db.refresh(asset)

    # 异步触发 AI 图像/视频内容审核（不阻塞接口响应）
    if moderation_args:
        try:
            asyncio.create_task(run_async_asset_moderation(*moderation_args))
        except Exception as task_err:
            logger.warning("[广场] 资产启动 AI 异步审核失败 id=%d: %s", moderation_args[0], task_err)

    msg = (
        "已提交分享，正在审核中，审核通过后将展示到广场"
        if body.is_public
        else "已设为仅自己可见"
    )
    logger.info("[广场] 用户 %s 切换资产 %s 分享状态: %s", current_user.id, asset_id, body.is_public)

    return ok(
        data={"id": asset_id, "is_public": body.is_public},
        message=msg,
    )


@router.delete("/pipeline/assets/{asset_id}", summary="删除资产（含归档影子记录）")
async def delete_asset_endpoint(
    asset_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    删除资产（需登录 + 归属校验）。

    - 若资产是画布/项目自动归档的影子记录（container 非空），仅删除资产库影子记录，
      不影响画布/项目本体。
    - 若为手动保存的传统资产（container 为空），则一并删除该资产。
    """
    asset = await asset_library.get_asset_by_id(db, asset_id)
    if not asset or asset.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="未找到对应资产或无权操作")

    is_archive = bool(asset.container_type)
    # 清理点赞关系（SQLite 未启用外键 CASCADE，防孤儿行）
    await db.execute(delete(AssetLike).where(AssetLike.asset_id == asset_id))
    await asset_library.delete_asset(db, asset_id, user_id=current_user.id)
    logger.info(
        "[资产] 用户 %s 删除资产 %s（归档影子记录=%s）",
        current_user.id, asset_id, is_archive,
    )
    return ok(data={"id": asset_id}, message="已删除")


@router.post("/pipeline/assets/{asset_id}/use", summary="记录资产使用（用于生成），递增 use_count")
async def use_asset_endpoint(
    asset_id: int,
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    记录一次「用于生成」使用，递增 assets.use_count。

    公开资产任何访客可触发（无需登录），用于统计资产被复用次数；
    归属校验不做，避免阻塞生图页预填流程。
    """
    asset = await asset_library.get_asset_by_id(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    await asset_library.increment_use_count(db, asset_id)
    logger.info("[资产] 资产 %s 被使用，use_count=%s", asset_id, asset.use_count)
    return ok(data={"id": asset_id, "use_count": asset.use_count})

