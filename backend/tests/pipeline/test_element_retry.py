# =====================================================
# Task 29.3: 元素级重试测试（retry_step_item / execute_single）
#
# 覆盖 backend/app/services/pipeline/run_service.py:retry_step_item
# 测试场景：
#   1. 成功重试：execute_single 返回 success，items/summary 正确更新
#   2. item_id 未找到：返回 404
#   3. 步骤 stale：返回 409
#   4. 无 items 列表：返回 400
#   5. 执行器不支持 execute_single：返回 400
#   6. 已确认步骤重试后 requires_reconfirmation=True，confirmation_status 重置为 pending
#   7. 未确认步骤重试后 requires_reconfirmation=False
#   8. prompt_override 与 seed 参数透传到 SingleItemContext
#   9. LLM 失败时返回 failed 状态，items 更新带 error
#  10. 图片失败时返回 failed 状态，items 更新带 error
#  11. 兼容字段同步：output_data.images 同步更新
#  12. summary 重新统计 success/failed 计数
# =====================================================

import pytest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.services.pipeline.run_service import retry_step_item
from app.services.pipeline.steps.base import ItemResult
from tests.conftest import _make_step


# ---------- 辅助函数 ----------

def _make_step_config(step_key: str = "step_char", step_type: str = "character_gen") -> dict:
    """构造模板中的步骤配置"""
    return {
        "key": step_key,
        "type": step_type,
        "name": "角色生成",
        "config": {
            "character_source": "step_storyboard.characters",
            "image_config": {"model": "test-model"},
        },
    }


def _make_output_data_with_items(items: list) -> dict:
    """构造 output_data，包含 items + summary"""
    success_count = sum(1 for it in items if it.get("status") == "success")
    failed_count = sum(1 for it in items if it.get("status") == "failed")
    return {
        "items": items,
        "summary": {
            "total": len(items),
            "success_count": success_count,
            "failed_count": failed_count,
        },
        "success_count": success_count,
        "failed_count": failed_count,
    }


# ---------- 测试用例 ----------

@pytest.mark.asyncio
async def test_retry_step_item_success(memory_db, seed_user, seed_template):
    """成功重试：execute_single 返回 success，items/summary 正确更新"""
    from app.models.pipeline import PipelineRun

    # 1. 构造 run + 一个 character_gen 步骤，items 中有一个失败的角色
    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="paused",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    # 修改模板，添加一个 character_gen 步骤
    seed_template.steps_config = [_make_step_config()]
    await memory_db.commit()

    items = [
        {"id": "char_001", "name": "主角", "setting_text": "旧描述",
         "image_url": "old.jpg", "status": "success", "seed": 111, "error": None},
        {"id": "char_002", "name": "配角", "setting_text": "",
         "image_url": "", "status": "failed", "seed": None, "error": "图片生成失败"},
    ]
    step = _make_step(
        run.id, "step_char", "角色生成", "character_gen", 0,
        status="success",
        output_data=_make_output_data_with_items(items),
    )
    memory_db.add(step)
    await memory_db.commit()
    await memory_db.refresh(step)

    # 2. Mock executor.execute_single 返回成功
    new_item = {
        "id": "char_002", "name": "配角", "setting_text": "新描述",
        "image_url": "new.jpg", "status": "success", "seed": 222, "error": None,
    }
    mock_result = ItemResult(status="success", item=new_item, error=None)

    with patch(
        "app.services.pipeline.steps.create_step_executor"
    ) as mock_create:
        mock_executor = AsyncMock()
        mock_executor.execute_single = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_executor

        result = await retry_step_item(
            db=memory_db,
            run_id=run.id,
            step_key="step_char",
            item_id="char_002",
            user_id=seed_user.id,
        )

    # 3. 验证返回值
    assert result["status"] == "success"
    assert result["item"]["image_url"] == "new.jpg"
    assert result["requires_reconfirmation"] is False

    # 4. 验证 DB 中 items 已更新
    await memory_db.refresh(step)
    updated_items = step.output_data["items"]
    assert updated_items[1]["image_url"] == "new.jpg"
    assert updated_items[1]["status"] == "success"
    # summary 重新统计
    assert step.output_data["success_count"] == 2
    assert step.output_data["failed_count"] == 0


