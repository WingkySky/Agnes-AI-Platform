# =====================================================
# 数据库连接与 SQLAlchemy 基础配置（全异步）
# =====================================================

from typing import AsyncGenerator

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# ---------- 异步数据库引擎（SQLite 使用 aiosqlite driver，PostgreSQL 使用 asyncpg）
if settings.database_url.startswith("sqlite"):
    _async_url = settings.database_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
else:
    _async_url = settings.database_url

async_engine = create_async_engine(
    _async_url,
    connect_args={"check_same_thread": False} if _async_url.startswith("sqlite") else {},
    pool_pre_ping=not _async_url.startswith("sqlite"),
    pool_size=10,
    max_overflow=20,
    echo=False,
)

# ---------- 异步 Session 工厂
async_session = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ---------- ORM 模型基类
Base = declarative_base()


# ---------- 异步数据库 Session 依赖注入
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 异步路由的数据库 Session 依赖注入
    在异步路由中使用，不会阻塞事件循环。

    用法：
        async def some_route(db: AsyncSession = Depends(get_async_db)):
            ...
    """
    async with async_session() as session:
        yield session


# ---------- 便捷函数：获取独立的异步 Session（后台任务使用）
def new_async_session() -> AsyncSession:
    """
    创建一个新的独立异步 Session（非依赖注入场景，如后台轮询任务）。
    使用完毕后必须 `await session.close()` 释放资源。
    """
    return async_session()
