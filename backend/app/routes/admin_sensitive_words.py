# =====================================================
# 敏感词管理路由（审核员/管理员）
#
#   GET    /api/admin/sensitive-words              敏感词列表
#   POST   /api/admin/sensitive-words              新增敏感词
#   PUT    /api/admin/sensitive-words/{id}         修改敏感词
#   DELETE /api/admin/sensitive-words/{id}         删除敏感词
#   POST   /api/admin/sensitive-words/batch-import 批量导入敏感词
#
# 说明：从原 admin_moderation.py 拆分而来，仅保留敏感词管理；
#       作品/预设/模板审核统一由 admin_review.py 提供。
# =====================================================

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_async_db
from app.core.security import require_permission
from app.models.user import User
from app.models.sensitive_word import SensitiveWord, SENSITIVE_CATEGORIES

logger = logging.getLogger("agnes_platform")
router = APIRouter(prefix="/admin/sensitive-words", tags=["管理员-敏感词管理"])


@router.get("", summary="[审核员] 敏感词列表")
async def list_sensitive_words(
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    _moderator: User = Depends(require_permission("moderation:config")),
):
    """获取敏感词列表，支持按分类、关键词筛选和分页"""
    query = select(SensitiveWord)
    if category and category != "all":
        query = query.filter(SensitiveWord.category == category)
    if keyword:
        query = query.filter(SensitiveWord.word.contains(keyword))
    query = query.order_by(SensitiveWord.id.desc())

    # 简化 count：先全量取出再切片
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


@router.post("", summary="[审核员] 新增敏感词")
async def create_sensitive_word(
    data: dict = Body(...),
    db: AsyncSession = Depends(get_async_db),
    moderator: User = Depends(require_permission("moderation:config")),
):
    """新增单个敏感词"""
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


@router.put("/{word_id}", summary="[审核员] 修改敏感词")
async def update_sensitive_word(
    word_id: int,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_async_db),
    moderator: User = Depends(require_permission("moderation:config")),
):
    """修改敏感词字段（word/category/description/is_active）"""
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


@router.delete("/{word_id}", summary="[审核员] 删除敏感词")
async def delete_sensitive_word(
    word_id: int,
    db: AsyncSession = Depends(get_async_db),
    moderator: User = Depends(require_permission("moderation:config")),
):
    """删除一个敏感词"""
    result = await db.execute(select(SensitiveWord).filter(SensitiveWord.id == word_id))
    sw = result.scalar_one_or_none()
    if not sw:
        raise HTTPException(status_code=404, detail="敏感词不存在")

    await db.delete(sw)
    await db.commit()

    logger.info("[敏感词管理] %s 删除敏感词: %s", moderator.username, sw.word)
    return {"success": True, "message": "已删除"}


@router.post("/batch-import", summary="[审核员] 批量导入敏感词")
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
