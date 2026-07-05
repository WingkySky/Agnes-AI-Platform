# =====================================================
# Task 29.1: 引擎自动暂停 + 就绪判定单元测试
#
# 测试 PipelineEngine 的 3 个核心逻辑（不启动真实执行循环，避免后台任务干扰）：
#   1. _handle_step_confirmation：requires_confirmation / human_gate / auto_confirm 三种分支
#   2. _get_ready_steps：上游 confirmation_status=pending 时下游不就绪
#   3. _check_pause_request：pause_requested=True 时退出循环
#
# Mock 策略：
#   - 直接构造 PipelineEngine 实例并手工注入 _db / _run / _steps / _template
#   - 不调用 start() / resume()，避免触发 _execute_loop
#   - patch _safe_commit / _emit_progress / _serialize_step 为 no-op
# =====================================================

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from app.models.pipeline import PipelineRun, PipelineStep, PipelineTemplate
from app.services.pipeline.engine import PipelineEngine


# ---------- 辅助：构造一个未启动的 PipelineEngine ----------
def _make_engine(run: PipelineRun, steps: dict) -> PipelineEngine:
    """构造 PipelineEngine 实例并注入 _run / _steps，跳过数据库加载"""
    engine = PipelineEngine(run_id=run.id)
    engine._run = run
    engine._steps = steps
    engine._db = MagicMock()
    engine._template = MagicMock(spec=PipelineTemplate)
    # 把会触发数据库 / SSE 的方法 patch 成 no-op
    engine._safe_commit = AsyncMock(return_value=None)
    engine._emit_progress = MagicMock(return_value=None)
    engine._serialize_step = MagicMock(return_value={"step_key": "mock"})
    return engine


def _make_run(
    run_id: int = 1,
    status: str = "running",
    auto_confirm: bool = False,
    pause_requested: bool = False,
    pause_reason: str | None = None,
) -> PipelineRun:
    return PipelineRun(
        id=run_id,
        template_id=1,
        user_id=1,
        inputs={},
        status=status,
        auto_confirm=auto_confirm,
        pause_requested=pause_requested,
        pause_reason=pause_reason,
    )


def _make_step(
    step_key: str,
    step_type: str = "llm_generate",
    status: str = "pending",
    depends_on: list | None = None,
    requires_confirmation: bool = False,
    confirmation_status: str | None = None,
    step_type_for_gate: str | None = None,
) -> PipelineStep:
    return PipelineStep(
        id=hash(step_key) & 0xFFFFFF,
        run_id=1,
        step_key=step_key,
        name=step_key,
        step_type=step_type_for_gate or step_type,
        status=status,
        sort_order=0,
        depends_on=depends_on or [],
        requires_confirmation=requires_confirmation,
        confirmation_status=confirmation_status,
    )


# =====================================================
# 场景 1: _handle_step_confirmation 行为分支
# =====================================================

@pytest.mark.asyncio
async def test_handle_confirmation_no_confirmation_required_does_nothing():
    """无需确认的步骤调用 _handle_step_confirmation 应直接 return，不改任何状态"""
    run = _make_run()
    step = _make_step("step_a", requires_confirmation=False)
    engine = _make_engine(run, {"step_a": step})

    await engine._handle_step_confirmation("step_a")

    # 状态不应被修改
    assert step.confirmation_status is None
    assert run.pause_requested is False
    assert run.pause_reason is None
    # 不应推送 SSE 事件
    assert engine._emit_progress.call_count == 0


@pytest.mark.asyncio
async def test_handle_confirmation_requires_confirmation_pauses_pipeline():
    """requires_confirmation=True 且 auto_confirm=False 时应：
    - 置 step.confirmation_status=pending
    - 置 run.pause_requested=True / pause_reason=awaiting_confirmation
    - 推送 step_awaiting_confirmation 事件
    """
    run = _make_run(auto_confirm=False)
    step = _make_step("step_a", requires_confirmation=True, status="success")
    engine = _make_engine(run, {"step_a": step})

    await engine._handle_step_confirmation("step_a")

    assert step.confirmation_status == "pending"
    assert run.pause_requested is True
    assert run.pause_reason == "awaiting_confirmation"
    # 验证推送了 step_awaiting_confirmation 事件
    engine._emit_progress.assert_called_once()
    args, kwargs = engine._emit_progress.call_args
    assert args[0] == "step_awaiting_confirmation"
    assert args[1] == "step_a"


@pytest.mark.asyncio
async def test_handle_confirmation_human_gate_type_always_pauses():
    """step_type=human_gate 应无视 requires_confirmation 触发暂停"""
    run = _make_run(auto_confirm=False)
    step = _make_step(
        "gate",
        step_type_for_gate="human_gate",
        requires_confirmation=False,
        status="success",
    )
    engine = _make_engine(run, {"gate": step})

    await engine._handle_step_confirmation("gate")

    assert step.confirmation_status == "pending"
    assert run.pause_reason == "awaiting_confirmation"


@pytest.mark.asyncio
async def test_handle_confirmation_auto_confirm_skips_pause():
    """auto_confirm=True 时应直接置 confirmed，不暂停"""
    run = _make_run(auto_confirm=True)
    step = _make_step("step_a", requires_confirmation=True, status="success")
    engine = _make_engine(run, {"step_a": step})

    await engine._handle_step_confirmation("step_a")

    assert step.confirmation_status == "confirmed"
    assert run.pause_requested is False
    assert run.pause_reason is None
    # 不应推送 step_awaiting_confirmation 事件
    assert engine._emit_progress.call_count == 0


