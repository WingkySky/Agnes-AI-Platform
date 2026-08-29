# =====================================================
# Asset 模型 — 资产库数据模型
# 包含角色、道具、场景、品牌等可复用创意资产
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


class Asset(Base):
    """
    创意资产

    可复用的创意素材单元，包括角色、道具、场景、品牌等。
    资产可以被多个流水线复用，支持版本管理和分享。

    字段说明:
    - id: 主键
    - type: 类型（character 角色 / prop 道具 / scene 场景 / brand 品牌 /
           material 素材图（含分镜图）/ clip 视频片段 / final 成片）
    - name: 名称
    - description: 详细描述
    - visual_description: 外观描述文本（用于生成提示词）
    - reference_images: 参考图 URL 数组（JSON）
    - style_id: 关联的风格预设 ID（可选）
    - user_id: 创建者用户 ID
    - is_public: 是否公开到广场
    - moderation_status: 审核状态
    - moderation_reason: 审核原因
    - tags: 标签数组（JSON）
    - version: 版本号（从 1 开始）
    - parent_id: 父版本 ID（用于版本链）
    - likes_count: 点赞数
    - views_count: 浏览次数
    - use_count: 被使用次数

    创作归档字段（container_* 非空即为画布/项目生成的自动归档影子记录）：
    - container_type: 创作容器类型（project / canvas_script / canvas）
    - container_id: 创作容器 ID（项目 ID / 剧本面板 ID / 固定 'canvas'）
    - container_name: 容器名快照（剧本/项目改名或删除后归档记录仍可正常分组显示）
    - source_generation_id: 来源生成记录 ID（归档去重键）
    - kind: 媒体类型（image / video）
    - asset_url: 单媒体 URL（归档记录用；传统多图角色卡继续用 reference_images）
    """

    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(30), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    visual_description = Column(Text, nullable=False)
    reference_images = Column(JSON, default=list, nullable=False)
    style_id = Column(Integer, ForeignKey("style_presets.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    is_public = Column(Boolean, default=False, nullable=False, index=True)
    moderation_status = Column(String(20), default="approved", nullable=False, index=True)
    moderation_reason = Column(String(255), nullable=True)
    tags = Column(JSON, default=list, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    parent_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    likes_count = Column(Integer, default=0, nullable=False)
    views_count = Column(Integer, default=0, nullable=False)
    use_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ===== 广场分享时间（用于「创作」Tab 最新排序）=====
    public_shared_at = Column(DateTime, nullable=True)

    # ===== 创作归档字段 =====
    container_type = Column(String(30), nullable=True)      # project / canvas_script / canvas
    container_id = Column(String(100), nullable=True)       # 项目 ID / 剧本面板 ID / 'canvas'
    container_name = Column(String(200), nullable=True)     # 容器名快照
    source_generation_id = Column(Integer, ForeignKey("generations.id"), nullable=True, index=True)
    kind = Column(String(20), nullable=True)                # image / video
    asset_url = Column(Text, nullable=True)                 # 单媒体 URL

    # 关联
    style = relationship("StylePreset", back_populates="assets")
    parent = relationship("Asset", remote_side=[id])

    # 创作单元分组查询索引：(user_id, container_type, container_id)
    __table_args__ = (
        Index("ix_assets_user_container", "user_id", "container_type", "container_id"),
    )
