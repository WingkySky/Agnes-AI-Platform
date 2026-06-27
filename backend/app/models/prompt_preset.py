# =====================================================
# PromptPreset 模型 — 统一提示词预设
# 存储通用文本提示词、摄像机参数、风格参数、脚本、
# 流水线配置等可复用创作配置。
# 
# 同时包含 PresetIndex 轻量索引表，用于跨表聚合查询。
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean

from app.core.database import Base


class PromptPreset(Base):
    """
    提示词预设

    字段说明:
    - id: 主键
    - user_id: 创建者用户 ID
    - type: 预设类型（camera / prompt / style / script / pipeline）
    - category: 分类（默认 "通用"，枚举：人像/场景/构图/动作/光影/风格/通用）
    - tags: 标签（JSON 数组，开放自由填写）
    - name: 预设名称
    - description: 预设描述
    - prompt_text: 提示词文本（prompt 类型核心字段）
    - camera_params: 摄像机参数（JSON，camera 类型使用，nullable）
    - style_params: 风格参数（JSON，style 类型使用，nullable）
    - script_text: 脚本文本（script 类型使用，nullable）
    - pipeline_config: 流水线配置（JSON，pipeline 类型使用，nullable）
    - is_public: 是否公开共享
    - is_approved: 是否通过管理员审核
    - usage_count: 使用次数（异步定时统计，非实时精确）
    - created_at: 创建时间
    - updated_at: 更新时间
    """

    __tablename__ = "prompt_presets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    type = Column(String(50), default="prompt", nullable=False)
    category = Column(String(50), default="通用", nullable=False)
    tags = Column(JSON, default=list, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    prompt_text = Column(Text, nullable=False, default="")
    camera_params = Column(JSON, nullable=True)
    style_params = Column(JSON, nullable=True)
    script_text = Column(Text, nullable=True)
    pipeline_config = Column(JSON, nullable=True)
    is_public = Column(Boolean, default=False, nullable=False)
    is_approved = Column(Boolean, default=False, nullable=False)
    # is_rejected: 管理员驳回标记，True 时禁止再次提交公开审核
    is_rejected = Column(Boolean, default=False, nullable=False)
    usage_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PresetIndex(Base):
    """
    预设轻量索引表

    用于跨表聚合查询，避免全表扫描多张预设表。
    各 Preset Service 在 CUD 操作时同步 upsert 本表。
    type 为空（全部类型）时走本表；单一 type 时走原表。

    字段说明:
    - id: 主键
    - preset_type: 预设类型（camera / prompt / style / script / pipeline）
    - preset_id: 对应原表的主键 ID
    - category: 分类
    - tags: 标签（JSON 数组）
    - user_id: 创建者用户 ID
    - is_public: 是否公开
    - is_approved: 是否审核通过
    - usage_count: 使用次数
    - name: 预设名称
    - description: 预设描述
    - created_at: 创建时间（首次创建时间）
    """

    __tablename__ = "preset_index"

    id = Column(Integer, primary_key=True, index=True)
    preset_type = Column(String(50), nullable=False, index=True)
    preset_id = Column(Integer, nullable=False, index=True)
    category = Column(String(50), default="通用")
    tags = Column(JSON, default=list, nullable=False)
    user_id = Column(Integer, nullable=True, index=True)
    is_public = Column(Boolean, default=False)
    is_approved = Column(Boolean, default=False)
    # is_rejected: 管理员驳回标记，True 时禁止再次提交公开审核
    is_rejected = Column(Boolean, default=False, nullable=False)
    usage_count = Column(Integer, default=0)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
