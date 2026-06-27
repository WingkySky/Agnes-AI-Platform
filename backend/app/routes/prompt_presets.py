# =====================================================
# 提示词预设路由 — CRUD API + 聚合查询
# 标准 REST 接口 + 列表查询支持 type/category/tags/search/sort
# 聚合查询：type=camera 或未指定 type 时走 PresetAggregator
# =====================================================

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_async_db
from app.core.security import get_current_user, get_current_user_optional
from app.models.generation import Generation
from app.models.plaza_like import PlazaLike
from app.models.user import User
from app.models.prompt_preset import PromptPreset
from app.models.camera_preset import CameraPreset
from app.routes.plaza import _build_plaza_work
from app.services import prompt_preset_service as svc
from app.services import preset_aggregator


router = APIRouter(prefix="/presets", tags=["提示词预设"])


# ---------- 请求/响应模型 ----------

class PresetCreate(BaseModel):
    """创建提示词预设请求"""
    name: str = Field(..., description="预设名称")
    prompt_text: str = Field("", description="提示词文本")
    description: Optional[str] = Field(None, description="预设描述")
    type: str = Field("prompt", description="预设类型（camera/prompt/style/script/pipeline）")
    category: Optional[str] = Field(None, description="分类（默认 '通用'）")
    tags: Optional[list[str]] = Field(None, description="标签列表")
    camera_params: Optional[dict] = Field(None, description="摄像机参数（JSON）")
    style_params: Optional[dict] = Field(None, description="风格参数（JSON）")
    script_text: Optional[str] = Field(None, description="脚本文本")
    pipeline_config: Optional[dict] = Field(None, description="流水线配置（JSON）")
    is_public: bool = Field(False, description="是否公开")


class PresetUpdate(BaseModel):
    """更新提示词预设请求（所有字段可选）"""
    name: Optional[str] = Field(None, description="预设名称")
    prompt_text: Optional[str] = Field(None, description="提示词文本")
    description: Optional[str] = Field(None, description="预设描述")
    category: Optional[str] = Field(None, description="分类")
    tags: Optional[list[str]] = Field(None, description="标签列表")
    camera_params: Optional[dict] = Field(None, description="摄像机参数（JSON）")
    style_params: Optional[dict] = Field(None, description="风格参数（JSON）")
    script_text: Optional[str] = Field(None, description="脚本文本")
    pipeline_config: Optional[dict] = Field(None, description="流水线配置（JSON）")
    is_public: Optional[bool] = Field(None, description="是否公开")


class PresetResponse(BaseModel):
    """提示词预设响应"""
    id: int
    user_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    type: str
    category: str
    tags: list
    prompt_text: str
    camera_params: Optional[dict] = None
    style_params: Optional[dict] = None
    script_text: Optional[str] = None
    pipeline_config: Optional[dict] = None
    is_public: bool
    is_approved: bool
    usage_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class PresetListResponse(BaseModel):
    """提示词预设列表响应"""
    items: list[PresetResponse]
    total: int


# ---------- API 路由 ----------

