"""add provider_type column to api_providers

Revision ID: 20260627_add_provider_type
Revises: 20260627_add_style_elements
Create Date: 2026-06-27

说明:
    本迁移在 api_providers 表新增 provider_type 字段，用于区分不同 agn-sdk Adapter。
    - 默认 "agnes"，兼容历史 Provider 数据（所有旧 Provider 自动标记为 agnes）
    - 用户可在配置中心新增火山引擎 / Kling 等其他 adapter 的 Provider
    - provider_registry 据此字段选择对应的 agn-sdk Adapter 路由请求

注意：项目当前未启用 alembic（init_db.py 用 Base.metadata.create_all 建表，
不会修改已有表），实际升级通过 init_db.py 的 _auto_alter_provider_type() 兜底。
本文件作为后续启用 alembic 时的迁移记录保留。
"""
from alembic import op
import sqlalchemy as sa


revision = "20260627_add_provider_type"
down_revision = "20260627_add_style_elements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 新增 provider_type 字段，默认 "agnes"（兼容历史数据）
    op.add_column(
        "api_providers",
        sa.Column(
            "provider_type",
            sa.String(50),
            nullable=False,
            server_default="agnes",
            comment="agn-sdk adapter 标识：agnes / volcengine_cv / kling / runway / pika 等",
        ),
    )


def downgrade() -> None:
    op.drop_column("api_providers", "provider_type")
