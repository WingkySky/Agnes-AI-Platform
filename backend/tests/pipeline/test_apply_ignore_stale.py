# =====================================================
# Task 29.5: apply-stale / ignore-stale 测试
#
# 覆盖 backend/app/services/pipeline/run_service.py:
#   - apply_stale（应用下游失效：重置 stale 步骤及下游 + resume）
#   - ignore_stale（忽略下游失效：仅清 stale 标记）
#
# 测试场景：
#   1. apply_stale：重置 stale 步骤及其下游（status/output_data/stale）
#   2. apply_stale：重置后 run.status 变为 pending，pause_requested 清除
#   3. apply_stale：调用 resume_pipeline 恢复执行
#   4. apply_stale：无 stale 步骤时返回空 reset_steps
#   5. apply_stale：run 状态 running 时返回 409
#   6. apply_stale：非本人流水线返回 403
#   7. apply_stale：流水线不存在返回 404
#   8. ignore_stale：清除所有 stale 标记和 stale_reason
#   9. ignore_stale：不影响 step.status / output_data
#  10. ignore_stale：无 stale 步骤时返回空列表
#  11. ignore_stale：run 状态 running 时返回 409
#  12. ignore_stale：非本人流水线返回 403
#  13. ignore_stale：流水线不存在返回 404
# =====================================================

import pytest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.services.pipeline.run_service import apply_stale, ignore_stale
from app.models.pipeline import PipelineRun
from tests.conftest import _make_step


# ---------- 辅助函数 ----------

def _output_with_items(count: int) -> dict:
    """构造有 items 的 output_data"""
    return {
        "items": [
            {"id": f"item_{i+1}", "name": f"项目{i+1}", "status": "success"}
            for i in range(count)
        ],
        "success_count": count,
    }


# ---------- apply_stale 测试 ----------

@pytest.mark.asyncio
async def test_apply_stale_resets_steps(memory_db, seed_user, seed_template, seed_run_with_steps):
    """apply_stale：重置 stale 步骤及其下游（status/output_data/stale）"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]
    step_b = seed_run_with_steps["steps"][1]
    step_c = seed_run_with_steps["steps"][2]

    # 让 step_a 成功，step_b 和 step_c 标记 stale 并有 output
    step_a.status = "success"
    step_a.output_data = _output_with_items(2)
    step_b.status = "success"
    step_b.stale = True
    step_b.stale_reason = "上游被编辑"
    step_b.output_data = _output_with_items(3)
    step_c.status = "success"
    step_c.stale = True
    step_c.stale_reason = "上游被编辑"
    step_c.output_data = _output_with_items(1)
    run.status = "paused"
    await memory_db.commit()

    # mock resume_pipeline 避免真实执行
    with patch(
        "app.services.pipeline.run_service.resume_pipeline",
        new_callable=AsyncMock,
    ):
        result = await apply_stale(
            db=memory_db,
            run_id=run.id,
            user_id=seed_user.id,
        )

    # step_b 和 step_c 都应被重置
    assert "step_b" in result["reset_steps"]
    assert "step_c" in result["reset_steps"]

    await memory_db.refresh(step_b)
    await memory_db.refresh(step_c)
    assert step_b.status == "pending"
    assert step_b.output_data == {}
    assert step_b.stale is False
    assert step_b.stale_reason is None
    assert step_c.status == "pending"
    assert step_c.output_data == {}
    assert step_c.stale is False


@pytest.mark.asyncio
async def test_apply_stale_clears_run_pause(memory_db, seed_user, seed_template, seed_run_with_steps):
    """apply_stale：重置后 run.status 变为 pending，pause_requested 清除"""
    run = seed_run_with_steps["run"]
    step_b = seed_run_with_steps["steps"][1]

    step_b.stale = True
    step_b.stale_reason = "x"
    run.status = "paused"
    run.pause_requested = True
    run.pause_reason = "等待"
    await memory_db.commit()

    with patch(
        "app.services.pipeline.run_service.resume_pipeline",
        new_callable=AsyncMock,
    ):
        await apply_stale(db=memory_db, run_id=run.id, user_id=seed_user.id)

    await memory_db.refresh(run)
    assert run.status == "pending"
    assert run.pause_requested is False
    assert run.pause_reason is None


@pytest.mark.asyncio
async def test_apply_stale_calls_resume(memory_db, seed_user, seed_template, seed_run_with_steps):
    """apply_stale：调用 resume_pipeline 恢复执行"""
    run = seed_run_with_steps["run"]
    step_b = seed_run_with_steps["steps"][1]
    step_b.stale = True
    run.status = "paused"
    await memory_db.commit()

    with patch(
        "app.services.pipeline.run_service.resume_pipeline",
        new_callable=AsyncMock,
    ) as mock_resume:
        await apply_stale(db=memory_db, run_id=run.id, user_id=seed_user.id)
        mock_resume.assert_awaited_once()
        # 验证传入的 run_id
        args, kwargs = mock_resume.await_args
        assert args[0] == run.id or kwargs.get("run_id") == run.id


@pytest.mark.asyncio
async def test_apply_stale_no_stale_returns_empty(memory_db, seed_user, seed_template, seed_run_with_steps):
    """apply_stale：无 stale 步骤时返回空 reset_steps"""
    run = seed_run_with_steps["run"]
    # 不标记任何 stale
    run.status = "paused"
    await memory_db.commit()

    result = await apply_stale(db=memory_db, run_id=run.id, user_id=seed_user.id)
    assert result["reset_steps"] == []
    assert "无 stale" in result["message"]


@pytest.mark.asyncio
async def test_apply_stale_running_rejected(memory_db, seed_user, seed_template, seed_run_with_steps):
    """apply_stale：run 状态 running 时返回 409"""
    run = seed_run_with_steps["run"]
    step_b = seed_run_with_steps["steps"][1]
    step_b.stale = True
    run.status = "running"
    await memory_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await apply_stale(db=memory_db, run_id=run.id, user_id=seed_user.id)
    assert exc_info.value.status_code == 409
    assert "运行中" in exc_info.value.detail


@pytest.mark.asyncio
async def test_apply_stale_wrong_user(memory_db, seed_user, seed_template, seed_run_with_steps):
    """apply_stale：非本人流水线返回 403"""
    run = seed_run_with_steps["run"]
    step_b = seed_run_with_steps["steps"][1]
    step_b.stale = True
    run.status = "paused"
    await memory_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await apply_stale(db=memory_db, run_id=run.id, user_id=seed_user.id + 999)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_apply_stale_run_not_found(memory_db, seed_user, seed_template):
    """apply_stale：流水线不存在返回 404"""
    with pytest.raises(HTTPException) as exc_info:
        await apply_stale(db=memory_db, run_id=99999, user_id=seed_user.id)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_apply_stale_includes_downstream_of_stale(memory_db, seed_user, seed_template, seed_run_with_steps):
    """apply_stale：stale 步骤的下游（非直接 stale）也应被重置"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]
    step_b = seed_run_with_steps["steps"][1]
    step_c = seed_run_with_steps["steps"][2]

    # 仅 step_b 标 stale，但 step_c 依赖 step_b 也应被重置
    step_a.status = "success"
    step_b.stale = True
    step_b.stale_reason = "x"
    step_b.status = "success"
    step_b.output_data = _output_with_items(1)
    step_c.status = "success"
    step_c.output_data = _output_with_items(1)
    # step_c 没标 stale，但因为依赖 step_b 也应被重置
    run.status = "paused"
    await memory_db.commit()

    with patch(
        "app.services.pipeline.run_service.resume_pipeline",
        new_callable=AsyncMock,
    ):
        result = await apply_stale(db=memory_db, run_id=run.id, user_id=seed_user.id)

    # step_b 和 step_c 都应被重置
    assert "step_b" in result["reset_steps"]
    assert "step_c" in result["reset_steps"]

    await memory_db.refresh(step_c)
    assert step_c.status == "pending"
    assert step_c.output_data == {}


