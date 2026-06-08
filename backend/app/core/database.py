# =====================================================
# 数据库连接与 SQLAlchemy 基础配置（异步 + 同步双模式）
# - 异步模式：async_engine / async_session / AsyncSession（推荐，不阻塞事件循环
# - 同步模式：engine / SessionLocal（保留，兼容旧代码）
# =====================================================

from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# ---------- 同步数据库引擎（保留，低并发场景或旧代码兼容）
_sync_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    connect_args=_sync_connect_args,
    pool_pre_ping=not settings.database_url.startswith("sqlite"),
    echo=False,
)

# ---------- 异步数据库引擎（推荐，所有异步路由使用）
# SQLite 使用 aiosqlite driver，PostgreSQL 使用 asyncpg
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

# ---------- 同步 Session 工厂
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ---------- 异步 Session 工厂（推荐）
async_session = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ---------- ORM 模型基类
Base = declarative_base()


# ---------- 同步数据库 Session 依赖注入（旧代码兼容，不推荐）
def get_db():
    """
    ⚠️ 已不推荐，保留同步版本，请优先使用 get_async_db
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- 异步数据库 Session 依赖注入（推荐）
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
