# =====================================================
# 首启初始化测试
#   - /api/setup/bootstrap：免登录查询 admin_exists / 创建首个管理员（无管理员 200、已有 409、用户名冲突 409、校验 422）
#   - /api/setup/status：未登录 401 / 登录 200（provider_pending 仅管理员且无 Provider 时 true）
#   - /api/setup/complete：未登录 401 / 普通用户 403 / admin 200，幂等
#   - ensure 链路：env 种子条件化 / 重复执行幂等 / 官方卡刷新字段 / 积分规则不覆盖
# =====================================================

import pytest
import pytest_asyncio
from sqlalchemy import select
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.credit_rule import DEFAULT_CREDIT_RULES, CreditRule
from app.models.prompt_preset import PromptPreset
from app.models.user import ROLE_ADMIN, User
from app.seed import admin_config
from app.seed.ensure import (
    ensure_default_admin,
    ensure_default_credit_rules,
    ensure_official_presets,
    ensure_pipeline_seed,
)
from app.seed.official_presets import (
    OFFICIAL_CAMERAS,
    OFFICIAL_EFFECTS,
    OFFICIAL_SKILLS,
    OFFICIAL_STYLES,
)
from app.seed.pipeline_seed import BUILTIN_STYLES
from app.services import system_config_service

# 官方风格卡 = 硬编码 15 张 + StylePreset 内置行派生 12 张
OFFICIAL_CARD_TOTAL = (
    len(OFFICIAL_STYLES) + len(BUILTIN_STYLES)
    + len(OFFICIAL_SKILLS) + len(OFFICIAL_EFFECTS) + len(OFFICIAL_CAMERAS)
)


@pytest.fixture(autouse=True)
def _clear_config_cache():
    """system_config 有 60s TTL 模块级缓存，测试间必须清空防串扰"""
    system_config_service._config_cache.clear()
    yield
    system_config_service._config_cache.clear()


# ---------- HTTP 客户端工具（同 test_providers_auth 范式） ----------

async def _build_client(memory_db, user=None):
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"} if user else {}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
    app.dependency_overrides.clear()


