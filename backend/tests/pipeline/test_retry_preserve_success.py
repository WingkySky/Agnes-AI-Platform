# =====================================================
# Task 29.8: 步骤级重试跳过成功元素测试
#
# 覆盖 backend/app/services/pipeline/run_service.py:
#   - retry_step_preserve_success（保留 success 元素，重跑 failed）
#
# 测试场景：
#   1. 保留 success 元素：preserved_items 写入，items 仅留 failed
#   2. 无 success 元素时 preserved_items 为空
#   3. 全部 success 时 preserved_items 含全部，items 为空
#   4. 重置 step 状态为 pending
#   5. 重置 run 状态为 pending
#   6. 调用 resume_pipeline 恢复执行
#   7. run 状态 running 时返回 400
#   8. 步骤状态非 failed/skipped/success 时返回 400
#   9. 非本人流水线返回 403
#  10. 流水线/步骤不存在返回 404
#  11. 混合状态：1 success + 2 failed → preserved_count=1，items 仅留 2 failed
# =====================================================

import pytest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.services.pipeline.run_service import retry_step_preserve_success
from app.models.pipeline import PipelineRun
from tests.conftest import _make_step


# ---------- 辅助函数 ----------

def _make_item(item_id: str, status: str) -> dict:
    """构造单个 item"""
    return {
        "id": item_id,
        "name": f"项目{item_id}",
        "status": status,
        "image_url": "url.jpg" if status == "success" else "",
        "error": None if status == "success" else "失败原因",
    }


def _output_mixed() -> dict:
    """构造混合状态的 output_data：1 成功 + 2 失败"""
    items = [
        _make_item("item_001", "success"),
        _make_item("item_002", "failed"),
        _make_item("item_003", "failed"),
    ]
    return {
        "items": items,
        "success_count": 1,
        "failed_count": 2,
    }


# ---------- 测试用例 ----------

@pytest.mark.asyncio
async def test_retry_preserve_success_separates_items(memory_db, seed_user, seed_template, seed_run_with_steps):
    """保留 success 元素：preserved_items 写入，items 仅留 failed"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    step_a.status = "failed"
    step_a.output_data = _output_mixed()
    run.status = "paused"
    await memory_db.commit()

    with patch(
        "app.services.pipeline.run_service.resume_pipeline",
        new_callable=AsyncMock,
    ):
        result = await retry_step_preserve_success(
            db=memory_db, run_id=run.id, step_key="step_a", user_id=seed_user.id,
        )

    assert result["preserved_count"] == 1

    await memory_db.refresh(step_a)
    # preserved_items 含 1 个 success
    assert len(step_a.output_data["preserved_items"]) == 1
    assert step_a.output_data["preserved_items"][0]["id"] == "item_001"
    # items 仅留 2 个 failed
    assert len(step_a.output_data["items"]) == 2
    assert all(it["status"] == "failed" for it in step_a.output_data["items"])


@pytest.mark.asyncio
async def test_retry_preserve_success_no_success_items(memory_db, seed_user, seed_template, seed_run_with_steps):
    """无 success 元素时 preserved_items 为空"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    step_a.status = "failed"
    step_a.output_data = {
        "items": [_make_item("item_001", "failed"), _make_item("item_002", "failed")],
        "success_count": 0,
        "failed_count": 2,
    }
    run.status = "paused"
    await memory_db.commit()

    with patch(
        "app.services.pipeline.run_service.resume_pipeline",
        new_callable=AsyncMock,
    ):
        result = await retry_step_preserve_success(
            db=memory_db, run_id=run.id, step_key="step_a", user_id=seed_user.id,
        )

    assert result["preserved_count"] == 0

    await memory_db.refresh(step_a)
    assert step_a.output_data["preserved_items"] == []
    # items 仍是原来的 2 个 failed
    assert len(step_a.output_data["items"]) == 2


@pytest.mark.asyncio
async def test_retry_preserve_success_all_success(memory_db, seed_user, seed_template, seed_run_with_steps):
    """全部 success 时 preserved_items 含全部，items 为空"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    step_a.status = "success"
    step_a.output_data = {
        "items": [_make_item("item_001", "success"), _make_item("item_002", "success")],
        "success_count": 2,
        "failed_count": 0,
    }
    run.status = "paused"
    await memory_db.commit()

    with patch(
        "app.services.pipeline.run_service.resume_pipeline",
        new_callable=AsyncMock,
    ):
        result = await retry_step_preserve_success(
            db=memory_db, run_id=run.id, step_key="step_a", user_id=seed_user.id,
        )

    assert result["preserved_count"] == 2

    await memory_db.refresh(step_a)
    assert len(step_a.output_data["preserved_items"]) == 2
    assert len(step_a.output_data["items"]) == 0


@pytest.mark.asyncio
async def test_retry_preserve_success_resets_step_status(memory_db, seed_user, seed_template, seed_run_with_steps):
    """重置 step 状态为 pending"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    step_a.status = "failed"
    step_a.error_message = "错误"
    step_a.retry_count = 3
    step_a.output_data = _output_mixed()
    run.status = "paused"
    await memory_db.commit()

    with patch(
        "app.services.pipeline.run_service.resume_pipeline",
        new_callable=AsyncMock,
    ):
        await retry_step_preserve_success(
            db=memory_db, run_id=run.id, step_key="step_a", user_id=seed_user.id,
        )

    await memory_db.refresh(step_a)
    assert step_a.status == "pending"
    assert step_a.error_message is None
    assert step_a.retry_count == 0
    assert step_a.started_at is None
    assert step_a.finished_at is None


