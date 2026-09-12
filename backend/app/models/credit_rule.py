# =====================================================
# CreditRule 模型 — 积分消耗规则
# 支持按生成类型（图片/视频）、模式（text2image/image2image/text2video/keyframes/image2video）
# 和尺寸/时长等参数计算积分消耗。
#
# 规则表中每条规则对应一个 "规则 key"，例如：
#   - image.text2image.base_cost     (图片文生图基础消耗)
#   - image.image2image.base_cost    (图片图生图基础消耗)
#   - video.text2video.per_second    (视频文生视频每秒消耗)
#   - video.image2video.per_second   (视频图生视频每秒消耗)
#   - new_user_default_credits       (新用户初始赠送积分)
#
# 后台启动时自动写入默认值；管理员可在前端配置页实时调整。
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text

from app.core.database import Base


class CreditRule(Base):
    """
    积分规则表（key-value 结构，value 为整数或 JSON，value_type 标注解释方式）
    """
    __tablename__ = "credit_rules"

    id = Column(Integer, primary_key=True, index=True)
    # 规则的唯一键（前端按 key 读取）
    rule_key = Column(String(128), unique=True, index=True, nullable=False)
    # 规则名（中文）
    name = Column(String(128), nullable=False)
    # 整型值（基础积分成本 / 每分每秒 / 初始积分等）
    value = Column(Integer, default=0, nullable=False)
    # 规则说明
    description = Column(Text, default="", nullable=True)
    # 更新时间
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "rule_key": self.rule_key,
            "name": self.name,
            "value": self.value,
            "description": self.description or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------- 默认规则（启动时若数据库为空，则自动插入） ----------
DEFAULT_CREDIT_RULES = [
    # 图片生成
    {"rule_key": "image.text2image.base_cost", "name": "图片-文生图-基础消耗",
     "value": 10, "description": "每次进行 text2image 时消耗的基础积分"},
    {"rule_key": "image.image2image.base_cost", "name": "图片-图生图-基础消耗",
     "value": 15, "description": "每次进行 image2image 时消耗的基础积分"},
    # 视频生成
    {"rule_key": "video.text2video.per_second", "name": "视频-文生视频-每秒消耗",
     "value": 5, "description": "text2video 每秒消耗的积分（最终成本按秒数相乘）"},
    {"rule_key": "video.image2video.per_second", "name": "视频-图生视频-每秒消耗",
     "value": 6, "description": "image2video / keyframes 每秒消耗积分"},
    # 新用户默认积分
    {"rule_key": "new_user.default_credits", "name": "新用户初始积分",
     "value": 500, "description": "新注册用户自动获得的积分"},
]
