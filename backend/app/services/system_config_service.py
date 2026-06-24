# =====================================================
# 系统配置服务
# - 读写 system_configs 表，提供缓存机制
# - SMTP 等配置优先从数据库读取，兜底用 .env
# =====================================================

import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.system_config import SystemConfig, DEFAULT_SYSTEM_CONFIGS
from app.core.config import settings

logger = logging.getLogger("agnes_platform")

# 内存缓存：{config_key: (config_value, updated_at)}
_config_cache: dict[str, tuple[str, float]] = {}


async def get_all_configs(db: AsyncSession) -> dict[str, str]:
    """获取所有系统配置（键值对字典）"""
    result = await db.execute(select(SystemConfig))
    configs = result.scalars().all()
    return {c.config_key: c.config_value for c in configs}


async def get_config_by_category(db: AsyncSession, category: str) -> dict[str, str]:
    """按分类获取系统配置"""
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.category == category)
    )
    configs = result.scalars().all()
    return {c.config_key: c.config_value for c in configs}


async def get_config_value(db: AsyncSession, key: str, default: str = "") -> str:
    """获取单个配置值"""
    # 先查缓存
    import time
    cached = _config_cache.get(key)
    if cached:
        return cached[0]

    result = await db.execute(
        select(SystemConfig).where(SystemConfig.config_key == key)
    )
    config = result.scalar_one_or_none()
    value = config.config_value if config else default

    # 写入缓存（有效期 60 秒）
    _config_cache[key] = (value, time.time())
    return value


async def set_config_value(db: AsyncSession, key: str, value: str) -> None:
    """设置单个配置值"""
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.config_key == key)
    )
    config = result.scalar_one_or_none()

    if config:
        config.config_value = value
    else:
        config = SystemConfig(
            config_key=key,
            config_value=value,
            category="site",
        )
        db.add(config)

    await db.commit()

    # 清除缓存
    _config_cache.pop(key, None)


async def batch_set_configs(db: AsyncSession, configs: dict[str, str]) -> None:
    """批量设置配置"""
    if not configs:
        return

    result = await db.execute(
        select(SystemConfig).where(SystemConfig.config_key.in_(configs.keys()))
    )
    existing = result.scalars().all()
    existing_map = {c.config_key: c for c in existing}

    for key, value in configs.items():
        if key in existing_map:
            existing_map[key].config_value = value
        else:
            db.add(SystemConfig(
                config_key=key,
                config_value=value,
                category="site",
            ))
        # 清除缓存
        _config_cache.pop(key, None)

    await db.commit()


async def ensure_default_configs(db: AsyncSession) -> int:
    """确保默认配置存在（缺失的补上），返回新增的配置数"""
    result = await db.execute(select(SystemConfig.config_key))
    existing_keys = {row[0] for row in result.all()}

    added = 0
    for key, info in DEFAULT_SYSTEM_CONFIGS.items():
        if key not in existing_keys:
            db.add(SystemConfig(
                config_key=key,
                config_value=info["value"],
                category=info["category"],
                description=info["description"],
            ))
            added += 1

    if added > 0:
        await db.commit()
        logger.info("[系统配置] 初始化了 %d 条默认配置", added)

    return added


# =====================================================
# SMTP 配置相关
# =====================================================

class SmtpConfig:
    """SMTP 配置封装（优先从数据库读取，兜底用 .env）"""
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        from_email: str,
        from_name: str,
        use_tls: bool,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_email = from_email
        self.from_name = from_name
        self.use_tls = use_tls

    @property
    def is_enabled(self) -> bool:
        """SMTP 是否已配置启用"""
        return bool(self.host and self.user and self.password and self.from_email)


async def get_smtp_config(db: AsyncSession) -> SmtpConfig:
    """
    获取 SMTP 配置。
    优先从数据库 system_configs 表读取，数据库为空时兜底用 .env 配置。
    """
    db_configs = await get_config_by_category(db, "smtp")

    # 数据库中有 host 就认为是数据库配置（否则兜底 .env）
    if db_configs.get("smtp_host"):
        return SmtpConfig(
            host=db_configs.get("smtp_host", ""),
            port=int(db_configs.get("smtp_port", "587")),
            user=db_configs.get("smtp_user", ""),
            password=db_configs.get("smtp_password", ""),
            from_email=db_configs.get("smtp_from_email", ""),
            from_name=db_configs.get("smtp_from_name", "Agnes AI Platform"),
            use_tls=db_configs.get("smtp_use_tls", "true").lower() in ("true", "1", "yes"),
        )

    # 兜底：.env 配置
    return SmtpConfig(
        host=settings.smtp_host,
        port=settings.smtp_port,
        user=settings.smtp_user,
        password=settings.smtp_password,
        from_email=settings.smtp_from_email,
        from_name=settings.smtp_from_name,
        use_tls=settings.smtp_use_tls,
    )


async def update_smtp_config(db: AsyncSession, config_data: dict) -> None:
    """更新 SMTP 配置（批量写入数据库）"""
    smtp_keys = {
        "smtp_host": str(config_data.get("smtp_host", "")),
        "smtp_port": str(config_data.get("smtp_port", 587)),
        "smtp_user": str(config_data.get("smtp_user", "")),
        "smtp_password": str(config_data.get("smtp_password", "")),
        "smtp_from_email": str(config_data.get("smtp_from_email", "")),
        "smtp_from_name": str(config_data.get("smtp_from_name", "Agnes AI Platform")),
        "smtp_use_tls": "true" if config_data.get("smtp_use_tls", True) else "false",
    }
    await batch_set_configs(db, smtp_keys)
