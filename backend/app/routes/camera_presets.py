# =====================================================
# 摄像机预设路由 — CRUD API
# =====================================================

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.security import get_current_user
from app.models.user import User
from app.services import camera_preset_service as svc


router = APIRouter(prefix="/camera-presets", tags=["摄像机预设"])


# ---------- 请求/响应模型 ----------

class CameraPresetCreate(BaseModel):
    """创建摄像机预设请求"""
    name: str = Field(..., description="预设名称")
    description: Optional[str] = Field(None, description="预设描述")
    category: Optional[str] = Field(None, description="分类（默认 '通用'）")
    tags: Optional[list[str]] = Field(None, description="标签列表")
    camera_model: Optional[str] = Field(None, description="摄像机机型（如 Sony FX3）")
    focal_length: Optional[str] = Field(None, description="焦段（如 85mm）")
    aperture: Optional[str] = Field(None, description="光圈（如 f/2.8）")
    depth_of_field: Optional[str] = Field(None, description="景深（如 浅景深）")
    shutter_speed: Optional[str] = Field(None, description="快门速度（如 1/125）")
    shutter_angle: Optional[str] = Field(None, description="快门角度（如 180°）")
    camera_movement: Optional[str] = Field(None, description="运镜方式（如 手持运镜）")
    camera_angle: Optional[str] = Field(None, description="拍摄角度（如 平视视角）")
    aspect_ratio: Optional[str] = Field(None, description="画幅比（如 2.35:1）")
    visual_style: Optional[str] = Field(None, description="视觉风格（如 暖色调胶片风格）")
    is_public: bool = Field(False, description="是否公开")


class CameraPresetUpdate(BaseModel):
    """更新摄像机预设请求（所有字段可选）"""
    name: Optional[str] = Field(None, description="预设名称")
    description: Optional[str] = Field(None, description="预设描述")
    category: Optional[str] = Field(None, description="分类")
    tags: Optional[list[str]] = Field(None, description="标签列表")
    camera_model: Optional[str] = Field(None, description="摄像机机型")
    focal_length: Optional[str] = Field(None, description="焦段")
    aperture: Optional[str] = Field(None, description="光圈")
    depth_of_field: Optional[str] = Field(None, description="景深")
    shutter_speed: Optional[str] = Field(None, description="快门速度")
    shutter_angle: Optional[str] = Field(None, description="快门角度")
    camera_movement: Optional[str] = Field(None, description="运镜方式")
    camera_angle: Optional[str] = Field(None, description="拍摄角度")
    aspect_ratio: Optional[str] = Field(None, description="画幅比")
    visual_style: Optional[str] = Field(None, description="视觉风格")
    is_public: Optional[bool] = Field(None, description="是否公开")


class CameraPresetResponse(BaseModel):
    """摄像机预设响应"""
    id: int
    user_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    type: str
    category: str
    tags: list
    camera_model: Optional[str] = None
    focal_length: Optional[str] = None
    aperture: Optional[str] = None
    depth_of_field: Optional[str] = None
    shutter_speed: Optional[str] = None
    shutter_angle: Optional[str] = None
    camera_movement: Optional[str] = None
    camera_angle: Optional[str] = None
    aspect_ratio: Optional[str] = None
    visual_style: Optional[str] = None
    is_public: bool
    is_approved: bool
    usage_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class CameraPresetListResponse(BaseModel):
    """摄像机预设列表响应"""
    items: list[CameraPresetResponse]
    total: int


# ---------- API 路由 ----------

@router.get("", response_model=CameraPresetListResponse, summary="列出摄像机预设")
async def list_camera_presets(
    page: int = Query(1, ge=1, description="页码（1-based）"),
    page_size: int = Query(20, ge=1, le=500, description="每页数量"),
    search: Optional[str] = Query(None, description="按名称/描述关键词搜索"),
    category: Optional[str] = Query(None, description="分类筛选"),
    is_public: Optional[bool] = Query(None, description="是否仅公开/私有"),
    limit: int = Query(100, ge=1, le=500, description="兼容旧参数，与 page_size 二选一"),
    offset: int = Query(0, ge=0, description="兼容旧参数，偏移量"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    列出摄像机预设（用户自己的 + 公开审核通过的）。

    前端默认传 page/page_size/search/category/is_public；
    为兼容旧调用，同时支持 limit/offset。
    """
    # 优先使用 page/page_size；若旧调用只传 limit/offset，则换算
    if page_size != 20 or page != 1:
        actual_limit = page_size
        actual_offset = (page - 1) * page_size
    else:
        actual_limit = limit
        actual_offset = offset

    presets, total = await svc.list_presets(
        db,
        user_id=current_user.id,
        limit=actual_limit,
        offset=actual_offset,
        search=search,
        category=category,
        is_public=is_public,
    )
    return CameraPresetListResponse(
        items=[CameraPresetResponse.model_validate(p) for p in presets],
        total=total,
    )


@router.post("", response_model=CameraPresetResponse, summary="创建摄像机预设")
async def create_camera_preset(
    payload: CameraPresetCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """创建新的摄像机预设"""
    preset = await svc.create_preset(
        db,
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        category=payload.category,
        tags=payload.tags,
        camera_model=payload.camera_model,
        focal_length=payload.focal_length,
        aperture=payload.aperture,
        depth_of_field=payload.depth_of_field,
        shutter_speed=payload.shutter_speed,
        shutter_angle=payload.shutter_angle,
        camera_movement=payload.camera_movement,
        camera_angle=payload.camera_angle,
        aspect_ratio=payload.aspect_ratio,
        visual_style=payload.visual_style,
        is_public=payload.is_public,
    )
    return CameraPresetResponse.model_validate(preset)


@router.get("/{preset_id}", response_model=CameraPresetResponse, summary="获取摄像机预设详情")
async def get_camera_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个摄像机预设详情"""
    preset = await svc.get_preset(db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="摄像机预设不存在")
    # 权限：自己的或公开审核通过的
    if preset.user_id != current_user.id and not (preset.is_public and preset.is_approved):
        raise HTTPException(status_code=403, detail="无权查看")
    return CameraPresetResponse.model_validate(preset)


@router.put("/{preset_id}", response_model=CameraPresetResponse, summary="更新摄像机预设")
async def update_camera_preset(
    preset_id: int,
    payload: CameraPresetUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """更新摄像机预设（仅创建者）"""
    preset = await svc.get_preset(db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="摄像机预设不存在")
    if preset.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改")

    update_data = payload.model_dump(exclude_unset=True)
    updated = await svc.update_preset(db, preset_id, **update_data)
    return CameraPresetResponse.model_validate(updated)


@router.delete("/{preset_id}", summary="删除摄像机预设")
async def delete_camera_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """删除摄像机预设（仅创建者）"""
    preset = await svc.get_preset(db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="摄像机预设不存在")
    if preset.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除")

    ok = await svc.delete_preset(db, preset_id)
    if not ok:
        raise HTTPException(status_code=400, detail="删除失败")
    return {"message": "已删除"}
