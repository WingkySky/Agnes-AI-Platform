# =====================================================
# 任务恢复体系测试（可靠性三件套 ①）
# 账本 pending 行创建/保守初值、终态幂等 upsert、uncertain 对账退款、
# 启动恢复三态（视频续轮询/超限视频对账/图片对账）、轮询端点 DB 回退
# =====================================================

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.generation import Generation
from app.services import _generation_persist as gp
from app.services import task_recovery


def _bind(session):
    """把服务层自建的 new_async_session 打桩到测试内存库"""
    @asynccontextmanager
    async def _fake():
        yield session
    return _fake


@pytest.fixture
def bound_db(memory_db, monkeypatch):
    fake = _bind(memory_db)
    monkeypatch.setattr(gp, "new_async_session", fake)
    monkeypatch.setattr(task_recovery, "new_async_session", fake)
    return memory_db


@pytest.fixture
def refund_spy(monkeypatch):
    calls = []

    async def _spy(session, user_id, ref_id, reason=""):
        calls.append((user_id, ref_id))
        return True

    monkeypatch.setattr(gp, "refund_credits", _spy)
    return calls


def make_row(user_id, kind="image", task_id="t1", status="pending", age_sec=0, **kw):
    kw.setdefault("params", {"model": "m1"})
    return Generation(
        type=kind,
        user_id=user_id,
        prompt="测试提示词",
        model="m1",
        status=status,
        task_id=task_id,
        credits_consumed=10,
        created_at=datetime.utcnow() - timedelta(seconds=age_sec),
        **kw,
    )


def fake_task(user_id, task_id="t1", status="success"):
    return SimpleNamespace(
        user_id=user_id, prompt="测试提示词", task_id=task_id, status=status,
        credits_consumed=10, preset_id=None, context={},
        error_category=None, error_message=None,
        params={"model": "m1", "mode": "text2image", "is_public": False},
    )


# ---------- 账本行创建 ----------

@pytest.mark.asyncio
async def test_pending_row_safe_defaults(bound_db, seed_user):
    await gp.create_pending_generation(
        kind="video", user_id=seed_user.id, prompt="p", model="m1",
        params={"model": "m1"}, mode="text2video", task_id="v1", video_id="vid1",
        credits_consumed=10, preset_id=None, context={"source": "canvas"},
    )
    row = (await bound_db.scalars(
        select(Generation).where(Generation.task_id == "v1")
    )).one()
    assert row.status == "pending"
    assert row.is_public is False          # 不进广场
    assert row.moderation_status == "approved"  # 不进审核队列（队列只查 pending）
    assert row.video_id == "vid1"          # 恢复凭据双存
    assert row.context == {"source": "canvas"}


# ---------- 终态幂等 upsert ----------

@pytest.mark.asyncio
async def test_persist_success_upserts_pending_row(bound_db, seed_user):
    await gp.create_pending_generation(
        kind="image", user_id=seed_user.id, prompt="p", model="m1",
        params={"model": "m1"}, mode="text2image", task_id="t1", credits_consumed=10,
    )
    await gp.persist_generation(
        fake_task(seed_user.id),
        kind="image", result_url="data:image/png;base64,QQ==",
        record_params={"model": "m1", "size": "1024x1024"}, record_task_id="t1",
        log_prefix="[测试]",
    )
    rows = (await bound_db.scalars(select(Generation).where(Generation.task_id == "t1"))).all()
    assert len(rows) == 1                 # 不重复插行
    assert rows[0].status == "success"
    assert rows[0].result_url == "data:image/png;base64,QQ=="
    assert rows[0].credits_consumed == 10


@pytest.mark.asyncio
async def test_persist_failure_upserts_pending_row(bound_db, seed_user):
    await gp.create_pending_generation(
        kind="image", user_id=seed_user.id, prompt="p", model="m1",
        params={"model": "m1"}, mode="text2image", task_id="t1", credits_consumed=10,
    )
    task = fake_task(seed_user.id, status="failed")
    task.error_category = "upstream_error"
    task.error_message = "上游炸了"
    await gp.persist_generation_failure(
        task, kind="image", record_params={"model": "m1"}, record_task_id="t1",
        log_prefix="[测试]",
    )
    rows = (await bound_db.scalars(select(Generation).where(Generation.task_id == "t1"))).all()
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].error_category == "upstream_error"
    assert rows[0].credits_consumed == 0


# ---------- uncertain 对账 ----------

