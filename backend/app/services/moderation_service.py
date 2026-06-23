# =====================================================
# 内容审核服务
# - 敏感词检测（Prompt 文本审核）
# - 自动预审：命中敏感词的作品自动标记为待审核
# =====================================================

import logging
from typing import List, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.sensitive_word import SensitiveWord, DEFAULT_SENSITIVE_WORDS

logger = logging.getLogger("agnes_platform")


# ---------- 初始化默认敏感词 ----------
async def ensure_default_sensitive_words(db: AsyncSession) -> None:
    """确保默认敏感词存在，启动时调用"""
    for word in DEFAULT_SENSITIVE_WORDS:
        result = await db.execute(select(SensitiveWord).filter(SensitiveWord.word == word))
        if not result.scalar_one_or_none():
            db.add(SensitiveWord(
                word=word,
                category="other",
                description="系统默认敏感词",
                is_active=1,
            ))
    await db.commit()


# ---------- 敏感词检测 ----------
async def check_sensitive_text(
    db: AsyncSession,
    text: str,
) -> Tuple[bool, List[str]]:
    """
    检查文本中是否包含敏感词。
    返回：(是否命中, 命中的敏感词列表)
    """
    if not text:
        return False, []

    # 读取所有启用的敏感词
    result = await db.execute(
        select(SensitiveWord).filter(SensitiveWord.is_active == 1)
    )
    words = result.scalars().all()
    if not words:
        return False, []

    text_lower = text.lower()
    hit_words = []
    for w in words:
        if w.word.lower() in text_lower:
            hit_words.append(w.word)

    return (len(hit_words) > 0), hit_words


# ---------- 为 Generation 记录应用审核结果 ----------
def apply_moderation_result(record, hit_words: List[str], reason: Optional[str] = None):
    """
    将敏感词检测结果应用到 Generation 记录。
    命中后设置 moderation_status = 'pending'，并记录命中的关键词。
    """
    if hit_words:
        record.moderation_status = "pending"
        record.moderation_flags = hit_words
        record.moderation_reason = reason or f"命中敏感词: {', '.join(hit_words[:5])}"
    else:
        record.moderation_status = "approved"
        record.moderation_flags = None
        record.moderation_reason = None
