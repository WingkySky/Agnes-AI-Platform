# =====================================================
# 多渠道路由 failover 链路集成测试（M2）
# 图片 _gen_loop 接入 failover（成功切换 + route_used 落账本 / 候选耗置 failed）、
# 视频提交路由（route_used 入账本 context / 5xx 耗尽响应 category=upstream_server）、
# 视频轮询锁定提交渠道 / 无快照回退按模型路由
# =====================================================

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from app.models.generation import Generation
from app.services import _generation_persist as gp
from app.services import model_routing
from app.services import provider_registry as pr_module
from app.services.agnes_client import UpstreamError
from app.services.image_poller import ImageTask, image_poller_manager
from app.services.video_poller import VideoTask, poller_manager
from tests.test_model_routing import _seed_def, _seed_provider, _seed_route


def _bind(session):
    """把服务层自建的 new_async_session 打桩到测试内存库"""
    @asynccontextmanager
    async def _fake():
        yield session
    return _fake


@pytest.fixture
def bound_all(memory_db, monkeypatch):
    """绑定 model_routing / _generation_persist / provider_registry 的自建 session"""
    fake = _bind(memory_db)
    monkeypatch.setattr(model_routing, "new_async_session", fake)
    monkeypatch.setattr(gp, "new_async_session", fake)
    monkeypatch.setattr(pr_module, "new_async_session", fake)
    return memory_db


class FakeClient:
    def __init__(self, results: dict, poll_results: list | None = None):
        self.results = results
        self.poll_results = list(poll_results or [])
        self.image_calls: list[str] = []
        self.video_calls: list[str] = []
        self.poll_calls: list[str] = []

    async def create_image(self, **kwargs):
        self.image_calls.append(kwargs.get("model", ""))
        result = self.results.get("image")
        if isinstance(result, Exception):
            raise result
        return result

    async def create_video_task(self, **kwargs):
        self.video_calls.append(kwargs.get("model", ""))
        result = self.results.get("video")
        if isinstance(result, Exception):
            raise result
        return result

    async def poll_video_status(self, **kwargs):
        self.poll_calls.append(kwargs.get("model_name", ""))
        if self.poll_results:
            return self.poll_results.pop(0)
        return {"status": "running"}


@pytest.fixture
def fake_clients(monkeypatch):
    clients: dict[int, FakeClient] = {}
    monkeypatch.setattr(model_routing.provider_registry, "_clients", clients)
    return clients


# ---------- 图片链路 ----------

@pytest.mark.asyncio
async def test_image_failover_success_records_route_used(bound_all, fake_clients):
    db = bound_all
    await _seed_provider(db, 1, "主渠道")
    await _seed_provider(db, 2, "备用渠道", billing_tier="free")
    await _seed_def(db, "m1", 1)
    await _seed_route(db, "m1", 2, "m-b", priority=1)
    fake_clients[1] = FakeClient({"image": UpstreamError("请求过于频繁", status_code=429)})
    fake_clients[2] = FakeClient({"image": {"data": [{"b64_json": "aGVsbG8="}]}})

    task = ImageTask(task_id="img_t1", prompt="测试", params={"model": "m1", "size": "1024x1024"})
    await image_poller_manager._gen_loop(task.task_id, task)

    assert task.status == "success"
    assert fake_clients[1].image_calls == ["m1"]
    assert fake_clients[2].image_calls == ["m-b"]
    record = (await db.scalars(select(Generation).where(Generation.task_id == "img_t1"))).first()
    assert record is not None
    assert record.context["route_used"]["provider_id"] == 2
    assert record.context["route_used"]["model_id"] == "m-b"
    assert record.context["route_used"]["billing_tier"] == "free"


@pytest.mark.asyncio
async def test_image_failover_exhausted_marks_failed(bound_all, fake_clients):
    db = bound_all
    await _seed_provider(db, 1, "主渠道")
    await _seed_provider(db, 2, "备用渠道")
    await _seed_def(db, "m1", 1)
    await _seed_route(db, "m1", 2, "m-b", priority=1)
    fake_clients[1] = FakeClient({"image": UpstreamError("限流一", status_code=429)})
    fake_clients[2] = FakeClient({"image": UpstreamError("限流二", status_code=429)})

    task = ImageTask(task_id="img_t2", prompt="测试", params={"model": "m1"})
    await image_poller_manager._gen_loop(task.task_id, task)

    assert task.status == "failed"
    assert task.error_category == "rate_limited"
    # 发生过渠道切换：失败文案透出尝试渠道数
    assert "已在 2 个渠道间尝试" in (task.error_message or "")
    record = (await db.scalars(select(Generation).where(Generation.task_id == "img_t2"))).first()
    assert record is not None and record.status == "failed"


