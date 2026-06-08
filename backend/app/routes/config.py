# =====================================================
# 配置接口路由
# 返回前端可用的非敏感配置（不含 API Key）
# =====================================================

from fastapi import APIRouter
from app.core.config import settings
from app.schemas.common import ConfigResponse

router = APIRouter()


@router.get("/config", response_model=ConfigResponse, summary="获取前端配置")
async def get_config():
    """
    返回前端需要的非敏感配置：
    - 支持的图片尺寸
    - 可用的模型名称
    - 视频帧数选项
    - 上传大小限制

    注意：不会返回 API Key 或任何敏感信息。
    """
    return ConfigResponse(
        image_sizes=["1024x768", "1024x1024", "768x1024", "512x512"],
        image_models=["agnes-image-2.1-flash"],
        video_models=["agnes-video-v2.0"],
        video_num_frames=[9, 33, 49, 81, 121, 161, 241, 441],
        default_frame_rate=24,
        default_video_width=1152,
        default_video_height=768,
        max_upload_size_mb=settings.max_upload_size_mb,
    )
