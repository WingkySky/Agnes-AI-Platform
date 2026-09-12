# =====================================================
# StyleElement 模型 — 分层风格元素
# 风格库的分层组合基本单元，用户可在多个视觉维度层
# 独立选择元素，组合出个性化风格。借鉴 Leonardo Elements 设计。
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, ForeignKey, Float, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


# 风格层级常量（与前端 Tab 一一对应）
LAYER_VISUAL_STYLE = "visual_style"  # 画风层
LAYER_LIGHTING = "lighting"          # 光影层
LAYER_COLOR = "color"                # 配色层
LAYER_CAMERA = "camera"              # 镜头层
LAYER_MOOD = "mood"                  # 氛围层
LAYER_QUALITY = "quality"            # 品质层

ALL_LAYERS = [
    LAYER_VISUAL_STYLE,
    LAYER_LIGHTING,
    LAYER_COLOR,
    LAYER_CAMERA,
    LAYER_MOOD,
    LAYER_QUALITY,
]


class StyleElement(Base):
    """
    风格元素（分层组合的基本单元）

    一个 StyleElement 聚焦一个视觉维度（如画风、光影、配色等），
    用户可在多个层独立选择元素，组合出个性化风格。

    与 StylePreset 的关系：两条并行路径，互斥使用。
    - StylePreset：完整风格套装，一键应用（简单快速）
    - StyleElement：分层元素，按层组合+权重（灵活定制）

    字段说明:
    - id: 主键
    - key: 元素唯一标识（如 "visual_style.manga_jp"）
    - name: 显示名称（如 "日系漫画"）
    - description: 描述
    - layer: 所属层（visual_style / lighting / color / camera / mood / quality）
    - category: 细分类（如 visual_style 下分 anime/realistic/watercolor...）
    - content: 该层提示词内容（如 "manga style, japanese comic book art, clean lineart"）
    - negative_content: 该层负面提示词（如 "photorealistic, 3d render"）
    - preview_image: 缩略图 URL（用 Agnes Image API 生成）
    - weight_default: 默认权重 0.0–1.0（用户可调）
    - tags: 标签（JSON 数组）
    - is_builtin: 是否内置
    - is_public: 是否公开
    - author_id: 作者用户 ID
    - use_count: 使用次数
    - sort_order: 排序权重
    """

    __tablename__ = "style_elements"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    layer = Column(String(50), nullable=False, index=True)
    category = Column(String(50), nullable=True)
    content = Column(Text, nullable=False)
    negative_content = Column(Text, nullable=True)
    preview_image = Column(String(500), nullable=True)
    weight_default = Column(Float, default=1.0, nullable=False)
    tags = Column(JSON, default=list, nullable=False)
    is_builtin = Column(Boolean, default=False, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    use_count = Column(Integer, default=0, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 索引：按 layer + sort_order 查询常用
    __table_args__ = (
        Index("ix_style_elements_layer_sort", "layer", "sort_order"),
    )
