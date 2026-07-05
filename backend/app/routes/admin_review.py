# =====================================================
# 统一审核管理路由（管理员/审核员）
#
# 聚合所有类型的审核任务：作品、预设
# 走一套统一的列表 + 通过 + 驳回逻辑
#
# API 列表:
#   GET    /admin/review/list         - 统一审核列表（支持类型/状态筛选）
#   POST   /admin/review/{id}/approve - 审核通过
#   POST   /admin/review/{id}/reject  - 驳回
#   POST   /admin/review/batch-approve - 批量通过
#   POST   /admin/review/batch-reject  - 批量驳回
#   GET    /admin/review/stats        - 各类型待审核统计
# =====================================================

import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_async_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.generation import Generation
from app.models.prompt_preset import PresetIndex

# =====================================================
# 作品审核：仅展示公开到广场的作品，与旧 ModerationView 行为保持一致
# =====================================================
WORK_REVIEW_ONLY_PUBLIC = True

logger = logging.getLogger("agnes_platform")
router = APIRouter(prefix="/admin/review", tags=["管理员-统一审核"])


# 审核类型枚举（流水线模板审核已下线，仅保留作品 / 预设两类）
REVIEW_TYPES = ("work", "preset")
REVIEW_STATUSES = ("pending", "approved", "rejected", "all")
# AI 预审状态枚举
AI_MODERATION_STATUSES = ("pending", "passed", "violated", "failed", "none", "all")


# =====================================================
# 统一审核列表
# =====================================================

