# =====================================================
# Task 29.7: 版本历史与回滚测试
#
# 覆盖 backend/app/services/pipeline/run_service.py:
#   - list_step_revisions（查询版本历史）
#   - rollback_step_revision（回滚到指定版本）
#   - _save_step_output_revision（版本快照保存，含上限清理）
#
# 测试场景：
#   1. list_step_revisions：返回空列表（无版本）
#   2. list_step_revisions：返回所有版本，按 revision 降序
#   3. list_step_revisions：非本人流水线返回 403
#   4. list_step_revisions：流水线/步骤不存在返回 404
#   5. rollback_step_revision：成功回滚到指定版本
#   6. rollback_step_revision：回滚后下游步骤被标记 stale
#   7. rollback_step_revision：回滚前保存当前快照（便于反向回滚）
#   8. rollback_step_revision：revision 不存在返回 404
#   9. rollback_step_revision：run 状态 running 返回 409
#  10. rollback_step_revision：非本人流水线返回 403
#  11. rollback_step_revision：流水线/步骤不存在返回 404
#  12. _save_step_output_revision：超过上限时删除最旧版本
# =====================================================

import pytest
from sqlalchemy import select

from fastapi import HTTPException

from app.services.pipeline.run_service import (
    list_step_revisions,
    rollback_step_revision,
    _save_step_output_revision,
    MAX_REVISIONS_PER_RUN,
)
from app.models.pipeline import PipelineRun
from app.models.pipeline_step_output_revision import PipelineStepOutputRevision
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


async def _add_revision(db, run_id, step_key, rev_num, items_count, user_id=None):
    """直接插入一条版本记录"""
    rev = PipelineStepOutputRevision(
        run_id=run_id,
        step_key=step_key,
        revision=rev_num,
        output_data=_output_with_items(items_count),
        edited_by=user_id,
        edited_at=None,
        change_summary=f"测试版本 {rev_num}",
    )
    db.add(rev)
    await db.commit()
    return rev


# ---------- list_step_revisions 测试 ----------

@pytest.mark.asyncio
async def test_list_revisions_empty(memory_db, seed_user, seed_template, seed_run_with_steps):
    """list_step_revisions：返回空列表（无版本）"""
    run = seed_run_with_steps["run"]

    result = await list_step_revisions(
        db=memory_db, run_id=run.id, step_key="step_a", user_id=seed_user.id
    )
    assert result == []


@pytest.mark.asyncio
async def test_list_revisions_desc_order(memory_db, seed_user, seed_template, seed_run_with_steps):
    """list_step_revisions：返回所有版本，按 revision 降序"""
    run = seed_run_with_steps["run"]

    # 插入 3 个版本
    await _add_revision(memory_db, run.id, "step_a", 1, 2, seed_user.id)
    await _add_revision(memory_db, run.id, "step_a", 2, 3, seed_user.id)
    await _add_revision(memory_db, run.id, "step_a", 3, 4, seed_user.id)

    result = await list_step_revisions(
        db=memory_db, run_id=run.id, step_key="step_a", user_id=seed_user.id
    )

    assert len(result) == 3
    # 降序：3, 2, 1
    assert result[0]["revision"] == 3
    assert result[1]["revision"] == 2
    assert result[2]["revision"] == 1
    # 验证字段
    assert result[0]["change_summary"] == "测试版本 3"
    assert result[0]["output_data_size"] > 0


