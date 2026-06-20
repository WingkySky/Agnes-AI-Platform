# =====================================================
# 配置接口路由
# 返回前端可用的非敏感配置（不含 API Key）
# 模型列表从数据库 model_definitions 表读取（由 provider_registry 管理）
# =====================================================

from fastapi import APIRouter
from app.core.config import settings
from app.schemas.common import ConfigResponse, ImageSizeOption, VideoAspectRatioOption
from app.services.model_registry import get_all_models

router = APIRouter()

# 图片尺寸预设（匹配 Agnes Image 2.0/2.1 Flash 文档）
IMAGE_SIZE_OPTIONS = [
    ImageSizeOption(value="1280x720",  w=16, h=9,  label="16:9 横屏"),
    ImageSizeOption(value="1024x768",  w=4,  h=3,  label="4:3 横屏"),
    ImageSizeOption(value="1536x1024", w=3,  h=2,  label="3:2 横屏"),
    ImageSizeOption(value="1792x1024", w=7,  h=4,  label="7:4 宽幅"),
    ImageSizeOption(value="1024x1024", w=1,  h=1,  label="1:1 方形"),
    ImageSizeOption(value="1024x1536", w=2,  h=3,  label="2:3 竖屏"),
    ImageSizeOption(value="720x1280",  w=9,  h=16, label="9:16 竖屏"),
    ImageSizeOption(value="1024x1792", w=4,  h=7,  label="4:7 窄幅"),
]

# 视频宽高比预设（匹配 Agnes Video V2.0 文档）
VIDEO_ASPECT_RATIO_OPTIONS = [
    VideoAspectRatioOption(value="16:9", w=16, h=9,  label="16:9 横屏"),
    VideoAspectRatioOption(value="4:3",  w=4,  h=3,  label="4:3 横屏"),
    VideoAspectRatioOption(value="1:1",  w=1,  h=1,  label="1:1 方形"),
    VideoAspectRatioOption(value="3:4",  w=3,  h=4,  label="3:4 竖屏"),
    VideoAspectRatioOption(value="9:16", w=9,  h=16, label="9:16 竖屏"),
]


@router.get("/config", response_model=ConfigResponse, summary="获取前端配置")
async def get_config():
    """
    返回前端需要的非敏感配置：
    - 可用模型列表（从数据库 model_definitions 表读取，由 provider_registry 管理）
    - 图片尺寸选项（结构化，含比例信息）
    - 视频宽高比、时长、帧率选项
    - 上传大小限制

    模型列表来源：Provider 的 /models API 同步 + 用户自定义模型。
    管理入口：前端配置页 /api/providers/* 和 /api/models/* 接口。
    """
    return ConfigResponse(
        models=await get_all_models(),
        # 图片尺寸（兼容旧版 + 结构化新版）
        image_sizes=[opt.value for opt in IMAGE_SIZE_OPTIONS],
        image_size_options=IMAGE_SIZE_OPTIONS,
        default_image_size="1280x720",
        # 视频参数
        video_aspect_ratios=VIDEO_ASPECT_RATIO_OPTIONS,
        default_video_aspect_ratio="16:9",
        video_num_frames=[9, 33, 49, 81, 121, 161, 241, 441],
        video_durations=[3, 5, 7, 10, 15],
        default_video_duration=5,
        video_frame_rates=[24, 30],
        default_frame_rate=24,
        default_video_width=1152,
        default_video_height=768,
        max_upload_size_mb=settings.max_upload_size_mb,
    )
