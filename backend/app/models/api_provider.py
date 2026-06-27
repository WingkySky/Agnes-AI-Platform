# =====================================================
# ApiProvider 模型 — API 提供商配置
# 支持多个 Provider（Agnes 官方 / 自建代理 / 其他兼容 OpenAI 的服务）
# 每个 Provider 独立的 Base URL + API Key + 轮询 URL
# API Key 使用 Fernet 加密存储
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean

from app.core.database import Base


class ApiProvider(Base):
    """
    API 提供商配置

    字段说明:
    - id: 主键
    - name: 显示名称（如 "Agnes 官方" / "自建代理"）
    - provider_type: agn-sdk 的 adapter 标识（如 agnes / volcengine_cv / kling 等），
                    决定 provider_registry 用哪个 agn-sdk Adapter 路由请求。
                    默认 "agnes"，兼容历史 Provider 数据。
    - base_url: API Base URL（如 https://apihub.agnes-ai.com/v1）
    - api_key_encrypted: 加密后的 API Key（Fernet）
    - poll_url: 异步任务轮询 URL（可选，Agnes 用 /agnesapi）
    - is_active: 是否启用
    - is_default: 是否默认 Provider（业务调用未指定时使用此）
    - sort_order: 排序权重（越小越靠前）
    - created_at / updated_at: 时间戳
    """

    __tablename__ = "api_providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="显示名称")
    provider_type = Column(
        String(50),
        nullable=False,
        default="agnes",
        server_default="agnes",
        comment="agn-sdk adapter 标识：agnes / volcengine_cv / kling / runway / pika 等",
    )
    base_url = Column(String(500), nullable=False, comment="API Base URL")
    api_key_encrypted = Column(Text, nullable=True, comment="加密后的 API Key")
    poll_url = Column(String(500), nullable=True, comment="异步任务轮询 URL")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    is_default = Column(Boolean, default=False, nullable=False, comment="是否默认 Provider")
    sort_order = Column(Integer, default=0, nullable=False, comment="排序权重")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self, include_key: bool = False, decrypted_key: str = "") -> dict:
        """
        转换为字典。
        - include_key=False: 默认不返回明文 key，只返回掩码（前端展示用）
        - include_key=True: 返回明文 key（仅后端内部使用）
        """
        from app.core.security import mask_api_key
        return {
            "id": self.id,
            "name": self.name,
            "provider_type": self.provider_type or "agnes",
            "base_url": self.base_url,
            "api_key": decrypted_key if include_key else mask_api_key(decrypted_key),
            "poll_url": self.poll_url or "",
            "is_active": self.is_active,
            "is_default": self.is_default,
            "sort_order": self.sort_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
