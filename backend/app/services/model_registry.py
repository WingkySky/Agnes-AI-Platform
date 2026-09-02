# =====================================================
# 模型注册表（兼容层）
# 多 Provider 管理、模型列表、模型同步的实现在 services/provider_registry.py，
# 本文件仅转发查询函数并提供对话模型解析链。
# =====================================================

from typing import List

from app.schemas.common import ModelInfo


# =====================================================
# 兼容层：转发到 provider_registry
# =====================================================

async def get_all_models() -> List[ModelInfo]:
    """获取所有可用模型（带缓存）。实际由 provider_registry.list_all_models() 提供。"""
    from app.services.provider_registry import provider_registry
    return await provider_registry.list_all_models()


async def get_models_by_type(model_type: str) -> List[ModelInfo]:
    """按类型筛选模型（转发到 provider_registry）"""
    from app.services.provider_registry import provider_registry
    return await provider_registry.list_models_by_type(model_type)


# =====================================================
# 对话模型解析链（消除硬编码，支持模型随时切换）
# - 创作类：显式指定 > 用户偏好 default_chat_model_id > 系统默认 > 第一个 chat 模型
# - 系统类：管理员配置项 > 系统默认 > 第一个 chat 模型
# =====================================================

# 系统级对话模型配置项（system_configs 表，管理员后台可改）
SYSTEM_CHAT_MODEL_KEYS = {
    "chat_default": "model.chat_default",        # 系统默认对话模型（用户未设置偏好时的兜底）
    "moderation": "model.moderation_chat",       # 内容审核模型
    "title_summary": "model.title_summary_chat",  # 会话标题总结模型
}


async def get_first_chat_model_id() -> str:
    """注册表中第一个 chat 模型 ID（无则返回空串）"""
    models = await get_models_by_type("chat")
    return models[0].id if models else ""


async def _valid_chat_model_ids() -> set:
    """当前注册表中可用的 chat 模型 ID 集合（已停用/已下线的模型不在其中）"""
    return {m.id for m in await get_models_by_type("chat")}


async def _system_default_chat_model_id(db) -> str:
    """系统默认对话模型：model.chat_default（管理员配置，须仍有效）> 第一个 chat 模型"""
    from app.services.system_config_service import get_config_value
    configured = (await get_config_value(db, SYSTEM_CHAT_MODEL_KEYS["chat_default"], "") or "").strip()
    if configured and configured in await _valid_chat_model_ids():
        return configured
    return await get_first_chat_model_id()


async def resolve_user_chat_model_id(db, user_id: int, explicit: str = "") -> str:
    """
    创作类对话模型解析：显式指定 > 用户偏好 > 系统默认 > 第一个 chat 模型。
    user_id<=0 时跳过用户偏好（匿名/系统上下文）。
    每一级都会校验模型仍在注册表中（被停用/下线/改名的模型自动落到下一级，
    避免把失效模型名发往上游）。
    """
    valid = await _valid_chat_model_ids()
    if explicit and explicit in valid:
        return explicit
    if user_id:
        from sqlalchemy.future import select
        from app.models.user_preference import UserPreference
        result = await db.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        pref = result.scalars().first()
        preferred = ((pref.preferences or {}).get("generation", {}).get("default_chat_model_id", "") if pref else "")
        preferred = (preferred or "").strip()
        if preferred and preferred in valid:
            return preferred
    return await _system_default_chat_model_id(db)


async def resolve_project_chat_model_id(db, project_id: int, explicit: str = "") -> str:
    """按项目解析创作类对话模型（使用项目所有者的用户偏好，免去各调用点透传 user_id）"""
    if explicit:
        return explicit
    from sqlalchemy.future import select
    from app.models.project import Project
    result = await db.execute(select(Project.user_id).where(Project.id == project_id))
    row = result.first()
    owner_id = row[0] if row else 0
    return await resolve_user_chat_model_id(db, owner_id)


async def resolve_system_chat_model_id(db, key: str) -> str:
    """
    系统级对话模型解析（审核 / 标题总结等）：指定配置项 > 系统默认 > 第一个 chat 模型。
    db 传 None 时自动开短连接（后台任务场景）。
    """
    from app.core.database import new_async_session
    if db is None:
        async with new_async_session() as session:
            return await resolve_system_chat_model_id(session, key)
    from app.services.system_config_service import get_config_value
    configured = (await get_config_value(db, key, "") or "").strip()
    if configured and configured in await _valid_chat_model_ids():
        return configured
    return await _system_default_chat_model_id(db)
