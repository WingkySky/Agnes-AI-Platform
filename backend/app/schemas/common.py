# =====================================================
# 通用 / 历史记录相关的 Pydantic Schema
# =====================================================

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    service: str


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


class VideoAspectRatioOption(BaseModel):
    """视频宽高比选项"""
    value: str = Field(description="传给 API 的比例值，如 16:9")
    w: int = Field(description="宽高比宽分量")
    h: int = Field(description="宽高比高分量")
    label: str = Field(description="显示标签，如 16:9 横屏")


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


# =====================================================
# 历史记录相关 Schema
# =====================================================

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
