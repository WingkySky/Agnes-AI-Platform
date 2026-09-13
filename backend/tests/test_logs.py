# =====================================================
# 日志查询 / 前端错误上报测试
# - 上报：写入归一、字段截断、批量上限、限频、user_id 服务端 stamp
# - 鉴权：未登录 401 / 普通用户 403 / admin 200
# - 白名单：file 参数拒绝白名单外取值
# - 翻页 / 文本日志级别过滤 / 下载 / 清空
# =====================================================

import json
import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.routes import logs as logs_route

# 测试允许读写的日志文件名（固定集合，防测试代码误写其他路径）
_TEST_LOG_FILES = {
    "frontend.jsonl", "frontend.jsonl.1", "frontend.jsonl.2",
    "agnes_platform.log", "agnes_platform.log.3",
}


def _log_path(filename: str) -> str:
    if filename not in _TEST_LOG_FILES:
        raise ValueError(f"测试不允许访问该路径：{filename}")
    base = os.path.realpath(settings.log_dir)
    path = os.path.realpath(os.path.join(base, filename))
    if os.path.dirname(path) != base:
        raise ValueError(f"测试路径越界：{filename}")
    return path


@pytest.fixture(autouse=True)
def _log_env(tmp_path, monkeypatch):
    """日志目录指向临时目录，重置上报 logger 单例与限频状态"""
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    monkeypatch.setattr(logs_route, "_fe_logger", None)
    monkeypatch.setattr(logs_route, "_rate_windows", {})


async def _build_client(memory_db, user=None):
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"} if user else {}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(memory_db):
    admin = User(username="root", email="root@example.com", password_hash="x",
                 role="admin", is_admin=True, credits=0)
    memory_db.add(admin)
    await memory_db.commit()
    await memory_db.refresh(admin)
    async for client in _build_client(memory_db, admin):
        yield client


@pytest_asyncio.fixture
async def anon_client(memory_db):
    async for client in _build_client(memory_db):
        yield client


def _read_lines(filename: str) -> list:
    text = Path(_log_path(filename)).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _write_jsonl(filename: str, entries: list) -> None:
    content = "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries)
    Path(_log_path(filename)).write_text(content, encoding="utf-8")


def _exists(filename: str) -> bool:
    return os.path.exists(_log_path(filename))


# ---------- 上报 ----------

@pytest.mark.asyncio
async def test_report_writes_normalized_entries(anon_client):
    resp = await anon_client.post("/api/logs/frontend", json={"events": [
        {"message": "boom", "stack": "Error: boom\n  at foo", "level": "error", "url": "http://x/login"},
        {"message": "warn-ish", "level": "warning"},
    ]})
    assert resp.status_code == 200
    assert resp.json()["data"]["received"] == 2

    entries = _read_lines("frontend.jsonl")
    assert entries[0]["module"] == "frontend"
    assert entries[0]["level"] == "ERROR"
    assert entries[0]["exception"] == "Error: boom\n  at foo"
    assert entries[0]["timestamp"]  # 服务端生成
    assert entries[0]["context"]["url"] == "http://x/login"
    assert entries[0]["context"]["user_id"] is None
    assert entries[1]["level"] == "WARNING"
    assert entries[1]["context"]["ip"]


@pytest.mark.asyncio
async def test_report_stamps_user_id_from_token(admin_client):
    resp = await admin_client.post("/api/logs/frontend", json={
        "events": [{"message": "boom", "user_id": 999}]})  # 客户端伪造的 user_id 应被忽略
    entry = _read_lines("frontend.jsonl")[0]
    assert resp.json()["data"]["received"] == 1
    assert entry["context"]["user_id"] == 1  # 服务端解析（admin 是库里第一个用户）


@pytest.mark.asyncio
async def test_report_truncates_long_fields(anon_client):
    resp = await anon_client.post("/api/logs/frontend", json={"events": [
        {"message": "m" * 5000, "stack": "s" * 20000},
    ]})
    assert resp.status_code == 200
    entry = _read_lines("frontend.jsonl")[0]
    assert len(entry["message"]) == 2048
    assert len(entry["exception"]) == 8192


@pytest.mark.asyncio
async def test_report_rejects_oversized_batch(anon_client):
    events = [{"message": f"e{i}"} for i in range(51)]
    resp = await anon_client.post("/api/logs/frontend", json={"events": events})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_report_rate_limit_drops_excess(anon_client):
    first = await anon_client.post("/api/logs/frontend", json={
        "events": [{"message": f"e{i}"} for i in range(50)]})
    assert first.json()["data"]["received"] == 50
    # 同一 IP 再来 20 条：超过每分钟 60 条上限，整批丢弃
    second = await anon_client.post("/api/logs/frontend", json={
        "events": [{"message": f"f{i}"} for i in range(20)]})
    assert second.status_code == 200
    assert second.json()["data"]["received"] == 0
    assert len(_read_lines("frontend.jsonl")) == 50


