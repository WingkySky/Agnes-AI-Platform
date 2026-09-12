"""add pipeline_template_revisions table + has_pending_revision column

Revision ID: 20260628_template_revision
Revises: 20260628_template_approval
Create Date: 2026-06-28

说明:
    1. 新建 pipeline_template_revisions 表，存放公开模板的修订草稿快照
       （模板字段 + 审核字段 + 编辑者/时间）。
    2. 给 pipeline_templates 增加 has_pending_revision 列（默认 False），
       标记是否存在未审核的修订草稿。

注意：项目当前未启用 alembic（init_db.py 用 Base.metadata.create_all 建表，
加上 _auto_migrate_missing_columns 自动补列），实际升级通过自动迁移兜底。
本文件作为后续启用 alembic 时的迁移记录保留。
"""
from alembic import op
import sqlalchemy as sa


revision = "20260628_template_revision"
down_revision = "20260628_template_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 给 pipeline_templates 增加 has_pending_revision 列
    op.add_column(
        "pipeline_templates",
        sa.Column(
            "has_pending_revision",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
            index=True,
        ),
    )

    # 2) 新建 pipeline_template_revisions 表
    op.create_table(
        "pipeline_template_revisions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "template_id",
            sa.Integer,
            sa.ForeignKey("pipeline_templates.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("thumbnail_url", sa.String(500), nullable=True),
        sa.Column("inputs_config", sa.JSON, nullable=False),
        sa.Column("steps_config", sa.JSON, nullable=False),
        sa.Column("output_mapping", sa.JSON, nullable=True),
        sa.Column(
            "script_template_id",
            sa.Integer,
            sa.ForeignKey("script_templates.id"),
            nullable=True,
        ),
        sa.Column("estimated_credits", sa.Integer, nullable=False, server_default="100"),
        sa.Column("estimated_time_minutes", sa.Integer, nullable=False, server_default="10"),
        sa.Column("tags", sa.JSON, nullable=False),
        sa.Column("is_approved", sa.Boolean, nullable=False, server_default=sa.false(), index=True),
        sa.Column("is_rejected", sa.Boolean, nullable=False, server_default=sa.false(), index=True),
        sa.Column("submit_reason", sa.String(500), nullable=True),
        sa.Column("reject_reason", sa.String(500), nullable=True),
        sa.Column(
            "edited_by",
            sa.Integer,
            sa.ForeignKey("users.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
    )

    # 联合索引：便于查询某模板的 pending revision
    op.create_index(
        "idx_ptrev_template_pending",
        "pipeline_template_revisions",
        ["template_id", "is_approved", "is_rejected"],
    )


def downgrade() -> None:
    op.drop_index("idx_ptrev_template_pending", table_name="pipeline_template_revisions")
    op.drop_table("pipeline_template_revisions")
    op.drop_column("pipeline_templates", "has_pending_revision")
