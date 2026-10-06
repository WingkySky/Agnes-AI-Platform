# =====================================================
# 作品实体库模型
#
# - work_entities: 作品级实体（角色/场景/物品），跨集画布复用的事实源，
#   画布实体卡（image 节点 content.entityId）引用
# - work_entity_versions: 实体设定图版本（只增不删历史）；版本内多张表现图
#   （images JSON: [{asset_id, role}]，表现图挂统一资产库）；
#   is_active 采用位（每实体至多一个，service 层保证）
# =====================================================

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base

ENTITY_KINDS = ("character", "scene", "prop")
IMAGE_ROLES = ("design", "turnaround", "angle")


class WorkEntity(Base):
    """作品实体：归属作品，name/description 喂生成 prompt"""

    __tablename__ = "work_entities"

    id = Column(Integer, primary_key=True, index=True)
    work_id = Column(Integer, ForeignKey("works.id"), nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    name = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 无 relationship 时 unit of work 不识别表级 FK，删实体会先删父行撞外键
    versions = relationship(
        "WorkEntityVersion", cascade="all, delete-orphan",
        order_by="WorkEntityVersion.created_at", lazy="selectin",
    )


class WorkEntityVersion(Base):
    """实体版本：只增不删历史；angle/turnaround 角色表现图追加进当前采用版本"""

    __tablename__ = "work_entity_versions"

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(Integer, ForeignKey("work_entities.id"), nullable=False, index=True)
    images = Column(JSON, nullable=False, default=list)
    source_generation_id = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
