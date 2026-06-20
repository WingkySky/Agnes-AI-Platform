# =====================================================
# Provider 注册表（核心预处理层）
# 职责：
#   1. 管理多个 API Provider（不同 base_url / api_key 的 Agnes 兼容 API）
#   2. 为每个 Provider 维护独立的 AgnesAIClient 实例（连接池隔离）
#   3. 从数据库加载 Provider 配置和模型定义，支持运行时增删改
#   4. 调用 Provider 的 /models API 自动同步模型列表（保留用户自定义模型）
#   5. 启动时配置全局 agnes_client 单例指向默认 Provider（兼容现有代码）
#
# 数据流：
#   数据库 api_providers / model_definitions 表
#     ↓ 启动时加载
#   ProviderRegistry._clients: {provider_id: AgnesAIClient}
#   ProviderRegistry._models_cache: List[ModelInfo]
#     ↓ 全局单例兼容
#   agnes_client.configure(default_provider_config)
# =====================================================

import logging
import time
from typing import Dict, List, Optional, Any

from sqlalchemy import select, update, delete, and_

from app.core.config import settings
from app.core.database import new_async_session
from app.core.security import encrypt_api_key, decrypt_api_key
from app.models.api_provider import ApiProvider
from app.models.model_definition import ModelDefinition
from app.schemas.common import ModelInfo
from app.services.agnes_client import AgnesAIClient, agnes_client

logger = logging.getLogger("agnes_platform")

# ---------- 模型类型推断规则（与原 model_registry 保持一致） ----------

_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "image": ["image", "flux", "sd3", "sdxl", "dall", "seedream", "wanx", "ideogram", "midjourney"],
    "video": ["video", "veo", "seedance", "cogvideox", "wan", "kling", "runway", "pika", "luma"],
}

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

_DEFAULT_CAPABILITIES: Dict[str, List[str]] = {
    "image": ["text2image", "image2image"],
    "video": ["text2video", "image2video", "keyframes"],
    "chat": ["text"],
}


# ---------- 模型推断工具函数 ----------

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
    import re
    name = model_id
    for prefix in _PROVIDER_PREFIXES:
        if name.lower().startswith(prefix):
            name = name[len(prefix):]
            break
    # 先保护版本号中的点号（如 2.1 → 2⑴），替换后再恢复
    protected = re.sub(r'(\d)\.(\d)', r'\1⑴\2', name)
    protected = protected.replace("-", " ").replace(".", " ").title()
    result = protected.replace("⑴", ".")
    return f"{provider} {result}" if provider != "Unknown" else result


def _build_model_info_from_definition(defn: ModelDefinition) -> ModelInfo:
    """从 ModelDefinition ORM 对象构建 ModelInfo"""
    # 优先使用数据库中存储的 display_name / type，否则自动推断
    model_type = defn.type or _detect_type(defn.model_id)
    provider_name = defn.provider_name or _detect_provider(defn.model_id)
    display_name = defn.display_name or _generate_display_name(defn.model_id, provider_name, model_type)
    capabilities = defn.capabilities if defn.capabilities else _detect_capabilities(defn.model_id, model_type)
    return ModelInfo(
        id=defn.model_id,
        name=display_name,
        type=model_type,
        provider=provider_name,
        capabilities=capabilities,
    )


