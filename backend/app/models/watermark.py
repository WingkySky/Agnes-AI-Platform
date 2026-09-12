# =====================================================
# 水印配置模型
# - 全局水印配置（管理员在后台设置）
# - 每个用户可单独开关（users.watermark_enabled）
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean

from app.core.database import Base


class WatermarkConfig(Base):
    """全局水印配置表（只存一条记录，id=1）"""
    __tablename__ = "watermark_config"

    id = Column(Integer, primary_key=True)
    # 水印类型：text（文字水印）/ image（图片水印）
    type = Column(String(16), default="text", nullable=False)
    # 文字水印内容
    text = Column(String(128), default="Agnes AI", nullable=False)
    # 字体大小
    font_size = Column(Integer, default=24, nullable=False)
    # 字体颜色（十六进制，如 #FFFFFF）
    color = Column(String(16), default="#FFFFFF", nullable=False)
    # 透明度（0-1，0 完全透明，1 完全不透明）
    opacity = Column(Integer, default=50, nullable=False)  # 百分比 0-100
    # 位置：top-left / top-right / bottom-left / bottom-right / center
    position = Column(String(32), default="bottom-right", nullable=False)
    # 边距（像素）
    margin = Column(Integer, default=20, nullable=False)
    # 图片水印 URL（当 type=image 时使用）
    image_url = Column(String(255), nullable=True)
    # 图片水印大小（宽度，高度按比例缩放，像素）
    image_width = Column(Integer, default=120, nullable=False)
    # 是否全局强制启用水印（所有用户都加水印，覆盖用户级开关）
    force_all = Column(Boolean, default=False, nullable=False)
    # 配置更新时间
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "text": self.text,
            "font_size": self.font_size,
            "color": self.color,
            "opacity": self.opacity,
            "position": self.position,
            "margin": self.margin,
            "image_url": self.image_url,
            "image_width": self.image_width,
            "force_all": self.force_all,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
