# =====================================================
# PipelineStepOutputRevision 模型 — 步骤产物版本历史
#
# 用途：记录流水线步骤产物的每一次修订快照，支持回滚与版本对比。
#       当用户对某一步骤的输出（如分镜图片、字幕、配音）进行编辑或替换时，
#       在写入新 output_data 之前先把当前快照追加到本表，从而保留完整历史。
#
# 关键字段说明:
#   - run_id: 关联的流水线实例（FK pipeline_runs.id，CASCADE 删除）
#   - step_key: 步骤定义的 key（如 'image_generation'）
#   - revision: 第几次修订（从 1 开始递增）
#   - output_data: 该修订的完整产物快照（JSON）
#   - edited_by: 编辑者用户 ID
#   - edited_at: 编辑时间
#   - change_summary: 变更摘要（如 "替换 char_001 的图片"）
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


class PipelineStepOutputRevision(Base):
    """流水线步骤产物的修订历史快照"""

    __tablename__ = "pipeline_step_output_revisions"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(
        Integer,
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_key = Column(String(100), nullable=False)
    # 第几次修订（从 1 开始）
    revision = Column(Integer, nullable=False)
    # 完整快照
    output_data = Column(JSON, nullable=False)
    edited_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    edited_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # 变更摘要（如 "替换 char_001 的图片"）
    change_summary = Column(String(500), nullable=True)

    # 关联（PipelineRun 不需要 back_populates，避免改动现有模型）
    run = relationship("PipelineRun")

    __table_args__ = (
        # 联合索引：便于按 run + step 查询其全部修订历史
        Index(
            "idx_step_output_rev_run_step",
            "run_id",
            "step_key",
            "revision",
        ),
    )