@router.get("/list", summary="统一审核列表")
async def list_review_items(
    review_type: str = Query("all", description="类型筛选：work / preset / template / all"),
    status: str = Query("pending", description="状态：pending / approved / rejected / all"),
    keyword: Optional[str] = Query(None, description="关键词搜索（名称/描述/提示词）"),
    item_id: Optional[int] = Query(None, description="按内容 ID 精确搜索"),
    user_id: Optional[int] = Query(None, description="按创作者用户 ID 搜索"),
    username: Optional[str] = Query(None, description="按用户名模糊搜索（仅作品类型生效）"),
    work_type: Optional[str] = Query(None, description="作品子类型筛选：image / video"),
    ai_status: Optional[str] = Query(None, description="AI 预审结果筛选：pending / passed / violated / failed / none / all（仅作品类型生效）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取统一审核列表，聚合作品、预设、模板三种类型。

    返回格式：
    {
      items: [{ id, review_type, item_id, name, description, user_id, status, created_at, ... }],
      total, page, page_size
    }
    """
    if not current_user.is_admin and not current_user.role in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="仅管理员/审核员可访问")

    if review_type != "all" and review_type not in REVIEW_TYPES:
        raise HTTPException(status_code=400, detail=f"review_type 必须是 {', '.join(REVIEW_TYPES + ('all',))} 之一")
    if status not in REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail=f"status 必须是 {', '.join(REVIEW_STATUSES)} 之一")
    if work_type and work_type not in ("image", "video"):
        raise HTTPException(status_code=400, detail="work_type 必须是 image / video 之一")
    if ai_status and ai_status not in AI_MODERATION_STATUSES:
        raise HTTPException(status_code=400, detail=f"ai_status 必须是 {', '.join(AI_MODERATION_STATUSES)} 之一")

    # ---------- 分类型查询 ----------
    all_items: List[Dict[str, Any]] = []

    # 1. 作品审核
    if review_type in ("all", "work"):
        try:
            work_items = await _query_work_reviews(
                db, status, keyword, item_id, user_id, username, work_type, ai_status
            )
            all_items.extend(work_items)
        except Exception:
            logger.exception("查询作品审核列表失败")

    # 2. 预设审核
    if review_type in ("all", "preset"):
        try:
            preset_items = await _query_preset_reviews(db, status, keyword, item_id, user_id)
            all_items.extend(preset_items)
        except Exception:
            logger.exception("查询预设审核列表失败")

    # 按创建时间倒序
    all_items.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    # 分页
    total = len(all_items)
    start = (page - 1) * page_size
    end = start + page_size
    paged_items = all_items[start:end]

    return {
        "items": paged_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# =====================================================
# 统计
# =====================================================

@router.get("/stats", summary="各类型待审核统计")
async def get_review_stats(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """获取各类型待审核数量统计，含 AI 预审结果分布"""
    if not current_user.is_admin and not current_user.role in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="仅管理员/审核员可访问")

    # 作品待审核数
    work_pending = 0
    try:
        result = await db.execute(
            select(func.count()).select_from(Generation).filter(
                Generation.moderation_status == "pending"
            )
        )
        work_pending = result.scalar_one()
    except Exception:
        logger.exception("统计作品待审核数失败")

    # 预设待审核数
    preset_pending = 0
    try:
        result = await db.execute(
            select(func.count()).select_from(PresetIndex).filter(
                and_(
                    PresetIndex.is_public == True,  # noqa: E712
                    PresetIndex.is_approved == False,  # noqa: E712
                )
            )
        )
        preset_pending = result.scalar_one()
    except Exception:
        logger.exception("统计预设待审核数失败")

    # 模板待审核数（模板审核已下线，恒为 0）
    # 保留字段是为了兼容前端 UnifiedReview.vue 的 stats 显示

    # ===== AI 预审结果分布（仅作品）=====
    # ai_passed_pending：AI 预审通过、等待人工复审的项
    ai_passed_pending = 0
    # ai_violated：AI 判违规（已自动屏蔽）
    ai_violated = 0
    # ai_failed：AI 审核失败、需人工兜底
    ai_failed = 0
    # ai_pending：AI 审核进行中
    ai_pending = 0
    try:
        # AI 通过且仍待人工复审
        result = await db.execute(
            select(func.count()).select_from(Generation).filter(
                and_(
                    Generation.ai_moderation_status == "passed",
                    Generation.moderation_status == "pending",
                )
            )
        )
        ai_passed_pending = result.scalar_one()

        # AI 判违规
        result = await db.execute(
            select(func.count()).select_from(Generation).filter(
                Generation.ai_moderation_status == "violated"
            )
        )
        ai_violated = result.scalar_one()

        # AI 失败
        result = await db.execute(
            select(func.count()).select_from(Generation).filter(
                Generation.ai_moderation_status == "failed"
            )
        )
        ai_failed = result.scalar_one()

        # AI 审核中
        result = await db.execute(
            select(func.count()).select_from(Generation).filter(
                Generation.ai_moderation_status == "pending"
            )
        )
        ai_pending = result.scalar_one()
    except Exception:
        logger.exception("统计 AI 预审结果分布失败")

    return {
        "work_pending": work_pending,
        "preset_pending": preset_pending,
        # 模板审核已下线，保留字段恒为 0（兼容前端 stats 显示）
        "template_pending": 0,
        "template_revision_pending": 0,
        "total_pending": work_pending + preset_pending,
        # AI 预审结果分布
        "ai_passed_pending": ai_passed_pending,
        "ai_violated": ai_violated,
        "ai_failed": ai_failed,
        "ai_pending": ai_pending,
    }


# =====================================================
# 审核通过
# =====================================================

@router.post("/{review_type}/{item_id}/approve", summary="审核通过")
async def approve_item(
    review_type: str,
    item_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    审核通过一个条目。

    review_type: work / preset / template
    item_id: 对应类型的 ID
    """
    if not current_user.is_admin and not current_user.role in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="仅管理员/审核员可操作")

    if review_type not in REVIEW_TYPES:
        raise HTTPException(status_code=400, detail=f"review_type 必须是 {', '.join(REVIEW_TYPES)} 之一")

    if review_type == "work":
        # 作品审核通过（与旧 admin_moderation 行为保持一致：清空 flags 和 reason，记录审核人和时间）
        from datetime import datetime
        result = await db.execute(select(Generation).filter(Generation.id == item_id))
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="作品不存在")
        item.moderation_status = "approved"
        item.moderation_reason = None
        item.moderation_flags = None
        # 人工审核完成后清空 AI 预审状态
        item.ai_moderation_status = None
        item.moderated_by = current_user.id
        item.moderated_at = datetime.utcnow()
        await db.commit()
        logger.info("[统一审核] %s 审核通过作品 id=%d", current_user.username, item_id)
        return {"message": "审核通过", "review_type": review_type, "item_id": item_id}

    elif review_type == "preset":
        # 预设审核通过（item_id 是 preset_index 表的 id）
        result = await db.execute(select(PresetIndex).filter(PresetIndex.id == item_id))
        entry = result.scalar_one_or_none()
        if not entry:
            raise HTTPException(status_code=404, detail="待审核预设不存在")

        from app.services import camera_preset_service as cam_svc
        from app.services import prompt_preset_service as prompt_svc

        if entry.preset_type == "camera":
            await cam_svc.update_preset(
                db, entry.preset_id, is_approved=True, is_rejected=False
            )
        else:
            await prompt_svc.update_preset(
                db, entry.preset_id, is_approved=True, is_rejected=False
            )
        return {"message": "审核通过", "review_type": review_type, "item_id": item_id}