async def _seed_user(memory_db, username: str, role: str = "user", is_admin: bool = False):
    user = User(username=username, email=f"{username}@example.com", password_hash="x",
                role=role, is_admin=is_admin, credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    return user


@pytest.fixture
def _seed_creds(monkeypatch):
    """种子凭据打桩：模拟部署者显式设置 ADMIN_USERNAME/ADMIN_PASSWORD"""
    monkeypatch.setattr(admin_config, "seed_credentials", lambda: ("admin", "adm12345"))


# ---------- /api/setup/bootstrap（免登录） ----------

@pytest.mark.asyncio
async def test_bootstrap_status_empty_db(memory_db):
    async for client in _build_client(memory_db):
        resp = await client.get("/api/setup/bootstrap")
    assert resp.status_code == 200
    assert resp.json()["data"]["admin_exists"] is False


@pytest.mark.asyncio
async def test_bootstrap_status_with_admin(memory_db):
    await _seed_user(memory_db, "root", role="admin", is_admin=True)
    async for client in _build_client(memory_db):
        resp = await client.get("/api/setup/bootstrap")
    assert resp.status_code == 200
    assert resp.json()["data"]["admin_exists"] is True


@pytest.mark.asyncio
async def test_bootstrap_create_admin_and_token_works(memory_db):
    async for client in _build_client(memory_db):
        resp = await client.post("/api/setup/bootstrap", json={
            "username": "root", "password": "secret123",
        })
    assert resp.status_code == 200
    token = resp.json()["data"]["access_token"]
    assert token

    # 签发的 token 可直接通过鉴权且身份为管理员
    async for client in _build_client(memory_db):
        me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    me_body = me.json()["data"]
    assert me_body["username"] == "root"
    assert me_body["is_admin"] is True


@pytest.mark.asyncio
async def test_bootstrap_conflict_when_admin_exists(memory_db):
    await _seed_user(memory_db, "root", role="admin", is_admin=True)
    async for client in _build_client(memory_db):
        resp = await client.post("/api/setup/bootstrap", json={
            "username": "another", "password": "secret123",
        })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_bootstrap_username_taken_by_normal_user(memory_db):
    await _seed_user(memory_db, "taken")
    async for client in _build_client(memory_db):
        resp = await client.post("/api/setup/bootstrap", json={
            "username": "taken", "password": "secret123",
        })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_bootstrap_validation_400(memory_db):
    """校验失败走全局 RequestValidationError 处理器（项目惯例返回 400 中文提示）"""
    async for client in _build_client(memory_db):
        short_pw = await client.post("/api/setup/bootstrap", json={
            "username": "root", "password": "123",
        })
        bad_name = await client.post("/api/setup/bootstrap", json={
            "username": "bad name!", "password": "secret123",
        })
    assert short_pw.status_code == 400
    assert bad_name.status_code == 400


# ---------- /api/setup/status ----------

@pytest.mark.asyncio
async def test_status_anon_401(memory_db):
    async for client in _build_client(memory_db):
        resp = await client.get("/api/setup/status")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_status_admin_provider_pending_true(memory_db):
    admin = await _seed_user(memory_db, "root", role="admin", is_admin=True)
    async for client in _build_client(memory_db, admin):
        resp = await client.get("/api/setup/status")
    body = resp.json()["data"]
    assert resp.status_code == 200
    assert body["provider_pending"] is True
    assert body["setup_completed"] is False


@pytest.mark.asyncio
async def test_status_normal_user_provider_pending_false(memory_db):
    user = await _seed_user(memory_db, "u1")
    async for client in _build_client(memory_db, user):
        resp = await client.get("/api/setup/status")
    body = resp.json()["data"]
    # 非管理员不探测 Provider 状态
    assert body["provider_pending"] is False
    assert body["setup_completed"] is False


# ---------- /api/setup/complete ----------

@pytest.mark.asyncio
async def test_complete_anon_401(memory_db):
    async for client in _build_client(memory_db):
        resp = await client.post("/api/setup/complete")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_complete_normal_user_403(memory_db):
    user = await _seed_user(memory_db, "u1")
    async for client in _build_client(memory_db, user):
        resp = await client.post("/api/setup/complete")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_complete_admin_200_and_idempotent(memory_db):
    admin = await _seed_user(memory_db, "root", role="admin", is_admin=True)
    async for client in _build_client(memory_db, admin):
        first = await client.post("/api/setup/complete")
        second = await client.post("/api/setup/complete")
        status = await client.get("/api/setup/status")
    assert first.status_code == 200
    assert second.status_code == 200
    assert status.json()["data"]["setup_completed"] is True


# ---------- ensure 链路 ----------

@pytest.mark.asyncio
async def test_ensure_default_admin_creates_on_empty(memory_db, _seed_creds):
    await ensure_default_admin(memory_db)
    admin = (await memory_db.scalars(
        select(User).filter(User.username == "admin")
    )).first()
    assert admin is not None
    assert admin.is_admin is True


@pytest.mark.asyncio
async def test_ensure_default_admin_skips_without_env(memory_db, monkeypatch):
    """未显式设置 ADMIN_USERNAME/ADMIN_PASSWORD 时不种任何账号（首启走向导）"""
    monkeypatch.setattr(admin_config, "seed_credentials", lambda: None)
    await ensure_default_admin(memory_db)
    assert (await memory_db.scalars(select(User))).first() is None


@pytest.mark.asyncio
async def test_ensure_default_admin_skips_when_exists(memory_db, _seed_creds):
    await _seed_user(memory_db, "existing_admin", role="admin", is_admin=True)
    await ensure_default_admin(memory_db)
    admins = (await memory_db.scalars(
        select(User).filter(User.role == ROLE_ADMIN)
    )).all()
    assert len(admins) == 1
    assert admins[0].username == "existing_admin"


@pytest.mark.asyncio
async def test_ensure_credit_rules_insert_and_no_override(memory_db):
    await ensure_default_credit_rules(memory_db)
    keys_before = set((await memory_db.scalars(select(CreditRule.rule_key))).all())
    assert keys_before == {r["rule_key"] for r in DEFAULT_CREDIT_RULES}

    # 已有规则不被覆盖
    rule = (await memory_db.scalars(
        select(CreditRule).filter(CreditRule.rule_key == keys_before.pop())
    )).first()
    rule.value = 999
    await memory_db.commit()
    await ensure_default_credit_rules(memory_db)
    await memory_db.refresh(rule)
    assert rule.value == 999


@pytest.mark.asyncio
async def test_ensure_pipeline_seed_and_official_presets(memory_db):
    # 空库：先流水线种子（官方风格卡依赖 StylePreset 内置行），再官方预设
    await ensure_pipeline_seed(memory_db)
    await ensure_official_presets(memory_db)

    cards = (await memory_db.scalars(select(PromptPreset))).all()
    assert len(cards) == OFFICIAL_CARD_TOTAL
    assert all(c.is_official and c.is_public and c.user_id is None for c in cards)

    # 幂等：重复执行不新增
    await ensure_pipeline_seed(memory_db)
    await ensure_official_presets(memory_db)
    cards_after = (await memory_db.scalars(select(PromptPreset))).all()
    assert len(cards_after) == OFFICIAL_CARD_TOTAL

    # 官方卡字段被种子刷新（含封面路径指向 /seed-assets）
    cinematic = next(c for c in cards_after if c.type == "style" and c.name == "电影感")
    assert cinematic.cover_image == "/seed-assets/style-cinematic.webp"
    cinematic.description = "被篡改的描述"
    await memory_db.commit()
    await ensure_official_presets(memory_db)
    refreshed = (await memory_db.scalars(
        select(PromptPreset).filter(PromptPreset.name == "电影感")
    )).all()
    assert len(refreshed) == 1
    assert refreshed[0].description != "被篡改的描述"
    assert refreshed[0].prompt_config == {"suffix": "电影感，戏剧性光照，宽银幕"}


@pytest.mark.asyncio
async def test_ensure_official_presets_respects_user_card(memory_db):
    """用户同名卡（非官方）不被种子覆盖或删除"""
    memory_db.add(PromptPreset(
        name="电影感", type="style", category="风格插画", description="我的自定义卡",
        prompt_text="", prompt_config={"suffix": "自定义"}, user_id=1,
        is_official=False, is_public=False, is_approved=False,
    ))
    await memory_db.commit()

    await ensure_pipeline_seed(memory_db)
    await ensure_official_presets(memory_db)

    cards = (await memory_db.scalars(
        select(PromptPreset).filter(PromptPreset.name == "电影感")
    )).all()
    assert len(cards) == 2  # 用户卡与官方卡并存
    user_card = next(c for c in cards if not c.is_official)
    assert user_card.prompt_config == {"suffix": "自定义"}