@pytest.mark.asyncio
async def test_retry_step_item_not_found(memory_db, seed_user, seed_template):
    """item_id 未找到时返回 404"""
    from app.models.pipeline import PipelineRun

    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="paused",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    seed_template.steps_config = [_make_step_config()]
    await memory_db.commit()

    items = [
        {"id": "char_001", "name": "主角", "status": "success"},
    ]
    step = _make_step(
        run.id, "step_char", "角色生成", "character_gen", 0,
        output_data=_make_output_data_with_items(items),
    )
    memory_db.add(step)
    await memory_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await retry_step_item(
            db=memory_db,
            run_id=run.id,
            step_key="step_char",
            item_id="not_exists",
            user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 404
    assert "未在步骤 items 中找到" in exc_info.value.detail


@pytest.mark.asyncio
async def test_retry_step_item_stale_rejected(memory_db, seed_user, seed_template):
    """步骤 stale 时返回 409"""
    from app.models.pipeline import PipelineRun

    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="paused",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    seed_template.steps_config = [_make_step_config()]
    await memory_db.commit()

    items = [{"id": "char_001", "name": "主角", "status": "success"}]
    step = _make_step(
        run.id, "step_char", "角色生成", "character_gen", 0,
        output_data=_make_output_data_with_items(items),
        stale=True,
    )
    memory_db.add(step)
    await memory_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await retry_step_item(
            db=memory_db,
            run_id=run.id,
            step_key="step_char",
            item_id="char_001",
            user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 409
    assert "stale" in exc_info.value.detail


@pytest.mark.asyncio
async def test_retry_step_item_no_items(memory_db, seed_user, seed_template):
    """步骤无 items 列表时返回 400"""
    from app.models.pipeline import PipelineRun

    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="paused",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    seed_template.steps_config = [_make_step_config()]
    await memory_db.commit()

    # output_data 中没有 items 字段
    step = _make_step(
        run.id, "step_char", "角色生成", "character_gen", 0,
        output_data={"text": "some text"},
    )
    memory_db.add(step)
    await memory_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await retry_step_item(
            db=memory_db,
            run_id=run.id,
            step_key="step_char",
            item_id="char_001",
            user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 400
    assert "无 items 列表" in exc_info.value.detail


@pytest.mark.asyncio
async def test_retry_step_item_not_implemented(memory_db, seed_user, seed_template):
    """执行器不支持 execute_single 时返回 400"""
    from app.models.pipeline import PipelineRun

    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="paused",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    seed_template.steps_config = [_make_step_config()]
    await memory_db.commit()

    items = [{"id": "char_001", "name": "主角", "status": "success"}]
    step = _make_step(
        run.id, "step_char", "角色生成", "character_gen", 0,
        output_data=_make_output_data_with_items(items),
    )
    memory_db.add(step)
    await memory_db.commit()

    with patch(
        "app.services.pipeline.steps.create_step_executor"
    ) as mock_create:
        mock_executor = AsyncMock()
        mock_executor.execute_single = AsyncMock(
            side_effect=NotImplementedError("此步骤类型不支持元素级重试")
        )
        mock_create.return_value = mock_executor

        with pytest.raises(HTTPException) as exc_info:
            await retry_step_item(
                db=memory_db,
                run_id=run.id,
                step_key="step_char",
                item_id="char_001",
                user_id=seed_user.id,
            )
        assert exc_info.value.status_code == 400
        assert "不支持元素级重试" in exc_info.value.detail


@pytest.mark.asyncio
async def test_retry_step_item_requires_reconfirmation(memory_db, seed_user, seed_template):
    """已确认步骤重试后 requires_reconfirmation=True，confirmation_status 重置为 pending"""
    from app.models.pipeline import PipelineRun

    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="paused",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    seed_template.steps_config = [_make_step_config()]
    await memory_db.commit()

    items = [{"id": "char_001", "name": "主角", "status": "success"}]
    step = _make_step(
        run.id, "step_char", "角色生成", "character_gen", 0,
        output_data=_make_output_data_with_items(items),
        confirmation_status="confirmed",
    )
    memory_db.add(step)
    await memory_db.commit()
    await memory_db.refresh(step)

    new_item = {
        "id": "char_001", "name": "主角", "setting_text": "新描述",
        "image_url": "new.jpg", "status": "success", "seed": 999, "error": None,
    }
    mock_result = ItemResult(status="success", item=new_item, error=None)

    with patch(
        "app.services.pipeline.steps.create_step_executor"
    ) as mock_create:
        mock_executor = AsyncMock()
        mock_executor.execute_single = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_executor

        result = await retry_step_item(
            db=memory_db,
            run_id=run.id,
            step_key="step_char",
            item_id="char_001",
            user_id=seed_user.id,
        )

    # 验证返回值中 requires_reconfirmation=True
    assert result["requires_reconfirmation"] is True

    # 验证 DB 中 confirmation_status 已重置为 pending
    await memory_db.refresh(step)
    assert step.confirmation_status == "pending"


@pytest.mark.asyncio
async def test_retry_step_item_no_reconfirmation_when_pending(memory_db, seed_user, seed_template):
    """未确认步骤重试后 requires_reconfirmation=False"""
    from app.models.pipeline import PipelineRun

    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="paused",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    seed_template.steps_config = [_make_step_config()]
    await memory_db.commit()

    items = [{"id": "char_001", "name": "主角", "status": "failed", "error": "x"}]
    step = _make_step(
        run.id, "step_char", "角色生成", "character_gen", 0,
        output_data=_make_output_data_with_items(items),
        confirmation_status=None,  # 从未确认
    )
    memory_db.add(step)
    await memory_db.commit()

    new_item = {
        "id": "char_001", "name": "主角", "setting_text": "新描述",
        "image_url": "new.jpg", "status": "success", "seed": 999, "error": None,
    }
    mock_result = ItemResult(status="success", item=new_item, error=None)

    with patch(
        "app.services.pipeline.steps.create_step_executor"
    ) as mock_create:
        mock_executor = AsyncMock()
        mock_executor.execute_single = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_executor

        result = await retry_step_item(
            db=memory_db,
            run_id=run.id,
            step_key="step_char",
            item_id="char_001",
            user_id=seed_user.id,
        )

    assert result["requires_reconfirmation"] is False


@pytest.mark.asyncio
async def test_retry_step_item_prompt_override_passed(memory_db, seed_user, seed_template):
    """prompt_override 与 seed 参数透传到 SingleItemContext"""
    from app.models.pipeline import PipelineRun

    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="paused",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    seed_template.steps_config = [_make_step_config()]
    await memory_db.commit()

    items = [{"id": "char_001", "name": "主角", "status": "failed", "error": "x"}]
    step = _make_step(
        run.id, "step_char", "角色生成", "character_gen", 0,
        output_data=_make_output_data_with_items(items),
    )
    memory_db.add(step)
    await memory_db.commit()

    new_item = {
        "id": "char_001", "name": "主角", "setting_text": "用户自定义 prompt",
        "image_url": "new.jpg", "status": "success", "seed": 12345, "error": None,
    }
    mock_result = ItemResult(status="success", item=new_item, error=None)

    with patch(
        "app.services.pipeline.steps.create_step_executor"
    ) as mock_create:
        mock_executor = AsyncMock()
        mock_executor.execute_single = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_executor

        await retry_step_item(
            db=memory_db,
            run_id=run.id,
            step_key="step_char",
            item_id="char_001",
            user_id=seed_user.id,
            prompt_override="用户自定义 prompt",
            seed=12345,
        )

    # 验证 execute_single 被调用，且 SingleItemContext 中 prompt_override / seed 已透传
    mock_executor.execute_single.assert_awaited_once()
    single_ctx = mock_executor.execute_single.await_args.args[0]
    assert single_ctx.prompt_override == "用户自定义 prompt"
    assert single_ctx.seed == 12345


@pytest.mark.asyncio
async def test_retry_step_item_llm_failure(memory_db, seed_user, seed_template):
    """LLM 失败时返回 failed 状态，items 更新带 error"""
    from app.models.pipeline import PipelineRun

    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="paused",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    seed_template.steps_config = [_make_step_config()]
    await memory_db.commit()

    items = [{"id": "char_001", "name": "主角", "status": "success"}]
    step = _make_step(
        run.id, "step_char", "角色生成", "character_gen", 0,
        output_data=_make_output_data_with_items(items),
    )
    memory_db.add(step)
    await memory_db.commit()

    failed_item = {
        "id": "char_001", "name": "主角", "setting_text": "",
        "image_url": "", "status": "failed", "seed": 1,
        "error": "LLM 生成失败: timeout",
    }
    mock_result = ItemResult(
        status="failed", item=failed_item, error="LLM 生成失败: timeout"
    )

    with patch(
        "app.services.pipeline.steps.create_step_executor"
    ) as mock_create:
        mock_executor = AsyncMock()
        mock_executor.execute_single = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_executor

        result = await retry_step_item(
            db=memory_db,
            run_id=run.id,
            step_key="step_char",
            item_id="char_001",
            user_id=seed_user.id,
        )

    assert result["status"] == "failed"
    assert "LLM 生成失败" in result["item"]["error"]

    await memory_db.refresh(step)
    assert step.output_data["items"][0]["status"] == "failed"
    assert step.output_data["failed_count"] == 1
    assert step.output_data["success_count"] == 0


@pytest.mark.asyncio
async def test_retry_step_item_image_failure(memory_db, seed_user, seed_template):
    """图片生成失败时返回 failed 状态，items 更新带 error"""
    from app.models.pipeline import PipelineRun

    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="paused",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    seed_template.steps_config = [_make_step_config()]
    await memory_db.commit()

    items = [{"id": "char_001", "name": "主角", "status": "success"}]
    step = _make_step(
        run.id, "step_char", "角色生成", "character_gen", 0,
        output_data=_make_output_data_with_items(items),
    )
    memory_db.add(step)
    await memory_db.commit()

    failed_item = {
        "id": "char_001", "name": "主角", "setting_text": "新描述",
        "image_url": "", "status": "failed", "seed": 1,
        "error": "图片生成失败: timeout",
    }
    mock_result = ItemResult(
        status="failed", item=failed_item, error="图片生成失败: timeout"
    )

    with patch(
        "app.services.pipeline.steps.create_step_executor"
    ) as mock_create:
        mock_executor = AsyncMock()
        mock_executor.execute_single = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_executor

        result = await retry_step_item(
            db=memory_db,
            run_id=run.id,
            step_key="step_char",
            item_id="char_001",
            user_id=seed_user.id,
        )

    assert result["status"] == "failed"
    assert "图片生成失败" in result["item"]["error"]

    await memory_db.refresh(step)
    assert step.output_data["items"][0]["status"] == "failed"
    assert step.output_data["items"][0]["setting_text"] == "新描述"
    assert step.output_data["failed_count"] == 1


@pytest.mark.asyncio
async def test_retry_step_item_sync_images_field(memory_db, seed_user, seed_template):
    """兼容字段同步：output_data.images 同步更新"""
    from app.models.pipeline import PipelineRun

    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="paused",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    seed_template.steps_config = [_make_step_config()]
    await memory_db.commit()

    items = [
        {"id": "char_001", "name": "主角", "status": "failed", "error": "x"},
    ]
    output_data = _make_output_data_with_items(items)
    # 加上兼容字段 images（旧版字段）
    output_data["images"] = list(items)

    step = _make_step(
        run.id, "step_char", "角色生成", "character_gen", 0,
        output_data=output_data,
    )
    memory_db.add(step)
    await memory_db.commit()

    new_item = {
        "id": "char_001", "name": "主角", "setting_text": "新描述",
        "image_url": "new.jpg", "status": "success", "seed": 1, "error": None,
    }
    mock_result = ItemResult(status="success", item=new_item, error=None)

    with patch(
        "app.services.pipeline.steps.create_step_executor"
    ) as mock_create:
        mock_executor = AsyncMock()
        mock_executor.execute_single = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_executor

        await retry_step_item(
            db=memory_db,
            run_id=run.id,
            step_key="step_char",
            item_id="char_001",
            user_id=seed_user.id,
        )

    # 验证兼容字段 images 也同步更新
    await memory_db.refresh(step)
    assert step.output_data["images"][0]["image_url"] == "new.jpg"
    assert step.output_data["images"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_retry_step_item_summary_recount(memory_db, seed_user, seed_template):
    """summary 重新统计 success/failed 计数"""
    from app.models.pipeline import PipelineRun

    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="paused",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    seed_template.steps_config = [_make_step_config()]
    await memory_db.commit()

    # 3 个 item：1 成功 2 失败
    items = [
        {"id": "char_001", "name": "主角", "status": "success"},
        {"id": "char_002", "name": "配角A", "status": "failed", "error": "x"},
        {"id": "char_003", "name": "配角B", "status": "failed", "error": "y"},
    ]
    step = _make_step(
        run.id, "step_char", "角色生成", "character_gen", 0,
        output_data=_make_output_data_with_items(items),
    )
    memory_db.add(step)
    await memory_db.commit()

    # 重试 char_002，成功
    new_item = {
        "id": "char_002", "name": "配角A", "setting_text": "新描述",
        "image_url": "new.jpg", "status": "success", "seed": 1, "error": None,
    }
    mock_result = ItemResult(status="success", item=new_item, error=None)

    with patch(
        "app.services.pipeline.steps.create_step_executor"
    ) as mock_create:
        mock_executor = AsyncMock()
        mock_executor.execute_single = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_executor

        await retry_step_item(
            db=memory_db,
            run_id=run.id,
            step_key="step_char",
            item_id="char_002",
            user_id=seed_user.id,
        )

    # 验证 summary 重新统计：2 成功 1 失败
    await memory_db.refresh(step)
    assert step.output_data["success_count"] == 2
    assert step.output_data["failed_count"] == 1
    summary = step.output_data.get("summary", {})
    assert summary.get("success_count") == 2
    assert summary.get("failed_count") == 1


@pytest.mark.asyncio
async def test_retry_step_item_wrong_user(memory_db, seed_user, seed_template):
    """非本人流水线返回 403"""
    from app.models.pipeline import PipelineRun

    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="paused",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    seed_template.steps_config = [_make_step_config()]
    await memory_db.commit()

    items = [{"id": "char_001", "name": "主角", "status": "success"}]
    step = _make_step(
        run.id, "step_char", "角色生成", "character_gen", 0,
        output_data=_make_output_data_with_items(items),
    )
    memory_db.add(step)
    await memory_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await retry_step_item(
            db=memory_db,
            run_id=run.id,
            step_key="step_char",
            item_id="char_001",
            user_id=seed_user.id + 999,  # 不同的 user_id
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_retry_step_item_run_not_found(memory_db, seed_user, seed_template):
    """流水线不存在返回 404"""
    with pytest.raises(HTTPException) as exc_info:
        await retry_step_item(
            db=memory_db,
            run_id=99999,
            step_key="step_char",
            item_id="char_001",
            user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 404
    assert "流水线不存在" in exc_info.value.detail


@pytest.mark.asyncio
async def test_retry_step_item_step_not_found(memory_db, seed_user, seed_template):
    """步骤不存在返回 404"""
    from app.models.pipeline import PipelineRun

    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="paused",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    with pytest.raises(HTTPException) as exc_info:
        await retry_step_item(
            db=memory_db,
            run_id=run.id,
            step_key="not_exists",
            item_id="char_001",
            user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 404
    assert "步骤不存在" in exc_info.value.detail


@pytest.mark.asyncio
async def test_retry_step_item_match_by_index(memory_db, seed_user, seed_template):
    """通过 index 字段匹配 item（兼容字段）"""
    from app.models.pipeline import PipelineRun

    run = PipelineRun(
        template_id=seed_template.id,
        user_id=seed_user.id,
        inputs={},
        status="paused",
    )
    memory_db.add(run)
    await memory_db.commit()
    await memory_db.refresh(run)

    seed_template.steps_config = [_make_step_config()]
    await memory_db.commit()

    # item 用 index 字段作为 ID
    items = [
        {"index": 0, "name": "主角", "status": "failed", "error": "x"},
    ]
    step = _make_step(
        run.id, "step_char", "角色生成", "character_gen", 0,
        output_data=_make_output_data_with_items(items),
    )
    memory_db.add(step)
    await memory_db.commit()

    new_item = {
        "index": 0, "name": "主角", "setting_text": "新描述",
        "image_url": "new.jpg", "status": "success", "seed": 1, "error": None,
    }
    mock_result = ItemResult(status="success", item=new_item, error=None)

    with patch(
        "app.services.pipeline.steps.create_step_executor"
    ) as mock_create:
        mock_executor = AsyncMock()
        mock_executor.execute_single = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_executor

        # 用 index 值 "0" 作为 item_id
        result = await retry_step_item(
            db=memory_db,
            run_id=run.id,
            step_key="step_char",
            item_id="0",
            user_id=seed_user.id,
        )

    assert result["status"] == "success"
    assert result["item"]["image_url"] == "new.jpg"