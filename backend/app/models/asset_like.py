# =====================================================
# AssetLike 模型 — 广场「创作」Tab 资产点赞关系表
# 与 PlazaLike（generations 作品点赞）平行，用于 assets 的点赞防重复与「我点赞的」反查
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, UniqueConstraint, ForeignKey

from app.core.database import Base


class AssetLike(Base):
    """
    创作资产点赞关系

    字段说明:
    - id: 主键
    - user_id: 点赞的用户 ID
    - asset_id: 被点赞的资产 ID
    - created_at: 点赞时间
    """

    __tablename__ = "asset_likes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 唯一约束：同一用户对同一资产只能点赞一次
    __table_args__ = (
        UniqueConstraint("user_id", "asset_id", name="uk_user_asset"),
    )