# =====================================================
# 驳回
# =====================================================

@router.post("/{review_type}/{item_id}/reject", summary="驳回")
async def reject_item(
    review_type: str,
    item_id: int,
    payload: Dict[str, Any] = Body(default_factory=dict),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    驳回一个条目。

    review_type: work / preset / template
    item_id: 对应类型的 ID
    payload.reason: 驳回理由（可选）
    """
    if not current_user.is_admin and not current_user.role in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="仅管理员/审核员可操作")

    if review_type not in REVIEW_TYPES:
        raise HTTPException(status_code=400, detail=f"review_type 必须是 {', '.join(REVIEW_TYPES)} 之一")

    reason = (payload or {}).get("reason") or ""

    if review_type == "work":
        # 作品驳回（与旧 admin_moderation 行为保持一致：记录审核人、时间，并保留 is_public 状态以保留历史记录可回看）
        from datetime import datetime
        result = await db.execute(select(Generation).filter(Generation.id == item_id))
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="作品不存在")
        item.moderation_status = "rejected"
        item.moderation_reason = reason or "管理员审核不通过"
        item.moderated_by = current_user.id
        item.moderated_at = datetime.utcnow()
        # 人工驳回后清空 AI 预审状态（以人工结果为准）
        item.ai_moderation_status = None
        # 注意：不修改 is_public，以便用户在审核历史中看到驳回记录；广场查询时按 moderation_status 过滤即可
        await db.commit()
        logger.info("[统一审核] %s 驳回作品 id=%d reason=%s", current_user.username, item_id, reason)
        return {"message": "已驳回", "review_type": review_type, "item_id": item_id}

    elif review_type == "preset":
        # 预设驳回（item_id 是 preset_index 表的 id）
        result = await db.execute(select(PresetIndex).filter(PresetIndex.id == item_id))
        entry = result.scalar_one_or_none()
        if not entry:
            raise HTTPException(status_code=404, detail="待审核预设不存在")

        from app.services import camera_preset_service as cam_svc
        from app.services import prompt_preset_service as prompt_svc

        if entry.preset_type == "camera":
            await cam_svc.update_preset(
                db, entry.preset_id,
                is_public=False, is_approved=False, is_rejected=True,
            )
        else:
            await prompt_svc.update_preset(
                db, entry.preset_id,
                is_public=False, is_approved=False, is_rejected=True,
            )
        return {"message": "已驳回", "review_type": review_type, "item_id": item_id}


# =====================================================
# 批量通过
# =====================================================

@router.post("/batch-approve", summary="批量审核通过")
async def batch_approve(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量审核通过。

    请求体：{ items: [{ review_type, item_id }, ...] }
    """
    if not current_user.is_admin and not current_user.role in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="仅管理员/审核员可操作")

    items = payload.get("items") or []
    success = 0
    failed = 0

    for item in items:
        try:
            await approve_item(
                review_type=item["review_type"],
                item_id=item["item_id"],
                db=db,
                current_user=current_user,
            )
            success += 1
        except Exception:
            failed += 1

    return {"message": f"批量处理完成：成功 {success} 个，失败 {failed} 个", "success": success, "failed": failed}