# ---------- ignore_stale 测试 ----------

@pytest.mark.asyncio
async def test_ignore_stale_clears_marks(memory_db, seed_user, seed_template, seed_run_with_steps):
    """ignore_stale：清除所有 stale 标记和 stale_reason"""
    run = seed_run_with_steps["run"]
    step_b = seed_run_with_steps["steps"][1]
    step_c = seed_run_with_steps["steps"][2]

    step_b.stale = True
    step_b.stale_reason = "测试1"
    step_c.stale = True
    step_c.stale_reason = "测试2"
    run.status = "paused"
    await memory_db.commit()

    result = await ignore_stale(db=memory_db, run_id=run.id, user_id=seed_user.id)

    assert set(result["cleared_steps"]) == {"step_b", "step_c"}

    await memory_db.refresh(step_b)
    await memory_db.refresh(step_c)
    assert step_b.stale is False
    assert step_b.stale_reason is None
    assert step_c.stale is False
    assert step_c.stale_reason is None


@pytest.mark.asyncio
async def test_ignore_stale_preserves_output(memory_db, seed_user, seed_template, seed_run_with_steps):
    """ignore_stale：不影响 step.status / output_data"""
    run = seed_run_with_steps["run"]
    step_b = seed_run_with_steps["steps"][1]

    step_b.stale = True
    step_b.stale_reason = "x"
    step_b.status = "success"
    step_b.output_data = _output_with_items(3)
    run.status = "paused"
    await memory_db.commit()

    await ignore_stale(db=memory_db, run_id=run.id, user_id=seed_user.id)

    await memory_db.refresh(step_b)
    # status 和 output_data 应保持不变
    assert step_b.status == "success"
    assert len(step_b.output_data["items"]) == 3


@pytest.mark.asyncio
async def test_ignore_stale_no_stale_returns_empty(memory_db, seed_user, seed_template, seed_run_with_steps):
    """ignore_stale：无 stale 步骤时返回空列表"""
    run = seed_run_with_steps["run"]
    run.status = "paused"
    await memory_db.commit()

    result = await ignore_stale(db=memory_db, run_id=run.id, user_id=seed_user.id)
    assert result["cleared_steps"] == []


@pytest.mark.asyncio
async def test_ignore_stale_running_rejected(memory_db, seed_user, seed_template, seed_run_with_steps):
    """ignore_stale：run 状态 running 时返回 409"""
    run = seed_run_with_steps["run"]
    step_b = seed_run_with_steps["steps"][1]
    step_b.stale = True
    run.status = "running"
    await memory_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await ignore_stale(db=memory_db, run_id=run.id, user_id=seed_user.id)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_ignore_stale_wrong_user(memory_db, seed_user, seed_template, seed_run_with_steps):
    """ignore_stale：非本人流水线返回 403"""
    run = seed_run_with_steps["run"]
    step_b = seed_run_with_steps["steps"][1]
    step_b.stale = True
    run.status = "paused"
    await memory_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await ignore_stale(db=memory_db, run_id=run.id, user_id=seed_user.id + 999)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_ignore_stale_run_not_found(memory_db, seed_user, seed_template):
    """ignore_stale：流水线不存在返回 404"""
    with pytest.raises(HTTPException) as exc_info:
        await ignore_stale(db=memory_db, run_id=99999, user_id=seed_user.id)
    assert exc_info.value.status_code == 404
