# =====================================================
# CreditTransaction 模型 — 积分变动明细流水
#
# 记录用户积分的每一次变动，包括：
#   - 充值（recharge）：管理员给用户充值
#   - 消耗（consume）：生成任务创建时预扣
#   - 退还（refund）：生成任务失败时退还预扣的积分
#   - 调整（adjust）：管理员手动调整
#
# 字段说明：
#   - amount：变动数量（正数为增加，负数为减少）
#   - balance_after：变动后的余额（便于审计和对账）
#   - status：consume 类型有效（pending=预扣中 / confirmed=已确认 / refunded=已退还）
#             其他类型默认为 confirmed
#   - ref_type / ref_id：关联的生成任务类型和 ID（image/video + task_id）
#   - description：人类可读的变动说明
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey

from app.core.database import Base


class CreditTransaction(Base):
    """积分变动明细流水表"""
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True, index=True)
    # 关联用户
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # 变动类型：recharge / consume / refund / adjust
    type = Column(String(32), nullable=False, index=True)
    # 变动数量（正数为增加，负数为减少；consume 为负数，recharge/refund 为正数）
    amount = Column(Integer, nullable=False)
    # 变动后余额（便于审计）
    balance_after = Column(Integer, nullable=False, default=0)
    # 状态：consume 类型有效（pending=预扣中 / confirmed=已确认 / refunded=已退还）
    # 其他类型默认为 confirmed
    status = Column(String(32), nullable=False, default="confirmed")
    # 关联的生成任务类型（image / video），仅 consume/refund 有值
    ref_type = Column(String(32), nullable=True)
    # 关联的生成任务 ID（task_id），仅 consume/refund 有值
    ref_id = Column(String(128), nullable=True, index=True)
    # 变动说明
    description = Column(Text, default="", nullable=True)
    # 操作者（管理员 ID；用户自己操作时为空）
    operator_id = Column(Integer, nullable=True)
    # 创建时间
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "amount": self.amount,
            "balance_after": self.balance_after,
            "status": self.status,
            "ref_type": self.ref_type,
            "ref_id": self.ref_id,
            "description": self.description or "",
            "operator_id": self.operator_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
