# =====================================================
# 流水线相关的 Pydantic Schema
# 包含流水线模板、执行实例、步骤记录等
# =====================================================

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, computed_field


# =====================================================
# 流水线模板 Schema
# =====================================================

class PipelineTemplateBase(BaseModel):
    """流水线模板基础字段"""
    key: str = Field(..., min_length=1, max_length=100, description="模板唯一标识")
    name: str = Field(..., min_length=1, max_length=200, description="显示名称")
    description: Optional[str] = Field(None, description="详细描述")
    category: str = Field(..., description="分类：drama / ad / education / art")
    thumbnail_url: Optional[str] = Field(None, max_length=500, description="缩略图 URL")
    inputs_config: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="用户输入参数定义（JSON 数组）",
    )
    steps_config: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="步骤定义（JSON 数组，有序）",
    )
    script_template_id: Optional[int] = Field(None, description="关联的剧本模板 ID")


class PipelineTemplateCreate(PipelineTemplateBase):
    """创建流水线模板请求"""
    is_public: bool = Field(False, description="是否公开")


class PipelineTemplateUpdate(BaseModel):
    """更新流水线模板请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    thumbnail_url: Optional[str] = None
    inputs_config: Optional[List[Dict[str, Any]]] = None
    steps_config: Optional[List[Dict[str, Any]]] = None
    script_template_id: Optional[int] = None
    is_public: Optional[bool] = None
    # 补全之前缺失的字段（修复 tags 无法写入的 bug）
    output_mapping: Optional[Dict[str, Any]] = None
    estimated_credits: Optional[int] = None
    estimated_time_minutes: Optional[int] = None
    tags: Optional[List[str]] = None


class PipelineTemplateResponse(PipelineTemplateBase):
    """流水线模板响应"""
    id: int
    is_builtin: bool = False
    is_public: bool = False
    is_approved: bool = False
    is_rejected: bool = False
    submit_reason: Optional[str] = None
    reject_reason: Optional[str] = None
    author_id: Optional[int] = None
    use_count: int = 0
    likes_count: int = 0
    tags: List[str] = Field(default_factory=list, description="标签列表")
    estimated_credits: int = Field(default=0, description="预估积分")
    estimated_time_minutes: int = Field(default=10, description="预估耗时（分钟）")
    output_mapping: Optional[Dict[str, Any]] = Field(default=None, description="输出映射配置")
    # 是否存在未审核的修订草稿（编辑器进入时拉取草稿、卡片显示"修订中"徽章用）
    has_pending_revision: bool = Field(default=False, description="是否存在未审核的修订草稿")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @computed_field
    @property
    def thumbnail(self) -> Optional[str]:
        return self.thumbnail_url

    @computed_field
    @property
    def estimated_time(self) -> str:
        if self.estimated_time_minutes >= 60:
            hours = self.estimated_time_minutes // 60
            mins = self.estimated_time_minutes % 60
            if mins > 0:
                return f"约{hours}小时{mins}分钟"
            return f"约{hours}小时"
        return f"约{self.estimated_time_minutes}分钟"

    class Config:
        from_attributes = True


# 兼容别名
PipelineTemplateOut = PipelineTemplateResponse


# =====================================================
# 流水线模板修订草稿（Revision）Schema
# 用于公开已审核模板被编辑后生成的 pending revision 序列化
# =====================================================

class TemplateFromScenarioRequest(BaseModel):
    """从场景预设创建模板请求"""
    scenario_key: str = Field(..., description="场景预设 key")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="用户输入参数")
    name: Optional[str] = None
    description: Optional[str] = None
    is_public: bool = Field(False, description="是否公开")
    tags: Optional[List[str]] = None
    custom_steps_config: Optional[List[Dict[str, Any]]] = Field(None, description="自定义步骤配置（如果提供，则覆盖场景预设的步骤配置）")


class PipelineTemplateRevisionOut(BaseModel):
    """流水线模板修订草稿响应（编辑器拉取草稿 + 审核页面展示共用）"""
    id: int
    template_id: int
    # ----- 编辑后的字段快照 -----
    name: str
    description: Optional[str] = None
    category: str
    thumbnail_url: Optional[str] = None
    inputs_config: List[Dict[str, Any]] = Field(default_factory=list)
    steps_config: List[Dict[str, Any]] = Field(default_factory=list)
    output_mapping: Optional[Dict[str, Any]] = None
    script_template_id: Optional[int] = None
    estimated_credits: int = 0
    estimated_time_minutes: int = 10
    tags: List[str] = Field(default_factory=list)
    # ----- 审核字段 -----
    is_approved: bool = False
    is_rejected: bool = False
    submit_reason: Optional[str] = None
    reject_reason: Optional[str] = None
    # ----- 编辑者与时间 -----
    edited_by: Optional[int] = None
    created_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PipelineTemplateListResponse(BaseModel):
    """流水线模板列表响应"""
    total: int
    page: int
    page_size: int
    items: List[PipelineTemplateResponse]


# =====================================================
# 积分预估 Schema
# =====================================================

class CreditEstimateRequest(BaseModel):
    """积分预估请求"""
    template_id: int = Field(None, description="模板 ID（URL 参数提供）")
    inputs: Dict[str, Any] = Field(default_factory=dict)


class CreditEstimateResponse(BaseModel):
    """积分预估响应"""
    estimated_total: int = Field(description="预估总积分")
    breakdown: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="各步骤预估明细：[{step_key, step_name, step_type, estimated_credits}]",
    )
    note: Optional[str] = Field(None, description="说明（如实际消耗可能因重试等因素变化）")


# 兼容别名
CreditEstimateOut = CreditEstimateResponse
