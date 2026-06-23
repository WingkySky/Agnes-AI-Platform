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

# 图片尺寸预设（基于 Agnes Image 2.0/2.1 Flash 实测真实输出尺寸）
# 按清晰度等级分组：sd=标清 / hd=超清 / 4k=4K
# 实测发现：非标准尺寸会被 Agnes 自动降级到 ~1MP 标清档，故只保留真实输出尺寸
IMAGE_SIZE_OPTIONS = [
    # 标清档 (~1MP, 耗时 ~20s)
    ImageSizeOption(value="1024x1024", w=1,  h=1,  label="1:1 方形",  tier="sd", pixels=1048576),
    ImageSizeOption(value="1312x736",  w=16, h=9,  label="16:9 横屏", tier="sd", pixels=965632),
    ImageSizeOption(value="1248x832",  w=3,  h=2,  label="3:2 横屏",  tier="sd", pixels=1038336),
    ImageSizeOption(value="832x1248",  w=2,  h=3,  label="2:3 竖屏",  tier="sd", pixels=1038336),
    # 超清档 (2048x2048, 4MP, 耗时 ~56s)
    ImageSizeOption(value="2048x2048", w=1,  h=1,  label="1:1 方形",  tier="hd", pixels=4194304),
    # 4K 档 (~8MP, 耗时 ~150s)
    ImageSizeOption(value="3840x2160", w=16, h=9,  label="16:9 横屏", tier="4k", pixels=8294400),
    ImageSizeOption(value="4096x4096", w=1,  h=1,  label="1:1 方形",  tier="4k", pixels=16777216),
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
        default_image_size="1024x1024",
        # 视频参数
        video_aspect_ratios=VIDEO_ASPECT_RATIO_OPTIONS,
        default_video_aspect_ratio="16:9",
        # 视频时长/帧率
        # 官方 Q&A 限制：视频时间与帧率联动限制
        #   24 FPS 不超过 15s；30 FPS 不超过 10s；60 FPS 不超过 5s
        # 前端 ParamSelector 会按当前 FPS 过滤可选时长，这里给出全量候选项
        video_num_frames=[9, 33, 49, 81, 121, 161, 241, 441],
        video_durations=[3, 5, 7, 10, 15],
        default_video_duration=5,
        video_frame_rates=[24, 30, 60],
        default_frame_rate=24,
        default_video_width=1152,
        default_video_height=768,
        max_upload_size_mb=settings.max_upload_size_mb,
    )
