# =====================================================
# 风格元素路由 — CRUD + prompt 预览
# =====================================================

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.style_element import (
    StyleElementCreate,
    StyleElementUpdate,
    StyleElementResponse,
    StyleElementListResponse,
    PromptPreviewRequest,
    PromptPreviewResponse,
)
from app.services import style_element_service as svc


router = APIRouter(prefix="/style-elements", tags=["风格元素"])

# 缩略图存放目录
_PREVIEW_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "style_previews",
)


@router.get("", response_model=StyleElementListResponse, summary="列出风格元素")
async def list_style_elements(
    layer: Optional[str] = Query(None, description="按层过滤"),
    category: Optional[str] = Query(None, description="按分类过滤"),
    is_builtin: Optional[bool] = Query(None, description="是否内置"),
    is_public: Optional[bool] = Query(None, description="是否公开"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """列出风格元素（用户可见：内置 + 自己创建的 + 公开的）"""
    elements, total = await svc.list_elements(
        db,
        layer=layer,
        category=category,
        is_builtin=is_builtin,
        is_public=is_public,
        search=search,
        limit=limit,
        offset=offset,
    )
    # 过滤：非内置元素仅返回作者自己的或公开的
    visible = [
        e for e in elements
        if e.is_builtin
        or e.is_public
        or e.author_id == current_user.id
    ]
    return StyleElementListResponse(
        items=[StyleElementResponse.model_validate(e) for e in visible],
        total=len(visible),
    )


@router.get("/layers", summary="获取所有风格层级")
async def list_layers():
    """返回所有可用的风格层级（供前端 Tab 渲染）"""
    from app.models.style_element import ALL_LAYERS
    layer_names = {
        "visual_style": "画风",
        "lighting": "光影",
        "color": "配色",
        "camera": "镜头",
        "mood": "氛围",
        "quality": "品质",
    }
    return {
        "layers": [
            {"key": k, "name": layer_names.get(k, k)}
            for k in ALL_LAYERS
        ]
    }


@router.get("/preview/{key}", summary="获取风格元素缩略图")
async def get_element_preview(key: str):
    """返回风格元素缩略图静态文件"""
    # 防目录穿越
    if "/" in key or "\\" in key or ".." in key:
        raise HTTPException(status_code=400, detail="非法 key")
    # 支持的扩展名
    for ext in (".png", ".jpg", ".webp"):
        path = os.path.join(_PREVIEW_DIR, f"{key}{ext}")
        if os.path.exists(path):
            return FileResponse(path)
    raise HTTPException(status_code=404, detail="缩略图不存在")


@router.post("/preview-prompt", response_model=PromptPreviewResponse, summary="预览拼接后的 prompt")
async def preview_prompt(
    payload: PromptPreviewRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """输入元素ID+权重，返回拼接后的完整 prompt（不存库，实时计算）"""
    elements_input = [
        {"element_id": e.element_id, "weight": e.weight}
        for e in payload.elements
    ]
    resolved = await svc.resolve_elements(db, elements_input)
    result = svc.preview_prompt(payload.base_prompt, resolved)
    return PromptPreviewResponse(**result)


@router.get("/{element_id}", response_model=StyleElementResponse, summary="获取风格元素详情")
async def get_style_element(
    element_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    element = await svc.get_element_by_id(db, element_id)
    if not element:
        raise HTTPException(status_code=404, detail="风格元素不存在")
    # 权限：非内置需作者或公开
    if not element.is_builtin and not element.is_public and element.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看")
    return StyleElementResponse.model_validate(element)


@router.post("", response_model=StyleElementResponse, summary="创建风格元素")
async def create_style_element(
    payload: StyleElementCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """创建用户自建风格元素"""
    # 自动生成 key（如用户不传）
    key = payload.key or f"user_{current_user.id}_{payload.layer}_{hash(payload.name) & 0xFFFFFF:x}"

    # 校验 key 唯一
    existing = await svc.get_element_by_key(db, key)
    if existing:
        raise HTTPException(status_code=400, detail="key 已存在")

    element = await svc.create_element(
        db,
        key=key,
        name=payload.name,
        layer=payload.layer,
        content=payload.content,
        description=payload.description,
        category=payload.category,
        negative_content=payload.negative_content,
        preview_image=payload.preview_image,
        weight_default=payload.weight_default,
        tags=payload.tags,
        is_public=payload.is_public,
        author_id=current_user.id,
    )
    return StyleElementResponse.model_validate(element)


@router.put("/{element_id}", response_model=StyleElementResponse, summary="更新风格元素")
async def update_style_element(
    element_id: int,
    payload: StyleElementUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """更新风格元素（仅作者或管理员）"""
    element = await svc.get_element_by_id(db, element_id)
    if not element:
        raise HTTPException(status_code=404, detail="风格元素不存在")
    if element.is_builtin:
        raise HTTPException(status_code=403, detail="内置元素不可修改")
    if element.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改")

    update_data = payload.model_dump(exclude_unset=True)
    updated = await svc.update_element(db, element_id, **update_data)
    return StyleElementResponse.model_validate(updated)


@router.delete("/{element_id}", summary="删除风格元素")
async def delete_style_element(
    element_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """删除风格元素（仅作者，内置不可删）"""
    element = await svc.get_element_by_id(db, element_id)
    if not element:
        raise HTTPException(status_code=404, detail="风格元素不存在")
    if element.is_builtin:
        raise HTTPException(status_code=403, detail="内置元素不可删除")
    if element.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除")

    ok = await svc.delete_element(db, element_id)
    if not ok:
        raise HTTPException(status_code=400, detail="删除失败")
    return {"message": "已删除"}
