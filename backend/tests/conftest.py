# =====================================================
# pytest 共享 fixture
#
# 功能模块：
#   1. _patch_credits：把 credits_service 的扣 / 退积分改成 no-op
#   2. memory_db：基于 aiosqlite 的内存数据库 AsyncSession（仅本测试使用），
#      测试结束自动销毁；启用 SQLite foreign_keys pragma 让 CASCADE 级联生效
#   3. db：memory_db 的别名 fixture（便于测试代码用通用名 db）
#   4. seed_user：插入一个测试用户
#   5. seed_template：插入一个最小流水线模板（PipelineTemplate）
#   6. auth_client：带 JWT 鉴权的 httpx AsyncClient，覆盖 get_async_db 使用内存数据库
#
# 说明：项目制创作（Project）已取代旧 PipelineRun/PipelineStep 体系，
#       旧 Pipeline 专用 fixture（seed_run_with_steps / _make_step 等）已移除。
# =====================================================

import pytest
import pytest_asyncio
from typing import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import Base, get_async_db
from app.models.pipeline import PipelineTemplate
from app.models.user import User


# ---------- 自动 mock 积分服务 ----------
# 所有测试默认不触发真实积分扣退，需要时在测试内重新 patch
@pytest.fixture(autouse=True)
def _patch_credits(monkeypatch):
    from app.services import credits_service

    async def _noop_consume(*args, **kwargs):
        return True

    async def _noop_refund(*args, **kwargs):
        return True

    monkeypatch.setattr(credits_service, "consume_credits", _noop_consume)
    monkeypatch.setattr(credits_service, "refund_credits", _noop_refund)


# ---------- 内存数据库 fixture ----------
@pytest_asyncio.fixture
async def memory_db() -> AsyncIterator[AsyncSession]:
    """基于 aiosqlite 的内存数据库 session，所有表预先创建

    启用 SQLite foreign_keys pragma（PRAGMA foreign_keys=ON），
    让 ON DELETE CASCADE 级联删除在 SQLite 中也生效。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    # 在每个底层 DBAPI connection 上启用外键约束（SQLite 默认关闭）
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with Session() as session:
        yield session

    await engine.dispose()


# ---------- db fixture：memory_db 别名，便于测试用通用名 db ----------
@pytest_asyncio.fixture
async def db(memory_db: AsyncSession) -> AsyncSession:
    """memory_db 的别名，便于测试代码用 db 命名引用内存数据库 session"""
    return memory_db


# ---------- 工厂 fixture：用户 + 模板 ----------
@pytest_asyncio.fixture
async def seed_user(memory_db: AsyncSession) -> User:
    """插入一个测试用户"""
    user = User(
        username="tester",
        email="tester@example.com",
        password_hash="x",
        role="user",
        credits=10000,
    )
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def seed_template(memory_db: AsyncSession) -> PipelineTemplate:
    """插入一个最小流水线模板（wizard_chain 风格 steps_config）"""
    template = PipelineTemplate(
        key="test_tpl",
        name="测试模板",
        category="drama",
        inputs_config={},
        steps_config=[
            {"key": "script_generation", "type": "llm_generate", "name": "剧本生成", "config": {}},
            {"key": "entity_extraction", "type": "llm_generate", "name": "实体提取",
             "depends_on": ["script_generation"], "config": {}},
            {"key": "storyboard_split", "type": "llm_generate", "name": "分镜拆分",
             "depends_on": ["entity_extraction"], "config": {}},
            {"key": "frame_prompt_extract", "type": "llm_generate", "name": "帧 prompt 提取",
             "depends_on": ["storyboard_split"], "config": {}},
        ],
        estimated_credits=10,
        is_builtin=True,
    )
    memory_db.add(template)
    await memory_db.commit()
    await memory_db.refresh(template)
    return template


# ---------- auth_client fixture：带 JWT 的 httpx AsyncClient ----------
@pytest_asyncio.fixture
async def auth_client(memory_db: AsyncSession, seed_user: User) -> AsyncIterator:
    """带 JWT 鉴权的 httpx AsyncClient

    - 覆盖 get_async_db 依赖，让路由使用内存数据库 session（与 memory_db 同一个）
    - 自动在请求头注入 Authorization: Bearer <token>（seed_user 的 JWT）
    - 使用 ASGITransport 直接调用 ASGI app，不触发 lifespan（不启动 poller 等后台任务）
    """
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.core.security import create_access_token

    # 覆盖 get_async_db 依赖：让路由使用 memory_db 的同一个 session
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db

    token = create_access_token(seed_user.id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {token}"
        yield client

    app.dependency_overrides.clear()