@pytest.mark.asyncio
async def test_image_anchor_missing_fails_with_model_missing(bound_all, fake_clients):
    await _seed_provider(bound_all, 1, "主渠道")
    fake_clients[1] = FakeClient({"image": {"data": [{"b64_json": "aGk="}]}})

    task = ImageTask(task_id="img_t3", prompt="测试", params={"model": "ghost"})
    await image_poller_manager._gen_loop(task.task_id, task)

    assert task.status == "failed"
    assert task.error_category == "model_missing"


# ---------- 视频提交链路（路由级） ----------

@pytest.mark.asyncio
async def test_video_submit_failover_and_route_used_in_ledger(bound_all, fake_clients, auth_client):
    db = bound_all
    await _seed_provider(db, 1, "主渠道")
    await _seed_provider(db, 2, "备用渠道")
    await _seed_def(db, "v1", 1, type_="video")
    await _seed_def(db, "v2", 2, type_="video")
    await _seed_route(db, "v1", 2, "v2", priority=1)
    fake_clients[1] = FakeClient({"video": UpstreamError("服务错误", status_code=502)})
    fake_clients[2] = FakeClient({"video": {"data": [{"task_id": "up-123"}]}},
                                 poll_results=[{"status": "failed", "error": "上游判死"}])

    resp = await auth_client.post("/api/videos", json={"prompt": "测试", "model": "v1", "seconds": 5})
    assert resp.status_code == 200, resp.text
    assert fake_clients[1].video_calls == ["v1"]
    assert fake_clients[2].video_calls == ["v2"]

    record = (await db.scalars(select(Generation).where(Generation.task_id == "up-123"))).first()
    assert record is not None
    assert record.context["route_used"]["provider_id"] == 2
    assert record.context["route_used"]["model_id"] == "v2"


@pytest.mark.asyncio
async def test_video_submit_exhausted_5xx_category_upstream_server(bound_all, fake_clients, auth_client):
    db = bound_all
    await _seed_provider(db, 1, "主渠道")
    await _seed_provider(db, 2, "备用渠道")
    await _seed_def(db, "v1", 1, type_="video")
    await _seed_route(db, "v1", 2, "v2", priority=1)
    fake_clients[1] = FakeClient({"video": UpstreamError("网关错误一", status_code=502)})
    fake_clients[2] = FakeClient({"video": UpstreamError("网关错误二", status_code=503)})

    resp = await auth_client.post("/api/videos", json={"prompt": "测试", "model": "v1", "seconds": 5})
    assert resp.status_code == 502
    body = resp.json()
    # 提交阶段明确 HTTP 拒绝 ≠ 结果未知：耗尽后归 upstream_server 而非 submission_uncertain
    assert body["category"] == "upstream_server"
    assert "已在 2 个渠道间尝试" in body["detail"]


# ---------- 视频轮询锁定 ----------

@pytest.mark.asyncio
async def test_poll_loop_locks_submitted_provider(bound_all, fake_clients):
    db = bound_all
    await _seed_provider(db, 1, "主渠道")
    await _seed_provider(db, 2, "提交渠道")
    await _seed_def(db, "v1", 1, type_="video")
    fake_clients[1] = FakeClient({})
    locked = FakeClient({}, poll_results=[{"status": "failed", "error": "上游判死"}])
    fake_clients[2] = locked

    task = VideoTask(
        task_id="up-9", video_id=None, prompt="测试",
        params={"model": "v1", "mode": "text2video"},
        context={"route_used": {"provider_id": 2, "provider_name": "提交渠道", "model_id": "v2"}},
    )
    await poller_manager._poll_loop("up-9", task)

    assert task.status == "failed"
    assert locked.poll_calls == ["v2"]
    assert fake_clients[1].poll_calls == []


@pytest.mark.asyncio
async def test_poll_loop_falls_back_without_route_used(bound_all, fake_clients):
    db = bound_all
    await _seed_provider(db, 1, "主渠道")
    await _seed_def(db, "v1", 1, type_="video")
    fallback = FakeClient({}, poll_results=[{"status": "failed", "error": "上游判死"}])
    fake_clients[1] = fallback

    task = VideoTask(
        task_id="up-8", video_id=None, prompt="测试",
        params={"model": "v1", "mode": "text2video"},
        context=None,  # 存量任务无路由快照 → 回退按模型路由
    )
    await poller_manager._poll_loop("up-8", task)

    assert task.status == "failed"
    assert fallback.poll_calls == ["v1"]
