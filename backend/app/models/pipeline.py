# =====================================================
# Pipeline 模型 — 流水线模板、剧本模板、风格预设等数据模型
# 项目制创作（Project）已迁移到 app.models.project，本文件仅保留模板相关表
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


class PipelineTemplate(Base):
    """
    流水线模板

    预定义的多步骤生成流程，描述「一件作品是怎么一步步做出来的」。
    内置模板由系统提供，用户也可以创建自定义模板。

    字段说明:
    - id: 主键
    - key: 模板唯一标识（如 'comic_drama_standard'）
    - name: 显示名称
    - description: 详细描述
    - category: 分类（drama 剧情类 / ad 广告类 / education 科普类 / art 艺术类）
    - thumbnail_url: 缩略图 URL
    - inputs_config: 用户输入参数定义（JSON 数组）
    - steps_config: 步骤定义（JSON 数组，有序）
    - output_mapping: 输出映射配置（JSON 对象）
    - script_template_id: 关联的剧本模板 ID
    - estimated_credits: 预估消耗积分
    - estimated_time_minutes: 预估耗时（分钟）
    - tags: 标签（JSON 数组）
    - is_builtin: 是否内置模板
    - is_public: 是否公开（用户分享的模板）
    - is_approved: 是否通过审核（公开模板需审核通过才可见）
    - is_rejected: 是否已被驳回（驳回后不可再次提交公开）
    - submit_reason: 提交公开时的说明文字
    - reject_reason: 驳回理由
    - author_id: 作者用户 ID（内置模板为 NULL）
    - use_count: 使用次数统计
    - likes_count: 点赞数
    - has_pending_revision: 是否有未审核的修订草稿（公开模板编辑时置 True）
    """

    __tablename__ = "pipeline_templates"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False, index=True)
    thumbnail_url = Column(String(500), nullable=True)
    inputs_config = Column(JSON, nullable=False)
    steps_config = Column(JSON, nullable=False)
    output_mapping = Column(JSON, nullable=True)
    script_template_id = Column(Integer, ForeignKey("script_templates.id"), nullable=True)
    estimated_credits = Column(Integer, default=100, nullable=False)
    estimated_time_minutes = Column(Integer, default=10, nullable=False)
    tags = Column(JSON, default=list, nullable=False)
    is_builtin = Column(Boolean, default=False, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False, index=True)
    is_approved = Column(Boolean, default=False, nullable=False, index=True)
    is_rejected = Column(Boolean, default=False, nullable=False)
    submit_reason = Column(String(500), nullable=True)
    reject_reason = Column(String(500), nullable=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    use_count = Column(Integer, default=0, nullable=False)
    likes_count = Column(Integer, default=0, nullable=False)
    # 是否存在未审核的修订草稿（公开模板编辑时置 True，审核通过/拒绝时置回 False）
    has_pending_revision = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    script_template = relationship("ScriptTemplate", back_populates="pipeline_templates")
    # 公开模板的修订草稿列表（CASCADE 删除由外键约束保证）
    revisions = relationship(
        "PipelineTemplateRevision",
        back_populates="template",
        cascade="all, delete-orphan",
    )


class ScriptTemplate(Base):
    """
    剧本模板

    LLM 生成剧本的提示词模板与输出结构定义。
    不同类型的内容（漫剧、广告、科普）使用不同的剧本模板。

    字段说明:
    - id: 主键
    - key: 模板唯一标识
    - name: 模板名称
    - description: 描述
    - category: 分类（drama / ad / education / art）
    - structure: 叙事结构（three_act 三幕式 / five_act 五幕式 / kishotenketsu 起承转合）
    - prompt_template: 提示词模板（Jinja2 风格变量）
    - output_schema: 期望的 JSON 输出结构（JSON Schema）
    - variables_schema: 输入变量定义（JSON Schema）
    - scenes_min: 最少分镜数
    - scenes_max: 最多分镜数
    - default_scene_duration: 默认单镜时长（秒）
    - output_format: 输出格式（json/text）
    - tags: 标签（JSON 数组）
    - is_builtin: 是否内置模板
    - is_public: 是否公开
    - author_id: 作者用户 ID
    """

    __tablename__ = "script_templates"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False, index=True)
    structure = Column(String(50), nullable=False)
    prompt_template = Column(Text, nullable=False)
    output_schema = Column(JSON, nullable=False)
    variables_schema = Column(JSON, nullable=True)
    scenes_min = Column(Integer, default=3, nullable=False)
    scenes_max = Column(Integer, default=20, nullable=False)
    default_scene_duration = Column(Integer, default=5, nullable=False)
    output_format = Column(String(20), default="json", nullable=False)
    tags = Column(JSON, default=list, nullable=False)
    is_builtin = Column(Boolean, default=False, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    pipeline_templates = relationship("PipelineTemplate", back_populates="script_template")


class StylePreset(Base):
    """
    风格预设

    视觉风格的可复用配置，包括画风、光影、配色、镜头语言等。

    字段说明:
    - id: 主键
    - key: 风格唯一标识
    - name: 风格名称
    - description: 描述
    - category: 分类（art_style 画风 / mood 氛围 / cinematography 镜头）
    - visual_prefix: 视觉风格前缀
    - lighting: 光影风格
    - color_palette: 配色方案
    - quality_suffix: 品质增强词
    - negative_prompt: 负面提示词
    - camera_language: 镜头语言偏好
    - mood_keywords: 氛围关键词
    - preview_image: 预览图 URL
    - tags: 标签（JSON 数组）
    - is_builtin: 是否内置
    - is_public: 是否公开
    - author_id: 作者用户 ID
    - use_count: 使用次数
    """

    __tablename__ = "style_presets"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False, index=True)
    visual_prefix = Column(Text, nullable=True)
    lighting = Column(String(500), nullable=True)
    color_palette = Column(String(500), nullable=True)
    quality_suffix = Column(Text, nullable=True)
    negative_prompt = Column(Text, nullable=True)
    camera_language = Column(String(500), nullable=True)
    mood_keywords = Column(String(500), nullable=True)
    preview_image = Column(String(500), nullable=True)
    tags = Column(JSON, default=list, nullable=False)
    is_builtin = Column(Boolean, default=False, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    use_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    assets = relationship("Asset", back_populates="style")
