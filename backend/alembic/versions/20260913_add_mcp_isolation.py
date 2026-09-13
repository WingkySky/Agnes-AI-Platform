"""add mcp_servers.isolation

Revision ID: 20260913_add_mcp_isolation
Revises: 20260913_add_mcp_market
Create Date: 2026-09-13

说明:
    MCP 服务器实例隔离级别：shared（默认，全局一个实例）/ per_user（按用户各起实例，
    配置中的 {user_id} 模板在网关侧替换）。有状态服务器（memory/filesystem）必须 per_user。
"""
from alembic import op
import sqlalchemy as sa


revision = "20260913_add_mcp_isolation"
down_revision = "20260913_add_mcp_market"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mcp_servers", sa.Column("isolation", sa.String(16), nullable=False, server_default="shared"))


def downgrade() -> None:
    op.drop_column("mcp_servers", "isolation")
