# =====================================================
# 诊断包导出测试（可靠性三件套 ③）
# 鉴权三态、ZIP 内容清单、secret 打码、prompt 截断、结构完整
# =====================================================

import io
import json
import zipfile
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.generation import Generation
from app.models.system_config import SystemConfig
from app.models.user import User

EXPECTED_FILES = {
    "meta.txt",
    "config_sanitized.json",
    "logs/backend.tail.log",
    "logs/frontend.tail.jsonl",
    "logs/errors.tail.jsonl",
    "generations_recent.json",
    "api_calls_recent.json",
    "storage_summary.json",
    "table_stats.json",
}


def _make_client(memory_db, user) -> AsyncClient:
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["Authorization"] = f"Bearer {create_access_token(user.id)}"
    return client


@pytest_asyncio.fixture
async def admin_user(memory_db):
    admin = User(username="diagroot", email="diagroot@example.com", password_hash="x",
                 role="admin", is_admin=True, credits=0)
    memory_db.add(admin)
    await memory_db.commit()
    await memory_db.refresh(admin)
    return admin


# ---------- 鉴权三态 ----------

@pytest.mark.asyncio
async def test_export_requires_admin(memory_db, seed_user, admin_user):
    anon = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    assert (await anon.get("/api/admin/diagnostics/export")).status_code == 401
    await anon.aclose()

    user_client = _make_client(memory_db, seed_user)
    assert (await user_client.get("/api/admin/diagnostics/export")).status_code == 403
    await user_client.aclose()

    admin_client = _make_client(memory_db, admin_user)
    resp = await admin_client.get("/api/admin/diagnostics/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    await admin_client.aclose()


# ---------- 内容清单 / 脱敏 / 截断 ----------

@pytest.mark.asyncio
async def test_zip_contents_sanitized_and_truncated(memory_db, seed_user, admin_user):
    # 带敏感键名的系统配置 + 超长 prompt 生成记录
    memory_db.add(SystemConfig(config_key="smtp_password", config_value="supersecret123",
                               category="smtp", description=""))
    memory_db.add(SystemConfig(config_key="site_name", config_value="Agnes", category="site", description=""))
    memory_db.add(Generation(
        type="image", user_id=seed_user.id, prompt="长" * 500, model="m1",
        status="uncertain", error_category="submission_uncertain", error_message="e" * 900,
        credits_consumed=0, task_id="diag_t1", is_public=False, moderation_status="approved",
        created_at=datetime.utcnow(),
    ))
    await memory_db.commit()

    client = _make_client(memory_db, admin_user)
    resp = await client.get("/api/admin/diagnostics/export")
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = set(zf.namelist())
    assert EXPECTED_FILES <= names
    assert zf.comment.decode() == "Agnes AI Platform diagnostics bundle (sanitized)"

    # 脱敏：secret 值打码且原文不入包；普通键保留
    config = json.loads(zf.read("config_sanitized.json"))
    assert config["system_configs"]["smtp_password"] == "***<len=14>"
    assert config["system_configs"]["site_name"] == "Agnes"
    assert b"supersecret123" not in resp.content

    # 截断：prompt ≤ 201（200 + 省略号）、error ≤ 501
    gens = json.loads(zf.read("generations_recent.json"))
    row = next(g for g in gens if g["task_id"] == "diag_t1")
    assert len(row["prompt"]) <= 201
    assert row["status"] == "uncertain" and row["error_category"] == "submission_uncertain"
    assert len(row["error_message"]) <= 501

    # 结构：meta / 表统计 / 存储摘要
    meta = zf.read("meta.txt").decode()
    assert "version:" in meta and "database: sqlite" in meta
    stats = json.loads(zf.read("table_stats.json"))
    assert {"users", "generations", "storage_objects"} <= set(stats)
    storage = json.loads(zf.read("storage_summary.json"))
    assert {"total_used", "top_users"} <= set(storage)
    await client.aclose()
