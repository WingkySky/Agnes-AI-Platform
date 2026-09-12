# =====================================================
# 敏感词配置模型
# - 用于自动预审：生成前检查 Prompt 中是否包含敏感关键词
# - 命中后自动标记为待审核（moderation_status = pending）
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime

from app.core.database import Base


# 默认敏感词列表（首次启动时初始化）
DEFAULT_SENSITIVE_WORDS = [
    # 违法违规类
    "毒品", "赌博", "色情", "暴力", "恐怖", "血腥",
    "枪支", "弹药", "炸药", "毒品配方",
    # 政治敏感类
    "反动", "颠覆", "分裂", "邪教",
    # 诈骗类
    "诈骗", "洗钱", "传销",
]

# 敏感词分类
SENSITIVE_CATEGORIES = {
    "illegal": "违法违规",
    "political": "政治敏感",
    "fraud": "诈骗虚假",
    "violence": "暴力血腥",
    "porn": "色情低俗",
    "other": "其他",
}


class SensitiveWord(Base):
    """敏感词表"""
    __tablename__ = "sensitive_words"

    id = Column(Integer, primary_key=True, index=True)
    word = Column(String(128), unique=True, index=True, nullable=False)    # 敏感关键词
    category = Column(String(32), default="other", nullable=False, index=True)  # 分类
    description = Column(String(255), nullable=True)                           # 描述/备注
    is_active = Column(Integer, default=1, nullable=False, index=True)       # 是否启用（1=启用，0=禁用）
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "word": self.word,
            "category": self.category,
            "description": self.description,
            "is_active": bool(self.is_active),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
