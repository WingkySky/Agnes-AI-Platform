# =====================================================
# PipelineTemplateRevision 模型 — 公开模板修订草稿
#
# 用途：公开已审核模板被作者/admin 编辑时，先写入本表生成 pending revision，
#       原 PipelineTemplate 继续在市场可见可用；admin 审核通过后 revision
#       字段覆盖原模板，审核拒绝则仅标记 revision。
#
# 关键字段说明:
#   - template_id: 关联的原模板（FK pipeline_templates.id，CASCADE 删除）
#   - name/description/category/thumbnail_url/inputs_config/steps_config/
#     output_mapping/script_template_id/estimated_credits/estimated_time_minutes/tags
#     : 编辑后的字段快照
#   - is_approved/is_rejected: 审核状态（默认均 False，即 pending）
#   - submit_reason: 作者提交修订时的说明
#   - reject_reason: 审核拒绝时的理由
#   - edited_by: 编辑者用户 ID
#   - created_at: 创建时间
#   - reviewed_at: 审核完成时间
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


class PipelineTemplateRevision(Base):
    """公开模板的修订草稿"""

    __tablename__ = "pipeline_template_revisions"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(
        Integer,
        ForeignKey("pipeline_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # ----- 编辑后的字段快照 -----
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False)
    thumbnail_url = Column(String(500), nullable=True)
    inputs_config = Column(JSON, nullable=False)
    steps_config = Column(JSON, nullable=False)
    output_mapping = Column(JSON, nullable=True)
    script_template_id = Column(Integer, ForeignKey("script_templates.id"), nullable=True)
    estimated_credits = Column(Integer, default=100, nullable=False)
    estimated_time_minutes = Column(Integer, default=10, nullable=False)
    tags = Column(JSON, default=list, nullable=False)

    # ----- 审核字段 -----
    is_approved = Column(Boolean, default=False, nullable=False, index=True)
    is_rejected = Column(Boolean, default=False, nullable=False, index=True)
    submit_reason = Column(String(500), nullable=True)
    reject_reason = Column(String(500), nullable=True)

    # ----- 编辑者与时间 -----
    edited_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)

    # ----- 关联 -----
    template = relationship("PipelineTemplate", back_populates="revisions")

    __table_args__ = (
        # 同一模板下未审核的 revision 唯一（应用层保证覆盖），此处加联合索引便于查询
        Index(
            "idx_ptrev_template_pending",
            "template_id",
            "is_approved",
            "is_rejected",
        ),
    )
