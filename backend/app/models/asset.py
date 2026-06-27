# =====================================================
# Asset 模型 — 资产库数据模型
# 包含角色、道具、场景、品牌等可复用创意资产
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class Asset(Base):
    """
    创意资产

    可复用的创意素材单元，包括角色、道具、场景、品牌等。
    资产可以被多个流水线复用，支持版本管理和分享。

    字段说明:
    - id: 主键
    - type: 类型（character 角色 / prop 道具 / scene 场景 / brand 品牌）
    - name: 名称
    - description: 详细描述
    - visual_description: 外观描述文本（用于生成提示词）
    - reference_images: 参考图 URL 数组（JSON）
    - style_id: 关联的风格预设 ID（可选）
    - user_id: 创建者用户 ID
    - is_public: 是否公开到广场
    - moderation_status: 审核状态
    - moderation_reason: 审核原因
    - tags: 标签数组（JSON）
    - version: 版本号（从 1 开始）
    - parent_id: 父版本 ID（用于版本链）
    - likes_count: 点赞数
    - views_count: 浏览次数
    - use_count: 被使用次数
    """

    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(30), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    visual_description = Column(Text, nullable=False)
    reference_images = Column(JSON, default=list, nullable=False)
    style_id = Column(Integer, ForeignKey("style_presets.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    is_public = Column(Boolean, default=False, nullable=False, index=True)
    moderation_status = Column(String(20), default="approved", nullable=False, index=True)
    moderation_reason = Column(String(255), nullable=True)
    tags = Column(JSON, default=list, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    parent_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    likes_count = Column(Integer, default=0, nullable=False)
    views_count = Column(Integer, default=0, nullable=False)
    use_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    style = relationship("StylePreset", back_populates="assets")
    parent = relationship("Asset", remote_side=[id])
