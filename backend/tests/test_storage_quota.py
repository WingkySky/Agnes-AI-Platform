# =====================================================
# 存储配额测试（可靠性三件套 ②）
# 预检两维度（总量/滚动 24h 上传）与 0=不限、记账幂等与 S3 件跳过、
# 存量回填幂等、usage/overview 端点鉴权三态、canvas 上传超限 413 集成
# =====================================================

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient, ASGITransport

from sqlalchemy import select

from app.main import app
from app.core.database import get_async_db
from app.core.security import create_access_token
from app.models.asset import Asset
from app.models.storage_object import StorageObject
from app.models.user import User
from app.services import storage_quota
from app.services.system_config_service import set_config_value

KB = 1024


def _bind(session):
    @asynccontextmanager
    async def _fake():
        yield session
    return _fake


@pytest.fixture
def bound_db(memory_db, monkeypatch):
    """storage_quota 自建 session 打桩到内存库"""
    fake = _bind(memory_db)
    monkeypatch.setattr(storage_quota, "new_async_session", fake)
    return memory_db


@pytest.fixture(autouse=True)
def _reset_config_cache():
    """本模块改过 storage_quota_mb/daily_upload_quota_mb，测试后清空系统配置内存缓存，
    防止 60s TTL 缓存把测试配额泄漏给其他测试文件"""
    yield
    from app.services import system_config_service as scs
    scs._config_cache.clear()


async def _set_quota(memory_db, total_mb, daily_mb):
    await set_config_value(memory_db, "storage_quota_mb", "0" if total_mb is None else str(total_mb))
    await set_config_value(memory_db, "daily_upload_quota_mb", "0" if daily_mb is None else str(daily_mb))


def _row(user_id, key, size, source="upload", age_hours=0):
    return StorageObject(
        user_id=user_id, storage_key=key, bytes=size, kind="image",
        source=source, created_at=datetime.utcnow() - timedelta(hours=age_hours),
    )


def _make_client(memory_db, user: User) -> AsyncClient:
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["Authorization"] = f"Bearer {create_access_token(user.id)}"
    return client


# ---------- 预检 ----------

@pytest.mark.asyncio
async def test_quota_unlimited_when_zero(bound_db, seed_user):
    await _set_quota(bound_db, None, None)
    bound_db.add(_row(seed_user.id, "a/big.png", 10 * 1024 * 1024))
    await bound_db.commit()
    await storage_quota.check_upload_quota(seed_user.id, 9 * 1024 * 1024)  # 不抛


@pytest.mark.asyncio
async def test_quota_total_exceeded(bound_db, seed_user):
    await _set_quota(bound_db, 1, None)  # 总 1MB
    bound_db.add(_row(seed_user.id, "a/old.png", 900 * KB))
    await bound_db.commit()
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        await storage_quota.check_upload_quota(seed_user.id, 200 * KB)
    assert ei.value.status_code == 413
    assert "存储空间已满" in ei.value.detail


@pytest.mark.asyncio
async def test_quota_daily_only_counts_uploads(bound_db, seed_user):
    await _set_quota(bound_db, None, 1)  # 每日 1MB
    bound_db.add(_row(seed_user.id, "gen/old.png", 900 * KB, source="generation"))
    bound_db.add(_row(seed_user.id, "up/recent.png", 800 * KB, source="upload", age_hours=2))
    bound_db.add(_row(seed_user.id, "up/old.png", 900 * KB, source="upload", age_hours=30))
    await bound_db.commit()
    from fastapi import HTTPException

    # 归档件不计入每日；30h 前的上传已滑出滚动窗口 → 900KB + 200KB 未超 1MB
    await storage_quota.check_upload_quota(seed_user.id, 200 * KB)
    # 再来 1MB → 超每日窗口
    with pytest.raises(HTTPException) as ei:
        await storage_quota.check_upload_quota(seed_user.id, 1024 * KB)
    assert "24 小时上传上限" in ei.value.detail


# ---------- 记账 ----------