@pytest.mark.asyncio
async def test_finalize_uncertain_marks_and_refunds(bound_db, seed_user, refund_spy):
    bound_db.add(make_row(seed_user.id, task_id="t1"))
    await bound_db.commit()

    done = await gp.finalize_uncertain(
        kind="image", user_id=seed_user.id, task_id="t1", reason="重启中断", log_prefix="[测试]",
    )
    assert done is True
    row = (await bound_db.scalars(select(Generation).where(Generation.task_id == "t1"))).one()
    assert row.status == "uncertain"
    assert row.error_category == "submission_uncertain"
    assert row.credits_consumed == 0
    assert refund_spy == [(seed_user.id, "t1")]

    # 幂等：终态行不再匹配，二次对账 False 且不重复退款
    again = await gp.finalize_uncertain(
        kind="image", user_id=seed_user.id, task_id="t1", reason="重启中断", log_prefix="[测试]",
    )
    assert again is False
    assert len(refund_spy) == 1


@pytest.mark.asyncio
async def test_mark_row_cancelled(bound_db, seed_user):
    bound_db.add(make_row(seed_user.id, task_id="t1"))
    await bound_db.commit()
    await gp.mark_row_cancelled(kind="image", user_id=seed_user.id, record_task_id="t1", log_prefix="[测试]")
    row = (await bound_db.scalars(select(Generation).where(Generation.task_id == "t1"))).one()
    assert row.status == "cancelled"


# ---------- 启动恢复三态 ----------

@pytest.mark.asyncio
async def test_recover_resumes_fresh_video_finalizes_others(bound_db, seed_user, refund_spy, monkeypatch):
    bound_db.add_all([
        make_row(seed_user.id, kind="video", task_id="v_fresh", age_sec=10,
                 video_id="vid_fresh", params={"model": "m1"}, context={"source": "canvas"}),
        make_row(seed_user.id, kind="video", task_id="v_stale", age_sec=99999),
        make_row(seed_user.id, kind="image", task_id="i_lost", age_sec=10),
    ])
    await bound_db.commit()

    resumed = []

    async def _start_polling(**kwargs):
        resumed.append(kwargs)

    monkeypatch.setattr(task_recovery, "poller_manager", SimpleNamespace(start_polling=_start_polling))

    counts = await task_recovery.recover_pending_tasks()
    assert counts == {"video_resumed": 1, "video_finalized": 1, "image_finalized": 1}

    # 新鲜视频：原凭据 + 完整上下文重注册（本地 task_id 不变，前端轮询无感）
    assert resumed == [{
        "task_id": "v_fresh", "video_id": "vid_fresh", "prompt": "测试提示词",
        "params": {"model": "m1"}, "user_id": seed_user.id, "credits_consumed": 10,
        "preset_id": None, "context": {"source": "canvas"},
    }]
    # 超限视频 + 图片行：uncertain + 退款
    assert sorted(ref for _, ref in refund_spy) == ["i_lost", "v_stale"]
    stale = (await bound_db.scalars(
        select(Generation).where(Generation.task_id == "v_stale")
    )).one()
    assert stale.status == "uncertain"


@pytest.mark.asyncio
async def test_recover_empty_noop(bound_db):
    counts = await task_recovery.recover_pending_tasks()
    assert counts == {"video_resumed": 0, "video_finalized": 0, "image_finalized": 0}


# ---------- 轮询端点 DB 回退 ----------

@pytest.mark.asyncio
async def test_image_status_fallback_pending_then_uncertain(auth_client, memory_db, seed_user):
    row = make_row(seed_user.id, task_id="img_x")
    memory_db.add(row)
    await memory_db.commit()

    resp = await auth_client.get("/api/images/tasks/img_x")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["status"] == "pending"    # 保持前端续轮询

    row.status = "uncertain"
    row.error_category = "submission_uncertain"
    row.error_message = "重启中断"
    await memory_db.commit()

    resp = await auth_client.get("/api/images/tasks/img_x")
    body = resp.json()["data"]
    assert body["status"] == "failed"     # uncertain 不外泄（前端终态集合不含它）
    assert body["error_category"] == "submission_uncertain"


@pytest.mark.asyncio
async def test_video_status_fallback_matches_video_id(auth_client, memory_db, seed_user):
    # 上游只返回 video_id 无 task_id 的场景：task_id 列存 real_ref_id（=video_id），按其回退命中
    row = make_row(seed_user.id, kind="video", task_id="vid9", status="processing")
    row.video_id = "vid9"
    memory_db.add(row)
    await memory_db.commit()

    resp = await auth_client.get("/api/videos/vid9")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["status"] == "processing"
    assert body["video_id"] == "vid9"
