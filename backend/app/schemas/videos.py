# =====================================================
# 视频生成相关的 Pydantic Schema
# =====================================================

from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, model_validator


class VideoGenerationRequest(BaseModel):
    """
    视频生成请求体

    模式说明:
    - text2video: 只需 prompt + 视频参数
    - image2video: 额外提供 image 字段（单张参考图，起始帧）
    - keyframes: 额外提供 images 数组（首尾帧，起始帧必填 + 结束帧可选，最多2张）
    """

    prompt: str = Field(..., min_length=1, max_length=2000, description="提示词")
    negative_prompt: Optional[str] = Field(default=None, description="负向提示词")
    model: str = Field(default="agnes-video-v2.0", description="模型名称")

    # 视频参数（推荐使用 aspect_ratio，让服务端自动计算宽高）
    # 直接给 aspect_ratio 优先级高于 width/height
    aspect_ratio: Optional[str] = Field(default="16:9", description="画面比例（如 16:9 / 9:16 / 1:1 / 4:3 / 3:4 / 3:2 / 2:3 / 21:9）")
    seconds: Optional[float] = Field(default=None, gt=0, description="视频时长（秒，可与 num_frames/frame_rate 二选一）")

    # 视频参数（若提供 aspect_ratio，则 width/height 由服务端根据 aspect_ratio 确定）
    num_frames: Optional[int] = Field(default=None, ge=9, le=441, description="帧数（需满足 8n+1）")
    frame_rate: Optional[int] = Field(default=None, ge=1, le=60, description="帧率 1-60")
    width: Optional[int] = Field(default=None, description="视频宽度")
    height: Optional[int] = Field(default=None, description="视频高度")

    # 参考图 / 首尾帧
    mode: Optional[str] = Field(default="text2video", description="模式: text2video | image2video | keyframes")
    image: Optional[str] = Field(default=None, description="图生视频时的参考图（base64 或 URL）")
    images: Optional[List[str]] = Field(default=None, description="首尾帧模式时的图片列表（最多2张：起始帧+结束帧）")
    # MIME 类型（前端传递，用于构建正确的 Data URI 前缀，避免统一用 image/png 导致格式不匹配）
    image_mime_type: Optional[str] = Field(default=None, description="image2video 参考图的 MIME 类型（如 image/jpeg）")
    image_mime_types: Optional[List[str]] = Field(default=None, description="keyframes 各图片的 MIME 类型列表")

    # 种子（可选）
    seed: Optional[int] = Field(default=None, description="随机种子，不传则由 API 自动生成")

    @field_validator("prompt")
    @classmethod
    def prompt_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("prompt 不能为空")
        return v.strip()

    @field_validator("num_frames")
    @classmethod
    def validate_num_frames(cls, v):
        """
        帧数必须满足 8n+1 规则（Agnes Video API 要求）
        允许值：9, 17, 25, 33, 41, 49, 57, 65, 73, 81, ..., 441
        """
        if v is None:
            return v
        if (v - 1) % 8 != 0:
            raise ValueError(
                f"num_frames 需满足 8n+1 规则（当前值 {v} 不满足），"
                f"推荐值: 9, 33, 49, 81, 121, 161, 241, 441"
            )
        return v

    @model_validator(mode="after")
    def check_mode_requirements(self):
        """
        根据 mode 校验必填字段：
        - image2video 必须有 image 字段且非空
        - keyframes 必须有 images 数组且至少 1 张有效图片（最多 2 张：起始帧+结束帧）
        """
        if self.mode == "image2video":
            if not self.image or not self.image.strip():
                raise ValueError("image2video 模式需提供参考图（image 字段不能为空）")
        if self.mode == "keyframes":
            # 先过滤 images 中的空值/None/空字符串
            if self.images:
                self.images = [img for img in self.images if img and isinstance(img, str) and img.strip()]
            if not self.images or len(self.images) < 1:
                raise ValueError("keyframes 模式需提供至少 1 张起始帧图片（images 字段，过滤空值后无有效图片）")
            if len(self.images) > 2:
                raise ValueError("keyframes 模式最多提供 2 张图片（起始帧 + 结束帧）")
        return self


class VideoTaskCreatedResponse(BaseModel):
    """视频任务创建成功响应体"""
    task_id: Optional[str] = None              # Agnes AI 任务 ID（用于轮询）
    video_id: Optional[str] = None             # 如果 Agnes 直接返回了 video_id
    status: str = "pending"                     # pending / processing / success / failed / cancelled
    prompt: str
    model: str
    num_frames: int
    frame_rate: int
    width: int
    height: int
    mode: str
    message: Optional[str] = None


class VideoStatusResponse(BaseModel):
    """视频任务状态轮询响应体"""
    task_id: Optional[str] = None
    video_id: Optional[str] = None
    status: str                                 # pending / processing / success / failed / cancelled
    progress: int                               # 0-100，服务端估算的进度
    video_url: Optional[str] = None             # 生成成功时返回的视频 URL
    message: Optional[str] = None               # 状态信息或错误消息
    elapsed_sec: int = 0                        # 已耗时（秒）
