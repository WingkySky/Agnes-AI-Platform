# =====================================================
# 内容审核管理路由（审核员/管理员）
#
# 广场作品审核：
#   GET    /api/admin/moderation/works              审核队列（按状态筛选）
#   POST   /api/admin/moderation/works/{id}/approve  审核通过
#   POST   /api/admin/moderation/works/{id}/reject   屏蔽/驳回
#   POST   /api/admin/moderation/works/batch-approve 批量通过
#   POST   /api/admin/moderation/works/batch-reject  批量屏蔽
#
# 敏感词管理：
#   GET    /api/admin/moderation/sensitive-words     敏感词列表
#   POST   /api/admin/moderation/sensitive-words     新增敏感词
#   PUT    /api/admin/moderation/sensitive-words/{id} 修改敏感词
#   DELETE /api/admin/moderation/sensitive-words/{id} 删除敏感词
# =====================================================

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_

from app.core.database import get_async_db
from app.core.security import require_permission
from app.models.user import User
from app.models.generation import Generation
from app.models.sensitive_word import SensitiveWord, SENSITIVE_CATEGORIES

logger = logging.getLogger("agnes_platform")
router = APIRouter(prefix="/admin/moderation", tags=["管理员-内容审核"])


# =====================================================
# 一、广场作品审核
# =====================================================

@router.get("/works", summary="[审核员] 审核队列列表")
async def list_moderation_works(
    status: Optional[str] = Query("pending", description="审核状态：pending/approved/rejected/all"),
    work_type: Optional[str] = Query(None, description="类型筛选：image/video"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    _moderator: User = Depends(require_permission("plaza:moderate")),
):
    """获取审核队列，支持按状态/类型筛选"""
    query = select(Generation)

    # 状态筛选
    if status and status != "all":
        if status not in ("pending", "approved", "rejected"):
            raise HTTPException(status_code=400, detail="无效的审核状态")
        query = query.filter(Generation.moderation_status == status)

    # 类型筛选
    if work_type and work_type != "all":
        if work_type not in ("image", "video"):
            raise HTTPException(status_code=400, detail="无效的类型")
        query = query.filter(Generation.type == work_type)

    # 只展示公开到广场的作品
    query = query.filter(Generation.is_public == True)

    # 排序：待审核优先（pending 在前），然后按时间倒序
    from sqlalchemy import case
    order_case = case(
        (Generation.moderation_status == "pending", 0),
        (Generation.moderation_status == "rejected", 1),
        (Generation.moderation_status == "approved", 2),
        else_=3,
    )
    query = query.order_by(order_case, Generation.public_shared_at.desc())

    # 总数
    count_query = select(Generation.id).where(
        *([c for c in query.whereclause.get_children()] if query.whereclause is not None else [True])
    )
    # 简化：单独构建 count
    count_q = select(Generation.id).filter(Generation.is_public == True)
    if status and status != "all":
        count_q = count_q.filter(Generation.moderation_status == status)
    if work_type and work_type != "all":
        count_q = count_q.filter(Generation.type == work_type)
    total_result = await db.execute(count_q)
    total = len(total_result.scalars().all())

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": g.id,
                "type": g.type,
                "prompt": g.prompt,
                "model": g.model,
                "result_url": g.result_url,
                "user_id": g.user_id,
                "is_public": g.is_public,
                "likes_count": getattr(g, "likes_count", 0),
                "views_count": getattr(g, "views_count", 0),
                "moderation_status": g.moderation_status,
                "moderation_reason": g.moderation_reason,
                "moderation_flags": g.moderation_flags,
                "moderated_at": g.moderated_at.isoformat() if g.moderated_at else None,
                "public_shared_at": g.public_shared_at.isoformat() if g.public_shared_at else None,
                "created_at": g.created_at.isoformat() if g.created_at else None,
            }
            for g in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/works/{work_id}/approve", summary="[审核员] 审核通过作品")
async def approve_work(
    work_id: int,
    db: AsyncSession = Depends(get_async_db),
    moderator: User = Depends(require_permission("plaza:moderate")),
):
    result = await db.execute(select(Generation).filter(Generation.id == work_id))
    work = result.scalar_one_or_none()
    if not work:
        raise HTTPException(status_code=404, detail="作品不存在")

    work.moderation_status = "approved"
    work.moderation_reason = None
    work.moderation_flags = None
    work.moderated_by = moderator.id
    work.moderated_at = datetime.utcnow()
    await db.commit()

    logger.info("[内容审核] %s 审核通过作品 id=%d", moderator.username, work_id)
    return {"success": True, "id": work_id, "moderation_status": "approved"}


