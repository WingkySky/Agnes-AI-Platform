# =====================================================
# 配置接口路由
# 返回前端可用的非敏感配置（不含 API Key）
# 模型列表从环境变量动态读取，自动识别类型和供应商
# =====================================================

from fastapi import APIRouter
from app.core.config import settings
from app.schemas.common import ConfigResponse
from app.services.model_registry import get_all_models

router = APIRouter()


@router.get("/config", response_model=ConfigResponse, summary="获取前端配置")
async def get_config():
    """
    返回前端需要的非敏感配置：
    - 可用模型列表（从 API 动态获取，自动识别类型/供应商/能力）
    - 支持的图片尺寸
    - 视频帧数选项
    - 上传大小限制

    模型列表来源优先级：API GET /models > 环境变量 AVAILABLE_MODELS
    自动推断不准时：在 .env 的 MODEL_OVERRIDES 中手动指定。
    """
    return ConfigResponse(
        models=await get_all_models(),
        image_sizes=["1024x768", "1024x1024", "768x1024", "512x512"],
        video_num_frames=[9, 33, 49, 81, 121, 161, 241, 441],
        default_frame_rate=24,
        default_video_width=1152,
        default_video_height=768,
        max_upload_size_mb=settings.max_upload_size_mb,
    )