# =====================================================
# 批量驳回
# =====================================================

@router.post("/batch-reject", summary="批量驳回")
async def batch_reject(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量驳回。

    请求体：{ items: [{ review_type, item_id }, ...], reason: "驳回理由" }
    """
    if not current_user.is_admin and not current_user.role in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="仅管理员/审核员可操作")

    items = payload.get("items") or []
    reason = payload.get("reason") or ""
    success = 0
    failed = 0

    for item in items:
        try:
            await reject_item(
                review_type=item["review_type"],
                item_id=item["item_id"],
                payload={"reason": reason},
                db=db,
                current_user=current_user,
            )
            success += 1
        except Exception:
            failed += 1

    return {"message": f"批量处理完成：成功 {success} 个，失败 {failed} 个", "success": success, "failed": failed}


# =====================================================
# 内部辅助函数：分类型查询审核列表
# =====================================================

async def _query_work_reviews(
    db: AsyncSession,
    status: str,
    keyword: Optional[str],
    item_id: Optional[int],
    user_id: Optional[int],
    username: Optional[str] = None,
    work_type: Optional[str] = None,
    ai_status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """查询作品审核列表（仅展示公开到广场的作品，与旧 ModerationView 行为一致）"""
    query = select(Generation)

    # 仅展示公开到广场的作品
    if WORK_REVIEW_ONLY_PUBLIC:
        query = query.filter(Generation.is_public == True)  # noqa: E712

    # 状态筛选
    if status != "all":
        query = query.filter(Generation.moderation_status == status)

    # 作品子类型筛选：image / video
    if work_type:
        query = query.filter(Generation.type == work_type)

    # AI 预审结果筛选
    if ai_status and ai_status != "all":
        if ai_status == "none":
            # 未触发 AI 审核（字段为 NULL）
            query = query.filter(Generation.ai_moderation_status.is_(None))
        else:
            query = query.filter(Generation.ai_moderation_status == ai_status)

    # 按内容 ID 精确搜索
    if item_id:
        query = query.filter(Generation.id == item_id)

    # 按创作者用户 ID 搜索
    if user_id:
        query = query.filter(Generation.user_id == user_id)

    # 按用户名模糊搜索（先查 User 表拿到 user_ids，再过滤 Generation）
    if username:
        user_subq = select(User.id).filter(User.username.contains(username))
        user_result = await db.execute(user_subq)
        user_ids = [row[0] for row in user_result.all()]
        if user_ids:
            query = query.filter(Generation.user_id.in_(user_ids))
        else:
            # 没匹配到用户，返回空
            return []

    # 关键词搜索（匹配 prompt）
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(Generation.prompt.ilike(pattern))

    query = query.order_by(Generation.created_at.desc()).limit(200)
    result = await db.execute(query)
    items = result.scalars().all()

    # 批量查询作者信息（用户名/昵称）
    user_ids_set = {g.user_id for g in items if g.user_id is not None}
    authors_map: dict = {}
    if user_ids_set:
        user_stmt = select(User).filter(User.id.in_(list(user_ids_set)))
        user_result = await db.execute(user_stmt)
        for u in user_result.scalars().all():
            authors_map[u.id] = u

    return [
        {
            "id": f"work-{item.id}",
            "review_type": "work",
            "item_id": item.id,
            "name": (item.prompt or "")[:50] + ("..." if item.prompt and len(item.prompt) > 50 else ""),
            "description": item.prompt,
            "prompt": item.prompt,
            "user_id": item.user_id,
            "username": authors_map[item.user_id].username if item.user_id and authors_map.get(item.user_id) else None,
            "nickname": getattr(authors_map.get(item.user_id), "nickname", None) if item.user_id and authors_map.get(item.user_id) else None,
            "status": item.moderation_status,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "public_shared_at": item.public_shared_at.isoformat() if item.public_shared_at else None,
            "work_type": item.type,
            "model": item.model,
            "result_url": item.result_url,
            # 视频类型直接用 result_url 当缩略图会失败（el-image 无法渲染视频），
            # 改为指向缩略图端点，由后端 ffmpeg 提取首帧返回 JPEG。
            "thumbnail_url": (
                f"/api/history/video/{item.id}/thumbnail"
                if item.type == "video"
                else item.result_url
            ),
            "is_public": item.is_public,
            "likes_count": getattr(item, "likes_count", 0) or 0,
            "views_count": getattr(item, "views_count", 0) or 0,
            "moderation_flags": item.moderation_flags or [],
            "moderation_reason": item.moderation_reason,
            "moderated_at": item.moderated_at.isoformat() if getattr(item, "moderated_at", None) else None,
            # AI 预审状态：NULL / pending / passed / violated / failed
            "ai_moderation_status": item.ai_moderation_status,
        }
        for item in items
    ]


async def _query_preset_reviews(
    db: AsyncSession,
    status: str,
    keyword: Optional[str],
    item_id: Optional[int],
    user_id: Optional[int],
) -> List[Dict[str, Any]]:
    """查询预设审核列表"""
    query = select(PresetIndex)

    # 预设状态映射
    if status == "pending":
        query = query.filter(
            and_(
                PresetIndex.is_public == True,  # noqa: E712
                PresetIndex.is_approved == False,  # noqa: E712
            )
        )
    elif status == "approved":
        query = query.filter(
            and_(
                PresetIndex.is_public == True,  # noqa: E712
                PresetIndex.is_approved == True,  # noqa: E712
            )
        )
    elif status == "rejected":
        query = query.filter(PresetIndex.is_rejected == True)  # noqa: E712
    # all: 不额外限制

    if item_id:
        query = query.filter(PresetIndex.id == item_id)
    if user_id:
        query = query.filter(PresetIndex.user_id == user_id)
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                PresetIndex.name.ilike(pattern),
                PresetIndex.description.ilike(pattern),
            )
        )

    query = query.order_by(PresetIndex.created_at.desc()).limit(200)
    result = await db.execute(query)
    entries = result.scalars().all()

    # 批量查询作者信息
    user_ids_set = {e.user_id for e in entries if e.user_id is not None}
    authors_map: dict = {}
    if user_ids_set:
        user_stmt = select(User).filter(User.id.in_(list(user_ids_set)))
        user_result = await db.execute(user_stmt)
        for u in user_result.scalars().all():
            authors_map[u.id] = u

    # 计算状态
    def _preset_status(entry) -> str:
        if getattr(entry, "is_rejected", False):
            return "rejected"
        if entry.is_public and entry.is_approved:
            return "approved"
        if entry.is_public and not entry.is_approved:
            return "pending"
        return "private"

    return [
        {
            "id": f"preset-{entry.id}",
            "review_type": "preset",
            "item_id": entry.id,
            "preset_type": entry.preset_type,
            "preset_original_id": entry.preset_id,
            "name": entry.name,
            "description": entry.description,
            "user_id": entry.user_id,
            "username": authors_map[entry.user_id].username if entry.user_id and authors_map.get(entry.user_id) else None,
            "nickname": getattr(authors_map.get(entry.user_id), "nickname", None) if entry.user_id and authors_map.get(entry.user_id) else None,
            "category": entry.category,
            "tags": entry.tags or [],
            "usage_count": getattr(entry, "usage_count", 0) or 0,
            "status": _preset_status(entry),
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
        for entry in entries
    ]


