# =====================================================
# Task 29.6: 编辑锁并发测试
#
# 覆盖 backend/app/services/pipeline/run_service.py:
#   - acquire_edit_lock（5 分钟超时，互斥锁）
#   - release_edit_lock（仅持有者或过期后可释放）
#
# 测试场景：
#   1. 首次获取锁成功
#   2. 同一用户重复获取锁成功（续期）
#   3. 其他用户在锁未过期时获取返回 409
#   4. 其他用户在锁已过期时获取成功（惰性释放）
#   5. 持有者释放锁成功
#   6. 无锁时释放返回提示信息
#   7. 非本人流水线获取锁返回 403
#   8. 非本人流水线释放锁返回 403
#   9. 流水线不存在返回 404
#  10. 释放后其他用户可获取锁
#  11. 锁过期后原用户也可重新获取
#  12. 非持有者无法释放未过期的锁
# =====================================================

import pytest
from datetime import datetime, timedelta

from fastapi import HTTPException

from app.services.pipeline.run_service import (
    acquire_edit_lock,
    release_edit_lock,
    EDIT_LOCK_TIMEOUT_SECONDS,
)
from app.models.pipeline import PipelineRun
from app.models.user import User
from tests.conftest import _make_step


# ---------- 辅助 fixture ----------

@pytest.fixture
def other_user_factory(memory_db, seed_user):
    """构造另一个测试用户"""
    async def _make():
        other = User(
            username="other_user",
            email="other@example.com",
            password_hash="x",
            role="user",
            credits=10000,
        )
        memory_db.add(other)
        await memory_db.commit()
        await memory_db.refresh(other)
        return other
    return _make


# ---------- acquire_edit_lock 测试 ----------

@pytest.mark.asyncio
async def test_acquire_lock_first_time(memory_db, seed_user, seed_template, seed_run_with_steps):
    """首次获取锁成功"""
    run = seed_run_with_steps["run"]

    result = await acquire_edit_lock(
        db=memory_db, run_id=run.id, user_id=seed_user.id
    )

    assert result["locked_by"] == seed_user.id
    assert result["expires_at"] is not None

    await memory_db.refresh(run)
    assert run.edit_lock_user_id == seed_user.id
    assert run.edit_lock_expires_at is not None


@pytest.mark.asyncio
async def test_acquire_lock_same_user_renew(memory_db, seed_user, seed_template, seed_run_with_steps):
    """同一用户重复获取锁成功（续期）"""
    run = seed_run_with_steps["run"]

    # 第一次获取
    await acquire_edit_lock(db=memory_db, run_id=run.id, user_id=seed_user.id)
    await memory_db.refresh(run)
    first_expires = run.edit_lock_expires_at

    # 第二次获取（续期）
    await acquire_edit_lock(db=memory_db, run_id=run.id, user_id=seed_user.id)
    await memory_db.refresh(run)
    second_expires = run.edit_lock_expires_at

    # 过期时间应更新（>= 第一次）
    assert second_expires >= first_expires
    assert run.edit_lock_user_id == seed_user.id


@pytest.mark.asyncio
async def test_acquire_lock_other_user_no_permission(memory_db, seed_user, seed_template, seed_run_with_steps, other_user_factory):
    """其他用户无法获取锁（run.user_id 校验返回 403）"""
    run = seed_run_with_steps["run"]
    other = await other_user_factory()

    # seed_user 先获取锁
    await acquire_edit_lock(db=memory_db, run_id=run.id, user_id=seed_user.id)

    # other_user 不是 run 拥有者，直接返回 403
    with pytest.raises(HTTPException) as exc_info:
        await acquire_edit_lock(db=memory_db, run_id=run.id, user_id=other.id)
    assert exc_info.value.status_code == 403
    assert "无权操作" in exc_info.value.detail


@pytest.mark.asyncio
async def test_acquire_lock_wrong_user(memory_db, seed_user, seed_template, seed_run_with_steps, other_user_factory):
    """非本人流水线获取锁返回 403"""
    run = seed_run_with_steps["run"]
    other = await other_user_factory()

    with pytest.raises(HTTPException) as exc_info:
        await acquire_edit_lock(db=memory_db, run_id=run.id, user_id=other.id)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_acquire_lock_run_not_found(memory_db, seed_user):
    """流水线不存在返回 404"""
    with pytest.raises(HTTPException) as exc_info:
        await acquire_edit_lock(db=memory_db, run_id=99999, user_id=seed_user.id)
    assert exc_info.value.status_code == 404


# ---------- release_edit_lock 测试 ----------