@pytest.mark.asyncio
async def test_list_revisions_wrong_user(memory_db, seed_user, seed_template, seed_run_with_steps):
    """list_step_revisions：非本人流水线返回 403"""
    run = seed_run_with_steps["run"]

    with pytest.raises(HTTPException) as exc_info:
        await list_step_revisions(
            db=memory_db, run_id=run.id, step_key="step_a",
            user_id=seed_user.id + 999,
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_revisions_run_not_found(memory_db, seed_user):
    """list_step_revisions：流水线不存在返回 404"""
    with pytest.raises(HTTPException) as exc_info:
        await list_step_revisions(
            db=memory_db, run_id=99999, step_key="step_a", user_id=seed_user.id
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_revisions_step_not_found(memory_db, seed_user, seed_template, seed_run_with_steps):
    """list_step_revisions：步骤不存在返回 404"""
    run = seed_run_with_steps["run"]

    with pytest.raises(HTTPException) as exc_info:
        await list_step_revisions(
            db=memory_db, run_id=run.id, step_key="not_exists", user_id=seed_user.id
        )
    assert exc_info.value.status_code == 404


# ---------- rollback_step_revision 测试 ----------

@pytest.mark.asyncio
async def test_rollback_success(memory_db, seed_user, seed_template, seed_run_with_steps):
    """rollback_step_revision：成功回滚到指定版本"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    # 当前 output_data 有 3 个 items
    step_a.output_data = _output_with_items(3)
    await memory_db.commit()

    # 插入历史版本（revision=1 时只有 1 个 item）
    await _add_revision(memory_db, run.id, "step_a", 1, 1, seed_user.id)

    result = await rollback_step_revision(
        db=memory_db, run_id=run.id, step_key="step_a",
        revision=1, user_id=seed_user.id,
    )

    assert result["rolled_back_to"] == 1

    # 验证 DB 中 output_data 已回滚（1 个 item）
    await memory_db.refresh(step_a)
    assert len(step_a.output_data["items"]) == 1


@pytest.mark.asyncio
async def test_rollback_marks_downstream_stale(memory_db, seed_user, seed_template, seed_run_with_steps):
    """rollback_step_revision：回滚后下游步骤被标记 stale"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    step_a.output_data = _output_with_items(3)
    await memory_db.commit()

    await _add_revision(memory_db, run.id, "step_a", 1, 1, seed_user.id)

    result = await rollback_step_revision(
        db=memory_db, run_id=run.id, step_key="step_a",
        revision=1, user_id=seed_user.id,
    )

    # A→B→C，编辑 A 应让 B、C 都 stale
    assert "step_b" in result["downstream_marked_stale"]
    assert "step_c" in result["downstream_marked_stale"]


@pytest.mark.asyncio
async def test_rollback_saves_pre_snapshot(memory_db, seed_user, seed_template, seed_run_with_steps):
    """rollback_step_revision：回滚前保存当前快照（便于反向回滚）"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    # 当前有 3 个 items
    step_a.output_data = _output_with_items(3)
    await memory_db.commit()

    # 插入目标版本（1 个 item）
    await _add_revision(memory_db, run.id, "step_a", 1, 1, seed_user.id)

    await rollback_step_revision(
        db=memory_db, run_id=run.id, step_key="step_a",
        revision=1, user_id=seed_user.id,
    )

    # 验证现在有 2 条 revision：原 revision=1，加上回滚前快照 revision=2
    revs = (await memory_db.execute(
        select(PipelineStepOutputRevision).where(
            PipelineStepOutputRevision.run_id == run.id,
            PipelineStepOutputRevision.step_key == "step_a",
        ).order_by(PipelineStepOutputRevision.revision.asc())
    )).scalars().all()
    assert len(revs) == 2
    # revision=2 是回滚前快照，应有 3 个 items
    assert revs[1].revision == 2
    assert len(revs[1].output_data["items"]) == 3
    assert "回滚到 revision=1 前快照" in revs[1].change_summary


@pytest.mark.asyncio
async def test_rollback_revision_not_found(memory_db, seed_user, seed_template, seed_run_with_steps):
    """rollback_step_revision：revision 不存在返回 404"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]
    step_a.output_data = _output_with_items(2)
    await memory_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await rollback_step_revision(
            db=memory_db, run_id=run.id, step_key="step_a",
            revision=999, user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 404
    assert "未找到 revision=999" in exc_info.value.detail


@pytest.mark.asyncio
async def test_rollback_running_rejected(memory_db, seed_user, seed_template, seed_run_with_steps):
    """rollback_step_revision：run 状态 running 返回 409"""
    run = seed_run_with_steps["run"]
    run.status = "running"
    step_a = seed_run_with_steps["steps"][0]
    step_a.output_data = _output_with_items(2)
    await memory_db.commit()

    await _add_revision(memory_db, run.id, "step_a", 1, 1, seed_user.id)

    with pytest.raises(HTTPException) as exc_info:
        await rollback_step_revision(
            db=memory_db, run_id=run.id, step_key="step_a",
            revision=1, user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_rollback_wrong_user(memory_db, seed_user, seed_template, seed_run_with_steps):
    """rollback_step_revision：非本人流水线返回 403"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]
    step_a.output_data = _output_with_items(2)
    await memory_db.commit()

    await _add_revision(memory_db, run.id, "step_a", 1, 1, seed_user.id)

    with pytest.raises(HTTPException) as exc_info:
        await rollback_step_revision(
            db=memory_db, run_id=run.id, step_key="step_a",
            revision=1, user_id=seed_user.id + 999,
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_rollback_run_not_found(memory_db, seed_user, seed_template):
    """rollback_step_revision：流水线不存在返回 404"""
    with pytest.raises(HTTPException) as exc_info:
        await rollback_step_revision(
            db=memory_db, run_id=99999, step_key="step_a",
            revision=1, user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_rollback_step_not_found(memory_db, seed_user, seed_template, seed_run_with_steps):
    """rollback_step_revision：步骤不存在返回 404"""
    run = seed_run_with_steps["run"]

    with pytest.raises(HTTPException) as exc_info:
        await rollback_step_revision(
            db=memory_db, run_id=run.id, step_key="not_exists",
            revision=1, user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 404


# ---------- _save_step_output_revision 测试 ----------

@pytest.mark.asyncio
async def test_save_revision_increments_revision_number(memory_db, seed_user, seed_template, seed_run_with_steps):
    """_save_step_output_revision：revision 号递增"""
    run = seed_run_with_steps["run"]

    rev1 = await _save_step_output_revision(
        db=memory_db, run_id=run.id, step_key="step_a",
        output_data=_output_with_items(1), edited_by=seed_user.id,
        change_summary="第一次",
    )
    assert rev1.revision == 1

    rev2 = await _save_step_output_revision(
        db=memory_db, run_id=run.id, step_key="step_a",
        output_data=_output_with_items(2), edited_by=seed_user.id,
        change_summary="第二次",
    )
    assert rev2.revision == 2


@pytest.mark.asyncio
async def test_save_revision_max_limit(memory_db, seed_user, seed_template, seed_run_with_steps):
    """_save_step_output_revision：超过上限时删除最旧版本"""
    run = seed_run_with_steps["run"]

    # 插入 MAX_REVISIONS_PER_RUN + 2 个版本
    total = MAX_REVISIONS_PER_RUN + 2
    for i in range(1, total + 1):
        await _save_step_output_revision(
            db=memory_db, run_id=run.id, step_key="step_a",
            output_data=_output_with_items(i), edited_by=seed_user.id,
            change_summary=f"版本 {i}",
        )

    # 验证数量不超过上限
    count_result = await memory_db.execute(
        select(PipelineStepOutputRevision).where(
            PipelineStepOutputRevision.run_id == run.id,
            PipelineStepOutputRevision.step_key == "step_a",
        )
    )
    revisions = count_result.scalars().all()
    assert len(revisions) == MAX_REVISIONS_PER_RUN

    # 最旧的版本应已被删除（revision=1 应该不存在）
    rev_numbers = [r.revision for r in revisions]
    assert 1 not in rev_numbers
    assert 2 not in rev_numbers  # 删除了 2 个最旧的
    # 最新的版本号应该保留
    assert total in rev_numbers
