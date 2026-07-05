# =====================================================
# Task 29.4: 产物编辑 + 下游 stale 标记测试
#
# 覆盖 backend/app/services/pipeline/run_service.py:
#   - edit_step_output（替换/删除/新增 items）
#   - mark_downstream_stale（传递性下游 stale 标记）
#   - _collect_transitive_downstream（DAG 传递闭包）
#   - _save_step_output_revision（版本快照保存）
#
# 测试场景：
#   1. 整体替换 items：current_items 被覆盖，summary 更新
#   2. 删除指定 item_id：remove_item_ids 生效
#   3. 追加新 items：add_items 生效
#   4. 编辑后下游步骤被标记 stale
#   5. 编辑前保存版本快照到 PipelineStepOutputRevision
#   6. run 状态为 running 时返回 409
#   7. 非本人流水线返回 403
#   8. 流水线/步骤不存在返回 404
#   9. mark_downstream_stale 传递闭包：A→B→C，编辑 A 则 B、C 都 stale
#  10. _collect_transitive_downstream 不含自身
#  11. 兼容字段 images / videos 同步更新
# =====================================================

import pytest
from unittest.mock import patch

from fastapi import HTTPException

from app.services.pipeline.run_service import (
    edit_step_output,
    mark_downstream_stale,
    _collect_transitive_downstream,
)
from app.models.pipeline import PipelineRun, PipelineStep
from app.models.pipeline_step_output_revision import PipelineStepOutputRevision
from tests.conftest import _make_step


# ---------- 辅助函数 ----------

def _make_items(count: int, status: str = "success") -> list:
    """构造 count 个 item"""
    return [
        {"id": f"item_{i+1:03d}", "name": f"项目{i+1}",
         "image_url": f"img_{i+1}.jpg", "status": status, "error": None}
        for i in range(count)
    ]


def _output_with_items(items: list) -> dict:
    """构造包含 items + summary 的 output_data"""
    success = sum(1 for it in items if it.get("status") == "success")
    failed = sum(1 for it in items if it.get("status") == "failed")
    return {
        "items": items,
        "summary": {"total": len(items), "success_count": success, "failed_count": failed},
        "success_count": success,
        "failed_count": failed,
    }


# ---------- edit_step_output 测试 ----------

@pytest.mark.asyncio
async def test_edit_step_output_replace_items(memory_db, seed_user, seed_template, seed_run_with_steps):
    """整体替换 items：current_items 被覆盖，summary 更新"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    # 初始化 step_a 的 output_data
    step_a.output_data = _output_with_items(_make_items(3))
    await memory_db.commit()
    await memory_db.refresh(step_a)

    # 整体替换为 2 个新 item
    new_items = _make_items(2)
    result = await edit_step_output(
        db=memory_db,
        run_id=run.id,
        step_key="step_a",
        items=new_items,
        user_id=seed_user.id,
    )

    assert result["step_key"] == "step_a"
    assert len(result["items"]) == 2
    assert result["success_count"] == 2
    assert result["failed_count"] == 0

    # 验证 DB 已更新
    await memory_db.refresh(step_a)
    assert len(step_a.output_data["items"]) == 2
    assert step_a.output_data["success_count"] == 2


@pytest.mark.asyncio
async def test_edit_step_output_remove_items(memory_db, seed_user, seed_template, seed_run_with_steps):
    """删除指定 item_id：remove_item_ids 生效"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    items = _make_items(3)
    step_a.output_data = _output_with_items(items)
    await memory_db.commit()

    # 删除 item_002
    result = await edit_step_output(
        db=memory_db,
        run_id=run.id,
        step_key="step_a",
        remove_item_ids=["item_002"],
        user_id=seed_user.id,
    )

    assert len(result["items"]) == 2
    ids = [it["id"] for it in result["items"]]
    assert "item_002" not in ids
    assert "item_001" in ids
    assert "item_003" in ids


@pytest.mark.asyncio
async def test_edit_step_output_add_items(memory_db, seed_user, seed_template, seed_run_with_steps):
    """追加新 items：add_items 生效"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    items = _make_items(2)
    step_a.output_data = _output_with_items(items)
    await memory_db.commit()

    # 追加 1 个新 item
    new_item = {"id": "item_new", "name": "新项目",
                "image_url": "new.jpg", "status": "success", "error": None}
    result = await edit_step_output(
        db=memory_db,
        run_id=run.id,
        step_key="step_a",
        add_items=[new_item],
        user_id=seed_user.id,
    )

    assert len(result["items"]) == 3
    ids = [it["id"] for it in result["items"]]
    assert "item_new" in ids


@pytest.mark.asyncio
async def test_edit_step_output_marks_downstream_stale(memory_db, seed_user, seed_template, seed_run_with_steps):
    """编辑后下游步骤被标记 stale（A→B→C 链路）"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]
    step_b = seed_run_with_steps["steps"][1]
    step_c = seed_run_with_steps["steps"][2]

    step_a.output_data = _output_with_items(_make_items(2))
    await memory_db.commit()

    result = await edit_step_output(
        db=memory_db,
        run_id=run.id,
        step_key="step_a",
        items=_make_items(3),
        user_id=seed_user.id,
    )

    # A→B→C，编辑 A 应让 B、C 都 stale
    assert "step_b" in result["downstream_marked_stale"]
    assert "step_c" in result["downstream_marked_stale"]

    # 验证 DB 中 step_b、step_c 的 stale 标记
    await memory_db.refresh(step_b)
    await memory_db.refresh(step_c)
    assert step_b.stale is True
    assert step_c.stale is True
    assert step_b.stale_reason is not None
    assert "step_a" in step_b.stale_reason


