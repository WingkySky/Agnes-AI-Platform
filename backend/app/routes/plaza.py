# =====================================================
# 广场（Plaza）路由（全异步）
# GET    /api/plaza/works              - 获取广场公开作品列表（分页 + 类型筛选 + 排序）
# GET    /api/plaza/works/{id}         - 获取广场作品详情（浏览数 +1）
# POST   /api/plaza/works/{id}/like    - 点赞作品（需登录）
# DELETE /api/plaza/works/{id}/like    - 取消点赞（需登录）
# GET    /api/plaza/likes/status       - 批量查询当前用户是否已点赞
#
# 关键设计：
#   - 广场浏览接口公开（未登录可访问），不暴露作者敏感信息
#   - 点赞操作需要登录，通过唯一约束防重复
#   - 作者昵称脱敏显示（如 User_123）
# =====================================================

import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, func, or_

from app.core.database import get_async_db
from app.core.security import get_current_user, get_current_user_optional
from app.models.generation import Generation
from app.models.plaza_like import PlazaLike
from app.models.user import User
from app.schemas.plaza import (
    PlazaWork,
    PlazaListResponse,
    LikeActionResponse,
    LikeStatusResponse,
)

logger = logging.getLogger("agnes_platform")
router = APIRouter()


# ---------- 工具：生成公开昵称 ----------
def _anonymize_nickname(user: Optional[User]) -> Optional[str]:
    """获取公开昵称：优先 nickname，其次 username，最终回退到 User_id。

    在广场等公开场景下，昵称由用户主动设置，展示给其他用户。
    """
    if not user:
        return None
    # 优先使用用户设置的昵称
    if user.nickname and user.nickname.strip():
        return user.nickname.strip()
    # 其次使用用户名
    if user.username:
        return user.username
    # 兜底
    return f"User_{user.id}"


# ---------- 工具：构建 PlazaWork 响应对象 ----------
def _build_plaza_work(
    record: "Generation",
    author: Optional["User"],
    current_user_id: Optional[int],
    liked_ids: Optional[set] = None,
) -> PlazaWork:
    """从 Generation 记录构建广场作品响应"""
    # 向后兼容：mode 可能为空，从 params 回退
    mode = record.mode
    if not mode and isinstance(record.params, dict):
        mode = record.params.get("mode")

    is_mine = current_user_id is not None and record.user_id == current_user_id
    is_liked = bool(liked_ids and record.id in liked_ids) if liked_ids is not None else False

    return PlazaWork(
        id=record.id,
        type=record.type,
        prompt=record.prompt,
        model=record.model,
        params=record.params,
        mode=mode,
        result_url=record.result_url,
        likes_count=getattr(record, "likes_count", 0) or 0,
        views_count=getattr(record, "views_count", 0) or 0,
        author_nickname=_anonymize_nickname(author),
        author_avatar_url=author.avatar_url if author else None,
        created_at=record.created_at,
        public_shared_at=getattr(record, "public_shared_at", None),
        is_mine=is_mine,
        is_liked=is_liked,
        preset_id=getattr(record, "preset_id", None),
    )


