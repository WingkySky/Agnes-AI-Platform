# =====================================================
# Pipeline 模型 — 创意流水线相关数据模型
# 包含流水线模板、执行实例、步骤记录等核心表
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


# =====================================================
# 流水线运行状态常量（与 engine.py 保持一致）
# =====================================================
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

# 步骤状态常量
STEP_STATUS_PENDING = "pending"
STEP_STATUS_RUNNING = "running"
STEP_STATUS_SUCCESS = "success"
STEP_STATUS_FAILED = "failed"
STEP_STATUS_SKIPPED = "skipped"


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
    - author_id: 作者用户 ID（内置模板为 NULL）
    - use_count: 使用次数统计
    - likes_count: 点赞数
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
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    use_count = Column(Integer, default=0, nullable=False)
    likes_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    script_template = relationship("ScriptTemplate", back_populates="pipeline_templates")
    runs = relationship("PipelineRun", back_populates="template", cascade="all, delete-orphan")


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


class PipelineRun(Base):
    """
    流水线执行实例

    一次具体的流水线执行，有状态，可断点续跑。

    字段说明:
    - id: 主键
    - template_id: 使用的模板 ID
    - user_id: 所属用户
    - name: 本次运行的名称（用户可自定义）
    - inputs: 用户输入的参数值（JSON）
    - status: 整体状态
    - current_step_key: 当前执行到的步骤 key
    - started_at: 开始时间
    - finished_at: 结束时间
    - total_credits: 累计消耗积分
    - output_summary: 输出摘要（最终成片 URL 等）
    - error_message: 整体错误信息
    - canvas_export_data: 导出到画布的数据（Phase 3）
    """

    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("pipeline_templates.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String(200), nullable=True)
    inputs = Column(JSON, nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)
    current_step_key = Column(String(100), nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    total_credits = Column(Integer, default=0, nullable=False)
    output_summary = Column(JSON, default=dict, nullable=False)
    error_message = Column(Text, nullable=True)
    canvas_export_data = Column(JSON, nullable=True)
    pause_requested = Column(Boolean, default=False, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    template = relationship("PipelineTemplate", back_populates="runs")
    steps = relationship("PipelineStep", back_populates="run", cascade="all, delete-orphan",
                         order_by="PipelineStep.sort_order")

    __table_args__ = (
        Index("idx_pipeline_runs_user_status", "user_id", "status"),
    )


class PipelineStep(Base):
    """
    流水线步骤执行记录

    流水线中的一个执行步骤，记录输入、输出、状态、耗时等。

    字段说明:
    - id: 主键
    - run_id: 所属流水线实例 ID
    - step_key: 步骤定义的 key（如 'script_generation'）
    - name: 步骤显示名称
    - step_type: 步骤类型
    - status: 状态
    - input_data: 步骤输入数据（JSON）
    - output_data: 步骤输出数据（JSON）
    - error_message: 错误信息
    - started_at: 开始时间
    - finished_at: 结束时间
    - credits_consumed: 本步消耗积分
    - retry_count: 重试次数
    - max_retries: 最大重试次数
    - timeout_sec: 超时时间（秒）
    - depends_on: 依赖的步骤 key 数组（JSON）
    - sort_order: 排序序号
    """

    __tablename__ = "pipeline_steps"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_key = Column(String(100), nullable=False)
    name = Column(String(200), nullable=False)
    step_type = Column(String(50), nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)
    input_data = Column(JSON, default=dict, nullable=False)
    output_data = Column(JSON, default=dict, nullable=False)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    credits_consumed = Column(Integer, default=0, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=1, nullable=False)
    timeout_sec = Column(Integer, default=300, nullable=False)
    depends_on = Column(JSON, default=list, nullable=False)
    sort_order = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    run = relationship("PipelineRun", back_populates="steps")

    __table_args__ = (
        Index("idx_pipeline_steps_run_status", "run_id", "status"),
    )

    # 联合唯一约束：同一个 run 内 step_key 唯一
    __mapper_args__ = {
        "confirm_deleted_rows": False,
    }
