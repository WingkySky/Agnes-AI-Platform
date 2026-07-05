# =====================================================
# pytest 共享 fixture
#
# 功能模块：
#   1. event_loop：单测试单事件循环
#   2. _patch_sse_emit：自动把 pipeline_sse_manager.emit / emit_sync 改成 no-op，
#      避免测试中触发 SSE 推送（emit 内部会 asyncio.create_task 干扰断言）
#   3. _patch_credits：把 credits_service 的扣 / 退积分改成 no-op
#   4. memory_db：基于 aiosqlite 的内存数据库 AsyncSession（仅本测试使用），
#      测试结束自动销毁
#   5. seed_run_with_steps：构造一个 PipelineRun + 多个 PipelineStep 的最小可运行场景
# =====================================================

import asyncio
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from typing import AsyncIterator, List, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import select

from app.core.database import Base
from app.models.pipeline import (
    PipelineRun,
    PipelineStep,
    PipelineTemplate,
    ScriptTemplate,
    StylePreset,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    STATUS_FAILED,
    STEP_STATUS_PENDING,
)
from app.models.pipeline_step_output_revision import PipelineStepOutputRevision
from app.models.user import User


# ---------- 自动 mock SSE manager 与积分服务 ----------
# 所有测试默认不触发真实 SSE 推送 / 积分扣退，需要时在测试内重新 patch
@pytest.fixture(autouse=True)
def _patch_sse_and_credits(monkeypatch):
    async def _noop_emit(*args, **kwargs):
        return None

    def _noop_emit_sync(*args, **kwargs):
        return None

    from app.services.pipeline import sse_manager
    monkeypatch.setattr(sse_manager.pipeline_sse_manager, "emit", _noop_emit)
    monkeypatch.setattr(sse_manager.pipeline_sse_manager, "emit_sync", _noop_emit_sync)
    monkeypatch.setattr(
        sse_manager.pipeline_sse_manager,
        "make_progress_callback",
        lambda run_id: (lambda event_type, step_key, data: None),
    )

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


# ---------- 工厂 fixture：用户 + 模板 + 运行 + 步骤 ----------
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
    """插入一个最小流水线模板"""
    template = PipelineTemplate(
        key="test_tpl",
        name="测试模板",
        category="drama",
        inputs_config={},
        steps_config=[
            {"key": "step_a", "type": "llm_generate", "name": "步骤A", "config": {}},
            {"key": "step_b", "type": "llm_generate", "name": "步骤B",
             "depends_on": ["step_a"], "config": {}},
            {"key": "step_c", "type": "llm_generate", "name": "步骤C",
             "depends_on": ["step_b"], "config": {}},
        ],
        estimated_credits=10,
        is_builtin=True,
    )
    memory_db.add(template)
    await memory_db.commit()
    await memory_db.refresh(template)
    return template


def _make_step(
    run_id: int,
    key: str,
    name: str,
    step_type: str,
    sort_order: int,
    depends_on: Optional[List[str]] = None,
    requires_confirmation: bool = False,
    status: str = STEP_STATUS_PENDING,
    output_data: Optional[dict] = None,
    confirmation_status: Optional[str] = None,
    stale: bool = False,
) -> PipelineStep:
    """构造 PipelineStep 实例（未提交）"""
    return PipelineStep(
        run_id=run_id,
        step_key=key,
        name=name,
        step_type=step_type,
        sort_order=sort_order,
        depends_on=depends_on or [],
        requires_confirmation=requires_confirmation,
        status=status,
        output_data=output_data or {},
        confirmation_status=confirmation_status,
        stale=stale,
    )


@pytest_asyncio.fixture
async def seed_run_with_steps(
    memory_db: AsyncSession,
    seed_user: User,
    seed_template: PipelineTemplate,
) -> dict:
    """构造 run + 3 个步骤（A→B→C）的最小场景

    步骤链路：step_a (llm_generate) → step_b (llm_generate) → step_c (llm_generate)
    """
    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="pending",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    steps = [
        _make_step(run.id, "step_a", "步骤A", "llm_generate", 0),
        _make_step(run.id, "step_b", "步骤B", "llm_generate", 1, depends_on=["step_a"]),
        _make_step(run.id, "step_c", "步骤C", "llm_generate", 2, depends_on=["step_b"]),
    ]
    memory_db.add_all(steps)
    await memory_db.commit()
    for s in steps:
        await memory_db.refresh(s)

    return {"run": run, "steps": steps, "user": seed_user, "template": seed_template}