@pytest.mark.asyncio
async def test_handle_confirmation_unknown_step_does_nothing():
    """step_key 不存在于 _steps 中时应安全返回"""
    run = _make_run()
    engine = _make_engine(run, {})

    # 不应抛异常
    await engine._handle_step_confirmation("nonexistent_step")


# =====================================================
# 场景 2: _get_ready_steps 就绪判定
# =====================================================

def test_get_ready_steps_returns_step_with_no_deps():
    """无依赖的 pending 步骤应判为就绪"""
    run = _make_run()
    step_a = _make_step("step_a", status="pending", depends_on=[])
    engine = _make_engine(run, {"step_a": step_a})

    ready = engine._get_ready_steps()
    assert ready == ["step_a"]


def test_get_ready_steps_blocks_when_dep_not_success():
    """上游 dep 状态非 success 时，下游不就绪"""
    run = _make_run()
    step_a = _make_step("step_a", status="running")
    step_b = _make_step("step_b", status="pending", depends_on=["step_a"])
    engine = _make_engine(run, {"step_a": step_a, "step_b": step_b})

    ready = engine._get_ready_steps()
    assert "step_b" not in ready


def test_get_ready_steps_blocks_when_dep_needs_confirmation_pending():
    """上游 requires_confirmation=True 且 confirmation_status=pending 时，下游不就绪"""
    run = _make_run()
    step_a = _make_step(
        "step_a",
        status="success",
        requires_confirmation=True,
        confirmation_status="pending",
    )
    step_b = _make_step("step_b", status="pending", depends_on=["step_a"])
    engine = _make_engine(run, {"step_a": step_a, "step_b": step_b})

    ready = engine._get_ready_steps()
    assert "step_b" not in ready


def test_get_ready_steps_allows_when_dep_confirmation_confirmed():
    """上游 requires_confirmation=True 且 confirmation_status=confirmed 时，下游就绪"""
    run = _make_run()
    step_a = _make_step(
        "step_a",
        status="success",
        requires_confirmation=True,
        confirmation_status="confirmed",
    )
    step_b = _make_step("step_b", status="pending", depends_on=["step_a"])
    engine = _make_engine(run, {"step_a": step_a, "step_b": step_b})

    ready = engine._get_ready_steps()
    assert "step_b" in ready


def test_get_ready_steps_blocks_when_dep_confirmation_rejected():
    """上游 confirmation_status=rejected 时，下游不就绪（应由 _skip_blocked_steps 标记 skipped）"""
    run = _make_run()
    step_a = _make_step(
        "step_a",
        status="success",
        requires_confirmation=True,
        confirmation_status="rejected",
    )
    step_b = _make_step("step_b", status="pending", depends_on=["step_a"])
    engine = _make_engine(run, {"step_a": step_a, "step_b": step_b})

    ready = engine._get_ready_steps()
    assert "step_b" not in ready


def test_get_ready_steps_human_gate_pending_blocks_downstream():
    """human_gate 类型上游 confirmation_status=pending 时阻塞下游"""
    run = _make_run()
    step_gate = _make_step(
        "gate",
        step_type_for_gate="human_gate",
        status="success",
        confirmation_status="pending",
    )
    step_b = _make_step("step_b", status="pending", depends_on=["gate"])
    engine = _make_engine(run, {"gate": step_gate, "step_b": step_b})

    ready = engine._get_ready_steps()
    assert "step_b" not in ready


# =====================================================
# 场景 3: _check_pause_request 暂停检查
# =====================================================

@pytest.mark.asyncio
async def test_check_pause_request_exits_when_pause_requested(monkeypatch):
    """pause_requested=True 时应：
    - 将 run.status 置为 paused
    - 清除 pause_requested 标志
    - 置 self._cancelled = True（让 _execute_loop 退出）
    - 推送 pipeline_paused 事件
    """
    run = _make_run(status="running", pause_requested=True, pause_reason="user_manual")
    engine = _make_engine(run, {})

    # mock 数据库查询：返回 pause_requested=True
    async def fake_db_execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = True
        return result

    engine._db.execute = fake_db_execute
    engine._safe_commit = AsyncMock(return_value=None)
    engine._emit_progress = MagicMock(return_value=None)

    await engine._check_pause_request()

    assert run.status == "paused"
    assert run.pause_requested is False
    assert engine._cancelled is True
    # pause_reason 应保留（给 resume 判断用）
    assert run.pause_reason == "user_manual"
    engine._emit_progress.assert_called_once()
    args = engine._emit_progress.call_args.args
    assert args[0] == "pipeline_paused"


@pytest.mark.asyncio
async def test_check_pause_request_does_nothing_when_not_paused():
    """pause_requested=False 时不应改变任何状态"""
    run = _make_run(status="running", pause_requested=False)
    engine = _make_engine(run, {})

    async def fake_db_execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = False
        return result

    engine._db.execute = fake_db_execute

    await engine._check_pause_request()

    assert run.status == "running"
    assert engine._cancelled is False
