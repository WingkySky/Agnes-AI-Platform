# =====================================================
# 模型能力合同层（capability_service）
#
# 把「模型能做什么」收敛为单一解析入口，三级优先：
#   1. DB gen_params 显式配置（逐键覆盖）
#   2. 按模型名自动画像（detect_model_profile）
#   3. 默认兜底（全默认 ModelGenParams，由调用方 get_model_gen_params 保证）
#
# 纯函数层：不访问数据库、不持有连接；DB/缓存编排在 provider_registry。
# 新增画像 = 在 detect_model_profile 追加一条分支；模型特例数据化后不改生成代码。
# =====================================================

from typing import Optional

import logging

from app.schemas.common import ModelGenParams

logger = logging.getLogger("agnes_platform")


def detect_model_profile(model_id: str) -> Optional[ModelGenParams]:
    """
    根据模型 ID 推断生成能力画像（同族模型开箱即用；DB gen_params 显式配置优先于此推断）。
    """
    lower = (model_id or "").lower()
    if "seedream" in lower:
        # 火山 Seedream 系：官方 watermark 参数可关「AI生成」显式水印；尺寸需归一化到合法档（≥2K）
        return ModelGenParams(watermark_param_off=True, size_rule="seedream")
    if lower.startswith("agnes-image-2"):
        # Agnes Image 2.x 家族（2.1/2.5 实测一致）：上游参考图上限 6 张，超出返回
        # HTTP 400 "too many input images: N provided, at most 6 allowed"（官方文档均未标注该限制）
        return ModelGenParams(max_ref_images=6)
    return None


def resolve_capabilities(model_id: str, explicit: Optional[dict]) -> Optional[ModelGenParams]:
    """
    合并生成能力配置：DB 显式配置（gen_params 列）逐键覆盖自动画像，未设置的键（None）沿用画像；
    显式配置非法时整体忽略（回退画像）。
    """
    profile = detect_model_profile(model_id)
    if not explicit:
        return profile
    try:
        explicit_params = ModelGenParams(**explicit)
    except Exception as e:
        logger.warning("[Capability] 模型 %s 的 gen_params 配置无效，已忽略: %s", model_id, e)
        return profile
    if profile is None:
        return explicit_params
    merged = {**profile.model_dump(), **explicit_params.model_dump(exclude_none=True)}
    return ModelGenParams(**merged)
