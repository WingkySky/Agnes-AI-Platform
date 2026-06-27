# =====================================================
# CameraPreset 模型 — 摄像机参数预设
# 存储摄像机参数组合（机型、焦段、光圈、运镜等），
# 用于图片/视频生成时将摄像机参数拼接到 prompt 中。
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean

from app.core.database import Base


class CameraPreset(Base):
    """
    摄像机参数预设

    字段说明:
    - id: 主键
    - user_id: 创建者用户 ID
    - name: 预设名称
    - description: 预设描述
    - type: 类型（固定为 "camera"）
    - category: 分类（默认 "通用"）
    - tags: 标签（JSON 数组）
    - camera_model: 摄像机机型（如 "Sony FX3"）
    - focal_length: 焦段（如 "85mm"）
    - aperture: 光圈（如 "f/2.8"）
    - depth_of_field: 景深（如 "浅景深"）
    - shutter_speed: 快门速度（如 "1/125"）
    - shutter_angle: 快门角度（如 "180°"）
    - camera_movement: 运镜方式（如 "手持运镜"）
    - camera_angle: 拍摄角度（如 "平视视角"）
    - aspect_ratio: 画幅比（如 "2.35:1"）
    - visual_style: 视觉风格（如 "暖色调胶片风格"）
    - is_public: 是否公开
    - is_approved: 是否审核通过
    - usage_count: 使用次数
    - created_at: 创建时间
    - updated_at: 更新时间
    """

    __tablename__ = "camera_presets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String(20), default="camera", nullable=False)
    category = Column(String(50), default="通用", nullable=False)
    tags = Column(JSON, default=list, nullable=False)
    camera_model = Column(String(200), nullable=True)
    focal_length = Column(String(50), nullable=True)
    aperture = Column(String(50), nullable=True)
    depth_of_field = Column(String(100), nullable=True)
    shutter_speed = Column(String(50), nullable=True)
    shutter_angle = Column(String(50), nullable=True)
    camera_movement = Column(String(200), nullable=True)
    camera_angle = Column(String(100), nullable=True)
    aspect_ratio = Column(String(50), nullable=True)
    visual_style = Column(String(200), nullable=True)
    is_public = Column(Boolean, default=False, nullable=False)
    is_approved = Column(Boolean, default=False, nullable=False)
    # is_rejected: 管理员驳回标记，True 时禁止再次提交公开审核
    is_rejected = Column(Boolean, default=False, nullable=False)
    usage_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
