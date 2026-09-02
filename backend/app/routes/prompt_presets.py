# =====================================================
# 提示词预设路由 — 统一预设广场 API
# 五类预设（style/effect/camera/prompt/script）统一存 prompt_presets 表
# 列表支持 tab（广场/我的收藏/最近使用）+ 类型/分类/搜索/排序
# 审核：投稿 submit + admin_review（走 preset_index 队列）
# =====================================================

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_async_db
from app.core.response import ok
from app.core.security import get_current_user, get_current_user_optional
from app.models.generation import Generation
from app.models.plaza_like import PlazaLike
from app.models.user import User
from app.models.prompt_preset import PromptPreset
from app.routes.plaza import _build_plaza_work
from app.services import prompt_preset_service as svc
from app.services import preset_cover_service as cover_svc


router = APIRouter(prefix="/presets", tags=["提示词预设"])


# ---------- 请求/响应模型 ----------

class PresetCreate(BaseModel):
    """创建提示词预设请求"""
    name: str = Field(..., description="预设名称")
    prompt_text: str = Field("", description="提示词文本")
    description: Optional[str] = Field(None, description="预设描述")
    type: str = Field("prompt", description="预设类型（style/effect/camera/prompt/script）")
    category: Optional[str] = Field(None, description="分类（默认 '通用'）")
    tags: Optional[list[str]] = Field(None, description="标签列表")
    camera_params: Optional[dict] = Field(None, description="摄像机参数（JSON，camera 类型）")
    style_params: Optional[dict] = Field(None, description="风格参数（JSON，兼容保留）")
    prompt_config: Optional[dict] = Field(None, description="提示词配置（JSON：prefix/suffix/negative_prompt，style/effect 类型）")
    cover_image: Optional[str] = Field(None, description="封面图 URL")
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
    prompt_config: Optional[dict] = Field(None, description="提示词配置（JSON）")
    cover_image: Optional[str] = Field(None, description="封面图 URL")
    is_official: Optional[bool] = Field(None, description="官方标记（仅管理员生效）")
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
    prompt_config: Optional[dict] = None
    cover_image: Optional[str] = None
    cover_video: Optional[str] = None
    is_public: bool
    is_approved: bool
    is_official: bool = False
    usage_count: int = 0
    # 广场列表附加字段
    author_nickname: str = ""
    is_favorite: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PresetListResponse(BaseModel):
    """提示词预设列表响应"""
    items: list[PresetResponse]
    total: int


# ---------- 列表查询 ----------

