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
    - image2video: 图生视频，支持单张或多张参考图
      - 单张: image 字段（1张起始帧）
      - 多张: images 数组（2+ 张参考图，指导视频生成）
    - keyframes: 关键帧动画，额外提供 images 数组（最多2张：起始帧必填 + 结束帧可选）
    """

    prompt: str = Field(..., min_length=1, max_length=15000, description="提示词")
    negative_prompt: Optional[str] = Field(default=None, description="负向提示词")
    model: str = Field(default="", description="模型名称（前端从 /api/config 获取可用模型列表）")

    # 视频参数（推荐使用 aspect_ratio，让服务端自动计算宽高）
    # 直接给 aspect_ratio 优先级高于 width/height
    aspect_ratio: Optional[str] = Field(default="16:9", description="画面比例（如 16:9 / 9:16 / 1:1 / 4:3 / 3:4 / 3:2 / 2:3 / 21:9）")
    seconds: Optional[float] = Field(default=None, gt=0, description="视频时长（秒，可与 num_frames/frame_rate 二选一）")

    # 视频参数（若提供 aspect_ratio，则 width/height 由服务端根据 aspect_ratio 确定）
    num_frames: Optional[int] = Field(default=None, ge=9, le=441, description="帧数（需满足 8n+1）")
    frame_rate: Optional[int] = Field(default=None, ge=1, le=60, description="帧率 1-60")
    width: Optional[int] = Field(default=None, description="视频宽度")
    height: Optional[int] = Field(default=None, description="视频高度")

    # 参考图 / 多图 / 首尾帧
    mode: Optional[str] = Field(default="text2video", description="模式: text2video | image2video | keyframes")
    image: Optional[str] = Field(default=None, description="图生视频时的单张参考图（base64 或 URL）")
    images: Optional[List[str]] = Field(default=None, description="图生视频多图/关键帧模式时的图片列表")
    # MIME 类型（前端传递，用于构建正确的 Data URI 前缀，避免统一用 image/png 导致格式不匹配）
    image_mime_type: Optional[str] = Field(default=None, description="单张参考图的 MIME 类型（如 image/jpeg）")
    image_mime_types: Optional[List[str]] = Field(default=None, description="多张图片各图片的 MIME 类型列表")

    # 种子（可选）
    seed: Optional[int] = Field(default=None, description="随机种子，不传则由 API 自动生成")

    # ── 摄像机参数：拼接到 prompt 末尾 ──
    camera_params: Optional[dict] = Field(
        default=None,
        description="摄像机参数，含 enabled 子字段。enabled=True 时拼接到 prompt 末尾",
    )

    # ── 预设来源：用于追溯作品使用了哪个预设 ──
    preset_id: Optional[int] = Field(
        default=None,
        description="生成时使用的预设 ID（来自 PresetQuickPanel 选择），用于作品来源追溯",
    )

    # ── 广场分享：生成时可选择是否公开到广场 ──
    is_public: bool = Field(default=False, description="是否分享到广场")

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

    @field_validator("width", "height")
    @classmethod
    def validate_dimensions(cls, v):
        """校验视频宽高：范围 256-3840，且会被自动对齐到 8 的倍数"""
        if v is None:
            return v
        if v < 256 or v > 3840:
            raise ValueError("视频宽高需在 256-3840 之间")
        # 自动对齐到 8 的倍数（视频编码硬性要求）
        aligned = ((v + 7) // 8) * 8
        return aligned

    @model_validator(mode="after")
    def check_mode_requirements(self):
        """
        根据 mode 校验必填字段：
        - image2video: 必须有 image 或 images 字段（至少1张有效图片）
        - keyframes: 必须有 images 数组且至少 1 张有效图片（最多 2 张：起始帧+结束帧）
        """
        if self.mode == "image2video":
            # 过滤 images 中的空值
            if self.images:
                self.images = [img for img in self.images if img and isinstance(img, str) and img.strip()]
            has_single = self.image and isinstance(self.image, str) and self.image.strip()
            has_multi = self.images and len(self.images) >= 1
            if not has_single and not has_multi:
                raise ValueError("image2video 模式需提供参考图（image 或 images 字段不能为空）")
            # 如果同时传了 image 和 images，以 images 为准（把 image 放进 images 开头）
            if has_single and has_multi:
                self.images = [self.image] + [img for img in self.images if img != self.image]
                self.image = None
            # 如果只传了 image 单张，转成 images 数组方便统一处理
            if has_single and not has_multi:
                self.images = [self.image]
                self.image = None
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
    num_frames: Optional[int] = None            # Agnes Video V2.0 使用 aspect_ratio + seconds，此字段可选
    frame_rate: Optional[int] = None            # 同上
    width: Optional[int] = None                 # 同上
    height: Optional[int] = None                # 同上
    aspect_ratio: Optional[str] = None          # 画面比例（如 16:9）
    seconds: Optional[float] = None             # 视频时长（秒）
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
