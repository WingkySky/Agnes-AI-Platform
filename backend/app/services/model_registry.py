# =====================================================
# 模型注册表
# 从 API 动态获取可用模型列表，自动推断类型/供应商/能力
# 支持手动覆盖（MODEL_OVERRIDES 环境变量）
# =====================================================

import time
import logging
from typing import Dict, Any, List, Optional

from app.core.config import settings
from app.schemas.common import ModelInfo

logger = logging.getLogger("agnes_platform")

# ---------- 自动推断规则 ----------

# 模型类型推断关键词（按优先级匹配，命中即返回）
_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "image": ["image", "flux", "sd3", "sdxl", "dall", "seedream", "wanx", "ideogram", "midjourney"],
    "video": ["video", "veo", "seedance", "cogvideox", "wan", "kling", "runway", "pika", "luma"],
    # 未命中以上关键词的默认归为 chat
}

# 供应商推断规则（前缀匹配）
_PROVIDER_PREFIXES: Dict[str, str] = {
    "agnes-": "Agnes",
    "doubao-": "字节跳动",
    "qwen-": "阿里云",
    "gpt-": "OpenAI",
    "gemini-": "Google",
    "claude-": "Anthropic",
    "deepseek-": "DeepSeek",
    "glm-": "智谱AI",
}

# 模型能力推断（根据 type 自动赋予默认能力）
_DEFAULT_CAPABILITIES: Dict[str, List[str]] = {
    "image": ["text2image", "image2image"],
    "video": ["text2video", "image2video", "keyframes"],
    "chat": ["text"],
}

# ---------- 缓存 ----------

# 模型列表缓存（避免每次请求都调 API）
_cached_models: Optional[List[ModelInfo]] = None
_cache_time: float = 0
_CACHE_TTL = 300  # 缓存有效期 5 分钟


def _detect_type(model_id: str) -> str:
    """根据模型 ID 中的关键词推断类型（image / video / chat）"""
    lower = model_id.lower()
    for type_name, keywords in _TYPE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return type_name
    return "chat"


def _detect_provider(model_id: str) -> str:
    """根据模型 ID 前缀推断供应商"""
    lower = model_id.lower()
    for prefix, provider in _PROVIDER_PREFIXES.items():
        if lower.startswith(prefix):
            return provider
    return "Unknown"


def _detect_capabilities(model_id: str, model_type: str) -> List[str]:
    """根据类型推断默认能力列表"""
    return list(_DEFAULT_CAPABILITIES.get(model_type, []))


def _generate_display_name(model_id: str, provider: str, model_type: str) -> str:
    """根据模型 ID 生成可读的显示名称（保留版本号中的点号）"""
    name = model_id
    for prefix in _PROVIDER_PREFIXES:
        if name.lower().startswith(prefix):
            name = name[len(prefix):]
            break
    # 先保护版本号中的点号（如 2.1 → 2⑴），替换后再恢复
    import re
    # 将数字.数字模式中的点号临时替换
    protected = re.sub(r'(\d)\.(\d)', r'\1⑴\2', name)
    protected = protected.replace("-", " ").replace(".", " ").title()
    # 恢复版本号点号
    result = protected.replace("⑴", ".")
    return f"{provider} {result}" if provider != "Unknown" else result


def build_model_info(model_id: str, overrides: Optional[Dict[str, Any]] = None) -> ModelInfo:
    """
    根据模型 ID 构建完整的 ModelInfo
    - 自动推断 type / provider / capabilities / name
    - overrides 中的字段会覆盖自动推断结果
    """
    detected_type = _detect_type(model_id)
    provider = _detect_provider(model_id)
    capabilities = _detect_capabilities(model_id, detected_type)
    name = _generate_display_name(model_id, provider, detected_type)

    # 应用手动覆盖
    if overrides:
        if "type" in overrides:
            detected_type = overrides["type"]
            if "capabilities" not in overrides:
                capabilities = _detect_capabilities(model_id, detected_type)
        if "name" in overrides:
            name = overrides["name"]
        if "capabilities" in overrides:
            capabilities = overrides["capabilities"]
        if "provider" in overrides:
            provider = overrides["provider"]

    return ModelInfo(
        id=model_id,
        name=name,
        type=detected_type,
        provider=provider,
        capabilities=capabilities,
    )


async def fetch_models_from_api() -> List[str]:
    """
    从 API 动态获取可用模型 ID 列表
    - 优先从 API 获取（GET /models）
    - API 不可用时回退到环境变量 AVAILABLE_MODELS
    """
    try:
        from app.services.agnes_client import agnes_client
        raw_models = await agnes_client.list_models()
        if raw_models:
            model_ids = [m.get("id", "") for m in raw_models if m.get("id")]
            logger.info("[模型注册表] 从 API 获取到 %d 个模型", len(model_ids))
            return model_ids
    except Exception as e:
        logger.warning("[模型注册表] 从 API 获取模型列表失败，回退到环境变量: %s", e)

    # 回退：从环境变量读取
    fallback = settings.model_id_list
    if fallback:
        logger.info("[模型注册表] 使用环境变量中的 %d 个模型", len(fallback))
    return fallback


async def get_all_models() -> List[ModelInfo]:
    """
    获取所有可用模型（带缓存）
    - 缓存有效期 5 分钟，过期后重新从 API 拉取
    - API 不可用时回退到环境变量
    """
    global _cached_models, _cache_time

    now = time.time()
    if _cached_models is not None and (now - _cache_time) < _CACHE_TTL:
        return _cached_models

    model_ids = await fetch_models_from_api()
    overrides = settings.model_overrides_dict

    result = []
    for mid in model_ids:
        model_overrides = overrides.get(mid, {})
        result.append(build_model_info(mid, model_overrides))

    _cached_models = result
    _cache_time = now
    logger.info("[模型注册表] 模型列表已更新，共 %d 个模型", len(result))
    return result


async def get_models_by_type(model_type: str) -> List[ModelInfo]:
    """按类型筛选模型"""
    all_models = await get_all_models()
    return [m for m in all_models if m.type == model_type]


def invalidate_cache():
    """手动清除缓存（用于配置变更后强制刷新）"""
    global _cached_models, _cache_time
    _cached_models = None
    _cache_time = 0
