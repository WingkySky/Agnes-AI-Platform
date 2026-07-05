# =====================================================
# pytest 共享 fixture
#
# 功能模块：
#   1. _patch_credits：把 credits_service 的扣 / 退积分改成 no-op
#   2. memory_db：基于 aiosqlite 的内存数据库 AsyncSession（仅本测试使用），
#      测试结束自动销毁
#   3. seed_user：插入一个测试用户
#   4. seed_template：插入一个最小流水线模板（PipelineTemplate）
#
# 说明：项目制创作（Project）已取代旧 PipelineRun/PipelineStep 体系，
#       旧 Pipeline 专用 fixture（seed_run_with_steps / _make_step 等）已移除。
# =====================================================

import pytest
import pytest_asyncio
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import Base
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
    """基于 aiosqlite 的内存数据库 session，所有表预先创建"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
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