@router.post("/works/{work_id}/reject", summary="[审核员] 屏蔽/驳回作品")
async def reject_work(
    work_id: int,
    reason: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
    moderator: User = Depends(require_permission("plaza:moderate")),
):
    result = await db.execute(select(Generation).filter(Generation.id == work_id))
    work = result.scalar_one_or_none()
    if not work:
        raise HTTPException(status_code=404, detail="作品不存在")

    work.moderation_status = "rejected"
    work.moderation_reason = reason or "管理员审核不通过"
    work.moderated_by = moderator.id
    work.moderated_at = datetime.utcnow()
    await db.commit()

    logger.info("[内容审核] %s 屏蔽作品 id=%d reason=%s", moderator.username, work_id, reason)
    return {"success": True, "id": work_id, "moderation_status": "rejected"}


@router.post("/works/batch-approve", summary="[审核员] 批量审核通过")
async def batch_approve(
    ids: list[int] = Body(..., embed=True),
    db: AsyncSession = Depends(get_async_db),
    moderator: User = Depends(require_permission("plaza:moderate")),
):
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要操作的作品")

    now = datetime.utcnow()
    result = await db.execute(select(Generation).filter(Generation.id.in_(ids)))
    works = result.scalars().all()
    for w in works:
        w.moderation_status = "approved"
        w.moderation_reason = None
        w.moderation_flags = None
        w.moderated_by = moderator.id
        w.moderated_at = now
    await db.commit()

    logger.info("[内容审核] %s 批量审核通过 %d 件作品", moderator.username, len(works))
    return {"success": True, "updated_count": len(works), "failed_ids": [i for i in ids if i not in [w.id for w in works]]}


@router.post("/works/batch-reject", summary="[审核员] 批量屏蔽")
async def batch_reject(
    ids: list[int] = Body(..., embed=True),
    reason: Optional[str] = Body(None),
    db: AsyncSession = Depends(get_async_db),
    moderator: User = Depends(require_permission("plaza:moderate")),
):
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要操作的作品")

    now = datetime.utcnow()
    result = await db.execute(select(Generation).filter(Generation.id.in_(ids)))
    works = result.scalars().all()
    for w in works:
        w.moderation_status = "rejected"
        w.moderation_reason = reason or "管理员审核不通过"
        w.moderated_by = moderator.id
        w.moderated_at = now
    await db.commit()

    logger.info("[内容审核] %s 批量屏蔽 %d 件作品", moderator.username, len(works))
    return {"success": True, "updated_count": len(works), "failed_ids": [i for i in ids if i not in [w.id for w in works]]}


# =====================================================
# 二、敏感词管理
# =====================================================

@router.get("/sensitive-words", summary="[审核员] 敏感词列表")
async def list_sensitive_words(
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    _moderator: User = Depends(require_permission("moderation:config")),
):
    query = select(SensitiveWord)
    if category and category != "all":
        query = query.filter(SensitiveWord.category == category)
    if keyword:
        query = query.filter(SensitiveWord.word.contains(keyword))
    query = query.order_by(SensitiveWord.id.desc())

    total_result = await db.execute(select(SensitiveWord.id).where(
        *([c for c in query.whereclause.get_children()] if query.whereclause is not None else [True])
    ))
    # 简化 count
    all_result = await db.execute(query)
    all_items = all_result.scalars().all()
    total = len(all_items)

    # 分页
    paginated = all_items[(page - 1) * page_size: page * page_size]

    return {
        "items": [w.to_dict() for w in paginated],
        "total": total,
        "page": page,
        "page_size": page_size,
        "categories": SENSITIVE_CATEGORIES,
    }


@router.post("/sensitive-words", summary="[审核员] 新增敏感词")
async def create_sensitive_word(
    data: dict = Body(...),
    db: AsyncSession = Depends(get_async_db),
    moderator: User = Depends(require_permission("moderation:config")),
):
    word = (data.get("word") or "").strip()
    category = data.get("category", "other")
    description = data.get("description")
    if not word:
        raise HTTPException(status_code=400, detail="敏感词不能为空")

    # 检查是否已存在
    existing = await db.execute(select(SensitiveWord).filter(SensitiveWord.word == word))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该敏感词已存在")

    if category not in SENSITIVE_CATEGORIES:
        category = "other"

    sw = SensitiveWord(
        word=word,
        category=category,
        description=description,
        is_active=1,
    )
    db.add(sw)
    await db.commit()
    await db.refresh(sw)

    logger.info("[敏感词管理] %s 新增敏感词: %s", moderator.username, word)
    return sw.to_dict()


