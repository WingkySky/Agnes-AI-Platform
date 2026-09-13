# =====================================================
# MCP 服务器配置模型（管理员全局配置，Agent 经 BFF 调用）
#
# - transport: stdio（后端拉起子进程）| http（streamable HTTP 远程）
# - env_json / headers_json 的值仅服务端持有，接口响应永不回传（脱敏在 service 层做）
# =====================================================

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.core.database import Base


class McpServer(Base):
    """MCP 服务器配置表（stdio / streamable HTTP 双传输）"""

    __tablename__ = "mcp_servers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)          # 显示名（唯一）
    transport = Column(String(16), nullable=False, default="http")   # stdio | http
    # stdio 传输：可执行命令 + 参数数组 + 环境变量对象（JSON 字符串存储）
    command = Column(String(500), nullable=True)
    args_json = Column(Text, nullable=True)      # JSON: ["--flag", "value"]
    env_json = Column(Text, nullable=True)       # JSON: {"KEY": "value"}（值敏感，不回传）
    # http 传输：streamable HTTP 端点 + 请求头（JSON 字符串存储）
    url = Column(String(500), nullable=True)
    headers_json = Column(Text, nullable=True)   # JSON: {"Authorization": "..."}（值敏感，不回传）
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_safe_dict(self) -> dict:
        """脱敏序列化：env/headers 只回传键名与是否已配置，值永不出后端"""
        import json

        def keys_of(raw: str | None) -> dict:
            if not raw:
                return {}
            try:
                data = json.loads(raw)
            except (ValueError, TypeError):
                return {}
            return {k: True for k in data} if isinstance(data, dict) else {}

        return {
            "id": self.id,
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "args": self.parse_json(self.args_json, []),
            "env_keys": keys_of(self.env_json),
            "url": self.url,
            "header_keys": keys_of(self.headers_json),
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @staticmethod
    def parse_json(raw: str | None, fallback):
        import json

        if not raw:
            return fallback
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return fallback
        return data if data is not None else fallback