# =====================================================
# 广场列表接口
# =====================================================
@router.get("/plaza/works", response_model=PlazaListResponse, summary="获取广场公开作品列表")
async def get_plaza_works(
    type: str = Query("all", description="筛选类型: all / image / video"),
    sort: str = Query("latest", description="排序: latest（最新）/ popular（最热门）"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(24, ge=1, le=100, description="每页数量"),
    preset_id: Optional[int] = Query(None, description="按预设 ID 筛选作品（用于'按预设浏览'入口）"),
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    分页获取广场公开作品列表（未登录也可访问）。
    - 按 is_public=True 且 status=success 筛选
    - sort=latest 按 public_shared_at 倒序
    - sort=popular 按 likes_count 倒序
    - preset_id 不为空时，按预设筛选作品
    """
    # 基础查询：只返回公开、成功、且审核通过的作品
    stmt = select(Generation).filter(
        Generation.is_public == True,       # noqa: E712
        Generation.status == "success",
        Generation.result_url.isnot(None),
        Generation.moderation_status == "approved",  # 只展示审核通过的
    )

    # 类型筛选
    if type and type.lower() in ("image", "video"):
        stmt = stmt.filter(Generation.type == type.lower())

    # ── 按预设筛选：仅返回使用指定预设生成的作品 ──
    if preset_id is not None:
        stmt = stmt.filter(Generation.preset_id == preset_id)

    # 总数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one() or 0

    # 排序
    if sort == "popular":
        stmt = stmt.order_by(desc(Generation.likes_count), desc(Generation.public_shared_at))
    else:
        stmt = stmt.order_by(desc(Generation.public_shared_at), desc(Generation.created_at))

    # 分页
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = result.scalars().all()

    # 批量查询作者信息
    user_ids = {item.user_id for item in items if item.user_id is not None}
    authors_map: dict = {}
    if user_ids:
        user_stmt = select(User).filter(User.id.in_(list(user_ids)))
        user_result = await db.execute(user_stmt)
        for u in user_result.scalars().all():
            authors_map[u.id] = u

    # 批量查询当前用户的点赞状态
    liked_ids: set = set()
    if current_user and items:
        like_stmt = select(PlazaLike.generation_id).filter(
            PlazaLike.user_id == current_user.id,
            PlazaLike.generation_id.in_([item.id for item in items]),
        )
        like_result = await db.execute(like_stmt)
        liked_ids = {row[0] for row in like_result.all()}

    # 构建响应
    works = [
        _build_plaza_work(
            item,
            authors_map.get(item.user_id),
            current_user.id if current_user else None,
            liked_ids,
        )
        for item in items
    ]

    return PlazaListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=works,
    )


# =====================================================
# 广场作品详情接口
# =====================================================
@router.get("/plaza/works/{work_id}", response_model=PlazaWork, summary="获取广场作品详情")
async def get_plaza_work_detail(
    work_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    获取广场单个作品详情（未登录也可访问）。
    每次访问浏览数 +1。
    """
    stmt = select(Generation).filter(
        Generation.id == work_id,
        Generation.is_public == True,       # noqa: E712
        Generation.status == "success",
        Generation.moderation_status == "approved",  # 只展示审核通过的
    )
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="未找到该作品或作品未公开")

    # 浏览数 +1
    record.views_count = (record.views_count or 0) + 1
    await db.commit()
    await db.refresh(record)

    # 查询作者信息
    author = None
    if record.user_id:
        user_result = await db.execute(select(User).filter(User.id == record.user_id))
        author = user_result.scalar_one_or_none()

    # 查询当前用户是否已点赞
    liked_ids: set = set()
    if current_user:
        like_result = await db.execute(
            select(PlazaLike.generation_id).filter(
                PlazaLike.user_id == current_user.id,
                PlazaLike.generation_id == work_id,
            )
        )
        liked_ids = {row[0] for row in like_result.all()}

    return _build_plaza_work(
        record, author,
        current_user.id if current_user else None,
        liked_ids,
    )


# =====================================================
# 点赞接口
# =====================================================
@router.post("/plaza/works/{work_id}/like", response_model=LikeActionResponse, summary="点赞作品")
async def like_plaza_work(
    work_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    点赞广场作品（需登录）。
    通过唯一约束防止重复点赞。
    """
    # 验证作品存在且公开
    stmt = select(Generation).filter(
        Generation.id == work_id,
        Generation.is_public == True,       # noqa: E712
    )
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="未找到该作品")

    # 检查是否已点赞
    existing = await db.execute(
        select(PlazaLike).filter(
            PlazaLike.user_id == current_user.id,
            PlazaLike.generation_id == work_id,
        )
    )
    if existing.scalar_one_or_none():
        # 已点赞，直接返回当前状态
        return LikeActionResponse(liked=True, likes_count=record.likes_count or 0)

    # 创建点赞记录
    like = PlazaLike(
        user_id=current_user.id,
        generation_id=work_id,
    )
    db.add(like)
    record.likes_count = (record.likes_count or 0) + 1
    await db.commit()
    await db.refresh(record)

    return LikeActionResponse(liked=True, likes_count=record.likes_count)


@router.delete("/plaza/works/{work_id}/like", response_model=LikeActionResponse, summary="取消点赞")
async def unlike_plaza_work(
    work_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    取消点赞广场作品（需登录）。
    """
    # 查找点赞记录
    stmt = select(PlazaLike).filter(
        PlazaLike.user_id == current_user.id,
        PlazaLike.generation_id == work_id,
    )
    result = await db.execute(stmt)
    like = result.scalar_one_or_none()

    if not like:
        # 未点赞，直接返回当前状态
        gen_result = await db.execute(
            select(Generation).filter(Generation.id == work_id)
        )
        record = gen_result.scalar_one_or_none()
        return LikeActionResponse(liked=False, likes_count=(record.likes_count if record else 0))

    # 删除点赞记录
    await db.delete(like)

    # 更新点赞计数
    gen_result = await db.execute(
        select(Generation).filter(Generation.id == work_id)
    )
    record = gen_result.scalar_one_or_none()
    if record:
        record.likes_count = max((record.likes_count or 0) - 1, 0)

    await db.commit()
    if record:
        await db.refresh(record)

    return LikeActionResponse(liked=False, likes_count=(record.likes_count if record else 0))


# =====================================================
# 批量查询点赞状态
# =====================================================
@router.get("/plaza/likes/status", response_model=LikeStatusResponse, summary="批量查询点赞状态")
async def get_like_status(
    ids: str = Query(..., description="作品 ID 列表，逗号分隔"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量查询当前用户是否已点赞指定作品（需登录）。
    用于前端批量渲染点赞图标状态。
    """
    try:
        id_list = [int(i.strip()) for i in ids.split(",") if i.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="ids 格式错误，应为逗号分隔的数字")

    if not id_list:
        return LikeStatusResponse(liked_ids=[])

    stmt = select(PlazaLike.generation_id).filter(
        PlazaLike.user_id == current_user.id,
        PlazaLike.generation_id.in_(id_list),
    )
    result = await db.execute(stmt)
    liked_ids = [row[0] for row in result.all()]

    return LikeStatusResponse(liked_ids=liked_ids)
