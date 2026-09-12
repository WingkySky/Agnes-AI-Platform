# =====================================================
# PlazaLike 模型 — 广场点赞关系表
# 记录用户对广场作品的点赞关系，支持防重复点赞和「我点赞的作品」反查
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, UniqueConstraint, ForeignKey

from app.core.database import Base


class PlazaLike(Base):
    """
    广场点赞关系

    字段说明:
    - id: 主键
    - user_id: 点赞的用户 ID
    - generation_id: 被点赞的作品 ID
    - created_at: 点赞时间
    """

    __tablename__ = "plaza_likes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    generation_id = Column(Integer, ForeignKey("generations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 唯一约束：同一用户对同一作品只能点赞一次
    __table_args__ = (
        UniqueConstraint("user_id", "generation_id", name="uk_user_generation"),
    )
