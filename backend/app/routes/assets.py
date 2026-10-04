# =====================================================
# 统一资产路由（/api/assets，登录级）
#
# - POST /api/assets          画布/上传素材建统一资产行（画布素材 uid 退役入库通道）
# - GET  /api/assets          本人资产列表（分页 + media_type/source/work_id/keyword 筛选）
#
# 语义：素材生命周期归资产层；画布节点/剪辑片段只持有 asset_id 引用。
# =====================================================

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.response import ok
from app.core.security import get_current_user
from app.models.user import User
from app.services import asset_library

router = APIRouter(prefix="/assets", tags=["资产库"], dependencies=[Depends(get_current_user)])


class AssetCreateRequest(BaseModel):
    """画布/上传素材建资产行请求体"""
    url: str = Field(..., min_length=1, description="素材地址（/uploads/ 本地路径或公网 http(s) URL）")
    media_type: str = Field(..., description="image / video / audio")
    name: Optional[str] = Field(None, max_length=200, description="素材名")
    work_id: Optional[int] = Field(None, description="所属作品标记（需归属当前用户）")


@router.post("", summary="创建素材资产（画布素材入库通道）")
async def create_asset(
    payload: AssetCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    asset = await asset_library.create_asset_from_upload(
        db,
        user_id=current_user.id,
        url=payload.url,
        media_type=payload.media_type,
        name=payload.name,
        work_id=payload.work_id,
    )
    return ok(data=asset_library.asset_to_dict(asset))


@router.get("", summary="本人资产列表（统一入口）")
async def list_assets(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    media_type: Optional[str] = Query(None, description="image / video / audio"),
    source: Optional[str] = Query(None, description="generation / upload / canvas / compose / archive"),
    work_id: Optional[int] = Query(None, description="按所属作品筛选"),
    keyword: Optional[str] = Query(None, max_length=100, description="名称关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    data = await asset_library.list_assets(
        db,
        user_id=current_user.id,
        media_type=media_type,
        source=source,
        work_id=work_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return ok(data=data)


@router.post("/backfill", summary="存量资产补课（storage_key/media_type 回填 + 上游 URL 转存；仅管理员）")
async def backfill_assets(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(200, ge=1, le=1000, description="单次处理上限"),
):
    """一次性补课：为存量资产行回填 media_type 与 storage_key（上游 URL 转存），幂等可重复调用"""
    if not current_user.is_admin and current_user.role not in ("admin", "moderator"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="仅管理员/审核员可访问")
    data = await asset_library.backfill_asset_storage(db, limit=limit)
    return ok(data=data)