@router.get("", summary="统一预设广场列表")
async def list_presets(
    tab: str = Query("plaza", description="plaza（广场）/ favorites（我的收藏）/ recent（最近使用）/ mine（我的预设）"),
    type: Optional[str] = Query(None, description="预设类型，逗号分隔多类型（style,effect,camera,prompt,script）"),
    category: Optional[str] = Query(None, description="分类筛选"),
    q: Optional[str] = Query(None, description="搜索名称/描述/标签/作者"),
    sort: str = Query("new", description="排序：new（最新）/ hot（官方优先+最热）/ name（名称）"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(24, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """统一预设广场列表：所有类型统一读 prompt_presets，排除 pipeline"""
    preset_types = [t.strip() for t in type.split(",") if t.strip()] if type else None
    items, total = await svc.list_plaza(
        db,
        user_id=current_user.id,
        tab=tab,
        preset_types=preset_types,
        category=category,
        q=q,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return ok(data=PresetListResponse(
        items=[PresetResponse.model_validate(item) for item in items],
        total=total,
    ))


# ---------- 创建 / 更新 / 删除 ----------

@router.post("", summary="创建提示词预设")
async def create_preset(
    payload: PresetCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """创建预设（统一写入 prompt_presets；管理员创建自动标记 is_official）"""
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
        prompt_config=payload.prompt_config,
        cover_image=payload.cover_image,
        is_official=current_user.effective_is_admin,
        script_text=payload.script_text,
        pipeline_config=payload.pipeline_config,
        is_public=payload.is_public,
    )
    return ok(data=PresetResponse.model_validate(preset))


@router.get("/export", summary="导出当前用户预设为 JSON")
async def export_presets(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """导出当前用户的所有预设（JSON 数组，可用于导入）"""
    result = await db.execute(
        select(PromptPreset)
        .filter(PromptPreset.user_id == current_user.id)
        .order_by(PromptPreset.created_at.desc())
    )
    return ok(data=[
        {
            "name": p.name,
            "prompt_text": p.prompt_text or "",
            "description": p.description,
            "type": p.type,
            "category": p.category,
            "tags": p.tags or [],
            "camera_params": p.camera_params,
            "style_params": p.style_params,
            "prompt_config": p.prompt_config,
            "cover_image": p.cover_image,
            "script_text": p.script_text,
            "pipeline_config": p.pipeline_config,
        }
        for p in result.scalars().all()
    ])


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
                preset_type=item.get("type", "prompt"),
                category=item.get("category", "通用"),
                tags=item.get("tags", []),
                camera_params=item.get("camera_params"),
                style_params=item.get("style_params"),
                prompt_config=item.get("prompt_config"),
                cover_image=item.get("cover_image"),
                script_text=item.get("script_text"),
                pipeline_config=item.get("pipeline_config"),
                is_public=False,
            )
            imported.append(PresetResponse.model_validate(preset))
        except Exception:
            skipped.append(name)

    return ok(data={
        "imported": len(imported),
        "skipped": len(skipped),
        "renamed": len(renamed),
        "items": [item.model_dump() for item in imported],
    })


@router.get("/{preset_id}", summary="获取提示词预设详情")
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
    return ok(data=PresetResponse.model_validate(preset))


@router.put("/{preset_id}", summary="更新提示词预设")
async def update_preset(
    preset_id: int,
    payload: PresetUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新预设（仅创建者）。

    - 硬约束：被驳回（is_rejected=True）的预设不可设为 is_public=True，
      防止通过 update 绕过 submit 检查
    - is_official 仅管理员可设置
    """
    preset = await svc.get_preset(db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")
    if preset.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改")

    update_data = payload.model_dump(exclude_unset=True)

    # is_official 仅管理员生效
    if update_data.get("is_official") is not None and not current_user.effective_is_admin:
        update_data.pop("is_official")

    # 硬约束：被驳回不可再公开
    if (
        getattr(preset, "is_rejected", False)
        and update_data.get("is_public") is True
    ):
        raise HTTPException(
            status_code=403,
            detail="该预设已被管理员驳回，不可再次设为公开",
        )

    updated = await svc.update_preset(db, preset_id, **update_data)
    return ok(data=PresetResponse.model_validate(updated))


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

    deleted = await svc.delete_preset(db, preset_id)
    if not deleted:
        raise HTTPException(status_code=400, detail="删除失败")
    return ok(message="已删除")


# ---------- 收藏 / 使用记录 ----------

@router.post("/{preset_id}/favorite", summary="收藏/取消收藏预设")
async def favorite_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """toggle 收藏状态，返回操作后的 is_favorite"""
    is_favorite = await svc.toggle_favorite(db, current_user.id, preset_id)
    return ok(data={"is_favorite": is_favorite})


@router.post("/{preset_id}/use", summary="记录预设使用")
async def use_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """应用预设时调用：upsert 最近使用记录 + usage_count+1"""
    await svc.record_use(db, current_user.id, preset_id)
    return ok(message="ok")


# ---------- Fork（复制预设） ----------

@router.post("/{preset_id}/fork", summary="Fork 预设")
async def fork_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    复制一个预设到当前用户名下。

    - 重置 is_public=False, is_approved=False, is_official=False, usage_count=0
    - 名称不变；若当前用户已有同名预设，追加 " (副本)" 后缀
    """
    result = await db.execute(
        select(PromptPreset).filter(PromptPreset.id == preset_id)
    )
    preset = result.scalar_one_or_none()
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")

    # 可见性检查：自己的或公开审核通过的才能 fork
    if preset.user_id != current_user.id and not (preset.is_public and preset.is_approved):
        raise HTTPException(status_code=403, detail="无权复制此预设")

    # 处理重名
    name = preset.name
    existing_pp = await db.execute(
        select(PromptPreset).filter(
            and_(PromptPreset.user_id == current_user.id, PromptPreset.name == name)
        )
    )
    if existing_pp.scalar_one_or_none():
        name = f"{name} (副本)"

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
        prompt_config=preset.prompt_config,
        cover_image=preset.cover_image,
        script_text=preset.script_text,
        pipeline_config=preset.pipeline_config,
        is_public=False,
    )
    return ok(data=PresetResponse.model_validate(new_preset))


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

    用于预设详情弹层"作品效果"区块。
    """
    preset = await svc.get_preset(db, preset_id)
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

    return ok(data={
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": works,
    })


# ---------- 封面生成 ----------

@router.post("/{preset_id}/generate-cover", summary="AI 生成预设封面（管理员）")
async def generate_preset_cover(
    preset_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    为预设生成封面并写回（已生成则覆盖）。仅管理员可用（官方卡维护）。

    - effect / camera 类型 → 动态封面：视频 API 生成 4s 3:4 示例片段，
      写入 cover_video（轮询至完成，约 1-3 分钟）
    - 其他类型 → 静态封面：生图 API 512x512，写入 cover_image
    """
    if not current_user.effective_is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可生成官方封面")
    preset = await svc.get_preset(db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")

    try:
        if preset.type in cover_svc.VIDEO_COVER_TYPES:
            url = await cover_svc.generate_cover_video(preset)
            await svc.update_preset(db, preset_id, cover_video=url)
            return ok(data={"cover_video": url})
        url = await cover_svc.generate_cover_image(preset)
        await svc.update_preset(db, preset_id, cover_image=url)
        return ok(data={"cover_image": url})
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


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
    return ok(data=PresetResponse.model_validate(updated))