@pytest.mark.asyncio
async def test_record_file_idempotent_and_s3_skip(bound_db, seed_user):
    await storage_quota.record_file(user_id=seed_user.id, storage_key="canvas/assets/x.png",
                                    source="upload", bytes_size=123)
    await storage_quota.record_file(user_id=seed_user.id, storage_key="canvas/assets/x.png",
                                    source="upload", bytes_size=123)  # 幂等
    rows = (await bound_db.scalars(select(StorageObject))).all()
    assert len(rows) == 1 and rows[0].bytes == 123 and rows[0].kind == "image"

    # S3 件（本地无此文件且未给 bytes）→ 跳过
    await storage_quota.record_file(user_id=seed_user.id, storage_key="generated/video/2026-01/9.mp4",
                                    source="generation")
    assert len((await bound_db.scalars(select(StorageObject))).all()) == 1


# ---------- 存量回填（hermetic：模拟本地文件存在，不触真实磁盘） ----------

@pytest.mark.asyncio
async def test_ensure_storage_ledger_idempotent(bound_db, seed_user, monkeypatch):
    key = "assets/2026-01/quota_test.png"
    bound_db.add(Asset(type="material", name="t", visual_description="v",
                       user_id=seed_user.id, storage_key=key))
    await bound_db.commit()

    # 模拟该 key 对应本地文件存在且 2048 字节
    monkeypatch.setattr(
        storage_quota, "_local_abs_path",
        lambda k: f"/fake/uploads/{k}" if k == key else None,
    )
    monkeypatch.setattr(os.path, "getsize", lambda p: 2048)

    added = await storage_quota.ensure_storage_ledger(bound_db)
    assert added == 1
    row = (await bound_db.scalars(
        select(StorageObject).where(StorageObject.storage_key == key)
    )).one()
    assert row.bytes == 2048 and row.source == "generation" and row.user_id == seed_user.id

    again = await storage_quota.ensure_storage_ledger(bound_db)
    assert again == 0  # 幂等


# ---------- 端点 ----------

@pytest.mark.asyncio
async def test_usage_endpoint_auth(bound_db, seed_user):
    bound_db.add(_row(seed_user.id, "a/1.png", 5 * KB))
    await bound_db.commit()

    client = _make_client(bound_db, seed_user)
    resp = await client.get("/api/storage/usage")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_used"] == 5 * KB

    anon = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    assert (await anon.get("/api/storage/usage")).status_code == 401
    await anon.aclose()
    await client.aclose()


@pytest.mark.asyncio
async def test_overview_endpoint_requires_admin(bound_db, seed_user):
    await _set_quota(bound_db, 2, None)
    bound_db.add(_row(seed_user.id, "a/1.png", 5 * KB))
    await bound_db.commit()

    user_client = _make_client(bound_db, seed_user)
    assert (await user_client.get("/api/admin/storage/overview")).status_code == 403
    await user_client.aclose()

    admin = User(username="root", email="root@example.com", password_hash="x",
                 role="admin", is_admin=True, credits=0)
    bound_db.add(admin)
    await bound_db.commit()
    await bound_db.refresh(admin)
    admin_client = _make_client(bound_db, admin)
    resp = await admin_client.get("/api/admin/storage/overview")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total_used"] == 5 * KB
    assert body["top_users"][0]["user_id"] == seed_user.id
    assert body["default_quota"] == 2 * 1024 * 1024
    await admin_client.aclose()


# ---------- canvas 上传 413 集成 ----------

@pytest.mark.asyncio
async def test_canvas_upload_rejected_when_quota_full(bound_db, seed_user):
    await _set_quota(bound_db, 1, None)
    bound_db.add(_row(seed_user.id, "canvas/assets/full.png", 1024 * KB))
    await bound_db.commit()

    client = _make_client(bound_db, seed_user)
    resp = await client.post(
        "/api/uploads/canvas",
        files={"file": ("a.png", b"x" * 100, "image/png")},
    )
    assert resp.status_code == 413
    assert "存储空间已满" in resp.json()["detail"]
    await client.aclose()