# =====================================================
# ProviderRegistry - 单例注册表
# =====================================================
class ProviderRegistry:
    """
    Provider 注册表单例。

    管理多个 API Provider 的 client 实例和模型列表缓存。
    启动时从数据库加载配置，运行时支持增删改 Provider 和模型。
    """

    def __init__(self):
        # {provider_id: AgnesAIClient} - 每个 Provider 一个独立 client
        self._clients: Dict[int, AgnesAIClient] = {}
        # 默认 Provider 的 ID（用于 agnes_client 单例兼容）
        self._default_provider_id: Optional[int] = None
        # 模型列表缓存（聚合所有 Provider 的 active 模型）
        self._models_cache: Optional[List[ModelInfo]] = None
        self._models_cache_time: float = 0
        self._models_cache_ttl: int = 300  # 5 分钟
        # 是否已初始化
        self._initialized: bool = False

    # ---------- 生命周期 ----------

    async def initialize(self) -> None:
        """
        应用启动时初始化：
        1. 从数据库加载所有 active Provider
        2. 若数据库为空，用 settings 引导配置创建默认 Provider
        3. 为每个 Provider 创建 AgnesAIClient 实例
        4. 用默认 Provider 配置全局 agnes_client 单例
        5. 加载模型列表缓存
        """
        if self._initialized:
            return

        logger.info("[ProviderRegistry] 开始初始化...")

        # 1) 加载所有 active Provider
        providers = await self._load_active_providers()

        # 2) 首次启动：数据库无 Provider 时用引导配置创建默认 Provider
        if not providers:
            providers = await self._create_default_provider_from_settings()

        # 3) 为每个 Provider 创建 client 实例
        for provider in providers:
            await self._init_client_for_provider(provider)

        # 4) 确定默认 Provider 并配置全局 agnes_client 单例
        await self._configure_default_client()

        # 5) 加载模型列表缓存
        await self.refresh_models_cache()

        self._initialized = True
        logger.info(
            "[ProviderRegistry] 初始化完成: %d 个 Provider, 默认 Provider ID=%s",
            len(self._clients), self._default_provider_id,
        )

    async def shutdown(self) -> None:
        """应用关闭时释放所有 client 连接池"""
        for provider_id, client in self._clients.items():
            try:
                await client.shutdown()
            except Exception as e:
                logger.warning("[ProviderRegistry] 关闭 Provider %s 的 client 失败: %s", provider_id, e)
        self._clients.clear()
        self._default_provider_id = None
        self._initialized = False

    # ---------- 数据库操作 ----------

    async def _load_active_providers(self) -> List[ApiProvider]:
        """从数据库加载所有 is_active=True 的 Provider，按 sort_order 排序"""
        async with new_async_session() as session:
            result = await session.execute(
                select(ApiProvider)
                .where(ApiProvider.is_active == True)
                .order_by(ApiProvider.sort_order, ApiProvider.id)
            )
            return list(result.scalars().all())

    async def _load_provider_by_id(self, provider_id: int) -> Optional[ApiProvider]:
        """根据 ID 加载单个 Provider"""
        async with new_async_session() as session:
            result = await session.execute(
                select(ApiProvider).where(ApiProvider.id == provider_id)
            )
            return result.scalars().first()

    async def _create_default_provider_from_settings(self) -> List[ApiProvider]:
        """
        首次启动时用 settings 中的引导配置创建默认 Provider。
        仅当 agnes_api_key 已配置时才创建。
        """
        if not settings.agnes_api_key:
            logger.warning("[ProviderRegistry] settings.agnes_api_key 为空，跳过默认 Provider 创建")
            return []

        logger.info("[ProviderRegistry] 数据库无 Provider，使用 settings 引导配置创建默认 Provider")
        async with new_async_session() as session:
            provider = ApiProvider(
                name="Agnes AI（默认）",
                base_url=settings.agnes_api_base_url,
                api_key_encrypted=encrypt_api_key(settings.agnes_api_key),
                poll_url=settings.agnes_api_poll_url,
                is_active=True,
                is_default=True,
                sort_order=0,
            )
            session.add(provider)
            await session.commit()
            await session.refresh(provider)
            logger.info("[ProviderRegistry] 默认 Provider 已创建: id=%s, name=%s", provider.id, provider.name)
            return [provider]

    async def _init_client_for_provider(self, provider: ApiProvider) -> None:
        """为指定 Provider 创建并启动 AgnesAIClient 实例"""
        decrypted_key = decrypt_api_key(provider.api_key_encrypted or "")
        client = AgnesAIClient(
            base_url=provider.base_url,
            api_key=decrypted_key,
            poll_url=provider.poll_url or "",
        )
        await client.start()
        self._clients[provider.id] = client
        logger.info(
            "[ProviderRegistry] Provider %s (id=%s) client 已启动: base_url=%s",
            provider.name, provider.id, provider.base_url,
        )

    async def _configure_default_client(self) -> None:
        """
        确定默认 Provider，用其配置全局 agnes_client 单例。
        优先选择 is_default=True 的 Provider，否则选第一个 active Provider。
        """
        if not self._clients:
            logger.warning("[ProviderRegistry] 无可用 Provider，agnes_client 单例保持引导配置")
            return

        # 查询默认 Provider
        async with new_async_session() as session:
            result = await session.execute(
                select(ApiProvider)
                .where(and_(ApiProvider.is_active == True, ApiProvider.is_default == True))
                .order_by(ApiProvider.sort_order)
                .limit(1)
            )
            default_provider = result.scalars().first()

        if default_provider is None:
            # 没有 is_default=True 的，取第一个
            async with new_async_session() as session:
                result = await session.execute(
                    select(ApiProvider)
                    .where(ApiProvider.is_active == True)
                    .order_by(ApiProvider.sort_order, ApiProvider.id)
                    .limit(1)
                )
                default_provider = result.scalars().first()

        if default_provider is None:
            logger.warning("[ProviderRegistry] 无法确定默认 Provider")
            return

        self._default_provider_id = default_provider.id
        decrypted_key = decrypt_api_key(default_provider.api_key_encrypted or "")
        # 配置全局 agnes_client 单例（兼容现有代码）
        agnes_client.configure(
            base_url=default_provider.base_url,
            api_key=decrypted_key,
            poll_url=default_provider.poll_url or "",
        )
        # 确保 agnes_client 的连接池已启动
        await agnes_client.start()
        logger.info(
            "[ProviderRegistry] 全局 agnes_client 单例已配置为默认 Provider: id=%s, name=%s",
            default_provider.id, default_provider.name,
        )

    # ---------- Client 获取 ----------

    def get_client(self, provider_id: Optional[int] = None) -> AgnesAIClient:
        """
        获取指定 Provider 的 client。
        provider_id 为 None 时返回默认 Provider 的 client（即全局 agnes_client 单例）。
        """
        if provider_id is None:
            return agnes_client
        client = self._clients.get(provider_id)
        if client is None:
            raise RuntimeError(f"Provider {provider_id} 不存在或未激活")
        return client

    def get_default_client(self) -> AgnesAIClient:
        """获取默认 Provider 的 client（即全局 agnes_client 单例）"""
        return agnes_client

    def list_provider_ids(self) -> List[int]:
        """列出所有已激活 Provider 的 ID"""
        return list(self._clients.keys())

    # ---------- 模型列表管理 ----------

    async def refresh_models_cache(self) -> List[ModelInfo]:
        """
        从数据库重新加载所有 active 模型到缓存。
        返回聚合后的模型列表（所有 Provider 的 active 模型）。
        """
        async with new_async_session() as session:
            result = await session.execute(
                select(ModelDefinition)
                .where(ModelDefinition.is_active == True)
                .order_by(ModelDefinition.sort_order, ModelDefinition.id)
            )
            definitions = list(result.scalars().all())

        self._models_cache = [_build_model_info_from_definition(d) for d in definitions]
        self._models_cache_time = time.time()
        logger.info("[ProviderRegistry] 模型缓存已刷新: %d 个模型", len(self._models_cache))
        return self._models_cache

    async def list_all_models(self, use_cache: bool = True) -> List[ModelInfo]:
        """
        获取所有可用模型（带缓存）。
        缓存过期或 use_cache=False 时从数据库重新加载。
        """
        if use_cache and self._models_cache is not None:
            if (time.time() - self._models_cache_time) < self._models_cache_ttl:
                return self._models_cache
        return await self.refresh_models_cache()

    async def list_models_by_type(self, model_type: str) -> List[ModelInfo]:
        """按类型筛选模型"""
        all_models = await self.list_all_models()
        return [m for m in all_models if m.type == model_type]

    async def get_model_definition(self, model_id: str) -> Optional[ModelDefinition]:
        """根据 model_id 查询模型定义（用于校验模型是否存在）"""
        async with new_async_session() as session:
            result = await session.execute(
                select(ModelDefinition).where(ModelDefinition.model_id == model_id)
            )
            return result.scalars().first()

    async def find_provider_for_model(self, model_id: str) -> Optional[ApiProvider]:
        """根据 model_id 查找其所属 Provider（用于路由请求到正确的 client）"""
        async with new_async_session() as session:
            result = await session.execute(
                select(ModelDefinition)
                .where(and_(ModelDefinition.model_id == model_id, ModelDefinition.is_active == True))
                .limit(1)
            )
            defn = result.scalars().first()
            if defn is None:
                return None
            result2 = await session.execute(
                select(ApiProvider).where(
                    and_(ApiProvider.id == defn.provider_id, ApiProvider.is_active == True)
                )
            )
            return result2.scalars().first()

    # ---------- Provider 同步模型（调用 /models API） ----------

    async def sync_provider_models(self, provider_id: int) -> Dict[str, Any]:
        """
        调用指定 Provider 的 /models API，同步模型列表到数据库。
        - 新增的模型自动添加（is_custom=False）
        - 已存在的 API 模型保持不变（用户可能修改过 display_name 等）
        - 用户自定义模型（is_custom=True）不会被覆盖或删除
        - API 中已不存在的非自定义模型会被标记为 is_active=False（软删除）

        返回: {"added": N, "updated": N, "deactivated": N, "total": N}
        """
        client = self._clients.get(provider_id)
        if client is None:
            raise RuntimeError(f"Provider {provider_id} 不存在或未激活")

        # 调用 /models API
        raw_models = await client.list_models()
        api_model_ids = set()
        for m in raw_models:
            mid = m.get("id", "")
            if mid:
                api_model_ids.add(mid)

        logger.info(
            "[ProviderRegistry] Provider %s 的 /models API 返回 %d 个模型",
            provider_id, len(api_model_ids),
        )

        # 加载该 Provider 在数据库中已有的模型定义
        async with new_async_session() as session:
            result = await session.execute(
                select(ModelDefinition).where(ModelDefinition.provider_id == provider_id)
            )
            existing_defs = {d.model_id: d for d in result.scalars().all()}

            added = 0
            updated = 0
            deactivated = 0

            # 1) 新增 API 中存在但数据库中没有的模型
            for mid in api_model_ids:
                if mid in existing_defs:
                    # 已存在：重新激活（如果之前被软删除）
                    defn = existing_defs[mid]
                    if not defn.is_active and not defn.is_custom:
                        defn.is_active = True
                        updated += 1
                    continue
                # 新增
                model_type = _detect_type(mid)
                provider_name = _detect_provider(mid)
                new_defn = ModelDefinition(
                    provider_id=provider_id,
                    model_id=mid,
                    display_name=_generate_display_name(mid, provider_name, model_type),
                    type=model_type,
                    provider_name=provider_name,
                    capabilities=_detect_capabilities(mid, model_type),
                    is_active=True,
                    is_custom=False,
                    sort_order=0,
                )
                session.add(new_defn)
                added += 1

            # 2) 软删除 API 中已不存在的非自定义模型
            for mid, defn in existing_defs.items():
                if mid not in api_model_ids and not defn.is_custom and defn.is_active:
                    defn.is_active = False
                    deactivated += 1

            await session.commit()

        # 刷新缓存
        await self.refresh_models_cache()

        result_summary = {
            "added": added,
            "updated": updated,
            "deactivated": deactivated,
            "total": len(api_model_ids),
        }
        logger.info("[ProviderRegistry] Provider %s 模型同步完成: %s", provider_id, result_summary)
        return result_summary

    async def sync_all_providers(self) -> List[Dict[str, Any]]:
        """同步所有 active Provider 的模型列表"""
        results = []
        for provider_id in list(self._clients.keys()):
            try:
                result = await self.sync_provider_models(provider_id)
                result["provider_id"] = provider_id
                results.append(result)
            except Exception as e:
                logger.error("[ProviderRegistry] 同步 Provider %s 失败: %s", provider_id, e)
                results.append({"provider_id": provider_id, "error": str(e)})
        return results

    # ---------- Provider CRUD ----------

    async def create_provider(
        self,
        name: str,
        base_url: str,
        api_key: str,
        poll_url: str = "",
        is_active: bool = True,
        is_default: bool = False,
        sort_order: int = 0,
    ) -> ApiProvider:
        """
        新增 Provider。
        - api_key 会用 Fernet 加密后存储
        - 如果 is_default=True，会把其他 Provider 的 is_default 置为 False
        - 创建后立即初始化 client 实例
        """
        # 如果设为默认，先取消其他默认
        async with new_async_session() as session:
            if is_default:
                await session.execute(
                    update(ApiProvider).values(is_default=False)
                )

            provider = ApiProvider(
                name=name,
                base_url=base_url,
                api_key_encrypted=encrypt_api_key(api_key) if api_key else "",
                poll_url=poll_url,
                is_active=is_active,
                is_default=is_default,
                sort_order=sort_order,
            )
            session.add(provider)
            await session.commit()
            await session.refresh(provider)

        # 初始化 client
        if is_active:
            await self._init_client_for_provider(provider)
            # 如果是默认 Provider，重新配置全局单例
            if is_default:
                await self._configure_default_client()

        logger.info("[ProviderRegistry] Provider 已创建: id=%s, name=%s", provider.id, provider.name)
        return provider

    async def update_provider(
        self,
        provider_id: int,
        name: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        poll_url: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_default: Optional[bool] = None,
        sort_order: Optional[int] = None,
    ) -> Optional[ApiProvider]:
        """
        更新 Provider 配置。
        - api_key 非空时才更新（避免误清空）
        - is_default=True 时取消其他默认
        - base_url/api_key/poll_url 变更后重建 client
        """
        async with new_async_session() as session:
            result = await session.execute(
                select(ApiProvider).where(ApiProvider.id == provider_id)
            )
            provider = result.scalars().first()
            if provider is None:
                return None

            # 如果设为默认，先取消其他默认
            if is_default is True:
                await session.execute(
                    update(ApiProvider)
                    .where(ApiProvider.id != provider_id)
                    .values(is_default=False)
                )

            need_rebuild = False
            if name is not None:
                provider.name = name
            if base_url is not None and base_url != provider.base_url:
                provider.base_url = base_url
                need_rebuild = True
            if api_key:  # 非空才更新
                provider.api_key_encrypted = encrypt_api_key(api_key)
                need_rebuild = True
            if poll_url is not None and poll_url != provider.poll_url:
                provider.poll_url = poll_url
                need_rebuild = True
            if is_active is not None:
                provider.is_active = is_active
            if is_default is not None:
                provider.is_default = is_default
            if sort_order is not None:
                provider.sort_order = sort_order

            await session.commit()
            await session.refresh(provider)

        # 重建 client（如果配置变更或激活状态变更）
        was_active = provider_id in self._clients
        is_now_active = provider.is_active

        if need_rebuild or (was_active and not is_now_active):
            # 关闭旧 client
            old_client = self._clients.pop(provider_id, None)
            if old_client is not None:
                await old_client.shutdown()

        if is_now_active and (need_rebuild or not was_active):
            await self._init_client_for_provider(provider)

        # 如果是默认 Provider 或默认 Provider 变了，重新配置全局单例
        if is_default is True or (self._default_provider_id is None and is_now_active):
            await self._configure_default_client()

        logger.info("[ProviderRegistry] Provider 已更新: id=%s, name=%s", provider.id, provider.name)
        return provider

    async def delete_provider(self, provider_id: int) -> bool:
        """
        删除 Provider。
        - 关闭对应的 client
        - 级联删除其下所有模型定义（由外键 ON DELETE CASCADE 保证）
        - 如果删除的是默认 Provider，自动选择新的默认
        """
        was_default = False
        # 关闭 client
        client = self._clients.pop(provider_id, None)
        if client is not None:
            await client.shutdown()

        async with new_async_session() as session:
            # 检查是否是默认 Provider
            result = await session.execute(
                select(ApiProvider).where(ApiProvider.id == provider_id)
            )
            provider = result.scalars().first()
            if provider is None:
                return False
            was_default = provider.is_default

            # 删除 Provider（级联删除模型定义）
            await session.execute(
                delete(ApiProvider).where(ApiProvider.id == provider_id)
            )
            await session.commit()

        # 如果删除的是默认 Provider，重新选择默认
        if was_default:
            self._default_provider_id = None
            await self._configure_default_client()

        # 刷新模型缓存
        await self.refresh_models_cache()

        logger.info("[ProviderRegistry] Provider 已删除: id=%s", provider_id)
        return True

    async def list_providers(self, include_key: bool = False) -> List[Dict[str, Any]]:
        """
        列出所有 Provider（按 sort_order 排序）。
        - include_key=False: API Key 以掩码形式返回（如 sk-a****b123），前端展示用
        - include_key=True: 返回解密后的明文 API Key（仅后端内部使用）
        """
        async with new_async_session() as session:
            result = await session.execute(
                select(ApiProvider).order_by(ApiProvider.sort_order, ApiProvider.id)
            )
            providers = list(result.scalars().all())

        # 始终解密 API Key，由 to_dict 根据 include_key 决定返回掩码还是明文
        return [
            p.to_dict(
                include_key=include_key,
                decrypted_key=decrypt_api_key(p.api_key_encrypted or ""),
            )
            for p in providers
        ]

    # ---------- 模型 CRUD ----------

    async def add_custom_model(
        self,
        provider_id: int,
        model_id: str,
        display_name: str = "",
        model_type: str = "",
        provider_name: str = "",
        capabilities: Optional[List[str]] = None,
        sort_order: int = 0,
    ) -> ModelDefinition:
        """
        添加用户自定义模型。
        - is_custom=True，同步时不会被覆盖或删除
        - 字段为空时自动推断
        """
        # 自动推断缺失字段
        if not model_type:
            model_type = _detect_type(model_id)
        if not provider_name:
            provider_name = _detect_provider(model_id)
        if not display_name:
            display_name = _generate_display_name(model_id, provider_name, model_type)
        if capabilities is None:
            capabilities = _detect_capabilities(model_id, model_type)

        async with new_async_session() as session:
            defn = ModelDefinition(
                provider_id=provider_id,
                model_id=model_id,
                display_name=display_name,
                type=model_type,
                provider_name=provider_name,
                capabilities=capabilities,
                is_active=True,
                is_custom=True,
                sort_order=sort_order,
            )
            session.add(defn)
            await session.commit()
            await session.refresh(defn)

        await self.refresh_models_cache()
        logger.info(
            "[ProviderRegistry] 自定义模型已添加: provider_id=%s, model_id=%s",
            provider_id, model_id,
        )
        return defn

    async def update_model(
        self,
        model_id: str,
        display_name: Optional[str] = None,
        model_type: Optional[str] = None,
        provider_name: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        is_active: Optional[bool] = None,
        sort_order: Optional[int] = None,
    ) -> Optional[ModelDefinition]:
        """更新模型定义"""
        async with new_async_session() as session:
            result = await session.execute(
                select(ModelDefinition).where(ModelDefinition.model_id == model_id)
            )
            defn = result.scalars().first()
            if defn is None:
                return None

            if display_name is not None:
                defn.display_name = display_name
            if model_type is not None:
                defn.type = model_type
            if provider_name is not None:
                defn.provider_name = provider_name
            if capabilities is not None:
                defn.capabilities = capabilities
            if is_active is not None:
                defn.is_active = is_active
            if sort_order is not None:
                defn.sort_order = sort_order

            await session.commit()
            await session.refresh(defn)

        await self.refresh_models_cache()
        logger.info("[ProviderRegistry] 模型已更新: model_id=%s", model_id)
        return defn

    async def delete_model(self, model_id: str) -> bool:
        """删除模型定义（包括自定义和 API 同步的）"""
        async with new_async_session() as session:
            result = await session.execute(
                delete(ModelDefinition).where(ModelDefinition.model_id == model_id)
            )
            await session.commit()
            deleted = result.rowcount > 0

        if deleted:
            await self.refresh_models_cache()
            logger.info("[ProviderRegistry] 模型已删除: model_id=%s", model_id)
        return deleted

    async def list_models(self, provider_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        列出模型定义（可按 Provider 过滤）。
        返回字典列表（包含 is_custom / is_active 等管理字段）。
        """
        async with new_async_session() as session:
            stmt = select(ModelDefinition).order_by(ModelDefinition.sort_order, ModelDefinition.id)
            if provider_id is not None:
                stmt = stmt.where(ModelDefinition.provider_id == provider_id)
            result = await session.execute(stmt)
            definitions = list(result.scalars().all())

        return [
            {
                "id": d.id,
                "provider_id": d.provider_id,
                "model_id": d.model_id,
                "display_name": d.display_name or "",
                "type": d.type,
                "provider_name": d.provider_name or "",
                "capabilities": d.capabilities or [],
                "is_active": d.is_active,
                "is_custom": d.is_custom,
                "sort_order": d.sort_order,
            }
            for d in definitions
        ]

    # ---------- 缓存控制 ----------

    def invalidate_cache(self) -> None:
        """手动清除模型缓存（用于配置变更后强制刷新）"""
        self._models_cache = None
        self._models_cache_time = 0


# ---------- 全局单例 ----------
provider_registry = ProviderRegistry()
