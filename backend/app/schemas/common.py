# =====================================================
# 通用 / 历史记录相关的 Pydantic Schema
# =====================================================

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    service: str


class ImageSizeOption(BaseModel):
    """图片尺寸选项（含比例信息，供前端绘制比例图标）"""
    value: str = Field(description="传给 API 的尺寸值，如 1024x768")
    w: int = Field(description="宽高比宽分量")
    h: int = Field(description="宽高比高分量")
    label: str = Field(description="显示标签，如 16:9 横屏")
    # 清晰度等级：sd=标清 / hd=超清 / 4k=4K
    tier: str = Field(default="sd", description="清晰度等级：sd=标清 / hd=超清 / 4k=4K")
    # 实际输出像素数（用于 UI 展示，如 1024x1024 → 1048576）
    pixels: int = Field(default=0, description="实际输出像素数（用于 UI 展示）")


class ModelGenParams(BaseModel):
    """
    模型生成能力配置（model_definitions.gen_params，按模型差异化的约束/规则）

    已知键在此定义为唯一出处；新增键 = 扩展本 schema + 对应规则实现。
    NULL/缺省表示无特例，注册表按模型名自动画像兜底。
    """
    max_ref_images: Optional[int] = Field(
        default=None,
        description="单次生成参考图/参考帧上限（超出由后端截断、前端提前截断）；None=不限制",
    )
    watermark_param_off: Optional[bool] = Field(
        default=None,
        description="请求是否携带厂商官方 watermark=false（关闭「AI生成」显式标识水印）；None=按自动画像",
    )
    size_rule: Optional[str] = Field(
        default=None,
        description="尺寸归一化规则名，如 seedream（合法总像素 [2K,4K]，越界按宽高比映射 2K 推荐档）；None=原样透传",
    )
    image_sizes: Optional[List[ImageSizeOption]] = Field(
        default=None,
        description="覆盖该模型的尺寸选项（结构化同全局 IMAGE_SIZE_OPTIONS）；None=用全局",
    )
    default_size: Optional[str] = Field(
        default=None,
        description="覆盖该模型的默认尺寸；None=用全局默认",
    )


class ModelInfo(BaseModel):
    """单个模型信息"""
    id: str = Field(description="模型标识，如 agnes-image-2.1-flash")
    name: str = Field(description="模型显示名称，如 Agnes Image 2.1 Flash")
    type: str = Field(description="模型类型：image / video / chat")
    provider: str = Field(default="Unknown", description="模型供应商，如 Agnes / 字节跳动 / OpenAI")
    capabilities: List[str] = Field(
        default_factory=list,
        description="模型能力标签，如 text2image, image2image, text2video, image2video, keyframes",
    )
    gen_params: Optional[ModelGenParams] = Field(
        default=None,
        description="生成能力配置（None=无特例，按模型名自动画像）",
    )


class VideoAspectRatioOption(BaseModel):
    """视频宽高比选项"""
    value: str = Field(description="传给 API 的比例值，如 16:9")
    w: int = Field(description="宽高比宽分量")
    h: int = Field(description="宽高比高分量")
    label: str = Field(description="显示标签，如 16:9 横屏")


class VideoResolutionOption(BaseModel):
    """视频分辨率选项（以高度为基准，宽度按比例计算）"""
    value: int = Field(description="高度像素值，如 768")
    label: str = Field(description="显示标签，如 720p 高清")
    width_16_9: int = Field(description="16:9 下的参考宽度")


class WatermarkConfigPublic(BaseModel):
    """公开的水印配置（前端 CSS 水印用，不含敏感信息）"""
    enabled: bool = Field(description="是否启用水印（全局强制 或 对当前用户启用）")
    type: str = Field(default="text", description="水印类型：text / image")
    text: str = Field(default="Agnes AI", description="文字水印内容")
    font_size: int = Field(default=24, description="字体大小")
    color: str = Field(default="#FFFFFF", description="字体颜色（十六进制）")
    opacity: int = Field(default=50, description="透明度（0-100）")
    position: str = Field(default="bottom-right", description="位置：top-left / top-right / bottom-left / bottom-right / center")
    margin: int = Field(default=20, description="边距（像素）")
    image_url: Optional[str] = Field(default=None, description="图片水印 URL")
    image_width: int = Field(default=120, description="图片水印宽度")


