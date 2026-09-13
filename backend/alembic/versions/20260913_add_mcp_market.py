"""add mcp_market tables + mcp_servers.market_slug

Revision ID: 20260913_add_mcp_market
Revises: 20260913_add_mcp_servers
Create Date: 2026-09-13

说明:
    MCP 市场 v1：mcp_market_sources（管理员自建源）/ mcp_market_items（官方+远程市场项）
    / mcp_servers.market_slug（安装溯源）。建表实际走 init_db.py create_all。
"""
from alembic import op
import sqlalchemy as sa


revision = "20260913_add_mcp_market"
down_revision = "20260913_add_mcp_servers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_market_sources",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("last_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "mcp_market_items",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("source_type", sa.String(16), nullable=False, index=True),
        sa.Column("source_id", sa.Integer(), nullable=True, index=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("category", sa.String(50), nullable=False, server_default="官方精选"),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_mcp_market_items_slug", "mcp_market_items", ["slug"], unique=True)
    op.add_column("mcp_servers", sa.Column("market_slug", sa.String(100), nullable=True))
    op.create_index("ix_mcp_servers_market_slug", "mcp_servers", ["market_slug"])


def downgrade() -> None:
    op.drop_index("ix_mcp_servers_market_slug", table_name="mcp_servers")
    op.drop_column("mcp_servers", "market_slug")
    op.drop_index("ix_mcp_market_items_slug", table_name="mcp_market_items")
    op.drop_table("mcp_market_items")
    op.drop_table("mcp_market_sources")