# ---------- 鉴权 ----------

@pytest.mark.asyncio
async def test_query_requires_auth(anon_client):
    resp = await anon_client.get("/api/logs")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_query_forbidden_for_normal_user(auth_client):
    resp = await auth_client.get("/api/logs")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_query_ok_for_admin(admin_client):
    resp = await admin_client.get("/api/logs")
    assert resp.status_code == 200
    assert resp.json()["data"]["logs"] == []


# ---------- file 白名单 ----------

@pytest.mark.asyncio
async def test_query_rejects_file_outside_whitelist(admin_client):
    resp = await admin_client.get("/api/logs", params={"file": "not_in_whitelist.jsonl"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_download_rejects_file_outside_whitelist(admin_client):
    resp = await admin_client.get("/api/logs/download", params={"file": "unknown.log"})
    assert resp.status_code == 400


# ---------- 翻页与过滤 ----------

@pytest.mark.asyncio
async def test_query_before_pagination(admin_client):
    _write_jsonl("frontend.jsonl", [
        {"timestamp": f"2026-09-13T00:00:0{i}+00:00", "level": "ERROR", "message": f"e{i}"}
        for i in range(1, 6)
    ])
    page1 = (await admin_client.get("/api/logs", params={"file": "frontend.jsonl", "limit": 2})).json()["data"]["logs"]
    assert [e["message"] for e in page1] == ["e5", "e4"]
    page2 = (await admin_client.get("/api/logs", params={
        "file": "frontend.jsonl", "limit": 2, "before": page1[-1]["timestamp"]})).json()["data"]["logs"]
    assert [e["message"] for e in page2] == ["e3", "e2"]


@pytest.mark.asyncio
async def test_text_log_level_filter(admin_client):
    lines = (
        "2026-09-13 21:26:41.032 [INFO] [req-1] mod.f:1: hello\n"
        "2026-09-13 21:26:42.032 [ERROR] [req-2] mod.f:2: bad thing\n"
    )
    Path(_log_path("agnes_platform.log")).write_text(lines, encoding="utf-8")
    resp = await admin_client.get("/api/logs", params={"file": "agnes_platform.log", "level": "ERROR"})
    logs = resp.json()["data"]["logs"]
    assert len(logs) == 1
    assert logs[0]["level"] == "ERROR"
    assert logs[0]["timestamp"] == "2026-09-13 21:26:42.032"
    assert "bad thing" in logs[0]["raw"]


# ---------- 下载与清空 ----------

@pytest.mark.asyncio
async def test_download_log(admin_client):
    _write_jsonl("frontend.jsonl", [{"timestamp": "2026-09-13T00:00:00+00:00", "message": "x"}])
    resp = await admin_client.get("/api/logs/download", params={"file": "frontend.jsonl"})
    assert resp.status_code == 200
    assert '"message"' in resp.text


@pytest.mark.asyncio
async def test_download_missing_file(admin_client):
    resp = await admin_client.get("/api/logs/download", params={"file": "errors.jsonl"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_clear_main_file_removes_backups(admin_client):
    _write_jsonl("frontend.jsonl", [{"timestamp": "t", "message": "x"}])
    for suffix in (".1", ".2"):
        _write_jsonl(f"frontend.jsonl{suffix}", [{"message": "old"}])
    resp = await admin_client.delete("/api/logs", params={"file": "frontend.jsonl"})
    assert resp.status_code == 200
    assert resp.json()["data"]["removed"] == ["frontend.jsonl.1", "frontend.jsonl.2"]
    assert _read_lines("frontend.jsonl") == []
    assert not _exists("frontend.jsonl.1")


@pytest.mark.asyncio
async def test_clear_single_backup(admin_client):
    _write_jsonl("agnes_platform.log.3", [{"raw": "old"}])
    resp = await admin_client.delete("/api/logs", params={"file": "agnes_platform.log.3"})
    assert resp.status_code == 200
    assert not _exists("agnes_platform.log.3")


# ---------- 权限点定义 ----------

def test_permission_defs_contains_log_view():
    from app.routes.admin_roles import PERMISSION_DEFS
    keys = {item["key"] for item in PERMISSION_DEFS}
    assert "log:view" in keys