@pytest.mark.asyncio
async def test_retry_preserve_success_resets_run_status(memory_db, seed_user, seed_template, seed_run_with_steps):
    """重置 run 状态为 pending"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    step_a.status = "failed"
    step_a.output_data = _output_mixed()
    run.status = "paused"
    run.error_message = "错误"
    await memory_db.commit()

    with patch(
        "app.services.pipeline.run_service.resume_pipeline",
        new_callable=AsyncMock,
    ):
        await retry_step_preserve_success(
            db=memory_db, run_id=run.id, step_key="step_a", user_id=seed_user.id,
        )

    await memory_db.refresh(run)
    assert run.status == "pending"
    assert run.error_message is None
    assert run.finished_at is None


@pytest.mark.asyncio
async def test_retry_preserve_success_calls_resume(memory_db, seed_user, seed_template, seed_run_with_steps):
    """调用 resume_pipeline 恢复执行"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    step_a.status = "failed"
    step_a.output_data = _output_mixed()
    run.status = "paused"
    await memory_db.commit()

    with patch(
        "app.services.pipeline.run_service.resume_pipeline",
        new_callable=AsyncMock,
    ) as mock_resume:
        await retry_step_preserve_success(
            db=memory_db, run_id=run.id, step_key="step_a", user_id=seed_user.id,
        )
        mock_resume.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_preserve_success_running_rejected(memory_db, seed_user, seed_template, seed_run_with_steps):
    """run 状态 running 时返回 400"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    step_a.status = "failed"
    step_a.output_data = _output_mixed()
    run.status = "running"
    await memory_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await retry_step_preserve_success(
            db=memory_db, run_id=run.id, step_key="step_a", user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 400
    assert "运行中" in exc_info.value.detail


@pytest.mark.asyncio
async def test_retry_preserve_success_invalid_step_status(memory_db, seed_user, seed_template, seed_run_with_steps):
    """步骤状态非 failed/skipped/success 时返回 400"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    # step_a 状态为 pending（不在允许列表中）
    step_a.status = "pending"
    step_a.output_data = _output_mixed()
    run.status = "paused"
    await memory_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await retry_step_preserve_success(
            db=memory_db, run_id=run.id, step_key="step_a", user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 400
    assert "只能重试失败/被跳过/已完成的步骤" in exc_info.value.detail


@pytest.mark.asyncio
async def test_retry_preserve_success_skipped_step_allowed(memory_db, seed_user, seed_template, seed_run_with_steps):
    """步骤状态为 skipped 时允许重试"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    step_a.status = "skipped"
    step_a.output_data = _output_mixed()
    run.status = "paused"
    await memory_db.commit()

    with patch(
        "app.services.pipeline.run_service.resume_pipeline",
        new_callable=AsyncMock,
    ):
        result = await retry_step_preserve_success(
            db=memory_db, run_id=run.id, step_key="step_a", user_id=seed_user.id,
        )

    assert result["preserved_count"] == 1


@pytest.mark.asyncio
async def test_retry_preserve_success_wrong_user(memory_db, seed_user, seed_template, seed_run_with_steps):
    """非本人流水线返回 403"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    step_a.status = "failed"
    step_a.output_data = _output_mixed()
    run.status = "paused"
    await memory_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await retry_step_preserve_success(
            db=memory_db, run_id=run.id, step_key="step_a",
            user_id=seed_user.id + 999,
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_retry_preserve_success_run_not_found(memory_db, seed_user, seed_template):
    """流水线不存在返回 404"""
    with pytest.raises(HTTPException) as exc_info:
        await retry_step_preserve_success(
            db=memory_db, run_id=99999, step_key="step_a", user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_retry_preserve_success_step_not_found(memory_db, seed_user, seed_template, seed_run_with_steps):
    """步骤不存在返回 404"""
    run = seed_run_with_steps["run"]

    with pytest.raises(HTTPException) as exc_info:
        await retry_step_preserve_success(
            db=memory_db, run_id=run.id, step_key="not_exists", user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_retry_preserve_success_mixed_status(memory_db, seed_user, seed_template, seed_run_with_steps):
    """混合状态：1 success + 2 failed → preserved_count=1，items 仅留 2 failed"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    step_a.status = "failed"
    step_a.output_data = {
        "items": [
            _make_item("char_001", "success"),
            _make_item("char_002", "failed"),
            _make_item("char_003", "failed"),
            _make_item("char_004", "success"),  # 另一个 success
            _make_item("char_005", "failed"),
        ],
        "success_count": 2,
        "failed_count": 3,
    }
    run.status = "paused"
    await memory_db.commit()

    with patch(
        "app.services.pipeline.run_service.resume_pipeline",
        new_callable=AsyncMock,
    ):
        result = await retry_step_preserve_success(
            db=memory_db, run_id=run.id, step_key="step_a", user_id=seed_user.id,
        )

    # 2 个 success 被保留
    assert result["preserved_count"] == 2

    await memory_db.refresh(step_a)
    # preserved_items 含 2 个 success
    preserved_ids = {it["id"] for it in step_a.output_data["preserved_items"]}
    assert preserved_ids == {"char_001", "char_004"}
    # items 仅留 3 个 failed
    assert len(step_a.output_data["items"]) == 3
    assert all(it["status"] == "failed" for it in step_a.output_data["items"])
