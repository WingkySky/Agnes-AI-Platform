# =====================================================
# MCP 市场模型（官方内置目录 + 管理员自建源）
#
# - 市场是 MCP 服务器的"发现/一键安装"层：安装 = 从市场项生成 mcp_servers 记录
# - payload 为市场项完整定义（name/description/预填配置/密钥声明/工具预览），JSON 存储
# =====================================================

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.core.database import Base


class McpMarketSource(Base):
    """市场源（管理员自建：URL 指向 manifest JSON；官方目录不落此表）"""

    __tablename__ = "mcp_market_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    last_fetched_at = Column(DateTime, nullable=True)
    item_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "enabled": self.enabled,
            "last_fetched_at": self.last_fetched_at.isoformat() if self.last_fetched_at else None,
            "item_count": self.item_count,
        }


class McpMarketItem(Base):
    """市场项（official=官方内置 seed；remote=自建源拉取）"""

    __tablename__ = "mcp_market_items"

    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String(16), nullable=False, index=True)  # official | remote
    source_id = Column(Integer, nullable=True, index=True)        # remote 源 id；official 为空
    slug = Column(String(100), unique=True, nullable=False, index=True)
    category = Column(String(50), nullable=False, default="官方精选")
    payload = Column(Text, nullable=False)  # JSON：完整市场项定义
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
