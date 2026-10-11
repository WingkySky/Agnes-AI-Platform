# =====================================================
# 个人访问令牌（PAT）模型 —— 外部 Agent/CLI 经 MCP Server 接入的凭据
#
# - token 只存 sha256 哈希（token_hash 唯一），明文仅创建响应返回一次
# - permission: readonly | full（写类工具在 mcp_gateway 分派层统一拦截）
# - revoked_at 非空 = 已吊销（软删保留记录），每次请求实时查表即时生效
# =====================================================

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.core.database import Base


class PatToken(Base):
    """个人访问令牌表（用户级；MCP Server 接入凭据）"""

    __tablename__ = "pat_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    name = Column(String(100), nullable=False)                       # 用户起名
    token_hash = Column(String(64), unique=True, nullable=False)     # sha256 hex（明文不落库）
    permission = Column(String(16), nullable=False, default="readonly")  # readonly | full
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_safe_dict(self) -> dict:
        """脱敏序列化：永不回传 token 材料本身"""
        return {
            "id": self.id,
            "name": self.name,
            "permission": self.permission,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