class ConfigResponse(BaseModel):
    """前端可用配置（不含敏感信息）"""

    # 可用模型列表（结构化，按类型自动分类）
    models: List[ModelInfo] = Field(
        default_factory=list,
        description="所有可用模型列表",
    )

    # 图片尺寸选项（结构化，含比例信息）
    image_sizes: List[str] = Field(
        default=["1024x768", "1024x1024", "768x1024", "512x512"],
        description="支持的图片尺寸选项（兼容旧版）",
    )
    image_size_options: List[ImageSizeOption] = Field(
        default_factory=list,
        description="图片尺寸选项（结构化，含比例和标签）",
    )
    default_image_size: str = Field(
        default="1280x720",
        description="默认图片尺寸",
    )

    # 视频宽高比选项
    video_aspect_ratios: List[VideoAspectRatioOption] = Field(
        default_factory=list,
        description="视频宽高比选项",
    )
    default_video_aspect_ratio: str = Field(
        default="16:9",
        description="默认视频宽高比",
    )

    # 视频分辨率选项
    video_resolutions: List[VideoResolutionOption] = Field(
        default_factory=list,
        description="视频分辨率选项（以高度为基准）",
    )
    default_video_resolution: int = Field(
        default=768,
        description="默认视频分辨率高度",
    )

    # 视频帧数选项（需满足 8n+1 规则）
    video_num_frames: List[int] = Field(
        default=[9, 33, 49, 81, 121, 161, 241, 441],
        description="支持的视频帧数选项（需满足 8n+1）",
    )

    # 视频时长选项（秒）
    # 官方 Q&A 限制：FPS 与时长联动：
    #   24 FPS 不超过 15s；30 FPS 不超过 10s；60 FPS 不超过 5s
    video_durations: List[int] = Field(
        default=[3, 5, 7, 10, 15],
        description="视频时长选项（秒），前端会按 FPS 联动过滤",
    )
    default_video_duration: int = Field(
        default=5,
        description="默认视频时长（秒）",
    )

    # 视频帧率选项
    video_frame_rates: List[int] = Field(
        default=[24, 30, 60],
        description="视频帧率选项（FPS）",
    )
    default_frame_rate: int = 24

    # 默认分辨率
    default_video_width: int = 1152
    default_video_height: int = 768

    # 上传限制
    max_upload_size_mb: int = 10

    # 水印配置（公开，前端 CSS 水印用）
    watermark: Optional[WatermarkConfigPublic] = None


# =====================================================
# 历史记录相关 Schema
# =====================================================

class GenerationContext(BaseModel):
    """
    创作上下文（生成任务可选携带，用于历史瘦身与资产归档）

    - source：independent（生图页/生视频页/聊天）/ canvas（画布）/ project（项目制）
    - container_type/container_id：创作容器，如 ('canvas_script', 剧本面板 ID) /
      ('project', 项目 ID)。两者同时存在才触发自动归档，独立生成不传
    - container_name：容器名快照（剧本/项目改名或删除后，归档记录仍可正常分组显示）
    - asset_type：归档后的资产类型（material / clip / character / scene / final …）
    - asset_name：归档后的资产名（分镜序号 / 角色名 / 节点名 …）
    """
    source: str = Field(default="independent", description="来源：independent / canvas / project")
    container_type: Optional[str] = Field(default=None, description="容器类型：project / canvas_script / canvas")
    container_id: Optional[str] = Field(default=None, description="容器 ID（项目 ID / 剧本面板 ID / 'canvas'）")
    container_name: Optional[str] = Field(default=None, description="容器名快照")
    asset_type: Optional[str] = Field(default=None, description="归档资产类型：material / clip / character / scene / final")
    asset_name: Optional[str] = Field(default=None, description="归档资产名")

    @field_validator("source")
    @classmethod
    def validate_source(cls, v):
        return v if v in ("independent", "canvas", "project") else "independent"

    @field_validator("container_type")
    @classmethod
    def validate_container_type(cls, v):
        return v if v in ("project", "canvas_script", "canvas") else None


class GenerationRecord(BaseModel):
    """生成记录响应体"""
    id: int
    type: str                      # 'image' | 'video'
    prompt: str
    model: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    mode: Optional[str] = None     # 'text2image' | 'image2image' | 'text2video' | 'image2video' | 'keyframes'
    result_url: Optional[str] = None
    status: str
    task_id: Optional[str] = None
    credits_consumed: int = 0       # 本次任务消耗的积分数（与积分流水 ref_id 对应）
    is_public: bool = False         # 是否公开到广场
    likes_count: int = 0            # 点赞数
    created_at: Optional[datetime] = None
    # 内容审核相关
    moderation_status: Optional[str] = None   # approved / pending / rejected
    moderation_reason: Optional[str] = None   # 审核原因
    moderation_flags: Optional[List[str]] = None  # 命中的敏感词/违规类别
    # 创作归属（历史瘦身：画布/项目生成不进默认历史，可按来源筛选回看）
    source: str = "independent"                # independent / canvas / project
    container_type: Optional[str] = None       # project / canvas_script / canvas
    container_id: Optional[str] = None

    class Config:
        from_attributes = True    # Pydantic v2 对应原来的 orm_mode


class HistoryListResponse(BaseModel):
    """历史列表响应体（支持分页 + 各类型全局计数）"""
    total: int                                          # 当前筛选条件下的总记录数
    page: int
    page_size: int
    items: List[GenerationRecord]
    total_image_count: int = 0                           # 图片记录全局总数（不受筛选影响）
    total_video_count: int = 0                           # 视频记录全局总数（不受筛选影响）


class DeleteResponse(BaseModel):
    """删除操作响应"""
    success: bool
    message: str


# =====================================================
# 批量删除相关 Schema
# =====================================================

class BatchDeleteRequest(BaseModel):
    """批量删除请求体（接收记录 ID 列表）"""
    ids: List[int] = Field(..., description="要删除的记录 ID 列表")


class BatchDeleteResponse(BaseModel):
    """批量删除操作响应"""
    success: bool
    message: str
    deleted_count: int = Field(description="实际成功删除的记录数量")
    failed_ids: List[int] = Field(default_factory=list, description="删除失败的记录 ID 列表")
