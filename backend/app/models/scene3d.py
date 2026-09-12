# =====================================================
# Scene3D 模型 — 3D 场景布局（导演台 MVP）
# 存储用户在 3D 空间中摆放的相机位姿、主体位置、灯光等布局数据。
# 生成图片/视频时，把 3D 布局翻译成精确的镜头语言描述，
# 注入到现有 prompt 拼接流程，让构图、机位、视角变得可控。
#
# scene_data JSON 结构（支持多主体/多灯光/道具布景）：
#   {
#     "subjects": [
#       {"x":0, "y":0, "z":0, "label":"角色A"},
#       {"x":2, "y":0, "z":0, "label":"角色B"}
#     ],
#     "camera": {
#       "position": {"x":0, "y":1.6, "z":5},
#       "lookAt":   {"x":0, "y":0, "z":0},
#       "fov": 50
#     },
#     "lights": [
#       {"type":"directional", "x":5, "y":8, "z":5, "intensity":1.0},
#       {"type":"directional", "x":-5, "y":3, "z":-3, "intensity":0.4}
#     ],
#     "props": [
#       {"type":"box", "x":1, "y":0, "z":-2, "label":"桌子"}
#     ],
#     "environment": {"type":"studio", "label":"工作室"}
#   }
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, Index

from app.core.database import Base


class Scene3D(Base):
    """
    3D 场景布局（导演台）

    字段说明:
    - id: 主键
    - user_id: 创建者用户 ID
    - name: 场景名称
    - description: 场景描述
    - scene_data: 3D 布局数据（JSON，结构见模块注释）
    - is_public: 是否公开到广场供他人复用（MVP 暂不实现审核流程）
    - created_at / updated_at: 时间戳
    """

    __tablename__ = "scene3d"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    scene_data = Column(JSON, default=dict, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_scene3d_user_updated", "user_id", "updated_at"),
    )
