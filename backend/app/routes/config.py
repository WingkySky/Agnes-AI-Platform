# =====================================================
# 配置接口路由
# 返回前端可用的非敏感配置（不含 API Key）
# 模型列表从数据库 model_definitions 表读取（由 provider_registry 管理）
# =====================================================

from fastapi import APIRouter, Depends
from app.core.config import settings
from app.schemas.common import ConfigResponse, ImageSizeOption, VideoAspectRatioOption, VideoResolutionOption, WatermarkConfigPublic
from app.services.model_registry import get_all_models
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_db

router = APIRouter()

# 图片尺寸预设（基于 Agnes Image API 支持的尺寸配置）
# 按清晰度等级分组：sd=标清 / hd=超清 / 4k=4K
# 宽高使用 16 的倍数对齐，保证编码兼容
IMAGE_SIZE_OPTIONS = [
    # 标清档 (~1MP, 耗时 ~20s) - 完整比例覆盖
    ImageSizeOption(value="1024x1024", w=1,  h=1,  label="1:1 方形",  tier="sd", pixels=1048576),
    ImageSizeOption(value="1280x720",  w=16, h=9,  label="16:9 横屏", tier="sd", pixels=921600),
    ImageSizeOption(value="720x1280",  w=9,  h=16, label="9:16 竖屏", tier="sd", pixels=921600),
    ImageSizeOption(value="1216x832",  w=3,  h=2,  label="3:2 横屏",  tier="sd", pixels=1011712),
    ImageSizeOption(value="832x1216",  w=2,  h=3,  label="2:3 竖屏",  tier="sd", pixels=1011712),
    ImageSizeOption(value="1152x864",  w=4,  h=3,  label="4:3 横屏",  tier="sd", pixels=995328),
    ImageSizeOption(value="864x1152",  w=3,  h=4,  label="3:4 竖屏",  tier="sd", pixels=995328),
    # 超清档 (2-4MP, 耗时 ~56s) - 完整比例覆盖
    ImageSizeOption(value="2048x2048", w=1,  h=1,  label="1:1 方形",  tier="hd", pixels=4194304),
    ImageSizeOption(value="2304x1296", w=16, h=9,  label="16:9 横屏", tier="hd", pixels=2985984),
    ImageSizeOption(value="1296x2304", w=9,  h=16, label="9:16 竖屏", tier="hd", pixels=2985984),
    ImageSizeOption(value="2176x1456", w=3,  h=2,  label="3:2 横屏",  tier="hd", pixels=3168256),
    ImageSizeOption(value="1456x2176", w=2,  h=3,  label="2:3 竖屏",  tier="hd", pixels=3168256),
    ImageSizeOption(value="2048x1536", w=4,  h=3,  label="4:3 横屏",  tier="hd", pixels=3145728),
    ImageSizeOption(value="1536x2048", w=3,  h=4,  label="3:4 竖屏",  tier="hd", pixels=3145728),
    # 4K 档 (8-16MP, 耗时 ~150s) - 完整比例覆盖
    ImageSizeOption(value="4096x4096", w=1,  h=1,  label="1:1 方形",  tier="4k", pixels=16777216),
    ImageSizeOption(value="3840x2160", w=16, h=9,  label="16:9 横屏", tier="4k", pixels=8294400),
    ImageSizeOption(value="2160x3840", w=9,  h=16, label="9:16 竖屏", tier="4k", pixels=8294400),
    ImageSizeOption(value="3840x2560", w=3,  h=2,  label="3:2 横屏",  tier="4k", pixels=9830400),
    ImageSizeOption(value="2560x3840", w=2,  h=3,  label="2:3 竖屏",  tier="4k", pixels=9830400),
    ImageSizeOption(value="3648x2736", w=4,  h=3,  label="4:3 横屏",  tier="4k", pixels=9980928),
    ImageSizeOption(value="2736x3648", w=3,  h=4,  label="3:4 竖屏",  tier="4k", pixels=9980928),
]

