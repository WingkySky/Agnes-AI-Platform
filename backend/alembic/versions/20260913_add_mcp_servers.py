"""add mcp_servers table

Revision ID: 20260913_add_mcp_servers
Revises: 20260628_template_approval
Create Date: 2026-09-13

说明:
    本迁移创建 mcp_servers 表（MCP 服务器配置，stdio / streamable HTTP 双传输）。
    注意：当前项目尚未实际启用 alembic（建表走 init_db.py 的 create_all），
    本文件作为迁移记录保留。
"""
from alembic import op
import sqlalchemy as sa


revision = "20260913_add_mcp_servers"
down_revision = "20260628_template_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("transport", sa.String(16), nullable=False, server_default="http"),
        sa.Column("command", sa.String(500), nullable=True),
        sa.Column("args_json", sa.Text(), nullable=True),
        sa.Column("env_json", sa.Text(), nullable=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("headers_json", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_mcp_servers_name", "mcp_servers", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_mcp_servers_name", table_name="mcp_servers")
    op.drop_table("mcp_servers")
