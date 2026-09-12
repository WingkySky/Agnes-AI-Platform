"""add is_approved/is_rejected/submit_reason/reject_reason to pipeline_templates

Revision ID: 20260628_template_approval
Revises: 20260627_add_provider_type
Create Date: 2026-06-28

说明:
    为 pipeline_templates 表新增审核相关字段，支持模板市场的审核流程：
    - is_approved: 是否通过审核（公开模板需审核通过才可见）
    - is_rejected: 是否已被驳回（驳回后不可再次提交公开）
    - submit_reason: 提交公开时的说明文字
    - reject_reason: 驳回理由

    内置模板（is_builtin=1）自动标记为 is_approved=1，无需审核。

注意：项目当前未启用 alembic（init_db.py 用 Base.metadata.create_all 建表，
加上 _auto_migrate_missing_columns 自动补列），实际升级通过自动迁移 + 数据
初始化兜底。本文件作为后续启用 alembic 时的迁移记录保留。
"""
from alembic import op
import sqlalchemy as sa


revision = "20260628_template_approval"
down_revision = "20260627_add_provider_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 新增审核字段
    op.add_column(
        "pipeline_templates",
        sa.Column("is_approved", sa.Boolean, nullable=False, server_default=sa.false(), index=True),
    )
    op.add_column(
        "pipeline_templates",
        sa.Column("is_rejected", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "pipeline_templates",
        sa.Column("submit_reason", sa.String(500), nullable=True),
    )
    op.add_column(
        "pipeline_templates",
        sa.Column("reject_reason", sa.String(500), nullable=True),
    )

    # 内置模板自动标记为已审核通过
    op.execute(
        "UPDATE pipeline_templates SET is_approved = 1 WHERE is_builtin = 1"
    )


def downgrade() -> None:
    op.drop_column("pipeline_templates", "reject_reason")
    op.drop_column("pipeline_templates", "submit_reason")
    op.drop_column("pipeline_templates", "is_rejected")
    op.drop_column("pipeline_templates", "is_approved")
