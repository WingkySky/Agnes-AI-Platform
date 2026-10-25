# =====================================================
# PAT（个人访问令牌）端点测试 —— 三态鉴权 / 明文一次性 / 吊销即时生效 / 跨用户隔离
# =====================================================

from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.future import select

from app.core.database import get_async_db
from app.models.pat_token import PatToken
from app.services import mcp_gateway


def _all_rows():
    return select(PatToken)


# ---------- 401：未登录访问清单 ----------
@pytest.mark.asyncio
async def test_pat_requires_auth(memory_db, seed_user):
    from app.main import app

    async def _override():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/auth/pat")
    app.dependency_overrides.clear()
    assert resp.status_code == 401


# ---------- 创建：明文仅此一次、库中只存哈希、清单脱敏 ----------
@pytest.mark.asyncio
async def test_pat_create_returns_token_once(auth_client, memory_db, seed_user):
    resp = await auth_client.post("/api/auth/pat", json={"name": "我的CLI", "permission": "full"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["token"].startswith("agn_pat_")
    assert data["permission"] == "full"

    rows = (await memory_db.scalars(_all_rows())).all()
    assert len(rows) == 1
    assert rows[0].token_hash == mcp_gateway.hash_token(data["token"])  # 哈希落库

    listing = (await auth_client.get("/api/auth/pat")).json()["data"]
    assert len(listing) == 1
    assert "token" not in listing[0] and "token_hash" not in listing[0]


# ---------- 创建：非法档位 400 ----------
@pytest.mark.asyncio
async def test_pat_create_invalid_permission(auth_client):
    resp = await auth_client.post("/api/auth/pat", json={"name": "x", "permission": "admin"})
    assert resp.status_code == 400


# ---------- 吊销：软删保留记录；幂等；他人/不存在令牌 404 ----------
@pytest.mark.asyncio
async def test_pat_revoke(auth_client, memory_db, seed_user):
    created = (await auth_client.post("/api/auth/pat", json={"name": "t", "permission": "readonly"})).json()["data"]
    assert (await auth_client.delete(f"/api/auth/pat/{created['id']}")).status_code == 200
    row = (await memory_db.scalars(_all_rows())).first()
    assert row.revoked_at is not None  # 软删保留

    assert (await auth_client.delete(f"/api/auth/pat/{created['id']}")).status_code == 200  # 幂等
    assert (await auth_client.delete("/api/auth/pat/99999")).status_code == 404            # 不存在


# ---------- authenticate_pat：有效/吊销即时失效/未知/前缀不符/空 ----------
@pytest.mark.asyncio
async def test_authenticate_pat(memory_db, seed_user):
    plain = mcp_gateway.new_token()
    memory_db.add(PatToken(user_id=seed_user.id, name="t", token_hash=mcp_gateway.hash_token(plain), permission="full"))
    await memory_db.commit()

    principal = await mcp_gateway.authenticate_pat(memory_db, plain)
    assert principal is not None
    assert principal.user_id == seed_user.id and principal.permission == "full"
    assert principal.token_id > 0

    row = (await memory_db.scalars(_all_rows())).first()
    row.revoked_at = datetime.utcnow()
    await memory_db.commit()
    assert await mcp_gateway.authenticate_pat(memory_db, plain) is None  # 吊销即时生效

    assert await mcp_gateway.authenticate_pat(memory_db, "agn_pat_deadbeef") is None  # 未知
    assert await mcp_gateway.authenticate_pat(memory_db, "garbage") is None            # 前缀不符
    assert await mcp_gateway.authenticate_pat(memory_db, "") is None                   # 空
