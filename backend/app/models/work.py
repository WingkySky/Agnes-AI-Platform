# =====================================================
# 作品（轻容器）模型
#
# - works: 一部剧一条作品，聚合多张画布（每集一张）/ 剪辑工程 / 实体库
#   （替代旧 projects 重结构的轻量顶层容器，实体归属与发布投稿以作品为单位）
# =====================================================

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.core.database import Base


class Work(Base):
    """作品：创作顶层容器，下挂集画布（canvas_workspaces.work_id）、剪辑工程与实体库"""

    __tablename__ = "works"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    cover_url = Column(String(1024), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "cover_url": self.cover_url,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
