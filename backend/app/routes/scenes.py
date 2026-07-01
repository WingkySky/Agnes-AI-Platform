# =====================================================
# 3D 场景（导演台）路由 — CRUD + prompt 预览
# - GET    /api/scenes                 列表
# - POST   /api/scenes                 创建
# - GET    /api/scenes/{id}            详情
# - PUT    /api/scenes/{id}            更新
# - DELETE /api/scenes/{id}            删除
# - POST   /api/scenes/preview-prompt  预览翻译后的 prompt
# =====================================================

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.scene import (
    SceneCreate,
    SceneUpdate,
    SceneResponse,
    SceneListResponse,
    ScenePromptPreviewRequest,
    ScenePromptPreviewResponse,
)
from app.services import scene_service as svc
from app.services.scene_service import scene_to_prompt_suffix


router = APIRouter(prefix="/scenes", tags=["3D 场景（导演台）"])


@router.get("", response_model=SceneListResponse, summary="列出 3D 场景")
async def list_scenes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="按名称/描述搜索"),
    is_public: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """列出当前用户的场景 + 公开场景"""
    limit = page_size
    offset = (page - 1) * page_size
    scenes, total = await svc.list_scenes(
        db, user_id=current_user.id, limit=limit, offset=offset,
        search=search, is_public=is_public,
    )
    return SceneListResponse(
        items=[SceneResponse.from_model(s) for s in scenes],
        total=total,
    )


@router.post("", response_model=SceneResponse, summary="创建 3D 场景")
async def create_scene(
    payload: SceneCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """创建新的 3D 场景"""
    scene = await svc.create_scene(
        db, user_id=current_user.id, name=payload.name,
        description=payload.description, scene_data=payload.scene_data,
        is_public=payload.is_public,
    )
    return SceneResponse.from_model(scene)


# 注意：/preview-prompt 必须放在 /{scene_id} 之前，否则会被当作 scene_id 匹配
@router.post("/preview-prompt", response_model=ScenePromptPreviewResponse, summary="预览场景翻译后的 prompt")
async def preview_prompt(
    payload: ScenePromptPreviewRequest,
    current_user: User = Depends(get_current_user),
):
    """
    把 3D 场景数据翻译为镜头语言描述，便于前端实时预览。
    不需要持久化，纯计算接口。
    """
    suffix, details = scene_to_prompt_suffix(payload.scene_data)
    return ScenePromptPreviewResponse(prompt_suffix=suffix, details=details)


@router.get("/{scene_id}", response_model=SceneResponse, summary="获取场景详情")
async def get_scene(
    scene_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个 3D 场景详情（自己的或公开的）"""
    scene = await svc.get_scene(db, scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    if scene.user_id != current_user.id and not scene.is_public:
        raise HTTPException(status_code=403, detail="无权查看")
    return SceneResponse.from_model(scene)


@router.put("/{scene_id}", response_model=SceneResponse, summary="更新 3D 场景")
async def update_scene(
    scene_id: int,
    payload: SceneUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """更新 3D 场景（仅创建者）"""
    scene = await svc.get_scene(db, scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    if scene.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改")
    update_data = payload.model_dump(exclude_unset=True)
    updated = await svc.update_scene(db, scene_id, **update_data)
    return SceneResponse.from_model(updated)


@router.delete("/{scene_id}", summary="删除 3D 场景")
async def delete_scene(
    scene_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """删除 3D 场景（仅创建者）"""
    scene = await svc.get_scene(db, scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    if scene.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除")
    await svc.delete_scene(db, scene_id)
    return {"message": "已删除"}
