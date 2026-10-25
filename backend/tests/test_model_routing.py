# =====================================================
# 多渠道路由 failover 测试（M1 内核）
# 路由链解析（锚点链首/优先级排序/停用渠道跳过/锚点缺失报错）、
# failover 类目判定（视频提交 5xx 局部覆盖/网络不切/429 可切）、
# 执行器切换行为（切换/不切/耗尽抛最后错误/候选 client 缺失跳过）、
# 唯一约束、delete_model 级联清理路由
# =====================================================

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.api_provider import ApiProvider
from app.models.model_definition import ModelDefinition
from app.models.model_route import ModelRoute
from app.services import model_routing
from app.services import provider_registry as pr_module
from app.services.agnes_client import UpstreamError
from app.services.model_routing import (
    execute_with_failover,
    failover_category,
    resolve_route_chain,
)


def _bind(session):
    """把服务层自建的 new_async_session 打桩到测试内存库"""
    @asynccontextmanager
    async def _fake():
        yield session
    return _fake


@pytest.fixture
def bound_db(memory_db, monkeypatch):
    fake = _bind(memory_db)
    monkeypatch.setattr(model_routing, "new_async_session", fake)
    monkeypatch.setattr(pr_module, "new_async_session", fake)
    return memory_db


async def _seed_provider(db, pid: int, name: str, *, billing_tier: str = "paid", is_active: bool = True):
    db.add(ApiProvider(
        id=pid, name=name, provider_type="agnes", base_url="http://upstream",
        is_active=is_active, is_default=pid == 1, billing_tier=billing_tier,
    ))
    await db.commit()


async def _seed_def(db, model_id: str, provider_id: int, *, type_: str = "image",
                    is_active: bool = True, is_disabled: bool = False):
    db.add(ModelDefinition(
        provider_id=provider_id, model_id=model_id, display_name=model_id,
        type=type_, is_active=is_active, is_disabled=is_disabled,
    ))
    await db.commit()


async def _seed_route(db, anchor: str, provider_id: int, model_id: str, *,
                      priority: int = 0, is_enabled: bool = True):
    route = ModelRoute(
        anchor_model_id=anchor, provider_id=provider_id, model_id=model_id,
        priority=priority, is_enabled=is_enabled,
    )
    db.add(route)
    await db.commit()
    return route


# ---------- 路由链解析 ----------

@pytest.mark.asyncio
async def test_chain_anchor_first_then_priority_order(bound_db):
    await _seed_provider(bound_db, 1, "主渠道")
    await _seed_provider(bound_db, 2, "备用A")
    await _seed_provider(bound_db, 3, "备用B", billing_tier="free")
    await _seed_def(bound_db, "m1", 1)
    await _seed_def(bound_db, "m-b", 2)
    await _seed_def(bound_db, "m-c", 3)
    await _seed_route(bound_db, "m1", 2, "m-b", priority=5)
    await _seed_route(bound_db, "m1", 3, "m-c", priority=1)
    await _seed_route(bound_db, "m1", 2, "m-d", priority=9, is_enabled=False)

    chain = await resolve_route_chain("m1")
    assert [(t.provider_id, t.model_id) for t in chain] == [(1, "m1"), (3, "m-c"), (2, "m-b")]
    assert chain[0].provider_name == "主渠道"
    assert chain[1].billing_tier == "free"  # 档位随渠道透出（跨档警示用）


@pytest.mark.asyncio
async def test_chain_skips_route_of_inactive_provider(bound_db):
    await _seed_provider(bound_db, 1, "主渠道")
    await _seed_provider(bound_db, 2, "停用渠道", is_active=False)
    await _seed_def(bound_db, "m1", 1)
    await _seed_route(bound_db, "m1", 2, "m-b", priority=1)

    chain = await resolve_route_chain("m1")
    assert [(t.provider_id, t.model_id) for t in chain] == [(1, "m1")]


@pytest.mark.asyncio
async def test_chain_anchor_missing_raises(bound_db):
    await _seed_provider(bound_db, 1, "主渠道")
    with pytest.raises(ValueError, match="不存在或已停用"):
        await resolve_route_chain("ghost-model")


@pytest.mark.asyncio
async def test_chain_anchor_disabled_raises(bound_db):
    await _seed_provider(bound_db, 1, "主渠道")
    await _seed_def(bound_db, "m1", 1, is_active=False)
    with pytest.raises(ValueError, match="不存在或已停用"):
        await resolve_route_chain("m1")


# ---------- failover 类目判定 ----------

def test_category_video_submit_http_5xx_switchable():
    # 明确收到 HTTP 拒绝且无凭据 ≠ 结果未知：5xx 参与切换（设计的局部覆盖）
    exc = UpstreamError("上游服务错误", status_code=502)
    assert failover_category(exc, submitted=False, receipt=True) == "upstream_server"


def test_category_video_submit_network_stays_uncertain():
    exc = UpstreamError("连接失败", error_kind="network")
    assert failover_category(exc, submitted=False, receipt=True) == "submission_uncertain"


def test_category_429_rate_limited_regardless_of_receipt():
    exc = UpstreamError("请求过于频繁", status_code=429)
    assert failover_category(exc, submitted=False, receipt=True) == "rate_limited"