@router.get("", response_model=PresetListResponse, summary="列出提示词预设（聚合）")
async def list_presets(
    type: Optional[str] = Query(None, description="预设类型（camera/prompt/style/script/pipeline），不传则聚合所有类型"),
    category: Optional[str] = Query(None, description="分类筛选"),
    tags: Optional[str] = Query(None, description="标签筛选，逗号分隔"),
    search: Optional[str] = Query(None, description="搜索名称/描述关键词"),
    sort: str = Query("new", description="排序方式：new（最新）/ hot（热门）/ usage（使用量）"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    列出提示词预设（聚合查询）。

    - 指定 type → 查该类型原表（camera 走 CameraPreset，其他走 PromptPreset）
    - 不指定 type → 查 preset_index 索引表，聚合所有类型
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    page = (offset // limit) + 1 if limit > 0 else 1

    # 使用聚合器：camera 类型或不指定 type 时走聚合器
    # prompt/style/script/pipeline 类型也可走聚合器以保持一致
    items, total = await preset_aggregator.aggregate_presets(
        db,
        user_id=current_user.id,
        preset_type=type,
        category=category,
        search=search,
        sort=sort,
        page=page,
        page_size=limit,
    )
    return PresetListResponse(
        items=items,
        total=total,
    )


@router.post("", response_model=PresetResponse, summary="创建提示词预设")
async def create_preset(
    payload: PresetCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    创建新的预设。

    - type=camera → 写入 camera_presets 表（CameraPreset）
    - 其他类型 → 写入 prompt_presets 表（PromptPreset）
    """
    # camera 类型走 CameraPreset service
    if payload.type == "camera":
        from app.services import camera_preset_service as cam_svc

        cp = payload.camera_params or {}
        new_preset = await cam_svc.create_preset(
            db,
            user_id=current_user.id,
            name=payload.name,
            description=payload.description,
            category=payload.category,
            tags=payload.tags,
            camera_model=cp.get("camera_model"),
            focal_length=cp.get("focal_length"),
            aperture=cp.get("aperture"),
            depth_of_field=cp.get("depth_of_field"),
            shutter_speed=cp.get("shutter_speed"),
            shutter_angle=cp.get("shutter_angle"),
            camera_movement=cp.get("camera_movement"),
            camera_angle=cp.get("camera_angle"),
            aspect_ratio=cp.get("aspect_ratio"),
            visual_style=cp.get("visual_style"),
            is_public=payload.is_public,
        )
        # 转为统一响应格式
        return PresetResponse(
            id=new_preset.id,
            user_id=new_preset.user_id,
            name=new_preset.name,
            description=new_preset.description,
            type="camera",
            category=new_preset.category,
            tags=new_preset.tags or [],
            prompt_text="",
            camera_params={
                "camera_model": new_preset.camera_model,
                "focal_length": new_preset.focal_length,
                "aperture": new_preset.aperture,
                "depth_of_field": new_preset.depth_of_field,
                "shutter_speed": new_preset.shutter_speed,
                "shutter_angle": new_preset.shutter_angle,
                "camera_movement": new_preset.camera_movement,
                "camera_angle": new_preset.camera_angle,
                "aspect_ratio": new_preset.aspect_ratio,
                "visual_style": new_preset.visual_style,
            },
            style_params=None,
            script_text=None,
            pipeline_config=None,
            is_public=new_preset.is_public,
            is_approved=new_preset.is_approved,
            usage_count=new_preset.usage_count,
            created_at=new_preset.created_at.isoformat() if new_preset.created_at else None,
            updated_at=new_preset.updated_at.isoformat() if new_preset.updated_at else None,
        )

    # 非 camera 类型走 PromptPreset service
    preset = await svc.create_preset(
        db,
        user_id=current_user.id,
        name=payload.name,
        prompt_text=payload.prompt_text,
        description=payload.description,
        preset_type=payload.type,
        category=payload.category,
        tags=payload.tags,
        camera_params=payload.camera_params,
        style_params=payload.style_params,
        script_text=payload.script_text,
        pipeline_config=payload.pipeline_config,
        is_public=payload.is_public,
    )
    return PresetResponse.model_validate(preset)


@router.get("/{preset_id}", response_model=PresetResponse, summary="获取提示词预设详情")
async def get_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个提示词预设详情"""
    preset = await svc.get_preset(db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="提示词预设不存在")
    # 权限：自己的或公开审核通过的
    if preset.user_id != current_user.id and not (preset.is_public and preset.is_approved):
        raise HTTPException(status_code=403, detail="无权查看")
    return PresetResponse.model_validate(preset)


@router.put("/{preset_id}", response_model=PresetResponse, summary="更新提示词预设")
async def update_preset(
    preset_id: int,
    payload: PresetUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新预设（仅创建者）。

    - 自动按预设类型分发到对应 service
    - 硬约束：被驳回（is_rejected=True）的预设不可设为 is_public=True，
      防止通过 update 绕过 submit 检查
    """
    # 先查 PromptPreset
    preset = await svc.get_preset(db, preset_id)
    is_camera = False
    if not preset:
        # 再查 CameraPreset
        from app.services import camera_preset_service as cam_svc
        cp = await cam_svc.get_preset(db, preset_id)
        if cp:
            preset = cp
            is_camera = True

    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")
    if preset.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改")

    update_data = payload.model_dump(exclude_unset=True)

    # 硬约束：被驳回不可再公开
    if (
        getattr(preset, "is_rejected", False)
        and update_data.get("is_public") is True
    ):
        raise HTTPException(
            status_code=403,
            detail="该预设已被管理员驳回，不可再次设为公开",
        )

    if is_camera:
        from app.services import camera_preset_service as cam_svc
        # camera 类型只更新 CameraPreset 支持的字段；忽略 prompt_text/style_params 等无关字段
        camera_fields = {
            "name", "description", "category", "tags",
            "is_public", "is_approved",
        }
        camera_update = {k: v for k, v in update_data.items() if k in camera_fields}
        # camera_params 拆解为顶层字段
        if "camera_params" in update_data and isinstance(update_data["camera_params"], dict):
            cp_map = update_data["camera_params"]
            for cp_key in [
                "camera_model", "focal_length", "aperture", "depth_of_field",
                "shutter_speed", "shutter_angle", "camera_movement",
                "camera_angle", "aspect_ratio", "visual_style",
            ]:
                if cp_key in cp_map:
                    camera_update[cp_key] = cp_map[cp_key]
        updated = await cam_svc.update_preset(db, preset_id, **camera_update)
        # 转为统一响应格式
        return PresetResponse(
            id=updated.id,
            user_id=updated.user_id,
            name=updated.name,
            description=updated.description,
            type="camera",
            category=updated.category,
            tags=updated.tags or [],
            prompt_text="",
            camera_params={
                "camera_model": updated.camera_model,
                "focal_length": updated.focal_length,
                "aperture": updated.aperture,
                "depth_of_field": updated.depth_of_field,
                "shutter_speed": updated.shutter_speed,
                "shutter_angle": updated.shutter_angle,
                "camera_movement": updated.camera_movement,
                "camera_angle": updated.camera_angle,
                "aspect_ratio": updated.aspect_ratio,
                "visual_style": updated.visual_style,
            },
            style_params=None,
            script_text=None,
            pipeline_config=None,
            is_public=updated.is_public,
            is_approved=updated.is_approved,
            usage_count=updated.usage_count,
            created_at=updated.created_at.isoformat() if updated.created_at else None,
            updated_at=updated.updated_at.isoformat() if updated.updated_at else None,
        )

    # 非 camera 类型走 PromptPreset service
    updated = await svc.update_preset(db, preset_id, **update_data)
    return PresetResponse.model_validate(updated)


@router.delete("/{preset_id}", summary="删除提示词预设")
async def delete_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """删除提示词预设（仅创建者）"""
    preset = await svc.get_preset(db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="提示词预设不存在")
    if preset.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除")

    ok = await svc.delete_preset(db, preset_id)
    if not ok:
        raise HTTPException(status_code=400, detail="删除失败")
    return {"message": "已删除"}


# ---------- 导入/导出 ----------

@router.get("/export", summary="导出预设为 JSON")
async def export_presets(
    type: Optional[str] = Query(None, description="导出类型（camera/prompt/style/script/pipeline），不传则导出所有"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    导出当前用户的预设为 JSON 数组。

    - 指定 type → 仅导出该类型
    - 不指定 → 导出所有类型
    """
    items, _ = await preset_aggregator.aggregate_presets(
        db,
        user_id=current_user.id,
        preset_type=type,
        sort="new",
        page=1,
        page_size=10000,
    )
    # 只导出自己的预设
    own_items = [item for item in items if item.get("user_id") == current_user.id]
    return own_items


@router.post("/import", summary="批量导入预设")
async def import_presets(
    payload: list[dict],
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量导入预设（JSON 数组）。

    每条记录按 name 检查是否与用户已有预设重名：
    - 重名 → 自动追加 " (导入)" 后缀
    - 不重名 → 直接用原名
    """
    imported = []
    skipped = []
    renamed = []

    for item in payload:
        name = item.get("name", "未命名")
        preset_type = item.get("type", "prompt")

        # 检查重名
        existing_result = await db.execute(
            select(PromptPreset).filter(
                and_(
                    PromptPreset.user_id == current_user.id,
                    PromptPreset.name == name,
                )
            )
        )
        if existing_result.scalar_one_or_none():
            name = f"{name} (导入)"
            renamed.append(name)

        try:
            preset = await svc.create_preset(
                db,
                user_id=current_user.id,
                name=name,
                prompt_text=item.get("prompt_text", ""),
                description=item.get("description"),
                preset_type=preset_type,
                category=item.get("category", "通用"),
                tags=item.get("tags", []),
                camera_params=item.get("camera_params"),
                style_params=item.get("style_params"),
                script_text=item.get("script_text"),
                pipeline_config=item.get("pipeline_config"),
                is_public=False,
            )
            imported.append(PresetResponse.model_validate(preset))
        except Exception:
            skipped.append(name)

    return {
        "imported": len(imported),
        "skipped": len(skipped),
        "renamed": len(renamed),
        "items": [item.model_dump() for item in imported],
    }


# ---------- Fork（复制预设） ----------

@router.post("/{preset_id}/fork", summary="Fork 预设")
async def fork_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    复制一个公开预设到当前用户。

    - 重置 is_public=False, is_approved=False, usage_count=0
    - 名称不变；若当前用户已有同名预设，追加 " (副本)" 后缀
    - 支持所有类型预设：camera 类型走 CameraPreset 表，其他走 PromptPreset 表
    """
    from app.services import camera_preset_service as cam_svc

    # 先查 PromptPreset（覆盖 prompt/style/script/pipeline 类型）
    result = await db.execute(
        select(PromptPreset).filter(PromptPreset.id == preset_id)
    )
    preset = result.scalar_one_or_none()

    # 若 PromptPreset 没命中，尝试查 CameraPreset
    camera_preset = None
    if not preset:
        result = await db.execute(
            select(CameraPreset).filter(CameraPreset.id == preset_id)
        )
        camera_preset = result.scalar_one_or_none()

    if not preset and not camera_preset:
        raise HTTPException(status_code=404, detail="预设不存在")

    # 统一取源预设的关键字段
    if camera_preset:
        src_user_id = camera_preset.user_id
        src_is_visible = camera_preset.is_public and camera_preset.is_approved
        src_name = camera_preset.name
        src_type = "camera"
    else:
        src_user_id = preset.user_id
        src_is_visible = preset.is_public and preset.is_approved
        src_name = preset.name
        src_type = preset.type

    # 可见性检查：自己的或公开审核通过的才能 fork
    if src_user_id != current_user.id and not src_is_visible:
        raise HTTPException(status_code=403, detail="无权复制此预设")

    # 处理重名（跨表检查 CameraPreset + PromptPreset）
    name = src_name
    existing_pp = await db.execute(
        select(PromptPreset).filter(
            and_(PromptPreset.user_id == current_user.id, PromptPreset.name == name)
        )
    )
    existing_cp = await db.execute(
        select(CameraPreset).filter(
            and_(CameraPreset.user_id == current_user.id, CameraPreset.name == name)
        )
    )
    if existing_pp.scalar_one_or_none() or existing_cp.scalar_one_or_none():
        name = f"{name} (副本)"

    # 按 type 分发到对应 service
    if src_type == "camera" and camera_preset:
        new_preset = await cam_svc.create_preset(
            db,
            user_id=current_user.id,
            name=name,
            description=camera_preset.description,
            category=camera_preset.category,
            tags=camera_preset.tags or [],
            camera_model=camera_preset.camera_model,
            focal_length=camera_preset.focal_length,
            aperture=camera_preset.aperture,
            depth_of_field=camera_preset.depth_of_field,
            shutter_speed=camera_preset.shutter_speed,
            shutter_angle=camera_preset.shutter_angle,
            camera_movement=camera_preset.camera_movement,
            camera_angle=camera_preset.camera_angle,
            aspect_ratio=camera_preset.aspect_ratio,
            visual_style=camera_preset.visual_style,
            is_public=False,
        )
        # 转为统一响应格式（camera 字段映射到 camera_params）
        return PresetResponse(
            id=new_preset.id,
            user_id=new_preset.user_id,
            name=new_preset.name,
            description=new_preset.description,
            type="camera",
            category=new_preset.category,
            tags=new_preset.tags or [],
            prompt_text="",
            camera_params={
                "camera_model": new_preset.camera_model,
                "focal_length": new_preset.focal_length,
                "aperture": new_preset.aperture,
                "depth_of_field": new_preset.depth_of_field,
                "shutter_speed": new_preset.shutter_speed,
                "shutter_angle": new_preset.shutter_angle,
                "camera_movement": new_preset.camera_movement,
                "camera_angle": new_preset.camera_angle,
                "aspect_ratio": new_preset.aspect_ratio,
                "visual_style": new_preset.visual_style,
            },
            style_params=None,
            script_text=None,
            pipeline_config=None,
            is_public=new_preset.is_public,
            is_approved=new_preset.is_approved,
            usage_count=new_preset.usage_count,
            created_at=new_preset.created_at.isoformat() if new_preset.created_at else None,
            updated_at=new_preset.updated_at.isoformat() if new_preset.updated_at else None,
        )

    # 非 camera 类型：走 PromptPreset 表
    new_preset = await svc.create_preset(
        db,
        user_id=current_user.id,
        name=name,
        prompt_text=preset.prompt_text,
        description=preset.description,
        preset_type=preset.type,
        category=preset.category,
        tags=preset.tags or [],
        camera_params=preset.camera_params,
        style_params=preset.style_params,
        script_text=preset.script_text,
        pipeline_config=preset.pipeline_config,
        is_public=False,
    )
    return PresetResponse.model_validate(new_preset)


# ---------- 预设关联作品查询（展示形态） ----------

@router.get("/{preset_id}/works", summary="获取使用该预设的公开作品")
async def get_preset_works(
    preset_id: int,
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(24, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    获取使用指定预设生成的公开作品列表（未登录也可访问）。

    用于：
    - 预设中心详情抽屉"作品效果" section
    - 预设中心主页面"作品展示" Tab 视图

    流程：
    1. 在 prompt_presets / camera_presets 两表中查找预设
    2. 可见性校验：自己的或公开审核通过的
    3. 查询 generations 表 preset_id=preset_id 且公开审核通过的作品
    """
    # 校验预设存在 + 可见
    preset = await svc.get_preset(db, preset_id)
    if not preset:
        # 尝试 camera_presets 表
        from app.services import camera_preset_service as cam_svc
        preset = await cam_svc.get_preset(db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")

    src_user_id = preset.user_id
    src_is_visible = preset.is_public and preset.is_approved
    current_uid = current_user.id if current_user else None
    if src_user_id != current_uid and not src_is_visible:
        raise HTTPException(status_code=403, detail="无权查看此预设的作品")

    # 查询使用该预设的公开作品
    stmt = select(Generation).filter(
        Generation.is_public == True,       # noqa: E712
        Generation.status == "success",
        Generation.result_url.isnot(None),
        Generation.moderation_status == "approved",
        Generation.preset_id == preset_id,
    )

    # 总数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one() or 0

    # 排序 + 分页
    stmt = stmt.order_by(
        desc(Generation.public_shared_at),
        desc(Generation.created_at),
    ).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()

    # 批量查询作者
    user_ids = {item.user_id for item in items if item.user_id is not None}
    authors_map: dict = {}
    if user_ids:
        user_stmt = select(User).filter(User.id.in_(list(user_ids)))
        for u in (await db.execute(user_stmt)).scalars().all():
            authors_map[u.id] = u

    # 批量查询当前用户的点赞状态
    liked_ids: set = set()
    if current_user and items:
        like_stmt = select(PlazaLike.generation_id).filter(
            PlazaLike.user_id == current_user.id,
            PlazaLike.generation_id.in_([item.id for item in items]),
        )
        liked_ids = {row[0] for row in (await db.execute(like_stmt)).all()}

    # 复用 plaza 路由的响应构建器
    works = [
        _build_plaza_work(
            item,
            authors_map.get(item.user_id),
            current_uid,
            liked_ids,
        )
        for item in items
    ]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": works,
    }


# ---------- 公开审核 ----------

@router.post("/{preset_id}/submit", summary="提交审核")
async def submit_for_review(
    preset_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    将预设提交公开审核。

    设置 is_public=True, is_approved=False，
    预设进入待审核状态，管理员通过后可公开可见。

    硬约束：被管理员驳回过的预设（is_rejected=True）不可再次提交，
    返回 403。
    """
    preset = await svc.get_preset(db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="提示词预设不存在")
    if preset.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")
    # 被驳回不可再公开（硬约束）
    if getattr(preset, "is_rejected", False):
        raise HTTPException(
            status_code=403,
            detail="该预设已被管理员驳回，不可再次提交公开审核",
        )

    updated = await svc.update_preset(
        db, preset_id, is_public=True, is_approved=False
    )
    return PresetResponse.model_validate(updated)