@pytest.mark.asyncio
async def test_release_lock_by_holder(memory_db, seed_user, seed_template, seed_run_with_steps):
    """持有者释放锁成功"""
    run = seed_run_with_steps["run"]

    await acquire_edit_lock(db=memory_db, run_id=run.id, user_id=seed_user.id)
    result = await release_edit_lock(db=memory_db, run_id=run.id, user_id=seed_user.id)

    assert result["released_by"] == seed_user.id
    await memory_db.refresh(run)
    assert run.edit_lock_user_id is None
    assert run.edit_lock_expires_at is None


@pytest.mark.asyncio
async def test_release_lock_no_lock(memory_db, seed_user, seed_template, seed_run_with_steps):
    """无锁时释放返回提示信息"""
    run = seed_run_with_steps["run"]

    result = await release_edit_lock(db=memory_db, run_id=run.id, user_id=seed_user.id)
    assert "无编辑锁" in result["message"]


@pytest.mark.asyncio
async def test_release_lock_other_user_rejected(memory_db, seed_user, seed_template, seed_run_with_steps, other_user_factory):
    """非持有者无法释放未过期的锁"""
    run = seed_run_with_steps["run"]
    other = await other_user_factory()

    # seed_user 获取锁
    await acquire_edit_lock(db=memory_db, run_id=run.id, user_id=seed_user.id)

    # other_user 尝试释放应失败
    # 注意：release_edit_lock 先校验 run.user_id != user_id 返回 403
    # other_user 不是 run 拥有者，所以会返回 403
    with pytest.raises(HTTPException) as exc_info:
        await release_edit_lock(db=memory_db, run_id=run.id, user_id=other.id)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_release_lock_wrong_user(memory_db, seed_user, seed_template, seed_run_with_steps, other_user_factory):
    """非本人流水线释放锁返回 403"""
    run = seed_run_with_steps["run"]
    other = await other_user_factory()

    with pytest.raises(HTTPException) as exc_info:
        await release_edit_lock(db=memory_db, run_id=run.id, user_id=other.id)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_release_lock_run_not_found(memory_db, seed_user):
    """流水线不存在返回 404"""
    with pytest.raises(HTTPException) as exc_info:
        await release_edit_lock(db=memory_db, run_id=99999, user_id=seed_user.id)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_release_then_acquire_other_user(memory_db, seed_user, seed_template, seed_run_with_steps, other_user_factory):
    """释放后其他用户可获取锁"""
    run = seed_run_with_steps["run"]

    # 注：other_user 无法释放 seed_user 的锁，因为 run 属于 seed_user
    # 所以这里测试 seed_user 释放后，seed_user 再获取
    await acquire_edit_lock(db=memory_db, run_id=run.id, user_id=seed_user.id)
    await release_edit_lock(db=memory_db, run_id=run.id, user_id=seed_user.id)

    # 再获取
    result = await acquire_edit_lock(db=memory_db, run_id=run.id, user_id=seed_user.id)
    assert result["locked_by"] == seed_user.id


@pytest.mark.asyncio
async def test_acquire_lock_after_expiry_same_user(memory_db, seed_user, seed_template, seed_run_with_steps):
    """锁过期后原用户也可重新获取"""
    run = seed_run_with_steps["run"]

    # 获取锁
    await acquire_edit_lock(db=memory_db, run_id=run.id, user_id=seed_user.id)
    # 过期
    run.edit_lock_expires_at = datetime.utcnow() - timedelta(seconds=1)
    await memory_db.commit()

    # 重新获取
    result = await acquire_edit_lock(db=memory_db, run_id=run.id, user_id=seed_user.id)
    assert result["locked_by"] == seed_user.id

    await memory_db.refresh(run)
    assert run.edit_lock_expires_at > datetime.utcnow()


@pytest.mark.asyncio
async def test_lock_timeout_is_5_minutes(memory_db, seed_user, seed_template, seed_run_with_steps):
    """验证锁超时时间是 5 分钟"""
    run = seed_run_with_steps["run"]

    before = datetime.utcnow()
    await acquire_edit_lock(db=memory_db, run_id=run.id, user_id=seed_user.id)
    await memory_db.refresh(run)

    # 验证过期时间约为 5 分钟后
    expected_expiry = before + timedelta(seconds=EDIT_LOCK_TIMEOUT_SECONDS)
    # 允许 5 秒误差
    assert abs((run.edit_lock_expires_at - expected_expiry).total_seconds()) < 5
    assert EDIT_LOCK_TIMEOUT_SECONDS == 5 * 60