def test_category_image_network_by_message():
    assert failover_category(UpstreamError("请求超时", error_kind="network"), submitted=True, receipt=False) == "timeout"
    assert failover_category(UpstreamError("网络连接失败", error_kind="network"), submitted=True, receipt=False) == "network_transient"


# ---------- 执行器 ----------

class FakeClient:
    def __init__(self, results: dict):
        self.results = results
        self.calls: list[str] = []


async def _call(client, target):
    client.calls.append(target.model_id)
    result = client.results.get(target.model_id)
    if isinstance(result, Exception):
        raise result
    return result


@pytest.fixture
def fake_clients(monkeypatch):
    clients: dict[int, FakeClient] = {}
    monkeypatch.setattr(model_routing.provider_registry, "_clients", clients)
    return clients


def _target(pid: int, model: str) -> model_routing.RouteTarget:
    return model_routing.RouteTarget(provider_id=pid, provider_name=f"渠道{pid}", model_id=model)


@pytest.mark.asyncio
async def test_executor_switches_on_rate_limit(fake_clients):
    fake_clients[1] = FakeClient({"m1": UpstreamError("请求过于频繁", status_code=429)})
    fake_clients[2] = FakeClient({"m-b": "ok"})
    targets = [_target(1, "m1"), _target(2, "m-b")]

    result, used = await execute_with_failover(_call, targets, submitted=True, receipt=False)
    assert result == "ok"
    assert used.model_id == "m-b"
    assert fake_clients[1].calls == ["m1"] and fake_clients[2].calls == ["m-b"]


@pytest.mark.asyncio
async def test_executor_no_switch_on_invalid_params(fake_clients):
    fake_clients[1] = FakeClient({"m1": UpstreamError("参数错误", status_code=400)})
    fake_clients[2] = FakeClient({"m-b": "ok"})
    targets = [_target(1, "m1"), _target(2, "m-b")]

    with pytest.raises(UpstreamError):
        await execute_with_failover(_call, targets, submitted=True, receipt=False)
    assert fake_clients[1].calls == ["m1"] and fake_clients[2].calls == []


@pytest.mark.asyncio
async def test_executor_exhausted_raises_last_with_category(fake_clients):
    fake_clients[1] = FakeClient({"m1": UpstreamError("限流一", status_code=429)})
    fake_clients[2] = FakeClient({"m-b": UpstreamError("限流二", status_code=429)})
    targets = [_target(1, "m1"), _target(2, "m-b")]

    with pytest.raises(UpstreamError, match="限流二") as info:
        await execute_with_failover(_call, targets, submitted=True, receipt=False)
    assert getattr(info.value, "_route_category", None) == "rate_limited"


@pytest.mark.asyncio
async def test_executor_skips_candidate_with_missing_client(fake_clients):
    fake_clients[2] = FakeClient({"m-b": "ok"})
    targets = [_target(1, "m1"), _target(2, "m-b")]

    result, used = await execute_with_failover(_call, targets, submitted=True, receipt=False)
    assert result == "ok" and used.provider_id == 2


@pytest.mark.asyncio
async def test_executor_video_submit_network_never_switches(fake_clients):
    fake_clients[1] = FakeClient({"m1": UpstreamError("连接失败", error_kind="network")})
    fake_clients[2] = FakeClient({"m-b": "ok"})
    targets = [_target(1, "m1"), _target(2, "m-b")]

    with pytest.raises(UpstreamError, match="连接失败"):
        await execute_with_failover(_call, targets, submitted=False, receipt=True)
    assert fake_clients[2].calls == []


@pytest.mark.asyncio
async def test_executor_video_submit_http_5xx_switches(fake_clients):
    fake_clients[1] = FakeClient({"m1": UpstreamError("服务错误", status_code=502)})
    fake_clients[2] = FakeClient({"m-b": "ok"})
    targets = [_target(1, "m1"), _target(2, "m-b")]

    result, used = await execute_with_failover(_call, targets, submitted=False, receipt=True)
    assert result == "ok" and used.provider_id == 2


@pytest.mark.asyncio
async def test_executor_no_targets_raises(fake_clients):
    with pytest.raises(RuntimeError, match="无可用生成渠道"):
        await execute_with_failover(_call, [], submitted=True, receipt=False)


# ---------- 约束与级联 ----------

@pytest.mark.asyncio
async def test_route_unique_constraint(memory_db):
    await _seed_provider(memory_db, 1, "主渠道")
    await _seed_route(memory_db, "m1", 1, "m-b")
    with pytest.raises(IntegrityError):
        await _seed_route(memory_db, "m1", 1, "m-b")


@pytest.mark.asyncio
async def test_delete_model_cascades_routes(bound_db):
    await _seed_provider(bound_db, 1, "主渠道")
    await _seed_def(bound_db, "m1", 1)
    await _seed_route(bound_db, "m1", 1, "m-b")

    deleted = await pr_module.provider_registry.delete_model("m1")
    assert deleted is True
    remaining = (await bound_db.scalars(select(ModelRoute).where(ModelRoute.anchor_model_id == "m1"))).all()
    assert remaining == []
