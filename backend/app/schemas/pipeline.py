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
# 流水线实例 Schema
# =====================================================

class PipelineRunCreate(BaseModel):
    """创建流水线实例请求"""
    template_id: int = Field(..., description="使用的模板 ID")
    name: Optional[str] = Field(None, max_length=200, description="本次运行名称")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="用户输入参数值")
    camera_params: Optional[dict] = Field(
        default=None,
        description="摄像机参数，含 enabled 子字段。enabled=True 时拼接到 prompt 末尾",
    )


class PipelineRunResponse(BaseModel):
    """流水线实例响应"""
    id: int
    template_id: int
    template_name: Optional[str] = None
    user_id: Optional[int] = None
    name: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"
    current_step_key: Optional[str] = None
    current_step: Optional[str] = Field(None, description="当前步骤（别名）")
    progress: int = Field(default=0, description="进度百分比（0-100）")
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    total_credits: int = 0
    output_summary: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @computed_field
    @property
    def video_url(self) -> Optional[str]:
        """从 output_summary 中提取最终视频 URL"""
        return self.output_summary.get("final_video_url") or self.output_summary.get("video_url")

    @computed_field
    @property
    def thumbnail_url(self) -> Optional[str]:
        """从 output_summary 中提取视频缩略图 URL"""
        return self.output_summary.get("thumbnail_url")

    @computed_field
    @property
    def duration_seconds(self) -> Optional[float]:
        """从 output_summary 中提取视频时长（秒）"""
        dur = self.output_summary.get("duration_seconds") or self.output_summary.get("duration")
        if dur is not None:
            return float(dur)
        return None

    class Config:
        from_attributes = True


# 兼容别名
PipelineRunOut = PipelineRunResponse


class PipelineRunDetailResponse(PipelineRunResponse):
    """流水线实例详情（含所有步骤）"""
    steps: List["PipelineStepResponse"] = Field(default_factory=list)


class PipelineRunListResponse(BaseModel):
    """流水线实例列表响应"""
    total: int
    page: int
    page_size: int
    items: List[PipelineRunResponse]


# =====================================================
# 流水线步骤 Schema
# =====================================================

class PipelineStepResponse(BaseModel):
    """流水线步骤响应"""
    id: int
    run_id: int
    step_key: str
    name: str
    step_type: str
    status: str = "pending"
    depends_on: List[str] = Field(default_factory=list)
    sort_order: int = 0
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 1
    credits_consumed: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # 前端兼容字段
    @computed_field
    @property
    def output(self) -> Dict[str, Any]:
        return self.output_data

    @computed_field
    @property
    def error(self) -> Optional[str]:
        return self.error_message

    class Config:
        from_attributes = True


# 兼容别名
PipelineStepOut = PipelineStepResponse


class PipelineStepRetryRequest(BaseModel):
    """重试步骤请求"""
    reset_output: bool = Field(True, description="是否重置输出数据")


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


# =====================================================
# 字幕编辑 Schema
# =====================================================

class SubtitleEntry(BaseModel):
    """单条字幕条目"""
    index: int = Field(description="字幕序号（从 0 开始连续递增）")
    scene_index: Optional[int] = Field(None, description="对应原场景序号")
    start: float = Field(description="开始时间（秒）")
    end: float = Field(description="结束时间（秒）")
    text: str = Field(description="字幕文本")


class SubtitlesSaveRequest(BaseModel):
    """字幕保存请求"""
    subtitles: List[SubtitleEntry] = Field(description="字幕条目列表")


class SubtitlesSaveResponse(BaseModel):
    """字幕保存响应"""
    srt_url: str = Field(description="重新生成的 SRT 文件 URL")
    vtt_url: str = Field("", description="重新生成的 VTT 文件 URL（浏览器 <track> 标签需要）")
    subtitles: List[SubtitleEntry] = Field(description="保存后的字幕列表（已重新编号）")


# =====================================================
# 字幕样式 + 重新烧录 Schema
# =====================================================

class SubtitleStyle(BaseModel):
    """字幕样式配置"""
    font_size: Optional[int] = Field(None, ge=12, le=120, description="字号（12-120）")
    font_color: Optional[str] = Field(None, description="字体颜色 hex（如 FFFFFF）")
    box_color: Optional[str] = Field(None, description="底框颜色 hex")
    box_opacity: Optional[float] = Field(None, ge=0.0, le=1.0, description="底框不透明度（0-1）")
    position: Optional[str] = Field(None, pattern="^(top|center|bottom)$", description="位置")
    margin: Optional[int] = Field(None, ge=0, le=500, description="边距 px")


class RecomposeRequest(BaseModel):
    """重新烧录视频请求"""
    subtitles: Optional[List[Dict[str, Any]]] = Field(
        None, description="字幕条目列表（不传则用已保存的）"
    )
    subtitle_style: Optional[SubtitleStyle] = Field(
        None, description="字幕样式配置（不传则用模板默认）"
    )


# =====================================================
# 历史视频后期处理 Schema
# =====================================================

class VideoEditOperation(BaseModel):
    """剪辑操作条目"""
    type: str = Field(..., pattern="^(trim|cut)$", description="操作类型：trim 保留区间 / cut 删除区间")
    start: float = Field(..., ge=0, description="起始时间（秒）")
    end: float = Field(..., ge=0, description="结束时间（秒）")


class PostProcessRequest(BaseModel):
    """
    历史视频后期处理请求

    对 Generation 表中已存在的视频做二次后期处理（调色 / 剪辑），
    无需重跑整个流水线。处理结果作为新的 Generation 记录入库。
    """
    operation: str = Field(
        ...,
        pattern="^(color_grade|video_edit)$",
        description="操作类型：color_grade 调色 / video_edit 剪辑",
    )
    # 调色配置（operation=color_grade 时使用）
    preset: Optional[str] = Field(
        "neutral_punch",
        description="调色预设：subtle/neutral_punch/warm_cinematic/none/auto 或自定义 ffmpeg 滤镜链",
    )
    with_audio_fade: Optional[bool] = Field(
        True, description="是否叠加 30ms 音频淡入淡出（避免切点爆音）",
    )
    # 剪辑配置（operation=video_edit 时使用）
    operations: Optional[List[VideoEditOperation]] = Field(
        None, description="剪辑操作列表（trim 保留区间 / cut 删除区间）",
    )


class PostProcessResponse(BaseModel):
    """历史视频后期处理响应"""
    success: bool = Field(description="是否处理成功")
    source_generation_id: int = Field(description="源视频 Generation ID")
    new_generation_id: int = Field(description="新生成的视频 Generation ID")
    result_url: str = Field(description="处理结果视频 URL")
    operation: str = Field(description="实际执行的操作类型")
    credits_consumed: int = Field(description="本次处理消耗的积分")


# =====================================================
# 画布导出 Schema
# =====================================================

class CanvasExportData(BaseModel):
    """画布导出数据（用于将流水线结果导入画布）"""
    nodes: List[Dict[str, Any]] = Field(default_factory=list, description="节点列表")
    edges: List[Dict[str, Any]] = Field(default_factory=list, description="连线列表")
    viewport: Dict[str, Any] = Field(default_factory=dict, description="视口位置")


# 修复前向引用
PipelineRunDetailResponse.model_rebuild()

