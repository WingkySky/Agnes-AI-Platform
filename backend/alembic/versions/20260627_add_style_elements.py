"""add style_elements table

Revision ID: 20260627_add_style_elements
Revises: None
Create Date: 2026-06-27

说明:
    本迁移创建 style_elements 表（分层风格元素模型 StyleElement）。
    注意：当前项目尚未启用 alembic（无 alembic.ini / alembic 目录），
    实际建表通过 backend/init_db.py 的 Base.metadata.create_all 完成。
    本文件作为后续启用 alembic 时的迁移记录保留，down_revision 暂为 None。
"""
from alembic import op
import sqlalchemy as sa


revision = "20260627_add_style_elements"
down_revision = None  # 项目当前未启用 alembic，无前置 revision
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "style_elements",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("key", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("layer", sa.String(50), nullable=False, index=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("negative_content", sa.Text(), nullable=True),
        sa.Column("preview_image", sa.String(500), nullable=True),
        sa.Column("weight_default", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_style_elements_layer_sort",
        "style_elements",
        ["layer", "sort_order"],
    )


def downgrade() -> None:
    op.drop_index("ix_style_elements_layer_sort", table_name="style_elements")
    op.drop_table("style_elements")
