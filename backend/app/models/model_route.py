# =====================================================
# ModelRoute 模型 — 模型备用路由（多渠道路由 failover）
# 锚点模型（用户所选 model_definitions.model_id）的显式备用渠道列表：
#   - 目标为裸的 (provider_id, model_id) 对：与锚点相同 = 同款渠道备用，
#     不同 = 等价模型备用；不要求目标存在 model_definitions 行（允许手填）。
#   - 锚点自身渠道不入表，恒为路由链首（见 services/model_routing.py）。
#   - 模型同步（sync_provider_models）不触碰本表；删除锚点模型定义时
#     由 provider_registry.delete_model 级联清理，删除 Provider 走 FK CASCADE。
# 存量库升级：建表由 lifespan 的 Base.metadata.create_all 自动完成，无需手工 ALTER。
# =====================================================

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from app.core.database import Base


class ModelRoute(Base):
    """模型备用路由（anchor_model_id → (provider_id, model_id)，priority 越小越优先）"""

    __tablename__ = "model_routes"
    __table_args__ = (
        UniqueConstraint("anchor_model_id", "provider_id", "model_id", name="uq_model_routes_anchor_target"),
    )

    id = Column(Integer, primary_key=True, index=True)
    anchor_model_id = Column(String(100), nullable=False, index=True, comment="锚点模型 ID（用户所选模型）")
    provider_id = Column(
        Integer, ForeignKey("api_providers.id", ondelete="CASCADE"), nullable=False, index=True,
        comment="目标渠道（备用 Provider）",
    )
    model_id = Column(String(100), nullable=False, comment="目标模型 ID（同款渠道或等价模型）")
    priority = Column(Integer, default=0, nullable=False, comment="优先级：越小越优先")
    is_enabled = Column(Boolean, default=True, nullable=False, comment="是否启用该备用路由")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "anchor_model_id": self.anchor_model_id,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "priority": self.priority,
            "is_enabled": self.is_enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
