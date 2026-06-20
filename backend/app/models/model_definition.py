# =====================================================
# ModelDefinition 模型 — 模型定义
# 从各 Provider 的 /models 接口拉取后持久化到数据库
# 支持用户手动新增自定义模型（is_custom=True，刷新时不覆盖）
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class ModelDefinition(Base):
    """
    模型定义

    字段说明:
    - id: 主键
    - provider_id: 关联的 ApiProvider ID
    - model_id: 模型标识（如 agnes-image-2.1-flash）
    - display_name: 显示名称
    - type: 模型类型（image / video / chat）
    - provider_name: 供应商名称（如 Agnes / OpenAI）
    - capabilities: 能力标签数组（JSON）
    - is_active: 是否启用
    - is_custom: 是否用户手动新增（true 时刷新模型列表不被覆盖）
    - sort_order: 排序权重
    - created_at / updated_at: 时间戳
    """

    __tablename__ = "model_definitions"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("api_providers.id", ondelete="CASCADE"), nullable=False, index=True)
    model_id = Column(String(100), nullable=False, comment="模型标识")
    display_name = Column(String(200), nullable=True, comment="显示名称")
    type = Column(String(20), nullable=False, default="chat", comment="模型类型: image/video/chat")
    provider_name = Column(String(100), nullable=True, comment="供应商名称")
    capabilities = Column(JSON, nullable=True, comment="能力标签数组")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    is_custom = Column(Boolean, default=False, nullable=False, comment="是否用户自定义")
    sort_order = Column(Integer, default=0, nullable=False, comment="排序权重")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        """转换为字典（对齐前端 ModelInfo 结构）"""
        return {
            "id": self.id,
            "provider_id": self.provider_id,
            "id_field": self.model_id,  # 兼容旧 ModelInfo.id
            "model_id": self.model_id,
            "name": self.display_name or self.model_id,
            "type": self.type,
            "provider": self.provider_name or "Unknown",
            "capabilities": self.capabilities or [],
            "is_active": self.is_active,
            "is_custom": self.is_custom,
            "sort_order": self.sort_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
