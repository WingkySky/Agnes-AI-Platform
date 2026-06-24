# =====================================================
# 系统配置模型
# - 键值对方式存储全局系统配置（SMTP、站点设置等）
# - 配置值统一存为字符串，使用时根据 key 解析对应类型
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Index

from app.core.database import Base


# 默认系统配置（首次启动时初始化）
# 分类：smtp / site / security
DEFAULT_SYSTEM_CONFIGS = {
    # ---------- SMTP 邮件配置 ----------
    "smtp_host": {"value": "", "category": "smtp", "description": "SMTP 服务器地址"},
    "smtp_port": {"value": "587", "category": "smtp", "description": "SMTP 服务器端口"},
    "smtp_user": {"value": "", "category": "smtp", "description": "SMTP 用户名"},
    "smtp_password": {"value": "", "category": "smtp", "description": "SMTP 密码（加密存储）"},
    "smtp_from_email": {"value": "", "category": "smtp", "description": "发件人邮箱地址"},
    "smtp_from_name": {"value": "Agnes AI Platform", "category": "smtp", "description": "发件人显示名称"},
    "smtp_use_tls": {"value": "true", "category": "smtp", "description": "是否使用 TLS 加密"},
}


class SystemConfig(Base):
    """系统配置表（键值对）"""
    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String(128), unique=True, index=True, nullable=False)    # 配置键
    config_value = Column(Text, default="", nullable=False)                      # 配置值（字符串存储）
    category = Column(String(32), default="site", nullable=False, index=True)    # 分类：smtp/site/security
    description = Column(String(255), nullable=True)                             # 配置说明
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_config_key", "config_key", unique=True),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "config_key": self.config_key,
            "config_value": self.config_value,
            "category": self.category,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