@router.put("/sensitive-words/{word_id}", summary="[审核员] 修改敏感词")
async def update_sensitive_word(
    word_id: int,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_async_db),
    moderator: User = Depends(require_permission("moderation:config")),
):
    result = await db.execute(select(SensitiveWord).filter(SensitiveWord.id == word_id))
    sw = result.scalar_one_or_none()
    if not sw:
        raise HTTPException(status_code=404, detail="敏感词不存在")

    word = data.get("word")
    category = data.get("category")
    description = data.get("description")
    is_active = data.get("is_active")

    if word is not None:
        word = word.strip()
        if not word:
            raise HTTPException(status_code=400, detail="敏感词不能为空")
        # 检查重名
        existing = await db.execute(
            select(SensitiveWord).filter(SensitiveWord.word == word, SensitiveWord.id != word_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="该敏感词已存在")
        sw.word = word

    if category is not None:
        if category not in SENSITIVE_CATEGORIES:
            raise HTTPException(status_code=400, detail="无效的分类")
        sw.category = category

    if description is not None:
        sw.description = description

    if is_active is not None:
        sw.is_active = 1 if is_active else 0

    sw.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(sw)

    logger.info("[敏感词管理] %s 修改敏感词 id=%d", moderator.username, word_id)
    return sw.to_dict()


@router.delete("/sensitive-words/{word_id}", summary="[审核员] 删除敏感词")
async def delete_sensitive_word(
    word_id: int,
    db: AsyncSession = Depends(get_async_db),
    moderator: User = Depends(require_permission("moderation:config")),
):
    result = await db.execute(select(SensitiveWord).filter(SensitiveWord.id == word_id))
    sw = result.scalar_one_or_none()
    if not sw:
        raise HTTPException(status_code=404, detail="敏感词不存在")

    await db.delete(sw)
    await db.commit()

    logger.info("[敏感词管理] %s 删除敏感词: %s", moderator.username, sw.word)
    return {"success": True, "message": "已删除"}


@router.post("/sensitive-words/batch-import", summary="[审核员] 批量导入敏感词")
async def batch_import_sensitive_words(
    data: dict = Body(...),
    db: AsyncSession = Depends(get_async_db),
    moderator: User = Depends(require_permission("moderation:config")),
):
    """
    批量导入敏感词。
    - words: 敏感词文本，支持换行、逗号、分号分隔
    - category: 默认分类
    - skip_existing: 是否跳过已存在的词（默认 true）
    """
    import re
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    raw_text = (data.get("words") or "").strip()
    category = data.get("category", "other")
    skip_existing = data.get("skip_existing", True)

    if not raw_text:
        raise HTTPException(status_code=400, detail="请输入要导入的敏感词")

    if category not in SENSITIVE_CATEGORIES:
        raise HTTPException(status_code=400, detail="无效的分类")

    # 解析：支持换行、逗号、分号、顿号、空格分隔
    raw_words = re.split(r"[\n,，;；、\s]+", raw_text)
    # 去重、去空、截断长度
    word_set = set()
    for w in raw_words:
        w = w.strip()
        if w and len(w) <= 100:
            word_set.add(w)

    if not word_set:
        raise HTTPException(status_code=400, detail="没有有效的敏感词")

    word_list = list(word_set)

    # 查询已存在的词
    result = await db.execute(
        select(SensitiveWord.word).filter(SensitiveWord.word.in_(word_list))
    )
    existing = {row[0] for row in result.all()}

    new_words = [w for w in word_list if w not in existing]
    skipped_count = len(existing)

    inserted_count = 0
    if new_words:
        for w in new_words:
            sw = SensitiveWord(word=w, category=category, is_active=1)
            db.add(sw)
        await db.commit()
        inserted_count = len(new_words)

    logger.info(
        "[敏感词管理] %s 批量导入敏感词：新增 %d，跳过 %d",
        moderator.username, inserted_count, skipped_count,
    )

    return {
        "success": True,
        "inserted_count": inserted_count,
        "skipped_count": skipped_count,
        "total_count": len(word_list),
    }
