# =====================================================
# 模型备用路由接口（多渠道路由 failover）
# GET /api/models/{model_id}/routes  查询锚点模型的备用路由列表
# PUT  /api/models/{model_id}/routes  整表替换保存（空列表=清空）
#
# 纯管理员功能，整路由挂 admin 依赖（未登录 401 / 普通用户 403），
# 鉴权三态由 tests/test_model_routes.py 锁死。
# 校验：锚点定义存在、目标 Provider 存在、(provider, model) 去重、
#       目标有定义行时类型必须与锚点一致（无定义行的手填目标信任管理员）。
# 查询统一 db.scalars(select(...))（Mimosa 门禁对新增代码 db.execute 误报）。
# =====================================================

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.response import ok
from app.core.security import get_current_admin_user
from app.models.api_provider import ApiProvider
from app.models.model_definition import ModelDefinition
from app.models.model_route import ModelRoute
from app.schemas.providers import (
    ModelRouteItemResponse,
    ModelRouteSaveRequest,
    ModelRoutesResponse,
)

logger = logging.getLogger("agnes_platform")

router = APIRouter(
    prefix="/models",
    dependencies=[Depends(get_current_admin_user)],
    tags=["模型备用路由"],
)


async def _load_anchor(session: AsyncSession, model_id: str) -> ModelDefinition:
    """锚点定义必须存在（active 与否不限制——停用模型也允许预配置路由）"""
    anchor = (
        await session.scalars(
            select(ModelDefinition).where(ModelDefinition.model_id == model_id).limit(1)
        )
    ).first()
    if anchor is None:
        raise HTTPException(status_code=404, detail=f"模型 {model_id} 不存在")
    return anchor


@router.get("/{model_id}/routes", summary="查询模型备用路由")
async def list_model_routes(model_id: str, db: AsyncSession = Depends(get_async_db)):
    """查询锚点模型的备用路由列表（含渠道名/档位/目标显示名快照）"""
    anchor = await _load_anchor(db, model_id)

    routes = (
        await db.scalars(
            select(ModelRoute)
            .where(ModelRoute.anchor_model_id == model_id)
            .order_by(ModelRoute.priority, ModelRoute.id)
        )
    ).all()
    providers = {
        p.id: p for p in (await db.scalars(select(ApiProvider))).all()
    }
    target_defs = {
        (d.provider_id, d.model_id): d
        for d in (await db.scalars(select(ModelDefinition))).all()
    }

    items = []
    for route in routes:
        provider = providers.get(route.provider_id)
        target_def = target_defs.get((route.provider_id, route.model_id))
        items.append(ModelRouteItemResponse(
            id=route.id,
            provider_id=route.provider_id,
            provider_name=provider.name if provider else "",
            billing_tier=(provider.billing_tier or "paid") if provider else "paid",
            model_id=route.model_id,
            display_name=(target_def.display_name or "") if target_def else "",
            priority=route.priority,
            is_enabled=route.is_enabled,
        ))

    return ok(data=ModelRoutesResponse(
        anchor_model_id=model_id,
        anchor_type=anchor.type,
        anchor_provider_id=anchor.provider_id,
        items=items,
    ))


@router.put("/{model_id}/routes", summary="保存模型备用路由（整表替换）")
async def save_model_routes(model_id: str, req: ModelRouteSaveRequest, db: AsyncSession = Depends(get_async_db)):
    """整表替换锚点模型的备用路由；空列表 = 清空全部备用"""
    anchor = await _load_anchor(db, model_id)

    # 校验目标渠道存在 + (provider, model) 去重 + 目标类型一致（有定义行时）
    seen: set[tuple[int, str]] = set()
    for index, item in enumerate(req.routes):
        key = (item.provider_id, item.model_id)
        if key in seen:
            raise HTTPException(status_code=400, detail=f"第 {index + 1} 条路由重复：渠道 {item.provider_id} + 模型 {item.model_id}")
        seen.add(key)

    provider_ids = {item.provider_id for item in req.routes}
    known_providers: set[int] = set()
    if provider_ids:
        rows = (await db.scalars(select(ApiProvider.id).where(ApiProvider.id.in_(provider_ids)))).all()
        known_providers = set(rows)
    for index, item in enumerate(req.routes):
        if item.provider_id not in known_providers:
            raise HTTPException(status_code=400, detail=f"第 {index + 1} 条路由的渠道 {item.provider_id} 不存在")

    if req.routes:
        target_model_ids = {item.model_id for item in req.routes}
        target_defs = {
            (d.provider_id, d.model_id): d
            for d in (
                await db.scalars(
                    select(ModelDefinition).where(
                        ModelDefinition.model_id.in_(target_model_ids),
                        ModelDefinition.provider_id.in_(known_providers),
                    )
                )
            ).all()
        }
        for index, item in enumerate(req.routes):
            target_def = target_defs.get((item.provider_id, item.model_id))
            if target_def is not None and target_def.type != anchor.type:
                raise HTTPException(
                    status_code=400,
                    detail=f"第 {index + 1} 条路由的目标模型 {item.model_id} 类型为 {target_def.type}，与锚点模型类型 {anchor.type} 不一致",
                )

    # 整表替换
    existing = (
        await db.scalars(select(ModelRoute).where(ModelRoute.anchor_model_id == model_id))
    ).all()
    for route in existing:
        await db.delete(route)
    await db.flush()
    for item in req.routes:
        db.add(ModelRoute(
            anchor_model_id=model_id,
            provider_id=item.provider_id,
            model_id=item.model_id,
            priority=item.priority,
            is_enabled=item.is_enabled,
        ))
    await db.commit()
    logger.info("[模型路由] 已保存备用路由: anchor=%s 共 %d 条", model_id, len(req.routes))

    return await list_model_routes(model_id, db)