# 视频宽高比预设（匹配 Agnes Video V2.0 文档）
VIDEO_ASPECT_RATIO_OPTIONS = [
    VideoAspectRatioOption(value="16:9", w=16, h=9,  label="16:9 横屏"),
    VideoAspectRatioOption(value="4:3",  w=4,  h=3,  label="4:3 横屏"),
    VideoAspectRatioOption(value="1:1",  w=1,  h=1,  label="1:1 方形"),
    VideoAspectRatioOption(value="3:4",  w=3,  h=4,  label="3:4 竖屏"),
    VideoAspectRatioOption(value="9:16", w=9,  h=16, label="9:16 竖屏"),
]

# 视频分辨率预设（以高度为基准，16:9 宽度作为参考）
# 注意：宽高会自动对齐到 8 的倍数（视频编码硬性要求）
VIDEO_RESOLUTION_OPTIONS = [
    VideoResolutionOption(value=480,  label="480p 流畅", width_16_9=856),
    VideoResolutionOption(value=720,  label="720p 高清", width_16_9=1280),
    VideoResolutionOption(value=1080, label="1080p 超清", width_16_9=1920),
    VideoResolutionOption(value=1440, label="2K 极致", width_16_9=2560),
    VideoResolutionOption(value=2160, label="4K 顶级", width_16_9=3840),
]


@router.get("/config", response_model=ConfigResponse, summary="获取前端配置")
async def get_config(db: AsyncSession = Depends(get_async_db)):
    """
    返回前端需要的非敏感配置：
    - 可用模型列表（从数据库 model_definitions 表读取，由 provider_registry 管理）
    - 图片尺寸选项（结构化，含比例信息）
    - 视频宽高比、时长、帧率选项
    - 上传大小限制
    - 水印配置（前端 CSS 水印用）

    模型列表来源：Provider 的 /models API 同步 + 用户自定义模型。
    管理入口：前端配置页 /api/providers/* 和 /api/models/* 接口。
    """
    # 获取水印配置
    watermark_config = None
    try:
        from app.services.watermark_service import get_watermark_config
        wm = await get_watermark_config(db)
        watermark_config = WatermarkConfigPublic(
            enabled=wm.force_all,  # 公开接口只返回全局强制状态，用户级开关在用户信息里
            type=wm.type,
            text=wm.text,
            font_size=wm.font_size,
            color=wm.color,
            opacity=wm.opacity,
            position=wm.position,
            margin=wm.margin,
            image_url=wm.image_url,
            image_width=wm.image_width,
        )
    except Exception as e:
        import logging
        logging.getLogger("agnes_platform").warning("[config] 获取水印配置失败: %s", e)

    return ConfigResponse(
        models=await get_all_models(),
        # 图片尺寸（兼容旧版 + 结构化新版）
        image_sizes=[opt.value for opt in IMAGE_SIZE_OPTIONS],
        image_size_options=IMAGE_SIZE_OPTIONS,
        default_image_size="1024x1024",
        # 视频参数
        video_aspect_ratios=VIDEO_ASPECT_RATIO_OPTIONS,
        default_video_aspect_ratio="16:9",
        # 视频分辨率
        video_resolutions=VIDEO_RESOLUTION_OPTIONS,
        default_video_resolution=720,
        # 视频时长/帧率
        # 官方 Q&A 限制：视频时间与帧率联动限制
        #   24 FPS 不超过 15s；30 FPS 不超过 10s；60 FPS 不超过 5s
        # 前端 ParamSelector 会按当前 FPS 过滤可选时长，这里给出全量候选项
        video_num_frames=[9, 33, 49, 81, 121, 161, 241, 441],
        video_durations=[3, 5, 7, 10, 15],
        default_video_duration=5,
        video_frame_rates=[24, 30, 60],
        default_frame_rate=24,
        default_video_width=1280,
        default_video_height=720,
        max_upload_size_mb=settings.max_upload_size_mb,
        watermark=watermark_config,
    )