@pytest.mark.asyncio
async def test_edit_step_output_saves_revision(memory_db, seed_user, seed_template, seed_run_with_steps):
    """编辑前保存版本快照到 PipelineStepOutputRevision"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    original_items = _make_items(2)
    step_a.output_data = _output_with_items(original_items)
    await memory_db.commit()

    await edit_step_output(
        db=memory_db,
        run_id=run.id,
        step_key="step_a",
        items=_make_items(3),
        user_id=seed_user.id,
    )

    # 验证修订表中有 1 条记录
    from sqlalchemy import select
    revs = (await memory_db.execute(
        select(PipelineStepOutputRevision).where(
            PipelineStepOutputRevision.run_id == run.id,
            PipelineStepOutputRevision.step_key == "step_a",
        )
    )).scalars().all()
    assert len(revs) == 1
    assert revs[0].revision == 1
    assert revs[0].edited_by == seed_user.id
    # 快照应是编辑前的数据（2 个 items）
    assert len(revs[0].output_data["items"]) == 2


@pytest.mark.asyncio
async def test_edit_step_output_running_rejected(memory_db, seed_user, seed_template, seed_run_with_steps):
    """run 状态为 running 时返回 409"""
    run = seed_run_with_steps["run"]
    run.status = "running"
    await memory_db.commit()

    step_a = seed_run_with_steps["steps"][0]
    step_a.output_data = _output_with_items(_make_items(2))
    await memory_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await edit_step_output(
            db=memory_db,
            run_id=run.id,
            step_key="step_a",
            items=_make_items(3),
            user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 409
    assert "运行中" in exc_info.value.detail


@pytest.mark.asyncio
async def test_edit_step_output_wrong_user(memory_db, seed_user, seed_template, seed_run_with_steps):
    """非本人流水线返回 403"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]
    step_a.output_data = _output_with_items(_make_items(1))
    await memory_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await edit_step_output(
            db=memory_db,
            run_id=run.id,
            step_key="step_a",
            items=_make_items(2),
            user_id=seed_user.id + 999,
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_edit_step_output_run_not_found(memory_db, seed_user, seed_template):
    """流水线不存在返回 404"""
    with pytest.raises(HTTPException) as exc_info:
        await edit_step_output(
            db=memory_db,
            run_id=99999,
            step_key="step_a",
            items=_make_items(2),
            user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_edit_step_output_step_not_found(memory_db, seed_user, seed_template, seed_run_with_steps):
    """步骤不存在返回 404"""
    run = seed_run_with_steps["run"]
    with pytest.raises(HTTPException) as exc_info:
        await edit_step_output(
            db=memory_db,
            run_id=run.id,
            step_key="not_exists",
            items=_make_items(2),
            user_id=seed_user.id,
        )
    assert exc_info.value.status_code == 404
    assert "步骤不存在" in exc_info.value.detail


@pytest.mark.asyncio
async def test_edit_step_output_sync_compat_fields(memory_db, seed_user, seed_template, seed_run_with_steps):
    """兼容字段 images / videos 同步更新"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    items = _make_items(2)
    output_data = _output_with_items(items)
    # 加上兼容字段
    output_data["images"] = list(items)
    output_data["videos"] = list(items)
    step_a.output_data = output_data
    await memory_db.commit()

    new_items = _make_items(3)
    await edit_step_output(
        db=memory_db,
        run_id=run.id,
        step_key="step_a",
        items=new_items,
        user_id=seed_user.id,
    )

    await memory_db.refresh(step_a)
    assert len(step_a.output_data["images"]) == 3
    assert len(step_a.output_data["videos"]) == 3


@pytest.mark.asyncio
async def test_edit_step_output_summary_recount(memory_db, seed_user, seed_template, seed_run_with_steps):
    """编辑后 summary 重新统计 success/failed"""
    run = seed_run_with_steps["run"]
    step_a = seed_run_with_steps["steps"][0]

    # 初始：2 个成功
    step_a.output_data = _output_with_items(_make_items(2))
    await memory_db.commit()

    # 替换为：1 成功 + 1 失败
    new_items = [
        {"id": "item_001", "name": "成功", "status": "success"},
        {"id": "item_002", "name": "失败", "status": "failed", "error": "x"},
    ]
    result = await edit_step_output(
        db=memory_db,
        run_id=run.id,
        step_key="step_a",
        items=new_items,
        user_id=seed_user.id,
    )

    assert result["success_count"] == 1
    assert result["failed_count"] == 1

    await memory_db.refresh(step_a)
    assert step_a.output_data["summary"]["success_count"] == 1
    assert step_a.output_data["summary"]["failed_count"] == 1


# ---------- mark_downstream_stale 测试 ----------

@pytest.mark.asyncio
async def test_mark_downstream_stale_transitive(memory_db, seed_user, seed_template, seed_run_with_steps):
    """mark_downstream_stale 传递闭包：A→B→C，编辑 A 则 B、C 都 stale"""
    run = seed_run_with_steps["run"]

    marked = await mark_downstream_stale(
        db=memory_db,
        run_id=run.id,
        edited_step_key="step_a",
        reason="测试标记下游",
    )

    assert set(marked) == {"step_b", "step_c"}

    # 验证 DB
    step_b = seed_run_with_steps["steps"][1]
    step_c = seed_run_with_steps["steps"][2]
    await memory_db.refresh(step_b)
    await memory_db.refresh(step_c)
    assert step_b.stale is True
    assert step_c.stale is True
    assert step_b.stale_reason == "测试标记下游"


@pytest.mark.asyncio
async def test_mark_downstream_stale_middle_node(memory_db, seed_user, seed_template, seed_run_with_steps):
    """编辑中间节点 B，仅 C 被 stale，A 不受影响"""
    run = seed_run_with_steps["run"]

    marked = await mark_downstream_stale(
        db=memory_db,
        run_id=run.id,
        edited_step_key="step_b",
        reason="编辑 B",
    )

    assert set(marked) == {"step_c"}

    step_a = seed_run_with_steps["steps"][0]
    step_c = seed_run_with_steps["steps"][2]
    await memory_db.refresh(step_a)
    await memory_db.refresh(step_c)
    assert step_a.stale is False
    assert step_c.stale is True


@pytest.mark.asyncio
async def test_mark_downstream_stale_leaf_node(memory_db, seed_user, seed_template, seed_run_with_steps):
    """编辑叶子节点 C，无下游被标记"""
    run = seed_run_with_steps["run"]

    marked = await mark_downstream_stale(
        db=memory_db,
        run_id=run.id,
        edited_step_key="step_c",
        reason="编辑 C",
    )

    assert marked == []


# ---------- _collect_transitive_downstream 单元测试 ----------

def test_collect_transitive_downstream_chain():
    """A→B→C 链式依赖：从 A 出发应返回 {B, C}"""
    steps = [
        _make_step(1, "a", "A", "llm_generate", 0),
        _make_step(1, "b", "B", "llm_generate", 1, depends_on=["a"]),
        _make_step(1, "c", "C", "llm_generate", 2, depends_on=["b"]),
    ]
    result = _collect_transitive_downstream(steps, "a")
    assert result == {"b", "c"}


def test_collect_transitive_downstream_diamond():
    """菱形依赖：A→{B,C}→D，从 A 出发应返回 {B, C, D}"""
    steps = [
        _make_step(1, "a", "A", "llm_generate", 0),
        _make_step(1, "b", "B", "llm_generate", 1, depends_on=["a"]),
        _make_step(1, "c", "C", "llm_generate", 1, depends_on=["a"]),
        _make_step(1, "d", "D", "llm_generate", 2, depends_on=["b", "c"]),
    ]
    result = _collect_transitive_downstream(steps, "a")
    assert result == {"b", "c", "d"}


def test_collect_transitive_downstream_excludes_self():
    """结果不包含 root_key 自身"""
    steps = [
        _make_step(1, "a", "A", "llm_generate", 0),
        _make_step(1, "b", "B", "llm_generate", 1, depends_on=["a"]),
    ]
    result = _collect_transitive_downstream(steps, "a")
    assert "a" not in result
    assert result == {"b"}


def test_collect_transitive_downstream_no_downstream():
    """叶子节点无下游"""
    steps = [
        _make_step(1, "a", "A", "llm_generate", 0),
        _make_step(1, "b", "B", "llm_generate", 1, depends_on=["a"]),
    ]
    result = _collect_transitive_downstream(steps, "b")
    assert result == set()


def test_collect_transitive_downstream_unknown_root():
    """未知 root_key 返回空集"""
    steps = [
        _make_step(1, "a", "A", "llm_generate", 0),
    ]
    result = _collect_transitive_downstream(steps, "unknown")
    assert result == set()
